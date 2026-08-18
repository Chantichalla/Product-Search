"""
CSS-Based Product Extraction (Zero LLM Cost)

Uses Crawl4AI's JsonCssExtractionStrategy for lightning-fast extraction.
Site-specific schemas for Amazon and Flipkart.

Performance:
- CSS extraction: ~15ms per page
- Regex fallback: ~50ms per page
- LLM fallback: 30-120s per page (avoid!)
"""

import re
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field


# ============================================================
# EXTRACTION SCHEMA (Shared with llm_extraction.py)
# ============================================================

class CSSExtractedProduct(BaseModel):
    """Product data extracted via CSS selectors."""
    name: str = Field(..., description="Product title")
    url: str = Field(default="", description="Source URL")
    site: str = Field(default="unknown", description="Site name")
    
    # Pricing
    price: Optional[int] = Field(default=None, description="Price in INR")
    original_price: Optional[int] = Field(default=None, description="MRP")
    
    # Product details
    brand: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None)
    
    # Specs
    ram_gb: Optional[int] = Field(default=None)
    storage_gb: Optional[int] = Field(default=None)
    
    # Ratings
    rating: Optional[float] = Field(default=None)
    rating_count: Optional[int] = Field(default=None)
    
    # Availability
    in_stock: bool = Field(default=True)


# ============================================================
# CSS SELECTORS BY SITE
# ============================================================

AMAZON_SELECTORS = {
    "name": [
        "#productTitle",
        "#title span",
        "h1.a-size-large",
    ],
    "price": [
        ".a-price-whole",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price .a-offscreen",
        "#corePrice_feature_div .a-price-whole",
    ],
    "original_price": [
        ".a-text-price .a-offscreen",
        "#listPrice .a-offscreen",
        ".basisPrice .a-offscreen",
    ],
    "rating": [
        "#acrPopover",
        "span.a-icon-alt",
        "#averageCustomerReviews span",
    ],
    "rating_count": [
        "#acrCustomerReviewText",
    ],
    "in_stock": [
        "#availability span",
        "#outOfStock",
    ],
    "brand": [
        "#bylineInfo",
        "a#bylineInfo",
    ],
}

FLIPKART_SELECTORS = {
    "name": [
        "span.VU-ZEz",
        "h1.yhB1nd",
        "span.B_NuCI",
        ".G6XhRU",
        "h1._6EBuvT",           # New 2024
        "span.mEh187",          # New 2024
    ],
    "price": [
        "div.Nx9bqj._CxhGH",
        "div._30jeq3._16Jk6d",
        "div._30jeq3",
        "div.Nx9bqj",           # New 2024
    ],
    "original_price": [
        "div.yRaY8j.A6+E6v",
        "div._3I9_wc._2p6lqe",
        "div.yRaY8j",           # New 2024
    ],
    "rating": [
        "div.XQDdHH",
        "div._3LWZlK",
    ],
    "rating_count": [
        "span.Wphh3N span",
        "span._2_R_DZ",
    ],
    "in_stock": [
        "._16FRp0",
        "._3XINqE",
        ".UOCQB1",              # New "Sold Out" badge
    ],
    "brand": [
        "span.mEh114",
    ],
}


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def _parse_price(text: str) -> Optional[int]:
    """Extract integer price from text like '₹45,999' or '45999'."""
    if not text:
        return None
    # Remove currency symbols, commas, spaces
    cleaned = re.sub(r'[₹,\s]', '', text)
    # Extract first number sequence
    match = re.search(r'(\d+)', cleaned)
    if match:
        try:
            return int(match.group(1))
        except:
            pass
    return None


def _parse_rating(text: str) -> Optional[float]:
    """Extract rating like '4.5 out of 5' -> 4.5."""
    if not text:
        return None
    match = re.search(r'(\d+\.?\d*)', text)
    if match:
        try:
            rating = float(match.group(1))
            return rating if 0 <= rating <= 5 else None
        except:
            pass
    return None


def _parse_rating_count(text: str) -> Optional[int]:
    """Extract count like '2,345 ratings' -> 2345."""
    if not text:
        return None
    cleaned = re.sub(r'[,\s]', '', text)
    match = re.search(r'(\d+)', cleaned)
    if match:
        try:
            return int(match.group(1))
        except:
            pass
    return None


def _check_in_stock(text: str) -> bool:
    """Check if product is in stock from availability text."""
    if not text:
        return True  # Assume in stock if no info
    text_lower = text.lower().strip()
    out_of_stock_indicators = [
        'out of stock', 'unavailable', 'currently unavailable',
        'not available', 'sold out', 'coming soon'
    ]
    return not any(ind in text_lower for ind in out_of_stock_indicators)


def _extract_field(soup: BeautifulSoup, selectors: list) -> Optional[str]:
    """Try multiple selectors and return first match."""
    for selector in selectors:
        try:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text:
                    return text
        except:
            continue
    return None


