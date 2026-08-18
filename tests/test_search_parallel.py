"""
Test: Parallel Multi-Site Search
Tests multi-site concurrent search across search backends.
"""
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows event loop if needed
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ddgs import DDGS

TARGET_SITES = [
    "amazon.in",
    "flipkart.com",
    "croma.com",
    "reliancedigital.in",
]
BACKENDS = ["google", "duckduckgo"]


async def _do_search(query: str, backend: str, site: str):
    """Wrapper that returns (site, backend, elapsed, urls, error)."""
    t0 = time.perf_counter()
    try:
        loop = asyncio.get_event_loop()
        def _search():
            with DDGS() as ddg:
                return list(ddg.text(f"site:{site} {query}", max_results=3, backend=backend))

        results = await loop.run_in_executor(None, _search)
        elapsed = time.perf_counter() - t0
        urls = [r.get("href", "?") for r in results if isinstance(r, dict)]
        return (site, backend, elapsed, urls, None)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return (site, backend, elapsed, [], str(e)[:100])


async def test_search(query: str = "iPhone 15"):
    print("=" * 60)
    print(f"  TEST: Parallel Multi-Site Search")
    print(f"  Query: '{query}'")
    print(f"  Sites: {len(TARGET_SITES)}")
    print("=" * 60)

    tasks = [_do_search(query, "duckduckgo", site) for site in TARGET_SITES]
    results = await asyncio.gather(*tasks)

    for site, backend, elapsed, urls, error in results:
        status = f"✅ {len(urls)} URLs ({elapsed:.2f}s)" if urls else f"⚠️ None ({elapsed:.2f}s)"
        if error:
            status = f"❌ Error: {error}"
        print(f"  • {site:<20} | {status}")


if __name__ == "__main__":
    asyncio.run(test_search("MacBook Air M3"))
