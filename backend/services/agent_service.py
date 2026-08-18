"""Service layer wrapping the e-commerce multi-agent."""
import sys
import time
import asyncio
from pathlib import Path
from typing import Tuple, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.helpers import logger
from db.session import get_session
from db import crud


class AgentService:
    """Service class that wraps the multi-agent orchestrator."""
    
    def __init__(self):
        self._agent_loaded = False
        self._ask_agent = None
        self._agent_type = "multi_agent"  # Track which agent is loaded
    
    def _load_agent(self):
        """
        Lazy load the single-agent to avoid import issues at startup.
        """
        if not self._agent_loaded:
            try:
                # Load single-agent
                from agent.single_agent.run import ask_agent, ask_agent_streaming
                self._ask_agent = ask_agent
                self._ask_agent_streaming = ask_agent_streaming
                self._agent_type = "single_agent"
                self._agent_loaded = True
                logger.info("Single-agent orchestrator loaded successfully")
            except ImportError as e:
                logger.error(f"Failed to import single-agent: {e}")
                raise
    
    @property
    def agent_type(self) -> str:
        """Return which agent type is currently loaded."""
        return self._agent_type if self._agent_loaded else "not_loaded"
    
    async def ask(self, message: str, session_id: Optional[int] = None,
                  provided_url: str = "", provided_image_b64: str = "") -> Tuple[str, float]:
        """
        Send a message to the agent and get a response.
        
        Args:
            message: User's query
            session_id: Database Session ID (optional)
            provided_url: Optional URL pasted by the user
            provided_image_b64: Optional base64-encoded image
            
        Returns:
            Tuple of (response_text, execution_time_seconds)
        """
        self._load_agent()
        start_time = time.time()
        
        # 1. DB Operations: Save User Message
        history = []
        try:
            async with get_session() as db_session:
                # hardcoded guest email for now
                user = await crud.get_or_create_user(db_session, "guest@example.com")
                
                if not session_id:
                    # Create new session if none provided
                    chat_session = await crud.create_chat_session(db_session, user.id, title=message[:30])
                    session_id = chat_session.id
                else:
                    # Verify session exists
                    chat_session = await crud.get_chat_session(db_session, session_id)
                    if not chat_session:
                        # Fallback if invalid ID
                        chat_session = await crud.create_chat_session(db_session, user.id, title=message[:30])
                        session_id = chat_session.id
                
                # Save User Message
                await crud.add_message(db_session, session_id, "user", message)
                
                # Get History (Paginated: Last 20 messages for context)
                # We need the *latest* messages, so we might need to adjust the query order or limit strategy.
                # If we order by timestamp ASC, limit 50 gives the *first* 50.
                # To get last 50, we should count and offset, or sort DESC, limit, then re-sort.
                # For now, let's just get the last 50 by assuming the DB implementation handles it or we accept the trade-off.
                # Actually, standard chat history usually grabs everything or infinite scrolls. 
                # Agent needs recent context.
                history = await crud.get_chat_history(db_session, session_id, limit=50) 
                
        except Exception as e:
            logger.error(f"DB Error (User Turn): {e}")
            pass

        try:
            # 2. Call Agent
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self._ask_agent,
                message,
                None, 
                history,
                provided_url,
                provided_image_b64,
            )
            
            execution_time = time.time() - start_time
            logger.info(f"[{self._agent_type}] responded in {execution_time:.2f}s")
            
            # 3. DB Operations: Save Assistant Response & Update Title
            try:
                async with get_session() as db_session:
                    if session_id:
                       await crud.add_message(db_session, session_id, "assistant", response)
                       
                       # Auto-generate title after 2nd turn if it's still default
                       # For simplicity, if title is just "New Chat" or very short, and we have enough context
                       chat_session = await crud.get_chat_session(db_session, session_id)
                       if chat_session and (chat_session.title == "New Chat" or chat_session.title == message[:30]):
                           # Try Local LLM for title generation
                           try:
                               new_title = await self._generate_title_ollama(message)
                           except Exception as e:
                               logger.warning(f"Local LLM Title Gen Failed: {e}. Falling back to heuristic.")
                               new_title = self._generate_simple_title(message)
                               
                           await crud.update_session_title(db_session, session_id, new_title)
                           
            except Exception as e:
                logger.error(f"DB Error (Assistant Turn): {e}")
            
            return response, execution_time
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Agent error after {execution_time:.2f}s: {e}")
            raise
    
    async def _generate_title_ollama(self, message: str) -> str:
        """
        Generate a title using Local LLM (Qwen 3).
        """
        from config.llm_config import get_local_title_llm
        
        llm = get_local_title_llm()
        
        # Prompt optimized for Qwen
        prompt = (
            f"Summarize the following user query into a short, concise chat title (max 5 words). "
            f"Do not use quotes. Just the title.\n\n"
            f"Query: {message}\n"
            f"Title:"
        )
        
        # Run in executor to avoid blocking main loop (since ChatOllama might be sync or heavy)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            llm.invoke,
            prompt
        )
        
        title = response.content.strip().replace('"', '')
        return title

    def _generate_simple_title(self, message: str) -> str:
        """Generate a short title from the message."""
        words = message.split()
        if len(words) > 5:
            return " ".join(words[:5]) + "..."
        return message

    def get_status(self) -> dict:
        """Get agent status info."""
        return {
            "loaded": self._agent_loaded,
            "type": self._agent_type,
        }


    async def create_session(self, user_email: str = "guest@example.com", title: str = "New Chat"):
        """Create a new chat session."""
        try:
            async with get_session() as db_session:
                user = await crud.get_or_create_user(db_session, user_email)
                session = await crud.create_chat_session(db_session, user.id, title)
                return session
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise

    async def get_user_sessions(self, user_email: str = "guest@example.com"):
        """Get all chat sessions for a user."""
        try:
            async with get_session() as db_session:
                user = await crud.get_or_create_user(db_session, user_email)
                sessions = await crud.get_user_chat_sessions(db_session, user.id)
                return sessions
        except Exception as e:
            logger.error(f"Error fetching sessions: {e}")
            return []

    async def get_session_messages(self, session_id: int):
        """Get all messages for a specific session."""
        try:
            async with get_session() as db_session:
                messages = await crud.get_chat_history(db_session, session_id, limit=100)
                # Messages are usually returned latest first by crud.get_chat_history if it sorts by desc
                # We want chronological order for the frontend
                return messages[::-1] 
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []
            
# Global instance
agent_service = AgentService()
