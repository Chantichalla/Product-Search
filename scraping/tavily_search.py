"""
Tavily Search Module

SIMPLIFIED: Query-type agnostic search - trusts Tavily's AI ranking.
No domain whitelisting - only excludes junk sites.
"""

import os
from typing import Dict, List, Optional, Any
from cache import redis_cache

from config.tavily_config import (
    get_tavily_client,
    credit_tracker,
    get_cache_key,
    TAVILY_CACHE_TTL,
    EXCLUDE_ALWAYS,
)


# ═══════════════════════════════════════════════════════
# CORE SEARCH FUNCTION
# ═══════════════════════════════════════════════════════

def tavily_search(
    query: str,
    include_domains: List[str] = None,
    exclude_domains: List[str] = None,
    max_results: int = 5,
    search_depth: str = "basic",  # "basic" = 1 credit, "advanced" = 2 credits
    include_raw_content: bool = True,  # Get full page content
    include_answer: bool = False,  # Get Tavily's LLM answer
    country: str = "india",  # Boost Indian results
    use_cache: bool = False,
    cache_ttl: int = 3600,
) -> Dict[str, Any]:
    """
    Core Tavily search function with caching and credit tracking.
    
    Returns dict with: 
    - results: list of search results
    - answer: optional LLM-generated answer
    - response_time: API response time
    """
    

    
    client = get_tavily_client()
    if not client:
        return {"error": "Tavily client not initialized", "results": []}
    
    try:
        # Make API call
        response = client.search(
            query=query,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            max_results=max_results,
            search_depth=search_depth,
            include_raw_content=include_raw_content,
            include_answer=include_answer,
        )
        
        # Track credits
        credit_tracker.log_search(search_depth)
        

        
        print(f"[Tavily] ✅ Found {len(response.get('results', []))} results for: {query[:50]}...")
        return response
        
    except Exception as e:
        print(f"[Tavily] ❌ Search error: {e}")
        return {"error": str(e), "results": []}


# ═══════════════════════════════════════════════════════
# UNIFIED SEARCH (Simplified - trusts Tavily's ranking)
# ═══════════════════════════════════════════════════════

