"""
Query Enhancement & Multi-Query Generation Prompts
===================================================
Contains prompts and helpers for:
1. Multi-Query Generation - Generate 5 variations of user query
2. Query Rewriting - Optimize query for e-commerce search
3. Result Reranking - Filter and score search results
"""

import json
import re
from typing import List, Dict, Any, Optional
from functools import lru_cache


# ============================================================
# LLM SETUP
# ============================================================

@lru_cache(maxsize=1)
def _get_query_llm():
    """Get LLM for fast query enhancement."""
    try:
        from config.llm_config import get_query_planner_llm
        return get_query_planner_llm()
    except Exception as e:
        print(f"[Query Enhancer] Warning: Could not load LLM: {e}")
        return None


# ============================================================
# MULTI-QUERY GENERATION
# ============================================================

MULTI_QUERY_PROMPT = """Generate 5 search queries to find product prices on Indian e-commerce sites.

User query: "{query}"

Rules:
1. Include the exact product name/model
2. Add storage/RAM variants if applicable (e.g., "256GB", "12GB RAM")
3. At least 2 queries MUST use site: operators like:
   - site:flipkart.com
   - site:amazon.in
   - site:gadgets360.com
   - site:91mobiles.com
4. Include brand name variations (e.g., "iQOO" and "vivo iQOO")
5. Focus on finding PRODUCT PAGES, not reviews or news
6. Use price-related terms like "price", "buy online", "best price"

Return ONLY a JSON array of 5 query strings, no other text:
["query1", "query2", "query3", "query4", "query5"]"""


def generate_multi_queries(user_query: str) -> List[str]:
    """Generate 5 search query variations from user input."""
    llm = _get_query_llm()
    
    if not llm:
        return _fallback_multi_query(user_query)
    
    try:
        prompt = MULTI_QUERY_PROMPT.format(query=user_query)
        response = llm.invoke(prompt)
        queries = _extract_json_array(response)
        
        if queries and len(queries) >= 3:
            print(f"  [Multi-Query] Generated {len(queries)} queries")
            return queries[:5]
        else:
            return _fallback_multi_query(user_query)
            
    except Exception as e:
        print(f"  [Multi-Query] Error: {e}")
        return _fallback_multi_query(user_query)


def _fallback_multi_query(query: str) -> List[str]:
    """Fallback query generation without LLM."""
    base = query.strip()
    return [
        f'site:flipkart.com "{base}" price',
        f'site:amazon.in "{base}" -case -cover',
        f'{base} price India buy online',
        f'{base} specifications price Flipkart',
        f'{base} best price',
    ]


# ============================================================
# QUERY REWRITING
# ============================================================

REWRITE_PROMPT = """Rewrite this search query to find product prices on Indian e-commerce sites.

Original query: "{query}"

Rules:
1. Fix any typos or spelling errors
2. Add the full brand name if abbreviated
3. Add "price India" or "buy online" for shopping intent
4. Include specific model numbers if identifiable
5. Keep it concise (under 15 words)

Return ONLY the rewritten query, no explanation:"""


def rewrite_query(user_query: str) -> str:
    """Rewrite user query for better search results."""
    llm = _get_query_llm()
    
    if not llm:
        return _fallback_rewrite(user_query)
    
    try:
        prompt = REWRITE_PROMPT.format(query=user_query)
        response = llm.invoke(prompt)
        rewritten = response.strip().strip('"\'')
        
        if len(rewritten) > 5 and len(rewritten) < 200:
            print(f"  [Rewrite] '{user_query}' -> '{rewritten}'")
            return rewritten
        else:
            return _fallback_rewrite(user_query)
            
    except Exception as e:
        print(f"  [Rewrite] Error: {e}")
        return _fallback_rewrite(user_query)


def _fallback_rewrite(query: str) -> str:
    """Simple query cleanup without LLM."""
    fixes = {
        "iqo": "iQOO",
        "iqoo": "iQOO",
        "iphone": "iPhone",
        "samsung": "Samsung",
        "oneplus": "OnePlus",
        "realme": "Realme",
        "redmi": "Redmi",
        "poco": "POCO",
    }
    
    result = query.lower()
    for wrong, right in fixes.items():
        if wrong in result:
            result = result.replace(wrong, right)
    
    if "price" not in result.lower():
        result = f"{result} price India"
    
    return result


# ============================================================
# RESULT RERANKING
# ============================================================

RERANK_PROMPT = """Score these search results for relevance to the query: "{query}"

For each result, determine:
- Is it a PRODUCT PAGE (not a category, review, or news article)?
- Does it match the exact product the user is looking for?
- Is it from a legitimate e-commerce site?

Results to score:
{results_json}

Return a JSON array with scores (0-10) for each result:
[{{"url": "...", "score": 8, "is_product": true}}, ...]

Score guide:
- 10: Exact product match, product page
- 7-9: Correct product, might be variant
- 4-6: Related product or category page
- 0-3: Wrong product, accessory, or article

Return ONLY the JSON array:"""


def rerank_results(query: str, results: List[Dict[str, Any]], min_score: int = 5) -> List[Dict[str, Any]]:
    """Rerank and filter search results by relevance."""
    if not results:
        return []
    
    llm = _get_query_llm()
    if not llm:
        return _fallback_rerank(query, results)
    
    try:
        results_to_score = results[:10]
        results_json = json.dumps([
            {"title": r.get("title", "")[:100], "url": r.get("url", r.get("href", ""))[:100]}
            for r in results_to_score
        ], indent=2)
        
        prompt = RERANK_PROMPT.format(query=query, results_json=results_json)
        response = llm.invoke(prompt)
        scored = _extract_json_array(response)
        
        if scored:
            url_to_score = {s.get("url", "")[:100]: s.get("score", 0) for s in scored}
            for r in results_to_score:
                url_key = r.get("url", r.get("href", ""))[:100]
                r["relevance_score"] = url_to_score.get(url_key, 5)
            
            filtered = [r for r in results_to_score if r.get("relevance_score", 0) >= min_score]
            filtered.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            return filtered
        else:
            return _fallback_rerank(query, results)
            
    except Exception as e:
        print(f"  [Rerank] Error: {e}")
        return _fallback_rerank(query, results)


def _fallback_rerank(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Simple keyword-based reranking without LLM."""
    query_words = set(query.lower().split())
    skip_keywords = ['protector', 'charger', 'case', 'cover', 'cable', 'adapter', 'glass']
    
    scored = []
    for r in results:
        title = r.get("title", "").lower()
        url = r.get("url", r.get("href", "")).lower()
        if any(skip in title for skip in skip_keywords):
            continue
        
        title_words = set(title.split())
        overlap = len(query_words & title_words)
        is_product = "/p/" in url or "/dp/" in url
        score = overlap * 2 + (3 if is_product else 0)
        
        r["relevance_score"] = min(score, 10)
        scored.append(r)
    
    scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return scored[:6]


def _extract_json_array(text: str) -> Optional[List]:
    """Extract JSON array from LLM response."""
    try:
        return json.loads(text)
    except:
        pass
    
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None
