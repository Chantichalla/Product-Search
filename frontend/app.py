"""
E-Commerce Agent - Streamlit Frontend

A chatbot interface for AI-powered product search and comparison.

Run with:
    streamlit run frontend/app.py --server.port 8501
"""
import streamlit as st
import requests
import time
from typing import Optional

# Configuration
API_URL = "http://localhost:8000/api"

# Page config
st.set_page_config(
    page_title="E-Commerce Agent",
    page_icon="🛒",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better chat UI
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
    }
    .stChatInput {
        padding: 0.5rem 0;
    }
    .main-header {
        text-align: center;
        padding: 1rem 0;
    }
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.8rem;
    }
    .status-online {
        background-color: #d4edda;
        color: #155724;
    }
    .status-offline {
        background-color: #f8d7da;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)


def check_api_health() -> bool:
    """Check if the backend API is running."""
    try:
        response = requests.get(f"{API_URL.replace('/api', '')}/", timeout=2)
        return response.status_code == 200
    except:
        return False


def send_message(message: str) -> Optional[dict]:
    """Send a message to the backend API."""
    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={"message": message},
            timeout=120  # 2 minute timeout for complex queries
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "response": f"Error: {response.status_code} - {response.text}",
                "status": "error",
                "execution_time": 0
            }
    except requests.exceptions.Timeout:
        return {
            "response": "⏰ Request timed out. The agent is taking too long to respond.",
            "status": "error",
            "execution_time": 0
        }
    except requests.exceptions.ConnectionError:
        return {
            "response": "🔌 Cannot connect to the backend. Make sure the API is running on http://localhost:8000",
            "status": "error",
            "execution_time": 0
        }


def clear_session():
    """Clear chat history and session."""
    st.session_state.messages = []
    try:
        requests.post(f"{API_URL}/clear", timeout=5)
    except:
        pass


# ============================================================
# MAIN UI
# ============================================================

# Header
st.markdown("<h1 class='main-header'>🛒 E-Commerce Agent</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>AI-powered product search and comparison</p>", unsafe_allow_html=True)

# API Status indicator
api_online = check_api_health()
if api_online:
    st.markdown("<p style='text-align: center;'><span class='status-badge status-online'>🟢 API Online</span></p>", unsafe_allow_html=True)
else:
    st.markdown("<p style='text-align: center;'><span class='status-badge status-offline'>🔴 API Offline - Start backend first</span></p>", unsafe_allow_html=True)
    st.info("💡 Start the backend with: `uvicorn backend.main:app --reload --port 8000`")

st.divider()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar with options
with st.sidebar:
    st.header("⚙️ Options")
    
    if st.button("🗑️ Clear Chat", use_container_width=True):
        clear_session()
        st.rerun()
    
    st.divider()
    
    st.markdown("### 💡 Try these queries:")
    example_queries = [
        "gaming phone under 45k",
        "best earbuds under 3k",
        "laptops under 1.5 lakh",
        "compare iPhone 15 vs Samsung S24",
    ]
    for query in example_queries:
        if st.button(query, use_container_width=True, key=f"example_{query}"):
            st.session_state.example_query = query
            st.rerun()
    
    st.divider()
    st.markdown("### 🔜 Coming Soon")
    st.markdown("- 🎤 Voice Input")
    st.markdown("- 📷 Image Input")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("execution_time"):
            st.caption(f"⏱️ {message['execution_time']:.1f}s")

# Handle example query from sidebar
if "example_query" in st.session_state:
    query = st.session_state.example_query
    del st.session_state.example_query
    
    # Add user message
    st.session_state.messages.append({"role": "user", "content": query})
    
    with st.chat_message("user"):
        st.markdown(query)
    
    # Get agent response
    with st.chat_message("assistant"):
        with st.spinner("🤔 Thinking..."):
            result = send_message(query)
            
            if result:
                st.markdown(result["response"])
                if result.get("execution_time"):
                    st.caption(f"⏱️ {result['execution_time']:.1f}s")
                
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["response"],
                    "execution_time": result.get("execution_time", 0)
                })
            else:
                st.error("Failed to get response from agent")

# Chat input
if prompt := st.chat_input("Ask about products... (e.g., 'gaming phone under 45k')"):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get and display agent response
    with st.chat_message("assistant"):
        with st.spinner("🤔 Thinking..."):
            result = send_message(prompt)
            
            if result:
                st.markdown(result["response"])
                if result.get("execution_time"):
                    st.caption(f"⏱️ {result['execution_time']:.1f}s")
                
                # Add to history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["response"],
                    "execution_time": result.get("execution_time", 0)
                })
            else:
                st.error("Failed to get response from agent")


# Footer
st.divider()
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 0.8rem;'>"
    "Powered by LangGraph + Groq + Ollama | Searches Flipkart & Amazon"
    "</p>",
    unsafe_allow_html=True
)
