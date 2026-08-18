"""Pydantic models for media (voice/image) endpoints - Future implementation."""
from pydantic import BaseModel, Field
from typing import Optional


class VoiceRequest(BaseModel):
    """Request model for /api/voice endpoint (Future)."""
    # Audio file will be handled as UploadFile in the router
    session_id: Optional[str] = None


class VoiceResponse(BaseModel):
    """Response model for /api/voice endpoint."""
    
    response: str = Field(..., description="Agent's response")
    transcript: str = Field(..., description="Transcribed text from audio")
    status: str = Field(default="success")
    execution_time: float = Field(..., description="Processing time in seconds")


class ImageRequest(BaseModel):
    """Request model for /api/image endpoint (Future)."""
    # Image file will be handled as UploadFile in the router
    session_id: Optional[str] = None


class ImageResponse(BaseModel):
    """Response model for /api/image endpoint."""
    
    response: str = Field(..., description="Agent's response about the product")
    identified_product: Optional[str] = Field(
        None, 
        description="Identified product name from the image"
    )
    confidence: Optional[float] = Field(
        None, 
        ge=0, 
        le=1, 
        description="Confidence score of product identification"
    )
    status: str = Field(default="success")
    execution_time: float = Field(..., description="Processing time in seconds")
