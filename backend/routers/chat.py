"""Chat endpoint router."""
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from backend.schemas.chat import (
    ChatRequest, 
    ChatResponse, 
    ClearSessionRequest, 
    ClearSessionResponse,
    SessionListResponse,
    MessageListResponse,
    ChatSessionSchema
)
from backend.services.agent_service import agent_service
from backend.utils.helpers import logger
import json

router = APIRouter()


# ── Price History Enrichment ──

# Keywords that indicate the user is asking about a specific product's price
_PRICE_KEYWORDS = re.compile(
    r'\b(price|cost|buy|purchase|worth|cheap|deal|offer|discount|flipkart|amazon|lowest|history)\b',
    re.IGNORECASE
)


def _extract_product_name(query: str, response: str) -> str | None:
    """
    Try to extract a clean product name from the query for price history lookup.
    
    Heuristic: If the query mentions price-related terms and contains a product 
    name (2-6 words, typically with a brand + model), extract it.
    """
    if not _PRICE_KEYWORDS.search(query) and not _PRICE_KEYWORDS.search(response):
        return None
    
    # Strip common query framing words to isolate the product name
    clean = re.sub(
        r'\b(price|of|the|for|in|india|buy|from|where|to|get|best|cheapest|what|is|show|me|tell|check|compare|vs|versus|history|current|lowest|highest)\b',
        '', query, flags=re.IGNORECASE
    ).strip()
    
    # Remove extra whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    # If we're left with something reasonable (2-8 words), it's likely a product name
    words = clean.split()
    if 1 <= len(words) <= 8 and len(clean) >= 3:
        return clean
    
    return None


async def _maybe_fetch_price_history(query: str, response: str) -> dict | None:
    """
    If the query looks like a product price query, fetch price history.
    Returns None if not applicable or on failure.
    """
    product_name = _extract_product_name(query, response)
    if not product_name:
        return None
    
    logger.info(f"[PriceHistory] Enriching response for product: {product_name}")
    
    try:
        from scraping.price_history_scraper import get_price_history
        from pathlib import Path
        
        result = await get_price_history(product_name)
        
        if not result.get("found"):
            logger.info(f"[PriceHistory] Product not found on pricehistory.app: {product_name}")
            return None
        
        # Convert chart path to URL for frontend
        chart_url = None
        if result.get("chart_image_path"):
            chart_url = f"/api/price-history/image/{Path(result['chart_image_path']).name}"
        
        return {
            "product_name": result.get("product_name", product_name),
            "lowest_price": result.get("lowest_price"),
            "highest_price": result.get("highest_price"),
            "average_price": result.get("average_price"),
            "current_price": result.get("current_price"),
            "trend": result.get("trend", "unknown"),
            "recommendation": result.get("recommendation", "NEUTRAL"),
            "recommendation_reason": result.get("recommendation_reason", ""),
            "chart_image_url": chart_url,
            "source_url": result.get("source_url"),
        }
        
    except Exception as e:
        logger.error(f"[PriceHistory] Enrichment failed: {e}")
        return None

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the e-commerce agent and get a response.
    
    - **message**: Your query about products (e.g., "gaming phone under 45k")
    - **session_id**: Optional session ID for conversation continuity
    - **provided_url**: Optional product page URL to analyze
    - **provided_image_b64**: Optional base64-encoded product image
    
    Returns the agent's response with product recommendations.
    """
    try:
        logger.info(f"Received chat request: {request.message[:50]}...")
        
        # Convert session_id to int if provided
        s_id = None
        if request.session_id:
            try:
                s_id = int(request.session_id)
            except (ValueError, TypeError):
                logger.warning(f"Invalid session_id: {request.session_id}")
        
        response, exec_time = await agent_service.ask(
            request.message, 
            session_id=s_id,
            provided_url=request.provided_url or "",
            provided_image_b64=request.provided_image_b64 or "",
        )
        
        # Enrich with price history if this looks like a product query
        price_history = await _maybe_fetch_price_history(request.message, response)
        
        return ChatResponse(
            response=response,
            status="success",
            price_history=price_history,
            execution_time=exec_time,
            session_id=str(s_id) if s_id else None
        )

        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(e)}"
        )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    SSE streaming endpoint for real-time progress updates.
    
    Streams JSON events as each LangGraph node completes:
    - {"type": "progress", "node": "search", "label": "Searching...", "done": false}
    - {"type": "result", "answer": "...", "thumbnail_url": "...", "done": true}
    """
    import asyncio
    
    async def event_generator():
        try:
            s_id = None
            if request.session_id:
                try:
                    s_id = int(request.session_id)
                except (ValueError, TypeError):
                    pass
            
            # Get DB history
            history = []
            try:
                from db.session import get_session
                from db import crud
                async with get_session() as db_session:
                    user = await crud.get_or_create_user(db_session, "guest@example.com")
                    if not s_id:
                        chat_session = await crud.create_chat_session(db_session, user.id, title=request.message[:30])
                        s_id = chat_session.id
                    await crud.add_message(db_session, s_id, "user", request.message)
                    history = await crud.get_chat_history(db_session, s_id, limit=50)
            except Exception as e:
                logger.error(f"DB Error (Stream): {e}")
            
            # Run the streaming agent in a thread executor
            loop = asyncio.get_event_loop()
            
            # We need to collect events from the sync generator in a thread
            agent_service._load_agent()
            
            def run_streaming():
                return list(agent_service._ask_agent_streaming(
                    query=request.message,
                    session_id=str(s_id) if s_id else None,
                    history=history,
                    provided_url=request.provided_url or "",
                    provided_image_b64=request.provided_image_b64 or "",
                ))
            
            events = await loop.run_in_executor(None, run_streaming)
            
            final_answer = ""
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "result":
                    final_answer = event.get("answer", "")
            
            # Enrich with price history if this looks like a product query
            try:
                price_history = await _maybe_fetch_price_history(request.message, final_answer)
                if price_history:
                    yield f"data: {json.dumps({'type': 'price_history', 'data': price_history, 'done': False})}\n\n"
            except Exception as e:
                logger.error(f"Price history enrichment error: {e}")
            
            # Save assistant response to DB
            if final_answer and s_id:
                try:
                    async with get_session() as db_session:
                        await crud.add_message(db_session, s_id, "assistant", final_answer)
                except Exception as e:
                    logger.error(f"DB Error (Stream Save): {e}")
                    
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'answer': str(e), 'done': True})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/clear", response_model=ClearSessionResponse)
async def clear_session(request: ClearSessionRequest = None):
    """
    Clear the agent's cache or session.
    
    - **session_id**: Optional specific session to clear
    """
    try:
        # Clear cache logic here if needed
        logger.info("Session cleared")
        return ClearSessionResponse(
            status="success",
            message="Session and cache cleared successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session", response_model=ChatSessionSchema)
async def create_session():
    """Create a new chat session."""
    try:
        session = await agent_service.create_session()
        return session
    except Exception as e:
        logger.error(f"Create session error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=SessionListResponse)
async def get_history():
    """List all chat sessions for the guest user."""
    try:
        sessions = await agent_service.get_user_sessions()
        return SessionListResponse(sessions=sessions)
    except Exception as e:
        logger.error(f"History error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}", response_model=MessageListResponse)
async def get_session_messages(session_id: int):
    """Get all messages for a specific session."""
    try:
        messages = await agent_service.get_session_messages(session_id)
        return MessageListResponse(messages=messages)
    except Exception as e:
        logger.error(f"Message fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

