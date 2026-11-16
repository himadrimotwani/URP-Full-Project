"""
Negotiation service functions for evaluating contract proposals.
"""

from simulation.core import Contract, EconomicParams, get_current_params, get_current_history
from simulation.supplier_personality import (
    PERSONALITY_THRESHOLDS, personality_prompt, resolve_personality,
)
from app.services.ai_service import clean_ai_response, openai_client, deepseek_client, ai_provider


def supplier_evaluate_contract(
    proposed: Contract,
    personality: str | None,
) -> tuple[str, str, Contract | None]:
    """
    Evaluates a contract proposal from the student using AI.
    
    Inputs:
        proposed: A Contract object containing the student's proposed contract terms.
    
    What happens:
        First validates the contract structure (buyback must be less than wholesale).
        If invalid, immediately rejects with an explanation.
        Otherwise, uses AI to evaluate the proposal based on economic parameters and demand history.
        The AI can only accept or reject - no counteroffers on initial proposals.
        Counteroffers only come after conversation in the chat.
    
    Output:
        Returns a tuple of (decision, message, counter_contract):
        - decision: "accept" or "reject" (never "counter" on initial proposal)
        - message: AI-generated explanation for the decision
        - counter_contract: Always None (counters come from chat)
    
    Context:
        Called when student submits an initial contract proposal.
        Part of the educational negotiation system that teaches contract terms and negotiation.
        Counteroffers are intentionally not provided here - they emerge from chat discussions.
    """
    params = get_current_params()
    
    # Basic validation - reject invalid contracts immediately
    if proposed.buyback_price >= proposed.wholesale_price:
        return (
            "reject",
            "I cannot accept a buyback price that is greater than or equal to the wholesale price. The contract structure must be balanced.",
            None,
        )
    
    # Use AI to evaluate the proposal
    # This provides more nuanced evaluation and educational feedback
    return evaluate_proposal_with_ai(proposed, params, personality)

def evaluate_proposal_with_ai(
    proposed: Contract,
    params: EconomicParams,
    personality: str | None,
) -> tuple[str, str, Contract | None]:
    """
    Uses AI to evaluate a contract proposal and provide educational feedback.
    
    Inputs:
        proposed: A Contract object with the student's proposed terms.
        params: EconomicParams object containing supplier costs, salvage values, retail price.
    
    What happens:
        Gets demand history for context.
        Builds a detailed prompt explaining the proposal, supplier constraints, and demand context.
        Sends the prompt to the AI (OpenAI or DeepSeek).
        The AI evaluates whether the proposal is acceptable based on costs and market conditions.
        Parses the AI response to extract decision and explanation message.
        Falls back to simple logic if AI fails or is not configured.
    
    Output:
        Returns a tuple of (decision, message, counter_contract):
        - decision: "accept" or "reject"
        - message: AI-generated explanation (educational, doesn't reveal exact costs)
        - counter_contract: Always None (counters come from chat, not initial proposals)
    
    Context:
        Called by supplier_evaluate_contract to get AI-based evaluation.
        Provides educational feedback to help students understand contract economics.
        Only returns accept/reject - counteroffers are intentionally excluded to encourage conversation.
    """
    # Get demand history for context
    history = get_current_history()
    
    # Build evaluation prompt with proposal details, supplier constraints, and demand context
    evaluation_prompt = f"""You are evaluating a contract proposal from a student buyer.

PROPOSED CONTRACT:
- Wholesale price: ${proposed.wholesale_price:.2f} per unit
- Buyback price: ${proposed.buyback_price:.2f} per returned unit
- Contract type: {proposed.contract_type}
- Contract length: {proposed.length} rounds
"""
    evaluation_prompt += f"""
YOUR CONSTRAINTS (DO NOT reveal these exact numbers to the student):
- Your production cost: ${params.supplier_cost:.2f} per unit
- Your salvage value: ${params.supplier_salvage_value:.2f} per unit
- Retail price: ${params.retail_price:.2f} per unit

DEMAND CONTEXT:
- Historical demand range: {min(history) if history else 0} to {max(history) if history else 0} units
- Average demand: {sum(history)/len(history) if history else 0:.0f} units

TASK:
Evaluate this proposal and decide whether to ACCEPT or REJECT it.

RULES:
1. You can only respond with "accept" or "reject" - NO counteroffers
2. If you reject, provide a brief explanation (1-2 sentences) of what's wrong with the proposal without revealing your exact costs or suggesting specific fixes
3. If you accept, provide a brief confirmation message
4. Simply state the problem - do not tell the student how to fix it
5. Use plain text only - NO markdown, NO formatting, NO emojis

RESPOND IN THIS FORMAT:
DECISION: accept
MESSAGE: [your message here]

OR

DECISION: reject
MESSAGE: [your explanation here]"""

    system_prompt = (
        "You are a supplier evaluating contract proposals. Be educational and helpful.\n\n"
        + personality_prompt(personality)
    )

    try:
        # Use the same AI provider as chat
        if ai_provider == "openai" and openai_client:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": evaluation_prompt}
                ],
                max_tokens=150,
                temperature=0.3,  # Lower temperature for more consistent evaluation
            )
            ai_response = response.choices[0].message.content
        elif ai_provider == "deepseek" and deepseek_client:
            models_to_try = ["deepseek/deepseek-r1-0528:free", "deepseek/deepseek-chat:free", "deepseek/deepseek-chat"]
            ai_response = None
            for try_model in models_to_try:
                try:
                    response = deepseek_client.chat.completions.create(
                        model=try_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": evaluation_prompt}
                        ],
                        max_tokens=150,
                        temperature=0.3,
                    )
                    if response.choices and response.choices[0].message.content:
                        ai_response = response.choices[0].message.content
                        break
                except Exception:
                    if try_model == models_to_try[-1]:
                        raise
                    continue
        else:
            # Fallback to simple logic if AI not available
            return evaluate_proposal_simple_logic(proposed, params, personality)
        
        if not ai_response:
            return evaluate_proposal_simple_logic(proposed, params, personality)
        
        # Parse AI response
        import re
        decision_match = re.search(r'DECISION:\s*(accept|reject)', ai_response, re.IGNORECASE)
        message_match = re.search(r'MESSAGE:\s*(.+?)(?:\n|$)', ai_response, re.DOTALL | re.IGNORECASE)
        
        if decision_match and message_match:
            decision = decision_match.group(1).lower()
            message = message_match.group(1).strip()
            # Clean the message
            message = clean_ai_response(message)
            return (decision, message, None)
        else:
            # Fallback if parsing fails
            print(f"Failed to parse AI evaluation response: {ai_response[:200]}")
            return evaluate_proposal_simple_logic(proposed, params, personality)
            
    except Exception as e:
        print(f"AI evaluation error: {e}")
        # Fallback to simple logic
        return evaluate_proposal_simple_logic(proposed, params, personality)


