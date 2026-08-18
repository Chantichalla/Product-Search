import sys
import os
import asyncio

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.single_agent.nodes import smart_planner_node, search_node

def run_full_test(query: str, provided_url: str = ""):
    print("="*60)
    print(f"🧪 TESTING AUTOMATIC ROUTING (PLANNER -> SEARCH)")
    print(f"Query: '{query}'")
    print(f"Provided URL: '{provided_url}'")
    print("="*60)
    
    # Initial state
    state = {
        "query": query,
        "provided_url": provided_url,
        "conversation_history": [],
        "previous_products": [],
        "step_count": 0
    }
    
    # 1. Run Planner Node
    print("\n[Executing smart_planner_node...]\n")
    try:
        planner_result = smart_planner_node(state)
        state.update(planner_result)
        print(f"\n🧠 Planner query_type: '{state.get('query_type')}'")
        print(f"🧩 Extracted Slots: {state.get('extracted_slots')}")
    except Exception as e:
        print(f"\n❌ Error executing planner node: {e}")
        return

    # 2. Run Search Node
    print("\n" + "="*60)
    print("[Executing search_node...]\n")
    try:
        result_state = search_node(state)
        state.update(result_state)
    except Exception as e:
        print(f"\n❌ Error executing search node: {e}")
        return

    results = state.get("raw_search_results", [])
    print(f"\n✅ Total Sources Found: {len(results)}")
    for i, res in enumerate(results[:3]):
        print(f"   [{i+1}] {res.get('title', 'No title')[:60]} ({res.get('url', '')[:45]}...)")


if __name__ == "__main__":
    test_query = "Sony WH-1000XM5 price"
    run_full_test(query=test_query)

