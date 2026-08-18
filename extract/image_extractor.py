"""
Image-based Product Detail Extraction

Uses a local Vision-Language Model (Qwen3-VL via Ollama) to analyze
user-uploaded product images and extract structured details, which are 
then synthesized into optimized search queries for Tavily.

Pipeline:
    Image → Base64 Encode → VLM Extraction → JSON Details → Search Query

Usage:
    from extract.image_extractor import ProductImageExtractor
    
    extractor = ProductImageExtractor()
    result = extractor.extract_details("path/to/product.jpg")
    query = extractor.synthesize_query(result)
"""

import base64
import json
import re
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# MIME type mapping
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

# ============================================================
# EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = """You are a retail product identification expert. Analyze this product image carefully.

INSTRUCTIONS:
1. Identify the product type, brand, model (if visible), and key visual features.
2. Read any visible text on the product, packaging, or labels.
3. Note the color, material, and condition of the product.

Respond ONLY with a valid JSON object in this exact format (no markdown, no extra text):

{
    "product_type": "category of product (e.g., headphones, smartphone, laptop, shoes)",
    "brand": "brand name if identifiable, otherwise 'unknown'",
    "model": "specific model name/number if visible, otherwise 'unknown'",
    "color": "primary color(s)",
    "key_features": "2-3 distinguishing visual features separated by commas",
    "visible_text": "any text readable on the product or packaging",
    "condition": "new/used/packaged",
    "confidence": "high/medium/low"
}"""


# ============================================================
# DATA CLASS
# ============================================================

@dataclass
class ImageExtractionResult:
    """Structured result from VLM image analysis."""
    product_type: str = "unknown"
    brand: str = "unknown"
    model: str = "unknown"
    color: str = "unknown"
    key_features: str = ""
    visible_text: str = ""
    condition: str = "unknown"
    confidence: str = "low"
    raw_response: str = ""
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if extraction produced usable results."""
        return (
            self.product_type != "unknown" 
            and self.error is None
            and self.confidence != "low"
        )
    
    def to_dict(self) -> dict:
        return {
            "product_type": self.product_type,
            "brand": self.brand,
            "model": self.model,
            "color": self.color,
            "key_features": self.key_features,
            "visible_text": self.visible_text,
            "condition": self.condition,
            "confidence": self.confidence,
        }


# ============================================================
# MAIN EXTRACTOR CLASS
# ============================================================

