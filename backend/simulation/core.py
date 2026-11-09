"""
Core simulation logic for fashion supply chain game.

This module contains:
- Data classes for game state, contracts, and round data
- Configuration loading functions for economic parameters and demand history
- Core simulation functions for calculating round results
- Demand generation functions
"""

# Standard library imports
import csv
import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List


# ================================
# Economic Parameters
# ================================

@dataclass
class EconomicParams:
    """
    Economic parameters that define the supply chain environment.
    
    Attributes:
        retail_price: Price at which buyer sells to customers (p)
        buyer_salvage_value: Value buyer gets for leftover inventory (v_B)
        return_shipping_buyer: Cost buyer pays to ship returns (c_ret)
        supplier_cost: Cost supplier pays to produce one unit (c)
        supplier_salvage_value: Value supplier gets for returned units (v_S)
        return_handling_supplier: Cost supplier pays to handle returns (h)
    """
    retail_price: float = 50.0              # p
    buyer_salvage_value: float = 3.0        # v_B
    return_shipping_buyer: float = 1        # c_ret

    supplier_cost: float = 12.0             # c
    supplier_salvage_value: float = 12.0    # v_S
    return_handling_supplier: float = 0.5   # h


# ================================
# Configuration Loading
# ================================

def load_economic_params_from_json(path: Path) -> EconomicParams:
    """
    Loads economic parameters from a JSON configuration file.

    Inputs:
        path: Path object pointing to the JSON configuration file.

    What happens:
        Attempts to read and parse the JSON file.
        If file is missing, returns default EconomicParams with hardcoded values.
        If file exists but parsing fails, returns default EconomicParams.
        If file exists and is valid, extracts parameter values from JSON.
        Uses default values for any missing parameters in JSON.

    Output:
        Returns an EconomicParams object with loaded or default values.

    Context:
        Called during module initialization to load DEFAULT_PARAMS.
        Called by reload_defaults() when instructor updates configuration.
        Provides fallback to defaults if config file is missing or invalid.
        Used to customize economic environment without code changes.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return EconomicParams()
    except Exception:
        # Silently fall back to defaults if file is invalid
        return EconomicParams()

    # Get default values from class definition
    base = EconomicParams()

    return EconomicParams(
        retail_price=data.get("retail_price", base.retail_price),
        buyer_salvage_value=data.get("buyer_salvage_value", base.buyer_salvage_value),
        supplier_salvage_value=data.get("supplier_salvage_value", base.supplier_salvage_value),
        supplier_cost=data.get("supplier_cost", base.supplier_cost),
        return_shipping_buyer=data.get("return_shipping_buyer", base.return_shipping_buyer),
        return_handling_supplier=data.get("return_handling_supplier", base.return_handling_supplier),
    )


def load_demand_history_from_csv(path: Path) -> List[int]:
    """
    Loads historical demand data from a CSV file.

    Inputs:
        path: Path object pointing to the CSV file.

    What happens:
        Attempts to open and read the CSV file.
        Parses each row, skipping empty rows and headers.
        Converts first column values to integers.
        If file is missing, returns default hardcoded history.
        If file exists but has no valid rows, returns default history.
        If file exists and is valid, returns list of demand values.

    Output:
        Returns a list of integers representing historical demand values.

    Context:
        Called during module initialization to load DEFAULT_HISTORY.
        Called by reload_defaults() when instructor updates configuration.
        Provides fallback to defaults if CSV file is missing or invalid.
        Used to customize demand patterns without code changes.
        Demand history is used for bootstrap sampling and statistics.
    """
    try:
        with path.open("r", newline="") as f:
            reader = csv.reader(f)
            values = []
            for row in reader:
                if not row:
                    continue
                # Try to parse the first column as int
                try:
                    val = int(row[0])
                    values.append(val)
                except ValueError:
                    # Skip header or bad rows
                    continue
        if not values:
            # If we didn't get anything valid, fall back to default
            raise ValueError("No valid rows in CSV")
        return values
    except (FileNotFoundError, ValueError, OSError):
        # Return default history if file is missing or invalid
        return [450, 520, 480, 600, 550, 530, 490]


def reload_defaults() -> None:
    """
    Reloads configuration from disk files into memory.

    Inputs:
        None (reads from global file paths).

    What happens:
        Calls load_economic_params_from_json() to reload economic parameters.
        Calls load_demand_history_from_csv() to reload demand history.
        Updates global DEFAULT_PARAMS and DEFAULT_HISTORY variables.
        New games will use the updated configuration.

    Output:
        None (modifies global state).

    Context:
        Called by update_config() endpoint after instructor updates configuration.
        Ensures configuration changes take effect immediately.
        Allows instructor to modify game parameters without restarting server.
    """
    global DEFAULT_PARAMS, DEFAULT_HISTORY
    DEFAULT_PARAMS = load_economic_params_from_json(Path("config/economic_params.json"))
    DEFAULT_HISTORY = load_demand_history_from_csv(Path("data/D_hist.csv"))


def get_current_params() -> EconomicParams:
    """
    Gets the current economic parameters from memory.

    Inputs:
        None (reads from global DEFAULT_PARAMS).

    What happens:
        Returns the global DEFAULT_PARAMS object.
        This contains the current economic configuration.

    Output:
        Returns an EconomicParams object with current parameter values.

    Context:
        Called throughout the codebase to get economic parameters.
        Used in simulation calculations (simulate_round).
        Used in AI evaluation prompts.
        Used in API responses to show current configuration.
    """
    return DEFAULT_PARAMS


def get_current_history() -> List[int]:
    """
    Gets the current demand history from memory.

    Inputs:
        None (reads from global DEFAULT_HISTORY).

    What happens:
        Returns the global DEFAULT_HISTORY list.
        This contains the current historical demand values.

    Output:
        Returns a list of integers representing historical demand values.

    Context:
        Called throughout the codebase to get demand history.
        Used for bootstrap demand generation.
        Used for demand statistics in API responses.
        Used in AI prompts to provide context about demand patterns.
    """
    return DEFAULT_HISTORY


# Load default configuration on module import
DEFAULT_PARAMS: EconomicParams = load_economic_params_from_json(Path("config/economic_params.json"))
DEFAULT_HISTORY: List[int] = load_demand_history_from_csv(Path("data/D_hist.csv"))


# ================================
# Data Classes
# ================================

@dataclass
class Contract:
    """
    Represents a supply chain contract between buyer and supplier.

    Attributes:
        wholesale_price: Price buyer pays supplier per unit (w)
        buyback_price: Price supplier pays buyer for returned units (b)
        length: Total number of rounds contract lasts (L)
        remaining_rounds: Number of rounds left in contract (auto-set to length if None)
        contract_type: Type of contract - "buyback"
    """
    wholesale_price: float                  # w
    buyback_price: float                    # b
    length: int                             # number of rounds (L)
    remaining_rounds: int | None = None     # remaining rounds on contract

    contract_type: str = "buyback"          # "buyback"

    def __post_init__(self) -> None:
        """
        Initializes remaining_rounds if not provided.
        """
        if self.remaining_rounds is None:
            self.remaining_rounds = self.length


@dataclass
class RoundInput:
    """
    Input data for simulating one round.

    Attributes:
        order_quantity: Number of units ordered by buyer (Q_t)
        realized_demand: Actual demand that occurred (D_t)
    """
    order_quantity: int             # Q_t
    realized_demand: int            # D_t


@dataclass
class RoundOutput:
    """
    Complete output from simulating one round.

    Attributes:
        order_quantity: Number of units ordered (Q_t)
        realized_demand: Actual demand that occurred (D_t)
        sales: Number of units sold (S_t)
        unsold: Number of units not sold (U_t)
        returns: Number of units returned to supplier (B_t)
        leftovers: Number of units kept by buyer (L_t)
        buyer_revenue: Total revenue for buyer
        buyer_cost: Total cost for buyer
        buyer_profit: Net profit for buyer
        supplier_revenue: Total revenue for supplier
        supplier_cost: Total cost for supplier
        supplier_profit: Net profit for supplier
        retail_revenue: Revenue from retail sales (p * S)
        salvage_revenue_buyer: Revenue from salvaging leftovers (v_B * L)
        buyback_refund_buyer: Refund from supplier for returns (b * B)
        wholesale_cost_buyer: Cost of purchasing units (w * Q)
        return_shipping_cost_buyer: Cost to ship returns (c_ret * B)
        wholesale_revenue_supplier: Revenue from selling to buyer (w * Q)
        salvage_revenue_supplier: Revenue from salvaging returns (v_S * B)
        production_cost_supplier: Cost to produce units (c * Q)
        buyback_cost_supplier: Cost to buy back returns (b * B)
        return_handling_cost_supplier: Cost to handle returns (h * B)
    """
    # Decision + uncertainty
    order_quantity: int              # Q_t
    realized_demand: int             # D_t

    # Core physical flows
    sales: int                       # S_t
    unsold: int                      # U_t
    returns: int                     # B_t
    leftovers: int                  # L_t

    # Total profits per side
    buyer_revenue: float = 0.0
    buyer_cost: float = 0.0
    buyer_profit: float = 0.0
    supplier_revenue: float = 0.0
    supplier_cost: float = 0.0
    supplier_profit: float = 0.0

    # Buyer-side components (per round)
    retail_revenue: float = 0.0                     # p * S
    salvage_revenue_buyer: float = 0.0            # v_B * L
    buyback_refund_buyer: float = 0.0              # b * B (refund from supplier)
    wholesale_cost_buyer: float = 0.0              # w * Q
    return_shipping_cost_buyer: float = 0.0        # c_ret * B

    # Supplier-side components (per round)
    wholesale_revenue_supplier: float = 0.0        # w * Q
    salvage_revenue_supplier: float = 0.0         # v_S * B
    production_cost_supplier: float = 0.0         # c * Q
    buyback_cost_supplier: float = 0.0             # b * B
    return_handling_cost_supplier: float = 0.0     # h * B


@dataclass
class RoundSummary:
    """
    Summary of one completed round for logging and analysis.

    Attributes:
        round_index: Round number (1-indexed)
        order_quantity: Number of units ordered
        realized_demand: Actual demand that occurred
        buyer_revenue: Total revenue for buyer
        buyer_cost: Total cost for buyer
        buyer_profit: Net profit for buyer
        supplier_revenue: Total revenue for supplier
        supplier_cost: Total cost for supplier
        supplier_profit: Net profit for supplier
        wholesale_price: Contract wholesale price at time of round
        buyback_price: Contract buyback price at time of round
        contract_length: Total length of contract
        remaining_rounds: Rounds remaining in contract
        contract_type: Type of contract
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

    # Contract details for logging
    wholesale_price: float
    buyback_price: float
    contract_length: int
    remaining_rounds: int
    contract_type: str


