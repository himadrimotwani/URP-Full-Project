"""
AI service for generating chat responses and detecting agreement in negotiations.
Includes AI client initialization and response parsing utilities.
"""

import os
from typing import Any
import json
import re
import statistics
from openai import OpenAI
from dotenv import load_dotenv

from simulation.core import Contract, GameState, get_current_params, get_current_history
from app.services.config_service import load_negotiation_config

# ============================================================================
# AI Client Initialization
# ============================================================================

# Load environment variables from .env file
# Force-load .env and override any existing environment variables so changes take effect
load_dotenv(override=True)

# AI client for negotiation chat (Step 3)
# Supports both OpenAI and DeepSeek via OpenRouter
# Priority: OpenAI if OPENAI_API_KEY is set, otherwise DeepSeek via OpenRouter if OPENROUTER_API_KEY is set
openai_client = None
deepseek_client = None
# Default provider is none until we detect a valid key
ai_provider = None  # "openai" or "deepseek"

# Try DeepSeek/OpenRouter first if configured (prefer DeepSeek when present)
openrouter_key = os.getenv("OPENROUTER_API_KEY")
if openrouter_key and openrouter_key.strip() and not openrouter_key.startswith("sk-or-v1-your-"):
    if "your" in openrouter_key.lower() or "here" in openrouter_key.lower() or len(openrouter_key) < 20:
        print("WARNING: OPENROUTER_API_KEY appears to be a placeholder. Please set a real API key in .env file.")
    else:
        deepseek_client = OpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1"
        )
        ai_provider = "deepseek"
        print("DeepSeek client initialized via OpenRouter for negotiation chat")
else:
    # Fallback to OpenAI if OpenRouter/DeepSeek isn't configured
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key.strip() and not openai_key.startswith("sk-your-"):
        if "your" in openai_key.lower() or "here" in openai_key.lower() or len(openai_key) < 20:
            print("WARNING: OPENAI_API_KEY appears to be a placeholder. Please set a real API key in .env file.")
        else:
            openai_client = OpenAI(api_key=openai_key)
            ai_provider = "openai"
            print("OpenAI client initialized for negotiation chat")

if not openai_client and not deepseek_client:
    print("No AI provider configured. Negotiation chat will use fallback responses.")
    print("To configure: Set OPENAI_API_KEY or OPENROUTER_API_KEY in backend/.env file")

# ============================================================================
# AI Response Parsing Utilities
# ============================================================================

def extract_from_malformed_json(json_str: str) -> dict[str, Any] | None:
    """
    Extracts contract terms from malformed or incomplete JSON strings.
    
    Inputs:
        json_str: A string that should contain JSON but may be malformed or incomplete.
    
    What happens:
        Uses regex patterns to find key-value pairs even if JSON syntax is broken.
        Looks for contract fields: wholesale_price, buyback_price, contract_length, etc.
        Converts numeric values to floats.
        Keeps string values (like contract_type) as strings.
        Returns None if no valid terms found.
    
    Output:
        Returns a dictionary with extracted contract terms, or None if extraction fails.
    
    Context:
        Used as a fallback when AI returns JSON that can't be parsed normally.
        Handles cases where AI returns incomplete JSON (e.g., "wholesale_price: 23.0, buyback_price: 11.0, contract_length:").
        Called by generate_chat_response when JSON parsing fails.
    """
    result = {}
    
    # Try to extract key-value pairs even if JSON is malformed
    patterns = {
        "wholesale_price": r'wholesale_price["\s]*:[\s]*(\d+(?:\.\d+)?)',
        "buyback_price": r'buyback_price["\s]*:[\s]*(\d+(?:\.\d+)?)',
        "contract_length": r'contract_length["\s]*:[\s]*(\d+)',
        "length": r'"length"["\s]*:[\s]*(\d+)',

        "contract_type": r'contract_type["\s]*:[\s]*"([^"]+)"',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, json_str, re.IGNORECASE)
        if match:
            if key == "contract_type":
                result[key] = match.group(1)
            else:
                try:
                    result[key] = float(match.group(1))
                except ValueError:
                    pass
    
    return result if result else None


