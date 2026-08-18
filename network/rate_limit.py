"""
Async Rate Limiter for E-commerce Agent

Provides per-domain rate limiting with:
- Semaphore-based concurrency control
- Optional random delay (jitter) before requests
- Non-blocking asyncio.sleep() instead of time.sleep()

Usage:
    limiter = RateLimiter(config={
        "amazon.in": {"min_delay": 1.0, "max_delay": 3.0, "max_concurrent": 3},
        "default": {"min_delay": 0.0, "max_delay": 0.0, "max_concurrent": 5},
    })
    
    async with limiter.slot("amazon.in"):
        result = await crawler.arun(url)
"""

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Dict, Optional
from urllib.parse import urlparse


# Default configuration for different domain types
DEFAULT_CONFIG = {
    # Sensitive e-commerce sites - be polite
    "amazon.in": {"min_delay": 1.0, "max_delay": 2.5, "max_concurrent": 3},
    "amazon.com": {"min_delay": 1.0, "max_delay": 2.5, "max_concurrent": 3},
    "flipkart.com": {"min_delay": 1.0, "max_delay": 2.5, "max_concurrent": 3},
    
    # Search engines - moderate limits
    "duckduckgo.com": {"min_delay": 0.3, "max_delay": 0.8, "max_concurrent": 5},
    "google.com": {"min_delay": 0.5, "max_delay": 1.0, "max_concurrent": 3},
    
    # Default for unknown domains - aggressive test mode
    "default": {"min_delay": 0.0, "max_delay": 0.2, "max_concurrent": 8},
}


def extract_domain(url: str) -> str:
    """
    Extract the base domain from a URL.
    
    Examples:
        "https://www.amazon.in/dp/123" -> "amazon.in"
        "https://flipkart.com/product" -> "flipkart.com"
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return "unknown"


class RateLimiter:
    """
    Async-friendly rate limiter with per-domain policies.
    
    Features:
    - Semaphore-based concurrency control per domain
    - Random delay (jitter) before requests
    - Non-blocking asyncio.sleep()
    - Automatic domain extraction from URLs
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize rate limiter with config.
        
        Args:
            config: Dict mapping domain -> {min_delay, max_delay, max_concurrent}
                    Falls back to DEFAULT_CONFIG for missing domains.
        """
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
    
    def _get_domain_config(self, domain: str) -> dict:
        """Get config for a domain, falling back to default."""
        # Check exact match first
        if domain in self.config:
            return self.config[domain]
        
        # Check if domain ends with a known domain (e.g., "www.amazon.in" -> "amazon.in")
        for known_domain in self.config:
            if domain.endswith(known_domain):
                return self.config[known_domain]
        
        # Fall back to default
        return self.config.get("default", {"min_delay": 0.0, "max_delay": 0.0, "max_concurrent": 5})
    
    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create semaphore for a domain. Recreates if event loop changed."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        existing = self._semaphores.get(domain)
        
        # Recreate if no semaphore, or if it was bound to a different loop
        if existing is None or (current_loop and hasattr(existing, '_loop') and existing._loop is not current_loop):
            config = self._get_domain_config(domain)
            self._semaphores[domain] = asyncio.Semaphore(config["max_concurrent"])
        
        return self._semaphores[domain]
    
    @asynccontextmanager
    async def slot(self, url_or_domain: str):
        """
        Async context manager for rate-limited operations.
        
        Applies:
        1. Semaphore limit for the domain
        2. Random delay (jitter) before yielding
        
        Usage:
            async with limiter.slot("https://amazon.in/product"):
                result = await scrape(url)
        """
        # Extract domain if URL provided
        if url_or_domain.startswith("http"):
            domain = extract_domain(url_or_domain)
        else:
            domain = url_or_domain.lower()
        
        config = self._get_domain_config(domain)
        semaphore = self._get_semaphore(domain)
        
        async with semaphore:
            # Apply random delay (jitter) if configured
            min_delay = config.get("min_delay", 0.0)
            max_delay = config.get("max_delay", 0.0)
            
            if max_delay > 0:
                delay = random.uniform(min_delay, max_delay)
                if delay > 0:
                    await asyncio.sleep(delay)
            
            yield
    
    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        stats = {}
        for domain, sem in self._semaphores.items():
            config = self._get_domain_config(domain)
            stats[domain] = {
                "max_concurrent": config["max_concurrent"],
                "available_slots": sem._value,  # Internal semaphore value
                "delay_range": f"{config['min_delay']}-{config['max_delay']}s"
            }
        return stats


class TokenBucketLimiter:
    """
    Token bucket rate limiter for LLM APIs (TPM/RPM).
    """
    def __init__(self, rpm_limit: int = 30, tpm_limit: int = 6000):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.tokens = tpm_limit
        self.requests = rpm_limit
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        
    async def acquire(self, tokens: int = 0):
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Replenish
            self.tokens = min(self.tpm_limit, self.tokens + (elapsed * (self.tpm_limit / 60.0)))
            self.requests = min(self.rpm_limit, self.requests + (elapsed * (self.rpm_limit / 60.0)))
            self.last_update = now
            
            # Check limits
            if self.requests < 1:
                wait_time = (1 - self.requests) / (self.rpm_limit / 60.0)
                print(f"  [Rate Limit] RPM hit, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.requests = 1
                
            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / (self.tpm_limit / 60.0)
                print(f"  [Rate Limit] TPM hit, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.tokens = tokens
                
            self.requests -= 1
            self.tokens -= tokens

# Global Groq limiter (conservative defaults)
import time
groq_limiter = TokenBucketLimiter(rpm_limit=10, tpm_limit=5000)
rate_limiter = RateLimiter()
