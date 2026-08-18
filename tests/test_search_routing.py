"""
Test: Search Node Routing Verification
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.single_agent.nodes import search_node


def run_routing_test(query: str, query_type: str, provided_url: str = ""):
    print("=" * 60)
    print(f"🧪 TESTING SEARCH NODE ROUTING")
    print(f"Query        : '{query}'")
    print(f"Query Type   : '{query_type}'")
    print(f"Provided URL : '{provided_url}'")
    print("=" * 60)
    
    state = {
        "query": query,
        "query_type": query_type,
        "extracted_slots": {"product": query} if query_type == "price_search" else {},
        "previous_products": [],
        "provided_url": provided_url,
        "step_count": 0
    }
    
    try:
        result_state = search_node(state)
        results = result_state.get("raw_search_results", [])
        print(f"\n✅ Total Sources Found: {len(results)}")
        for i, res in enumerate(results[:3]):
            print(f"   [{i+1}] {res.get('title', 'No Title')[:60]} -> {res.get('url', '')[:50]}...")
        return True
    except Exception as e:
        print(f"\n❌ Error executing search_node: {e}")
        return False


if __name__ == "__main__":
    # Run sample routing tests
    print("Running automated routing check:")
    run_routing_test("Sony WH-1000XM5 price", "price_search")
