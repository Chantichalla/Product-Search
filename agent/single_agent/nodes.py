from agent.single_agent.state import AgentState
from cache import redis_cache
from agent.single_agent.semantic_cache import semantic_cache
from agent.single_agent.deep_memory import deep_memory
import time
import asyncio
import re
from db.session import get_session
from db.models import Product
from scraping import ddg_search_concurrent, search_with_fallback
from sqlmodel import select
from scraping import scrape_urls_concurrent
from extract import extract_product_from_markdown
from network import extract_domain
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
load_dotenv()

# LLM for reasoning (using centralized config)
def get_advisor():
    from config.llm_config import get_google_advisor
    return get_google_advisor()




# ---------------------------------------------------------
# QUERY REWRITER NODE (The "Context Resolution" Layer)
# ---------------------------------------------------------
def query_rewriter_node(state: AgentState) -> dict:
    """
    Rewrites user query to specific standalone query using Deep Memory context.
    """
    print("[NODE] query_rewriter")
    query = state["query"]
    history = state.get("history", [])
    
    # 1. Save User Turn to Deep Memory (Async-like)
    deep_memory.add_turn("user", query)

    # If no history, no need to rewrite
    if not history:
        return {"step_count": state.get("step_count", 0) + 1}
    
    # 2. Retrieve Long-Term Context
    lt_context = deep_memory.search_context(query, k=2, threshold=0.5)

    from config.llm_config import get_query_planner_llm
    llm = get_query_planner_llm()
    
    # Format Context: Short Term + Long Term
    st_context = history[-3:] if len(history) > 3 else history
    context_str = "--- RECENT CONVERSATION ---\n"
    context_str += "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in st_context])
    
    if lt_context:
        context_str += "\n\n--- RELEVANT PAST MEMORY ---\n"
        context_str += "\n".join([f"[{m.get('timestamp'):.0f}] {m.get('role')}: {m.get('content')}" for m in lt_context])
    
    REWRITE_PROMPT = f"""You are a query resolution expert.
Your task is to REWRITE the User's latest query into a STANDALONE version.

Context:
{context_str}

User's Latest Query: "{query}"

RULES:
1. Replace "it", "that", "the first one" with actual product names/topics.
2. If already standalone, output EXACTLY as is.
3. Output ONLY the rewritten query.

Rewritten Query:"""

    try:
        response = llm.invoke(REWRITE_PROMPT)
        # Handle both string and object responses
        rewritten = response if isinstance(response, str) else getattr(response, 'content', str(response))
        rewritten = rewritten.strip().strip('"')
        
        if rewritten.lower() != query.lower():
            print(f" [Rewriter] '{query}' -> '{rewritten}'")
            return {
                "query": rewritten,
                "original_query": query, 
                "step_count": state.get("step_count", 0) + 1
            }
        else:
            print(f" [Rewriter] No change needed")
            return {"step_count": state.get("step_count", 0) + 1}
            
    except Exception as e:
        print(f" [Rewriter Error] {e}")
        return {"step_count": state.get("step_count", 0) + 1}



def check_cache_node(state: AgentState)-> dict:
    """Check redis for fresh cached products
    Fresh= cached within last 1 hour(3600 seconds)
    """
    print("[NODE] check_cache")
    query = state["query"]
    cached = redis_cache.get_search(query)
    if cached :
        # check freshness(timestamp stored with cache)
        cache_time = cached.get("timestamp",0)
        age_seconds = time.time() - cache_time
        
        if age_seconds < 3600 : # fresh (< 1 hour)
            print(f" [Cache HIT] Fresh data ({age_seconds: .0f}s old)")
            return {
                "cache_hit": True,
                "cached_products":cached.get("products",[]),
                "step_count":state.get("step_count",0)+1
            }
        else :
            print(f" [Cache Stale] data is {age_seconds:.0f}h old, refreshing")
    
    # ---------------------------------------------------------
    # SEMANTIC CACHE CHECK (Fallback if exact match fails)
    # ---------------------------------------------------------
    try:
        query_type = state.get("query_type", "unknown")
        semantic_hit = semantic_cache.search(query, query_type)
        
        if semantic_hit:
            print(f" [Semantic Cache HIT] Found similar query")
            return {
                "cache_hit": True,
                "cached_products": semantic_hit.get("products", []),
                "step_count": state.get("step_count", 0) + 1
            }
    except Exception as e:
        print(f" [Semantic Cache Error] {e}")

    print(" [Cache MISS] No cached data (Exact or Semantic)")

    return {
        "cache_hit":False,
        "cached_products":[],
        "step_count": state.get("step_count", 0)+1
    }


