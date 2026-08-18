from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes import (
    check_cache_node,
    smart_planner_node,
    search_node,
    adviser_node,
    error_handler_node,
    fallback_handler_node,
    query_rewriter_node,
)
from .memory import initialize_memory_state


# ════════════════════════════════════════════════════════════
# ROUTING FUNCTIONS
# ════════════════════════════════════════════════════════════

def route_after_cache(state: AgentState) -> str:
    """Route based on cache hit/miss"""
    if state.get("cache_hit"):
        print("[Router] Cache HIT -> advisor")
        return "advisor"
    print(" [Router] Cache MISS -> smart_planner")
    return "smart_planner"


def route_after_planner(state: AgentState) -> str:
    """
    Route based on query type from smart planner.
    
    Routes:
    - unknown/conversational -> fallback_handler (no search needed)
    - follow_up (with previous products) -> follow_up_handler
    - product_advice (generic, no product) -> advisor (direct LLM)
    - others -> parallel_search (need to search)
    """
    query_type = state.get("query_type", "")
    search_queries = state.get("search_queries", {})
    # Handle both dict (new) and list (legacy) formats
    if isinstance(search_queries, dict):
        total_queries = len(search_queries.get('price', [])) + len(search_queries.get('spec', []))
        has_queries = total_queries > 0
    else:
        total_queries = len(search_queries) if search_queries else 0
        has_queries = bool(search_queries)
    previous_products = state.get("previous_products", [])
    is_follow_up = state.get("is_follow_up", False)
    
    # Handle queries that don't need search
    if query_type in ['unknown', 'conversational']:
        print(f"[Router] {query_type} -> fallback_handler")
        return "fallback_handler"
    
    # Handle follow-ups - ONLY if previous products exist
    if is_follow_up and previous_products:
        print(f"[Router] follow_up -> follow_up_handler ({len(previous_products)} prev products)")
        return "follow_up_handler"
    
    # Product advice with specific product -> needs search for real data
    # Product advice without product (generic "how to choose") -> direct to advisor
    if query_type == 'product_advice':
        slots = state.get("extracted_slots", {})
        if not slots.get("product") and not has_queries:
            # Generic advice like "what to look for in a laptop" - no search needed
            print("[Router] product_advice (generic) -> advisor")
            return "advisor"
        # Specific product advice needs data
        if has_queries:
            print(f"[Router] product_advice (specific) -> search")
            return "search"
    
    # All other query types need search
    if has_queries:
        print(f"[Router] {query_type} -> search ({total_queries} queries)")
        return "search"
    
    # No queries generated, go to error
    print("[Router] No queries -> error_handler")
    return "error_handler"


def route_after_search(state: AgentState) -> str:
    """
    Route after search - go directly to advisor.
    """
    raw_results = state.get("raw_search_results", [])
    verified = state.get("verified_products", [])
    final_answer = state.get("final_answer")
    
    # If search already produced a final answer (conversational), go to end
    if final_answer:
        print(f"[Router] Search produced final answer -> advisor")
        return "advisor"
    
    if raw_results or verified:
        print(f"[Router] {len(raw_results or verified)} results -> advisor")
        return "advisor"
    
    print("[Router] No results -> error_handler")
    return "error_handler"



# ════════════════════════════════════════════════════════════
# FOLLOW-UP HANDLER NODE
# ════════════════════════════════════════════════════════════

