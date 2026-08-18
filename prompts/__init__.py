"""
Prompts package for Product-AI
"""

from .advisor import (
    ADVISOR_SYSTEM_PROMPT,
    get_advisor_prompt,
    get_prompt_by_query_type,
    format_user_message,
    build_scraped_data_markdown,
)
from .enhancer import (
    generate_multi_queries,
    rewrite_query,
    rerank_results,
)

__all__ = [
    "ADVISOR_SYSTEM_PROMPT",
    "get_advisor_prompt",
    "get_prompt_by_query_type",
    "format_user_message",
    "build_scraped_data_markdown",
    "generate_multi_queries",
    "rewrite_query",
    "rerank_results",
]
