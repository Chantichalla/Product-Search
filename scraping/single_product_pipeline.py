"""
Single Product Pipeline — The Ultimate E-Commerce Search & Scrape Engine

Self-contained, monolithic pipeline for deep product comparison.
No imports from concurrency.py — all execution logic is embedded here.

Pipeline:
    Product Identity → DDGS Multi-Engine Search (with jitter)
    → Product URL Filtering (Regex heuristics)
    → URL Deduplication
    → Crawl4AI Concurrent Scrape (Stealth + DOM Pruning)
    → fit_markdown / raw_markdown dict → Ready for Advisor LLM

Usage:
    from scraping.single_product_pipeline import execute_unified_product_pipeline

    result = asyncio.run(execute_unified_product_pipeline(
        product_identity="iPhone 15 Pro 256GB",
        brand_name="Apple",
    ))
    # result = {"product": "...", "results": {url: markdown, ...}}
"""

import asyncio
import random
import re
import logging
from difflib import SequenceMatcher
from typing import Dict, List, Set, Any, Optional, Tuple
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from ddgs import DDGS

from network import rate_limiter as default_limiter, get_random_user_agent

logger = logging.getLogger(__name__)


# ============================================================
# SECTION 1: INFRASTRUCTURE — Browser Config & Crawl Config
# ============================================================

def _build_browser_config() -> BrowserConfig:
    """Stealth-optimized browser config for e-commerce sites."""
    return BrowserConfig(
        headless=True,
        user_agent=get_random_user_agent(),
        user_agent_mode="random",
        viewport_width=1920,
        viewport_height=1080,
        enable_stealth=True,
        ignore_https_errors=True,
    )


def _build_ecommerce_run_config() -> CrawlerRunConfig:
    """
    Crawl4AI run config tuned for product pages.
    - CacheMode.BYPASS: Always fetch live prices
    - PruningContentFilter: Semantic noise removal
    - excluded_tags: Strip nav, footer, forms, sidebars
    """
    pruning_filter = PruningContentFilter(
        threshold=0.48,
        threshold_type="fixed",
        min_word_threshold=30,
    )
    markdown_generator = DefaultMarkdownGenerator(content_filter=pruning_filter)

    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=60000,
        word_count_threshold=10,
        excluded_tags=['form', 'header', 'footer', 'nav', 'script', 'style', 'aside'],
        markdown_generator=markdown_generator,
    )


# ============================================================
# SECTION 2: URL FILTERING — Regex Heuristics + Snippet Pre-Validation
# ============================================================

PRODUCT_URL_PATTERNS = {
    "amazon":   re.compile(r"/(dp|gp/product|exec/obidos/ASIN)/[A-Z0-9]{10}", re.IGNORECASE),
    "flipkart": re.compile(r"/p/itm[a-zA-Z0-9]+", re.IGNORECASE),
    "croma":    re.compile(r"/p/cp_[a-zA-Z0-9]+", re.IGNORECASE),
    "reliance": re.compile(r"/p/[0-9]+", re.IGNORECASE),
}

# Generic URL substrings that indicate non-product pages
_EXCLUSION_KEYWORDS = [
    "/blog", "/news", "/article", "/review", "/forum",
    "/support", "/help", "/faq", "/about", "/careers",
    "/best-", "/top-10", "/comparison", "/vs-",
]

# URL path signals for scoring
_URL_NEGATIVE_SIGNALS = [
    "/c/", "/category/", "/categories/", "/search?",
    "/blog-listing", "/brands/", "?page=", "/collection/",
]

# Accessory keywords — pages selling cases/covers/protectors, not the phone itself
_ACCESSORY_KEYWORDS = [
    "case", "cover", "protector", "screen guard", "tempered glass",
    "skin", "pouch", "holder", "stand", "charger", "cable", "adapter",
    "earphone", "earbuds", "back cover", "flip cover", "bumper",
]


def _extract_brand_token(product_name: str) -> Optional[str]:
    """
    Extract the likely brand name (first alphabetic word) from a product identity.
    E.g., 'iQOO 15' → 'iqoo', 'iPhone 15 Pro' → 'iphone', 'Samsung Galaxy S24' → 'samsung'
    Returns None if no alphabetic token found.
    """
    for token in product_name.lower().split():
        if token.isalpha() and len(token) > 1:
            return token
    return None


