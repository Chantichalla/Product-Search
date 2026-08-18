# E-Commerce Agent - Project Documentation

## Overview

AI-powered e-commerce agent that searches products across Flipkart and Amazon, extracts pricing, compares specs, and recommends the best deals.

---

## Architecture

### 5-Phase Multi-Agent Orchestration (LangGraph)

```
START → check_cache → (hit) → advisor → END
                    → (miss) → query_planner → parallel_search → variant_filter → verification → advisor → END
```

| Phase | Node | Purpose | Module |
|-------|------|---------|--------|
| - | `check_cache` | Redis lookup with 1hr freshness | `redis_cache.get_search()` |
| 1 | `query_planner` | Template-based search query generation | Uses `QUERY_TEMPLATES` |
| 2 | `parallel_search` | Multi-engine search with fallback | `search_with_fallback()` |
| 3 | `variant_filter` | Keyword ban + URL/variant dedup | Regex-based filtering |
| 4 | `verification` | Concurrent scraping via crawl4ai | `scrape_urls_concurrent()` |
| 5 | `advisor` | LLM reasoning (buy/wait) | Groq LLM |

### Search Engine Routing

```python
ENGINE_PRIORITY = {
    "site_search": ["google", "brave", "bing"],  # For site: operators
    "general": ["brave", "duckduckgo", "bing"],  # General queries
}
```

### File Structure

```
agent/
├── multi_agent/          # 5-Phase orchestration
│   ├── state.py          # AgentState (search_queries, raw_search_results, filtered_urls, etc.)
│   ├── nodes.py          # query_planner_node, parallel_search_node, variant_filter_node, etc.
│   ├── graph.py          # StateGraph + 5-phase edges
│   └── run.py            # Entry point
├── tools.py              # Helper functions
└── tools_langchain.py    # Atomic LangChain tools

cache/redis_cache.py      # Redis caching
db/models.py + session.py # SQLite persistence
scraping/concurrency.py   # Async scraping + search_with_fallback
extract/product.py        # ProductPage extraction
utils/budget_url.py       # Budget parsing
network/rate_limit.py     # Per-domain rate limiting
```

---

## Core Modules

### 1. Cache Layer (`cache/redis_cache.py`)
- Redis-based caching with auto-TTL
- `get_search(query)` / `set_search(query, data)`
- `get_page(url)` / `set_page(url, data)`
- 1-hour freshness for search results

### 2. Database Layer (`db/`)
- SQLModel for Product and PriceSnapshot tables
- `get_or_create_product()` - Upsert logic
- `add_price_snapshot()` - Track price history
- `get_product_by_name()` - Fuzzy search

### 3. Scraping Layer (`scraping/concurrency.py`)
- `scrape_urls_concurrent(urls)` - Parallel crawl4ai
- `ddg_search_concurrent(queries)` - Parallel DDG
- Shared AsyncWebCrawler for efficiency
- Integrated rate limiting

### 4. Extraction Layer (`extract/product.py`)
- `ProductPage` Pydantic model
- `extract_product_from_markdown()` - Regex + optional LLM
- Parses: price, brand, specs, rating

### 5. Budget Parsing (`utils/budget_url.py`)
- `parse_budget_from_query()` - "under 50k" → 50000
- Indian price formats (k, lakh, ₹)
- `extract_domain()`, `is_product_page()`

---

## API & Frontend

### Backend (`backend/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/chat` | POST | Send message to agent |
| `/api/clear` | POST | Clear session |

### Agent Service

```python
from backend.services.agent_service import agent_service

response, time = await agent_service.ask("laptop under 80k")
# Uses multi_agent by default, falls back to legacy
```

### Frontend (`frontend/app.py`)
Streamlit chat interface with:
- Chat history display
- Example queries sidebar
- Execution time display

---

## How to Run

```bash
# Prerequisites
redis-server              # Start Redis
ollama serve              # Start Ollama (optional)

# Terminal 1 - Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 - Frontend  
streamlit run frontend/app.py --server.port 8501
```

---

## Environment Variables (`.env`)

```
GROQ_API_KEY=gsk_...          # Required for LLM
OPENROUTER_API_KEY=sk-...     # Optional
```

---

## Dependencies

```
# Core
langchain, langgraph, langchain-openai

# Storage
redis, sqlmodel

# Web Scraping
crawl4ai, ddgs

# API
fastapi, uvicorn, streamlit
```
