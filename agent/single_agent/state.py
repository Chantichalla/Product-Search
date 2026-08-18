from typing import TypedDict, Annotated, Optional
import operator


class AgentState(TypedDict):
    """
    Agent State for Product-AI v2.0
    
    Layers:
    1. Memory Layer: Conversation history, slots, context (Week 1)
    2. Processing Layer: Search, filter, verify (existing)
    3. TSI Layer: Scores, consensus, confidence (Week 2-3)
    """
    
    # ════════════════════════════════════════════════════════════
    # INPUT (Omnibox - supports Text, URL, and Image)
    # ════════════════════════════════════════════════════════════
    query: str
    
    # Omnibox: URL or Image provided alongside text
    provided_url: str           # URL pasted by user (e.g., Amazon product link)
    provided_image_b64: str     # Base64-encoded image uploaded by user
    input_type: str             # "text" | "url" | "image" | "text+url" | "text+image"
    
    # Visual confirmation: product thumbnail for the user
    product_thumbnail_url: str  # Canonical product image URL for UI display
    
    # ════════════════════════════════════════════════════════════
    # MEMORY LAYER (Week 1 - Conversation Memory)
    # ════════════════════════════════════════════════════════════
    
    # Conversation history for multi-turn
    conversation_history: list  # [{role: "user/assistant", content: "..."}]
    
    # Extracted information from conversation
    extracted_slots: dict  # {budget: 45000, category: "phone", use_case: "gaming"}
    
    # Current query classification
    query_type: str  # price_search|comparison|best_under|product_advice|feature_query|follow_up|conversational|unknown
    classification_confidence: float  # 0.0 - 1.0
    
    # Follow-up context
    previous_products: list  # Products from previous turn
    current_topic: str  # What product/category we're discussing
    is_follow_up: bool  # Is this a continuation of previous query?
    
    # Missing information detection
    missing_slots: list  # ["budget", "use_case"] - info we need from user
    
    # ════════════════════════════════════════════════════════════
    # PROCESSING LAYER (Existing - Search & Filter)
    # ════════════════════════════════════════════════════════════
    
    # Cache check
    cache_hit: bool
    cached_products: list

    # Query Planner output (Phase 1)
    search_queries: dict  # {"price": [...], "spec": [...]} - Categorized search queries

    # Parallel Search output (Phase 2)
    raw_search_results: list  # Raw results from multi-engine search

    # Variant Filter output (Phase 3)
    filtered_urls: list  # Deduplicated, filtered URLs
    
    # Legacy: Discovery output (kept for compatibility)
    candidates: list

    # Verification output (Phase 4)
    verified_products: list  # Products from current query only (no accumulation)
    raw_markdown_sources: dict  # {url: markdown} - For advisor fallback analysis
    
    # ════════════════════════════════════════════════════════════
    # SPEC-FIRST DISCOVERY (for best_under queries)
    # ════════════════════════════════════════════════════════════
    
    discovered_products: list  # Products discovered from spec sites (Stage 1)
    product_prices: dict  # {product_name: {amazon: price, flipkart: price}} (Stage 2)
    
    # ════════════════════════════════════════════════════════════
    # TSI LAYER (Week 2-3 - Transparency Features)
    # ════════════════════════════════════════════════════════════
    
    # Value scoring breakdown
    score_breakdown: dict  # {product_id: {spec: 40, review: 30, value: 30, total: 85}}
    
    # Source consensus tracking
    source_consensus: dict  # {product_id: {total_sources: 6, agreeing: 5, confidence: "high"}}
    
    # Confidence level for recommendations
    confidence_level: str  # "high" | "medium" | "low"
    
    # Honest limitations / warnings
    limitations: list  # ["15 reviews mention heating", "Limited stock available"]
    
    # ════════════════════════════════════════════════════════════
    # OUTPUT
    # ════════════════════════════════════════════════════════════
    
    # Advisor output (Phase 5)
    recommendation: str
    final_answer: str
    
    # Follow-up suggestions for user
    follow_up_suggestions: list  # ["Want cheaper options?", "Compare with Samsung?"]

    # ════════════════════════════════════════════════════════════
    # ERROR HANDLING
    # ════════════════════════════════════════════════════════════
    error: str
    step_count: int


# ════════════════════════════════════════════════════════════
# QUERY TYPE DEFINITIONS
# ════════════════════════════════════════════════════════════

QUERY_TYPES = {
    "price_search": "Single product price lookup (e.g., 'iPhone 15 price')",
    "comparison": "Compare two or more products (e.g., 'iPhone vs Samsung')",
    "best_under": "Best products under budget (e.g., 'Best phones under 45k')",
    "product_advice": "General shopping advice (e.g., 'What to look for in a phone?')",
    "feature_query": "Specific feature question (e.g., 'Does iPhone 15 have wireless charging?')",
    "follow_up": "Continuation of previous query (e.g., 'Show cheaper ones')",
    "conversational": "Greetings, thanks, chitchat",
    "unknown": "Cannot classify - use fallback"
}


# ════════════════════════════════════════════════════════════
# SLOT DEFINITIONS (for extraction)
# ════════════════════════════════════════════════════════════

REQUIRED_SLOTS = {
    "price_search": ["product"],
    "comparison": ["product_a", "product_b"],
    "best_under": ["category", "budget"],
    "product_advice": ["category"],
    "feature_query": ["product", "feature"],
    "follow_up": [],  # Uses context
    "conversational": [],
    "unknown": [],
}