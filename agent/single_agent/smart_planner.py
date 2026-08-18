"""
Smart Planner - Query Classification & Slot Extraction

This module provides the expanded planner with:
1. 8+ query type classification
2. Confidence scoring
3. Slot extraction (budget, category, use_case)
4. Missing slot detection
5. Follow-up query detection

Query Types:
- price_search: "iPhone 15 price"
- comparison: "iPhone vs Samsung"
- best_under: "Best phones under 45k"
- product_advice: "What to look for in a phone?"
- feature_query: "Does iPhone 15 have wireless charging?"
- follow_up: "Show cheaper ones" (context-dependent)
- conversational: "Hi", "Thanks"
- unknown: Fallback with suggestions
"""

import re
from typing import Tuple, Dict, List, Optional

# ════════════════════════════════════════════════════════════
# LLM CLASSIFICATION
# ════════════════════════════════════════════════════════════

LLM_CLASSIFICATION_PROMPT = """You are a shopping assistant query classifier. Classify the user's query into exactly ONE of these types:

QUERY TYPES:
- price_search: User wants to find price of a specific product (e.g., "iPhone 15 price", "how much is MacBook Air", "DDR5 RAM cost")
- comparison: User wants to compare 2+ products (e.g., "iPhone vs Samsung", "which is better A or B")
- best_under: User wants recommendations under a budget (e.g., "best phones under 45k", "top laptops below 1 lakh")
- product_advice: User wants buying guidance (e.g., "what to look for in a laptop", "how to choose a monitor")
- feature_query: User asks about specific features (e.g., "does iPhone have wireless charging", "what's the battery life of Pixel")
- conversational: Greetings, thanks, chitchat (e.g., "hi", "thanks", "hello")
- unknown: Completely unrelated to shopping (e.g., "sing a song", "what's the weather")

Also extract these slots if present:
- category: The product category (phone, laptop, headphones, earbuds, smartwatch, tablet, tv, camera, speaker, monitor, ram, ssd, gpu, etc.)
- budget: The budget amount in numbers (convert 45k to 45000, 1 lakh to 100000)
- use_case: Intended use (gaming, work, photography, study, music, etc.)
- product: The specific product name if mentioned

USER QUERY: "{query}"

Respond in this EXACT JSON format (no markdown, no explanation):
{{"query_type": "type_here", "category": "category_or_null", "budget": number_or_null, "use_case": "use_case_or_null", "product": "product_name_or_null"}}"""


