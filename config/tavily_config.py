"""
Tavily API Configuration

Centralized configuration for Tavily search API including:
- Client initialization with API key
- Credit tracking and caching configuration

SIMPLIFIED: Removed domain whitelists - Tavily's AI ranking 
decides what's most relevant for each query.
"""

import os
from typing import Optional
from functools import lru_cache

# ═══════════════════════════════════════════════════════
# DOMAIN CONFIGURATION
# Only exclude junk sites - let Tavily rank everything else
# ═══════════════════════════════════════════════════════

# Sites to always exclude (low quality / irrelevant for product searches)
EXCLUDE_ALWAYS = [
    # Used goods marketplaces
    "olx.in", "quikr.com",
    # Social media (not product info)
    "facebook.com", "twitter.com", "instagram.com", "pinterest.com",
    # Video platforms (use transcript APIs if needed)
    "youtube.com",
    # Forums (unreliable for product decisions)
    "reddit.com", "quora.com",
    # Generic news (not product-focused)
    "news.google.com",
]


# ═══════════════════════════════════════════════════════
# CACHE CONFIGURATION
# ═══════════════════════════════════════════════════════

TAVILY_CACHE_TTL = {
    "price_search": 3600,      # 1 hour for price data
    "comparison": 86400,       # 24 hours for comparisons
    "best_under": 86400,       # 24 hours for recommendations
    "product_advice": 604800,  # 7 days for buying guides
    "feature_query": 86400,    # 24 hours for spec data
    "follow_up": 3600,         # 1 hour
    "unknown": 3600,           # 1 hour
}


# ═══════════════════════════════════════════════════════
# CLIENT INITIALIZATION
# ═══════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def get_tavily_client():
    """Get or create Tavily client (cached singleton)."""
    try:
        from tavily import TavilyClient
        
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            print("[Tavily] ⚠️ TAVILY_API_KEY not set in environment")
            return None
        
        client = TavilyClient(api_key=api_key)
        print("[Tavily] ✅ Client initialized")
        return client
        
    except ImportError:
        print("[Tavily] ⚠️ tavily-python not installed. Run: pip install tavily-python")
        return None
    except Exception as e:
        print(f"[Tavily] ❌ Error initializing client: {e}")
        return None


# ═══════════════════════════════════════════════════════
# CREDIT TRACKING (for free tier monitoring)
# ═══════════════════════════════════════════════════════

class CreditTracker:
    """Track Tavily API credit usage for free tier (1000/month)."""
    
    def __init__(self):
        self.total_credits = 0
        self.search_count = 0
        self.extract_count = 0
        self.cache_hits = 0
    
    def log_search(self, search_depth: str = "basic"):
        """Log a search call."""
        credits = 2 if search_depth == "advanced" else 1
        self.total_credits += credits
        self.search_count += 1
        print(f"[Tavily] Search #{self.search_count} | Credits: {credits} | Total: {self.total_credits}")
    
    def log_extract(self, url_count: int = 5):
        """Log an extract call (1 credit per 5 URLs)."""
        credits = (url_count + 4) // 5  # Round up
        self.total_credits += credits
        self.extract_count += 1
        print(f"[Tavily] Extract #{self.extract_count} ({url_count} URLs) | Credits: {credits} | Total: {self.total_credits}")
    
    def log_cache_hit(self):
        """Log a cache hit (saved credits)."""
        self.cache_hits += 1
    
    def get_stats(self) -> dict:
        """Get usage statistics."""
        return {
            "total_credits": self.total_credits,
            "search_count": self.search_count,
            "extract_count": self.extract_count,
            "cache_hits": self.cache_hits,
            "estimated_remaining": 1000 - self.total_credits,
        }
    
    def print_summary(self):
        """Print usage summary."""
        stats = self.get_stats()
        print(f"""
╔══════════════════════════════════════╗
║       TAVILY CREDIT USAGE            ║
╠══════════════════════════════════════╣
║ Searches:    {stats['search_count']:>4} calls              ║
║ Extracts:    {stats['extract_count']:>4} calls              ║
║ Cache Hits:  {stats['cache_hits']:>4} (saved credits!)    ║
║ ────────────────────────────────────║
║ Total Used:  {stats['total_credits']:>4} / 1000 credits    ║
║ Remaining:   {stats['estimated_remaining']:>4} credits           ║
╚══════════════════════════════════════╝
""")


# Global credit tracker instance
credit_tracker = CreditTracker()


# ═══════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════

def get_cache_key(query: str, query_type: str) -> str:
    """Generate cache key for Tavily queries."""
    import hashlib
    normalized = query.lower().strip()
    hash_str = hashlib.md5(normalized.encode()).hexdigest()[:8]
    return f"tavily:{query_type}:{hash_str}"


def get_domains_for_query_type(query_type: str) -> tuple:
    """
    Get (include_domains, exclude_domains) for query type.
    
    SIMPLIFIED: No more whitelisting - let Tavily's AI rank results.
    Only exclude junk sites that are never useful for product searches.
    """
    # All query types: no whitelist, just block junk
    return None, EXCLUDE_ALWAYS

