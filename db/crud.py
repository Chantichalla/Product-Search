"""
Database CRUD Operations

Handles all database interactions for Users, Sessions, and Messages.
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from .models import User, ChatSession, ChatMessage


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    """
    Get an existing user or create a new guest user.
    """
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        return user

    # Create new user
    user = User(
        email=email,
        hashed_password="hashed_guest_password",  # Placeholder for now
        is_active=True
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_chat_session(session: AsyncSession, user_id: int, title: str = "New Chat") -> ChatSession:
    """
    Create a new chat session for a user.
    """
    chat_session = ChatSession(
        user_id=user_id,
        title=title
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    await session.refresh(chat_session)
    return chat_session


async def get_user_chat_sessions(session: AsyncSession, user_id: int) -> List[ChatSession]:
    """Retrieve all chat sessions for a user, ordered by update time."""
    stmt = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()



async def get_chat_session(session: AsyncSession, session_id: int) -> Optional[ChatSession]:
    """Retrieve a chat session by ID."""
    return await session.get(ChatSession, session_id)


async def add_message(
    session: AsyncSession, 
    session_id: int, 
    role: str, 
    content: str
) -> ChatMessage:
    """
    Save a message to the database.
    """
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def update_session_title(session: AsyncSession, session_id: int, title: str) -> Optional[ChatSession]:
    """
    Update the title of a chat session.
    """
    chat_session = await session.get(ChatSession, session_id)
    if chat_session:
        chat_session.title = title
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)
    return chat_session


async def get_chat_history(
    session: AsyncSession, 
    session_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[dict]:
    """
    Retrieve full chat history for a session, formatted for the agent.
    Returns: [{"role": "user", "content": "..."}, ...]
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = result.scalars().all()
    
    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]
