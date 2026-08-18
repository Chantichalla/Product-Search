"""
Budget & URL Utilities

Provides:
- Budget parsing from natural language queries (Indian format: k, lakh, ₹)
- URL utilities for e-commerce site detection
- Query normalization for cache keys

Usage:
    budget = parse_budget_from_query("laptop under 50k")
    # BudgetRange(min_price=None, max_price=50000)
    
    domain = extract_domain("https://www.amazon.in/dp/123")
    # "amazon.in"
"""

import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel


class BudgetRange(BaseModel):
    """
    Price range from a user query.
    
    Both fields are optional:
    - Only max_price: "under X"
    - Only min_price: "above X"
    - Both: "between X and Y"
    """
    min_price: Optional[int] = None  # in rupees
    max_price: Optional[int] = None  # in rupees


# ============================================================
# Budget Parsing
# ============================================================

def _parse_indian_price(text: str) -> Optional[int]:
    """
    Parse Indian price notation to integer.
    
    Examples:
        "50k" -> 50000
        "1.5 lakh" -> 150000
        "45000" -> 45000
        "1,50,000" -> 150000
        "₹80k" -> 80000
    """
    if not text:
        return None
    
    # Clean up
    text = text.lower().strip()
    text = re.sub(r'[₹rs\.\s,]', '', text)
    
    try:
        # Handle "lakh" / "L"
        lakh_match = re.search(r'([\d.]+)\s*(?:lakh|lac|l)(?:s)?', text, re.IGNORECASE)
        if lakh_match:
            return int(float(lakh_match.group(1)) * 100000)
        
        # Handle "k" / "K"
        k_match = re.search(r'([\d.]+)\s*k', text, re.IGNORECASE)
        if k_match:
            return int(float(k_match.group(1)) * 1000)
        
        # Handle plain number
        num_match = re.search(r'(\d+)', text)
        if num_match:
            return int(num_match.group(1))
        
    except (ValueError, AttributeError):
        pass
    
    return None


def parse_budget_from_query(query: str) -> BudgetRange:
    """
    Parse budget constraints from a natural language query.
    
    Patterns supported:
        "under 50k" -> max=50000
        "below 1.5 lakh" -> max=150000
        "above 80000" -> min=80000
        "between 50k and 80k" -> min=50000, max=80000
        "around 60k" -> min=45000, max=75000 (±25%)
        "under ₹45,000" -> max=45000
    
    Returns:
        BudgetRange with parsed constraints
    """
    query_lower = query.lower()
    
    # Pattern: between X and Y
    between_match = re.search(
        r'between\s+([\d.]+\s*(?:k|lakh?|l)?)\s*(?:and|to|-)\s*([\d.]+\s*(?:k|lakh?|l)?)',
        query_lower,
        re.IGNORECASE
    )
    if between_match:
        min_price = _parse_indian_price(between_match.group(1))
        max_price = _parse_indian_price(between_match.group(2))
        return BudgetRange(min_price=min_price, max_price=max_price)
    
    # Pattern: X to Y (e.g., "50k to 80k")
    range_match = re.search(
        r'([\d.]+\s*(?:k|lakh?|l)?)\s*(?:to|-)\s*([\d.]+\s*(?:k|lakh?|l)?)',
        query_lower
    )
    if range_match:
        min_price = _parse_indian_price(range_match.group(1))
        max_price = _parse_indian_price(range_match.group(2))
        if min_price and max_price and min_price < max_price:
            return BudgetRange(min_price=min_price, max_price=max_price)
    
    # Pattern: under/below X
    under_match = re.search(
        r'(?:under|below|less than|max|upto|up to)\s*₹?\s*([\d.,]+\s*(?:k|lakh?|l)?)',
        query_lower
    )
    if under_match:
        max_price = _parse_indian_price(under_match.group(1))
        return BudgetRange(max_price=max_price)
    
    # Pattern: above/over X
    above_match = re.search(
        r'(?:above|over|more than|min|atleast|at least)\s*₹?\s*([\d.,]+\s*(?:k|lakh?|l)?)',
        query_lower
    )
    if above_match:
        min_price = _parse_indian_price(above_match.group(1))
        return BudgetRange(min_price=min_price)
    
    # Pattern: around X (±25%)
    around_match = re.search(
        r'(?:around|about|approximately|~)\s*₹?\s*([\d.,]+\s*(?:k|lakh?|l)?)',
        query_lower
    )
    if around_match:
        center = _parse_indian_price(around_match.group(1))
        if center:
            return BudgetRange(
                min_price=int(center * 0.75),
                max_price=int(center * 1.25)
            )
    
    # No budget constraint found
    return BudgetRange()


# ============================================================
# URL Utilities
# ============================================================

def extract_domain(url: str) -> str:
    """
    Extract base domain from URL.
    
    Examples:
        "https://www.amazon.in/dp/123" -> "amazon.in"
        "https://flipkart.com/product" -> "flipkart.com"
        "amazon.in" -> "amazon.in"
    """
    try:
        # Handle URLs without scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        
        return domain
    except Exception:
        return "unknown"


# Product page patterns for major sites
PRODUCT_PAGE_PATTERNS = {
    "amazon": [
        r'/dp/[A-Z0-9]{10}',           # /dp/B0EXAMPLE
        r'/gp/product/[A-Z0-9]{10}',   # /gp/product/B0EXAMPLE
    ],
    "flipkart": [
        r'/p/[a-z0-9]+',               # /p/itm123
        r'pid=[A-Z0-9]+',              # ?pid=EXAMPLE
    ],
}

def is_product_page(url: str) -> bool:
    """
    Check if URL is a single product page (not listing/search).
    
    Returns:
        True if URL looks like a product page.
    """
    domain = extract_domain(url)
    url_lower = url.lower()
    
    # Check known patterns
    for site, patterns in PRODUCT_PAGE_PATTERNS.items():
        if site in domain:
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
    
    # Generic heuristics
    # Avoid listing/category pages
    if any(x in url_lower for x in ['/s?', '/search', '/category/', '/browse/', '/store/']):
        return False
    
    # Product pages often have long alphanumeric IDs
    if re.search(r'/[A-Za-z0-9_-]{8,}', url):
        return True
    
    return False


# ============================================================
# Query Normalization
# ============================================================

FILLER_WORDS = {
    'find', 'search', 'for', 'the', 'a', 'an', 'best', 'top', 'good',
    'show', 'me', 'get', 'price', 'prices', 'of', 'in', 'india',
    'amazon', 'flipkart', 'online', 'buy', 'cheap', 'cheapest',
    'need', 'want', 'looking', 'please', 'help', 'suggest',
}

def normalize_search_query(query: str) -> str:
    """
    Normalize a search query for cache key generation.
    
    - Lowercase
    - Remove filler words
    - Sort remaining words
    - Join with underscore
    
    Examples:
        "Find me the best laptop under 50k" -> "50k_laptop_under"
        "iPhone 15 price in India" -> "15_iphone"
    """
    words = query.lower().split()
    
    # Filter out filler words and short words
    significant = [w for w in words if w not in FILLER_WORDS and len(w) > 2]
    
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for w in significant:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    
    # Sort for consistent cache keys
    unique.sort()
    
    return '_'.join(unique)
