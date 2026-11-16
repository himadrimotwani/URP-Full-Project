"""
Game management routes.
"""

from uuid import uuid4
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from simulation.core import (
    GameState,
    Contract,
    simulate_game_round,
)
from app.schemas import (
    GameStartRequest,
    GameStartResponse,
    GameStateRequest,
    GameStateResponse,
    OrderRequest,
    OrderResponse,
    GameSummary,
    RoundSummaryData,
    NegotiationHistory,
)
from app.services.game_service import (
    is_game_over,
    to_game_state_response,
    to_round_output_data,
    to_round_summary_data,
    to_contract_data,
)
from app.services.game_service import SESSIONS
from app.services.demand_history_service import load_demand_history_by_id
from app.services.storage_service import log_chat_record, log_round_record

router = APIRouter()


@router.post("/game/start", response_model=GameStartResponse)
def start_game(request: GameStartRequest) -> GameStartResponse:
    """
    Starts a new game session with specified parameters.
    
    Inputs:
        request: GameStartRequest containing:
            - rounds: Total number of rounds for this game
            - demand_method: "bootstrap" or "normal" for demand generation
    
    What happens:
        Validates the demand method is valid.
        Creates a new unique session ID.
        Creates an empty temporary contract (no active contract initially).
        Loads default demand history.
        Initializes a new GameState with round 1, empty profits, and default settings.
        Stores the game state in the SESSIONS dictionary.
        Initializes negotiation state (empty chat history, no draft contract).
    
    Output:
        Returns a GameStartResponse containing the new game state.
        Includes the session_id that must be used for all subsequent requests.
    
    Context:
        Called when instructor or student wants to start a new game.
        Must be called before any other game actions (negotiate, order, etc.).
        Each game gets a unique session_id that tracks its state.
    """
    session_id = str(uuid4())

    # Validate demand method
    if request.demand_method not in ("bootstrap", "normal"):
        raise HTTPException(
            status_code=400,
            detail="Invalid demand_method. Use 'bootstrap' or 'normal'.",
        )

    # temporary quick contract
    contract = Contract(
        wholesale_price=0,
        buyback_price=0,
        length=0,
        contract_type="buyback",
    )

    # Per-session copy. Selecting a scenario only affects this new game.
    try:
        history = list(load_demand_history_by_id(request.demand_history_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # initial game state
    state = GameState(
        round_number=1,
        total_rounds=request.rounds,
        contract=contract,
        cumulative_buyer_profit=0.0,
        cumulative_supplier_profit=0.0,
        historical_demands=history,
        method=request.demand_method,
        participant_id=request.participant_id,
        personality=request.personality,
        negotiation_chat_history=[],
        negotiation_draft_contract=None,
    )

    SESSIONS[session_id] = state

    # return response to frontend
    return GameStartResponse(
        state=to_game_state_response(session_id, state)
    )


@router.post("/game/state", response_model=GameStateResponse)
def get_game_state(request: GameStateRequest) -> GameStateResponse:
    """
    Retrieves the current game state for a session.
    
    Inputs:
        request: GameStateRequest containing:
            - session_id: The unique identifier for the game session
    
    What happens:
        Looks up the game state in the SESSIONS dictionary using session_id.
        If session not found, raises a 404 error.
        Converts the GameState to GameStateResponse format for API response.
    
    Output:
        Returns a GameStateResponse containing all current game information:
        - Current round number and total rounds
        - Active contract details
        - Cumulative profits
        - Game over status
        - Demand history
        - All completed round summaries
    
    Context:
        Called by frontend to refresh game state display.
        Used to check current game status without performing any actions.
        Called periodically to keep frontend in sync with backend state.
    """
    session_id = request.session_id

    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return to_game_state_response(session_id, state)


@router.post("/game/order", response_model=OrderResponse)
def place_order(request: OrderRequest) -> OrderResponse:
    """
    Processes an order from the student and simulates one round of the game.
    
    Inputs:
        request: OrderRequest containing:
            - session_id: Game session identifier
            - order_quantity: Number of units the student wants to order
    
    What happens:
        Looks up the game session.
        Checks if game is over (raises error if so).
        Checks if there's an active contract (raises error if not).
        Calls simulate_game_round with the order quantity.
        The simulation calculates demand, sales, returns, profits based on the contract.
        Updates the game state with new round results.
        Stores the updated state back in SESSIONS.
        Creates a round summary for logging.
    
    Output:
        Returns an OrderResponse containing:
        - Updated game state (with new round, updated profits, etc.)
        - Round output data (demand, sales, returns, profits for this round)
    
    Context:
        Called when student places an order during an active contract.
        This is the main gameplay action - simulates one round of the supply chain.
        Can only be called when there's an active contract with remaining rounds.
    """
    session_id = request.session_id
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # 1) Check round limit FIRST (true game over)
    if is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is over. Start a new game.",
        )

    # 2) Then check contract status (game still active, but no contract)
    if state.contract.remaining_rounds <= 0:
        raise HTTPException(
            status_code=400,
            detail="No active contract. Negotiate terms before ordering.",
        )

    # 3) Only then simulate a new round
    round_output, new_state = simulate_game_round(
        state,
        order_quantity=request.order_quantity,
    )

    SESSIONS[session_id] = new_state

    if new_state.round_summaries:
        log_round_record(
            participant_id=new_state.participant_id,
            session_id=session_id,
            round_summary=new_state.round_summaries[-1],
            round_output=round_output,
        )

    return OrderResponse(
        state=to_game_state_response(session_id, new_state),
        round_output=to_round_output_data(round_output),
    )


@router.get("/game/summary", response_model=GameSummary)
def get_game_summary(session_id: str) -> GameSummary:
    """
    Generates and returns a comprehensive summary of a completed game.
    
    Inputs:
        session_id: The unique identifier for the game session.
    
    What happens:
        Looks up the game state in SESSIONS.
        Verifies the game is over (raises error if not).
        Calculates game statistics (total rounds, demand, sales, returns, profits).
        Calculates performance metrics (fill rate, return rate, leftover rate).
        Saves any ongoing negotiation to history before ending.
        Converts all round summaries to API format.
        Converts negotiation history to API format.
        Builds a comprehensive GameSummary object.
    
    Output:
        Returns a GameSummary containing:
        - Total rounds played and game statistics
        - Cumulative profits for buyer and supplier
        - Performance metrics (fill rate, return rate, etc.)
        - All round summaries with contract details
        - Complete negotiation history with chat messages
    
    Context:
        Called when game ends (naturally or early) to show final results.
        Used by frontend to display game summary to students and instructors.
        Provides complete game history for analysis and grading.
    """
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is not over yet.",
        )

    # Rounds played so far (round_number starts at 1 and is incremented after each round)
    total_rounds_played = max(0, state.round_number - 1)

    total_demand = state.total_demand
    total_sales = state.total_sales
    total_returns = state.total_returns
    total_leftovers = state.total_leftovers

    cumulative_buyer_profit = state.cumulative_buyer_profit
    cumulative_supplier_profit = state.cumulative_supplier_profit

    average_demand = (
        total_demand / total_rounds_played if total_rounds_played > 0 else 0.0
    )

    fill_rate = (total_sales / total_demand) if total_demand > 0 else 0.0
    return_rate = (total_returns / total_sales) if total_sales > 0 else 0.0
    leftover_rate = (
        total_leftovers / (total_sales + total_leftovers)
        if (total_sales + total_leftovers) > 0
        else 0.0
    )

    rounds_data = [to_round_summary_data(rs) for rs in state.round_summaries]
    
    # Save any ongoing negotiation to history before game ends
    # Only save if game ended naturally (not early), since end_game_early already saves them
    from datetime import datetime
    if not state.ended_early and (state.negotiation_chat_history or state.negotiation_draft_contract):
        # Check if this negotiation was already saved to avoid duplicates
        current_start_time = getattr(state, "_current_negotiation_start_time", None)
        already_saved = False
        if state.negotiation_history and current_start_time:
            last_neg = state.negotiation_history[-1]
            # Check if same start_time and same chat messages (same negotiation)
            if (last_neg.get("start_time") == current_start_time and
                last_neg.get("chat_messages") == list(state.negotiation_chat_history)):
                already_saved = True
        
        if not already_saved:
            ongoing_negotiation = {
                "chat_messages": list(state.negotiation_chat_history),
                "final_decision": "ongoing" if state.negotiation_draft_contract else "rejected",
                "final_contract": to_contract_data(state.negotiation_draft_contract) if state.negotiation_draft_contract else None,
                "start_time": current_start_time,
                "end_time": datetime.now().isoformat(),  # Mark end time when game ends
            }
            state.negotiation_history.append(ongoing_negotiation)
            log_chat_record(
                participant_id=state.participant_id,
                session_id=session_id,
                negotiation_record=ongoing_negotiation,
            )
    
    # Convert negotiation history to schema format
    negotiation_history_data = [
        NegotiationHistory(
            final_contract=neg["final_contract"],
        )
        for neg in state.negotiation_history
    ]

    return GameSummary(
        session_id=session_id,
        total_rounds_played=total_rounds_played,
        total_demand=total_demand,
        total_sales=total_sales,
        total_returns=total_returns,
        total_leftovers=total_leftovers,
        cumulative_buyer_profit=cumulative_buyer_profit,
        cumulative_supplier_profit=cumulative_supplier_profit,
        average_demand=average_demand,
        fill_rate=fill_rate,
        return_rate=return_rate,
        leftover_rate=leftover_rate,
        historical_demands=list(state.historical_demands),
        rounds=rounds_data,
        negotiation_history=negotiation_history_data,
    )


