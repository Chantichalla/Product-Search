"""
FastAPI Application Entry Point

E-Commerce Agent API - AI-powered product search and comparison.

Run with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.config import settings
from backend.routers import chat_router
from backend.routers.media import router as media_router
from backend.routers.price_history import router as price_history_router
from backend.utils.helpers import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 E-Commerce Agent API starting up...")
    logger.info(f"📍 API available at http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"📖 API docs at http://{settings.API_HOST}:{settings.API_PORT}/docs")
    yield
    # Shutdown
    logger.info("👋 E-Commerce Agent API shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="""
    ## E-Commerce Agent API
    
    AI-powered product search and comparison for Indian e-commerce platforms.
    
    ### Features
    - 🔍 **Product Search**: Find products by category and budget
    - 💰 **Price Comparison**: Compare prices across Flipkart & Amazon
    - 🎯 **Smart Recommendations**: Get personalized product suggestions
    
    ### Input Modes
    - ✅ Text input (available now)
    - 🔜 Voice input (coming soon)
    - 🔜 Image input (coming soon)
    """,
    lifespan=lifespan
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers - Use /chat prefix to match frontend api.ts
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(media_router, prefix="/api", tags=["Media (Future)"])
app.include_router(price_history_router, prefix="/api", tags=["Price History"])



@app.get("/", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns API status and version information.
    """
    return {
        "status": "healthy",
        "version": settings.API_VERSION,
        "title": settings.API_TITLE,
        "endpoints": {
            "chat": "/api/chat",
            "clear": "/api/clear",
            "voice": "/api/voice (coming soon)",
            "image": "/api/image (coming soon)",
        }
    }


@app.get("/health", tags=["Health"])
async def detailed_health():
    """Detailed health check with system info."""
    return {
        "status": "healthy",
        "api_version": settings.API_VERSION,
        "debug_mode": settings.DEBUG,
    }