class ProductImageExtractor:
    """
    Extracts product details from images using a local Vision-Language Model
    and synthesizes optimized search queries for Tavily.
    """
    
    def __init__(self, vlm=None):
        """
        Initialize extractor.
        
        Args:
            vlm: Optional VLM instance. If None, uses get_local_vision_llm().
        """
        self._vlm = vlm
    
    @property
    def vlm(self):
        """Lazy-load the vision LLM."""
        if self._vlm is None:
            from config.llm_config import get_local_vision_llm
            self._vlm = get_local_vision_llm()
        return self._vlm
    
    # ----------------------------------------------------------
    # IMAGE PREPROCESSING
    # ----------------------------------------------------------
    
    @staticmethod
    def load_and_encode(image_path: str) -> tuple[str, str]:
        """
        Load an image file and encode it to base64.
        
        Args:
            image_path: Path to the image file.
            
        Returns:
            Tuple of (base64_string, mime_type)
            
        Raises:
            FileNotFoundError: If image doesn't exist.
            ValueError: If format is unsupported.
        """
        path = Path(image_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: {suffix}. "
                f"Supported: {', '.join(SUPPORTED_FORMATS)}"
            )
        
        mime_type = MIME_TYPES[suffix]
        
        with open(path, "rb") as f:
            image_data = f.read()
        
        base64_string = base64.b64encode(image_data).decode("utf-8")
        
        size_mb = len(image_data) / (1024 * 1024)
        logger.info(f"Loaded image: {path.name} ({size_mb:.1f} MB, {mime_type})")
        
        return base64_string, mime_type
    
    # ----------------------------------------------------------
    # VLM DETAIL EXTRACTION
    # ----------------------------------------------------------
    
    def extract_details(self, image_path: str) -> ImageExtractionResult:
        """
        Analyze a product image and extract structured details.
        
        Args:
            image_path: Path to the product image.
            
        Returns:
            ImageExtractionResult with extracted product details.
        """
        try:
            # Step 1: Encode image
            base64_img, mime_type = self.load_and_encode(image_path)
            
            # Step 2: Build multimodal message for the VLM
            message = HumanMessage(
                content=[
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_img}"
                        },
                    },
                ]
            )
            
            # Step 3: Invoke VLM
            logger.info("Sending image to Qwen3-VL for analysis...")
            response = self.vlm.invoke([message])
            raw_text = response.content if hasattr(response, 'content') else str(response)
            
            logger.info(f"VLM raw response: {raw_text[:200]}...")
            
            # Step 4: Parse JSON from response
            return self._parse_response(raw_text)
            
        except FileNotFoundError as e:
            logger.error(f"File error: {e}")
            return ImageExtractionResult(error=str(e))
        except ValueError as e:
            logger.error(f"Format error: {e}")
            return ImageExtractionResult(error=str(e))
        except Exception as e:
            logger.error(f"VLM extraction failed: {e}", exc_info=True)
            return ImageExtractionResult(error=str(e), raw_response=str(e))
    
    # ----------------------------------------------------------
    # RESPONSE PARSING
    # ----------------------------------------------------------
    
    @staticmethod
    def _parse_response(raw_text: str) -> ImageExtractionResult:
        """Parse VLM response text into structured result."""
        # Try to extract JSON from the response
        # Handle cases where VLM wraps JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'\{[\s\S]*\}', raw_text)
            if json_match:
                json_str = json_match.group(0)
            else:
                return ImageExtractionResult(
                    error="No JSON found in VLM response",
                    raw_response=raw_text
                )
        
        try:
            data = json.loads(json_str)
            return ImageExtractionResult(
                product_type=data.get("product_type", "unknown"),
                brand=data.get("brand", "unknown"),
                model=data.get("model", "unknown"),
                color=data.get("color", "unknown"),
                key_features=data.get("key_features", ""),
                visible_text=data.get("visible_text", ""),
                condition=data.get("condition", "unknown"),
                confidence=data.get("confidence", "low"),
                raw_response=raw_text,
            )
        except json.JSONDecodeError as e:
            return ImageExtractionResult(
                error=f"JSON parse error: {e}",
                raw_response=raw_text
            )
    
    # ----------------------------------------------------------
    # QUERY SYNTHESIS
    # ----------------------------------------------------------
    
    @staticmethod
    def synthesize_query(result: ImageExtractionResult) -> str:
        """
        Synthesize extracted details into an optimized Tavily search query.
        
        Builds a targeted query string from the extracted product details,
        filtering out 'unknown' fields and prioritizing brand + model.
        
        Args:
            result: The extraction result from extract_details().
            
        Returns:
            Optimized search query string.
        """
        parts = []
        
        # Priority order: brand > model > product_type > color > features
        if result.brand and result.brand.lower() != "unknown":
            parts.append(result.brand)
        
        if result.model and result.model.lower() != "unknown":
            parts.append(result.model)
        
        if result.product_type and result.product_type.lower() != "unknown":
            parts.append(result.product_type)
        
        if result.color and result.color.lower() != "unknown":
            parts.append(result.color)
        
        # Add key features (take first 2 to keep query focused)
        if result.key_features:
            features = [f.strip() for f in result.key_features.split(",")][:2]
            parts.extend(features)
        
        # Add useful visible text (model numbers, specs)
        if result.visible_text and result.visible_text.lower() != "unknown":
            # Only add if it provides new info not already in parts
            text_parts = result.visible_text.split()[:3]  # First 3 words max
            for tp in text_parts:
                if tp.lower() not in " ".join(parts).lower():
                    parts.append(tp)
        
        # Append search intent keywords
        query = " ".join(parts) + " price specifications review"
        
        return query.strip()
    
    # ----------------------------------------------------------
    # CONVENIENCE: FULL PIPELINE
    # ----------------------------------------------------------
    
    def extract_and_search(self, image_path: str) -> dict:
        """
        Full pipeline: Image → Extract Details → Synthesize Query.
        
        Args:
            image_path: Path to the product image.
            
        Returns:
            Dict with 'details', 'query', and 'is_valid' keys.
        """
        result = self.extract_details(image_path)
        query = self.synthesize_query(result)
        
        return {
            "details": result.to_dict(),
            "query": query,
            "is_valid": result.is_valid,
            "error": result.error,
        }