@dataclass
class GameState:
    """
    Complete state of a game session.

    Attributes:
        round_number: Current round number (1-indexed, increments after each round)
        total_rounds: Total number of rounds in this game
        contract: Current active contract
        cumulative_buyer_profit: Total profit accumulated by buyer
        cumulative_supplier_profit: Total profit accumulated by supplier
        historical_demands: List of demand values (includes initial history + generated demands)
        method: Demand generation method ("bootstrap" or "normal")
        total_demand: Sum of all demand values across rounds
        total_sales: Sum of all sales across rounds
        total_returns: Sum of all returns across rounds
        total_leftovers: Sum of all leftovers across rounds
        round_summaries: List of RoundSummary objects for each completed round
        negotiation_chat_history: List of chat messages during current negotiation
        negotiation_draft_contract: Draft contract from negotiation chat (if any)
        initial_contract_type: Contract type from initial proposal (cannot be changed)
        negotiation_history: List of completed negotiation sessions
        ended_early: Flag indicating if game was ended early by instructor
    """
    round_number: int
    total_rounds: int
    contract: Contract
    cumulative_buyer_profit: float
    cumulative_supplier_profit: float
    historical_demands: List[int]
    method: str = "bootstrap"
    participant_id: str | None = None

    # Aggregates for end-of-game summary
    total_demand: int = 0
    total_sales: int = 0
    total_returns: int = 0
    total_leftovers: int = 0

    round_summaries: List[RoundSummary] = field(default_factory=list)

    # Negotiation state
    negotiation_chat_history: List[Dict[str, str]] = field(default_factory=list)
    negotiation_draft_contract: Contract | None = None
    negotiation_offer_version: int = 0  # Monotonic across negotiations in this session
    negotiation_lock: Any = field(default_factory=RLock, repr=False, compare=False)
    initial_contract_type: str | None = None
    
    #BOT ADDITION
    personality: str | None = None

    # Storage for completed negotiations (for logging and analysis)
    negotiation_history: List[Dict[str, Any]] = field(default_factory=list)

    # Flag to mark if game was ended early by instructor
    ended_early: bool = False

    def is_contract_expired(self) -> bool:
        """
        Checks if the current contract has expired.

        Inputs:
            None (uses self.contract).

        What happens:
            Checks if remaining_rounds is less than or equal to 0.

        Output:
            Returns True if contract is expired, False otherwise.

        Context:
            Used to determine if a new contract needs to be negotiated.
            Called before allowing order placement.
        """
        return self.contract.remaining_rounds <= 0


