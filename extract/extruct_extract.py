"""
Enhanced Product Extraction with extruct + selectolax

Priority extraction pipeline:
1. extruct (JSON-LD) - Most reliable when available (~80% of major sites)
2. selectolax (CSS)  - Fast fallback for structured elements
3. Regex patterns    - Last resort for price/specs

Performance:
- extruct JSON-LD:  ~5ms (instant, structured data)
- selectolax CSS:   ~10ms (10-30x faster than BeautifulSoup)
- Regex:            ~50ms
"""

import re
import json
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

# Lazy imports to avoid startup cost
_extruct = None
_HTMLParser = None


def _get_extruct():
    """Lazy load extruct."""
    global _extruct
    if _extruct is None:
        import extruct
        _extruct = extruct
    return _extruct


def _get_selectolax():
    """Lazy load selectolax HTMLParser."""
    global _HTMLParser
    if _HTMLParser is None:
        from selectolax.parser import HTMLParser
        _HTMLParser = HTMLParser
    return _HTMLParser


# ============================================================
# DATA MODEL
# ============================================================

class ExtractedProductV2(BaseModel):
    """Product data with extraction source tracking."""
    name: str = Field(..., description="Product title")
    url: str = Field(default="", description="Source URL")
    site: str = Field(default="unknown", description="Site name")
    
    # Pricing
    price: Optional[int] = Field(default=None, description="Price in INR")
    original_price: Optional[int] = Field(default=None, description="MRP")
    currency: str = Field(default="INR")
    
    # Product details
    brand: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    image_url: Optional[str] = Field(default=None)
    
    # Specs
    ram_gb: Optional[int] = Field(default=None)
    storage_gb: Optional[int] = Field(default=None)
    
    # Ratings
    rating: Optional[float] = Field(default=None, le=5.0, ge=0.0)
    rating_count: Optional[int] = Field(default=None)
    
    # Availability
    in_stock: bool = Field(default=True)
    
    # Extraction metadata
    extraction_method: str = Field(default="unknown", description="jsonld, css, or regex")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ============================================================
# JSON-LD EXTRACTION (extruct)
# ============================================================