# ============================================================
# Phase 1: Smart Planner (8 Query Types + Slot Extraction)
# ============================================================

from agent.single_agent.smart_planner import smart_classify_and_extract


def generate_fallback_response(query: str) -> str:
    """Generate a helpful fallback response for unknown queries."""
    return f"""I'm not sure I understand your query: "{query}"

**I can help you with:**
• Finding product prices (e.g., "iPhone 15 price")
• Comparing products (e.g., "iPhone vs Samsung")
• Recommendations under a budget (e.g., "best phones under 30k")
• Product advice (e.g., "what to look for in a laptop")

Could you please rephrase your question?"""


# Query templates for search query generation
QUERY_TEMPLATES = {
    "price_search": [
        'site:amazon.in "{product}" -case -cover',
        'site:flipkart.com "{product}" -cover -glass',
        '"{product}" price india croma reliance',
    ],
    "comparison": [
        '"{product_a}" vs "{product_b}" comparison india',
        'site:amazon.in "{product_a}"',
        'site:flipkart.com "{product_b}"',
    ],
    "best_under": [
        'best {category} under {budget} india 2024',
        'top {category} under {budget} rupees',
        'site:91mobiles.com best {category} under {budget}',
        'site:smartprix.com {category} under {budget}',
    ],
    "feature_query": [
        '"{product}" specifications features',
        '"{product}" {feature}',
    ],
    "product_advice": [
        'how to choose best {category} guide',
        'what to look for when buying {category}',
        '{category} buying guide 2024',
    ],
    "general": [
        'site:amazon.in "{product}" -case -cover',
        'site:flipkart.com "{product}" -cover -glass',
        '"{product}" buy online india price',
    ],
}


def smart_planner_node(state: AgentState) -> dict:
    """
    Phase 1: Smart Query Classification & Slot Extraction
    
    Features:
    - 8 query type classification with confidence
    - Slot extraction (budget, category, use_case)
    - Follow-up detection
    - Unknown query fallback
    - LLM-based query generation (from query/enhancer.py)
    
    Returns updated state with:
    - query_type, classification_confidence
    - extracted_slots, missing_slots
    - is_follow_up
    - search_queries (LLM-generated)
    """
    print("[NODE] smart_planner")
    query = state["query"]
    
    # Get context from state (for follow-up detection)
    conversation_history = state.get("conversation_history", [])
    previous_products = state.get("previous_products", [])
    
    # Run smart classification
    result = smart_classify_and_extract(
        query=query,
        conversation_history=conversation_history,
        previous_products=previous_products
    )
    
    query_type = result['query_type']
    confidence = result['confidence']
    slots = result['slots']
    missing_slots = result['missing_slots']
    is_follow_up = result['is_follow_up']
    
    print(f"  [Planner] Type: {query_type} (confidence: {confidence:.2f})")
    print(f"  [Planner] Slots: {slots}")
    
    # Handle unknown/conversational - no search needed
    if query_type in ['unknown', 'conversational']:
        print(f"  [Planner] No search needed for {query_type}")
        return {
            "query_type": query_type,
            "classification_confidence": confidence,
            "extracted_slots": slots,
            "missing_slots": missing_slots,
            "is_follow_up": is_follow_up,
            "search_queries": {"price": [], "spec": []},
            "step_count": state.get("step_count", 0) + 1
        }
    
    # Handle follow-up queries - use previous context
    if is_follow_up and previous_products:
        print(f"  [Planner] Follow-up detected, using previous context")
        # For follow-ups, we might modify previous results rather than new search
        return {
            "query_type": "follow_up",
            "classification_confidence": confidence,
            "extracted_slots": slots,
            "missing_slots": [],
            "is_follow_up": True,
            "search_queries": {"price": [], "spec": []},  # Will use previous_products
            "step_count": state.get("step_count", 0) + 1
        }
    
    # Generate search query - simplified for Tavily
    # Tavily uses a single query string, not multiple categorized queries
    search_queries = {
        'price': [query] if query_type in ['price_search', 'comparison'] else [],
        'spec': [query] if query_type in ['best_under', 'product_advice', 'feature_query'] else []
    }
    
    # If no specific category, use both
    if not search_queries['price'] and not search_queries['spec']:
        search_queries['spec'] = [query]
    
    total_queries = len(search_queries.get('price', [])) + len(search_queries.get('spec', []))
    print(f"  [Planner] Using query for Tavily: '{query}'")

    
    return {
        "query_type": query_type,
        "classification_confidence": confidence,
        "extracted_slots": slots,
        "missing_slots": missing_slots,
        "is_follow_up": is_follow_up,
        "search_queries": search_queries,
        "step_count": state.get("step_count", 0) + 1
    }


