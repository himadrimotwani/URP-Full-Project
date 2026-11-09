"""
Pydantic models that define the shapes of data we send to / receive from the frontend.

These schemas are used for:
- API request/response validation
- Type checking and serialization
- Documentation generation (FastAPI automatically generates OpenAPI docs from these)

All models inherit from Pydantic's BaseModel, which provides automatic validation,
JSON serialization, and type checking.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


# ============================================================================
# Participant / Data Collection Schemas
# ============================================================================

class ParticipantCreateRequest(BaseModel):
    """
    Information collected before a player can access the game.
    """
    name: str
    email: str | None = None
    student_id: str | None = None
    section: str | None = None


class ParticipantCreateResponse(BaseModel):
    """
    Response after storing a participant record.
    """
    participant_id: str


# ============================================================================
# Configuration Schemas
# ============================================================================

class EconomicParamsData(BaseModel):
    """
    Economic parameters that define the simulation environment.
    
    Fields:
        retail_price: Price per unit sold to end customers (p)
        buyer_salvage_value: Value buyer gets from leftover units (v_B)
        supplier_salvage_value: Value supplier gets from returned units (v_S)
        supplier_cost: Production cost per unit for supplier (c)
        return_shipping_buyer: Cost buyer pays to ship returns (c_ret)
        return_handling_supplier: Cost supplier pays to handle returns (h)
    
    Usage:
        - Used in `/config/current` endpoint response
        - Used in `/config/update` endpoint request
        - Converted from EconomicParams (core.py) for API responses
        - Loaded from config/economic_params.json file
    
    Context:
        These parameters control the economic environment of the game.
        Instructors can modify these to create different scenarios.
        Used throughout simulation calculations in core.py.
    """
    retail_price: float
    buyer_salvage_value: float
    supplier_salvage_value: float
    supplier_cost: float
    return_shipping_buyer: float
    return_handling_supplier: float


class HistorySummary(BaseModel):
    """
    Statistical summary of demand history data.
    
    Fields:
        count: Number of historical demand periods
        min: Minimum demand value in history
        max: Maximum demand value in history
        mean: Average demand value
        stdev: Standard deviation of demand (None if count < 2)
        sample: First 10 demand values as a sample
    
    Usage:
        - Used in `/config/current` endpoint response
        - Displayed to instructor in frontend configuration panel
        - Helps instructor understand demand patterns
    
    Context:
        Provides summary statistics for the demand history.
        Used for display purposes only - actual simulation uses full history.
        Calculated in build_config_state_response() in main.py.
    """
    count: int
    min: int
    max: int
    mean: float
    stdev: float | None
    sample: List[int]


class ConfigStateResponse(BaseModel):
    """
    Complete configuration state returned to frontend.
    
    Fields:
        economic_params: Current economic parameters
        history_summary: Statistical summary of demand history
    
    Usage:
        - Returned by `/config/current` endpoint (GET)
        - Returned by `/config/update` endpoint (POST) after updating
        - Used by frontend to display current configuration to instructor
    
    Context:
        Provides all configuration information in one response.
        Used when instructor views or updates game parameters.
        Built by build_config_state_response() in main.py.
    """
    economic_params: EconomicParamsData
    history_summary: HistorySummary


class DemandHistoryOption(BaseModel):
    """
    One selectable demand-history scenario.
    """
    id: str
    label: str
    count: int
    min: int | None = None
    max: int | None = None
    sample: List[int] = Field(default_factory=list)


class DemandHistoriesResponse(BaseModel):
    """
    List of demand histories available for new games.
    """
    histories: List[DemandHistoryOption]


class UpdateConfigRequest(BaseModel):
    """
    Request to update configuration parameters.
    
    Fields:
        economic_params: New economic parameters (optional - only updates if provided)
        history: New demand history list (optional - only updates if provided)
    
    Usage:
        - Used in `/config/update` endpoint (POST)
        - Sent from frontend when instructor updates configuration
        - Both fields are optional - can update just one or both
    
    Context:
        Allows partial updates - only provided fields are updated.
        Updates are saved to config files and reloaded into memory.
        Used by instructor to customize game environment.
    """
    economic_params: EconomicParamsData | None = None
    history: List[int] | None = None


class NegotiationConfigData(BaseModel):
    """
    Configuration for negotiation system constraints and AI behavior.
    
    Fields:
        contract_types_available: List of allowed contract types (e.g., ["buyback"])
        length_min: Minimum contract length in rounds
        length_max: Maximum contract length in rounds
        system_prompt_template: Template for AI supplier's system prompt
        example_dialog: Example conversation for AI training (list of dicts with role/content)
    
    Usage:
        - Used in `/config/negotiation` endpoint (GET)
        - Used in `/config/negotiation/update` endpoint (POST)
        - Loaded from config/negotiation_config.json file
        - Used to validate student proposals and configure AI behavior
    
    Context:
        Allows instructor to restrict negotiation options for educational purposes.
        Constraints are enforced when students submit proposals.
        AI system prompt uses this config to understand negotiation boundaries.
    """
    contract_types_available: List[str]
    length_min: int
    length_max: int
    system_prompt_template: str
    example_dialog: List[Dict[str, str]] = Field(default_factory=list)


class NegotiationConfigResponse(BaseModel):
    """
    Response containing negotiation configuration.
    
    Fields:
        negotiation_config: Current negotiation configuration settings
    
    Usage:
        - Returned by `/config/negotiation` endpoint (GET)
        - Returned by `/config/negotiation/update` endpoint (POST)
        - Used by frontend to display and edit negotiation settings
    
    Context:
        Wraps NegotiationConfigData for API responses.
        Used when instructor views or updates negotiation constraints.
    """
    negotiation_config: NegotiationConfigData


class UpdateNegotiationConfigRequest(BaseModel):
    """
    Request to update negotiation configuration.
    
    Fields:
        negotiation_config: New negotiation configuration (required)
    
    Usage:
        - Used in `/config/negotiation/update` endpoint (POST)
        - Sent from frontend when instructor updates negotiation settings
        - Validates ranges and constraints before saving
    
    Context:
        Allows instructor to customize negotiation environment.
        Changes affect what contract terms students can propose.
        Saved to config/negotiation_config.json file.
    """
    negotiation_config: NegotiationConfigData | None = None


class ContractData(BaseModel):
    """
    Contract information sent to frontend (API representation of Contract).
    
    Fields:
        wholesale_price: Price per unit buyer pays to supplier (w)
        buyback_price: Price per unit supplier pays for returns (b)
        length: Total contract length in rounds (L)
        remaining_rounds: Number of rounds left on this contract
        contract_type: "buyback"
    
    Usage:
        - Used in all game state responses (GameStateResponse)
        - Used in negotiation responses (NegotiateResponse, NegotiationChatResponse)
        - Converted from Contract (core.py) using to_contract_data() in main.py
        - Displayed to student in frontend showing current contract
    
    Context:
        This is the API-friendly version of the Contract dataclass.
        Used whenever contract information needs to be sent to frontend.
        Student sees this information to understand their active contract.
    """
    wholesale_price: float          # w
    buyback_price: float            # b
    length: int                     # contract length in rounds
    remaining_rounds: int           # remaining rounds on this contract
    contract_type: str = "buyback"


class RoundOutputData(BaseModel):
    """
    Results from one round of gameplay (API representation of RoundOutput).
    
    Fields (Core):
        order_quantity: Number of units student ordered (Q_t)
        realized_demand: Actual demand that occurred (D_t)
        sales: Units sold to customers (S_t)
        unsold: Units not sold (U_t)
        returns: Units returned to supplier (B_t)
        leftovers: Units kept by buyer after returns (L_t)
        buyer_revenue: Total revenue for buyer this round
        buyer_cost: Total costs for buyer this round
        buyer_profit: Net profit for buyer this round
        supplier_revenue: Total revenue for supplier this round
        supplier_cost: Total costs for supplier this round
        supplier_profit: Net profit for supplier this round
    
    Fields (Detailed Components - Optional):
        Buyer-side: retail_revenue, salvage_revenue_buyer, buyback_refund_buyer,
                    wholesale_cost_buyer, return_shipping_cost_buyer
        Supplier-side: wholesale_revenue_supplier, salvage_revenue_supplier,
                       production_cost_supplier, buyback_cost_supplier,
                       return_handling_cost_supplier
    
    Usage:
        - Used in `/game/order` endpoint response (OrderResponse)
        - Converted from RoundOutput (core.py) using to_round_output_data() in main.py
        - Displayed to student showing results of their order decision
        - Shows detailed breakdown of profits and costs
    
    Context:
        This is the API-friendly version of the RoundOutput dataclass.
        Returned immediately after student places an order.
        Student uses this to understand consequences of their decisions.
    """
    # decision + demand
    order_quantity: int
    realized_demand: int

    # flows
    sales: int
    unsold: int
    returns: int
    leftovers: int
    buyer_revenue: float
    buyer_cost: float
    buyer_profit: float
    supplier_revenue: float
    supplier_cost: float
    supplier_profit: float

    # Buyer-side components
    retail_revenue: float | None = None
    salvage_revenue_buyer: float | None = None
    buyback_refund_buyer: float | None = None
    wholesale_cost_buyer: float | None = None
    return_shipping_cost_buyer: float | None = None

    # Supplier-side components
    wholesale_revenue_supplier: float | None = None
    salvage_revenue_supplier: float | None = None
    production_cost_supplier: float | None = None
    buyback_cost_supplier: float | None = None
    return_handling_cost_supplier: float | None = None


class RoundSummaryData(BaseModel):
    """
    Summary of one completed round for game history (API representation of RoundSummary).
    
    Fields (Round Results):
        round_index: Round number (1, 2, 3, ...)
        order_quantity: Units ordered by student
        realized_demand: Actual demand that occurred
        buyer_revenue: Total revenue for buyer
        buyer_cost: Total costs for buyer
        buyer_profit: Net profit for buyer
        supplier_revenue: Total revenue for supplier
        supplier_cost: Total costs for supplier
        supplier_profit: Net profit for supplier
    
    Fields (Contract Details - for logging, not shown to player):
            wholesale_price, buyback_price, contract_length,
    
    Usage:
        - Used in GameStateResponse.rounds (list of all completed rounds)
        - Used in GameSummary.rounds (end-of-game summary)
        - Converted from RoundSummary (core.py) using to_round_summary_data() in main.py
        - Displayed in frontend showing round-by-round history
    
    Context:
        This is the API-friendly version of the RoundSummary dataclass.
        Stored in game state for each completed round.
        Used to show students their performance history.
        Contract details included for instructor analysis but hidden from student view.
    """
    round_index: int
    order_quantity: int
    realized_demand: int

    buyer_revenue: float
    buyer_cost: float
    buyer_profit: float

    supplier_revenue: float
    supplier_cost: float
    supplier_profit: float

    # Contract details for logging (not shown to player in frontend)
    wholesale_price: float
    buyback_price: float
    contract_length: int
    remaining_rounds: int
    contract_type: str


class NegotiationHistory(BaseModel):
    """
    Complete record of one negotiation session.
    
    Fields:
        chat_messages: List of conversation messages with role ("student"/"supplier") and content
        final_decision: How negotiation ended - "accept", "reject", or None (ongoing)
        final_contract: Contract that was accepted (if any), None if rejected or ongoing
        start_time: ISO timestamp when negotiation started
        end_time: ISO timestamp when negotiation ended (accepted, rejected, or new negotiation started)
    
    Usage:
        - Used in GameSummary.negotiation_history (list of all negotiations)
        - Stored in GameState.negotiation_history during gameplay
        - Converted to this schema format in get_game_summary() in main.py
        - Displayed in game summary for instructor analysis
    
    Context:
        Tracks complete negotiation sessions for logging and analysis.
        Each negotiation attempt (from proposal to accept/reject) is one entry.
        Used by instructor to review student negotiation skills.
        Includes full conversation history for educational analysis.
    """
    chat_messages: List[Dict[str, str]] = Field(default_factory=list)  # List of {role: str, content: str}
    final_decision: str | None = None  # "accept", "reject", or None (ongoing)
    final_contract: ContractData | None = None  # The contract that was eventually accepted (if any)
    start_time: str | None = None  # ISO format timestamp when negotiation started
    end_time: str | None = None  # ISO format timestamp when negotiation ended (contract accepted or new negotiation started)


class GameSummary(BaseModel):
    """
    Complete end-of-game summary with all statistics and history.
    
    Fields (Game Statistics):
        session_id: Unique identifier for this game session
        total_rounds_played: Number of rounds completed
        total_demand: Sum of all demand values
        total_sales: Sum of all units sold
        total_returns: Sum of all units returned
        total_leftovers: Sum of all leftover units
        cumulative_buyer_profit: Total profit earned by buyer across all rounds
        cumulative_supplier_profit: Total profit earned by supplier across all rounds
        average_demand: Average demand per round
        fill_rate: Percentage of demand filled (total_sales / total_demand)
        return_rate: Percentage of sales returned (total_returns / total_sales)
        leftover_rate: Percentage of units that became leftovers
    
    Fields (History):
        historical_demands: List of all demand values (including pre-game history)
        rounds: List of summaries for each completed round
        negotiation_history: List of all negotiation sessions during the game
    
    Usage:
        - Returned by `/game/summary` endpoint (GET)
        - Generated when game ends (naturally or early)
        - Displayed to both student and instructor in frontend
        - Used for grading and performance analysis
    
    Context:
        Comprehensive summary of entire game session.
        Used for final evaluation and learning assessment.
        Includes all rounds, negotiations, and performance metrics.
        Available after game ends (naturally or when instructor ends early).
    """
    session_id: str

    total_rounds_played: int
    total_demand: int
    total_sales: int
    total_returns: int
    total_leftovers: int

    cumulative_buyer_profit: float
    cumulative_supplier_profit: float

    average_demand: float
    fill_rate: float               # total_sales / total_demand
    return_rate: float             # total_returns / total_sales
    leftover_rate: float           # total_leftovers / (sales + leftovers)

    historical_demands: List[int]
    rounds: List[RoundSummaryData] = Field(default_factory=list)
    
    # Negotiation history for logging and analysis
    negotiation_history: List[NegotiationHistory] = Field(default_factory=list)


# ============================================================================
# Game Flow Request/Response Schemas
# ============================================================================

class GameStateResponse(BaseModel):
    """
    Current game state information returned to frontend.
    
    Fields:
        session_id: Unique identifier for this game session
        round_number: Current round number (1-indexed)
        total_rounds: Total number of rounds in this game
        contract: Current active contract (or empty contract if none)
        cumulative_buyer_profit: Total profit earned by buyer so far
        cumulative_supplier_profit: Total profit earned by supplier so far
        game_over: Whether the game has ended
        demand_method: "bootstrap" or "normal" - how demand is generated
        historical_demands: List of all demand values (including pre-game history)
        rounds: List of summaries for all completed rounds
    
    Usage:
        - Returned by `/game/state` endpoint (POST)
        - Returned by `/game/start` endpoint (POST)
        - Returned by `/game/negotiate` endpoint (POST)
        - Returned by `/game/order` endpoint (POST)
        - Returned by `/game/negotiate/accept-counter` endpoint (POST)
        - Used by frontend to display current game status
    
    Context:
        This is the main game state object sent to frontend.
        Updated after every game action (start, negotiate, order, etc.).
        Frontend uses this to refresh the UI and show current status.
        Converted from GameState (core.py) using to_game_state_response() in main.py.
    """
    session_id: str
    round_number: int
    total_rounds: int
    contract: ContractData
    cumulative_buyer_profit: float
    cumulative_supplier_profit: float
    game_over: bool
    demand_method: str                  # "bootstrap" or "normal"
    personality: str | None = None      # Bot personality for debug purposes

    historical_demands: List[int]
    rounds: List[RoundSummaryData] = Field(default_factory=list)


class GameStartResponse(BaseModel):
    """
    Response when starting a new game.
    
    Fields:
        state: Initial game state with new session_id
    
    Usage:
        - Returned by `/game/start` endpoint (POST)
        - Contains the new session_id that must be used for all subsequent requests
    
    Context:
        Wraps GameStateResponse for game start endpoint.
        Frontend stores session_id from this response.
    """
    state: GameStateResponse


class GameStateRequest(BaseModel):
    """
    Request to get current game state.
    
    Fields:
        session_id: Unique identifier for the game session
    
    Usage:
        - Used in `/game/state` endpoint (POST)
        - Used in `/game/end-early` endpoint (POST)
        - Sent from frontend to refresh game state display
    
    Context:
        Simple request that only needs session_id to look up game state.
    """
    session_id: str


class GameStartRequest(BaseModel):
    """
    Request to start a new game.
    
    Fields:
        rounds: Total number of rounds for this game (default: 50)
        demand_method: "bootstrap" or "normal" - how to generate demand (default: "bootstrap")
    
    Usage:
        - Used in `/game/start` endpoint (POST)
        - Sent from frontend when instructor or student starts a new game
    
    Context:
        Allows customization of game length and demand generation method.
        Instructor can set these to create different game scenarios.
    """
    rounds: int = 50
    demand_method: str = "bootstrap"
    demand_history_id: str | None = None
    participant_id: str | None = None


class NegotiateRequest(BaseModel):
    """
    Request to propose a contract to the supplier.
    
    Fields:
        session_id: Unique identifier for the game session
        wholesale_price: Price per unit buyer proposes to pay (w)
        buyback_price: Price per unit supplier pays for returns (b)
        length: Contract length in rounds (L)
        contract_type: "buyback" (default: "buyback")
    
    Usage:
        - Used in `/game/negotiate` endpoint (POST)
        - Sent from frontend when student submits initial contract proposal
        - Validated against negotiation config constraints before evaluation
    
    Context:
        Student's initial contract proposal.
        Supplier (AI) evaluates this and returns accept/reject decision.
        If rejected, student can enter chat to negotiate further.
    """
    session_id: str
    wholesale_price: float
    buyback_price: float
    length: int
    contract_type: str = "buyback"          # "buyback"


class NegotiateResponse(BaseModel):
    """
    Response to contract proposal from supplier.
    
    Fields:
        state: Updated game state (contract active if accepted)
        ai_message: Supplier's explanation message (acceptance or rejection reason)
        decision: "accept" or "reject" - supplier's decision
        counter_contract: Always None for initial proposals (counters come from chat)
    
    Usage:
        - Returned by `/game/negotiate` endpoint (POST)
        - Displayed to student showing supplier's response
        - If accepted, contract becomes active immediately
        - If rejected, student can enter negotiation chat
    
    Context:
        Supplier's evaluation of student's initial proposal.
        Only returns accept or reject - no counteroffers on initial proposals.
        Counteroffers only emerge from chat discussions.
    """
    state: GameStateResponse
    ai_message: str                         # simple text explanation from "AI supplier"
    decision: str                           # "accept" or "reject"
    counter_contract: ContractData | None = None  # Always None for initial proposals
    offer_version: int | None = None


# ============================================================================
# Negotiation Chat Schemas
# ============================================================================

class ChatMessage(BaseModel):
    """
    Single message in negotiation chat conversation.
    
    Fields:
        role: "student" or "supplier" - who sent the message
        content: The message text
        timestamp: Optional ISO timestamp (not currently used but available)
    
    Usage:
        - Used internally in negotiation_chat_history (list of dicts, not this schema)
        - Could be used for more structured chat message handling in future
    
    Context:
        Represents one message in the negotiation conversation.
        Currently chat history uses dict format, but this schema is available.
    """
    role: str  # "student" or "supplier"
    content: str
    timestamp: str | None = None


class NegotiationChatRequest(BaseModel):
    """
    Request to send a message in negotiation chat.
    
    Fields:
        session_id: Unique identifier for the game session
        message: Student's chat message to the supplier AI
    
    Usage:
        - Used in `/game/negotiate/chat` endpoint (POST)
        - Sent from frontend when student types a message in chat
        - AI generates response and may detect agreement
    
    Context:
        Allows student to discuss terms with AI supplier.
        Part of educational negotiation flow - encourages conversation before committing.
    """
    session_id: str
    message: str  # Student's message


class NegotiationChatResponse(BaseModel):
    """
    Response from negotiation chat with AI supplier.
    
    Fields:
        supplier_message: AI supplier's response message
        negotiation_draft_contract: Draft contract if AI detected agreement, None otherwise
    
    Usage:
        - Returned by `/game/negotiate/chat` endpoint (POST)
        - Displayed to student showing AI's response
        - If draft_contract present, student can accept or reject it
    
    Context:
        AI supplier's conversational response.
        May include a draft contract if student agreed to terms.
        Student can then accept/reject the draft via accept_counter endpoint.
    """
    supplier_message: str
    negotiation_draft_contract: ContractData | None = None  # Draft contract from chat if agreement detected
    offer_version: int | None = None  # Identifies exactly the displayed draft


class AcceptCounterRequest(BaseModel):
    """
    Request to accept or reject a draft contract (offer).
    
    Fields:
        session_id: Unique identifier for the game session
        accept: True to accept the offer, False to reject it
    
    Usage:
        - Used in `/game/negotiate/accept-counter` endpoint (POST)
        - Sent from frontend when student clicks "Accept Offer" or "Reject Offer"
        - If accepted, draft contract becomes active
    
    Context:
        Final step in negotiation - student decides on draft contract.
        Accepting makes contract active so orders can be placed.
        Rejecting allows negotiation to continue in chat.
    """
    session_id: str
    accept: bool  # True to accept offer, False to reject
    offer_version: int = Field(gt=0, strict=True)  # Version displayed with the offer


class AcceptCounterResponse(BaseModel):
    """
    Response after accepting or rejecting a draft contract.
    
    Fields:
        state: Updated game state (contract active if accepted)
    
    Usage:
        - Returned by `/game/negotiate/accept-counter` endpoint (POST)
        - Shows updated game state after decision
    
    Context:
        Confirms the student's decision and updates game state.
        If accepted, contract is now active and orders can be placed.
    """
    state: GameStateResponse


# ============================================================================
# Order Schemas
# ============================================================================

class OrderRequest(BaseModel):
    """
    Request to place an order for the current round.
    
    Fields:
        session_id: Unique identifier for the game session
        order_quantity: Number of units student wants to order (Q)
    
    Usage:
        - Used in `/game/order` endpoint (POST)
        - Sent from frontend when student places an order
        - Requires an active contract to be in place
    
    Context:
        Main gameplay action - student decides how many units to order.
        Simulates one round of the supply chain game.
        Can only be called when there's an active contract.
    """
    session_id: str
    order_quantity: int


class OrderResponse(BaseModel):
    """
    Response after placing an order, showing round results.
    
    Fields:
        state: Updated game state (new round, updated profits, etc.)
        round_output: Detailed results from this round
    
    Usage:
        - Returned by `/game/order` endpoint (POST)
        - Displayed to student showing results of their order decision
        - Shows demand, sales, returns, profits for this round
    
    Context:
        Complete results from one round of gameplay.
        Student uses this to understand consequences of their order decision.
        Game state updated with new round and cumulative profits.
    """
    state: GameStateResponse
    round_output: RoundOutputData
