"""
Product Extraction from Scraped Markdown

Single-product focused extraction with:
- Pydantic validation via ProductPage model
- Regex-first extraction (fast)
- Optional LLM fallback for complex cases

Usage:
    product = extract_product_from_markdown(
        markdown=result.markdown,
        url="https://amazon.in/dp/123",
        site="amazon",
    )
    if product.price:
        save_to_db(product)
"""

import re
from typing import Optional, Any
from pydantic import BaseModel, Field


class ProductPage(BaseModel):
    """
    Validated product data from a single product page.
    
    All fields are optional except site, url, and raw_title
    since extraction may be partial.
    """
    site: str = Field(..., description="Source site: 'amazon', 'flipkart', etc.")
    url: str = Field(..., description="Original URL")
    
    # Title/name
    raw_title: str = Field(..., description="Raw product title from page")
    normalized_model_name: str = Field(default="", description="Normalized name for matching")
    brand: Optional[str] = Field(default=None, description="Brand name")
    category: Optional[str] = Field(default=None, description="Product category")
    
    # Pricing
    price: Optional[int] = Field(default=None, description="Price in rupees (smallest unit)")
    currency: str = Field(default="INR", description="Currency code")
    original_price: Optional[int] = Field(default=None, description="MRP/original price if discounted")
    discount_percent: Optional[int] = Field(default=None, description="Discount percentage")
    
    # Specs (laptop/phone specific)
    cpu: Optional[str] = Field(default=None)
    gpu: Optional[str] = Field(default=None)
    ram_gb: Optional[int] = Field(default=None)
    storage_gb: Optional[int] = Field(default=None)
    display: Optional[str] = Field(default=None)
    
    # Ratings
    rating: Optional[float] = Field(default=None, description="Rating out of 5")
    rating_count: Optional[int] = Field(default=None, description="Number of ratings")
    
    # Availability
    in_stock: bool = Field(default=True)
    
    # Extra data
    extra: dict = Field(default_factory=dict, description="Additional extracted data")


# ============================================================
# Price Parsing
# ============================================================

def parse_price(text: str) -> Optional[int]:
    """
    Parse Indian price from text.
    
    Examples:
        "₹45,999" -> 45999
        "Rs. 1,49,999" -> 149999
        "INR 50000" -> 50000
        "MRP: ₹1,25,000" -> 125000
    
    Returns:
        Price as integer (rupees), or None if parsing fails.
    """
    if not text:
        return None
    
    # Remove common prefixes
    text = re.sub(r'(?i)(MRP|Price|Rs\.?|INR|₹|:|\s)+', '', text)
    
    # Remove commas and spaces
    text = text.replace(',', '').replace(' ', '')
    
    # Extract first number
    match = re.search(r'\d+', text)
    if match:
        try:
            price = int(match.group())
            # Sanity check: price should be reasonable (₹100 to ₹10L)
            if 100 <= price <= 1000000:
                return price
        except ValueError:
            pass
    
    return None