def fallback_handler_node(state: AgentState) -> dict:
    """
    Handle unknown or conversational queries with a helpful response.
    """
    print("[NODE] fallback_handler")
    query_type = state.get("query_type", "unknown")
    query = state["query"]
    
    if query_type == "conversational":
        # Handle greetings, thanks, etc. with inline logic
        query_lower = query.lower().strip()
        if any(g in query_lower for g in ['hi', 'hello', 'hey']):
            response = "Hello! 👋 I'm your shopping assistant. What product are you looking for today?"
        elif any(t in query_lower for t in ['thanks', 'thank you', 'thx']):
            response = "You're welcome! 😊 Let me know if you need anything else."
        elif any(b in query_lower for b in ['bye', 'goodbye']):
            response = "Goodbye! Happy shopping! 🛒"
        else:
            response = "How can I help you with your shopping today?"
    else:
        # Unknown query - provide helpful fallback
        response = generate_fallback_response(query)
    
    return {
        "final_answer": response,
        "recommendation": response,
        "step_count": state.get("step_count", 0) + 1
    }


def variant_filter_node(state: AgentState) -> dict:
    """
    Phase 3: Pass-through for Tavily results.
    
    V3.1 UPDATE: Pure pass-through since Tavily already:
    - Returns unique URLs
    - Pre-filters quality results
    - Includes raw_content for advisor
    
    No deduplication or limits needed.
    """
    print("[NODE] variant_filter (pass-through)")
    results = state.get("raw_search_results", [])
    
    if not results:
        print("  [Filter] No results")
        return {
            "filtered_urls": [],
            "candidates": [],
            "step_count": state.get("step_count", 0) + 1
        }
    
    # Pass ALL results through with raw_content preserved
    candidates = []
    for r in results:
        candidates.append({
            "name": r.get("title", "")[:100],
            "url": r.get("url", r.get("href", "")),
            "content": r.get("content", ""),
            "raw_content": r.get("raw_content", ""),
            "source": "tavily",
            "score": r.get("score", 0),
        })
    
    print(f"  [Filter] Passing {len(candidates)} results to advisor")
    
    return {
        "filtered_urls": candidates,
        "candidates": candidates,
        "step_count": state.get("step_count", 0) + 1
    }


# ============================================================
# Phase 2: Parallel Search (Multi-Engine)
# ============================================================

