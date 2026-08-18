"""
Conversational Handler - Local LLM for Greetings/Chitchat

Uses Ollama (local) to handle conversational queries without spending API credits.
This keeps the main LLMs focused on product-related queries.
"""

from typing import Optional


# ════════════════════════════════════════════════════════════
# CONVERSATIONAL PROMPT
# ════════════════════════════════════════════════════════════

CONVERSATIONAL_PROMPT = """You are ProductAI, a friendly shopping assistant for Indian consumers.

You help users find the best electronics, phones, laptops, headphones, and more.
You are knowledgeable about prices, specs, and deals in India.

User said: {message}

Respond naturally and briefly (1-2 sentences). If they seem to have a product intent, 
ask what they're looking for or if they need help finding something.

Examples:
- "Hi" → "Hello! 👋 What are you shopping for today?"
- "Thanks" → "You're welcome! Let me know if you need anything else."
- "Who are you" → "I'm ProductAI, your shopping assistant! I can help find the best deals on phones, laptops, and more."
"""


# ════════════════════════════════════════════════════════════
# QUICK RESPONSES (No LLM needed - instant)
# ════════════════════════════════════════════════════════════

INSTANT_RESPONSES = {
    "hi": "Hello! 👋 What are you shopping for today?",
    "hello": "Hi there! How can I help you find the perfect product?",
    "hey": "Hey! Ready to help you find the best deals.",
    "thanks": "You're welcome! Happy to help. 🛒",
    "thank you": "You're welcome! Need help with anything else?",
    "bye": "Goodbye! Happy shopping! 🛒",
    "goodbye": "See you later! Happy shopping!",
    "ok": "Great! Let me know if you need anything else.",
    "okay": "Perfect! What else can I help with?",
    "yes": "Got it! What would you like to know?",
    "no": "Alright! Let me know if you change your mind.",
    "cool": "Glad I could help! Anything else?",
    "great": "Awesome! What else can I help you find?",
    "nice": "Thanks! What can I help you with next?",
    "hmm": "Take your time! Let me know when you're ready to search.",
}


# ════════════════════════════════════════════════════════════
# HANDLER FUNCTION
# ════════════════════════════════════════════════════════════

def handle_conversational(message: str) -> str:
    """
    Handle conversational queries using instant responses or local LLM.
    
    Args:
        message: User's message
        
    Returns:
        Natural conversational response
    """
    msg_lower = message.lower().strip()
    
    # Check for instant responses first
    if msg_lower in INSTANT_RESPONSES:
        return INSTANT_RESPONSES[msg_lower]
    
    # For longer conversational messages, use local Ollama
    return _ollama_respond(message)


def _ollama_respond(message: str) -> str:
    """
    Use local Ollama model for conversational responses.
    Falls back to generic response if Ollama unavailable.
    """
    try:
        from langchain_ollama import ChatOllama
        
        # Use qwen3:4b - fast and good for chat
        llm = ChatOllama(
            model="qwen3:4b",
            base_url="http://localhost:11434",
            temperature=0.7
        )
        
        prompt = CONVERSATIONAL_PROMPT.format(message=message)
        response = llm.invoke(prompt)
        
        # Extract text from response
        if hasattr(response, 'content'):
            return response.content
        return str(response)
        
    except Exception as e:
        print(f"[Conversational] Ollama error: {e}")
        # Fallback to generic response
        return "I'm here to help with product recommendations! What are you looking for?"


# ════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing conversational handler...")
    
    test_messages = ["hi", "Hello there!", "thanks", "who are you?", "bye"]
    
    for msg in test_messages:
        print(f"\nUser: {msg}")
        print(f"Bot: {handle_conversational(msg)}")