def follow_up_handler_node(state: AgentState) -> dict:
    """
    Handle follow-up queries using previous context.
    
    This node processes refinement requests like:
    - "Show cheaper ones" -> Filter previous products by lower price
    - "Tell me more about the first one" -> Get details on specific product
    - "Compare them" -> Compare previously shown products
    """
    from .memory import (
        apply_refinement,
        select_product_by_reference,
        filter_products_by_price
    )
    
    print("[NODE] follow_up_handler")
    query = state["query"].lower()
    previous_products = state.get("previous_products", [])
    slots = state.get("extracted_slots", {})
    
    if not previous_products:
        # No context available, treat as new query
        return {
            "error": "No previous products to reference. Please start a new search.",
            "step_count": state.get("step_count", 0) + 1
        }
    
    # Handle "cheaper" refinement
    if any(word in query for word in ['cheaper', 'less expensive', 'budget']):
        current_budget = slots.get('budget', 0)
        if current_budget:
            new_budget = int(current_budget * 0.75)
            filtered = filter_products_by_price(previous_products, new_budget)
            if filtered:
                return {
                    "verified_products": filtered,
                    "extracted_slots": {**slots, 'budget': new_budget},
                    "step_count": state.get("step_count", 0) + 1
                }
    
    # Handle selection ("first one", "tell me about #2")
    if any(word in query for word in ['first', 'second', 'third', 'last', '1', '2', '3']):
        selected = select_product_by_reference(previous_products, query)
        if selected:
            return {
                "verified_products": [selected],
                "current_topic": selected.get('name', 'Selected product'),
                "step_count": state.get("step_count", 0) + 1
            }
    
    # Handle "more options"
    if any(word in query for word in ['more', 'other', 'alternatives']):
        # Return to search with same parameters
        return {
            "is_follow_up": False,  # Treat as new search
            "step_count": state.get("step_count", 0) + 1
        }
    
    # Default: return previous products for re-display
    return {
        "verified_products": previous_products,
        "step_count": state.get("step_count", 0) + 1
    }


# ════════════════════════════════════════════════════════════
# MEMORY INITIALIZATION NODE
# ════════════════════════════════════════════════════════════

def memory_init_node(state: AgentState) -> dict:
    """
    Initialize memory fields at the start of each run.
    Also adds user message to conversation history.
    """
    print("[NODE] memory_init")
    
    # Initialize missing fields
    updated = initialize_memory_state(dict(state))
    
    # Add user query to conversation history
    history = updated.get('conversation_history', [])
    history.append({
        'role': 'user',
        'content': state['query']
    })
    
    return {
        'conversation_history': history,
        'extracted_slots': updated.get('extracted_slots', {}),
        'previous_products': updated.get('previous_products', []),
        'step_count': state.get("step_count", 0) + 1
    }


# ════════════════════════════════════════════════════════════
# BUILD THE GRAPH
# ════════════════════════════════════════════════════════════

workflow = StateGraph(AgentState)

# Add nodes (V6 - removed input_processor, query-specific routing in search_node)
workflow.add_node("memory_init", memory_init_node)
workflow.add_node("query_rewriter", query_rewriter_node)
workflow.add_node("check_cache", check_cache_node)
workflow.add_node("smart_planner", smart_planner_node)
workflow.add_node("search", search_node)
workflow.add_node("advisor", adviser_node)
workflow.add_node("error_handler", error_handler_node)
workflow.add_node("fallback_handler", fallback_handler_node)
workflow.add_node("follow_up_handler", follow_up_handler_node)

# ════════════════════════════════════════════════════════════
# EDGES (V5 SIMPLIFIED - search goes directly to advisor)
# ════════════════════════════════════════════════════════════

# Start -> Memory Init -> Query Rewriter -> Cache Check
workflow.add_edge(START, "memory_init")
workflow.add_edge("memory_init", "query_rewriter")
workflow.add_edge("query_rewriter", "check_cache")

# Cache hit/miss routing
workflow.add_conditional_edges(
    "check_cache",
    route_after_cache,
    {"advisor": "advisor", "smart_planner": "smart_planner"}
)

# Smart planner routes based on query type
workflow.add_conditional_edges(
    "smart_planner",
    route_after_planner,
    {
        "search": "search",
        "fallback_handler": "fallback_handler",
        "follow_up_handler": "follow_up_handler",
        "advisor": "advisor",
        "error_handler": "error_handler"
    }
)

# Search -> advisor directly (V5: removed variant_filter and extract_products)
workflow.add_conditional_edges(
    "search",
    route_after_search,
    {"advisor": "advisor", "error_handler": "error_handler"}
)

# Follow-up handler goes to advisor
workflow.add_edge("follow_up_handler", "advisor")

# End states
workflow.add_edge("advisor", END)
workflow.add_edge("error_handler", END)
workflow.add_edge("fallback_handler", END)

# ════════════════════════════════════════════════════════════
# COMPILE
# ════════════════════════════════════════════════════════════

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