def extract_jsonld(html: str, url: str) -> Optional[ExtractedProductV2]:
    """
    Extract product data from JSON-LD structured data.
    
    JSON-LD is embedded in <script type="application/ld+json"> tags.
    Major e-commerce sites (Amazon, Flipkart) use this for SEO.
    
    Returns:
        ExtractedProductV2 or None if no product data found
    """
    try:
        extruct = _get_extruct()
        data = extruct.extract(html, syntaxes=['json-ld'], uniform=True)
        
        jsonld_items = data.get('json-ld', [])
        if not jsonld_items:
            return None
        
        # Find Product schema
        product_data = None
        for item in jsonld_items:
            item_type = item.get('@type', '')
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else ''
            
            if item_type.lower() == 'product':
                product_data = item
                break
        
        if not product_data:
            return None
        
        # Extract fields
        name = product_data.get('name', '')
        if not name:
            return None
        
        # Price extraction (can be nested in offers)
        price = None
        original_price = None
        in_stock = True
        
        offers = product_data.get('offers', {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        
        if offers:
            price_str = offers.get('price') or offers.get('lowPrice')
            if price_str:
                try:
                    price = int(float(str(price_str).replace(',', '')))
                except:
                    pass
            
            availability = offers.get('availability', '')
            if 'OutOfStock' in str(availability):
                in_stock = False
        
        # Rating
        rating = None
        rating_count = None
        aggregate_rating = product_data.get('aggregateRating', {})
        if aggregate_rating:
            try:
                rating = float(aggregate_rating.get('ratingValue', 0))
                if rating > 5:
                    rating = None  # Invalid
            except:
                pass
            try:
                rating_count = int(aggregate_rating.get('ratingCount') or aggregate_rating.get('reviewCount') or 0)
            except:
                pass
        
        # Brand
        brand = None
        brand_data = product_data.get('brand', {})
        if isinstance(brand_data, dict):
            brand = brand_data.get('name')
        elif isinstance(brand_data, str):
            brand = brand_data
        
        # Image
        image_url = None
        image = product_data.get('image', [])
        if isinstance(image, list) and image:
            image_url = image[0] if isinstance(image[0], str) else image[0].get('url')
        elif isinstance(image, str):
            image_url = image
        
        # Detect site
        site = "unknown"
        if "amazon" in url.lower():
            site = "amazon"
        elif "flipkart" in url.lower():
            site = "flipkart"
        elif "croma" in url.lower():
            site = "croma"
        
        return ExtractedProductV2(
            name=name[:200],
            url=url,
            site=site,
            price=price,
            original_price=original_price,
            brand=brand,
            image_url=image_url,
            rating=rating,
            rating_count=rating_count,
            in_stock=in_stock,
            extraction_method="jsonld",
            confidence=0.95 if price else 0.7,
        )
        
    except Exception as e:
        print(f"  [JSON-LD] Error: {e}")
        return None


# ============================================================
# CSS EXTRACTION (selectolax)
# ============================================================

# Site-specific selectors
SELECTOLAX_SELECTORS = {
    "amazon": {
        "name": ["#productTitle", "#title span", "h1.a-size-large"],
        "price": [".a-price-whole", "#priceblock_ourprice", "#corePrice_feature_div .a-price-whole"],
        "rating": ["#acrPopover", "span.a-icon-alt"],
        "brand": ["#bylineInfo", "a#bylineInfo"],
    },
    "flipkart": {
        "name": ["span.VU-ZEz", "h1.yhB1nd", "span.B_NuCI", "h1._6EBuvT"],
        "price": ["div.Nx9bqj", "div._30jeq3"],
        "rating": ["div.XQDdHH", "div._3LWZlK"],
        "brand": ["span.mEh114"],
    },
}


def extract_with_selectolax(html: str, url: str) -> Optional[ExtractedProductV2]:
    """
    Extract product data using selectolax (fast CSS parser).
    
    10-30x faster than BeautifulSoup for large HTML documents.
    """
    try:
        HTMLParser = _get_selectolax()
        tree = HTMLParser(html)
        
        # Detect site
        site = "unknown"
        selectors = {}
        if "amazon" in url.lower():
            site = "amazon"
            selectors = SELECTOLAX_SELECTORS["amazon"]
        elif "flipkart" in url.lower():
            site = "flipkart"
            selectors = SELECTOLAX_SELECTORS["flipkart"]
        else:
            return None  # No selectors for this site
        
        def get_text(selector_list: List[str]) -> Optional[str]:
            """Try multiple selectors, return first match."""
            for selector in selector_list:
                try:
                    node = tree.css_first(selector)
                    if node:
                        text = node.text(strip=True)
                        if text:
                            return text
                except:
                    continue
            return None
        
        # Extract name
        name = get_text(selectors.get("name", []))
        if not name:
            return None
        
        # Extract price
        price = None
        price_text = get_text(selectors.get("price", []))
        if price_text:
            # Parse Indian price format
            cleaned = re.sub(r'[₹,\s]', '', price_text)
            match = re.search(r'(\d+)', cleaned)
            if match:
                try:
                    price = int(match.group(1))
                    if price < 100 or price > 1000000:
                        price = None  # Invalid range
                except:
                    pass
        
        # Extract rating
        rating = None
        rating_text = get_text(selectors.get("rating", []))
        if rating_text:
            match = re.search(r'(\d+\.?\d*)', rating_text)
            if match:
                try:
                    rating = float(match.group(1))
                    if rating > 5:
                        rating = None
                except:
                    pass
        
        # Extract brand
        brand = get_text(selectors.get("brand", []))
        
        return ExtractedProductV2(
            name=name[:200],
            url=url,
            site=site,
            price=price,
            brand=brand,
            rating=rating,
            extraction_method="css",
            confidence=0.8 if price else 0.5,
        )
        
    except Exception as e:
        print(f"  [selectolax] Error: {e}")
        return None


# ============================================================
# LLM EXTRACTION (Gemini Flash) - NEW: For sites without JSON-LD
# ============================================================

LLM_EXTRACTION_PROMPT = """Extract product information from this e-commerce page content.

Content (truncated):
{content}

URL: {url}

Extract ONLY these fields as JSON:
{{
    "name": "exact product name with variant",
    "price": integer price in INR (no commas, just number),
    "original_price": MRP if different from price,
    "brand": "brand name",
    "ram_gb": integer RAM in GB if applicable,
    "storage_gb": integer storage in GB if applicable,
    "rating": float rating out of 5,
    "in_stock": boolean
}}

IMPORTANT:
- price MUST be an integer (e.g., 73999 not "₹73,999")
- If you can't find a field, use null
- Only extract from the MAIN product, not related products
- Return ONLY the JSON, no explanation"""


def extract_with_llm(html: str, url: str, fit_markdown: str = None) -> Optional[ExtractedProductV2]:
    """
    Extract product data using Gemini Flash LLM.
    
    This is more reliable than regex for sites without JSON-LD (Flipkart, Amazon).
    Uses fit_markdown when available for 80% token reduction.
    
    Args:
        html: Raw HTML content (fallback)
        url: Source URL
        fit_markdown: Optional pruned markdown for token efficiency
    """
    try:
        from config.llm_config import get_google_lite
        llm = get_google_lite()
        
        if not llm:
            return None
        
        # Prefer fit_markdown for token efficiency (80% fewer tokens)
        if fit_markdown and len(fit_markdown) > 500:
            content = fit_markdown[:6000]  # Already pruned, can use more
            print(f"  [llm] Using fit_markdown ({len(content)} chars)")
        else:
            # Fallback to HTML, truncated
            content = html[:8000] if len(html) > 8000 else html
        
        # Clean up the content a bit
        import re as regex_module
        content = regex_module.sub(r'<script[^>]*>.*?</script>', '', content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        content = regex_module.sub(r'<style[^>]*>.*?</style>', '', content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
        content = regex_module.sub(r'<[^>]+>', ' ', content)  # Remove HTML tags
        content = regex_module.sub(r'\s+', ' ', content)  # Normalize whitespace
        content = content[:4000]  # Final truncation
        
        prompt = LLM_EXTRACTION_PROMPT.format(content=content, url=url)
        response = llm.invoke(prompt)
        
        # Parse JSON from response
        response_text = response.strip() if isinstance(response, str) else response
        
        # Try to find JSON in response
        json_match = regex_module.search(r'\{[^{}]*\}', str(response_text), regex_module.DOTALL)
        if not json_match:
            return None
        
        data = json.loads(json_match.group(0))
        
        if not data.get('name') or not data.get('price'):
            return None
        
        # Determine site from URL
        site = "Store"
        if "flipkart" in url.lower():
            site = "Flipkart"
        elif "amazon" in url.lower():
            site = "Amazon"
        elif "croma" in url.lower():
            site = "Croma"
        
        return ExtractedProductV2(
            name=data.get('name', ''),
            url=url,
            site=site,
            price=int(data['price']) if data.get('price') else None,
            original_price=int(data['original_price']) if data.get('original_price') else None,
            brand=data.get('brand'),
            ram_gb=int(data['ram_gb']) if data.get('ram_gb') else None,
            storage_gb=int(data['storage_gb']) if data.get('storage_gb') else None,
            rating=float(data['rating']) if data.get('rating') else None,
            in_stock=data.get('in_stock', True),
            extraction_method="llm",
            confidence=0.85,  # LLM extraction is fairly reliable
        )
        
    except Exception as e:
        print(f"  [llm] Error: {e}")
        return None


# ============================================================
# REGEX EXTRACTION (Fallback)
# ============================================================

def extract_with_regex(html: str, url: str) -> Optional[ExtractedProductV2]:
    """
    Fallback regex extraction for when JSON-LD and CSS fail.
    Works on markdown or raw HTML.
    """
    try:
        # Detect site
        site = "unknown"
        if "amazon" in url.lower():
            site = "amazon"
        elif "flipkart" in url.lower():
            site = "flipkart"
        
        # Title extraction - skip navigation items
        title = None
        ignored = ['skip to', 'menu', 'search', 'sign in', 'cart', 'keyboard shortcuts']
        
        for match in re.finditer(r'^#\s*(.+?)$', html, re.MULTILINE):
            text = match.group(1).strip()
            if len(text) > 10 and not any(x in text.lower() for x in ignored):
                title = text
                break
        
        if not title:
            # Try bold text
            for match in re.finditer(r'\*\*(.+?)\*\*', html):
                text = match.group(1).strip()
                if len(text) > 10 and not any(x in text.lower() for x in ignored):
                    title = text
                    break
        
        if not title:
            return None
        
        # Price extraction - IMPROVED: prefer higher prices, find most common
        price = None
        
        # Look for prices with currency symbol first (more reliable)
        price_patterns = [
            r'₹\s?([0-9,]+)',           # ₹76,999
            r'Rs\.?\s?([0-9,]+)',        # Rs. 76,999
            r'"price"\s*:\s*"?(\d+)"?',  # "price": 76999
        ]
        
        all_prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, html[:30000])  # Search more content
            for match in matches:
                try:
                    p = int(match.replace(',', ''))
                    # For phones/electronics: valid range is 5000 to 500000
                    if 5000 <= p <= 500000:
                        all_prices.append(p)
                except:
                    continue
        
        if all_prices:
            # Find the most common price (the actual product price appears multiple times)
            from collections import Counter
            price_counts = Counter(all_prices)
            # Get the most common price that's above 10000 (likely the real price)
            for p, count in price_counts.most_common():
                if p >= 10000:  # Phones usually cost 10k+
                    price = p
                    break
            # If no price >= 10000, take the most common one
            if not price:
                price = price_counts.most_common(1)[0][0]
        
        # Rating extraction - must have decimal
        rating = None
        rating_patterns = [
            r'(\d\.\d)\s*(?:out of 5|/5|stars)',
            r'rating[:\s]+(\d\.\d)',
        ]
        for pattern in rating_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    rating = float(match.group(1))
                    if 0 <= rating <= 5:
                        break
                    else:
                        rating = None
                except:
                    pass
        
        # Extract RAM and Storage from title
        ram_gb = None
        storage_gb = None
        
        # RAM patterns: "12 GB RAM", "12GB RAM", "(12 GB RAM)"
        ram_match = re.search(r'(\d+)\s*GB\s*RAM', title, re.IGNORECASE)
        if ram_match:
            ram_gb = int(ram_match.group(1))
        
        # Storage patterns: "256 GB Storage", "256GB", "(256 GB)"
        storage_match = re.search(r'(\d+)\s*GB(?:\s*Storage|\s*ROM|\)|,)', title, re.IGNORECASE)
        if not storage_match:
            # Try simpler pattern: just digits followed by GB (not RAM)
            for match in re.finditer(r'(\d+)\s*GB', title, re.IGNORECASE):
                val = int(match.group(1))
                # Storage is usually 64, 128, 256, 512, 1024
                if val in [64, 128, 256, 512, 1024]:
                    storage_gb = val
                    break
        else:
            storage_gb = int(storage_match.group(1))
        
        # Extract brand from title
        brand = None
        brands = ['iQOO', 'Samsung', 'Apple', 'iPhone', 'Xiaomi', 'Redmi', 'OnePlus', 
                  'Realme', 'POCO', 'Vivo', 'Oppo', 'Motorola', 'Nokia', 'Google']
        for b in brands:
            if b.lower() in title.lower():
                brand = b
                break
        
        return ExtractedProductV2(
            name=title[:200],
            url=url,
            site=site,
            price=price,
            rating=rating,
            ram_gb=ram_gb,
            storage_gb=storage_gb,
            brand=brand,
            extraction_method="regex",
            confidence=0.5 if price else 0.3,
        )
        
    except Exception as e:
        print(f"  [Regex] Error: {e}")
        return None


# ============================================================
# UNIVERSAL LIST PAGE EXTRACTION (LLM-based - works on ANY site)
# ============================================================

LIST_EXTRACTION_PROMPT = """Analyze this page and determine its type.

URL: {url}
Content:
{content}

DETERMINE PAGE TYPE:
1. "list" - A "best products" page with multiple ranked recommendations
2. "single" - A single product page with details/specs
3. "other" - Article, news, search page, or anything else

RESPOND WITH JSON ONLY:

If LIST page (rankings/recommendations), extract ALL products:
{{"type": "list", "products": [
    {{"name": "Full Product Name with variant", "price_hint": 79999, "rank": 1, "highlights": "key features mentioned"}},
    {{"name": "Second Product Name", "price_hint": 64999, "rank": 2, "highlights": "key features"}},
    ...
]}}

If SINGLE product page:
{{"type": "single", "product": {{"name": "Product Name", "price": 79999, "brand": "Brand", "specs": "key specs"}}}}

If NEITHER (article, news, search page):
{{"type": "other", "reason": "why this is not a product page"}}

RULES:
- price_hint can be approximate (from the list page)
- rank = position in list (1 = best/first)
- Extract ALL products mentioned, not just the first few
- Return ONLY valid JSON, no explanation"""


def extract_products_universal(html: str, url: str, fit_markdown: str = None) -> dict:
    """
    Universal product extraction - works on ANY site.
    
    Uses LLM to detect page type and extract accordingly:
    - List pages: Returns all products with ranks
    - Single product: Returns product details
    - Other: Returns empty
    
    Args:
        html: Raw HTML content
        url: Source URL
        fit_markdown: Optional pruned markdown (preferred for efficiency)
        
    Returns:
        dict with keys:
        - "type": "list" | "single" | "other"
        - "products": list of products (for list pages)
        - "product": single product (for single pages)
    """
    try:
        from config.llm_config import get_google_lite
        llm = get_google_lite()
        
        if not llm:
            print("  [universal] ⚠️ No LLM available")
            return {"type": "other", "reason": "LLM unavailable"}
        
        # IMPORTANT: fit_markdown often strips product data, use raw_markdown instead
        # Try to find the best content source in order of preference
        import re as regex_module
        
        # Get raw_markdown from the page_data (passed via fit_markdown parameter for compatibility)
        raw_markdown = fit_markdown  # The caller passes whatever markdown is available
        
        if raw_markdown and len(raw_markdown) > 500:
            # Use raw_markdown but intelligently truncate to focus on product content
            # Skip first ~500 chars (usually navigation) and last ~500 chars (usually footer)
            content = raw_markdown
            
            # If content is very long, try to find the main product section
            if len(content) > 10000:
                # Look for common product list indicators
                product_indicators = ['₹', 'Rs.', 'price', 'Price', 'RAM', 'SSD', 'processor']
                best_start = 0
                
                # Find where product content likely starts
                for indicator in product_indicators:
                    pos = content.find(indicator)
                    if pos > 0 and pos < 5000:
                        # Found indicator early, content probably starts near beginning
                        break
                    elif pos > 5000:
                        # Found indicator later, skip navigation
                        best_start = max(best_start, pos - 200)
                        break
                
                # Take 8000 chars from the best starting position
                content = content[best_start:best_start + 8000]
            else:
                content = content[:8000]
            
            print(f"  [universal] Using raw_markdown ({len(content)} chars)")
        elif html and len(html) > 500:
            # Fallback: Clean HTML
            content = html[:15000] if len(html) > 15000 else html
            content = regex_module.sub(r'<script[^>]*>.*?</script>', '', content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
            content = regex_module.sub(r'<style[^>]*>.*?</style>', '', content, flags=regex_module.DOTALL | regex_module.IGNORECASE)
            content = regex_module.sub(r'<[^>]+>', ' ', content)
            content = regex_module.sub(r'\s+', ' ', content)
            content = content[:8000]
            print(f"  [universal] Using cleaned HTML ({len(content)} chars)")
        else:
            print(f"  [universal] ⚠️ No usable content")
            return {"type": "other", "reason": "No content available"}
        
        prompt = LIST_EXTRACTION_PROMPT.format(content=content, url=url)
        response = llm.invoke(prompt)
        
        # Parse JSON from response
        response_text = str(response).strip() if not isinstance(response, str) else response.strip()
        
        # Extract JSON from response
        import re as regex_module
        # Try to find JSON object
        json_match = regex_module.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            print(f"  [universal] ⚠️ No JSON in response")
            return {"type": "other", "reason": "No JSON in LLM response"}
        
        data = json.loads(json_match.group(0))
        
        page_type = data.get("type", "other")
        
        if page_type == "list":
            products = data.get("products", [])
            print(f"  [universal] ✅ LIST page: {len(products)} products extracted")
            return {"type": "list", "products": products, "source_url": url}
            
        elif page_type == "single":
            product = data.get("product", {})
            print(f"  [universal] ✅ SINGLE product: {product.get('name', 'Unknown')[:40]}")
            return {"type": "single", "product": product, "source_url": url}
            
        else:
            reason = data.get("reason", "Unknown")
            print(f"  [universal] ℹ️ OTHER page: {reason[:50]}")
            return {"type": "other", "reason": reason}
        
    except json.JSONDecodeError as e:
        print(f"  [universal] ⚠️ JSON parse error: {e}")
        return {"type": "other", "reason": f"JSON parse error: {e}"}
    except Exception as e:
        print(f"  [universal] ⚠️ Error: {e}")
        return {"type": "other", "reason": str(e)}


def deduplicate_products(products: list) -> list:
    """
    Deduplicate products by fuzzy matching names.
    
    Uses simple normalization + substring matching.
    Products with same normalized name are merged, keeping lowest price_hint.
    
    Args:
        products: List of product dicts with 'name' key
        
    Returns:
        Deduplicated list, sorted by mention count (most mentioned first)
    """
    import re as regex_module
    
    def normalize_name(name: str) -> str:
        """Normalize product name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes/prefixes
        name = regex_module.sub(r'\s*\(.*?\)', '', name)  # Remove (2024) etc
        name = regex_module.sub(r'\s*-\s*\d+gb.*', '', name)  # Remove -8GB RAM etc
        name = regex_module.sub(r'[^\w\s]', '', name)  # Remove special chars
        name = regex_module.sub(r'\s+', ' ', name).strip()
        return name
    
    # Group by normalized name
    groups = {}
    for product in products:
        if not product.get('name'):
            continue
        key = normalize_name(product['name'])
        if not key:
            continue
            
        if key not in groups:
            groups[key] = {
                'names': [],
                'price_hints': [],
                'ranks': [],
                'sources': [],
                'highlights': []
            }
        
        groups[key]['names'].append(product.get('name', ''))
        if product.get('price_hint'):
            groups[key]['price_hints'].append(product['price_hint'])
        if product.get('rank'):
            groups[key]['ranks'].append(product['rank'])
        if product.get('source_url'):
            groups[key]['sources'].append(product['source_url'])
        if product.get('highlights'):
            groups[key]['highlights'].append(product['highlights'])
    
    # Merge groups into deduplicated products
    deduplicated = []
    for key, group in groups.items():
        # Pick the most complete name (longest)
        best_name = max(group['names'], key=len) if group['names'] else key
        
        # Use minimum price_hint (most conservative)
        price_hint = min(group['price_hints']) if group['price_hints'] else None
        
        # Average rank
        avg_rank = sum(group['ranks']) / len(group['ranks']) if group['ranks'] else 99
        
        deduplicated.append({
            'name': best_name,
            'price_hint': price_hint,
            'avg_rank': avg_rank,
            'mention_count': len(group['names']),  # How many sources mentioned this
            'sources': list(set(group['sources'])),
            'highlights': list(set(group['highlights']))[:3],  # Top 3 unique highlights
        })
    
    # Sort by mention count (most mentioned first), then by avg_rank
    deduplicated.sort(key=lambda x: (-x['mention_count'], x['avg_rank']))
    
    print(f"  [dedup] {len(products)} -> {len(deduplicated)} products")
    return deduplicated


# ============================================================
# MAIN EXTRACTION PIPELINE
# ============================================================

def extract_product_v2(html: str, url: str, fit_markdown: str = None) -> Optional[ExtractedProductV2]:
    """
    Main extraction function with priority pipeline (NO LLM - cost efficient):
    
    1. JSON-LD (extruct) - Best quality, instant (rarely available on Indian sites)
    2. CSS (selectolax) - Fast fallback for structured elements
    3. Regex - Last resort for basic price extraction
    
    NOTE: LLM extraction removed to save costs. If extraction fails,
    advisor will use raw fit_markdown for analysis.
    
    Args:
        html: Raw HTML content
        url: Source URL
        fit_markdown: Not used here (kept for API compatibility)
        
    Returns:
        ExtractedProductV2 or None if all methods fail
    """
    # 1. Try JSON-LD first (most reliable when available)
    # NOTE: Flipkart and Amazon do NOT have JSON-LD, so this will usually fail
    result = extract_jsonld(html, url)
    if result and result.name:
        print(f"  [extruct] ✅ JSON-LD: {result.name[:40]}... -> ₹{result.price}")
        return result
    
    # 2. Try selectolax CSS
    result = extract_with_selectolax(html, url)
    if result and result.name and result.price:
        print(f"  [selectolax] ✅ CSS: {result.name[:40]}... -> ₹{result.price}")
        return result
    
    # 3. Fallback to regex (basic price only)
    result = extract_with_regex(html, url)
    if result and result.name:
        print(f"  [regex] ✅ Fallback: {result.name[:40]}... -> ₹{result.price}")
        return result
    
    # NOTE: LLM extraction removed - advisor will use raw markdown
    print(f"  [extract_v2] ⚠️ Extraction failed for {url[:50]}... (advisor will use markdown)")
    return None


# ============================================================
# BATCH EXTRACTION
# ============================================================

def extract_products_v2(pages: Dict[str, Dict[str, Any]]) -> List[ExtractedProductV2]:
    """
    Extract products from multiple scraped pages.
    
    Args:
        pages: Dict mapping URL -> {"markdown": str, "raw_markdown": str, ...}
        
    Returns:
        List of successfully extracted products
    """
    results = []
    
    for url, data in pages.items():
        if not data.get("success"):
            continue
        
        # Prefer raw HTML for JSON-LD, fall back to markdown
        html = data.get("raw_markdown") or data.get("markdown", "")
        if not html:
            continue
        
        product = extract_product_v2(html, url)
        if product:
            results.append(product)
    
    return results


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    # Test with sample data
    sample_jsonld = '''
    <html>
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "iQOO 15 5G (Legend, 256GB)",
        "brand": {"@type": "Brand", "name": "iQOO"},
        "offers": {
            "@type": "Offer",
            "price": "76999",
            "priceCurrency": "INR"
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.5",
            "ratingCount": "1234"
        }
    }
    </script>
    </html>
    '''
    
    result = extract_product_v2(sample_jsonld, "https://www.flipkart.com/iqoo-15")
    if result:
        print("\n✅ Test passed!")
        print(result.model_dump_json(indent=2))
    else:
        print("❌ Test failed")
