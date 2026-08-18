"""
Multi-Agent Runner (V3.1 - Tavily Integration)
Entry point for the e-commerce multi-agent orchestrator.

Flow: Query → Planner → Tavily Search → Filter → Advisor → Response
"""
import sys
import os
import time
from typing import List, Dict, Optional

# Add project root to path for imports when running directly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agent.single_agent.graph import app

# Session state for maintaining context across queries
session_state = {
    "conversation_history": [],
    "previous_products": [],
    "extracted_slots": {},
}


def ask_agent(query: str, session_id: str = None, history: Optional[List[Dict]] = None,
              provided_url: str = "", provided_image_b64: str = "") -> str:
    """
    Run the multi-agent workflow for a query.
    
    V3.1: Uses Tavily Search API with simplified pipeline.
    
    Args:
        query: User's product search query
        session_id: Optional session ID for conversation continuity
        history: Optional list of past messages [{"role": "user", "content": "..."}]
        
    Returns:
        Final answer string
    """
    global session_state
    
    if not session_id:
        session_id = f"session_{int(time.time())}"
    
    config = {"configurable": {"thread_id": session_id}}
    
    # Use provided history if available, else fall back to session state
    conversation_history = history if history is not None else session_state.get("conversation_history", [])
    
    # Initialize state with memory fields for follow-up queries
    initial_state = {
        "query": query,
        # Omnibox inputs
        "provided_url": provided_url or "",
        "provided_image_b64": provided_image_b64 or "",
        "input_type": "text",  # Will be set by input_processor_node
        "product_thumbnail_url": "",
        # Memory fields (persist across queries in session)
        "conversation_history": conversation_history,
        "previous_products": session_state.get("previous_products", []),
        "extracted_slots": session_state.get("extracted_slots", {}),
        # Processing fields
        "cache_hit": False,
        "cached_products": [],
        "candidates": [],
        "verified_products": [],
        "raw_search_results": [],
        # Output fields
        "recommendation": "",
        "final_answer": "",
        "error": "",
        "step_count": 0,
    }
    
    try:
        result = app.invoke(initial_state, config=config)
        
        # Update session state for follow-up queries
        if result.get("previous_products"):
            session_state["previous_products"] = result["previous_products"]
        if result.get("extracted_slots"):
            session_state["extracted_slots"] = result["extracted_slots"]
        
        # Add to conversation history (Internal State Update)
        # Note: If history was provided, we are essentially maintaining a parallel state here if run locally.
        # But for API usage, this session_state is ignored on next request in favor of DB history.
        session_state["conversation_history"].append({
            "role": "user", "content": query
        })
        session_state["conversation_history"].append({
            "role": "assistant", "content": result.get("final_answer", "")[:500]
        })
        
        return result.get("final_answer", "No answer generated")
    except Exception as e:
        return f"❌ Error: {str(e)}"


# Node-to-label mapping for UI progress events
NODE_LABELS = {
    "memory_init": "Initializing session...",
    "input_processor": "Processing your input...",
    "query_rewriter": "Understanding your query...",
    "check_cache": "Checking cached results...",
    "smart_planner": "Planning search strategy...",
    "search": "Searching across sources...",
    "follow_up_handler": "Processing follow-up...",
    "advisor": "Analyzing and comparing products...",
    "error_handler": "Handling error...",
    "fallback_handler": "Generating response...",
}


def ask_agent_streaming(
    query: str,
    session_id: str = None,
    history: Optional[List[Dict]] = None,
    provided_url: str = "",
    provided_image_b64: str = "",
):
    """
    Streaming version of ask_agent.
    
    Yields dicts with progress events as each LangGraph node completes:
        {"type": "progress", "node": "search", "label": "Searching across sources...", "done": False}
        {"type": "progress", "node": "advisor", "label": "Analyzing...", "done": False}
        {"type": "result", "answer": "...", "thumbnail_url": "...", "done": True}
    """
    global session_state
    
    if not session_id:
        session_id = f"session_{int(time.time())}"
    
    config = {"configurable": {"thread_id": session_id}}
    
    conversation_history = history if history is not None else session_state.get("conversation_history", [])
    
    initial_state = {
        "query": query,
        "provided_url": provided_url or "",
        "provided_image_b64": provided_image_b64 or "",
        "input_type": "text",
        "product_thumbnail_url": "",
        "conversation_history": conversation_history,
        "previous_products": session_state.get("previous_products", []),
        "extracted_slots": session_state.get("extracted_slots", {}),
        "cache_hit": False,
        "cached_products": [],
        "candidates": [],
        "verified_products": [],
        "raw_search_results": [],
        "recommendation": "",
        "final_answer": "",
        "error": "",
        "step_count": 0,
    }
    
    try:
        # Use LangGraph's stream() to get per-node updates
        for event in app.stream(initial_state, config=config, stream_mode="updates"):
            # event is a dict like {"node_name": {state_updates}}
            for node_name, updates in event.items():
                label = NODE_LABELS.get(node_name, f"Processing ({node_name})...")
                
                # Yield progress event
                yield {
                    "type": "progress",
                    "node": node_name,
                    "label": label,
                    "done": False,
                }
                
                # If this node produced a final_answer, we're done
                if updates.get("final_answer"):
                    # Update session state
                    if updates.get("previous_products"):
                        session_state["previous_products"] = updates["previous_products"]
                    if updates.get("extracted_slots"):
                        session_state["extracted_slots"] = updates["extracted_slots"]
                    
                    session_state["conversation_history"].append({"role": "user", "content": query})
                    session_state["conversation_history"].append({
                        "role": "assistant", "content": updates["final_answer"][:500]
                    })
                    
                    yield {
                        "type": "result",
                        "answer": updates["final_answer"],
                        "thumbnail_url": updates.get("product_thumbnail_url", ""),
                        "done": True,
                    }
                    return
        
        # If stream ended without final_answer
        yield {"type": "result", "answer": "No answer generated", "thumbnail_url": "", "done": True}
        
    except Exception as e:
        yield {"type": "error", "answer": f"❌ Error: {str(e)}", "done": True}


def reset_session():
    """Clear session state for a fresh start."""
    global session_state
    session_state = {
        "conversation_history": [],
        "previous_products": [],
        "extracted_slots": {},
    }
    print("Session reset. Starting fresh conversation.")


if __name__ == "__main__":
    print("=" * 50)
    print("E-COMMERCE MULTI-AGENT (V3.1 - Tavily)")
    print("=" * 50)
    print("Type your query, 'reset' to clear context, or 'quit' to exit\n")
    
    session_id = f"session_{int(time.time())}"
    
    while True:
        try:
            query = input("You: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if query.lower() == 'reset':
                reset_session()
                session_id = f"session_{int(time.time())}"
                continue
            
            if not query:
                continue
            
            print("\nProcessing...")
            start = time.time()
            response = ask_agent(query, session_id)
            elapsed = time.time() - start
            
            print(f"\n[{elapsed:.1f}s] Agent:")
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}\n")

