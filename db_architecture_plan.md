
# Database Architecture Implementation Plan: Scalable Chat History

## 1. Executive Summary
This document outlines the architectural plan for integrating a production-grade **PostgreSQL** database to store chat sessions, user history, and agent interactions. This moves us from "Toy Memory" (RAM/Files) to "Enterprise Memory" (Structured SQL).

**Why PostgreSQL?**
- **ACID Compliance**: Guarantees your chat data is never lost, even if the server crashes.
- **Relational Integrity**: Links Users → Sessions → Messages → Metadata perfectly.
- **JSONB Support**: Allows storing flexible AI metadata (token counts, model names) without changing the schema.
- **Vector Extension (pgvector)**: Future-proofs us to move Deep Memory *into* Postgres if we want to simplify the stack later.

---

## 2. Database Schema Design (The "OpenAI-Style" Structure)

We will use a **Normalized 3-Tier Schema**: `Users` -> `Sessions` -> `Messages`.

### A. Tables

#### 1. `users`
*The humans or systems interacting with the agent.*
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    preferences JSONB DEFAULT '{}'  -- e.g., {"theme": "dark", "model": "gpt-4"}
);
```

#### 2. `chat_sessions`
*A container for a single conversation thread (like a ChatGPT sidebar item).*
```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),             -- Auto-generated summary of the chat
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- Used for sorting "Recent Chats"
    metadata JSONB DEFAULT '{}'     -- e.g., {"tags": ["shopping", "tech"], "agent_version": "v2"}
);
CREATE INDEX idx_sessions_user ON chat_sessions(user_id);
```

#### 3. `chat_messages`
*The actual dialogue turns.*
```sql
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,      -- "user", "assistant", "system"
    content TEXT NOT NULL,          -- The message text
    token_count INT,                -- For cost tracking/analytics
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'     -- e.g., {"latency_ms": 450, "search_sources": [...]}
);
CREATE INDEX idx_messages_session ON chat_messages(session_id, created_at);
```

---

## 3. Implementation Steps

### Phase 1: Foundation (Completed ✅)
1.  **Docker Setup**: Add `postgres:15` container to `docker-compose.yml`.
2.  **Dependencies**: Install `asyncpg`, `sqlalchemy`, `alembic`.
3.  **Configuration**: Add `DATABASE_URL` to `.env`.

### Phase 2: Schema & Migrations (Completed ✅)
1.  Define SQLAlchemy models in `database.py`.
2.  Initialize Alembic: `alembic init alembic`.
3.  Generate first migration: `alembic revision --autogenerate -m "Initial schema"`.
4.  Apply migration: `alembic upgrade head`.

### Phase 3: API Integration (Completed ✅)
1.  **Refactor `graph.py`**:
    *   Currently, the graph holds state in memory.
    *   **New Flow**:
        *   **Start**: API creates a `session_id`.
        *   **User Turn**: API saves user message to DB -> Calls Graph.
        *   **Graph Execution**: (No change to logic).
        *   **End**: API saves assistant response to DB -> Returns to UI.

### Phase 4: Optimization (Completed ✅)
1.  **Session Naming**: Integrate a small LLM call to auto-generate `title` for new sessions (e.g., "iPhone 15 Price Check") after 2 turns.
2.  **Pagination**: Ensure APIs return messages in chunks (e.g., last 50) to keep the UI snappy.

---

## 4. Hard Truth Recommendations

1.  **Don't build User Auth yet**: Start with a "Guest User" (hardcoded UUID) to get the chat history working first. Add Auth0 or Firebase later.
2.  **Don't use Postgres for Vector Search yet**: Keep using Redis/Pinecone for `DeepMemory`. Postgres `pgvector` is great, but migrating your working semantic search right now adds unnecessary risk. Stick to what works for vectors, use SQL for history.
3.  **Async is Mandatory**: If you use synchronous `psycopg2`, your high-throughput chat app **will** choke. Use `asyncpg`.