def search_node(state: AgentState) -> dict:
    """
    Phase 2: Query-Specific Search Routing.
    
    V7 UPDATE: 4 explicit routes based on input + query_type:
    
    ROUTE 0: User pasted a URL (e-commerce / any page)
             → Direct Crawl4AI (JS-heavy, no cascade waste)
    ROUTE 1: price_search
             → single_product_pipeline (5-store e-commerce sweep)
    ROUTE 2: feature_query / comparison
             → Tavily Smart Search (reranked raw_content, best relevance)
    ROUTE 3: Default (best_under, product_advice, etc.)
             → Tavily (standard behavior)
    """
    print("[NODE] search (V7 - Smart Routing)")
    
    query = state.get("query", "")
    query_type = state.get("query_type", "unknown")
    extracted_slots = state.get("extracted_slots", {})
    previous_products = state.get("previous_products", [])
    provided_url = state.get("provided_url", "")
    
    if not query and not provided_url:
        print("  [Search] No query or URL provided")
        return {"raw_search_results": [], "step_count": state.get("step_count", 0) + 1}
    
    print(f"  [Search] Query: '{query[:50]}' | URL: '{provided_url[:40]}' | type: {query_type}")
    
    try:
        # ════════════════════════════════════════════════════
        # ROUTE 0: USER-PROVIDED URL → Direct Crawl4AI
        # E-commerce pages are JS-heavy. No cascade waste.
        # ════════════════════════════════════════════════════
        if provided_url:
            print(f"  [Search] 🔗 Route 0: User URL -> Seed to Sweep: {provided_url[:60]}")
            from scraping.concurrency import scrape_urls_concurrent_v2
            from extract.llm_extraction import extract_single_product
            from scraping.single_product_pipeline import execute_unified_product_pipeline
            
            # Step 1: Scrape the user's seed URL
            # We're in a thread executor (no event loop), so asyncio.run() is safe
            scrape_results = asyncio.run(
                scrape_urls_concurrent_v2(
                    [provided_url],
                    max_concurrent=1,
                    timeout=30.0,
                )
            )
            
            seed_data = scrape_results.get(provided_url, {})
            formatted_results = []
            extracted_product_name = ""
            
            if seed_data.get("success") and seed_data.get("markdown"):
                seed_markdown = seed_data["markdown"]
                print(f"  [Search] Scraped {len(seed_markdown)} chars from seed")
                
                # Step 2: Extract Identity from seed markdown
                try:
                    product_info = asyncio.run(
                        extract_single_product(seed_markdown, url=provided_url)
                    )
                    
                    if product_info and product_info.name:
                        extracted_product_name = product_info.name
                        print(f"  [Search] 🧠 Extracted Identity: '{extracted_product_name}'")
                except Exception as e:
                    print(f"  [Search] Extraction failed: {e}")

                # Add seed URL result to the list
                formatted_results.append({
                    "title": f"Source: {provided_url.split('/')[2] if '/' in provided_url else provided_url}",
                    "url": provided_url,
                    "href": provided_url,
                    "content": seed_markdown[:500],
                    "raw_content": seed_markdown,
                    "score": 1.1, # Boost seed URL
                    "source_category": "user_seed",
                })
            
            # Step 3: If we have an identity, trigger the full store sweep
            if extracted_product_name:
                print(f"  [Search] 🚀 Triggering e-commerce sweep for '{extracted_product_name}'")
                
                # Search across all stores
                sweep_result = asyncio.run(
                    execute_unified_product_pipeline(
                        product_identity=extracted_product_name,
                        scrape_timeout=25.0,
                    )
                )
                
                # Merge sweep results
                sweep_results_dict = sweep_result.get("results", {})
                for url, markdown in sweep_results_dict.items():
                    # Avoid duplicating the seed URL if it was found in search
                    if url == provided_url:
                        continue
                        
                    formatted_results.append({
                        "title": f"Store: {url.split('/')[2]}" if '/' in url else "E-Commerce",
                        "url": url,
                        "href": url,
                        "content": markdown[:500] if markdown else "",
                        "raw_content": markdown or "",
                        "score": 1.0,
                        "source_category": "ecommerce_sweep",
                    })
                
                print(f"  [Search] Sweep added {len(sweep_results_dict)} more results")
            
            return {
                "raw_search_results": formatted_results,
                "step_count": state.get("step_count", 0) + 1,
            }

        # ════════════════════════════════════════════════════
        # ROUTE 1: PRICE SEARCH → E-Commerce Pipeline
        # ════════════════════════════════════════════════════
        if query_type == "price_search":
            print("  [Search] ⚡ Routing to E-Commerce Pipeline (single_product_pipeline)")
            from scraping.single_product_pipeline import execute_unified_product_pipeline
            
            product_identity = extracted_slots.get("product", query)
            # Try to extract brand from product name for official store
            brand_name = ""
            product_lower = product_identity.lower()
            known_brands = ["apple", "samsung", "oneplus", "xiaomi", "sony", "lg", "hp", "dell", "lenovo", "asus", "acer", "boat", "jbl", "nothing"]
            for brand in known_brands:
                if brand in product_lower:
                    brand_name = brand.capitalize()
                    break
            
            print(f"  [Search] Product: '{product_identity}', Brand: '{brand_name or 'unknown'}'")
            
            # Execute the monolithic pipeline (async → sync bridge)
            # We're in a thread executor (no event loop), so asyncio.run() is safe
            pipeline_result = asyncio.run(
                execute_unified_product_pipeline(
                    product_identity=product_identity,
                    brand_name=brand_name,
                    scrape_timeout=25.0,
                    max_concurrent_scrapes=5,
                )
            )
            
            # Format {url: markdown} into raw_search_results for advisor
            formatted_results = []
            for url, markdown in pipeline_result.get("results", {}).items():
                formatted_results.append({
                    "title": f"Store: {url.split('/')[2]}" if '/' in url else "E-Commerce",
                    "url": url,
                    "href": url,
                    "content": markdown[:500] if markdown else "",
                    "raw_content": markdown or "",
                    "score": 1.0,
                    "source_category": "ecommerce",
                })
            
            total = pipeline_result.get("total_scraped", 0)
            print(f"  [Search] Pipeline returned {total} store results")
            
            return {
                "raw_search_results": formatted_results,
                "raw_markdown_sources": pipeline_result.get("results", {}),
                "step_count": state.get("step_count", 0) + 1
            }
        
        # ════════════════════════════════════════════════════
        # ROUTE 2: FEATURE QUERY / COMPARISON → Tavily (Reranked)
        # Tavily AI-reranks and bundles raw_content in one call.
        # This is better than DDG + self-scrape for relevance-heavy queries.
        # ════════════════════════════════════════════════════
        elif query_type in ["feature_query", "comparison"]:
            print(f"  [Search] 🔍 Route 2: Tavily reranked search for {query_type}")
            from scraping import tavily_smart_search
            
            # Append research-intent keywords to improve reranking
            search_intent = query
            if query_type == "feature_query":
                search_intent += " review test benchmark"
            else:
                search_intent += " vs comparison review"
            
            # Tavily returns reranked results with raw_content bundled
            tavily_resp = tavily_smart_search(
                query=search_intent,
                query_type=query_type,
                extracted_slots=extracted_slots,
                previous_products=previous_products,
            )
            
            # Extract results — Tavily's raw_content is the primary data source
            formatted_results = []
            for r in tavily_resp.get("results", []):
                formatted_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "href": r.get("url", ""),
                    "content": r.get("content", ""),
                    "raw_content": r.get("raw_content", r.get("content", "")),
                    "score": r.get("score", 0),
                    "source_category": "tavily_research",
                })
            
            print(f"  [Search] Route 2: Tavily returned {len(formatted_results)} reranked results")
            return {
                "raw_search_results": formatted_results,
                "step_count": state.get("step_count", 0) + 1
            }
        
        # ════════════════════════════════════════════════════
        # ROUTE 3: DEFAULT → Tavily (best_under, product_advice, etc.)
        # ════════════════════════════════════════════════════
        else:
            print(f"  [Search] 🔍 Default Tavily search for {query_type}")
            from scraping import tavily_smart_search
            
            result = tavily_smart_search(
                query=query,
                query_type=query_type,
                extracted_slots=extracted_slots,
                previous_products=previous_products,
            )
            
            # Handle memory-based follow-ups
            if result.get("from_memory"):
                print(f"  [Search] Filtered from memory: {len(result.get('filtered_products', []))} products")
                return {
                    "raw_search_results": [],
                    "verified_products": result.get("filtered_products", []),
                    "step_count": state.get("step_count", 0) + 1
                }
            
            # Handle conversational responses
            if result.get("answer") and not result.get("results"):
                print(f"  [Search] Conversational response")
                return {
                    "raw_search_results": [],
                    "final_answer": result.get("answer", ""),
                    "step_count": state.get("step_count", 0) + 1
                }
            
            # Normal Tavily results
            results = result.get("results", [])
            print(f"  [Search] Tavily returned {len(results)} results")
            
            transformed_results = []
            for r in results:
                transformed_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "href": r.get("url", ""),
                    "content": r.get("content", ""),
                    "raw_content": r.get("raw_content", ""),
                    "score": r.get("score", 0),
                    "source_category": "tavily",
                })
            
            return {
                "raw_search_results": transformed_results,
                "step_count": state.get("step_count", 0) + 1
            }
    
    except Exception as e:
        print(f"  [Search] Routing error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "raw_search_results": [],
            "error": f"Search routing failed: {e}",
            "step_count": state.get("step_count", 0) + 1
        }


