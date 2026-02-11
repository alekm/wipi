"""
User-Agent strings for device spoofing.

Provides realistic User-Agent strings that match DHCP personalities
for HTTP/HTTPS traffic generation.
"""
from typing import Optional


# Real User-Agent strings collected from actual devices
USER_AGENT_DATABASE = {
    # Apple iOS Devices (2026 - iOS 18.x)
    "iphone": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "ipad": "Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",

    # Apple macOS
    "macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "macbook": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",

    # Windows
    "windows10": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "windows11": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    # Android Devices
    "android": "Mozilla/5.0 (Linux; Android 14; SM-G991U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "samsung": "Mozilla/5.0 (Linux; Android 14; SM-S918U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "pixel": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",

    # Gaming Consoles
    "xbox": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; Xbox; Xbox One) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "playstation": "Mozilla/5.0 (PlayStation 4 5.55) AppleWebKit/601.2 (KHTML, like Gecko)",

    # Smart TVs
    "smart-tv-samsung": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 TV Safari/537.36",
    "smart-tv-lg": "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36 WebAppManager",

    # Smart Speakers
    "echo": "Mozilla/5.0 (Linux; Android 5.1.1; AFTT Build/LVY48F) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/41.0.2272.101 Mobile Safari/537.36",
    "echo-dot": "Mozilla/5.0 (Linux; Android 5.1.1; AFTT Build/LVY48F) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/41.0.2272.101 Mobile Safari/537.36",

    # Streaming Devices
    "chromecast": "Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.225 Safari/537.36 CrKey/1.56.500000",
    "roku": "Roku/DVP-9.20 (519.20E04111A)",

    # Linux
    "linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def get_user_agent_for_personality(personality: Optional[str] = None) -> str:
    """
    Get appropriate User-Agent string for a DHCP personality.

    Args:
        personality: DHCP personality name (e.g., "iphone", "windows10", "samsung")

    Returns:
        User-Agent string appropriate for the personality
    """
    if not personality:
        # Default to generic Linux if no personality specified
        return USER_AGENT_DATABASE["linux"]

    personality_lower = personality.lower()

    # Look up exact match
    if personality_lower in USER_AGENT_DATABASE:
        return USER_AGENT_DATABASE[personality_lower]

    # Fallback to generic Linux
    return USER_AGENT_DATABASE["linux"]
