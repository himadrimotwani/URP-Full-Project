"""
Negotiation routes for contract proposals and chat.
"""

from functools import wraps

from fastapi import APIRouter, HTTPException

from simulation.core import Contract
from app.schemas import (
    NegotiateRequest,
    NegotiateResponse,
    NegotiationChatRequest,
    NegotiationChatResponse,
    AcceptCounterRequest,
    AcceptCounterResponse,
)
from app.services.game_service import (
    is_game_over,
    has_active_contract,
    to_game_state_response,
    to_contract_data,
)
from app.services.negotiation_service import supplier_evaluate_contract
from app.services.config_service import load_negotiation_config
from app.services.ai_service import generate_chat_response
from app.services.game_service import SESSIONS
from app.services.storage_service import log_chat_record

router = APIRouter()


def serialize_negotiation(handler):
    """Keep chat, proposal, and offer decisions atomic within each session."""
    @wraps(handler)
    def wrapped(request):
        state = SESSIONS.get(request.session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")
        with state.negotiation_lock:
            return handler(request)
    return wrapped


@router.post("/game/negotiate", response_model=NegotiateResponse)
@serialize_negotiation
def negotiate(request: NegotiateRequest) -> NegotiateResponse:
    """
    Handles initial contract proposal from the student.
    
    Inputs:
        request: NegotiateRequest containing:
            - session_id: Game session identifier
            - All contract terms (wholesale_price, buyback_price, length, contract_type)
    
    What happens:
        Validates session exists and game is not over.
        Checks if there's already an active contract (can't negotiate if one exists).
        Saves any previous negotiation to history before starting new one.
        Clears previous negotiation state (chat history, draft contract).
        Stores the initial contract type (cannot be changed during negotiation).
        Validates proposal against negotiation config (length ranges, etc.).
        Builds a Contract object from the proposal.
        Evaluates proposal using AI (accept or reject only, no counters).
        If accepted: makes contract active, saves negotiation to history, clears negotiation state.
        If rejected: adds rejection message to chat history, allows student to enter chat.
    
    Output:
        Returns a NegotiateResponse containing:
        - Updated game state
        - AI decision message
        - Decision ("accept" or "reject")
        - Counter contract (always None for initial proposals)
    
    Context:
        Called when student submits initial contract proposal.
        First step in the negotiation flow.
        Counteroffers only come after conversation in the chat.
    """
    session_id = request.session_id
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is over. Start a new game.",
        )
    
    if has_active_contract(state):
        raise HTTPException(
            status_code=400,
            detail="A contract is already active. Wait until it expires before proposing a new one.",
        )

    # Save previous negotiation to history if it exists (before clearing)
    # This preserves chat history for logging and analysis
    if state.negotiation_chat_history or state.negotiation_draft_contract:
        from datetime import datetime
        previous_negotiation = {
            "chat_messages": list(state.negotiation_chat_history),  # Copy the list to preserve it
            "final_decision": None,  # Previous negotiation didn't complete, so no final decision
            "final_contract": None,  # No contract was agreed upon
            "start_time": None,  # Start time not available for previous negotiation
            "end_time": datetime.now().isoformat(),  # Mark end time when new negotiation starts
        }
        state.negotiation_history.append(previous_negotiation)
        log_chat_record(
            participant_id=state.participant_id,
            session_id=session_id,
            negotiation_record=previous_negotiation,
        )
    
    # Clear previous negotiation state when starting a NEW negotiation
    # This ensures each negotiation attempt has its own clean chat history
    # (prevents mixing chat history from previous negotiations)
    from datetime import datetime
    state.negotiation_chat_history = []  # Start fresh chat history
    state.negotiation_draft_contract = None  # Clear any previous draft
    state.negotiation_offer_version += 1
    # Store start time for this negotiation (will be added to history when negotiation ends)
    state._current_negotiation_start_time = datetime.now().isoformat()

    # Validate against negotiation config to ensure proposal meets instructor's constraints
    neg_config = load_negotiation_config()
    
    # Check contract type is allowed (instructor may restrict available types)
    if request.contract_type not in neg_config.contract_types_available:
        raise HTTPException(
            status_code=400,
            detail=f"Contract type '{request.contract_type}' is not available. Available types: {', '.join(neg_config.contract_types_available)}",
        )
    
    # Check length is within range
    if request.length < neg_config.length_min or request.length > neg_config.length_max:
        raise HTTPException(
            status_code=400,
            detail=f"Contract length must be between {neg_config.length_min} and {neg_config.length_max} rounds.",
        )
    
    # Build a temporary Contract object from buyer's proposal
    # This is used for evaluation - will become active if accepted
    proposed = Contract(
        wholesale_price=request.wholesale_price,
        buyback_price=request.buyback_price,
        length=request.length,
        contract_type=request.contract_type,
    )
    
    # Store the initial contract type - it cannot be changed during negotiation
    # This ensures student can't switch contract type after the initial proposal
    state.initial_contract_type = request.contract_type

    # Evaluate the proposal using AI (returns accept or reject, never counter on initial proposal)
    decision, ai_message, counter_contract = supplier_evaluate_contract(
        proposed,
        state.personality
    )
    counter_contract_data = None

    # Handle the supplier's decision
    if decision == "accept":
        # Contract becomes active immediately - student can now place orders
        state.contract = proposed
        state.contract.remaining_rounds = proposed.length  # Initialize remaining rounds
        
        # Save current negotiation to history before clearing
        # This preserves the negotiation session for game summary
        from datetime import datetime
        negotiation_record = {
            "chat_messages": list(state.negotiation_chat_history),  # May be empty if accepted immediately
            "final_decision": "accept",  # Negotiation ended with acceptance
            "final_contract": to_contract_data(proposed),  # The accepted contract
            "start_time": getattr(state, "_current_negotiation_start_time", None),
            "end_time": datetime.now().isoformat(),  # Mark end time when contract becomes active
        }
        state.negotiation_history.append(negotiation_record)
        log_chat_record(
            participant_id=state.participant_id,
            session_id=session_id,
            negotiation_record=negotiation_record,
        )
        
        # Clear negotiation state since negotiation is complete
        state.negotiation_chat_history = []
        state.negotiation_draft_contract = None
        state._current_negotiation_start_time = None

    elif decision == "counter":
        # Store counter as draft for potential acceptance
        # Note: This branch should not occur for initial proposals (AI only returns accept/reject)
        if counter_contract is not None:
            counter_contract_data = to_contract_data(counter_contract)
            state.negotiation_draft_contract = counter_contract
        # Don't save to history yet - negotiation is still ongoing

    elif decision == "reject":
        # Student may enter negotiation chat to discuss terms
        # Add the rejection message to chat history so AI has context for future messages
        state.negotiation_chat_history.append({
            "role": "supplier",
            "content": ai_message  # The rejection explanation from AI
        })
        # Don't save to history yet - negotiation is still ongoing, student can chat

    else:
        raise HTTPException(status_code=500, detail="Invalid supplier decision")

    # Build response game state (current active contract)
    state_response = to_game_state_response(session_id, state)

    return NegotiateResponse(
        state=state_response,
        ai_message=ai_message,
        decision=decision,
        counter_contract=counter_contract_data,
        offer_version=state.negotiation_offer_version if counter_contract_data else None,
    )