def _compute_relevance_score(product_name: str, title: str, body: str = "") -> float:
    """
    (P1) Fuzzy relevance scoring — how well does this search result match our query?

    Production-grade approach with 4 checks:
    1. Brand-token enforcement: Brand word MUST appear in title/body
    2. Token overlap: What fraction of product tokens appear?
    3. Short-name strictness: ≤3 token names require ALL tokens
    4. Accessory penalty: Detects case/cover/protector pages

    Returns a score from 0.0 (no match) to 1.0 (perfect match).
    """
    if not title:
        return 0.0

    product_lower = product_name.lower()
    title_lower = title.lower()
    body_lower = (body or "").lower()
    combined = f"{title_lower} {body_lower}"

    # ── Extract product tokens (skip single-char like 's') ──
    product_tokens = [t for t in product_lower.split() if len(t) > 1]
    if not product_tokens:
        return 0.0

    # ── CHECK 1: Brand-token enforcement ──
    # The brand (first alphabetic word) MUST appear somewhere in title or body.
    # This kills cross-brand collisions: "iqoo 15" won't match "iPhone 15"
    brand = _extract_brand_token(product_name)
    if brand and brand not in combined:
        return 0.0  # Hard reject — brand not even mentioned

    # ── CHECK 2: Token overlap ──
    tokens_found = sum(1 for t in product_tokens if t in combined)
    token_score = tokens_found / len(product_tokens)

    # ── CHECK 3: Short-name strictness ──
    # For products with ≤3 tokens (e.g., "iqoo 15", "iPhone 15 Pro"),
    # ALL tokens must appear. Otherwise "15" alone matches too many things.
    if len(product_tokens) <= 3 and tokens_found < len(product_tokens):
        # Not all tokens found → heavy penalty
        token_score *= 0.3

    # ── CHECK 4: Accessory detection ──
    # If the title mentions accessories (case, cover, protector), penalize
    is_accessory = any(kw in title_lower for kw in _ACCESSORY_KEYWORDS)
    accessory_penalty = 0.3 if is_accessory else 1.0

    # ── CHECK 5: URL path cross-check ──
    # If the product name tokens appear in the URL path, bonus confidence
    # (e.g., /iqoo-15-price vs /apple-iphone-15)
    # This is a lightweight signal, not decisive

    # ── SequenceMatcher for fuzzy similarity ──
    seq_score = SequenceMatcher(None, product_lower, title_lower).ratio()

    # ── Final weighted score ──
    raw_score = 0.7 * token_score + 0.3 * seq_score
    return raw_score * accessory_penalty


