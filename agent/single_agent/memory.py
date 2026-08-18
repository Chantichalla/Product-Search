"""
Conversation Memory Manager

This module handles:
1. Conversation history management
2. Slot persistence across turns
3. Follow-up context detection
4. Previous products tracking

The memory enables multi-turn conversations like:
User: "Best phones under 45k"
AI: [Shows 5 phones]
User: "Show cheaper ones"  <- Follow-up, uses context
AI: [Filters to below previous budget]
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import re


@dataclass
class ConversationMemory:
    """
    Manages conversation state across multiple turns.
    
    This is a session-scoped memory that persists during a conversation
    but resets when a new session starts.
    """
    # Conversation history
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Extracted slots (accumulated across turns)
    slots: Dict[str, Any] = field(default_factory=dict)
    
    # Previous products shown to user
    previous_products: List[Dict] = field(default_factory=list)
    
    # Current topic being discussed
    current_topic: str = ""
    
    # Session metadata
    session_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    turn_count: int = 0
    
    def add_user_message(self, message: str):
        """Add a user message to history."""
        self.history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        self.turn_count += 1
    
    def add_assistant_message(self, message: str):
        """Add an assistant message to history."""
        self.history.append({
            "role": "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def update_slots(self, new_slots: Dict):
        """Merge new slots with existing ones (new values override)."""
        self.slots.update(new_slots)
    
    def update_products(self, products: List[Dict]):
        """Update the list of products shown to user."""
        self.previous_products = products
    
    def get_last_n_turns(self, n: int = 5) -> List[Dict]:
        """Get the last N conversation turns."""
        return self.history[-n*2:] if self.history else []
    
    def has_context(self) -> bool:
        """Check if there's meaningful context from previous turns."""
        return bool(self.previous_products) or bool(self.slots)
    
    def clear(self):
        """Clear all memory (start fresh session)."""
        self.history = []
        self.slots = {}
        self.previous_products = []
        self.current_topic = ""
        self.turn_count = 0


# ════════════════════════════════════════════════════════════
# FOLLOW-UP DETECTION
# ════════════════════════════════════════════════════════════

# Patterns that indicate a follow-up query
FOLLOW_UP_INDICATORS = [
    # Refinement
    (r'^show\s+(me\s+)?(?:cheaper|expensive|better|similar|more)\b', 'refinement'),
    (r'^(?:cheaper|expensive|better|similar)\s+(?:ones?|options?)', 'refinement'),
    (r'^more\s+(?:like|similar|options?)\b', 'refinement'),
    (r'^less\s+(?:expensive|costly)\b', 'refinement'),
    
    # Selection
    (r'^(?:the\s+)?(?:first|second|third|fourth|fifth|last|1st|2nd|3rd)\s+(?:one|option)', 'selection'),
    (r'^(?:option\s+)?(?:1|2|3|4|5|one|two|three)\b', 'selection'),
    (r'^(?:tell\s+me\s+)?more\s+about\s+(?:the\s+)?(?:first|second|last|\d+)', 'selection'),
    
    # Clarification
    (r'^what\s+about\s+(?:the\s+)?(?:battery|camera|display|price|specs?)', 'clarification'),
    (r'^(?:and\s+)?(?:the\s+)?(?:battery|camera|display|price)', 'clarification'),
    (r'^how\s+(?:about|is)\s+(?:the\s+)?(?:battery|camera|display)', 'clarification'),
    
    # Comparison of shown products
    (r'^compare\s+(?:the\s+)?(?:first|second|last|these|them)\b', 'comparison'),
    (r'^which\s+(?:one\s+)?(?:is\s+)?(?:better|best)\b', 'comparison'),
    
    # Continuation
    (r'^(?:and|also|what\s+else)\b', 'continuation'),
    (r'^(?:any\s+)?(?:other|more)\s+(?:options?|choices?|suggestions?)', 'continuation'),
]

