"""Price History endpoint — serves price data + chart images."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Chart images directory
CHART_DIR = Path(__file__).parent.parent.parent / "data" / "price_charts"


@router.get("/price-history/{product_name}")
async def get_price_history(product_name: str):
    """
    Get price history data for a product.
    
    Scrapes pricehistory.app in real-time and returns:
    - Lowest, highest, average, current prices
    - Buy/Wait recommendation
    - Chart screenshot URL
    """
    try:
        from scraping.price_history_scraper import get_price_history as _get_ph
        
        result = await _get_ph(product_name)
        
        # Convert chart_image_path to a URL the frontend can fetch
        if result.get("chart_image_path"):
            result["chart_image_url"] = f"/api/price-history/image/{Path(result['chart_image_path']).name}"
        else:
            result["chart_image_url"] = None
        
        return result
        
    except Exception as e:
        logger.error(f"Price history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-history/image/{filename}")
async def serve_chart_image(filename: str):
    """Serve a saved chart screenshot PNG."""
    filepath = CHART_DIR / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Chart image not found")
    
    # Security: ensure the file is within the expected directory
    try:
        filepath.resolve().relative_to(CHART_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid path")
    
    return FileResponse(
        path=str(filepath),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"}
    )
