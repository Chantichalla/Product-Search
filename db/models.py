"""
SQLModel Database Models for E-commerce Agent

Tables:
- Product: Normalized product records with specs
- PriceSnapshot: Price history from different sites
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel, Relationship


class Product(SQLModel, table=True):
    """
    Represents a product with normalized specs.
    
    Stores extracted product information for fast lookup
    without needing to re-scrape.
    """
    __tablename__ = "products"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Normalized name for lookups (e.g., "asus_rog_strix_g16")
    normalized_model_name: str = Field(index=True)
    
    # Original scraped title for debugging
    raw_title: Optional[str] = None
    
    # Basic info
    brand: Optional[str] = None
    category: Optional[str] = None  # "laptop", "phone", "earbuds", etc.
    
    # Specs (for laptops/phones)
    cpu: Optional[str] = None
    gpu: Optional[str] = None
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    
    # Source tracking
    source_site: Optional[str] = None  # "amazon", "flipkart", "influencer_db"
    
    # Extra fields as JSON for misc data
    extra: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def __repr__(self):
        return f"<Product {self.normalized_model_name} ({self.brand})>"


class PriceSnapshot(SQLModel, table=True):
    """
    Represents a price observation from a specific site.
    
    Enables price history tracking and comparison across sites.
    """
    __tablename__ = "price_snapshots"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Link to product
    product_id: int = Field(foreign_key="products.id", index=True)
    
    # Price info
    site: str  # "amazon", "flipkart"
    price: int  # Price in INR (smallest unit)
    currency: str = "INR"
    
    # Source URL
    url: Optional[str] = None
    
    # When this price was seen
    seen_at: datetime = Field(default_factory=datetime.utcnow)
    
    def __repr__(self):
        return f"<PriceSnapshot ₹{self.price:,} from {self.site}>"


# ==================================================
# Helper functions for product operations
# ==================================================

def normalize_model_name(name: str) -> str:
    """
    Normalize a product name for database lookup.
    
    Examples:
        "ASUS ROG Strix G16" -> "asus_rog_strix_g16"
        "iPhone 15 Pro Max" -> "iphone_15_pro_max"
    """
    import re
    name = name.lower().strip()
    # Remove special characters except spaces
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    # Replace spaces with underscores
    return name.replace(' ', '_')


def extract_brand(name: str) -> Optional[str]:
    """
    Extract brand from product name.
    
    Examples:
        "ASUS ROG Strix G16" -> "ASUS"
        "Lenovo Legion 5 Pro" -> "Lenovo"
    """
    known_brands = [
        # Laptops
        "ASUS", "Lenovo", "HP", "Dell", "Acer", "MSI", "Apple", "Samsung",
        # Phones
        "OnePlus", "Realme", "Xiaomi", "Redmi", "POCO", "iQOO", "Vivo", "Oppo",
        "Nothing", "Motorola", "Google", "iPhone",
        # Audio
        "boAt", "JBL", "Sony", "Sennheiser", "Audio-Technica", "Skullcandy",
        "Bose", "Noise",
    ]
    
    name_lower = name.lower()
    for brand in known_brands:
        if brand.lower() in name_lower:
            return brand
    
    # Fallback: first word
    return name.split()[0] if name else None


class User(SQLModel, table=True):
    """
    Identity management for the AI Agent.
    """
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship: One user can have many chat sessions
    sessions: List["ChatSession"] = Relationship(back_populates="user")

    def __repr__(self):
        return f"<User {self.email}>"


class ChatSession(SQLModel, table=True):
    """
    Groups chat messages into identifiable conversations.
    """
    __tablename__ = "chat_sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    title: str = Field(default="New Conversation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: Optional[User] = Relationship(back_populates="sessions")
    messages: List["ChatMessage"] = Relationship(
        back_populates="session", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def __repr__(self):
        return f"<ChatSession {self.title}>"


class ChatMessage(SQLModel, table=True):
    """
    Individual messages within a chat session.
    """
    __tablename__ = "chat_messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    
    role: str  # "user", "assistant", or "system"
    content: str = Field(sa_column=Column(Text))
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship
    session: ChatSession = Relationship(back_populates="messages")

    def __repr__(self):
        return f"<{self.role}: {self.content[:20]}...>"