@router.post("/game/negotiate/chat", response_model=NegotiationChatResponse)
@serialize_negotiation
def negotiation_chat(request: NegotiationChatRequest) -> NegotiationChatResponse:
    """
    Handles chat messages during negotiation between student and AI supplier.
    
    Inputs:
        request: NegotiationChatRequest containing:
            - session_id: Game session identifier
            - message: The student's chat message
    
    What happens:
        Validates session exists and game is not over.
        Adds student's message to negotiation chat history.
        Generates AI response using generate_chat_response() with full context.
        Adds AI's response to chat history.
        Withdraws any previous offer before generating the supplier response.
        Replaces the offer state with the new draft (or None), with a new version.
    
    Output:
        Returns a NegotiationChatResponse containing:
        - supplier_message: AI's response to the student
        - negotiation_draft_contract: Contract object if agreement detected, None otherwise
    
    Context:
        Called when student sends a message in the negotiation chat.
        Part of the educational negotiation flow - allows discussion before committing.
        Draft contracts from chat can be accepted via accept_counter endpoint.
    """
    session_id = request.session_id
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is over. Start a new game.",
        )
    
    if has_active_contract(state):
        raise HTTPException(status_code=400, detail="A contract is already active.")

    # Resuming chat withdraws the previous offer before any AI work begins.
    # Keep it only as context; it must never remain available for acceptance.
    previous_draft = state.negotiation_draft_contract
    state.negotiation_draft_contract = None
    state.negotiation_offer_version += 1

    # Add student message to chat history
    state.negotiation_chat_history.append({
        "role": "student",
        "content": request.message
    })
    
    # Step 3: Generate AI response with game context
    # Get initial contract type - it's fixed and cannot be changed
    initial_contract_type = state.initial_contract_type or "buyback"
    
    supplier_response = generate_chat_response(
        state.negotiation_chat_history,
        previous_draft,
        state,  # Pass game state for context
        initial_contract_type  # Pass initial contract type to enforce it
    )
    
    # Add supplier response to chat history
    state.negotiation_chat_history.append({
        "role": "supplier",
        "content": supplier_response["message"]
    })
    
    # Every response replaces the offer state, including responses without a draft.
    state.negotiation_draft_contract = supplier_response.get("draft_contract")
    draft_contract_data = None
    if state.negotiation_draft_contract is not None:
        draft_contract_data = to_contract_data(state.negotiation_draft_contract)
    
    return NegotiationChatResponse(
        supplier_message=supplier_response["message"],
        negotiation_draft_contract=draft_contract_data,
        offer_version=state.negotiation_offer_version if draft_contract_data else None,
    )