# Context-dependent keywords (need previous context to make sense)
CONTEXT_DEPENDENT_TERMS = [
    'it', 'this', 'that', 'these', 'those', 'them',
    'the one', 'which one', 'both', 'either',
    'cheaper', 'expensive', 'better', 'similar',
    'more options', 'other options', 'alternatives',
]


def detect_follow_up(query: str, memory: ConversationMemory) -> Dict:
    """
    Detect if a query is a follow-up and determine type.
    
    Args:
        query: Current user query
        memory: Conversation memory with context
        
    Returns:
        Dict with:
        - is_follow_up: bool
        - follow_up_type: str (refinement/selection/clarification/comparison/continuation/none)
        - confidence: float
        - contextual_intent: str (what the user likely wants)
    """
    query_lower = query.lower().strip()
    
    # If no context exists, can't be a meaningful follow-up
    if not memory.has_context():
        return {
            'is_follow_up': False,
            'follow_up_type': 'none',
            'confidence': 0.0,
            'contextual_intent': None
        }
    
    # Check explicit follow-up patterns
    for pattern, follow_up_type in FOLLOW_UP_INDICATORS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return {
                'is_follow_up': True,
                'follow_up_type': follow_up_type,
                'confidence': 0.85,
                'contextual_intent': _infer_intent(follow_up_type, query_lower, memory)
            }
    
    # Check for context-dependent terms
    has_dependent_term = any(term in query_lower for term in CONTEXT_DEPENDENT_TERMS)
    
    # Short queries with context are likely follow-ups
    word_count = len(query.split())
    is_short = word_count <= 5
    
    if has_dependent_term and is_short:
        return {
            'is_follow_up': True,
            'follow_up_type': 'contextual',
            'confidence': 0.7,
            'contextual_intent': _infer_intent('contextual', query_lower, memory)
        }
    
    # Very short queries (1-2 words) with context
    if word_count <= 2 and memory.has_context():
        return {
            'is_follow_up': True,
            'follow_up_type': 'implicit',
            'confidence': 0.6,
            'contextual_intent': _infer_intent('implicit', query_lower, memory)
        }
    
    return {
        'is_follow_up': False,
        'follow_up_type': 'none',
        'confidence': 0.0,
        'contextual_intent': None
    }


def _infer_intent(follow_up_type: str, query: str, memory: ConversationMemory) -> str:
    """Infer what the user actually wants based on follow-up type."""
    
    if follow_up_type == 'refinement':
        if 'cheap' in query or 'less' in query:
            return 'filter_lower_price'
        elif 'expensive' in query or 'better' in query:
            return 'filter_higher_price'
        elif 'similar' in query:
            return 'find_similar'
        else:
            return 'refine_results'
    
    elif follow_up_type == 'selection':
        # Extract which item they're asking about
        match = re.search(r'(first|second|third|fourth|fifth|last|1|2|3|4|5)', query)
        if match:
            return f'select_item_{match.group(1)}'
        return 'select_item'
    
    elif follow_up_type == 'clarification':
        # What aspect are they asking about?
        for aspect in ['battery', 'camera', 'display', 'price', 'specs', 'performance']:
            if aspect in query:
                return f'clarify_{aspect}'
        return 'clarify_details'
    
    elif follow_up_type == 'comparison':
        return 'compare_shown_products'
    
    elif follow_up_type == 'continuation':
        return 'show_more_options'
    
    else:
        return 'continue_conversation'


# ════════════════════════════════════════════════════════════
# SLOT MERGING & CONTEXT CARRY-OVER
# ════════════════════════════════════════════════════════════

def merge_slots(previous_slots: Dict, new_slots: Dict, query_type: str) -> Dict:
    """
    Merge previous slots with newly extracted slots.
    
    Rules:
    - New explicit values override previous ones
    - For follow-ups, carry over category and context
    - Budget modifications are applied (e.g., "cheaper" reduces budget)
    """
    merged = previous_slots.copy()
    
    # Override with new explicit values
    for key, value in new_slots.items():
        if value:  # Only if value is not None/empty
            merged[key] = value
    
    return merged


