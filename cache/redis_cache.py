"""
Redis Cache Layer for E-commerce Agent

Provides fast, TTL-managed caching for:
- Search results (DDG/web searches)
- Scraped pages (product pages, listings)
- Comparison results

All keys are normalized for exact matching.
Redis handles TTL expiry automatically.
"""

import hashlib
import json
import re
import time
from typing import Any

import redis


class RedisCache:
    """
    Thin wrapper around Redis for caching.
    
    Key patterns:
    - search:{normalized_query} → search results
    - page:{url_hash} → scraped page content
    - comparison:{model_slug} → comparison results
    """
    
    # Default TTLs in seconds
    SEARCH_TTL = 21600    # 6 hours
    PAGE_TTL = 3600       # 1 hour
    COMPARISON_TTL = 1800 # 30 minutes
    
    # Tiered caching for different data types
    SPECS_TTL = 86400     # 24 hours - specs rarely change
    PRICE_TTL = 900       # 15 minutes - prices change frequently
    PRODUCT_TTL = 3600    # 1 hour - general product data
    
    # Query-type based TTLs (per user requirements)
    QUERY_TYPE_TTL = {
        "comparison": 7 * 24 * 3600,    # 7 days - specs don't change
        "best_under": 7 * 24 * 3600,    # 7 days - user preference
        "price_search": 24 * 3600,      # 1 day - prices fluctuate
        "feature_query": 7 * 24 * 3600, # 7 days - features don't change
        "product_advice": 7 * 24 * 3600,# 7 days - buying guides stable
        "default": 6 * 3600,            # 6 hours - fallback
    }
    
    def __init__(self, url: str = "redis://localhost:6379/0"):
        """Initialize Redis connection."""
        self.client = redis.from_url(url, decode_responses=True)
        self._connected = False
        self._check_connection()
    
    def _check_connection(self) -> bool:
        """Check if Redis is available."""
        try:
            self.client.ping()
            self._connected = True
            return True
        except redis.ConnectionError:
            self._connected = False
            print("[RedisCache] Warning: Redis not available, caching disabled")
            return False
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._connected
    
    # ========================================
    # Key Normalization Helpers
    # ========================================
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize a search query to a cache key.
        - Lowercase
        - Remove special characters
        - Replace spaces with underscores
        - Remove common filler words
        """
        q = query.lower().strip()
        # Remove common filler words
        filler = ["the", "a", "an", "in", "for", "best", "top", "most", "very", "what", "is", "are"]
        words = q.split()
        words = [w for w in words if w not in filler]
        # Clean each word
        words = [re.sub(r'[^a-z0-9]', '', w) for w in words]
        words = [w for w in words if w]  # Remove empty
        return "_".join(words)
    
    def _hash_url(self, url: str) -> str:
        """Hash a URL to a short key."""
        return hashlib.md5(url.encode()).hexdigest()[:12]
    
    def _normalize_model(self, model: str) -> str:
        """Normalize a model name to a cache key."""
        m = model.lower().strip()
        m = re.sub(r'[^a-z0-9\s]', '', m)
        return "_".join(m.split())
    
    # ========================================
    # Search Cache (6h TTL)
    # ========================================
    
    def get_search(self, query: str) -> dict | None:
        """
        Get cached search results.
        
        Args:
            query: The search query
            
        Returns:
            Cached data dict or None if not found
        """
        if not self._connected:
            return None
        
        key = f"search:{self._normalize_query(query)}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[RedisCache] get_search error: {e}")
        return None
    
    def set_search(self, query: str, data: dict, ttl_seconds: int = None) -> bool:
        """
        Cache search results.
        
        Args:
            query: The search query
            data: Dict to cache (will be JSON serialized)
            ttl_seconds: TTL in seconds (default: 6h)
            
        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False
        
        ttl = ttl_seconds or self.SEARCH_TTL
        key = f"search:{self._normalize_query(query)}"
        try:
            # Add timestamp to data
            data["_cached_at"] = time.time()
            self.client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"[RedisCache] set_search error: {e}")
        return False
    
    def set_search_typed(self, query: str, data: dict, query_type: str = None) -> bool:
        """
        Cache search results with TTL based on query type.
        """
        ttl = self.get_ttl_for_type(query_type)
        ttl_days = ttl / (24 * 3600)
        print(f"[RedisCache] Caching with {ttl_days:.1f} day TTL for {query_type}")
        return self.set_search(query, data, ttl_seconds=ttl)
    
    def get_ttl_for_type(self, query_type: str) -> int:
        """Get TTL in seconds for a specific query type."""
        return self.QUERY_TYPE_TTL.get(query_type, self.QUERY_TYPE_TTL["default"])
    
    # ========================================
    # Page Cache (1h TTL)
    # ========================================
    
    def get_page(self, url: str) -> dict | None:
        """
        Get cached page content.
        
        Args:
            url: The page URL
            
        Returns:
            Cached data dict or None if not found
        """
        if not self._connected:
            return None
        
        key = f"page:{self._hash_url(url)}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[RedisCache] get_page error: {e}")
        return None
    
    def set_page(self, url: str, data: dict, ttl_seconds: int = None) -> bool:
        """
        Cache page content.
        
        Args:
            url: The page URL
            data: Dict to cache (should include 'content' key)
            ttl_seconds: TTL in seconds (default: 1h)
            
        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False
        
        ttl = ttl_seconds or self.PAGE_TTL
        key = f"page:{self._hash_url(url)}"
        try:
            data["_cached_at"] = time.time()
            data["_url"] = url  # Store original URL for debugging
            self.client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"[RedisCache] set_page error: {e}")
        return False
    
    # ========================================
    # Comparison Cache (30m TTL)
    # ========================================
    
    def get_comparison(self, model: str) -> dict | None:
        """
        Get cached comparison result.
        
        Args:
            model: The model name
            
        Returns:
            Cached data dict or None if not found
        """
        if not self._connected:
            return None
        
        key = f"comparison:{self._normalize_model(model)}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[RedisCache] get_comparison error: {e}")
        return None
    
    def set_comparison(self, model: str, data: dict, ttl_seconds: int = None) -> bool:
        """
        Cache comparison result.
        
        Args:
            model: The model name
            data: Dict to cache
            ttl_seconds: TTL in seconds (default: 30m)
            
        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False
        
        ttl = ttl_seconds or self.COMPARISON_TTL
        key = f"comparison:{self._normalize_model(model)}"
        try:
            data["_cached_at"] = time.time()
            self.client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"[RedisCache] set_comparison error: {e}")
        return False
    
    # ========================================
    # Specs Cache (24h TTL) - Stable data
    # ========================================
    
    def get_specs(self, product_id: str) -> dict | None:
        """
        Get cached product specifications.
        
        Args:
            product_id: Normalized product identifier
            
        Returns:
            Cached specs dict or None if not found
        """
        if not self._connected:
            return None
        
        key = f"specs:{self._normalize_model(product_id)}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[RedisCache] get_specs error: {e}")
        return None
    
    def set_specs(self, product_id: str, data: dict, ttl_seconds: int = None) -> bool:
        """
        Cache product specifications (long TTL - 24h).
        
        Args:
            product_id: Normalized product identifier
            data: Specs dict to cache
            ttl_seconds: TTL in seconds (default: 24h)
            
        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False
        
        ttl = ttl_seconds or self.SPECS_TTL
        key = f"specs:{self._normalize_model(product_id)}"
        try:
            data["_cached_at"] = time.time()
            self.client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"[RedisCache] set_specs error: {e}")
        return False
    
    # ========================================
    # Price Cache (15m TTL) - Volatile data
    # ========================================
    
    def get_price(self, product_id: str, store: str = "any") -> dict | None:
        """
        Get cached product price.
        
        Args:
            product_id: Normalized product identifier
            store: Store name (amazon, flipkart, etc.)
            
        Returns:
            Cached price dict or None if not found
        """
        if not self._connected:
            return None
        
        key = f"price:{store}:{self._normalize_model(product_id)}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[RedisCache] get_price error: {e}")
        return None
    
    def set_price(self, product_id: str, store: str, data: dict, ttl_seconds: int = None) -> bool:
        """
        Cache product price (short TTL - 15min).
        
        Args:
            product_id: Normalized product identifier
            store: Store name (amazon, flipkart, etc.)
            data: Price dict to cache
            ttl_seconds: TTL in seconds (default: 15min)
            
        Returns:
            True if cached successfully
        """
        if not self._connected:
            return False
        
        ttl = ttl_seconds or self.PRICE_TTL
        key = f"price:{store}:{self._normalize_model(product_id)}"
        try:
            data["_cached_at"] = time.time()
            self.client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"[RedisCache] set_price error: {e}")
        return False
    
    # ========================================
    # Utility Methods
    # ========================================
    
    def clear_all(self) -> int:
        """
        Clear all cached data.
        
        Returns:
            Number of keys deleted
        """
        if not self._connected:
            return 0
        
        try:
            keys = self.client.keys("*")
            if keys:
                return self.client.delete(*keys)
        except Exception as e:
            print(f"[RedisCache] clear_all error: {e}")
        return 0
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Clear keys matching a pattern.
        
        Args:
            pattern: Redis key pattern (e.g., "search:*", "page:*")
            
        Returns:
            Number of keys deleted
        """
        if not self._connected:
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
        except Exception as e:
            print(f"[RedisCache] clear_pattern error: {e}")
        return 0
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with key counts and memory info
        """
        if not self._connected:
            return {"connected": False}
        
        try:
            info = self.client.info("memory")
            return {
                "connected": True,
                "search_keys": len(self.client.keys("search:*")),
                "page_keys": len(self.client.keys("page:*")),
                "comparison_keys": len(self.client.keys("comparison:*")),
                "used_memory": info.get("used_memory_human", "unknown"),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# Global instance
redis_cache = RedisCache()
redis_client = redis_cache.client
is_connected = redis_cache.is_connected
