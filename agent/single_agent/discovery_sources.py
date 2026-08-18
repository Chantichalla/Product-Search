"""
Discovery Sources for Spec-First Pipeline

This module provides additional data sources for product discovery:
- Reddit (P2): Extract product mentions from Reddit discussions
- YouTube (P3): Extract product mentions from video transcripts
- Price Lookup (P4): Targeted e-commerce searches for discovered products
"""

import requests
import json
import re
from typing import List, Dict, Optional
from functools import lru_cache


# ============================================================
# P2: REDDIT JSON SCRAPER (No auth required!)
# ============================================================

REDDIT_USER_AGENT = "ProductAI/1.0 (Multi-source product discovery)"

# Target subreddits for Indian market
REDDIT_SUBREDDITS = {
    "gaming": ["IndianGaming", "GamingLaptops", "SuggestALaptop"],
    "mobile": ["india", "mobilephones", "Android"],
    "audio": ["HeadphoneAdvice", "BudgetAudiophile"],
    "general": ["india", "IndianGaming"],
}


def search_reddit(query: str, subreddits: List[str] = None, limit: int = 10) -> List[Dict]:
    """
    Search Reddit using the /.json endpoint (no auth required!).
    
    Args:
        query: Search query
        subreddits: List of subreddits to search (default: IndianGaming, india)
        limit: Max posts per subreddit
        
    Returns:
        List of relevant posts with title, body, score, url
    """
    subreddits = subreddits or ["IndianGaming", "india"]
    all_posts = []
    
    headers = {"User-Agent": REDDIT_USER_AGENT}
    
    for subreddit in subreddits:
        try:
            # Use Reddit's JSON API
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {
                "q": query,
                "limit": limit,
                "sort": "relevance",
                "restrict_sr": "true",  # Restrict to this subreddit
                "t": "year",  # Last year only
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"  [Reddit] {subreddit}: HTTP {response.status_code}")
                continue
            
            data = response.json()
            posts = data.get("data", {}).get("children", [])
            
            for post in posts:
                post_data = post.get("data", {})
                score = post_data.get("score", 0)
                
                # Filter low-quality posts
                if score < 3:
                    continue
                
                all_posts.append({
                    "title": post_data.get("title", ""),
                    "body": post_data.get("selftext", "")[:1500],  # Truncate
                    "score": score,
                    "subreddit": subreddit,
                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    "num_comments": post_data.get("num_comments", 0),
                    "created_utc": post_data.get("created_utc", 0),
                })
            
            print(f"  [Reddit] r/{subreddit}: {len(posts)} posts found")
            
        except Exception as e:
            print(f"  [Reddit] r/{subreddit} error: {e}")
            continue
    
    # Sort by score
    all_posts.sort(key=lambda x: x["score"], reverse=True)
    return all_posts


def extract_products_from_reddit(posts: List[Dict], category: str = "laptop") -> List[Dict]:
    """
    Use LLM to extract product mentions from Reddit posts.
    
    Args:
        posts: List of Reddit posts
        category: Product category for context
        
    Returns:
        List of products mentioned with sentiment
    """
    if not posts:
        return []
    
    try:
        from config.llm_config import get_google_lite
        llm = get_google_lite()
    except Exception as e:
        print(f"  [Reddit] LLM unavailable: {e}")
        return []
    
    # Combine posts into context
    context = ""
    for post in posts[:5]:  # Limit to top 5 posts
        context += f"Title: {post['title']}\n"
        if post['body']:
            context += f"Content: {post['body'][:500]}\n"
        context += f"Score: {post['score']} upvotes\n\n"
    
    prompt = f"""Extract product recommendations from these Reddit discussions about {category}s.

Reddit Posts:
{context}

Return JSON array of products mentioned positively:
[
    {{"name": "Full Product Name", "sentiment": "positive/mixed/negative", "mentioned_in": "post title snippet", "reason": "why recommended"}}
]

Rules:
- Only include specific product models, not generic brands
- Focus on products recommended or praised
- Return empty array [] if no clear recommendations
- Return ONLY valid JSON"""

    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            products = json.loads(json_match.group(0))
            print(f"  [Reddit] Extracted {len(products)} product mentions")
            return products
    except Exception as e:
        print(f"  [Reddit] Extraction error: {e}")
    
    return []


# ============================================================
# P3: YOUTUBE TRANSCRIPT EXTRACTION
# ============================================================