def apply_refinement(memory: ConversationMemory, refinement_type: str) -> Dict:
    """
    Apply a refinement to the current context.
    
    Returns:
        Modified slots based on refinement
    """
    slots = memory.slots.copy()
    
    if refinement_type == 'filter_lower_price':
        # Reduce budget by 20-30%
        if 'budget' in slots:
            slots['budget'] = int(slots['budget'] * 0.75)
    
    elif refinement_type == 'filter_higher_price':
        # Increase budget by 30-50%
        if 'budget' in slots:
            slots['budget'] = int(slots['budget'] * 1.4)
    
    return slots


# ════════════════════════════════════════════════════════════
# PREVIOUS PRODUCTS OPERATIONS
# ════════════════════════════════════════════════════════════

def select_product_by_reference(products: List[Dict], reference: str) -> Optional[Dict]:
    """
    Select a product based on user's reference (first, second, etc.)
    """
    reference_lower = reference.lower()
    
    index_map = {
        'first': 0, '1st': 0, '1': 0, 'one': 0,
        'second': 1, '2nd': 1, '2': 1, 'two': 1,
        'third': 2, '3rd': 2, '3': 2, 'three': 2,
        'fourth': 3, '4th': 3, '4': 3, 'four': 3,
        'fifth': 4, '5th': 4, '5': 4, 'five': 4,
        'last': -1,
    }
    
    for ref, idx in index_map.items():
        if ref in reference_lower:
            try:
                return products[idx]
            except IndexError:
                return None
    
    return None


def filter_products_by_price(products: List[Dict], max_price: int) -> List[Dict]:
    """Filter products to those below max_price."""
    filtered = []
    for p in products:
        price = p.get('price', 0)
        if isinstance(price, str):
            # Extract numeric value from price string
            match = re.search(r'[\d,]+', price.replace(',', ''))
            if match:
                price = int(match.group())
        if price and price <= max_price:
            filtered.append(p)
    return filtered


# ════════════════════════════════════════════════════════════
# STATE INITIALIZATION
# ════════════════════════════════════════════════════════════

def initialize_memory_state(state: Dict) -> Dict:
    """
    Initialize memory-related fields in state if not present.
    
    Call this at the start of each graph run to ensure all fields exist.
    """
    defaults = {
        'conversation_history': [],
        'extracted_slots': {},
        'query_type': '',
        'classification_confidence': 0.0,
        'previous_products': [],
        'current_topic': '',
        'is_follow_up': False,
        'missing_slots': [],
        'follow_up_suggestions': [],
    }
    
    for key, default_value in defaults.items():
        if key not in state or state[key] is None:
            state[key] = default_value
    
    return state


def update_state_after_response(state: Dict, response: str, products: List[Dict]) -> Dict:
    """
    Update state after generating a response.
    
    This should be called at the end of each turn to:
    - Add the response to conversation history
    - Store shown products for next turn
    - Generate follow-up suggestions
    """
    # Add assistant response to history
    history = state.get('conversation_history', [])
    history.append({
        'role': 'assistant',
        'content': response[:500],  # Truncate for memory efficiency
    })
    state['conversation_history'] = history
    
    # Store products shown
    if products:
        state['previous_products'] = products
    
    # Generate follow-up suggestions
    state['follow_up_suggestions'] = _generate_follow_up_suggestions(
        state.get('query_type', ''),
        products
    )
    
    return state


def _generate_follow_up_suggestions(query_type: str, products: List[Dict]) -> List[str]:
    """Generate contextual follow-up suggestions for user."""
    suggestions = []
    
    if products:
        if len(products) >= 2:
            suggestions.append("Compare the top two options?")
        suggestions.append("Show cheaper alternatives?")
        suggestions.append("Tell me more about the first one?")
    
    if query_type == 'best_under':
        suggestions.append("What should I consider when choosing?")
    
    return suggestions[:3]  # Max 3 suggestions
