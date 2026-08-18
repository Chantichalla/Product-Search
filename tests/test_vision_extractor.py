"""
Test script for the Vision-based Product Image Extractor.

Usage:
    python -m tests.test_vision_extractor              (uses sample image)
    python -m tests.test_vision_extractor <image_path>  (uses provided image)
"""

import sys
import json
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract.image_extractor import ProductImageExtractor, ImageExtractionResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_load_and_encode(image_path: str):
    """Test image loading and base64 encoding."""
    print_separator("TEST 1: Image Loading & Encoding")
    
    try:
        b64, mime = ProductImageExtractor.load_and_encode(image_path)
        print(f"  ✅ Image loaded successfully")
        print(f"  📁 MIME type: {mime}")
        print(f"  📏 Base64 length: {len(b64)} chars ({len(b64) * 3 / 4 / 1024:.1f} KB)")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False


def test_extract_details(extractor: ProductImageExtractor, image_path: str):
    """Test VLM detail extraction."""
    print_separator("TEST 2: VLM Detail Extraction (Qwen3-VL)")
    
    print(f"  🔄 Sending image to Qwen3-VL... (this may take 30-60 seconds)")
    
    start = time.time()
    result = extractor.extract_details(image_path)
    elapsed = time.time() - start
    
    print(f"  ⏱️  Extraction took: {elapsed:.1f}s")
    
    if result.error:
        print(f"  ❌ Error: {result.error}")
        if result.raw_response:
            print(f"  📝 Raw response: {result.raw_response[:300]}")
        return result
    
    print(f"  ✅ Extraction successful!")
    print(f"\n  📋 Extracted Details:")
    details = result.to_dict()
    for key, value in details.items():
        print(f"     {key:>15}: {value}")
    
    print(f"\n  🎯 Valid for search: {'Yes' if result.is_valid else 'No'}")
    print(f"  🔮 Confidence: {result.confidence}")
    
    return result


def test_query_synthesis(result: ImageExtractionResult):
    """Test query synthesis from extracted details."""
    print_separator("TEST 3: Search Query Synthesis")
    
    query = ProductImageExtractor.synthesize_query(result)
    
    print(f"  🔍 Generated Tavily query:")
    print(f"     \"{query}\"")
    print(f"  📏 Query length: {len(query)} chars, {len(query.split())} words")
    
    return query


def test_full_pipeline(extractor: ProductImageExtractor, image_path: str):
    """Test the complete extract_and_search pipeline."""
    print_separator("TEST 4: Full Pipeline (extract_and_search)")
    
    start = time.time()
    output = extractor.extract_and_search(image_path)
    elapsed = time.time() - start
    
    print(f"  ⏱️  Full pipeline took: {elapsed:.1f}s")
    print(f"\n  📦 Output:")
    print(json.dumps(output, indent=4))
    
    return output


def main():
    # Get image path from command line or use default
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Look for any image in the project root
        project_root = Path(__file__).parent.parent
        sample_images = list(project_root.glob("*.png")) + list(project_root.glob("*.jpg")) + list(project_root.glob("*.jpeg"))
        
        if sample_images:
            image_path = str(sample_images[0])
            print(f"  ℹ️  No image specified, using: {sample_images[0].name}")
        else:
            print("❌ No image path provided and no sample images found.")
            print("   Usage: python -m tests.test_vision_extractor <image_path>")
            sys.exit(1)
    
    # Verify file exists
    if not Path(image_path).exists():
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)
    
    print(f"\n🖼️  Testing with image: {image_path}")
    
    # Initialize extractor
    extractor = ProductImageExtractor()
    
    # Run tests
    if not test_load_and_encode(image_path):
        print("\n⛔ Cannot proceed - image loading failed")
        sys.exit(1)
    
    result = test_extract_details(extractor, image_path)
    
    if result.error:
        print(f"\n⚠️  Extraction had errors, attempting query synthesis anyway...")
    
    test_query_synthesis(result)
    
    # Full pipeline test (uses a fresh call)
    print_separator("SUMMARY")
    if result.is_valid:
        print("  ✅ Pipeline is working! Ready to feed queries into Tavily.")
    else:
        print("  ⚠️  Pipeline ran but extraction confidence is low.")
        print("  💡 Try with a clearer product image for better results.")


if __name__ == "__main__":
    main()
