"""Pydantic models for chat endpoints."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    """Request model for /api/chat endpoint."""
    message: str
    session_id: Optional[str | int] = None
    provided_url: Optional[str] = None       # URL pasted by user
    provided_image_b64: Optional[str] = None  # Base64-encoded image



class ChatResponse(BaseModel):
    """Response model for /api/chat endpoint."""
    
    response: str = Field(
        ...,
        description="Agent's response to the user's query"
    )
    status: str = Field(
        default="success",
        description="Request status: 'success' or 'error'"
    )
    execution_time: float = Field(
        ...,
        description="Time taken to process the request in seconds"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for the conversation"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Response timestamp"
    )
    price_history: Optional[dict] = Field(
        default=None,
        description="Price history data from pricehistory.app (if applicable)"
    )


class ClearSessionRequest(BaseModel):
    """Request model for clearing session/cache."""
    
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to clear (if None, clears all)"
    )


class ClearSessionResponse(BaseModel):
    """Response model for clear session endpoint."""
    
    status: str = Field(default="success")
    message: str = Field(default="Session cleared successfully")


class ChatSessionSchema(BaseModel):
    """Schema for a chat session."""
    id: int
    title: str
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatMessageSchema(BaseModel):
    """Schema for a chat message."""
    id: int
    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""
    sessions: list[ChatSessionSchema]


class MessageListResponse(BaseModel):
    """Response model for listing messages."""
    messages: list[ChatMessageSchema]