# ================================
# Simulation Functions
# ================================

def simulate_round(contract: Contract, round_input: RoundInput) -> RoundOutput:
    """
    Simulates one round of the supply chain game under a given contract.

    Inputs:
        contract: Contract object containing contract terms (prices, type, etc.).
        round_input: RoundInput object containing order quantity and realized demand.

    What happens:
        Gets current economic parameters from config.
        Calculates sales (min of order quantity and demand).
        Calculates unsold units.
        Based on contract type (buyback):
            - Calculates returns (buyer returns units to supplier under buyback)
            - Calculates leftovers (unsold minus returns)
            - Calculates all revenue and cost components for buyer and supplier
            - Calculates profits for both parties
        Decrements contract's remaining_rounds by 1.
        Creates and returns RoundOutput with all calculated values.

    Output:
        Returns a RoundOutput object containing:
        - Quantities (sales, unsold, returns, leftovers)
        - Revenues, costs, and profits for buyer and supplier
        - Detailed component breakdowns for transparency

    Context:
        Core simulation function - calculates one round's results.
        Called by simulate_game_round() for each order placed.
        Supports buyback contracts only.
        All economic calculations happen here based on contract terms.
    """
    params = get_current_params()
    Q = round_input.order_quantity
    D = round_input.realized_demand

    # Calculate sales and unsold units
    sales = min(Q, D)
    unsold = max(Q - D, 0)
    returns = 0
    leftovers = unsold

    buyer_profit = 0.0
    supplier_profit = 0.0

    # Initialize all revenue and cost components
    retail_revenue = 0.0
    salvage_revenue_buyer = 0.0
    buyback_refund_buyer = 0.0
    wholesale_cost_buyer = 0.0
    return_shipping_cost_buyer = 0.0
    wholesale_revenue_supplier = 0.0
    salvage_revenue_supplier = 0.0
    production_cost_supplier = 0.0
    buyback_cost_supplier = 0.0
    return_handling_cost_supplier = 0.0

    ct = contract.contract_type or "buyback"

    # Buyback contract
    if ct == "buyback":
        # All unsold units are returned under buyback terms
        returns = unsold
        leftovers = 0

        # Buyer side calculations
        retail_revenue = params.retail_price * sales
        salvage_revenue_buyer = 0.0
        buyback_refund_buyer = contract.buyback_price * returns
        wholesale_cost_buyer = contract.wholesale_price * Q
        return_shipping_cost_buyer = params.return_shipping_buyer * returns

        buyer_profit = (
            retail_revenue
            + salvage_revenue_buyer
            + buyback_refund_buyer
            - wholesale_cost_buyer
            - return_shipping_cost_buyer
        )

        # Supplier side calculations
        wholesale_revenue_supplier = contract.wholesale_price * Q
        salvage_revenue_supplier = params.supplier_salvage_value * returns
        production_cost_supplier = params.supplier_cost * Q
        buyback_cost_supplier = contract.buyback_price * returns
        return_handling_cost_supplier = params.return_handling_supplier * returns

        supplier_profit = (
            wholesale_revenue_supplier
            + salvage_revenue_supplier
            - production_cost_supplier
            - buyback_cost_supplier
            - return_handling_cost_supplier
        )

    # Fallback: simple wholesale or unsupported contract types
    else:
        returns = 0
        leftovers = unsold

        retail_revenue = params.retail_price * sales
        salvage_revenue_buyer = params.buyer_salvage_value * leftovers
        wholesale_cost_buyer = contract.wholesale_price * Q

        buyer_profit = retail_revenue + salvage_revenue_buyer - wholesale_cost_buyer

        wholesale_revenue_supplier = contract.wholesale_price * Q
        production_cost_supplier = params.supplier_cost * Q

        supplier_profit = wholesale_revenue_supplier - production_cost_supplier

    # Aggregate revenue and cost totals
    buyer_revenue = (
        retail_revenue
        + salvage_revenue_buyer
        + buyback_refund_buyer
    )
    buyer_cost = (
        wholesale_cost_buyer
        + return_shipping_cost_buyer
    )

    supplier_revenue = (
        wholesale_revenue_supplier
        + salvage_revenue_supplier
    )
    supplier_cost = (
        production_cost_supplier
        + buyback_cost_supplier
        + return_handling_cost_supplier
    )

    # Update remaining rounds on contract
    contract.remaining_rounds -= 1

    return RoundOutput(
        order_quantity=Q,
        realized_demand=D,
        sales=sales,
        unsold=unsold,
        returns=returns,
        leftovers=leftovers,
        buyer_revenue=buyer_revenue,
        buyer_cost=buyer_cost,
        buyer_profit=buyer_profit,
        supplier_revenue=supplier_revenue,
        supplier_cost=supplier_cost,
        supplier_profit=supplier_profit,
        retail_revenue=retail_revenue,
        salvage_revenue_buyer=salvage_revenue_buyer,
        buyback_refund_buyer=buyback_refund_buyer,
        wholesale_cost_buyer=wholesale_cost_buyer,
        return_shipping_cost_buyer=return_shipping_cost_buyer,
        wholesale_revenue_supplier=wholesale_revenue_supplier,
        salvage_revenue_supplier=salvage_revenue_supplier,
        production_cost_supplier=production_cost_supplier,
        buyback_cost_supplier=buyback_cost_supplier,
        return_handling_cost_supplier=return_handling_cost_supplier,
    )