@router.post("/game/end-early")
def end_game_early(request: GameStateRequest) -> Dict[str, Any]:
    """
    Allows instructor to end the game early before all rounds are completed.
    
    Inputs:
        request: GameStateRequest containing:
            - session_id: The unique identifier for the game session
    
    What happens:
        Looks up the game state in SESSIONS.
        Checks if game is already over (raises error if so).
        Marks the game as ended early (sets ended_early flag to True).
        Saves any ongoing negotiation to history before ending (with duplicate check).
        Updates the game state in SESSIONS.
    
    Output:
        Returns a dictionary with:
        - message: Confirmation that game ended early
        - state: Updated game state (now marked as game_over)
    
    Context:
        Called by instructor to end a game before all rounds are played.
        Allows instructor to control game duration for teaching purposes.
        After calling this, get_game_summary can be called to see results.
    """
    session_id = request.session_id
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if is_game_over(state):
        raise HTTPException(
            status_code=400,
            detail="Game is already over.",
        )
    
    # Mark game as ended early
    state.ended_early = True
    
    # Save any ongoing negotiation to history before ending
    # Check if this negotiation was already saved to avoid duplicates
    from datetime import datetime
    if state.negotiation_chat_history or state.negotiation_draft_contract:
        # Check if the last negotiation in history matches the current one (to avoid duplicates)
        already_saved = False
        current_start_time = getattr(state, "_current_negotiation_start_time", None)
        if state.negotiation_history and current_start_time:
            last_neg = state.negotiation_history[-1]
            # Check if same start_time and same chat messages (same negotiation)
            if (last_neg.get("start_time") == current_start_time and
                last_neg.get("chat_messages") == list(state.negotiation_chat_history)):
                already_saved = True
        
        if not already_saved:
            ongoing_negotiation = {
                "chat_messages": list(state.negotiation_chat_history),
                "final_decision": "ongoing" if state.negotiation_draft_contract else "rejected",
                "final_contract": to_contract_data(state.negotiation_draft_contract) if state.negotiation_draft_contract else None,
                "start_time": current_start_time,
                "end_time": datetime.now().isoformat(),  # Mark end time when game ends
            }
            state.negotiation_history.append(ongoing_negotiation)
            log_chat_record(
                participant_id=state.participant_id,
                session_id=session_id,
                negotiation_record=ongoing_negotiation,
            )
    
    return {
        "message": "Game ended early. Summary is now available.",
        "state": to_game_state_response(session_id, state)
    }