def tavily_product_search(
    query: str,
    query_type: str = "unknown",
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Unified product search - trusts Tavily's AI ranking.
    
    SIMPLIFIED: No domain whitelisting. Tavily returns the most 
    relevant results for ANY product query across ALL sources.
    
    Args:
        query: User's search query
        query_type: For cache TTL selection (price_search, comparison, etc.)
        max_results: Number of results (default 10, max 20)
    
    Returns:
        Tavily search results with raw_content
    """
    # Get cache TTL based on query type
    cache_ttl = TAVILY_CACHE_TTL.get(query_type, 3600)
    
    return tavily_search(
        query=query,
        include_domains=None,  # Let Tavily decide
        exclude_domains=EXCLUDE_ALWAYS,  # Only block junk
        max_results=max_results,
        search_depth="basic",
        include_raw_content=True,
        include_answer=True,  # Get Tavily's direct answer
        country="india",
        cache_ttl=cache_ttl,
    )


# Legacy function aliases (for backward compatibility)
def tavily_price_search(product_name: str) -> Dict[str, Any]:
    """Search for product prices. Uses unified search."""
    return tavily_product_search(
        query=f"{product_name} price buy online India",
        query_type="price_search",
    )


def tavily_comparison_search(products: List[str]) -> Dict[str, Any]:
    """Search for product comparisons. Uses unified search."""
    product_str = " vs ".join(products)
    return tavily_product_search(
        query=f"{product_str} comparison specs features",
        query_type="comparison",
    )


def tavily_best_under_search(category: str, budget: int, query: str = None) -> Dict[str, Any]:
    """Search for 'best under X' recommendations. Uses unified search."""
    budget_str = f"{budget // 1000}k" if budget >= 1000 else str(budget)
    search_query = query or f"best {category} under {budget_str} India recommendations"
    return tavily_product_search(
        query=search_query,
        query_type="best_under",
    )


def tavily_advice_search(category: str, use_case: str = None) -> Dict[str, Any]:
    """Search for buying guides. Uses unified search."""
    query = f"how to choose {category} buying guide tips"
    if use_case:
        query += f" for {use_case}"
    return tavily_product_search(
        query=query,
        query_type="product_advice",
    )


def tavily_feature_search(product: str, feature: str) -> Dict[str, Any]:
    """Search for feature details. Uses unified search."""
    return tavily_product_search(
        query=f"{product} {feature} specifications details",
        query_type="feature_query",
    )


def tavily_unknown_search(query: str) -> Dict[str, Any]:
    """Fallback search for unknown queries. Uses unified search."""
    results = tavily_product_search(query=query, query_type="unknown")
    results["clarification_needed"] = True
    results["suggestions"] = [
        "Are you looking for product prices?",
        "Do you want to compare products?",
        "Are you looking for recommendations?",
    ]
    return results


# ═══════════════════════════════════════════════════════
# SMART ROUTER (Routes query to appropriate search)
# ═══════════════════════════════════════════════════════

def tavily_smart_search(
    query: str,
    query_type: str,
    extracted_slots: Dict[str, Any] = None,
    previous_products: List[Dict] = None,
) -> Dict[str, Any]:
    """
    Route to appropriate Tavily search based on query type.
    
    SIMPLIFIED: All searches now use unified tavily_product_search
    which trusts Tavily's AI ranking without domain restrictions.
    """
    if extracted_slots is None:
        extracted_slots = {}
    
    category = extracted_slots.get("category", "product")
    budget = extracted_slots.get("budget")
    products = extracted_slots.get("products", [])
    use_case = extracted_slots.get("use_case")
    feature = extracted_slots.get("feature")
    
    # Handle conversational queries (no API call)
    if query_type == "conversational":
        return {"answer": handle_conversational(query), "results": []}
    
    # Handle follow-ups with context
    if query_type == "follow_up":
        return handle_follow_up(query, extracted_slots, previous_products)
    
    # Build optimized query based on type
    if query_type == "price_search":
        product = products[0] if products else query
        search_query = f"{product} price buy online India"
    
    elif query_type == "comparison":
        if len(products) >= 2:
            search_query = f"{' vs '.join(products)} comparison specs features"
        else:
            search_query = f"{query} alternatives comparison"
    
    elif query_type == "best_under":
        if budget:
            budget_str = f"{budget // 1000}k" if budget >= 1000 else str(budget)
            search_query = f"best {category} under {budget_str} India recommendations"
        else:
            search_query = f"best {category} India recommendations"
    
    elif query_type == "product_advice":
        search_query = f"how to choose {category} buying guide tips"
        if use_case:
            search_query += f" for {use_case}"
    
    elif query_type == "feature_query":
        product = products[0] if products else query
        if feature:
            search_query = f"{product} {feature} specifications details"
        else:
            search_query = f"{product} specifications features"
    
    else:  # unknown
        search_query = query
    
    # All queries go through unified search
    return tavily_product_search(
        query=search_query,
        query_type=query_type,
    )


# ═══════════════════════════════════════════════════════
# FOLLOW-UP HANDLING (Credit optimization)
# ═══════════════════════════════════════════════════════

def handle_follow_up(
    query: str,
    extracted_slots: Dict[str, Any],
    previous_products: List[Dict] = None,
) -> Dict[str, Any]:
    """
    Handle follow-up queries with context.
    
    Credit optimization:
    - "cheaper ones" → Filter in memory (0 credits)
    - Brand-specific → New search (1 credit)
    - Generic → Combined search (1 credit)
    """
    query_lower = query.lower()
    
    # Price filtering (no API call)
    if "cheaper" in query_lower and previous_products:
        filtered = filter_by_price(previous_products, direction="lower")
        return {"results": [], "filtered_products": filtered, "from_memory": True}
    
    if "expensive" in query_lower and previous_products:
        filtered = filter_by_price(previous_products, direction="higher")
        return {"results": [], "filtered_products": filtered, "from_memory": True}
    
    # Brand-specific follow-up
    brands = ["samsung", "apple", "oneplus", "xiaomi", "realme", "oppo", "vivo", 
              "motorola", "nothing", "asus", "acer", "hp", "dell", "lenovo"]
    for brand in brands:
        if brand in query_lower:
            category = extracted_slots.get("category", "phone")
            budget = extracted_slots.get("budget")
            if budget:
                budget_str = f"{budget // 1000}k" if budget >= 1000 else str(budget)
                search_query = f"best {brand} {category} under {budget_str} India"
            else:
                search_query = f"best {brand} {category} India"
            return tavily_product_search(query=search_query, query_type="follow_up")
    
    # Generic follow-up - combine with original context
    original_category = extracted_slots.get("category", "")
    original_budget = extracted_slots.get("budget", "")
    
    combined_query = f"{original_category} {query}"
    if original_budget:
        combined_query += f" under {original_budget}"
    
    return tavily_product_search(query=combined_query, query_type="follow_up")


def filter_by_price(products: List[Dict], direction: str = "lower") -> List[Dict]:
    """Filter products by price (in memory, no API call)."""
    if not products:
        return []
    
    # Get median price
    prices = [p.get("price", 0) for p in products if p.get("price")]
    if not prices:
        return products
    
    median_price = sorted(prices)[len(prices) // 2]
    
    if direction == "lower":
        return [p for p in products if p.get("price", float('inf')) < median_price]
    else:
        return [p for p in products if p.get("price", 0) > median_price]


def handle_conversational(message: str) -> str:
    """Handle conversational messages (no API call)."""
    greetings = {
        "hi": "Hello! 👋 How can I help you find the perfect product today?",
        "hello": "Hi there! What are you shopping for?",
        "hey": "Hey! Ready to help you find the best deals. What are you looking for?",
        "thanks": "You're welcome! Need help with anything else?",
        "thank you": "You're welcome! Happy to help. Any other questions?",
        "bye": "Goodbye! Happy shopping! 🛒",
        "ok": "Great! Let me know if you need anything else.",
        "okay": "Perfect! What else can I help you with?",
    }
    
    msg_lower = message.lower().strip()
    
    for key, response in greetings.items():
        if key in msg_lower:
            return response
    
    return "I'm here to help you find products. What are you looking for?"


# ═══════════════════════════════════════════════════════
# EXTRACT FUNCTION (for when you need full page content)
# ═══════════════════════════════════════════════════════

def tavily_extract(urls: List[str]) -> Dict[str, Any]:
    """
    Extract full content from URLs.
    
    Cost: 1 credit per 5 URLs
    Use only when include_raw_content wasn't enough.
    """
    client = get_tavily_client()
    if not client:
        return {"error": "Tavily client not initialized", "results": []}
    
    try:
        response = client.extract(urls=urls[:5])  # Max 5 URLs
        credit_tracker.log_extract(len(urls[:5]))
        return response
    except Exception as e:
        print(f"[Tavily] ❌ Extract error: {e}")
        return {"error": str(e), "results": []}