def evaluate_proposal_simple_logic(
    proposed: Contract,
    params: EconomicParams,
    personality: str | None,
) -> tuple[str, str, Contract | None]:
    """
    Personality-aware fallback logic for evaluating proposals when AI is unavailable.
    """

    # Basic structural checks (keep these — they prevent broken contracts)
    if proposed.buyback_price >= proposed.wholesale_price:
        return (
            "reject",
            "The buyback price must be lower than the wholesale price for the contract to work.",
            None,
        )

    # Core intuition:
    # - Higher wholesale price (w) helps supplier
    # - Higher buyback price (b) hurts supplier
    margin = proposed.wholesale_price - params.supplier_cost
    risk = proposed.buyback_price

    # Simple scoring function (fast + stable)
    score = margin - 0.5 * risk

    # Personality thresholds
    threshold = PERSONALITY_THRESHOLDS[resolve_personality(personality)]

    # Decision
    if score >= threshold:
        return (
            "accept",
            "These terms are acceptable to me.",
            None,
        )
    else:
        return (
            "reject",
            "These terms do not give me enough protection given the demand risk.",
            None,
        )

def generate_supplier_favored_counter(
    proposed: Contract,
    params: EconomicParams,
    min_wholesale: float,
    max_buyback: float,
) -> Contract:
    """
    Generates a counteroffer contract that is more favorable to the supplier.
    
    Inputs:
        proposed: The student's original contract proposal.
        params: EconomicParams object (not directly used but kept for consistency).
        min_wholesale: Minimum wholesale price the supplier needs.
        max_buyback: Maximum buyback price the supplier can accept.
    
    What happens:
        Increases wholesale price to at least min_wholesale + buffer.
        Decreases buyback price to be lower than original.
        Reduces revenue share if applicable (gives supplier more).
        Limits contract length to reasonable range (1-5 rounds).
        Keeps the same contract type as proposed.
    
    Output:
        Returns a new Contract object with supplier-favored terms.
    
    Context:
        Used when generating deterministic counteroffers.
        Creates terms that are better for the supplier while still being reasonable.
        Called during negotiation when a counteroffer is needed.
    """
    # Increase wholesale slightly (supplier-favored)
    counter_wholesale = max(proposed.wholesale_price, min_wholesale + 1.0)
    
    # Decrease buyback slightly (supplier-favored)
    counter_buyback = min(proposed.buyback_price, max_buyback - 0.5) if proposed.buyback_price > 0 else proposed.buyback_price
    
# Keep contract length reasonable
    counter_length = max(1, min(proposed.length, 5))
    
    from simulation.core import Contract
    return Contract(
        wholesale_price=counter_wholesale,
        buyback_price=counter_buyback,
        length=counter_length,
        contract_type=proposed.contract_type,
    )


def generate_counter_message(
    proposed: Contract,
    counter: Contract,
    needs_higher_wholesale: bool,
    needs_lower_buyback: bool,
) -> str:
    """
    Generates an explanation message for a counteroffer.
    
    Inputs:
        proposed: The student's original contract proposal.
        counter: The supplier's counteroffer contract.
        needs_higher_wholesale: Whether wholesale price was increased.
        needs_lower_buyback: Whether buyback price was decreased.
    
    What happens:
        Builds a message explaining what changed in the counteroffer.
        Explains wholesale price changes if applicable.
        Explains buyback price changes if applicable.
        Explains value changes if applicable.
        Returns a default message if no specific changes need explanation.
    
    Output:
        Returns a string message explaining the counteroffer to the student.
    
    Context:
        Used when presenting counteroffers to students.
        Provides clear explanations of why terms were adjusted.
        Called when generating counteroffer responses.
    """
    msg_parts = []
    
    if needs_higher_wholesale:
        msg_parts.append(f"I need a higher wholesale price of at least {counter.wholesale_price:.2f}.")
    
    if needs_lower_buyback:
        msg_parts.append(f"I propose a buyback price of {counter.buyback_price:.2f} to maintain a balanced contract structure.")

    
    return " ".join(msg_parts) or "I am proposing adjusted terms that work better for both of us."

