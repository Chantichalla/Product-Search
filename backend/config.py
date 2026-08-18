"""Configuration and environment variables for the backend."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_TITLE: str = "E-Commerce Agent API"
    API_VERSION: str = "1.0.0"
    
    # Frontend URL (for CORS)
    FRONTEND_URL: str = "http://localhost:8501"
    
    # Debug mode
    DEBUG: bool = True
    
    # Agent settings
    AGENT_TIMEOUT: int = 120  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars like groq_api_key


# Global settings instance
settings = Settings()