def _parse_json_robust(response_text: str) -> Dict:
    """
    Robust JSON parsing with multiple fallback strategies.
    Handles: markdown blocks, extra text, malformed JSON.
    """
    import json
    import re
    
    text = response_text.strip()
    
    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except:
        pass
    
    # Strategy 2: Remove markdown code blocks
    if "```" in text:
        # Extract content between ```
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except:
                pass
    
    # Strategy 3: Find JSON object with regex
    json_match = re.search(r'\{[^{}]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    
    # Strategy 4: Try to repair common JSON errors
    # Fix: unquoted null values
    repaired = re.sub(r':\s*null\b', ': null', text, flags=re.IGNORECASE)
    repaired = re.sub(r':\s*None\b', ': null', repaired)
    # Fix: single quotes to double quotes
    repaired = repaired.replace("'", '"')
    # Extract JSON object
    json_match = re.search(r'\{[^{}]*\}', repaired)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass
    
    # Strategy 5: Manual extraction with regex
    result = {}
    type_match = re.search(r'"query_type":\s*"([^"]+)"', text)
    if type_match:
        result['query_type'] = type_match.group(1)
    cat_match = re.search(r'"category":\s*"([^"]+)"', text)
    if cat_match:
        result['category'] = cat_match.group(1)
    budget_match = re.search(r'"budget":\s*(\d+)', text)
    if budget_match:
        result['budget'] = int(budget_match.group(1))
    product_match = re.search(r'"product":\s*"([^"]+)"', text)
    if product_match:
        result['product'] = product_match.group(1)
    
    if result:
        return result
    
    raise ValueError(f"Could not parse JSON from: {text[:100]}...")


def _llm_classify(query: str, max_retries: int = 2) -> Dict:
    """
    Use Google Lite LLM to classify query.
    Fast, accurate 8-type classification with slot extraction.
    """
    from config.llm_config import get_google_lite
    
    llm = get_google_lite()
    prompt = LLM_CLASSIFICATION_PROMPT.format(query=query)
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # Retry with error feedback
                retry_prompt = f"""{prompt}

IMPORTANT: Your previous response had a JSON error: {last_error}
Please respond with ONLY valid JSON, no other text."""
                response = llm.invoke(retry_prompt)
            else:
                response = llm.invoke(prompt)
            
            # Robust parsing
            result = _parse_json_robust(response)
            
            # Validate query_type
            valid_types = ['price_search', 'comparison', 'best_under', 'product_advice', 
                           'feature_query', 'conversational', 'unknown']
            query_type = result.get('query_type', 'unknown')
            if query_type not in valid_types:
                query_type = 'unknown'
            
            # Build slots dict
            slots = {}
            if result.get('category'):
                slots['category'] = result['category'].lower()
            if result.get('budget'):
                slots['budget'] = int(result['budget'])
            if result.get('use_case'):
                slots['use_case'] = result['use_case'].lower()
            if result.get('product'):
                slots['product'] = result['product']
            
            return {
                'query_type': query_type,
                'confidence': 0.9,
                'slots': slots,
                'source': 'llm'
            }
            
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                print(f"  [LLM Fallback] Retry {attempt + 1}/{max_retries}: {e}")
            else:
                print(f"  [LLM Fallback] Failed after {max_retries + 1} attempts: {e}")
    
    # On failure, return low confidence so regex result is used instead
    return {
        'query_type': 'price_search',  # Default to price_search (safest for product queries)
        'confidence': 0.0,  # Zero confidence means regex result will be preferred
        'slots': {},
        'source': 'llm_error'
    }


# ════════════════════════════════════════════════════════════
# SLOT VALIDATION (must be before smart_classify_and_extract)
# ════════════════════════════════════════════════════════════

def get_missing_slots(query_type: str, slots: dict) -> list:
    """Check for missing required slots based on query type."""
    required = {
        'price_search': ['product'],
        'comparison': ['product_a', 'product_b'],
        'best_under': ['category'],  # budget is nice-to-have
        'product_advice': ['category'],
        'feature_query': ['product'],
        'follow_up': [],
        'conversational': [],
        'unknown': [],
    }
    
    needed = required.get(query_type, [])
    missing = [slot for slot in needed if not slots.get(slot)]
    return missing


# ════════════════════════════════════════════════════════════
# MAIN PLANNER FUNCTION (with LLM fallback)
# ════════════════════════════════════════════════════════════

# NOTE: Now LLM-ONLY classification (no regex fallback)
LLM_ONLY_MODE = True

def smart_classify_and_extract(
    query: str, 
    conversation_history: List = None,
    previous_products: List = None,
    use_llm_fallback: bool = True
) -> Dict:
    """
    Main function: Classify query and extract all slots.
    
    Uses HYBRID approach:
    1. Try regex classification first (fast, ~5ms)
    2. If confidence <= 0.7, use LLM fallback (accurate, ~500ms)
    
    Args:
        query: User's query
        conversation_history: Previous conversation turns
        previous_products: Products from last response
        use_llm_fallback: Whether to use LLM when regex confidence is low
        
    Returns:
        Dict with: query_type, confidence, slots, missing_slots, is_follow_up, fallback_message
    """
    has_context = bool(previous_products) or bool(conversation_history)
    
    # LLM-ONLY Classification (fast with Google Lite ~300ms)
    print(f"  [Planner] Classifying with Google Lite...")
    
    llm_result = _llm_classify(query)
    query_type = llm_result['query_type']
    confidence = llm_result['confidence']
    slots = llm_result.get('slots', {})
    source = 'llm'
    
    print(f"  [Planner] LLM result: {query_type} ({confidence:.0%})")
    
    # Fallback to regex ONLY if LLM completely fails
    if llm_result.get('source') == 'llm_error':
        print(f"  [Planner] LLM failed, falling back to regex...")
        query_type, confidence = classify_query(query, has_context)
        slots = extract_slots(query)
        source = 'regex_fallback'
    
    # ════════════════════════════════════════════════════════════
    # CLEANUP: Remove garbage slots for non-shopping queries
    # ════════════════════════════════════════════════════════════
    if query_type in ['conversational', 'unknown']:
        # Don't extract "product" from greetings like "hello how are you"
        slots.pop('product', None)
        slots.pop('product_a', None)
        slots.pop('product_b', None)
    
    # Check for missing required slots
    missing = get_missing_slots(query_type, slots)
    
    # Determine if follow-up - ONLY if previous products exist
    is_follow_up = (
        query_type == 'follow_up' and bool(previous_products)
    ) or (
        bool(previous_products) and 
        len(query.split()) <= 4 and 
        query_type not in ['price_search', 'best_under', 'comparison', 'product_advice']
    )
    
    # Generate fallback if needed
    fallback_message = None

    if query_type == 'unknown':
        fallback_message = generate_fallback_response(query)
    elif missing and confidence < 0.8:
        fallback_message = generate_missing_slot_question(missing, query_type)
    
    return {
        'query_type': query_type,
        'confidence': confidence,
        'slots': slots,
        'missing_slots': missing,
        'is_follow_up': is_follow_up,
        'fallback_message': fallback_message,
        'source': source,  # 'regex' or 'llm'
    }



# ════════════════════════════════════════════════════════════
# FALLBACK RESPONSE GENERATORS
# ════════════════════════════════════════════════════════════



def generate_fallback_response(query: str) -> str:
    """Generate a helpful fallback response for unknown queries."""
    return f"""I'm not sure I understand your query: "{query}"

**I can help you with:**
• Finding product prices (e.g., "iPhone 15 price")
• Comparing products (e.g., "iPhone vs Samsung")
• Recommendations under a budget (e.g., "best phones under 30k")
• Product advice (e.g., "what to look for in a laptop")

Could you please rephrase your question?"""


def generate_missing_slot_question(missing_slots: list, query_type: str) -> str:
    """Generate a question to fill missing required slots."""
    if not missing_slots:
        return None
    
    slot = missing_slots[0]  # Ask about first missing slot
    
    questions = {
        'budget': "What's your budget for this purchase?",
        'category': "What type of product are you looking for?",
        'product': "Which specific product are you interested in?",
        'product_a': "Which product would you like to compare?",
        'product_b': "What's the second product for comparison?",
        'use_case': "What will you primarily use this for?",
    }
    
    return questions.get(slot, f"Could you provide more details about {slot}?")