def search_youtube_videos(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search YouTube for product-related videos.
    Uses web scraping of search results (no API key needed).
    
    Args:
        query: Search query (e.g., "best laptops under 80000 2024")
        max_results: Maximum videos to return
        
    Returns:
        List of video info dicts with video_id, title, channel
    """
    # Note: This is a simplified version. For production, consider:
    # 1. YouTube Data API v3 (requires API key)
    # 2. yt-dlp for more robust extraction
    
    try:
        from scraping import scrape_urls_sync_v2
        
        # Search URL
        search_url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
        
        # This is a placeholder - YouTube search scraping is complex
        # In practice, you'd use yt-dlp or the official API
        print(f"  [YouTube] Searching: {query}")
        
        # For now, return empty - requires more complex implementation
        # TODO: Implement with yt-dlp or YouTube Data API
        return []
        
    except Exception as e:
        print(f"  [YouTube] Search error: {e}")
        return []


def get_youtube_transcript(video_id: str) -> Optional[str]:
    """
    Get transcript for a YouTube video.
    
    Uses youtube_transcript_api library (no API key needed).
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Full transcript text or None
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Try to get transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Prefer manual transcripts, fall back to auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-IN', 'hi'])
        except:
            transcript = transcript_list.find_generated_transcript(['en', 'en-US'])
        
        # Combine all text
        full_text = " ".join([t['text'] for t in transcript.fetch()])
        print(f"  [YouTube] Transcript: {len(full_text)} chars")
        return full_text
        
    except ImportError:
        print("  [YouTube] youtube_transcript_api not installed. Run: pip install youtube-transcript-api")
        return None
    except Exception as e:
        print(f"  [YouTube] Transcript error: {e}")
        return None


def extract_products_from_transcript(transcript: str, video_title: str, category: str = "laptop") -> List[Dict]:
    """
    Use LLM to extract product mentions from video transcript.
    
    Args:
        transcript: Full video transcript
        video_title: Video title for context
        category: Product category
        
    Returns:
        List of products mentioned
    """
    if not transcript:
        return []
    
    try:
        from config.llm_config import get_google_lite
        llm = get_google_lite()
    except Exception as e:
        print(f"  [YouTube] LLM unavailable: {e}")
        return []
    
    # Truncate transcript
    transcript_chunk = transcript[:6000]
    
    prompt = f"""Extract product recommendations from this YouTube video transcript.

Video Title: {video_title}
Category: {category}

Transcript:
{transcript_chunk}

Return JSON array of products mentioned:
[
    {{"name": "Full Product Name", "rank": 1, "price_mentioned": 79999, "pros": "key benefits", "cons": "any negatives"}}
]

Rules:
- rank = order mentioned or ranked in video (1 = best/first)
- price_mentioned = approximate price if stated, null otherwise
- Extract ALL products discussed, not just the top pick
- Return ONLY valid JSON"""

    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            products = json.loads(json_match.group(0))
            print(f"  [YouTube] Extracted {len(products)} products from transcript")
            return products
    except Exception as e:
        print(f"  [YouTube] Extraction error: {e}")
    
    return []


# ============================================================
# P4: TARGETED E-COMMERCE PRICE LOOKUP
# ============================================================

def lookup_product_prices(products: List[Dict], max_per_product: int = 2) -> Dict[str, Dict]:
    """
    Search e-commerce sites for specific product prices.
    
    Args:
        products: List of discovered products with 'name' field
        max_per_product: Max URLs to check per product
        
    Returns:
        Dict mapping product name to {site: price} dict
    """
    from scraping import search_with_fallback, scrape_urls_sync_v2
    from extract.extruct_extract import extract_product_v2
    
    prices = {}
    
    for product in products[:7]:  # Limit to top 7
        product_name = product.get("name", "")
        if not product_name:
            continue
        
        print(f"\n  [PriceLookup] Searching: {product_name[:40]}...")
        
        product_prices = {}
        
        # Generate site-specific searches
        search_queries = [
            f'site:amazon.in "{product_name}"',
            f'site:flipkart.com "{product_name}"',
        ]
        
        for query in search_queries:
            try:
                # Search
                import asyncio
                results = asyncio.run(search_with_fallback(
                    query, 
                    query_type="site_search",
                    max_results=2
                ))
                
                if not results:
                    continue
                
                # Get first valid URL
                url = results[0].get("href") or results[0].get("url", "")
                if not url:
                    continue
                
                # Determine site
                site = "unknown"
                if "amazon" in url.lower():
                    site = "amazon"
                elif "flipkart" in url.lower():
                    site = "flipkart"
                
                # Scrape and extract price
                scraped = asyncio.run(scrape_urls_sync_v2([url]))
                if url in scraped and scraped[url]:
                    html = scraped[url].get("html", "")
                    extracted = extract_product_v2(html, url)
                    
                    if extracted and extracted.price:
                        product_prices[site] = {
                            "price": extracted.price,
                            "url": url,
                            "name": extracted.name,
                        }
                        print(f"    [{site}] ₹{extracted.price}")
                
            except Exception as e:
                print(f"    [PriceLookup] Error: {e}")
                continue
        
        if product_prices:
            prices[product_name] = product_prices
    
    return prices


# ============================================================
# COMBINED DISCOVERY FUNCTION
# ============================================================

def discover_from_all_sources(query: str, category: str, budget: int = None) -> Dict:
    """
    Run discovery across all sources: Reddit, YouTube, and spec sites.
    
    Args:
        query: User query
        category: Product category (laptop, phone, etc.)
        budget: Budget in INR
        
    Returns:
        Combined results from all sources
    """
    results = {
        "reddit": [],
        "youtube": [],
        "sources_used": [],
    }
    
    # Build search query
    search_query = f"best {category}"
    if budget:
        if budget >= 100000:
            search_query += f" under {budget // 100000} lakh"
        else:
            search_query += f" under {budget // 1000}k"
    
    # P2: Reddit
    try:
        subreddits = REDDIT_SUBREDDITS.get(category, REDDIT_SUBREDDITS["general"])
        posts = search_reddit(search_query, subreddits[:2], limit=5)
        if posts:
            reddit_products = extract_products_from_reddit(posts, category)
            results["reddit"] = reddit_products
            results["sources_used"].append("reddit")
    except Exception as e:
        print(f"  [Discovery] Reddit error: {e}")
    
    # P3: YouTube (if transcript API available)
    # TODO: Implement when YouTube search is ready
    
    return results