# ============================================================
# SPEC-FIRST DISCOVERY (for best_under queries)
# ============================================================

def extract_products_node(state: AgentState) -> dict:
    """
    Discover products for 'best_under' queries using Tavily.
    
    V3 UPDATE: Simplified to use Tavily directly.
    - Uses tavily_best_under_search for targeted results
    - Extracts products from raw_content using LLM
    - No Crawl4AI or extract folder dependencies
    """
    print("\n[NODE] best_under_discovery (Tavily)")
    
    query_type = state.get("query_type", "")
    if query_type != "best_under":
        print("  [Discovery] Skipping - not a best_under query")
        return {"discovered_products": []}
    
    # Get slots
    slots = state.get("extracted_slots", {})
    category = slots.get("category", "phone")
    budget = slots.get("budget")
    
    # Build discovery query
    query = state.get("query", "")
    if not query and category and budget:
        query = f"best {category} under {budget}"
    
    print(f"  [Discovery] Query: '{query}' (category: {category}, budget: {budget})")
    
    try:
        from scraping import tavily_best_under_search
        
        # Use Tavily's best_under search
        result = tavily_best_under_search(
            category=category,
            budget=budget,
            query=query
        )
        
        if result.get("error"):
            print(f"  [Discovery] Error: {result['error']}")
            return {"discovered_products": []}
        
        search_results = result.get("results", [])
        print(f"  [Discovery] Tavily returned {len(search_results)} results")
        
        # Extract products from raw_content using LLM
        discovered_products = []
        
        # LLM prompt for extracting products from list pages
        PRODUCT_LIST_PROMPT = """Extract product names and prices from this content about "{category}" under ₹{budget}.

{content}

Return a JSON array of products found:
[{{"name": "Product Name", "price": 29999, "brand": "Brand"}}]

RULES:
- Only include products that cost LESS than ₹{budget}
- "price" must be a NUMBER (no ₹ symbol, no commas)
- Return ONLY valid JSON array, no explanation
- Maximum 5 products"""

        from config.llm_config import get_query_planner_llm
        llm = None
        try:
            llm = get_query_planner_llm()
        except Exception as e:
            print(f"  [Discovery] LLM Error: {e}")
        
        for r in search_results[:5]:
            raw_content = r.get("raw_content", "")
            content = r.get("content", "")
            url = r.get("url", "")
            
            text = raw_content if raw_content else content
            if not text or len(text) < 200:
                continue
            
            # Try LLM extraction
            if llm:
                try:
                    prompt = PRODUCT_LIST_PROMPT.format(
                        category=category,
                        budget=budget or 100000,
                        content=text[:5000]
                    )
                    
                    response = llm.invoke(prompt)
                    # Handle both string and object responses
                    if hasattr(response, 'content'):
                        response_text = response.content
                    elif isinstance(response, str):
                        response_text = response
                    else:
                        response_text = str(response)
                    
                    import json
                    import re
                    
                    # Find JSON array in response
                    json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                    if json_match:
                        products = json.loads(json_match.group())
                        for p in products:
                            if p.get("name") and p.get("price"):
                                discovered_products.append({
                                    "name": p.get("name", "")[:60],
                                    "price": int(p.get("price", 0)),
                                    "brand": p.get("brand"),
                                    "source_url": url,
                                    "source": "tavily",
                                })
                        print(f"  [Discovery] {url[:40]}... -> {len(products)} products")
                        
                except Exception as e:
                    error_msg = str(e)
                    # Only print once, not for every result
                    if "Connection" in error_msg and len(discovered_products) == 0:
                        print(f"  [Discovery] LLM connection issue - falling back to advisor")
                        break  # Exit loop, let advisor handle raw content
                    else:
                        print(f"  [Discovery] Extraction skip: {error_msg[:50]}")
        
        # Deduplicate by name
        seen_names = set()
        unique_products = []
        for p in discovered_products:
            name_key = p.get("name", "").lower()[:30]
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                unique_products.append(p)
        
        # Filter by budget
        if budget:
            unique_products = [p for p in unique_products if p.get("price", 0) < budget]
        
        # Take top 7
        top_products = unique_products[:7]
        
        # FALLBACK: If no products extracted, pass raw content to advisor
        if not top_products and search_results:
            print(f"  [Discovery] No products extracted - advisor will use raw content")
            # Return empty discovered_products but keep search_results for advisor
            return {
                "discovered_products": [],
                "search_results": search_results,  # Pass raw results to advisor
                "step_count": state.get("step_count", 0) + 1
            }
        
        print(f"\n  [Discovery] ✅ Found {len(top_products)} products under ₹{budget:,}")
        for i, p in enumerate(top_products, 1):
            print(f"    {i}. {p['name'][:35]}... -> ₹{p.get('price', 0):,}")
        
        return {
            "discovered_products": top_products,
            "verified_products": top_products,  # Skip separate verification
            "step_count": state.get("step_count", 0) + 1
        }
        
    except Exception as e:
        print(f"  [Discovery] Error: {e}")
        return {
            "discovered_products": [],
            "step_count": state.get("step_count", 0) + 1
        }

