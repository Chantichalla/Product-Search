"""Media (Voice/Image) endpoint router - Future implementation."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.schemas.media import VoiceResponse, ImageResponse
from backend.utils.helpers import logger

router = APIRouter()


@router.post("/voice", response_model=VoiceResponse)
async def process_voice(audio: UploadFile = File(...)):
    """
    Process voice input and get agent response.
    
    - **audio**: Audio file (WAV, MP3, etc.)
    
    Returns transcribed text and agent's response.
    
    **Status: Not implemented yet**
    """
    raise HTTPException(
        status_code=501,
        detail="Voice processing not implemented yet. Coming soon!"
    )


@router.post("/image", response_model=ImageResponse)
async def process_image(image: UploadFile = File(...)):
    """
    Process image input to identify product and get prices.
    
    - **image**: Image file (JPG, PNG, etc.)
    
    Returns identified product name and agent's response with prices.
    
    **Status: Not implemented yet**
    """
    raise HTTPException(
        status_code=501,
        detail="Image processing not implemented yet. Coming soon!"
    )
