# Extract module - product extraction utilities
from .product import (
    ProductPage,
    extract_product_from_markdown,
    normalize_model_name,
    parse_price,
    guess_category_from_title,
)

# CSS-based extraction (FAST - Primary)
from .css_extractors import (
    CSSExtractedProduct,
    extract_with_css,
    extract_products_css,
    extract_amazon,
    extract_flipkart,
)

# LLM-based extraction (SLOW - Fallback only)
from .llm_extraction import (
    ExtractedProduct,
    extract_single_product,
    extract_products_parallel,
    extract_with_llm,
)

# Vision-based extraction (IMAGE INPUT)
from .image_extractor import (
    ProductImageExtractor,
    ImageExtractionResult,
)

__all__ = [
    # Regex extraction
    "ProductPage",
    "extract_product_from_markdown",
    "normalize_model_name",
    "parse_price",
    "guess_category_from_title",
    # CSS extraction (PRIMARY)
    "CSSExtractedProduct",
    "extract_with_css",
    "extract_products_css",
    "extract_amazon",
    "extract_flipkart",
    # LLM extraction (FALLBACK)
    "ExtractedProduct",
    "extract_single_product",
    "extract_products_parallel",
    "extract_with_llm",
    # Vision extraction (IMAGE INPUT)
    "ProductImageExtractor",
    "ImageExtractionResult",
]
