"""
LLM Configuration - Centralized LLM Instances

This module provides pre-configured LLM instances for different use cases.
Import the LLM you need instead of defining it in every file.

Usage:
    from config.llm_config import planner_llm, advisor_llm, local_llm
"""

import os
from functools import lru_cache
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ============================================================
# LLM CONFIGURATIONS
# ============================================================

client = Anthropic(
    base_url=os.getenv("ANTHROPIC_BASE_URL"),
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

class LLMConfig:
    """
    Centralized LLM configurations.
    
    Categories:
    - FAST: Quick classification, simple tasks (< 500ms)
    - STANDARD: General purpose, balanced speed/quality
    - POWERFUL: Complex reasoning, final recommendations
    - LOCAL: Ollama models for offline/free usage
    """
    
    # Groq Models (Fast Cloud Inference)
    GROQ_FAST = {
        "model": "llama-3.1-8b-instant",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "temperature": 0,
        "max_tokens": 1024,
    }
    
    GROQ_TOOL_USE = {
        "model": "moonshotai/kimi-k2-instruct-0905",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "temperature": 0,
        "max_tokens": 2048,
    }
    
    GROQ_POWERFUL = {
        "model": "openai/gpt-oss-120b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    
    # =========================================
    # Options: gemini-2.5-flash , gemini-2.5-pro , gemini-3-pro-high(thinking), gemini-3-flash
    # =========================================
    
 
    ANTHROPIC_FAST = {
        "model": "gemini-2.5-flash",  # Fast responses via proxy
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    ANTHROPIC_STANDARD = {
        "model": "gemini-3-pro-low",  # Balanced quality/speed
        "max_tokens": 2048,
        "temperature": 0.7,
    }
    ANTHROPIC_EXTRACT = {
        "model": "gemini-2.0-flash",
        "max_tokens": 2048,
        "temperature": 0.7,
    }
    ANTHROPIC_POWERFUL = {
        "model": "gemini-3-pro-high",  # Deep reasoning
        "max_tokens": 4096,
        "temperature": 0.5,
    }

    ANTHROPIC_TOOL_USE = {
        "model": "gemini-3-flash",  # Best for function calling
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    GOOGLE_FAST = {
        "model": "gemini-2.5-flash",  # Higher quota, fast
        "max_output_tokens": 1024,
        "temperature": 0.7,
    }

    GOOGLE_STANDARD = {
        "model": "gemini-2-pro",  # Balanced speed/quality
        "max_output_tokens": 2048,
        "temperature": 0.7,
    }

    GOOGLE_POWERFUL = {
        "model": "gemini-2.5-pro",  # Best quality
        "max_output_tokens": 4096,
        "temperature": 0.5,
    }
    
    GOOGLE_LITE = {
        "model": "gemini-2.5-flash-lite",  # Fast queries, 65K output
        "max_output_tokens": 2048,
        "temperature": 0.3,
    }
    
    GOOGLE_ADVISOR = {
        "model": "gemini-3-flash-preview",  # Product advisor reasoning (correct API name)
        "max_output_tokens": 8192,
        "temperature": 0.7,
    }
    
    # Ollama Local Models (RTX 3050 6GB Compatible)
    OLLAMA_QWEN_SMALL = {
        "model": "qwen3:1.7b",
        "base_url": OLLAMA_BASE_URL,
        "temperature": 0,
    }
    
    OLLAMA_QWEN_CODER = {
        "model": "qwen3.5:4b",
        "base_url": OLLAMA_BASE_URL,
        "temperature": 0,
    }
    
    OLLAMA_LLAMA_SMALL = {
        "model": "llama3.2:3b",
        "base_url": OLLAMA_BASE_URL,
        "temperature": 0,
    }
    # Vision-LM's (local)
    OLLAMA_QWEN_VISION ={
        "model":"qwen3-VL:4b",
        "base_url":OLLAMA_BASE_URL,
        "temperature":0
    }

# ============================================================
# LLM FACTORY FUNCTIONS (Using Anthropic via Proxy)
# ============================================================

@lru_cache(maxsize=1)
def get_query_planner_llm():
    """
    LLM for quick query classification.
    Uses ANTHROPIC_FAST - fastest response time.
    """
    config = LLMConfig.ANTHROPIC_FAST
    
    def invoke(prompt: str, **kwargs):
        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config.get("temperature", 0.7),
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.content[0].text
    
    return type("QueryPlannerLLM", (), {
        "invoke": staticmethod(invoke),
        "config": config,
        "client": client
    })()


@lru_cache(maxsize=1)
def get_planner_llm():
    """
    LLM for detailed planning and orchestration.
    Uses ANTHROPIC_STANDARD - balanced quality/speed.
    """
    config = LLMConfig.ANTHROPIC_STANDARD
    
    def invoke(prompt: str, **kwargs):
        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config.get("temperature", 0.7),
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.content[0].text
    
    return type("PlannerLLM", (), {
        "invoke": staticmethod(invoke),
        "config": config,
        "client": client
    })()


@lru_cache(maxsize=1)
def get_tool_llm():
    """
    LLM optimized for tool/function calling.
    Uses ANTHROPIC_TOOL_USE - best for structured output.
    """
    config = LLMConfig.ANTHROPIC_TOOL_USE
    
    def invoke(prompt: str, tools: list = None, **kwargs):
        params = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "temperature": config.get("temperature", 0.3),
            "messages": [{"role": "user", "content": prompt}],
        }
        if tools:
            params["tools"] = tools
        response = client.messages.create(**params, **kwargs)
        return response
    
    return type("ToolLLM", (), {
        "invoke": staticmethod(invoke),
        "config": config,
        "client": client
    })()


@lru_cache(maxsize=1)
def get_advisor_llm():
    """
    Powerful LLM for final recommendations.
    Uses ANTHROPIC_POWERFUL - deep reasoning capability.
    """
    config = LLMConfig.ANTHROPIC_TOOL_USE
    
    def invoke(prompt: str, **kwargs):
        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config.get("temperature", 0.5),
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        # Option 1: Filter by type (ignore thinking blocks)
        for block in response.content:
            if hasattr(block, 'type') and block.type == 'text':
                return block.text
        
        # Fallback to first block if no text type found or simple string
        return response.content[0].text if response.content else ""
    
    return type("AdvisorLLM", (), {
        "invoke": staticmethod(invoke),
        "config": config,
        "client": client
    })()


@lru_cache(maxsize=1)
def get_extraction_llm():
    """
    LLM for universal product extraction from list pages.
    Uses ANTHROPIC_EXTRACT - Gemini 2.0 Flash via Anthropic proxy.
    Good balance of speed and JSON extraction quality.
    """
    config = LLMConfig.ANTHROPIC_EXTRACT
    
    def invoke(prompt: str, **kwargs):
        response = client.messages.create(
            model=config["model"],
            max_tokens=config["max_tokens"],
            temperature=config.get("temperature", 0.7),
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.content[0].text
    
    return type("ExtractionAnthropicLLM", (), {
        "invoke": staticmethod(invoke),
        "config": config,
        "client": client
    })()


# ============================================================
# GOOGLE GEMINI SDK FACTORY FUNCTIONS
# ============================================================

def get_google_client():
    """Get Google Generative AI client"""
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    return genai


@lru_cache(maxsize=1)
def get_google_fast():
    """
    Fast Google Gemini model.
    Uses Gemini Flash.
    """
    genai = get_google_client()
    config = LLMConfig.GOOGLE_FAST
    model = genai.GenerativeModel(config["model"])
    
    def invoke(prompt: str, **kwargs):
        response = model.generate_content(prompt)
        return response.text
    
    return type("GoogleFast", (), {"invoke": staticmethod(invoke), "model": model, "config": config})()


@lru_cache(maxsize=1)
def get_google_powerful():
    """
    Powerful Google Gemini model.
    Uses Gemini Pro.
    """
    genai = get_google_client()
    config = LLMConfig.GOOGLE_POWERFUL
    model = genai.GenerativeModel(config["model"])
    
    def invoke(prompt: str, **kwargs):
        response = model.generate_content(prompt)
        return response.text
    
    return type("GooglePowerful", (), {"invoke": staticmethod(invoke), "model": model, "config": config})()


@lru_cache(maxsize=1)
def get_google_lite():
    """
    Ultra-fast Google Gemini model for extraction.
    Uses Gemini 2.0 Flash Lite - fastest and lowest cost.
    """
    genai = get_google_client()
    config = LLMConfig.GOOGLE_LITE
    model = genai.GenerativeModel(config["model"])
    
    def invoke(prompt: str, **kwargs):
        response = model.generate_content(prompt)
        return response.text
    
    return type("GoogleLite", (), {"invoke": staticmethod(invoke), "model": model, "config": config})()


@lru_cache(maxsize=1)
def get_google_advisor():
    """
    Google Gemini model for product analysis and recommendations.
    Uses Gemini 3 Flash - balanced quality and speed.
    """
    genai = get_google_client()
    config = LLMConfig.GOOGLE_ADVISOR
    model = genai.GenerativeModel(config["model"])
    
    def invoke(prompt: str, **kwargs):
        response = model.generate_content(prompt)
        return response.text
    
    return type("GoogleAdvisor", (), {"invoke": staticmethod(invoke), "model": model, "config": config})()

# --- Ollama Factory functions ---
@lru_cache(maxsize=1)
def get_local_llm():
    """
    Local Ollama LLM for offline/free usage.
    Runs on RTX 3050 6GB (quantized).
    """
    from langchain_ollama import ChatOllama
    
    config = LLMConfig.OLLAMA_MISTRAL
    return ChatOllama(
        model=config["model"],
        base_url=config["base_url"],
        temperature=config["temperature"],
    )


@lru_cache(maxsize=1)
def get_local_coder_llm():
    """
    Local Qwen Coder for query decomposition.
    Good at structured reasoning and extraction.
    """
    from langchain_ollama import ChatOllama
    
    config = LLMConfig.OLLAMA_QWEN_CODER
    return ChatOllama(
        model=config["model"],
        base_url=config["base_url"],
        temperature=config["temperature"],
    )


@lru_cache(maxsize=1)
def get_groq_extraction_llm():
    """
    LLM optimized for product extraction from scraped content.
    Uses Groq Llama 3.3 70B with zero temperature for consistent JSON.
    """
    from langchain_openai import ChatOpenAI
    
    config = LLMConfig.GROQ_EXTRACTION
    return ChatOpenAI(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
    )


@lru_cache(maxsize=1)
def get_groq_powerful_llm():
    """
    LLM optimized for powerful reasoning and extraction from scraped content.
    Uses GROQ_POWERFUL (currently mapped to openai/gpt-oss-120b).
    """
    from langchain_openai import ChatOpenAI
    
    config = LLMConfig.GROQ_POWERFUL
    return ChatOpenAI(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
    )

@lru_cache(maxsize=1)
def get_local_title_llm():
    """
    Local LLM specifically for Session Naming.
    Uses Qwen 3 1.7B (Fast & Efficient).
    """
    from langchain_ollama import ChatOllama
    
    # Use OLLAMA_QWEN_SMALL if defined, else fallback to Mistral
    if hasattr(LLMConfig, "OLLAMA_QWEN_SMALL"):
        config = LLMConfig.OLLAMA_QWEN_SMALL
    else:
        config = LLMConfig.OLLAMA_MISTRAL
        
    return ChatOllama(
        model=config["model"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        # Add a timeout so it doesn't hang forever if Ollama is slow
        timeout=10 
    )


@lru_cache(maxsize=1)
def get_local_vision_llm():
    """
    Local Vision-Language Model for image detail extraction.
    Uses Qwen3-VL 4B via Ollama - can analyze product images
    and extract structured details (brand, type, features).
    """
    from langchain_ollama import ChatOllama
    
    config = LLMConfig.OLLAMA_QWEN_VISION
    return ChatOllama(
        model=config["model"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        timeout=120  # Vision models need more time for image processing
    )


# ============================================================
# CONVENIENCE ALIASES (Direct Import)
# ============================================================

# Use these for simple imports:
# from config.llm_config import planner_llm, advisor_llm

class _LazyLLM:
    """Lazy loader to avoid initialization at import time"""
    
    def __init__(self, getter):
        self._getter = getter
        self._instance = None
    
    def __getattr__(self, name):
        if self._instance is None:
            self._instance = self._getter()
        return getattr(self._instance, name)
    
    def invoke(self, *args, **kwargs):
        if self._instance is None:
            self._instance = self._getter()
        return self._instance.invoke(*args, **kwargs)
    
    def bind_tools(self, *args, **kwargs):
        if self._instance is None:
            self._instance = self._getter()
        return self._instance.bind_tools(*args, **kwargs)


# Pre-configured LLM instances (lazy loaded)
planner_llm = _LazyLLM(get_planner_llm)
tool_llm = _LazyLLM(get_tool_llm)
advisor_llm = _LazyLLM(get_advisor_llm)
local_llm = _LazyLLM(get_local_llm)
local_coder_llm = _LazyLLM(get_local_coder_llm)
local_vision_llm = _LazyLLM(get_local_vision_llm)
groq_powerful_llm = _LazyLLM(get_groq_powerful_llm)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_llm_by_name(name: str):
    """
    Get LLM instance by name.
    
    Args:
        name: One of 'planner', 'tool', 'advisor', 'local', 'local_coder'
    
    Returns:
        LLM instance
    """
    llm_map = {
        "planner": get_planner_llm,
        "tool": get_tool_llm,
        "advisor": get_advisor_llm,
        "local": get_local_llm,
        "local_coder": get_local_coder_llm,
        "local_vision": get_local_vision_llm,
    }
    
    if name not in llm_map:
        raise ValueError(f"Unknown LLM: {name}. Available: {list(llm_map.keys())}")
    
    return llm_map[name]()


def list_available_llms():
    """List all available LLM configurations"""
    return {
        "cloud": {
            "planner_llm": "Groq Llama 3.1 8B (fast classification)",
            "tool_llm": "Groq Llama 3 8B Tool Use (function calling)",
            "advisor_llm": "Groq Llama 3.3 70B (powerful reasoning)",
        },
        "local": {
            "local_llm": "Ollama Mistral 7B Q4 (general purpose)",
            "local_coder_llm": "Ollama Qwen2.5 Coder 7B Q4 (structured extraction)",
        }
    }


# ============================================================
# HEALTH CHECK
# ============================================================

def check_llm_availability():
    """
    Check which LLMs are available.
    Returns dict with status of each LLM.
    """
    results = {}
    
    # Check Groq
    if GROQ_API_KEY:
        try:
            llm = get_planner_llm()
            llm.invoke("test")
            results["groq"] = "✅ Available"
        except Exception as e:
            results["groq"] = f"❌ Error: {str(e)[:50]}"
    else:
        results["groq"] = "⚠️ No API key"
    
    # Check Ollama
    try:
        import requests
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            results["ollama"] = f"✅ Available ({len(models)} models)"
        else:
            results["ollama"] = "❌ Not responding"
    except Exception:
        results["ollama"] = "❌ Not running"
    
    return results


if __name__ == "__main__":
    print("LLM Configuration Check")
    print("=" * 40)
    
    for provider, status in check_llm_availability().items():
        print(f"{provider}: {status}")
    
    print("\nAvailable LLMs:")
    for category, llms in list_available_llms().items():
        print(f"\n{category.upper()}:")
        for name, desc in llms.items():
            print(f"  • {name}: {desc}")