def simulate_game_round(state: GameState, order_quantity: int) -> tuple[RoundOutput, GameState]:
    """
    Simulates one complete game round including demand generation and state updates.

    Inputs:
        state: Current GameState object containing game progress and contract.
        order_quantity: Number of units the student wants to order (Q).

    What happens:
        Generates demand using historical data and configured method (bootstrap/normal).
        Adds generated demand to session's historical_demands list.
        Creates RoundInput with order quantity and realized demand.
        Calls simulate_round() to calculate round results.
        Updates cumulative profits (buyer and supplier).
        Updates aggregate statistics (total_demand, total_sales, total_returns, total_leftovers).
        Creates RoundSummary and adds it to state.round_summaries.
        Increments state.round_number by 1.

    Output:
        Returns a tuple of (RoundOutput, GameState):
        - RoundOutput: Detailed results from this round
        - GameState: Updated game state with new round and aggregates

    Context:
        Main game round simulation function.
        Called by place_order() endpoint when student places an order.
        This is the core gameplay loop - one call = one round of the game.
        Updates all game state including profits, aggregates, and round history.
    """
    # Generate demand for this round
    D = generate_demand(state.historical_demands, method=state.method)

    # Add generated demand to session's history
    state.historical_demands.append(D)

    # Package round input
    round_input = RoundInput(order_quantity=order_quantity, realized_demand=D)

    # Run the round simulation
    round_output = simulate_round(state.contract, round_input)

    # Update cumulative profits
    state.cumulative_buyer_profit += round_output.buyer_profit
    state.cumulative_supplier_profit += round_output.supplier_profit

    # Update aggregate statistics
    state.total_demand += D
    state.total_sales += round_output.sales
    state.total_returns += round_output.returns
    state.total_leftovers += round_output.leftovers

    # Record per-round summary for logging
    state.round_summaries.append(
        RoundSummary(
            round_index=state.round_number,
            order_quantity=order_quantity,
            realized_demand=D,
            buyer_revenue=round_output.buyer_revenue,
            buyer_cost=round_output.buyer_cost,
            buyer_profit=round_output.buyer_profit,
            supplier_revenue=round_output.supplier_revenue,
            supplier_cost=round_output.supplier_cost,
            supplier_profit=round_output.supplier_profit,
            # Contract details for logging
            wholesale_price=state.contract.wholesale_price,
            buyback_price=state.contract.buyback_price,
            contract_length=state.contract.length,
            remaining_rounds=state.contract.remaining_rounds,
            contract_type=state.contract.contract_type,
        )
    )

    # Increment round number for next round
    state.round_number += 1
    return round_output, state


