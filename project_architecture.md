# Product-AI Architecture (V3.1 - Tavily Integration)

## Overview

Multi-agent e-commerce assistant using LangGraph for orchestration and Tavily Search API for unified search + content retrieval.

---

## System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER QUERY                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       memory_init_node                          │
│  • Initialize session state                                     │
│  • Add query to conversation history                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      check_cache_node                           │
│  • Check Redis for cached results                               │
│  • Routes: cache_hit → advisor, miss → smart_planner            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     smart_planner_node                          │
│  • Classify query into 8 types                                  │
│  • Extract slots (budget, category, brand)                      │
│  • Generate search queries                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   follow_up_handler    parallel_search      fallback_handler
   (refinements)        (Tavily API)         (conversational)
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   parallel_search_node                          │
│  • Calls tavily_smart_search()                                  │
│  • Returns results with raw_content                             │
│  • No DDG/Brave dependency                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   variant_filter_node                           │
│  • Pass-through (no dedup/limits)                               │
│  • Tavily handles pre-filtering                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
   adviser_node                          best_under_discovery
   (standard queries)                    (budget queries)
        │                                           │
        │                                           ▼
        │                                     adviser_node
        │                                           │
        └───────────────────┬───────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       adviser_node                              │
│  • Receives candidates with raw_content                         │
│  • Single LLM call: extract + recommend                         │
│  • Uses Groq/OpenRouter for response                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                        final_answer
```

---

## Key Files

| File | Purpose |
|------|---------|
| `agent/multi_agent/graph.py` | LangGraph workflow definition |
| `agent/multi_agent/nodes.py` | Node implementations |
| `agent/multi_agent/run.py` | CLI entry point |
| `agent/multi_agent/smart_planner.py` | Query classification |
| `agent/multi_agent/state.py` | AgentState TypedDict |
| `config/tavily_config.py` | Tavily client setup |
| `scraping/tavily_search.py` | Tavily search functions |

---

## Query Types

| Type | Description | Flow |
|------|-------------|------|
| `price_search` | "iPhone 15 price" | → search → filter → advisor |
| `best_under` | "best laptop under 80k" | → search → filter → discovery → advisor |
| `comparison` | "iPhone vs Samsung" | → search → filter → advisor |
| `feature_query` | "phones with 120Hz" | → search → filter → advisor |
| `follow_up` | "show cheaper ones" | → follow_up_handler → advisor |
| `unknown` | General questions | → fallback_handler |

---

## Tavily Integration

### Functions
- `tavily_smart_search()` - Routes to appropriate search type
- `tavily_price_search()` - E-commerce focused
- `tavily_best_under_search()` - Budget queries with raw_content
- `tavily_comparison_search()` - Comparison pages

### Key Features
- `include_raw_content=True` - Full page content for advisor
- `include_domains` - Focus on trusted sites
- Pre-filtered, deduplicated results

---

## Environment Variables

```env
TAVILY_API_KEY=tvly-xxxxx
GROQ_API_KEY=gsk_xxxxx
OPENROUTER_API_KEY=sk-or-xxxxx  # Optional
```

---

## Running

```powershell
cd c:\product-AI
.\.venv\Scripts\activate
python -m agent.multi_agent.run
```

---

## Credit Usage (Tavily)

| Action | Credits |
|--------|---------|
| Basic search | ~0.1 |
| Search + raw_content | ~0.3-0.5 |
| Target: per query | <1.0 |
