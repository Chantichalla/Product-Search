"""
User Agent Rotation for E-commerce Agent

Provides realistic user agents for web scraping.
Rotates between desktop and mobile UAs to appear more natural.
"""

import random
from typing import Optional


# Desktop User Agents (Chrome/Firefox on Windows/Mac)
DESKTOP_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Mobile User Agents (for mobile-first sites)
MOBILE_USER_AGENTS = [
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# Combined pool (default)
USER_AGENTS = DESKTOP_USER_AGENTS + MOBILE_USER_AGENTS


def get_random_user_agent(device_type: Optional[str] = None) -> str:
    """
    Get a random user agent string.
    
    Args:
        device_type: Optional filter - "desktop", "mobile", or None for any
        
    Returns:
        Random user agent string
    """
    if device_type == "desktop":
        return random.choice(DESKTOP_USER_AGENTS)
    elif device_type == "mobile":
        return random.choice(MOBILE_USER_AGENTS)
    else:
        # Prefer desktop (80%) for e-commerce scraping
        if random.random() < 0.8:
            return random.choice(DESKTOP_USER_AGENTS)
        return random.choice(MOBILE_USER_AGENTS)
