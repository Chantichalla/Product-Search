"""
Test Database Connectivity and Schema Tables
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url:
        url = url.replace("localhost", "127.0.0.1")
    return url


async def test_connection():
    url = get_db_url()
    if not url:
        print("❌ DATABASE_URL is not set in environment.")
        return False

    print(f"🔌 Connecting to: {url}")
    try:
        engine = create_async_engine(url, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 'Hello from Postgres!'"))
            print(f"✅ DB Response: {result.scalar()}")

            # Query existing public tables
            table_result = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
            tables = [row[0] for row in table_result]
            print(f"📊 Tables in DB: {tables}")

        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_connection())
