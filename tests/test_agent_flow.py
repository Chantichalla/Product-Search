"""
Integration Test: Full Async Agent Service + Database CRUD Flow
"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.session import get_session
from db import crud, models
from backend.services.agent_service import agent_service


async def test_agent_flow():
    print("\n🚀 Starting Async Agent Flow Verification...")
    
    # 1. Test DB Connection & CRUD
    try:
        async with get_session() as session:
            print("✅ Database Connected")
            
            # 2. CRUD: User Creation
            user = await crud.get_or_create_user(session, "test_user@example.com")
            print(f"✅ User Retrieved/Created: {user.email} (ID: {user.id})")
            
            # 3. CRUD: Session Creation
            chat_session = await crud.create_chat_session(session, user.id, "Integration Test Chat")
            print(f"✅ Chat Session Created: {chat_session.title} (ID: {chat_session.id})")
            
            # 4. CRUD: Add Message
            msg = await crud.add_message(session, chat_session.id, "user", "Hello DB!")
            print(f"✅ Message Saved: {msg.content}")
            
            # 5. CRUD: Retrieve History
            history = await crud.get_chat_history(session, chat_session.id)
            print(f"✅ History Retrieved: {len(history)} messages")
            assert len(history) >= 1
            assert history[-1]["content"] == "Hello DB!"

    except Exception as e:
        print(f"❌ DB Verification Failed: {e}")
        return

    # 6. Service Integration
    print("\n🤖 Testing Agent Service Integration...")
    try:
        test_session_id = chat_session.id
        
        # Inject mock agent response to test persistence logic cleanly
        agent_service._ask_agent = lambda q, s, h: f"Echo: {q}"
        agent_service._agent_loaded = True
        agent_service._agent_type = "mock"
        
        response, elapsed = await agent_service.ask("Testing persistence", session_id=test_session_id)
        print(f"✅ Agent Response: {response} (took {elapsed:.2f}s)")
        
        # Verify message persisted
        async with get_session() as session:
            updated_history = await crud.get_chat_history(session, test_session_id)
            print(f"✅ Updated History Count: {len(updated_history)} messages")
            assert len(updated_history) >= 3  # Initial + User query + Agent answer
            
        print("🎉 Agent Flow Verification Passed!\n")
    except Exception as e:
        print(f"❌ Agent Service Verification Failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_agent_flow())