def _extract_price_from_content(content: str) -> Optional[int]:
    """Extract price from page content using multiple patterns."""
    
    # First, try to find the main selling price (most reliable)
    selling_price_patterns = [
        r'"sellingPrice":\s*(\d+)',  # Flipkart JSON
        r'"price":\s*(\d+)',  # Generic JSON
        r'sellingPrice["\s:]+(\d+)',
        r'selling[_\- ]?price["\s:]+(\d+)',
    ]
    
    for pattern in selling_price_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            price = int(match.group(1))
            if 1000 <= price <= 1000000:
                return price
    
    # Look for price near keywords like "Price", "Buy Now", "Add to Cart"
    price_context_patterns = [
        r'(?:Price|Buy\s*Now|Add\s*to\s*Cart)[:\s]*₹\s*([\d,]+)',
        r'₹\s*([\d,]+)\s*(?:Price|Buy\s*Now)',
    ]
    
    for pattern in price_context_patterns:
        match = re.search(pattern, content[:10000], re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = int(price_str)
                if 1000 <= price <= 1000000:
                    return price
            except ValueError:
                pass
    
    # Fallback: find all prices and filter
    patterns = [
        r'₹\s?([\d,]+)',
        r'Rs\.?\s?([\d,]+)',
        r'INR\s?([\d,]+)',
        r'(\d{1,3},\d{2,3},?\d{0,3})',  # Indian format: 1,29,999 or 45,999
    ]
    
    prices = []
    for pattern in patterns:
        matches = re.findall(pattern, content[:10000])
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            price = parse_price(match)
            if price and 5000 <= price <= 1000000:  # Min ₹5,000 to avoid EMIs
                prices.append(price)
    
    if not prices:
        return None
    
    # Remove likely EMI amounts (common monthly payment values)
    emi_amounts = {
        999, 1499, 1999, 2499, 2999, 3499, 3999, 4499, 4999,
        5999, 6999, 7999, 8999, 9999,
        10999, 11000, 11999, 12999, 13999, 14556, 14999,
        15999, 16999, 17999, 18999, 19999,
        20999, 21999, 22999, 23999, 24999,
        25999, 26999, 27999, 28999, 29999, 30000,
        31999, 32999, 33999, 34999, 35999, 36999, 37999, 38999, 39999,
    }
    filtered = [p for p in prices if p not in emi_amounts]
    
    # If we have prices > ₹50,000, remove all prices < ₹40,000 (likely EMIs)
    high_prices = [p for p in filtered if p >= 50000]
    if high_prices:
        filtered = [p for p in filtered if p >= 40000]
    
    if filtered:
        # For electronics, return the MAX price (actual price, not discounted/EMI)
        return max(filtered)
    
    # Last resort: return max price
    return max(prices)


# ============================================================
# Title/Name Normalization
# ============================================================

def normalize_model_name(raw_title: str) -> str:
    """
    Normalize a product title for matching/lookup.
    
    Examples:
        "ASUS ROG Strix G16 (2024) Gaming Laptop" -> "asus_rog_strix_g16"
        "Apple iPhone 15 Pro Max 256GB" -> "apple_iphone_15_pro_max"
    
    Returns:
        Lowercase, underscore-separated name without filler words.
    """
    if not raw_title:
        return ""
    
    # Lowercase
    name = raw_title.lower().strip()
    
    # Remove parenthetical content like (2024), (Black), (8GB RAM)
    name = re.sub(r'\([^)]*\)', '', name)
    
    # Remove special characters except spaces and alphanumeric
    name = re.sub(r'[^a-z0-9\s]', '', name)
    
    # Remove filler words
    filler = {
        'new', 'latest', 'best', 'buy', 'sale', 'deal', 'offer',
        'laptop', 'phone', 'smartphone', 'gaming', 'with', 'and',
        'for', 'the', 'inch', 'cm', 'black', 'white', 'silver', 'grey', 'gray',
        'ssd', 'hdd', 'ram', 'gb', 'tb', 'display', 'screen',
    }
    
    words = name.split()
    words = [w for w in words if w not in filler and len(w) > 1]
    
    # Take first 6 significant words
    words = words[:6]
    
    return '_'.join(words)


# ============================================================
# Category Detection
# ============================================================

CATEGORY_KEYWORDS = {
    "laptop": ["laptop", "notebook", "macbook", "chromebook", "rog", "tuf", "legion", "ideapad", "thinkpad", "vivobook", "pavilion", "inspiron"],
    "phone": ["iphone", "smartphone", "mobile", "galaxy", "oneplus", "pixel", "redmi", "realme", "poco", "nothing phone", "iqoo", "vivo", "oppo"],
    "tablet": ["ipad", "tablet", "galaxy tab"],
    "headphones": ["headphones", "headphone", "over-ear", "on-ear"],
    "earbuds": ["earbuds", "earphones", "tws", "airpods", "buds"],
    "watch": ["smartwatch", "smart watch", "apple watch", "galaxy watch"],
    "tv": ["television", "tv", "smart tv", "led tv", "oled"],
}

def guess_category_from_title(title: str) -> Optional[str]:
    """
    Guess product category from title.
    
    Returns:
        Category string or None.
    """
    title_lower = title.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return category
    
    return None


# ============================================================
# Brand Extraction
# ============================================================

KNOWN_BRANDS = [
    # Laptops
    "ASUS", "Lenovo", "HP", "Dell", "Acer", "MSI", "Apple", "Samsung",
    # Phones
    "OnePlus", "Realme", "Xiaomi", "Redmi", "POCO", "iQOO", "Vivo", "Oppo",
    "Nothing", "Motorola", "Google", "iPhone",
    # Audio
    "boAt", "JBL", "Sony", "Sennheiser", "Bose", "Skullcandy",
]

def _extract_brand(title: str) -> Optional[str]:
    """Extract brand from title."""
    title_lower = title.lower()
    
    for brand in KNOWN_BRANDS:
        if brand.lower() in title_lower:
            return brand
    
    # Fallback: first word
    words = title.split()
    return words[0].title() if words else None


# ============================================================
# Spec Extraction
# ============================================================

def _extract_specs(content: str) -> dict:
    """Extract technical specs from content."""
    specs = {}
    
    # CPU
    cpu_patterns = [
        r'(Intel Core i[357]-\d{4,5}\w*)',
        r'(AMD Ryzen \d \d{4}\w*)',
        r'(Apple M\d(?: Pro| Max)?)',
        r'(Snapdragon \d{3,4}\w*)',
    ]
    for pattern in cpu_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            specs["cpu"] = match.group(1)
            break
    
    # GPU
    gpu_patterns = [
        r'(NVIDIA GeForce RTX \d{4}(?: Ti)?)',
        r'(RTX \d{4}(?: Ti)?)',
        r'(GTX \d{4}(?: Ti)?)',
        r'(AMD Radeon RX \d{4}\w*)',
    ]
    for pattern in gpu_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            specs["gpu"] = match.group(1)
            break
    
    # RAM
    ram_match = re.search(r'(\d+)\s*GB\s*(?:DDR|RAM|Memory)', content, re.IGNORECASE)
    if ram_match:
        specs["ram_gb"] = int(ram_match.group(1))
    
    # Storage
    storage_match = re.search(r'(\d+)\s*(?:GB|TB)\s*(?:SSD|HDD|Storage)', content, re.IGNORECASE)
    if storage_match:
        val = int(storage_match.group(1))
        if 'TB' in content[storage_match.start():storage_match.end()].upper():
            val *= 1024
        specs["storage_gb"] = val
    
    # Rating - Be more strict to avoid false positives from model names like "iQOO 9"
    rating_patterns = [
        r'(\d\.\d)\s*(?:out of 5|/5|stars)',  # Must have decimal: 4.5 out of 5
        r'rating[:\s]+(\d\.\d)',              # "rating: 4.5"
        r'(\d\.\d)\s*(?:rating|review)',      # "4.5 rating"
    ]
    for pattern in rating_patterns:
        rating_match = re.search(pattern, content, re.IGNORECASE)
        if rating_match:
            rating_val = float(rating_match.group(1))
            # Validate rating is in sensible range (0-5)
            if 0 <= rating_val <= 5:
                specs["rating"] = rating_val
                break
    
    return specs


# ============================================================
# Main Extraction Function
# ============================================================

def extract_product_from_markdown(
    markdown: str,
    url: str,
    site: str,
    *,
    llm = None,
) -> ProductPage:
    """
    Extract product info from scraped markdown.
    
    Args:
        markdown: Markdown content from crawl4ai
        url: Original URL
        site: Site label ('amazon', 'flipkart', etc.)
        llm: Optional LLM for enhanced extraction (not yet implemented)
    
    Returns:
        ProductPage with extracted data
    """
    # Check for Captcha/Robot pages first
    if "robot check" in markdown.lower() or "enter the characters you see below" in markdown.lower():
        # Return empty product or raise error - for now, return empty with flag
        return ProductPage(site=site, url=url, raw_title="", price=None)

    # Extract title (skip navigation links and UI elements)
    title_match = None
    ignored_titles = [
        'skip to', 'menu', 'search', 'sign in', 'cart', 'back to top',
        'keyboard shortcuts', 'need help', 'contact us', 'privacy notice',
        'conditions of use', 'accessibility', 'your account', 'returns',
        'customer service', 'best sellers', 'new releases', 'today\'s deals'
    ]
    
    for match in re.finditer(r'^#\s*(.+?)$', markdown, re.MULTILINE):
        text = match.group(1).strip()
        # Skip common navigation/header items
        if len(text) < 5 or any(x in text.lower() for x in ignored_titles):
            continue
        title_match = match
        break
    
    if not title_match:
        # Fallback to bold text if H1 not found
        for match in re.finditer(r'\*\*(.+?)\*\*', markdown):
            text = match.group(1).strip()
            if len(text) > 10 and not any(x in text.lower() for x in ['skip to', 'menu']):
                title_match = match
                break
    
    raw_title = title_match.group(1).strip() if title_match else url.split('/')[-1].replace('-', ' ').title()
    
    # Extract price
    price = _extract_price_from_content(markdown)
    
    # Extract specs
    specs = _extract_specs(markdown)
    
    # Build ProductPage
    product = ProductPage(
        site=site,
        url=url,
        raw_title=raw_title,
        normalized_model_name=normalize_model_name(raw_title),
        brand=_extract_brand(raw_title),
        category=guess_category_from_title(raw_title),
        price=price,
        cpu=specs.get("cpu"),
        gpu=specs.get("gpu"),
        ram_gb=specs.get("ram_gb"),
        storage_gb=specs.get("storage_gb"),
        rating=specs.get("rating"),
    )
    
    # TODO: If llm provided, use it for enhanced extraction
    
    return product
