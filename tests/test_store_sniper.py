"""
test_store_sniper.py
Isolated Pipeline Test for Option B (Targeted URL Discovery + Extraction)
"""

import sys
import os
import asyncio
import json
from bs4 import BeautifulSoup

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.concurrency import ddg_search_concurrent, scrape_urls_concurrent_v2

# Define target stores
TARGET_STORES = {
    "amazon": "amazon.in/dp",       # Only look for product pages
    "flipkart": "flipkart.com/p",    # Only look for product pages
    "croma": "croma.com",
}

async def discover_store_urls(product_name: str) -> dict:
    """Step 1: Find direct product URLs using search engines."""
    print(f"\n🔍 [Phase 1: Discovery] Hunting for '{product_name}'...")
    queries = [f"site:{domain} {product_name}" for domain in TARGET_STORES.values()]
    
    # We use Google/Bing via DDGS for high quality site: searches
    search_results = await ddg_search_concurrent(queries, max_results=3, backend="auto")
    
    discovered_urls = {}
    for i, (store, domain) in enumerate(TARGET_STORES.items()):
        query = queries[i]
        results = search_results.get(query, [])
        for r in results:
            url = r.get("href", "")
            
            # 1. Must be the actual store domain (filters out bing ad clicks)
            domain_base = domain.split('/')[0]
            if domain_base not in url:
                continue
                
            # 2. Filter out accessories and bad matches
            bad_keywords = ["cover", "case", "display", "refurbished", "renewed", "adapter", "cable", "screen-guard"]
            if any(kw in url.lower() for kw in bad_keywords):
                continue
                
            # 3. Basic validation
            if "search" not in url.lower() and url.startswith("http"):
                discovered_urls[store] = url
                print(f"  ✅ {store.upper()} Found: {url}")
                break
    return discovered_urls

def fast_extract_price(html: str) -> str:
    """Step 2a: INSTANT extraction via JSON-LD schema (Zero LLM cost)."""
    if not html: return None
    soup = BeautifulSoup(html, 'html.parser')
    
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Product' and 'offers' in item:
                        offers = item['offers']
                        if isinstance(offers, dict) and 'price' in offers:
                            return str(offers['price'])
                        elif isinstance(offers, list) and len(offers) > 0:
                            return str(offers[0].get('price'))
            elif isinstance(data, dict):
                if data.get('@type') == 'Product' and 'offers' in data:
                     offers = data['offers']
                     if isinstance(offers, dict) and 'price' in offers:
                         return str(offers['price'])
        except:
            continue
    
    # Optional fallback to OpenGraph meta tags
    meta_price = soup.find('meta', property='product:price:amount')
    if meta_price:
        return meta_price.get('content')
        
    return None

def fallback_llm_extract(markdown: str, store: str, product_name: str) -> str:
    """Step 2b: Use Local/Cloud LLM to extract JSON from markdown."""
    from config.llm_config import groq_powerful_llm
    try:
        llm = groq_powerful_llm
        print(f"  🤖 Querying Groq Powerful model for {store}...")
        
        truncated_markdown = markdown[:15000]
        
        # --- DEBUG DUMP ---
        # Save the exact markdown we are sending to the LLM so we can inspect it
        debug_filename = f"debug_markdown_{store}.md"
        with open(debug_filename, "w", encoding="utf-8") as f:
            f.write(truncated_markdown)
        print(f"  [Debug] Saved markdown to {debug_filename} for inspection.")
        # ------------------
        
        prompt = f"""Extract the current price of "{product_name}" from this markdown.
        Respond ONLY with a valid JSON object holding a single key "price" containing the numeric price.
        If not found, set "price" to null.
        Example: {{"price": 69900}}
        
        MARKDOWN:
        {truncated_markdown}  # 15k chars is well within Groq's 4k/8k context limit depending on the token ratio
        """
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        return content.strip()
    except Exception as e:
         return f"LLM Error: {e}"

async def main():
    product = "iPhone 15 128GB"
    
    # PHASE 1: Discovery
    urls_to_scrape = await discover_store_urls(product)
    
    if not urls_to_scrape:
        print("❌ Could not find any product URLs.")
        return

    # PHASE 2: Extraction
    print(f"\n🌐 [Phase 2: Extraction] Scraping {len(urls_to_scrape)} URLs with Crawl4AI...")
    url_list = list(urls_to_scrape.values())
    
    # We use v2 which returns raw HTML
    scrape_data = await scrape_urls_concurrent_v2(url_list)
    
    print("\n📊 [RESULTS]")
    for store, url in urls_to_scrape.items():
        data = scrape_data.get(url, {})
        if not data.get("success"):
            print(f"[{store.upper()}] ❌ Scrape Failed: {data.get('error')}")
            continue
            
        # Try Fast Path first
        fast_price = fast_extract_price(data.get("html", ""))
        if fast_price:
            print(f"[{store.upper()}] ⚡ FAST EXTRACT (JSON-LD): ₹{fast_price}")
        else:
             print(f"[{store.upper()}] ⚠️ Fast Extract Failed. Falling back to LLM...")
             fit_md = data.get("fit_markdown", "")
             llm_result = fallback_llm_extract(fit_md, store, product)
             print(f"[{store.upper()}] 🤖 LLM EXTRACT: {llm_result}")

if __name__ == "__main__":
    asyncio.run(main())
