"""
LLM-Based Product Extraction

Uses Groq Llama 3.3 70B for accurate extraction from scraped content.
Falls back to Gemini Flash-Lite if Groq fails.

Features:
- Parallel extraction (individual calls, NOT batched)
- Pydantic validation for structured output
- Graceful fallback to regex extraction

Usage:
    products = await extract_products_parallel(pages_dict)
"""

import asyncio
import json
import os
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# EXTRACTION SCHEMA
# ============================================================

class ExtractedProduct(BaseModel):
    """Validated product data from LLM extraction."""
    
    # Required fields
    name: str = Field(..., description="Product name/title")
    url: str = Field(default="", description="Source URL")
    site: str = Field(default="unknown", description="Source site")
    
    # Pricing
    price: Optional[int] = Field(default=None, description="Price in INR")
    original_price: Optional[int] = Field(default=None, description="MRP before discount")
    
    # Product details
    brand: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None, description="phone/laptop/tablet/etc")
    
    # Specs (phones/laptops)
    ram_gb: Optional[int] = Field(default=None)
    storage_gb: Optional[int] = Field(default=None)
    cpu: Optional[str] = Field(default=None)
    gpu: Optional[str] = Field(default=None)
    display: Optional[str] = Field(default=None)
    battery: Optional[str] = Field(default=None)
    
    # Ratings
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    rating_count: Optional[int] = Field(default=None)
    
    # Availability
    in_stock: bool = Field(default=True)
    
    @validator('price', 'original_price', pre=True)
    def parse_price(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            # Remove currency symbols and commas
            v = re.sub(r'[₹,\s]', '', v)
            try:
                return int(float(v))
            except:
                return None
        return int(v) if v else None
    
    @validator('rating', pre=True)
    def parse_rating(cls, v):
        if v is None:
            return None
        try:
            return float(v)
        except:
            return None
    
    @validator('in_stock', pre=True)
    def parse_in_stock(cls, v):
        if v is None:
            return True  # Default to in stock
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', 'yes', '1', 'in stock', 'available')
        return bool(v)



# ============================================================
# LLM CLIENTS (Using Centralized Factory Functions)
# ============================================================

def get_extraction_client():
    """Get LLM client for extraction (uses ANTHROPIC_TOOL_USE via proxy)."""
    from config.llm_config import get_tool_llm
    return get_tool_llm()


def get_fallback_client():
    """Get fallback LLM for extraction (uses ANTHROPIC_FAST)."""
    from config.llm_config import get_query_planner_llm
    return get_query_planner_llm()


# Global clients (lazy loaded)
_extraction_client = None
_fallback_client = None


def _get_extraction_llm():
    global _extraction_client
    if _extraction_client is None:
        _extraction_client = get_extraction_client()
    return _extraction_client


def _get_fallback_llm():
    global _fallback_client
    if _fallback_client is None:
        _fallback_client = get_fallback_client()
    return _fallback_client


# ============================================================
# EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = """Extract product information from this e-commerce page content.

CONTENT:
{content}

INSTRUCTIONS:
1. Extract the main product details (not accessories or related products)
2. Price should be in INR as an integer (e.g., 45999 not "₹45,999")
3. For specs, extract values as integers where applicable
4. If a field is not found, use null
5. Return ONLY valid JSON, no explanation

JSON SCHEMA:
{{
    "name": "full product name",
    "price": integer or null,
    "original_price": integer or null (MRP before discount),
    "brand": "brand name" or null,
    "category": "phone" | "laptop" | "tablet" | "headphones" | "watch" | "tv" | null,
    "ram_gb": integer or null,
    "storage_gb": integer or null,
    "cpu": "processor name" or null,
    "gpu": "graphics card" or null,
    "display": "display description" or null,
    "battery": "battery capacity" or null,
    "rating": float (0-5) or null,
    "rating_count": integer or null,
    "in_stock": boolean
}}

RESPOND WITH ONLY THE JSON OBJECT:"""


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def _parse_json_response(response_text: str) -> dict:
    """Parse JSON from LLM response with fallbacks."""
    text = response_text.strip()
    
    # Try direct parse
    try:
        return json.loads(text)
    except:
        pass
    
    # Try extracting from markdown code block
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass
    
    # Try finding JSON object in text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass
    
    # Try json_repair library
    try:
        import json_repair
        return json_repair.loads(text)
    except:
        pass
    
    return {}


async def extract_with_llm(content: str, url: str, site: str) -> Optional[ExtractedProduct]:
    """Extract product info using proxy LLM (gemini-3-flash via Anthropic)."""
    try:
        # Truncate content to avoid token limits
        truncated = content[:12000] if len(content) > 12000 else content
        
        prompt = EXTRACTION_PROMPT.format(content=truncated)
        
        # Run in executor to not block
        loop = asyncio.get_event_loop()
        llm = _get_extraction_llm()
        
        response = await loop.run_in_executor(
            None,
            lambda: llm.invoke(prompt)
        )
        
        # Parse response (handle both LangChain and Anthropic formats)
        response_text = response if isinstance(response, str) else getattr(response, 'content', str(response))
        data = _parse_json_response(response_text)
        
        if not data or not data.get("name"):
            print(f"  [Debug] Groq extracted invalid/empty JSON for {url[:30]}...")
            return None
        
        # Add URL and site
        data["url"] = url
        data["site"] = site
        
        product = ExtractedProduct(**data)
        print(f"  [Debug] Extract success: {product.name[:30]}... (₹{product.price})")
        return product
        
    except Exception as e:
        print(f"  [LLM Extraction] Error for {url[:50]}: {e}")
        return None


async def extract_with_fallback(content: str, url: str, site: str) -> Optional[ExtractedProduct]:
    """Fallback extraction using ANTHROPIC_FAST (gemini-2.5-flash)."""
    try:
        llm = _get_fallback_llm()
        if not llm:
            return None
        
        truncated = content[:15000] if len(content) > 15000 else content
        prompt = EXTRACTION_PROMPT.format(content=truncated)
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: llm.invoke(prompt)
        )
        
        response_text = response if isinstance(response, str) else getattr(response, 'content', str(response))
        data = _parse_json_response(response_text)
        
        if not data or not data.get("name"):
            return None
        
        data["url"] = url
        data["site"] = site
        
        return ExtractedProduct(**data)
        
    except Exception as e:
        print(f"  [Gemini Extraction] Error for {url[:50]}: {e}")
        return None


async def extract_single_product(
    content: str, 
    url: str, 
    site: str = "unknown"
) -> Optional[ExtractedProduct]:
    """
    Extract product from content with fallback.
    
    Tries: Groq 70B -> Gemini Flash-Lite -> None
    """
    # Try primary extraction first (gemini-3-flash)
    result = await extract_with_llm(content, url, site)
    if result and result.price:
        return result
    
    # Fallback to gemini-2.5-flash
    result = await extract_with_fallback(content, url, site)
    if result and result.price:
        return result
    
    return None


async def extract_products_parallel(
    pages: Dict[str, Dict[str, Any]],
    max_concurrent: int = 5
) -> List[Optional[ExtractedProduct]]:
    """
    Extract products from multiple pages in parallel.
    
    Args:
        pages: Dict mapping URL -> {"markdown": str, "error": str | None}
        max_concurrent: Max parallel extractions
        
    Returns:
        List of ExtractedProduct (or None for failures)
    """
    # Filter pages with content
    valid_pages = [
        (url, data["markdown"])
        for url, data in pages.items()
        if data.get("markdown") and not data.get("error")
    ]
    
    if not valid_pages:
        return []
    
    # Determine site from URL
    def get_site(url: str) -> str:
        if "amazon" in url:
            return "amazon"
        elif "flipkart" in url:
            return "flipkart"
        elif "croma" in url:
            return "croma"
        elif "reliance" in url:
            return "reliance"
        return "unknown"
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def extract_with_limit(url: str, content: str):
        async with semaphore:
            site = get_site(url)
            return await extract_single_product(content, url, site)
    
    # Run extractions in parallel
    tasks = [
        extract_with_limit(url, content)
        for url, content in valid_pages
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions
    return [
        r if isinstance(r, ExtractedProduct) else None
        for r in results
    ]


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def extract_products_sync(pages: Dict[str, Dict[str, Any]]) -> List[Optional[ExtractedProduct]]:
    """Sync wrapper for extract_products_parallel."""
    return asyncio.run(extract_products_parallel(pages))


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    # Test extraction
    test_content = """
    # Samsung Galaxy S24 Ultra 256GB
    
    Price: ₹1,29,999
    MRP: ₹1,34,999 (4% off)
    
    **Specifications:**
    - RAM: 12 GB
    - Storage: 256 GB
    - Processor: Snapdragon 8 Gen 3
    - Display: 6.8" Dynamic AMOLED 2X
    - Battery: 5000 mAh
    
    Rating: 4.5 out of 5 (2,345 reviews)
    
    In Stock - Delivery by Tomorrow
    """
    
    async def test():
        result = await extract_single_product(
            test_content,
            "https://amazon.in/dp/test",
            "amazon"
        )
        if result:
            print("Extraction successful!")
            print(result.model_dump_json(indent=2))
        else:
            print("Extraction failed")
    
    asyncio.run(test())
