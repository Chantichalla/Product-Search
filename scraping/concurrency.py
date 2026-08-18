"""
Concurrent Scraping Utilities

Provides async functions for batch web scraping and search with:
- Shared AsyncWebCrawler per batch (efficient)
- Per-domain rate limiting via RateLimiter
- Pure async (no asyncio.run inside - caller decides execution)

Usage:
    results = await scrape_urls_concurrent(
        urls=["https://amazon.in/dp/123", "https://flipkart.com/product"],
        browser_config=browser_config,
        run_config=run_config,
        limiter=rate_limiter,
    )
"""

import asyncio
from typing import Dict, List, Optional, Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from ddgs import DDGS

from network import rate_limiter as default_limiter, get_random_user_agent
import requests
import re
try:
    from bs4 import BeautifulSoup
    import trafilatura
except ImportError:
    pass


async def scrape_urls_concurrent(
    urls: List[str],
    *,
    browser_config: Optional[BrowserConfig] = None,
    run_config: Optional[CrawlerRunConfig] = None,
    limiter = None,
    timeout: float = 25.0,
) -> Dict[str, Dict[str, Any]]:
    """
    Scrape multiple URLs concurrently with a shared crawler.
    
    Args:
        urls: List of URLs to scrape
        browser_config: Optional crawl4ai browser config (defaults provided)
        run_config: Optional crawl4ai run config (defaults provided)
        limiter: RateLimiter instance (defaults to global rate_limiter)
        timeout: Timeout per URL in seconds
    
    Returns:
        Dict mapping url -> {"markdown": str | None, "error": str | None}
    
    Example:
        results = await scrape_urls_concurrent(
            urls=product_urls,
            limiter=rate_limiter,
        )
        for url, data in results.items():
            if data["error"]:
                print(f"Failed: {url} - {data['error']}")
            else:
                process_markdown(data["markdown"])
    """
    if limiter is None:
        limiter = default_limiter
    
    # Default configs if not provided
    if browser_config is None:
        browser_config = BrowserConfig(
            headless=True,
            # === ANTI-DETECTION FEATURES ===
            user_agent=get_random_user_agent(),
            user_agent_mode="random",          # Rotate user agents
            viewport_width=1920,               # Desktop viewport
            viewport_height=1080,
            enable_stealth=True,               # Stealth mode - hide automation
            ignore_https_errors=True,          # Don't fail on bad certs
        )
    
    if run_config is None:
        run_config = CrawlerRunConfig(
            wait_until="networkidle",          # Wait for network to settle
            page_timeout=45000,                # Increase from 20s to 45s
            delay_before_return_html=2.0,      # Wait 2s after page load
            magic=True,                        # Enable all anti-detection
            simulate_user=True,                # Human-like mouse/scroll
            override_navigator=True,           # Hide webdriver flag
        )
    
    async def _scrape_single(url: str, crawler: AsyncWebCrawler) -> Dict[str, Any]:
        """Scrape a single URL with rate limiting."""
        async with limiter.slot(url):
            try:
                result = await asyncio.wait_for(
                    crawler.arun(url=url, config=run_config),
                    timeout=timeout
                )
                return {
                    "url": url,
                    "markdown": result.markdown,
                    "error": None,
                }
            except asyncio.TimeoutError:
                return {"url": url, "markdown": None, "error": "timeout"}
            except Exception as e:
                return {"url": url, "markdown": None, "error": str(e)[:100]}
    
    # Use shared crawler for all URLs
    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [_scrape_single(url, crawler) for url in urls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert to dict
    results = {}
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            results[urls[i]] = {"markdown": None, "error": str(result)[:100]}
        else:
            results[result["url"]] = {
                "markdown": result["markdown"],
                "error": result["error"],
            }
    
    return results


async def ddg_search_concurrent(
    queries: List[str],
    *,
    max_results: int = 5,
    backend: str = "auto",
    limiter = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Perform multiple DuckDuckGo searches concurrently.
    
    Args:
        queries: List of search queries
        max_results: Results per query
        backend: Search backend - "auto", "google", "bing", "brave", "duckduckgo" or comma-separated
        limiter: RateLimiter instance (defaults to global rate_limiter)
    
    Returns:
        Dict mapping query -> list of search results
    
    Example:
        results = await ddg_search_concurrent(
            queries=["laptop under 50k", "iphone 15 price"],
            max_results=5,
            backend="google",
        )
    """
    if limiter is None:
        limiter = default_limiter
    
    async def _search_single(query: str) -> Dict[str, Any]:
        """Search a single query with rate limiting."""
        async with limiter.slot("duckduckgo.com"):
            try:
                # DDG is sync, run in executor
                loop = asyncio.get_event_loop()
                def _search():
                    with DDGS() as ddg:
                        return list(ddg.text(query, max_results=max_results, backend=backend))
                results = await loop.run_in_executor(None, _search)
                return {"query": query, "results": results, "error": None}
            except Exception as e:
                return {"query": query, "results": [], "error": str(e)[:50]}
    
    tasks = [_search_single(q) for q in queries]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert to dict
    output = {}
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            output[queries[i]] = []
        else:
            output[result["query"]] = result["results"]
    
    return output


# Engine priority for different query types
ENGINE_PRIORITY = {
    "site_search": ["google", "brave", "bing"],  # Google best for site: operators
    "general": ["brave", "duckduckgo", "bing"],   # Brave has independent index
}


async def search_with_fallback(
    query: str,
    *,
    query_type: str = "general",
    max_results: int = 5,
    limiter = None,
) -> List[Dict[str, Any]]:
    """
    Search with engine fallback for reliability.
    
    Args:
        query: Search query
        query_type: "site_search" for site: queries, "general" otherwise
        max_results: Max results to return
        limiter: RateLimiter instance
    
    Returns:
        List of search results from first successful engine
    """
    if limiter is None:
        limiter = default_limiter
    
    engines = ENGINE_PRIORITY.get(query_type, ENGINE_PRIORITY["general"])
    
    for engine in engines:
        try:
            async with limiter.slot("duckduckgo.com"):
                loop = asyncio.get_event_loop()
                def _search():
                    with DDGS() as ddg:
                        return list(ddg.text(query, max_results=max_results, backend=engine))
                results = await loop.run_in_executor(None, _search)
                if results:
                    return results
        except Exception as e:
            print(f"[Search] Engine {engine} failed for '{query[:30]}...': {e}")
            continue
    
    return []  # All engines failed


# ============================================================
# ENHANCED SCRAPING (V2) - Using Crawl4AI Best Practices
# ============================================================

async def scrape_urls_concurrent_v2(
    urls: List[str],
    *,
    browser_config: Optional[BrowserConfig] = None,
    run_config: Optional[CrawlerRunConfig] = None,
    use_fit_markdown: bool = True,
    max_concurrent: int = 5,
    timeout: float = 30.0,
) -> Dict[str, Dict[str, Any]]:
    """
    Enhanced scraping with Crawl4AI best practices.
    
    Improvements over v1:
    - Uses fit_markdown for ~80% token reduction
    - Better memory management with semaphore
    - Individual parallel calls (not batched)
    
    Args:
        urls: List of URLs to scrape
        browser_config: Optional browser config
        run_config: Optional run config
        use_fit_markdown: Use pruned markdown (default True)
        max_concurrent: Max parallel scrapes
        timeout: Timeout per URL
        
    Returns:
        Dict mapping url -> {"markdown": str, "fit_markdown": str, "error": str | None}
    """
    if not urls:
        return {}
    
    # Default configs
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter

    # ============================================================
    # SIMPLE CONFIG (like langgraph - faster, less overhead)
    # ============================================================
    if browser_config is None:
        browser_config = BrowserConfig(
            headless=True,
            # Minimal config - let Crawl4AI use defaults
        )
    
    if run_config is None:
        # Enable PruningContentFilter to generate fit_markdown
        pruning_filter = PruningContentFilter(
            threshold=0.48,  # Higher threshold = more aggressive pruning
            threshold_type="fixed", 
            min_word_threshold=30  # Keep blocks with at least 30 words
        )
        markdown_generator = DefaultMarkdownGenerator(content_filter=pruning_filter)
        
        run_config = CrawlerRunConfig(
            page_timeout=60000,  # 60s timeout
            markdown_generator=markdown_generator,  # Enable fit_markdown generation
        )
    
    # ============================================================
    # COMPLEX CONFIG (commented out - use if sites block simple config)
    # ============================================================
    # if browser_config is None:
    #     browser_config = BrowserConfig(
    #         headless=True,
    #         user_agent=get_random_user_agent(),
    #         user_agent_mode="random",
    #         viewport_width=1920,
    #         viewport_height=1080,
    #         enable_stealth=True,
    #         ignore_https_errors=True,
    #     )
    # 
    # if run_config is None:
    #     pruning_filter = PruningContentFilter(
    #         threshold=0.45, 
    #         threshold_type="fixed", 
    #         min_word_threshold=50
    #     )
    #     markdown_generator = DefaultMarkdownGenerator(content_filter=pruning_filter)
    #     
    #     run_config = CrawlerRunConfig(
    #         wait_until="networkidle",
    #         page_timeout=60000,
    #         delay_before_return_html=2.0,
    #         markdown_generator=markdown_generator,
    #         magic=True,
    #         simulate_user=True,
    #         override_navigator=True,
    #     )
    
    # Semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def _scrape_single(url: str, crawler: AsyncWebCrawler) -> Dict[str, Any]:
        """Scrape a single URL with rate limiting and concurrency control."""
        async with semaphore:
            # Apply rate limiting
            async with default_limiter.slot(url):
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=timeout
                    )
                    
                    # Extract both raw and fit markdown
                    # Crawl4AI 0.7.x stores markdown in different locations based on version
                    raw_md = ""
                    fit_md = ""
                    
                    # Try different attribute paths for raw markdown
                    if hasattr(result, 'markdown'):
                        if isinstance(result.markdown, str):
                            raw_md = result.markdown
                        elif hasattr(result.markdown, 'raw_markdown'):
                            raw_md = result.markdown.raw_markdown
                    
                    # Try different attribute paths for fit_markdown
                    # Crawl4AI 0.7.x: result.markdown.fit_markdown or result.markdown_v2.fit_markdown
                    if hasattr(result, 'markdown'):
                        if hasattr(result.markdown, 'fit_markdown'):
                            fit_md = result.markdown.fit_markdown or ""
                    if not fit_md and hasattr(result, 'markdown_v2'):
                        if hasattr(result.markdown_v2, 'fit_markdown'):
                            fit_md = result.markdown_v2.fit_markdown or ""
                    if not fit_md and hasattr(result, 'fit_markdown'):
                        fit_md = result.fit_markdown or ""
                    
                    # MANUAL PRUNING FALLBACK: If fit_markdown is empty, create our own
                    if (not fit_md or len(fit_md) < 500) and raw_md and len(raw_md) > 1000:
                        print(f"  [Debug] fit_markdown empty, applying manual pruning for {url[:30]}...")
                        # Simple pruning: Remove navigation, scripts, and keep product-relevant sections
                        import re
                        pruned = raw_md
                        
                        # Remove common noise patterns
                        noise_patterns = [
                            r'\[Skip to.*?\]',
                            r'\[Sign in\].*?(?=\n|$)',
                            r'!\[.*?\]\(.*?\)',  # Image markdown
                            r'\*\s*\[.*?\]\(.*?\)\s*',  # Navigation links
                            r'^\s*[-•]\s*[A-Za-z ]{3,20}\s*$',  # Simple nav items
                            r'Cookie.*?(?=\n|$)',
                            r'Accept.*?(?=\n|$)',
                        ]
                        for pattern in noise_patterns:
                            try:
                                pruned = re.sub(pattern, '', pruned, flags=re.IGNORECASE | re.MULTILINE)
                            except:
                                pass
                        
                        # Remove excess whitespace
                        pruned = re.sub(r'\n{3,}', '\n\n', pruned)
                        
                        # Truncate to reasonable size
                        if len(pruned) > 15000:
                            pruned = pruned[:15000]
                        
                        fit_md = pruned
                        print(f"  [Debug] Manual pruning: {len(raw_md)} -> {len(fit_md)} chars ({100-int(len(fit_md)/len(raw_md)*100)}% reduction)")
                    
                    # Final fallback to raw
                    if not fit_md or len(fit_md) < 500:
                        print(f"  [Debug] Fit markdown too short ({len(fit_md)}), using raw for {url[:30]}...")
                        fit_md = raw_md
                    
                    print(f"  [Debug] {url[:40]}... Raw: {len(str(raw_md))} chars, Fit: {len(str(fit_md))} chars")

                    # Get raw HTML for extraction (JSON-LD, CSS selectors need HTML)
                    raw_html = result.html if hasattr(result, 'html') else ""

                    return {
                        "url": url,
                        "html": raw_html,  # NEW: Raw HTML for JSON-LD/CSS extraction
                        "markdown": fit_md if use_fit_markdown else raw_md,
                        "raw_markdown": raw_md,
                        "fit_markdown": fit_md,
                        "error": None,
                        "success": True,
                    }
                    
                except asyncio.TimeoutError:
                    print(f"  [SCRAPE ERROR] {url[:40]}... TIMEOUT after {timeout}s")
                    return {
                        "url": url,
                        "markdown": None,
                        "error": f"timeout after {timeout}s",
                        "success": False,
                    }
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)[:150]
                    
                    # Categorize common errors
                    if "blocked" in error_msg.lower() or "403" in error_msg:
                        error_category = "BLOCKED (anti-bot)"
                    elif "connection" in error_msg.lower():
                        error_category = "CONNECTION ERROR"
                    elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                        error_category = "SSL ERROR"
                    elif "404" in error_msg:
                        error_category = "PAGE NOT FOUND"
                    else:
                        error_category = error_type
                    
                    print(f"  [SCRAPE ERROR] {url[:40]}... {error_category}: {error_msg[:80]}")
                    return {
                        "url": url,
                        "markdown": None,
                        "error": f"{error_category}: {error_msg}",
                        "success": False,
                    }
    
    # Use shared crawler for all URLs
    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [_scrape_single(url, crawler) for url in urls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert to dict
    results = {}
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            results[urls[i]] = {
                "markdown": None,
                "error": str(result)[:100],
                "success": False,
            }
        else:
            results[result["url"]] = {
                "markdown": result.get("markdown"),
                "fit_markdown": result.get("fit_markdown"),
                "raw_markdown": result.get("raw_markdown"),
                "error": result.get("error"),
                "success": result.get("success", False),
            }
    
    return results


# Convenience sync wrappers for simple use cases
def scrape_urls_sync(urls: List[str], **kwargs) -> Dict[str, Dict[str, Any]]:
    """Sync wrapper for scrape_urls_concurrent."""
    return asyncio.run(scrape_urls_concurrent(urls, **kwargs))


def scrape_urls_sync_v2(urls: List[str], **kwargs) -> Dict[str, Dict[str, Any]]:
    """Sync wrapper for scrape_urls_concurrent_v2."""
    return asyncio.run(scrape_urls_concurrent_v2(urls, **kwargs))


# ============================================================
# SCRAPING CASCADE (V3) - Journalism Deep Reader Strategy
# ============================================================

async def scrape_urls_cascade_v3(
    urls: List[str],
    *,
    timeout: float = 30.0,
    max_concurrent: int = 4
) -> Dict[str, Dict[str, Any]]:
    """
    Implements a 3-Tier Scraping Cascade:
    Tier 1: Trafilatura (Ultra-fast, ~200ms, pure HTTP text extraction)
    Tier 2: Requests + BeautifulSoup (Fast, ~500ms, handles some non-standard pages)
    Tier 3: Crawl4AI (Heavy, ~4000ms, handles JS-rendered and anti-bot protected pages)
    """
    results_map = {}
    heavy_urls = []
    
    # Tier 1 & 2 logic (Fast path)
    import concurrent.futures
    loop = asyncio.get_event_loop()
    
    def _fast_scrape(url: str) -> dict:
        result_data = {"markdown": None, "fit_markdown": None, "error": None, "success": False, "method": None}
        try:
            # ── Tier 1: Trafilatura ──
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                content = trafilatura.extract(
                    downloaded, include_comments=False, include_tables=True, favor_recall=True
                )
                if content and len(content) > 300:
                    result_data["markdown"] = content
                    result_data["fit_markdown"] = content
                    result_data["success"] = True
                    result_data["method"] = "trafilatura"
                    print(f"  [Cascade] ⚡ Tier-1 Success (Trafilatura): {url[:40]}... ({len(content)} chars)")
                    return result_data
            
            # ── Tier 2: Requests + BS4 ──
            headers = {
                'User-Agent': get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            if "Just a moment..." in response.text or "cloudflare" in response.text.lower() or "captcha" in response.text.lower():
                raise ValueError("Cloudflare/Captcha detected")
                
            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'header']):
                element.decompose()
            
            main = soup.find('main') or soup.find('article') or soup.find('body')
            content = main.get_text(separator='\n', strip=True) if main else ''
            
            if content and len(content) > 300:
                result_data["markdown"] = content
                result_data["fit_markdown"] = content
                result_data["success"] = True
                result_data["method"] = "bs4"
                print(f"  [Cascade] 🚀 Tier-2 Success (BS4): {url[:40]}... ({len(content)} chars)")
                return result_data
                
            raise ValueError("Insufficient content extracted")
            
        except Exception as e:
            return result_data

    # Execute fast path
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = {pool.submit(_fast_scrape, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                res = future.result()
                if res["success"]:
                    results_map[url] = res
                else:
                    heavy_urls.append(url)
            except:
                heavy_urls.append(url)

    # ── Tier 3: Crawl4AI ──
    if heavy_urls:
        print(f"  [Cascade] 🐢 Falling back to Tier-3 (Crawl4AI) for {len(heavy_urls)} URLs...")
        heavy_results = await scrape_urls_concurrent_v2(
            urls=heavy_urls,
            max_concurrent=max_concurrent,
            timeout=timeout
        )
        for url, data in heavy_results.items():
            if data.get("success"):
                data["method"] = "crawl4ai"
                results_map[url] = data
            else:
                results_map[url] = data

    return results_map


# ============================================================
# RESEARCH ORCHESTRATOR
# ============================================================

async def research_extra_info(query: str, max_urls: int = 5) -> Dict[str, Dict[str, Any]]:
    """
    Standalone Research Tool:
    1. Search for information (DDGS/Free)
    2. Deep-scrape results using the Cascade
    3. Return consolidated information
    """
    print(f"  [Research] 🧠 Deep Researching: '{query}'")
    
    # 1. Search for URLs
    results = await search_with_fallback(query, max_results=max_urls)
    urls = [r["href"] for r in results if r.get("href")]
    
    if not urls:
        print("  [Research] No URLs found")
        return {}
        
    # 2. Scrape them using the Cascade (Fast -> Slow)
    scraped_data = await scrape_urls_cascade_v3(urls)
    
    # 3. Add original metadata (title/snippet) back to result
    output = {}
    for r in results:
        url = r.get("href")
        if url in scraped_data:
            data = scraped_data[url]
            data["title"] = r.get("title", data.get("title", "Article"))
            data["snippet"] = r.get("body", "")
            output[url] = data
            
    return output


def research_extra_info_sync(query: str, **kwargs) -> Dict[str, Dict[str, Any]]:
    """Sync wrapper for research_extra_info."""
    return asyncio.run(research_extra_info(query, **kwargs))


def scrape_urls_cascade_sync_v3(urls: List[str], **kwargs) -> Dict[str, Dict[str, Any]]:
    """Sync wrapper for scrape_urls_cascade_v3."""
    return asyncio.run(scrape_urls_cascade_v3(urls, **kwargs))


def ddg_search_sync(queries: List[str], **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """Sync wrapper for ddg_search_concurrent."""
    return asyncio.run(ddg_search_concurrent(queries, **kwargs))