def extract_contract_terms_from_text(text: str) -> dict[str, Any] | None:
    """
    Extracts final contract terms from natural-language AI responses.
    """
    result: dict[str, Any] = {}

    patterns = {
        "wholesale_price": [
            r'wholesale\s+price\s*:?\s*\$?\s*(\d+(?:\.\d+)?)',
            r'wholesale\s+price\s+(?:is|at|of|to)\s+\$?\s*(\d+(?:\.\d+)?)',
        ],
        "buyback_price": [
            r'buyback\s+price\s*:?\s*\$?\s*(\d+(?:\.\d+)?)',
            r'buyback\s+price\s+(?:is|at|of|to)\s+\$?\s*(\d+(?:\.\d+)?)',
            r'\$\s*(\d+(?:\.\d+)?)\s+buyback',
        ],
        "contract_length": [
            r'contract\s+(?:duration|length)\s*:?\s*(\d+)\s+round',
            r'(?:duration|length)\s*:?\s*(\d+)\s+round',
            r'(\d+)\s+round\s+contract',
        ],
    }

    for key, key_patterns in patterns.items():
        matches: list[str] = []
        for pattern in key_patterns:
            matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
        if matches:
            try:
                result[key] = float(matches[-1])
            except ValueError:
                pass

    return result if result else None


def clean_ai_response(message: str) -> str:
    """
    Cleans AI response text to make it suitable for display to students.
    
    Inputs:
        message: Raw AI response text that may contain markdown, emojis, or technical markers.
    
    What happens:
        Removes NEGOTIATION_COMPLETE markers (technical, not for students).
        Removes CONTRACT_JSON markers and JSON blocks.
        Removes markdown formatting (bold, italic, bullets).
        Removes emojis and special characters.
        Cleans up extra whitespace and newlines.
        If message becomes empty after cleaning, provides a friendly default message.
    
    Output:
        Returns cleaned plain text message suitable for student display.
    
    Context:
        Called before displaying AI messages to students.
        Ensures students only see friendly, readable text without technical details.
        Used in generate_chat_response and evaluate_proposal_with_ai.
    """
    # Remove NEGOTIATION_COMPLETE markers (case insensitive)
    message = re.sub(r'NEGOTIATION_COMPLETE\s*:\s*yes', '', message, flags=re.IGNORECASE)
    message = re.sub(r'negotiation_complete\s*:\s*yes', '', message, flags=re.IGNORECASE)
    
    # Remove any remaining CONTRACT_JSON: text first
    message = re.sub(r'CONTRACT_JSON\s*:?\s*', '', message, flags=re.IGNORECASE)
    # Remove any JSON blocks that might have been missed
    message = re.sub(r'\{[^{}]*"wholesale_price"[^{}]*\}', '', message, flags=re.DOTALL)
    
    # Remove markdown bold (**text**)
    message = re.sub(r'\*\*([^*]+)\*\*', r'\1', message)
    # Remove markdown italic (*text*)
    message = re.sub(r'\*([^*]+)\*', r'\1', message)
    # Remove bullet points and convert to plain text
    message = re.sub(r'^[\s]*[-*•]\s*', '', message, flags=re.MULTILINE)
    # Remove emojis and special characters (but preserve spaces)
    message = re.sub(r'[^\w\s\.,!?;:\-\$\(\)\n]', '', message)
    
    # Fix concatenated words (insert space between lowercase letter and uppercase letter)
    # Example: "word1Word2" -> "word1 Word2"
    message = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', message)
    # Fix concatenated words (insert space between letter and number when appropriate)
    # Example: "word123" -> "word 123" (but be careful not to break prices like "$25")
    message = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', message)
    message = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', message)
    
    # Clean up multiple spaces
    message = re.sub(r' +', ' ', message)
    # Ensure proper newlines (replace multiple newlines with double newline)
    message = re.sub(r'\n{3,}', '\n\n', message)
    # Fix spaces before punctuation (remove extra spaces)
    message = re.sub(r'\s+([\.,!?;:])', r'\1', message)
    
    # If message is empty or only whitespace after cleaning, provide a friendly default
    cleaned = message.strip()
    if not cleaned or cleaned.lower() in ['yes', 'negotiation complete']:
        cleaned = "Great! Let's proceed with these terms."
    
    return cleaned

