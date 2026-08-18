"""
Price History Scraper — Lightweight httpx + DDGS pipeline

Extracts price history data from pricehistory.app using:
  1. DDGS search (brave backend, duckduckgo fallback) to find the product URL
  2. httpx GET to fetch raw HTML (no browser needed)
  3. Regex to parse prices from <meta> OG tags

Target latency: 1–3 seconds (vs 78s with Crawl4AI)

Usage:
    from scraping.price_history_scraper import get_price_history

    result = asyncio.run(get_price_history("iQOO 15"))
    # result = {
    #     "product_name": "IQOO 15 5G (Legend, 512 GB)",
    #     "lowest_price": 72975,
    #     "highest_price": 81576,
    #     "average_price": 77078,
    #     "current_price": 74499,
    #     "trend": "declining",
    #     "recommendation": "BUY",
    #     ...
    # }
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Any, List

import httpx
from ddgs import DDGS

logger = logging.getLogger(__name__)


# ============================================================
# SECTION 1: SEARCH — DDGS with google/bing backends
# ============================================================

# Semaphore to prevent flooding DDGS — lazy-created per event loop
_search_semaphore = None
_search_sem_loop = None

def _get_semaphore() -> asyncio.Semaphore:
    global _search_semaphore, _search_sem_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if _search_semaphore is None or loop is not _search_sem_loop:
        _search_semaphore = asyncio.Semaphore(2)
        _search_sem_loop = loop
    return _search_semaphore


async def _ddgs_search(
    query: str,
    backend: str = "brave",
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Execute a DDGS search with the specified backend.
    Runs in a thread executor since DDGS is synchronous.
    """
    async with _get_semaphore():
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
            logger.info(f"[PriceHistory] DDGS [{backend}] '{query[:50]}' → {len(results)} results")
            return results or []

        except Exception as e:
            logger.warning(f"[PriceHistory] DDGS [{backend}] search failed: {e}")
            return []


async def _find_product_url(product_name: str) -> Optional[str]:
    """
    Find the pricehistory.app product page URL using DDGS.
    
    Strategy:
      1. Primary: brave backend with site:pricehistory.app
      2. Fallback: duckduckgo backend if brave returns nothing
    """
    query = f"site:pricehistory.app {product_name}"

    # Primary: brave backend
    results = await _ddgs_search(query, backend="brave", max_results=5)

    # Fallback: duckduckgo backend
    if not results:
        logger.info("[PriceHistory] Brave returned 0 results, falling back to duckduckgo")
        results = await _ddgs_search(query, backend="duckduckgo", max_results=5)

    if not results:
        logger.warning(f"[PriceHistory] No results from any backend for: {product_name}")
        return None

    # Tokenize product name for URL slug matching
    # e.g. "iQOO 15" → ["iqoo", "15"]
    name_tokens = [t.lower() for t in product_name.split() if len(t) >= 2]

    # Accessory keywords — reject URLs containing these in the slug
    _ACCESSORY_SLUGS = {
        "screen-protector", "tempered-glass", "case", "cover", "pouch",
        "charger", "cable", "adapter", "stand", "holder", "mount",
        "earphone", "headphone", "earbud", "stylus", "pen", "film",
        "pack-for", "pack-iphone", "pack-samsung", "compatible",
    }

    # Find the first result that is a product page AND matches the product name
    for r in results:
        href = r.get("href", "")
        if "pricehistory.app/p/" not in href:
            continue
        
        # Extract slug: /p/iqoo-15-5g-legend-512-gb → "iqoo-15-5g-legend-512-gb"
        slug = href.split("/p/")[-1].lower()
        slug_segments = set(slug.split("-"))
        
        # Reject accessories
        is_accessory = any(acc_kw in slug for acc_kw in _ACCESSORY_SLUGS)
        if is_accessory:
            logger.info(f"[PriceHistory] Skipping accessory URL: {href}")
            continue
        
        # All key tokens from product name must appear as slug segments
        if all(token in slug_segments for token in name_tokens):
            logger.info(f"[PriceHistory] Found matching product URL: {href}")
            return href
        else:
            logger.info(f"[PriceHistory] Skipping non-matching URL: {href} (segments {slug_segments} vs tokens {name_tokens})")

    # Relaxed fallback: try any non-accessory pricehistory.app/p/ link
    for r in results:
        href = r.get("href", "")
        if "pricehistory.app/p/" in href:
            slug = href.split("/p/")[-1].lower()
            is_accessory = any(acc_kw in slug for acc_kw in _ACCESSORY_SLUGS)
            if not is_accessory:
                logger.info(f"[PriceHistory] Using first /p/ URL (relaxed match): {href}")
                return href

    logger.warning("[PriceHistory] No matching pricehistory.app URL in search results")
    return None