def _validate_search_results(
    results: List[Dict[str, Any]],
    product_identity: str,
    min_relevance: float = 0.35,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    (P0+P1) Snippet-level pre-validation of DDGS search results.

    Filters search results by checking title + body against the product name
    BEFORE scraping. This is FREE — we already have the data from DDGS.

    Key filters (production techniques):
    - Brand-token enforcement (kills cross-brand collisions)
    - Token overlap scoring (catches generic listing pages)
    - Accessory penalty (deprioritizes case/cover pages)
    - URL-signal penalty (catches category/search pages)

    Args:
        results: Raw DDGS results with 'title', 'body', 'href'.
        product_identity: The product we're searching for.
        min_relevance: Minimum fuzzy relevance score to pass (0.0-1.0).

    Returns:
        Tuple of (passed_results, rejected_results) with reason tags.
    """
    passed = []
    rejected = []

    brand = _extract_brand_token(product_identity)

    for r in results:
        if not isinstance(r, dict) or "href" not in r:
            continue

        title = r.get("title", "")
        body = r.get("body", "")
        url = r["href"]

        # Check for negative URL signals (category/listing pages)
        url_lower = url.lower()
        has_negative_signal = any(sig in url_lower for sig in _URL_NEGATIVE_SIGNALS)

        # Compute relevance score (includes brand check, token check, accessory check)
        score = _compute_relevance_score(product_identity, title, body)

        # Apply penalty for negative URL signals
        if has_negative_signal:
            score *= 0.5

        # Determine rejection reason for logging
        reason = ""
        if score == 0.0 and brand:
            combined = f"{title.lower()} {body.lower()}"
            if brand not in combined:
                reason = f"brand '{brand}' missing"
        elif score < min_relevance:
            reason = "low relevance"

        r["_relevance_score"] = round(score, 3)
        r["_reject_reason"] = reason

        if score >= min_relevance:
            passed.append(r)
        else:
            rejected.append(r)

    return passed, rejected


def is_valid_product_url(url: str) -> bool:
    """
    Heuristic check: is this URL likely an actual product page?

    Strategy:
    1. Reject URLs containing generic exclusion keywords.
    2. For known domains (Amazon, Flipkart, etc.), require strict regex match.
    3. For unknown domains (brand stores), allow through if no exclusion hit.
    """
    url_lower = url.lower()

    # Step 1: Generic exclusion
    if any(kw in url_lower for kw in _EXCLUSION_KEYWORDS):
        return False

    # Step 2: Domain-specific strict validation
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for site, pattern in PRODUCT_URL_PATTERNS.items():
        if site in domain:
            return bool(pattern.search(url))

    # Step 3: Unknown domain fallback (brand stores, Vijay Sales, etc.)
    return True


def _deduplicate_urls(raw_urls: List[str]) -> Set[str]:
    """Strip tracking params and deduplicate."""
    clean = set()
    for url in raw_urls:
        # Strip query params and Amazon ref tags
        base = url.split("?")[0].split("ref=")[0].rstrip("/")
        if is_valid_product_url(base):
            clean.add(base)
    return clean


# ============================================================
# SECTION 3: CONCURRENT SEARCH — DDGS with Jitter
# ============================================================

# Target e-commerce domains for India market (8 sites, 2 per backend)
DEFAULT_TARGET_SITES = [
    # Backend: google
    "amazon.in",
    "flipkart.com",
    # Backend: bing
    "reliancedigital.in",
    "croma.com",
    # Backend: brave
    "vijaysales.com",
    "gadgets360.com",
    # Backend: duckduckgo
    "smartprix.com",
    "mysmartprice.com",
]

# DDGS backends to cycle through for load distribution
_BACKENDS = ["brave", "duckduckgo", "yahoo", "mojeek"]

# Semaphore: raised to 8 for full parallel testing (2 per backend × 4 backends)
# Lazy-created to avoid binding to the wrong event loop
_search_semaphore = None
_search_semaphore_loop = None

def _get_search_semaphore() -> asyncio.Semaphore:
    """Get or recreate search semaphore for the current event loop."""
    global _search_semaphore, _search_semaphore_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    
    if _search_semaphore is None or current_loop is not _search_semaphore_loop:
        _search_semaphore = asyncio.Semaphore(8)
        _search_semaphore_loop = current_loop
    
    return _search_semaphore


async def _safe_ddg_search(
    query: str,
    backend: str = "auto",
    max_results: int = 4,
    jitter_range: tuple = (0.5, 1.5),
) -> List[Dict[str, Any]]:
    """
    Execute a single DDGS search with:
    - Semaphore throttle (max 8 concurrent for full parallel)
    - Jitter commented out for testing
    - Rate limiter slot (per-domain throttle)
    - Thread executor (DDGS is sync)
    """
    import time as _time
    async with _get_search_semaphore():
        # Jitter: COMMENTED OUT for parallel testing
        # await asyncio.sleep(random.uniform(*jitter_range))

        async with default_limiter.slot("duckduckgo.com"):
            t0 = _time.perf_counter()
            try:
                loop = asyncio.get_event_loop()

                def _search():
                    with DDGS() as ddg:
                        return list(ddg.text(
                            query,
                            max_results=max_results,
                            backend=backend,
                        ))

                results = await loop.run_in_executor(None, _search)
                elapsed = _time.perf_counter() - t0

                # Detailed per-search logging
                urls_found = [r.get("href", "?") for r in results if isinstance(r, dict)]
                print(f"  🔍 [{backend:>10}] '{query[:50]}' → {len(results)} results in {elapsed:.2f}s")
                for u in urls_found:
                    print(f"       ↳ {u}")

                return results or []

            except Exception as e:
                elapsed = _time.perf_counter() - t0
                print(f"  ❌ [{backend:>10}] '{query[:50]}' → ERROR in {elapsed:.2f}s: {e}")
                return []


async def _search_all_stores(
    product_identity: str,
    target_sites: List[str],
    max_results_per_site: int = 4,
) -> List[str]:
    """
    Fire targeted site: searches + open searches concurrently.
    Cycles DDGS backends to distribute load (2 sites per backend).

    Now includes:
    - P0+P1 snippet-level pre-validation on all results
    - Open (non-site-restricted) searches for broader coverage
    """
    import time as _time
    t_start = _time.perf_counter()

    tasks = []
    task_labels = []
    print(f"\n{'='*60}")
    print(f"🚀 LAUNCHING PARALLEL SEARCHES (no jitter)")
    print(f"{'='*60}")

    # ── Targeted site: searches ──
    for i, site in enumerate(target_sites):
        query = f"site:{site} {product_identity}"
        backend = _BACKENDS[i % len(_BACKENDS)]
        print(f"  #{i+1} [{backend:>10}] → site:{site}")
        tasks.append(_safe_ddg_search(query, backend=backend, max_results=max_results_per_site))
        task_labels.append(site)

    # ── Open (non-site-restricted) searches for broader coverage ──
    # These catch the most relevant pages across the entire web
    open_queries = [
        (f"{product_identity} price buy India", "google"),
        (f"{product_identity} specs review", "bing"),
    ]
    for oq, ob in open_queries:
        print(f"  #OPEN [{ob:>10}] → '{oq[:50]}'")
        tasks.append(_safe_ddg_search(oq, backend=ob, max_results=4))
        task_labels.append(f"OPEN:{ob}")

    print(f"{'─'*60}")
    all_results = await asyncio.gather(*tasks)

    # ── P0+P1: Snippet pre-validation on each result set ──
    raw_urls = []
    per_site_counts = []
    total_rejected = 0

    for i, result_list in enumerate(all_results):
        # Apply snippet filter BEFORE collecting URLs
        passed, rejected = _validate_search_results(result_list, product_identity)
        total_rejected += len(rejected)

        site_urls = []
        for r in passed:
            site_urls.append(r["href"])
            raw_urls.append(r["href"])

        per_site_counts.append((task_labels[i], len(site_urls), len(rejected)))

        # Log rejected URLs with reason
        for r in rejected:
            score = r.get("_relevance_score", 0)
            reason = r.get("_reject_reason", "")
            reason_tag = f" [{reason}]" if reason else ""
            print(f"       ✖ REJECTED (score={score:.2f}{reason_tag}): {r.get('title', '?')[:60]}")
            print(f"         URL: {r.get('href', '?')[:80]}")

    t_total = _time.perf_counter() - t_start
    print(f"{'─'*60}")
    print(f"📊 SEARCH SUMMARY (total: {t_total:.2f}s)")
    for site, count, rej in per_site_counts:
        rej_str = f" (rejected {rej})" if rej > 0 else ""
        print(f"   {site:>25}: {count} URLs{rej_str}")
    print(f"   {'TOTAL':>25}: {len(raw_urls)} passed, {total_rejected} rejected")
    print(f"{'='*60}\n")

    return raw_urls


# ============================================================
# SECTION 4: CONCURRENT SCRAPING — Crawl4AI with Stealth
# ============================================================

# Manual pruning regex patterns (fallback if fit_markdown fails)
_NOISE_PATTERNS = [
    r'\[Skip to.*?\]',
    r'\[Sign in\].*?(?=\n|$)',
    r'!\[.*?\]\(.*?\)',           # Image markdown
    r'\*\s*\[.*?\]\(.*?\)\s*',   # Navigation links
    r'^\s*[-•]\s*[A-Za-z ]{3,20}\s*$',  # Simple nav items
    r'Cookie.*?(?=\n|$)',
    r'Accept.*?(?=\n|$)',
]


def _manual_prune(raw_md: str) -> str:
    """
    Fallback pruning when Crawl4AI's semantic PruningContentFilter
    returns empty or too-short fit_markdown.
    """
    pruned = raw_md
    for pattern in _NOISE_PATTERNS:
        try:
            pruned = re.sub(pattern, '', pruned, flags=re.IGNORECASE | re.MULTILINE)
        except Exception:
            pass

    # Collapse excessive whitespace
    pruned = re.sub(r'\n{3,}', '\n\n', pruned)

    # Hard cap at 15k chars
    if len(pruned) > 15000:
        pruned = pruned[:15000]

    return pruned


async def _scrape_product_pages(
    urls: List[str],
    timeout: float = 25.0,
    max_concurrent: int = 5,
) -> Dict[str, Dict[str, Any]]:
    """
    Scrape validated product URLs using a shared Crawl4AI session.

    Features ported from concurrency.py:
    - Shared AsyncWebCrawler (one browser for all URLs)
    - Semaphore-controlled concurrency
    - Per-domain rate limiting
    - fit_markdown extraction with manual pruning fallback
    - Error categorization (BLOCKED, TIMEOUT, SSL, 404)
    """
    if not urls:
        return {}

    browser_config = _build_browser_config()
    run_config = _build_ecommerce_run_config()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _scrape_single(url: str, crawler: AsyncWebCrawler) -> Dict[str, Any]:
        async with semaphore:
            async with default_limiter.slot(url):
                try:
                    result = await asyncio.wait_for(
                        crawler.arun(url=url, config=run_config),
                        timeout=timeout,
                    )

                    # ── Extract raw_markdown ──
                    raw_md = ""
                    if hasattr(result, 'markdown'):
                        if isinstance(result.markdown, str):
                            raw_md = result.markdown
                        elif hasattr(result.markdown, 'raw_markdown'):
                            raw_md = result.markdown.raw_markdown

                    # ── Extract fit_markdown ──
                    fit_md = ""
                    if hasattr(result, 'markdown') and hasattr(result.markdown, 'fit_markdown'):
                        fit_md = result.markdown.fit_markdown or ""
                    if not fit_md and hasattr(result, 'markdown_v2') and hasattr(result.markdown_v2, 'fit_markdown'):
                        fit_md = result.markdown_v2.fit_markdown or ""
                    if not fit_md and hasattr(result, 'fit_markdown'):
                        fit_md = result.fit_markdown or ""

                    # ── Manual Pruning Fallback ──
                    if (not fit_md or len(fit_md) < 500) and raw_md and len(raw_md) > 1000:
                        logger.info(f"  [Prune] fit_markdown empty/short, applying manual pruning for {url[:40]}...")
                        fit_md = _manual_prune(raw_md)
                        reduction = 100 - int(len(fit_md) / len(raw_md) * 100)
                        logger.info(f"  [Prune] {len(raw_md)} → {len(fit_md)} chars ({reduction}% reduction)")

                    # ── Final Fallback ──
                    if not fit_md or len(fit_md) < 500:
                        logger.info(f"  [Prune] fit_markdown too short ({len(fit_md)}), using raw for {url[:40]}...")
                        fit_md = raw_md

                    logger.info(f"  [Scraped] {url[:50]}... Raw: {len(raw_md)} | Fit: {len(fit_md)}")

                    return {
                        "url": url,
                        "markdown": fit_md,
                        "raw_markdown": raw_md,
                        "fit_markdown": fit_md,
                        "error": None,
                        "success": True,
                    }

                except asyncio.TimeoutError:
                    logger.warning(f"  [TIMEOUT] {url[:50]}... after {timeout}s")
                    return {"url": url, "markdown": None, "error": f"timeout after {timeout}s", "success": False}

                except Exception as e:
                    error_msg = str(e)[:150]
                    if "blocked" in error_msg.lower() or "403" in error_msg:
                        cat = "BLOCKED (anti-bot)"
                    elif "connection" in error_msg.lower():
                        cat = "CONNECTION ERROR"
                    elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                        cat = "SSL ERROR"
                    elif "404" in error_msg:
                        cat = "PAGE NOT FOUND"
                    else:
                        cat = type(e).__name__

                    logger.warning(f"  [ERROR] {url[:50]}... {cat}: {error_msg[:80]}")
                    return {"url": url, "markdown": None, "error": f"{cat}: {error_msg}", "success": False}

    # ── ONE shared crawler instance ──
    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [_scrape_single(url, crawler) for url in urls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert to dict
    results = {}
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            results[urls[i]] = {"markdown": None, "error": str(result)[:100], "success": False}
        else:
            results[result["url"]] = {
                "markdown": result.get("markdown"),
                "fit_markdown": result.get("fit_markdown"),
                "raw_markdown": result.get("raw_markdown"),
                "error": result.get("error"),
                "success": result.get("success", False),
            }

    return results


# ============================================================
# SECTION 5: THE ORCHESTRATOR
# ============================================================

async def execute_unified_product_pipeline(
    product_identity: str,
    brand_name: str = "",
    target_sites: Optional[List[str]] = None,
    scrape_timeout: float = 25.0,
    max_concurrent_scrapes: int = 5,
) -> Dict[str, Any]:
    """
    The full pipeline: Search → Filter → Deduplicate → Scrape.

    Args:
        product_identity: Normalized product name (e.g., "iPhone 15 Pro 256GB").
        brand_name: Optional brand to add the official store (e.g., "Apple" → apple.com).
        target_sites: Override default target sites list.
        scrape_timeout: Per-URL scrape timeout in seconds.
        max_concurrent_scrapes: Max parallel Crawl4AI scrapes.

    Returns:
        Dict with "product", "results" (url→markdown), and metadata.
    """
    logger.info(f"═══ Pipeline Start: {product_identity} ═══")

    # ── 1. Build target site list (NO hardcoded brand domains) ──
    sites = list(target_sites or DEFAULT_TARGET_SITES)
    logger.info(f"  Targeting {len(sites)} stores: {sites}")

    # ── 2. Concurrent Search (includes P0+P1 snippet pre-validation) ──
    raw_urls = await _search_all_stores(product_identity, target_sites=sites)

    # ── 2b. (P2) Dynamic Official Store Discovery ──
    if brand_name:
        print(f"\n🏪 Searching for {brand_name} official store...")
        official_query = f"{product_identity} official store buy India"
        official_results = await _safe_ddg_search(
            official_query, backend="google", max_results=3
        )
        for r in official_results:
            if isinstance(r, dict) and "href" in r:
                url = r["href"]
                # Only add if it's NOT already from our target sites
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
                already_covered = any(site in domain for site in sites)
                if not already_covered:
                    score = _compute_relevance_score(product_identity, r.get("title", ""), r.get("body", ""))
                    if score >= 0.35:
                        print(f"  🏪 Official store found: {url[:80]} (score={score:.2f})")
                        raw_urls.append(url)
                    else:
                        print(f"  ✖ Official store rejected (score={score:.2f}): {r.get('title', '')[:60]}")

    if not raw_urls:
        logger.warning("  No URLs returned from search phase.")
        return {"product": product_identity, "results": {}, "error": "No search results"}

    # ── 3. Filter & Deduplicate ──
    valid_urls = _deduplicate_urls(raw_urls)
    logger.info(f"  {len(raw_urls)} raw → {len(valid_urls)} valid product URLs after filtering.")

    if not valid_urls:
        return {"product": product_identity, "results": {}, "error": "No valid product URLs after filtering"}

    # ── 3b. Rerank URLs by relevance to product identity ──
    # Uses Jina API (primary, free) or local ONNX cross-encoder (fallback).
    # Keeps top 7 — enough for 3-4 store prices + 2-3 spec/review pages.
    urls_to_scrape = list(valid_urls)
    try:
        from config.onnx_reranker import rerank as _rerank
        # Build passage list: title + URL domain (gives reranker more signal)
        passages = [urlparse(u).netloc.replace("www.", "") + " " + u for u in urls_to_scrape]
        ranked = _rerank(query=product_identity, passages=passages, top_n=7)
        # Map ranked passages back to original URLs
        reranked_urls = [urls_to_scrape[r["index"]] for r in ranked if r["index"] < len(urls_to_scrape)]
        if reranked_urls:
            print(f"  [Reranker] ✅ {len(urls_to_scrape)} → top {len(reranked_urls)} URLs selected")
            for r in ranked:
                idx = r["index"]
                if idx < len(urls_to_scrape):
                    print(f"    score={r['score']:.3f} → {urls_to_scrape[idx][:80]}")
            urls_to_scrape = reranked_urls
        else:
            print("  [Reranker] ⚠️ Reranker returned empty, using all valid URLs")
    except Exception as e:
        print(f"  [Reranker] ⚠️ Skipped ({e}), scraping all {len(urls_to_scrape)} URLs")

    # ── 4. Concurrent Scrape ──
    scrape_results = await _scrape_product_pages(
        urls_to_scrape,
        timeout=scrape_timeout,
        max_concurrent=max_concurrent_scrapes,
    )

    # ── 5. Extract successful markdowns ──
    successful = {}
    for url, data in scrape_results.items():
        if data.get("success") and data.get("markdown"):
            successful[url] = data["markdown"]

    logger.info(f"  {len(successful)}/{len(valid_urls)} pages scraped successfully.")
    logger.info(f"═══ Pipeline Complete: {product_identity} ═══")

    return {
        "product": product_identity,
        "results": successful,
        "total_searched": len(raw_urls),
        "total_filtered": len(valid_urls),
        "total_scraped": len(successful),
    }


# ── Convenience sync wrapper ──
def execute_pipeline_sync(product_identity: str, **kwargs) -> Dict[str, Any]:
    """Sync wrapper for execute_unified_product_pipeline."""
    return asyncio.run(execute_unified_product_pipeline(product_identity, **kwargs))


# ── Local testing entrypoint ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    test_identity = "iPhone 15 Pro 256GB Natural Titanium"
    result = asyncio.run(execute_unified_product_pipeline(test_identity, brand_name="Apple"))
    print(f"\n✅ Pipeline complete. Scraped {result.get('total_scraped', 0)} product pages.")
    for url in result.get("results", {}):
        print(f"  → {url[:70]}...")