# ============================================================================
# AI Chat Response Generation
# ============================================================================

def generate_chat_response(
    chat_history: list[dict[str, str]],
    current_draft_contract: Contract | None,
    game_state: GameState | None = None,
    initial_contract_type: str | None = None,
) -> dict[str, Any]:
    """
    Generates an AI response for negotiation chat using OpenAI or DeepSeek.
    
    Inputs:
        chat_history: List of previous chat messages with role and content.
        current_draft_contract: Previous, withdrawn draft used only as context.
        game_state: Current game state for context (demand history, rounds played, etc.).
        initial_contract_type: The contract type from initial proposal (cannot be changed).
    
    What happens:
        Determines which AI client to use (OpenAI or DeepSeek).
        Builds a system prompt with game context, demand history, and negotiation constraints.
        Requests a structured response with the current offer state on every turn.
        Sends conversation history and prompt to AI.
        Parses AI response to extract message and any JSON contract.
        Creates a draft only from complete terms in the latest structured response.
        Returns no draft on missing terms, malformed output, or provider failure.
    
    Output:
        Returns a dictionary with:
        - message: Cleaned AI response message (without technical markers)
        - draft_contract: Contract object if agreement detected, None otherwise
    
    Context:
        Called by negotiation_chat endpoint to generate AI supplier responses.
        Provides educational, conversational negotiation experience.
        Can detect when student agrees and create draft contracts automatically.
    """
    # Determine which client to use
    client = None
    model_name = "deepseek"
    
    if ai_provider == "openai" and openai_client:
        client = openai_client
        model_name = "gpt-4o-mini"  # Using cost-effective model
    elif ai_provider == "deepseek" and deepseek_client:
        client = deepseek_client
        # Use free model - will fallback in error handling if needed
        model_name = "deepseek/deepseek-r1-0528:free"  # Free DeepSeek model via OpenRouter
    
    if not client:
        # Fallback to simple responses if no AI provider is configured
        return {
            "message": "I'm open to discussing contract terms. What would you like to adjust?",
            "draft_contract": None
        }
    
    # Build system prompt with game context
    params = get_current_params()
    history = get_current_history()
    
    # Calculate demand statistics
    if history:
        demand_min = min(history)
        demand_max = max(history)
        demand_avg = statistics.mean(history)
        demand_count = len(history)
    else:
        demand_min = demand_max = demand_avg = 0
        demand_count = 0
    
    # Get game progress info if available
    game_context = ""
    if game_state:
        rounds_played = max(0, game_state.round_number - 1)
        game_context = f"""
Current Game Status:
- Rounds played: {rounds_played} / {game_state.total_rounds}
- Current round: {game_state.round_number}
"""
    
    # Get negotiation config
    neg_config = load_negotiation_config()
    
    # Get the fixed contract type (cannot be changed)
    fixed_contract_type = initial_contract_type or "buyback"
    
    # Build system prompt for chat negotiation
    recent_history_str = ', '.join(map(str, history[-10:])) if history else "0"
    
    # Format contract types list for prompt
    contract_types_str = ', '.join(neg_config.contract_types_available)
    
    # Create a chat-specific system prompt that encourages ongoing negotiation
    system_prompt = f"""You are a fashion supply chain supplier negotiating contract terms with a buyer. Your goal is to reach a mutually beneficial agreement.

BUSINESS CONTEXT:
- You produce fashion items at ${params.supplier_cost:.2f} per unit
- Your salvage value for unsold items: ${params.supplier_salvage_value:.2f} per unit  
- Retail price in market: ${params.retail_price:.2f} per unit
- Buyer salvage value: ${params.buyer_salvage_value:.2f} per unit
- Buyer return shipping cost: ${params.return_shipping_buyer:.2f} per unit
- Your return handling cost: ${params.return_handling_supplier:.2f} per unit

DEMAND HISTORY:
- Total rounds: {demand_count}
- Average demand: {demand_avg:.0f} units
- Range: {demand_min} to {demand_max} units
- Recent history: {recent_history_str}

NEGOTIATION CONSTRAINTS:
- Contract type (fixed): {fixed_contract_type}
- Contract length: {neg_config.length_min} to {neg_config.length_max} rounds
{game_context}

NEGOTIATION GUIDELINES:
1. Be professional and collaborative - aim for win-win agreements
2. Discuss specific terms: wholesale price, buyback price, contract length
3. Explain your reasoning based on costs, risks, and market conditions
4. Ask questions to understand the buyer's priorities and constraints
5. Make counter-proposals when terms don't work for you
6. Continue negotiating until agreement is reached - don't end conversations prematurely
7. When agreement is reached, clearly state the final terms

RESPONSE FORMAT:
Respond naturally as a supplier in conversation. Keep responses conversational and engaging. If you detect agreement on specific terms, you can propose finalizing the contract."""
    
    # A previous draft is context only: starting this turn withdrew that offer.
    if current_draft_contract is not None:
        system_prompt += f"""

PREVIOUS OFFER (withdrawn while negotiations resume):
- Wholesale price: {current_draft_contract.wholesale_price}
- Buyback price: {current_draft_contract.buyback_price}
- Contract length: {current_draft_contract.length}
Use these terms only as context when discussing a replacement offer."""

    # Request offer state on EVERY turn, including revisions after a draft exists.
    system_prompt += f"""

Return ONLY a JSON object in this format:
{{
  "response": "Your conversational supplier message",
  "contract": {{
    "wholesale_price": 25,
    "buyback_price": 10,
    "contract_length": 3,
    "contract_type": "{fixed_contract_type}"
  }}
}}
The numbers above illustrate the format only; use the actual negotiated terms.
Whenever you make, revise, or reaffirm a complete offer, include ALL current terms
in "contract", matching the offer in "response". The student does not need to
say an agreement keyword first. Never copy superseded terms over revised terms.
If you are only discussing terms or any term remains unresolved, set "contract"
to null and ask for clarification. Only the student's Accept Offer action activates
a contract; a chat message does not activate it."""
    
    # Build conversation history for AI (only last 10 messages to stay within token limits)
    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[-10:]:  # Last 10 messages for context
        role = "user" if msg["role"] == "student" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    
    try:
        # For DeepSeek, try alternative models if the free one fails
        models_to_try = [model_name]
        if ai_provider == "deepseek":
            models_to_try = [
                "deepseek/deepseek-r1-0528:free",
                "deepseek/deepseek-chat:free",
                "deepseek/deepseek-chat",
            ]
        
        ai_message = None
        last_error = None
        
        for try_model in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=try_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=350,
                )
                
                # Handle response - check if content exists
                if not hasattr(response, 'choices') or len(response.choices) == 0:
                    last_error = f"Model {try_model} returned no choices"
                    if try_model != models_to_try[-1]:  # Not the last model
                        continue
                    raise ValueError(last_error)
                
                message_obj = response.choices[0].message
                ai_message = message_obj.content if hasattr(message_obj, 'content') else None
                
                # Validate response
                if ai_message and ai_message.strip():
                    # Success - use this response
                    break
                else:
                    # Empty response - try next model if available
                    finish_reason = getattr(response.choices[0], 'finish_reason', None)
                    last_error = f"Model {try_model} returned empty response (finish_reason: {finish_reason})"
                    if try_model != models_to_try[-1]:  # Not the last model
                        print(f"DeepSeek: Trying alternative model. {last_error}")
                        continue
                    raise ValueError(last_error)
                    
            except Exception as e:
                error_str = str(e)
                last_error = f"Model {try_model}: {error_str}"
                # If it's a model not found error and we have more models to try, continue
                if ("model" in error_str.lower() or "not found" in error_str.lower() or "404" in error_str) and try_model != models_to_try[-1]:
                    print(f"DeepSeek: Model {try_model} not available, trying next model")
                    continue
                # Otherwise, re-raise if it's the last model
                if try_model == models_to_try[-1]:
                    raise
                # Continue to next model
                continue
        
        if not ai_message or not ai_message.strip():
            raise ValueError(f"All models failed. Last error: {last_error}")
        
        # Never reconstruct an offer from older chat when the latest response is
        # unstructured or malformed: doing so can resurrect superseded terms.
        ai_message_clean = ai_message.strip()
        ai_message_clean = re.sub(r'^```(?:json)?\s*', '', ai_message_clean, flags=re.MULTILINE)
        ai_message_clean = re.sub(r'```\s*$', '', ai_message_clean, flags=re.MULTILINE)
        try:
            response_data = json.loads(ai_message_clean.strip())
            if not isinstance(response_data, dict):
                raise ValueError("Expected a JSON object")
            cleaned_message = response_data.get("response", "")
            if not isinstance(cleaned_message, str) or not cleaned_message.strip():
                raise ValueError("Empty response field in JSON")
            cleaned_message = cleaned_message.strip()
            json_contract = response_data.get("contract")
            if not isinstance(json_contract, dict):
                json_contract = None
        except (ValueError, KeyError, TypeError):
            cleaned_message = ai_message.strip()
            json_contract = None
        
        # Get initial contract type from game state (contract type cannot be changed during negotiation)
        initial_ct = None
        if game_state:
            initial_ct = game_state.initial_contract_type
        
        # Create Contract object from JSON if present
        draft_contract = None
        if json_contract:
            try:
                params = get_current_params()
                neg_config = load_negotiation_config()
                
                # Handle both "contract_length" and "length" keys for backward compatibility
                contract_length = json_contract.get("contract_length", json_contract.get("length"))
                contract_type_to_use = initial_ct or "buyback"
                
                # Create Contract object from JSON data
                draft_contract = Contract(
                    wholesale_price=float(json_contract["wholesale_price"]),
                    buyback_price=float(json_contract["buyback_price"]),
                    length=int(contract_length),
                    contract_type=contract_type_to_use,
                )
                
                # Validate and clamp contract values to ensure they're within allowed ranges
                if draft_contract.wholesale_price > 0 and draft_contract.buyback_price >= 0 and draft_contract.buyback_price < draft_contract.wholesale_price:
                    # Clamp contract length to valid range
                    draft_contract.length = max(neg_config.length_min, min(draft_contract.length, neg_config.length_max))
                    
                    # Validate contract_type is valid
                    if draft_contract.contract_type not in ("buyback",):
                        draft_contract.contract_type = "buyback"
                else:
                    # Invalid contract values - discard it
                    print(f"Invalid contract from JSON: wholesale={draft_contract.wholesale_price}, buyback={draft_contract.buyback_price}")
                    cleaned_message = (
                        f"{cleaned_message}\n\nI cannot prepare the accept/reject offer yet because the buyback price "
                        "must be lower than the wholesale price in this version of the contract."
                    )
                    draft_contract = None
            except (ValueError, KeyError, TypeError) as e:
                # Error creating contract from JSON - log and continue without draft contract
                print(f"Error creating contract from JSON: {e}")
                draft_contract = None
        
        return {
            "message": cleaned_message,
            "draft_contract": draft_contract
        }
    except Exception as e:
        # Better error logging for debugging
        error_msg = str(e)
        print(f"AI API error ({ai_provider}): {error_msg}")
        print(f"Model: {model_name}")
        print(f"Messages count: {len(messages)}")
        
        # Provide more helpful fallback that maintains conversation
        fallback_responses = [
            "I understand you're asking about contract terms. Could you be more specific about what you'd like to adjust?",
            "Let me help you understand the contract structure. What specific term would you like to discuss?",
            "I'm here to negotiate. What changes are you proposing to the contract?",
        ]
        
        # Use a simple rotation based on message count to vary responses
        fallback_index = len(chat_history) % len(fallback_responses)
        
        return {
            "message": fallback_responses[fallback_index],
            "draft_contract": None
        }