def adviser_node(state:AgentState)-> dict:
    """LLM analyzes products and generates recommendations.
    
    V5 UPDATE: Handles raw_search_results directly from search_node.
    - Single LLM call for extraction + recommendation
    - No separate verification or extraction step needed
    """
    print("[NODE] Advisor")
    
    # Import prompts from centralized location
    from prompts.advisor import ADVISOR_SYSTEM_PROMPT, format_user_message, get_prompt_by_query_type

    query = state["query"]
    query_type = state.get("query_type", "price_search")
    
    # Select prompt based on query type
    system_prompt = get_prompt_by_query_type(query_type)
    print(f"  [Advisor] Using {query_type} prompt")
    
    # V5: Check for raw_search_results from search_node (new simplified flow)
    raw_search_results = state.get("raw_search_results", [])
    
    if raw_search_results:
        print(f"  [Advisor] Processing {len(raw_search_results)} Tavily results")
        
        # Build combined content from all results
        content_sections = []
        for i, r in enumerate(raw_search_results, 1):
            title = r.get("title", "Unknown")
            url = r.get("url", "")
            raw_content = r.get("raw_content", r.get("content", ""))
            
            # Limit raw_content to avoid token overflow
            if raw_content:
                truncated = raw_content[:4000]  # ~1000 tokens per result
                content_sections.append(
                    f"## Source {i}: {title}\n"
                    f"**URL:** {url}\n\n"
                    f"{truncated}\n"
                )
        
        if content_sections:
            combined_content = "\n---\n".join(content_sections[:5])  # Max 5 sources
            user_message = format_user_message(query, combined_content)
            full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"
            
            try:
                advisor = get_advisor()
                response = advisor.invoke(full_prompt)
                answer = response if isinstance(response, str) else getattr(response, 'content', str(response))
                
                # Save AI Turn to Deep Memory (Async-like)
                deep_memory.add_turn("assistant", answer)

                # Store results for follow-up queries
                return {
                    "recommendation": "tavily_direct",
                    "final_answer": answer,
                    "previous_products": raw_search_results,  # For follow-up context
                    "step_count": state.get("step_count",0)+1
                }
            except Exception as e:
                print(f"  [Advisor Error] {e}")
                return {
                    "recommendation": "error",
                    "final_answer": f"Error generating advice: {e}",
                    "step_count": state.get("step_count",0)+1
                }
    
    # LEGACY: Check for candidates with raw_content (old flow)
    candidates = state.get("candidates", [])
    verified_products = state.get("verified_products", []) or state.get("cached_products",[])
    raw_markdown_sources = state.get("raw_markdown_sources", {})

    
    # FALLBACK: Handle raw_markdown_sources (legacy flow)
    if not verified_products and raw_markdown_sources:
        print("  [Advisor] No extracted products, using raw markdown fallback")
        # Build combined markdown for advisor
        markdown_sections = []
        for url, md in list(raw_markdown_sources.items())[:3]:  # Limit to 3 sources
            markdown_sections.append(f"## Source: {url[:60]}...\n\n{md[:6000]}")
        
        combined_md = "\n\n---\n\n".join(markdown_sections)
        user_message = format_user_message(query, combined_md)
        full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"
        
        try:
            advisor = get_advisor()
            response = advisor.invoke(full_prompt)
            answer = response if isinstance(response, str) else getattr(response, 'content', str(response))
            return {
                "recommendation": "compare_more",
                "final_answer": answer,
                "step_count": state.get("step_count",0)+1
            }
        except Exception as e:
            print(f" [Advisor Fallback Error] {e}")
            return {
                "recommendation": "no_data",
                "final_answer": "Could not analyze products. Please try again.",
                "step_count": state.get("step_count",0)+1
            }
    
    # LEGACY: Use verified_products if available
    products = verified_products
    
    if not products:
        return {
            "recommendation":"no_data",
            "final_answer":"No product data available. Please try a different search.",
            "step_count":state.get("step_count",0)+1
        }

    
    # Step-1: Build STRUCTURED product data for LLM (prices are reliable here)
    product_lines = []
    for i, p in enumerate(products, 1):
        price = f"₹{p['price']:,}" if p.get('price') else "Price not available"
        site = p.get('site', 'Unknown')
        url = p.get('url', '')
        
        # Build specs list
        specs = []
        if p.get('cpu'): specs.append(f"CPU: {p['cpu']}")
        if p.get('gpu'): specs.append(f"GPU: {p['gpu']}")
        if p.get('ram_gb'): specs.append(f"RAM: {p['ram_gb']} GB")
        if p.get('rating'): specs.append(f"Rating: {p['rating']}/5")
        if p.get('in_stock') is not None:
            specs.append("In Stock" if p['in_stock'] else "Out of Stock")
        
        product_lines.append(
            f"## Product {i}: {p['name']}\n"
            f"- **Price:** {price}\n"
            f"- **Store:** {site}\n"
            f"- **Specs:** {', '.join(specs) if specs else 'See raw source below'}\n"
            f"- **URL:** {url[:80]}..."
        )

    structured_data = "\n\n".join(product_lines)
    
    # Step-2: Include RAW MARKDOWN for additional context (if specs missing)
    raw_context = ""
    if raw_markdown_sources and any(not p.get('cpu') and not p.get('ram_gb') for p in products):
        # Include first 2 markdown sources for additional specs
        raw_sections = []
        for url, md in list(raw_markdown_sources.items())[:2]:
            raw_sections.append(f"### Source: {url[:50]}...\n{md[:3000]}")
        if raw_sections:
            raw_context = "\n\n# [RAW SOURCES - For additional specs/context]\n\n" + "\n\n".join(raw_sections)
    
    # Step-3: Build combined prompt
    combined_data = structured_data + raw_context
    user_message = format_user_message(query, combined_data)
    
    # Combine system prompt with user message
    full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"
    
    # Step-3: LLM Calling
    try:
        advisor = get_advisor()
        response = advisor.invoke(full_prompt)
        answer = response if isinstance(response, str) else getattr(response, 'content', str(response))

        # Determine recommendation type from response
        answer_upper = answer.upper()
        if "BUY" in answer_upper and "SKIP" not in answer_upper:
            recommendation = "buy_now"
        elif "WAIT" in answer_upper or "SKIP" in answer_upper:
            recommendation = "wait"
        else:
            recommendation = "compare_more"
        print(f" [Advisor] Recommendation: {recommendation}")
    except Exception as e:
        print(f" [LLM Error] {e}")
        # Fallback: simple price comparison
        priced = [p for p in products if p.get('price')]
        if priced:
            cheapest = min(priced, key=lambda x: x.get('price', float('inf')))
            answer = f"Best price: {cheapest['name']} at ₹{cheapest.get('price', 'N/A'):,}"
        else:
            answer = f"Found {len(products)} products but no prices available."
        recommendation = "compare_more"
    
    # Step-4: Cache results (Standard + Semantic)
    try:
        # 1. Standard Redis Cache (Exact Match)
        cache_data = {
            "products": products,
            "timestamp": time.time()
        }
        redis_cache.set_search_typed(query, cache_data, query_type=query_type)
        
        # 2. Semantic Cache (Vector Search)
        # Wrap specifically for semantic to handle model loading issues
        try:
            semantic_cache.cache_result(query, query_type, cache_data)
            print(f" [Cache] Saved to Standard & Semantic cache ({query_type})")
        except Exception as sem_e:
            print(f" [Semantic Cache write error] {sem_e}")
            
    except Exception as e:
        print(f" [Cache Error] {e}")

    return {
        "recommendation":recommendation,
        "final_answer": answer,
        "step_count": state.get("step_count",0)+1
        }

def error_handler_node(state:AgentState)-> dict:
    """Handles errors gracefully"""

    print("[NODE] Error_handler")

    error= state.get("error", "unknown error")
    query= state["query"]

    message = f""" Search Issue
    I couldn't find products for {query}
    **ERROR:** {error}
    **TRY:**
    -More specific search
    -Different price range
    -check spelling
    """
    return {
        "final_answer": message,
        "step_count": state.get("step_count", 0) + 1
    }