@router.post("/game/negotiate/accept-counter", response_model=AcceptCounterResponse)
@serialize_negotiation
def accept_counter(request: AcceptCounterRequest) -> AcceptCounterResponse:
    """
    Handles student's acceptance or rejection of a draft contract (offer).
    
    Inputs:
        request: AcceptCounterRequest containing:
            - session_id: Game session identifier
            - accept: Boolean indicating whether student accepts (True) or rejects (False) the offer
            - offer_version: The version shown with the student's offer
    
    What happens:
        Validates session exists and game is not over.
        If accepting:
            - Checks that a draft contract exists.
            - Makes the draft contract active (sets it as state.contract).
            - Sets remaining_rounds to contract length.
            - Adds acceptance message to chat history.
            - Saves negotiation to history with "accept" decision.
            - Clears negotiation state (chat history, draft contract).
        If rejecting:
            - Clears the draft contract.
            - Adds rejection message to chat history (so AI knows negotiation continues).
            - Keeps chat history so conversation can continue.
    
    Output:
        Returns an AcceptCounterResponse containing the updated game state.
    
    Context:
        Called when student clicks "Accept Offer" or "Reject Offer" buttons.
        Final step in negotiation - accepting makes contract active so orders can be placed.
        Rejecting allows negotiation to continue in chat.
    """
    session_id = request.session_id
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is over. Start a new game.",
        )
    
    if has_active_contract(state):
        raise HTTPException(status_code=400, detail="A contract is already active.")

    if (
        state.negotiation_draft_contract is None
        or request.offer_version != state.negotiation_offer_version
    ):
        raise HTTPException(
            status_code=409,
            detail="This offer is no longer current. Review the latest supplier offer.",
        )

    if request.accept:
        # Accept the counteroffer - make draft contract active
        # Add acceptance message to chat history before saving (for completeness in history)
        state.negotiation_chat_history.append({
            "role": "student",
            "content": "I accept the counteroffer."
        })
        
        # Save current negotiation to history before clearing
        from datetime import datetime
        negotiation_record = {
            "chat_messages": list(state.negotiation_chat_history),  # Includes the acceptance message
            "final_decision": "accept",
            "final_contract": to_contract_data(state.negotiation_draft_contract),
            "start_time": getattr(state, "_current_negotiation_start_time", None),
            "end_time": datetime.now().isoformat(),  # Mark end time when contract becomes active
        }
        state.negotiation_history.append(negotiation_record)
        log_chat_record(
            participant_id=state.participant_id,
            session_id=session_id,
            negotiation_record=negotiation_record,
        )
        
        state.contract = state.negotiation_draft_contract
        state.contract.remaining_rounds = state.contract.length
        # Clear negotiation state
        state.negotiation_chat_history = []
        state.negotiation_draft_contract = None
        state._current_negotiation_start_time = None
    else:
        # Reject counteroffer - clear draft but keep chat history
        # Add a message to chat history so AI knows the student rejected the previous proposal
        # This helps the AI understand context when conversation continues
        if state.negotiation_draft_contract:
            # Add student rejection message to chat history for context
            state.negotiation_chat_history.append({
                "role": "student",
                "content": "I've rejected the previous counteroffer. Let's continue discussing terms."
            })
        state.negotiation_draft_contract = None
        # Don't save to history yet - negotiation might continue
    
    return AcceptCounterResponse(
        state=to_game_state_response(session_id, state)
    )