def generate_demand(historical_demands: List[int], method: str = "bootstrap") -> int:
    """
    Generates a random demand value for one round.

    Inputs:
        historical_demands: List of historical demand values to use for generation.
        method: "bootstrap" (sample from history) or "normal" (normal distribution).

    What happens:
        If method is "bootstrap":
            - Randomly selects one value from historical_demands list.
        If method is "normal":
            - Calculates mean and standard deviation from historical_demands.
            - Generates a random value from normal distribution with those parameters.
            - Ensures value is non-negative (clamps to 0 if negative).
        If method is invalid, raises ValueError.

    Output:
        Returns an integer representing the generated demand value.

    Context:
        Called by simulate_game_round() to generate demand for each round.
        Bootstrap method preserves exact historical distribution.
        Normal method creates smoother distribution based on statistics.
        Instructor can choose method when starting a game.
    """
    if method == "bootstrap":
        return random.choice(historical_demands)

    elif method == "normal":
        mean = statistics.mean(historical_demands)
        stdev = statistics.stdev(historical_demands) if len(historical_demands) > 1 else 1
        return max(0, int(random.gauss(mean, stdev)))

    else:
        raise ValueError("Unknown demand generation method")


# ================================
# Testing / Development
# ================================

if __name__ == "__main__":
    """
    Standalone testing code for simulation logic.
    """
    history = [50, 60, 70, 55, 65]

    contract = Contract(
        wholesale_price=10,
        buyback_price=4,
        length=3
    )
    state = GameState(
        round_number=1,
        total_rounds=3,
        contract=contract,
        cumulative_buyer_profit=0.0,
        cumulative_supplier_profit=0.0,
        historical_demands=history
    )

    print("Starting standalone game simulation...\n")
    print(f"[NEGOTIATION] bot personality = {state.personality}")
    for _ in range(3):
        out, state = simulate_game_round(state, order_quantity=100)
        print(f"Round {state.round_number - 1}:")
        print(out)
        print("Remaining contract rounds:", state.contract.remaining_rounds)
        print()

    print("Final buyer profit:", state.cumulative_buyer_profit)
    print("Final supplier profit:", state.cumulative_supplier_profit)