def extract_amazon(html: str, url: str) -> Optional[CSSExtractedProduct]:
    """Extract product from Amazon HTML using CSS selectors."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        name = _extract_field(soup, AMAZON_SELECTORS["name"])
        name = _extract_field(soup, AMAZON_SELECTORS["name"])
        if not name:
            # Debug: what page did we actually get?
            page_title = soup.title.string.strip() if soup.title else "No Title Tag"
            print(f"  [CSS Amazon] FAIL: '{url[:30]}...' -> Page Title: '{page_title}'")
            # If it's a captcha/bot check, explicitly say so
            if "Robot Check" in page_title or "Captcha" in page_title or "503" in page_title:
                print("  [CSS Amazon] ⚠️ BLOCKED BY BOT PROTECTION")
            return None
        
        price_text = _extract_field(soup, AMAZON_SELECTORS["price"])
        price = _parse_price(price_text)
        if not price:
             print(f"  [CSS Amazon] Price not found for {url[:40]}...")
        
        original_text = _extract_field(soup, AMAZON_SELECTORS["original_price"])
        original_price = _parse_price(original_text)
        
        rating_text = _extract_field(soup, AMAZON_SELECTORS["rating"])
        rating = _parse_rating(rating_text)
        
        rating_count_text = _extract_field(soup, AMAZON_SELECTORS["rating_count"])
        rating_count = _parse_rating_count(rating_count_text)
        
        stock_text = _extract_field(soup, AMAZON_SELECTORS["in_stock"])
        in_stock = _check_in_stock(stock_text)
        
        brand = _extract_field(soup, AMAZON_SELECTORS["brand"])
        
        return CSSExtractedProduct(
            name=name[:200],
            url=url,
            site="amazon",
            price=price,
            original_price=original_price,
            rating=rating,
            rating_count=rating_count,
            in_stock=in_stock,
            brand=brand,
        )
    except Exception as e:
        print(f"  [CSS Amazon] Error: {e}")
        return None


def extract_flipkart(html: str, url: str) -> Optional[CSSExtractedProduct]:
    """Extract product from Flipkart HTML using CSS selectors."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        name = _extract_field(soup, FLIPKART_SELECTORS["name"])
        if not name:
            print(f"  [CSS Flipkart] Title not found for {url[:40]}...")
            return None
        
        price_text = _extract_field(soup, FLIPKART_SELECTORS["price"])
        price = _parse_price(price_text)
        if not price:
             print(f"  [CSS Flipkart] Price not found for {url[:40]}...")
        
        original_text = _extract_field(soup, FLIPKART_SELECTORS["original_price"])
        original_price = _parse_price(original_text)
        
        rating_text = _extract_field(soup, FLIPKART_SELECTORS["rating"])
        rating = _parse_rating(rating_text)
        
        rating_count_text = _extract_field(soup, FLIPKART_SELECTORS["rating_count"])
        rating_count = _parse_rating_count(rating_count_text)
        
        stock_text = _extract_field(soup, FLIPKART_SELECTORS["in_stock"])
        in_stock = _check_in_stock(stock_text) if stock_text else True
        
        brand = _extract_field(soup, FLIPKART_SELECTORS["brand"])
        
        return CSSExtractedProduct(
            name=name[:200],
            url=url,
            site="flipkart",
            price=price,
            original_price=original_price,
            rating=rating,
            rating_count=rating_count,
            in_stock=in_stock,
            brand=brand,
        )
    except Exception as e:
        print(f"  [CSS Flipkart] Error: {e}")
        return None


def extract_with_css(html: str, url: str) -> Optional[CSSExtractedProduct]:
    """
    Main extraction function - auto-detects site and uses appropriate extractor.
    
    Returns:
        CSSExtractedProduct or None if extraction fails
    """
    url_lower = url.lower()
    
    if "amazon" in url_lower:
        return extract_amazon(html, url)
    elif "flipkart" in url_lower:
        return extract_flipkart(html, url)
    else:
        # Unknown site - do not force Amazon selectors
        # This allows fallback to Regex/LLM for sites like Croma/Samsung
        return None


def extract_products_css(pages: Dict[str, Dict[str, Any]]) -> list:
    """
    Extract products from multiple pages using CSS selectors.
    
    Args:
        pages: Dict mapping URL -> {"markdown": str, "raw_markdown": str, ...}
        
    Returns:
        List of CSSExtractedProduct
    """
    results = []
    
    for url, data in pages.items():
        # Use raw_markdown which contains HTML
        html = data.get("raw_markdown", data.get("markdown", ""))
        if not html:
            continue
            
        product = extract_with_css(html, url)
        if product:
            results.append(product)
            print(f"  [CSS OK] {product.name[:40]}... -> ₹{product.price}")
        else:
            print(f"  [CSS MISS] {url[:50]}...")
    
    return results


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    # Test with sample HTML
    sample_amazon = """
    <div id="dp-container">
        <h1 id="productTitle">Apple iPhone 15 Pro (256 GB) - Natural Titanium</h1>
        <span class="a-price-whole">1,34,900</span>
        <span class="a-text-price"><span class="a-offscreen">₹1,49,900</span></span>
        <span class="a-icon-alt">4.5 out of 5 stars</span>
        <span id="acrCustomerReviewText">12,345 ratings</span>
        <span id="availability"><span>In Stock</span></span>
        <a id="bylineInfo">Brand: Apple</a>
    </div>
    """
    
    result = extract_amazon(sample_amazon, "https://amazon.in/dp/test")
    if result:
        print("✅ Amazon extraction successful!")
        print(result.model_dump_json(indent=2))
    else:
        print("❌ Amazon extraction failed")
