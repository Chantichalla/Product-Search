
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.session import get_session
from db import crud, models
from backend.services.agent_service import agent_service

async def test_optimization():
    print("\n🚀 Starting Phase 4 Optimization Verification...")
    
    try:
        async with get_session() as session:
            # 1. Setup Data
            print("\n📝 Setting up test data...")
            user = await crud.get_or_create_user(session, "opt_test@example.com")
            chat_session = await crud.create_chat_session(session, user.id, title="New Chat")
            session_id = chat_session.id
            print(f"   Created Session: {session_id} (Title: {chat_session.title})")
            
            # 2. Test Pagination
            print("\n📄 Testing Pagination...")
            # Insert 10 messages
            for i in range(10):
                await crud.add_message(session, session_id, "user", f"Msg {i}")
            
            # Get first 3
            page1 = await crud.get_chat_history(session, session_id, limit=3, offset=0)
            print(f"   Page 1 (Limit 3): {[m['content'] for m in page1]}")
            assert len(page1) == 3
            assert page1[0]['content'] == "Msg 0"
            
            # Get next 3
            page2 = await crud.get_chat_history(session, session_id, limit=3, offset=3)
            print(f"   Page 2 (Offset 3): {[m['content'] for m in page2]}")
            assert len(page2) == 3
            assert page2[0]['content'] == "Msg 3"
            print("✅ Pagination Verified")
            
            # 3. Test Auto-Session Naming (Mocked Agent)
            print("\n🏷️ Testing Session Naming...")
            
            # Mock agent to return immediate response
            original_ask = agent_service._ask_agent
            agent_service._ask_agent = lambda q, s, h: "Response"
            agent_service._agent_loaded = True
            
            # Send a message that should trigger renaming
            # The heuristic uses the message content itself if title is "New Chat"
            test_msg = "Samsung Galaxy S24 Ultra Specifications" 
            await agent_service.ask(test_msg, session_id=session_id)
            
            # Check DB for title update
            # Need to re-fetch session
            # Note: The 'session' context manager was committed in previous calls inside 'ask'
            # We need a fresh check. Since 'ask' uses its own session scope, 
            # we can check with our current outer session, but might need to expire/refresh.
            await session.refresh(chat_session)
            
            print(f"   New Title: {chat_session.title}")
            
            # The heuristic trims to 5 words. 
            # "Samsung Galaxy S24 Ultra Specifications" -> 5 words -> "Samsung Galaxy S24 Ultra Specifications" (Exact)
            # or if > 5 words it truncates.
            expected_title = "Samsung Galaxy S24 Ultra Specifications"
            
            # Wait a moment if it was async background? No, it's awaited in current logic.
            assert chat_session.title != "New Chat"
            assert chat_session.title == expected_title
            print("✅ Session Naming Verified")
            
    except Exception as e:
        print(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'original_ask' in locals():
            agent_service._ask_agent = original_ask

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_optimization())