# ============================================================
# SECTION 2: EXTRACT — Parse price data from raw HTML
# ============================================================

def _parse_price(text: str) -> Optional[int]:
    """Parse '₹72,975' or '72975' into an integer."""
    if not text:
        return None
    cleaned = re.sub(r'[₹,\s]', '', text.strip())
    match = re.match(r'(\d+)', cleaned)
    return int(match.group(1)) if match else None


def _extract_price_data(html: str) -> Dict[str, Any]:
    """
    Extract price data from pricehistory.app raw HTML.
    
    All data comes from <meta> tags (OG description) — no JS needed.
    Example OG description:
      "Get Price History of IQOO 15 5G (Legend, 512 GB). 
       Lowest Price: ₹72975 | Average Price: ₹77078 | Highest Price: ₹81576 | ..."
    """
    data: Dict[str, Any] = {
        "lowest_price": None,
        "highest_price": None,
        "average_price": None,
        "current_price": None,
        "product_name": None,
    }

    # --- OG meta description (primary source) ---
    og_match = re.search(
        r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]*)"',
        html, re.IGNORECASE
    )
    if not og_match:
        og_match = re.search(
            r'content="([^"]*)"\s+(?:property="og:description"|name="description")',
            html, re.IGNORECASE
        )

    if og_match:
        desc = og_match.group(1)
        logger.info(f"[PriceHistory] OG desc: {desc[:120]}...")

        lowest = re.search(r'[Ll]owest(?:\s+[Pp]rice)?[:\s]*₹?([\d,]+)', desc)
        highest = re.search(r'[Hh]ighest(?:\s+[Pp]rice)?[:\s]*₹?([\d,]+)', desc)
        average = re.search(r'[Aa]verage(?:\s+[Pp]rice)?[:\s]*₹?([\d,]+)', desc)
        current = re.search(r'[Cc]urrent(?:\s+[Pp]rice)?[:\s]*₹?([\d,]+)', desc)

        if lowest:  data["lowest_price"]  = _parse_price(lowest.group(1))
        if highest: data["highest_price"] = _parse_price(highest.group(1))
        if average: data["average_price"] = _parse_price(average.group(1))
        if current: data["current_price"] = _parse_price(current.group(1))

    # --- OG title for product name ---
    title_match = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]*)"', html, re.IGNORECASE
    )
    if not title_match:
        title_match = re.search(r'<title>([^<]*)</title>', html, re.IGNORECASE)

    if title_match:
        raw_title = title_match.group(1)
        data["product_name"] = re.sub(r'\s*[-|].*$', '', raw_title).strip()

    # --- Fallback: search full HTML for price patterns ---
    if data["lowest_price"] is None:
        for keyword, field in [
            ("lowest", "lowest_price"),
            ("highest", "highest_price"),
            ("average", "average_price"),
        ]:
            pattern = re.search(
                rf'{keyword}.*?₹\s*([\d,]+)', html, re.IGNORECASE | re.DOTALL
            )
            if pattern and data[field] is None:
                data[field] = _parse_price(pattern.group(1))

    # Current price from JSON-LD or page content
    if data["current_price"] is None:
        offer_price = re.search(r'"price"\s*:\s*"?(\d+)"?', html)
        if offer_price:
            data["current_price"] = int(offer_price.group(1))

    if data["current_price"] is None:
        current_match = re.search(
            r'(?:Market\s+Price|Current\s+Price|Offer\s+Price).*?₹\s*([\d,]+)',
            html, re.IGNORECASE | re.DOTALL
        )
        if current_match:
            data["current_price"] = _parse_price(current_match.group(1))

    # --- Sanity checks: reject obviously wrong prices ---
    # If lowest is absurdly low (< ₹500) it's a regex false positive
    if data["lowest_price"] and data["lowest_price"] < 500:
        logger.warning(f"[PriceHistory] Rejecting suspicious lowest_price: ₹{data['lowest_price']}")
        data["lowest_price"] = None
    
    # If lowest > highest, something is wrong
    if (data["lowest_price"] and data["highest_price"] 
            and data["lowest_price"] > data["highest_price"]):
        logger.warning("[PriceHistory] lowest > highest — swapping")
        data["lowest_price"], data["highest_price"] = data["highest_price"], data["lowest_price"]

    return data


