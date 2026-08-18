"""
Integration Test: Tavily Search API
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


def test_tavily_connection():
    """Test basic Tavily API connection."""
    from config.tavily_config import get_tavily_client
    
    client = get_tavily_client()
    if not client:
        print("❌ Failed to initialize Tavily client. Check TAVILY_API_KEY in .env.")
        return False
    
    print("✅ Tavily client initialized successfully")
    return True


def test_price_search():
    """Test price search for a product."""
    from scraping import tavily_price_search
    
    print("\n🔍 Testing price_search: 'iPhone 15 price'")
    results = tavily_price_search("iPhone 15")
    
    if "error" in results and results["error"]:
        print(f"❌ Error: {results['error']}")
        return False
    
    result_count = len(results.get("results", []))
    print(f"✅ Found {result_count} results")
    
    if results.get("results"):
        first = results["results"][0]
        print(f"   📍 {first.get('title', 'No title')[:60]}...")
        print(f"   🔗 {first.get('url', 'No URL')[:60]}...")
    
    return True


def test_best_under_search():
    """Test best_under search."""
    from scraping import tavily_best_under_search
    
    print("\n🔍 Testing best_under: 'best phones under 30k'")
    results = tavily_best_under_search("phones", 30000)
    
    if "error" in results and results["error"]:
        print(f"❌ Error: {results['error']}")
        return False
    
    result_count = len(results.get("results", []))
    print(f"✅ Found {result_count} results")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("TAVILY API INTEGRATION TESTS")
    print("=" * 60)
    
    if test_tavily_connection():
        test_price_search()
        test_best_under_search()
        
        from config.tavily_config import print_credit_summary
        print_credit_summary()
