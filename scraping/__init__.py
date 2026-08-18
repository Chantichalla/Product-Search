# Scraping module - concurrent scraping utilities
from .concurrency import (
    # V1 (original)
    scrape_urls_concurrent, 
    ddg_search_concurrent,
    search_with_fallback,
    ENGINE_PRIORITY,
    # V2 (enhanced with fit_markdown)
    scrape_urls_concurrent_v2,
    scrape_urls_sync_v2,
)

# V3: Tavily API (recommended - replaces DDG/Brave + Crawl4AI)
from .tavily_search import (
    tavily_search,
    tavily_smart_search,
    tavily_price_search,
    tavily_comparison_search,
    tavily_best_under_search,
    tavily_advice_search,
    tavily_feature_search,
    tavily_extract,
)

__all__ = [
    # V1 (legacy)
    "scrape_urls_concurrent", 
    "ddg_search_concurrent",
    "search_with_fallback",
    "ENGINE_PRIORITY",
    # V2 (legacy)
    "scrape_urls_concurrent_v2",
    "scrape_urls_sync_v2",
    # V3: Tavily (recommended)
    "tavily_search",
    "tavily_smart_search",
    "tavily_price_search",
    "tavily_comparison_search",
    "tavily_best_under_search",
    "tavily_advice_search",
    "tavily_feature_search",
    "tavily_extract",
]