# ============================================================
# SECTION 3: RECOMMENDATION ENGINE
# ============================================================

def _compute_recommendation(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Buy/Wait recommendation based on price position.
    
    Rules:
    - Current ≤ lowest → STRONG_BUY
    - Current ≤ average and within 5% of lowest → BUY
    - Current > average → WAIT
    """
    current = data.get("current_price")
    lowest = data.get("lowest_price")
    highest = data.get("highest_price")
    average = data.get("average_price")

    if not current or not lowest:
        return {"recommendation": "NEUTRAL", "reason": "Not enough price data.", "trend": "unknown"}

    # Trend
    trend = "stable"
    if average:
        if current < average * 0.95:
            trend = "declining"
        elif current > average * 1.05:
            trend = "rising"

    # Recommendation
    if current <= lowest:
        return {
            "recommendation": "STRONG_BUY",
            "reason": f"Current price (₹{current:,}) is at or below all-time low (₹{lowest:,}). Best time to buy!",
            "trend": trend,
        }

    pct_above_low = ((current - lowest) / lowest) * 100 if lowest > 0 else 0

    if average and current <= average:
        if pct_above_low <= 5:
            return {
                "recommendation": "BUY",
                "reason": f"Current price (₹{current:,}) is near the all-time low (₹{lowest:,}, only {pct_above_low:.1f}% above). Good deal.",
                "trend": trend,
            }
        return {
            "recommendation": "BUY",
            "reason": f"Current price (₹{current:,}) is below average (₹{average:,}). {pct_above_low:.1f}% above lowest.",
            "trend": trend,
        }

    if average:
        return {
            "recommendation": "WAIT",
            "reason": f"Current price (₹{current:,}) is above average (₹{average:,}). Lowest was ₹{lowest:,}. Wait for a drop.",
            "trend": trend,
        }

    return {"recommendation": "NEUTRAL", "reason": "Insufficient data.", "trend": trend}


# ============================================================
# SECTION 4: ORCHESTRATOR — The public API
# ============================================================

async def get_price_history(product_name: str) -> Dict[str, Any]:
    """
    Get price history for a product from pricehistory.app.
    
    Pipeline:
      1. DDGS search (brave → duckduckgo fallback) to find the URL
      2. httpx GET to fetch raw HTML
      3. Regex to parse prices from <meta> OG tags
      4. Compute buy/wait recommendation
    
    Target latency: 1–3 seconds.
    """
    logger.info(f"[PriceHistory] Starting lookup for: {product_name}")
    start_time = time.time()

    result: Dict[str, Any] = {
        "product_name": product_name,
        "lowest_price": None,
        "highest_price": None,
        "average_price": None,
        "current_price": None,
        "trend": "unknown",
        "recommendation": "NEUTRAL",
        "recommendation_reason": "",
        "chart_image_url": None,       # No screenshot — link to source instead
        "source_url": None,
        "source_site": "pricehistory.app",
        "found": False,
        "execution_time": 0,
    }

    # Step 1: Find the product URL via DDGS
    product_url = await _find_product_url(product_name)

    if not product_url:
        result["execution_time"] = round(time.time() - start_time, 2)
        logger.warning(f"[PriceHistory] Product not found: {product_name}")
        return result

    result["source_url"] = product_url

    # Step 2: Fetch raw HTML with httpx (no browser needed)
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        ) as client:
            t0 = time.time()
            resp = await client.get(product_url)
            fetch_time = round(time.time() - t0, 2)
            logger.info(f"[PriceHistory] httpx GET {resp.status_code} in {fetch_time}s")

            if resp.status_code != 200:
                logger.warning(f"[PriceHistory] HTTP {resp.status_code} for {product_url}")
                result["execution_time"] = round(time.time() - start_time, 2)
                return result

            html = resp.text

    except Exception as e:
        logger.error(f"[PriceHistory] httpx error: {e}")
        result["execution_time"] = round(time.time() - start_time, 2)
        return result

    # Step 3: Parse prices from HTML
    price_data = _extract_price_data(html)
    result.update(price_data)
    result["found"] = any([
        price_data.get("lowest_price"),
        price_data.get("highest_price"),
        price_data.get("current_price"),
    ])

    if result["found"]:
        lo = f"₹{result['lowest_price']:,}" if result['lowest_price'] else 'N/A'
        hi = f"₹{result['highest_price']:,}" if result['highest_price'] else 'N/A'
        cu = f"₹{result['current_price']:,}" if result['current_price'] else 'N/A'
        logger.info(
            f"[PriceHistory] Extracted: lowest={lo}, "
            f"highest={hi}, current={cu}"
        )

    # Step 4: Compute recommendation
    rec = _compute_recommendation(result)
    result["trend"] = rec["trend"]
    result["recommendation"] = rec["recommendation"]
    result["recommendation_reason"] = rec["reason"]

    result["execution_time"] = round(time.time() - start_time, 2)
    logger.info(
        f"[PriceHistory] Done in {result['execution_time']}s — "
        f"recommendation: {result['recommendation']}"
    )
    return result


def get_price_history_sync(product_name: str) -> Dict[str, Any]:
    """Sync wrapper for get_price_history."""
    return asyncio.run(get_price_history(product_name))


# ── Interactive testing REPL ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def _fmt(price):
        return f"₹{price:,}" if price else "—"

    def _print_result(result):
        found = result.get("found", False)
        print(f"\n{'─'*60}")
        print(f"  📦 Product:  {result.get('product_name', 'Unknown')}")
        print(f"  🔗 Source:   {result.get('source_url', 'Not found')}")
        print(f"{'─'*60}")

        if found:
            print(f"  � Lowest:   {_fmt(result.get('lowest_price'))}")
            print(f"  📊 Average:  {_fmt(result.get('average_price'))}")
            print(f"  📈 Highest:  {_fmt(result.get('highest_price'))}")
            print(f"  💰 Current:  {_fmt(result.get('current_price'))}")
            print(f"  📉 Trend:    {result.get('trend', 'unknown')}")
            print(f"  💡 Verdict:  {result.get('recommendation', 'NEUTRAL')}")
            print(f"  📝 Reason:   {result.get('recommendation_reason', '')}")
        else:
            print(f"  ⚠️  No price data found on pricehistory.app")

        print(f"  ⏱️  Time:     {result.get('execution_time', 0)}s")
        print(f"{'─'*60}\n")

    print("\n" + "=" * 60)
    print("  🔍 Price History Tester — Interactive Mode")
    print("  Type a product name and press Enter.")
    print("  Type 'q' or 'exit' to quit.")
    print("=" * 60)

    while True:
        try:
            query = input("\n🔎 Product: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye!")
            break

        if not query or query.lower() in ("q", "quit", "exit"):
            print("👋 Bye!")
            break

        result = asyncio.run(get_price_history(query))
        _print_result(result)

