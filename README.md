# 🛍️ Product-AI — Autonomous E-Commerce Shopping & Advisory Agent

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-FF6F00.svg?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-000000.svg?logo=next.js&logoColor=white)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Cache-Redis-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![TailwindCSS](https://img.shields.io/badge/Styling-TailwindCSS-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**An intelligent, multi-source autonomous e-commerce assistant designed for Indian and global consumers.**  
Plans search strategies, scrapes and parses real-time prices across major retailers, tracks price histories, extracts specs from uploaded images, and provides unbiased purchase recommendations with anchored value scoring.

[Features](#-key-features) • [Architecture](#-architecture) • [Directory Layout](#-directory-structure) • [Getting Started](#-getting-started) • [Testing](#-running-tests) • [API Reference](#-api-reference)

</div>

---

## ✨ Key Features

- **🧠 Multi-Agent LangGraph Orchestration**: State-driven pipeline with dedicated nodes for contextual memory initialization, deep semantic query resolution, smart planning, multi-source search, and expert advisory.
- **🔍 Intelligent Multi-Source Search**: Hybrid search engine combining Tavily API, concurrent DuckDuckGo/Bing site sweeps, and stealth Crawl4AI browser automation.
- **📊 Real-Time Structured Data Extraction**: Parses JSON-LD Schema.org microdata, OpenGraph tags, fast CSS selectors (Amazon/Flipkart), and fallback LLM extraction.
- **👁️ Omnibox Vision Extraction**: Upload a photo of a device or gadget to extract its brand, model, and specifications using Vision-Language Models (Qwen3-VL).
- **⚡ Semantic & Redis Caching**: Minimizes API costs and reduces latency through vector similarity caching and Redis key-value storage.
- **📈 Historical Price Intelligence**: Scrapes historical price curves, average prices, and buy/wait deal signals.
- **💬 Deep Multi-Turn Context**: Resolves follow-ups (*"compare the first two"*, *"show cheaper alternatives"*) without losing past search state.
- **🎨 Glassmorphism Next.js UI**: Full-stack modern web interface with streaming token output, markdown rendering, comparison tables, and chat session management.

---

## 🏗️ Architecture

```
                                  ┌───────────────────────────┐
                                  │   User (Next.js Web / CLI)│
                                  └─────────────┬─────────────┘
                                                │ (HTTP / SSE / Direct)
                                                ▼
                                  ┌───────────────────────────┐
                                  │   FastAPI Service Layer   │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                            ┌───────────────────────────────────────┐
                            │    LangGraph Multi-Agent Engine       │
                            │      (agent/single_agent/run.py)      │
                            └───────────────────┬───────────────────┘
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
        [Memory Init Node]                                            [Query Rewriter Node]
  (Session State & Recents)                                      (Deep Vector Memory Context)
                 │                                                             │
                 └──────────────────────────────┬──────────────────────────────┘
                                                ▼
                                      [Semantic Cache Check]
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼ (Cache Hit)                                     ▼ (Cache Miss)
                       │                                       [Smart Planner Node]
                       │                           (Slot Extraction, Intent & Search Queries)
                       │                                                 │
                       │                        ┌────────────────────────┴────────────────────────┐
                       │                        ▼                                                 ▼
                       │               [Follow-Up Handler]                                 [Search Node]
                       │              (In-Memory Refinement)                    (Tavily / Scrapers / Extractor)
                       │                        │                                                 │
                       └────────────────────────┼─────────────────────────────────────────────────┘
                                                ▼
                                      [Advisor Reasoning LLM]
                            (Anchored Value Score & Price Comparison Table)
                                                │
                                                ▼
                                   [Structured Recommendation]
```

---

## 📁 Directory Structure

```
.
├── agent/
│   └── single_agent/        # Core LangGraph agent workflow
│       ├── run.py           # CLI & backend entrypoint (ask_agent / streaming)
│       ├── graph.py         # StateGraph routing & edge transitions
│       ├── nodes.py         # Node execution implementations
│       ├── smart_planner.py # Query parsing & slot extraction
│       ├── memory.py        # Conversation memory & follow-up filters
│       ├── deep_memory.py   # Long-term semantic turn memory
│       └── semantic_cache.py# Vector similarity cache
├── backend/                 # FastAPI Application
│   ├── main.py              # Server entrypoint & middleware
│   ├── routers/             # chat, media (image upload), price_history routes
│   ├── schemas/             # Pydantic request/response schemas
│   └── services/            # Agent service wrapper & session handlers
├── frontend/                # Next.js 14 React Web Application
│   ├── app/                 # App Router pages & layout
│   ├── components/          # Glassmorphism UI components
│   └── services/            # API integration & SSE streaming client
├── config/                  # LLM & Search Configurations
│   ├── llm_config.py        # Centralized LLM providers (Groq, Gemini, Ollama)
│   └── tavily_config.py     # Tavily search API settings & credit tracker
├── db/                      # Database & Persistence
│   ├── models.py            # SQLModel table schemas
│   ├── session.py           # Async PostgreSQL engine & sessions
│   └── crud.py              # User, session, and message database operations
├── extract/                 # Structured Product Extractors
│   ├── css_extractors.py    # Fast CSS parsers for Amazon / Flipkart
│   ├── extruct_extract.py   # Schema.org JSON-LD & OpenGraph extractor
│   ├── image_extractor.py   # Qwen3-VL image detail parser
│   ├── llm_extraction.py    # Fallback LLM structured extractor
│   └── product.py           # Price parsing & model normalization
├── scraping/                # Data Acquisition Layer
│   ├── tavily_search.py     # High-speed search API integration
│   ├── single_product_pipeline.py # Deep multi-site scraping sweep (Crawl4AI)
│   ├── price_history_scraper.py   # Real-time price history & chart scraper
│   └── concurrency.py       # Asynchronous multi-engine search routines
├── migrations/              # Alembic Database Migration Scripts
├── network/                 # Token-bucket rate limiter & user-agent rotation
├── prompts/                 # Advisor reasoning & query enhancement prompts
├── tests/                   # Consolidated test suite
├── docker-compose.yml       # PostgreSQL & Redis container stack
└── requirements.txt         # Python dependencies
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & `npm`
- **Docker & Docker Compose**

---

### 2. Clone Repository & Setup Environment

```bash
# Clone the repository
git clone https://github.com/<your-username>/product-AI.git
cd product-AI

# Create your .env from the template
cp .env.example .env
```

Edit your `.env` with your API keys:
```env
# LLM Providers
GROQ_API_KEY="your_groq_api_key"
GOOGLE_API_KEY="your_google_gemini_api_key"

# Search Provider
TAVILY_API_KEY="your_tavily_api_key"

# Database Connection (Default docker port 5433)
DATABASE_URL=postgresql+asyncpg://ai_user:ai_password@localhost:5433/product_ai_chat
```

---

### 3. Start Database & Redis (Docker)

```bash
docker compose up -d
```
*This launches PostgreSQL on port `5433` and Redis on port `6379`.*

---

### 4. Setup Python Environment & Database Migrations

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head
```

---

### 5. Running the Agent

#### Option A: Interactive CLI Mode
Test the agent workflow directly in your terminal:
```bash
python agent/single_agent/run.py
```

#### Option B: Full-Stack Web Application

**Start the FastAPI Backend:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**Start the Next.js Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🧪 Running Tests

The test suite in [`tests/`](tests/) covers database persistence, LangGraph routing, memory, and search integrations:

```bash
# Run database connectivity & schema test
python -m tests.test_db

# Run AgentService async flow integration test
python -m tests.test_agent_flow

# Run Planner to Search node integration test
python -m tests.test_planner_and_search

# Run Deep Memory & Query Rewriter unit test
python -m tests.test_memory

# Run Tavily search API test
python -m tests.test_tavily_api

# Run Store Sniper (Targeted URL & JSON-LD extraction)
python -m tests.test_store_sniper
```

---

## 📡 API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/chat` | Send query and get full agent response |
| `POST` | `/api/chat/stream` | Stream real-time node progress and response (SSE) |
| `GET` | `/api/chat/sessions` | Fetch user conversation history |
| `POST` | `/api/media/upload` | Upload product image for VLM feature extraction |
| `GET` | `/api/price-history/{product}` | Fetch historical lowest/highest prices & chart image |

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!
1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
