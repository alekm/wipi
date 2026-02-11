"""
MAC OUI (Organizationally Unique Identifier) Database

Provides vendor-specific MAC address prefixes for device spoofing.
"""
import random
from typing import List, Optional


# MAC OUI database - first 3 bytes (24 bits) identify manufacturer
# Format: "XX:XX:XX" - these will be combined with random last 3 bytes

MAC_OUI_DATABASE = {
    # Apple Inc.
    "apple": [
        "00:03:93",  # Apple
        "00:05:02",  # Apple
        "00:0A:27",  # Apple
        "00:0A:95",  # Apple
        "00:0D:93",  # Apple
        "00:14:51",  # Apple
        "00:16:CB",  # Apple
        "00:17:F2",  # Apple
        "00:19:E3",  # Apple
        "00:1B:63",  # Apple
        "00:1C:B3",  # Apple
        "00:1D:4F",  # Apple
        "00:1E:52",  # Apple
        "00:1F:5B",  # Apple
        "00:1F:F3",  # Apple
        "00:21:E9",  # Apple
        "00:22:41",  # Apple
        "00:23:12",  # Apple
        "00:23:32",  # Apple
        "00:23:6C",  # Apple
        "00:23:DF",  # Apple
        "00:24:36",  # Apple
        "00:25:00",  # Apple
        "00:25:4B",  # Apple
        "00:25:BC",  # Apple
        "00:26:08",  # Apple
        "00:26:4A",  # Apple
        "00:26:B0",  # Apple
        "00:26:BB",  # Apple
        "04:0C:CE",  # Apple
        "04:15:52",  # Apple
        "04:26:65",  # Apple
        "08:66:98",  # Apple
        "0C:3E:9F",  # Apple
        "0C:74:C2",  # Apple
        "10:40:F3",  # Apple
        "14:10:9F",  # Apple
        "14:5A:05",  # Apple
        "18:34:51",  # Apple
        "1C:AB:A7",  # Apple
        "20:C9:D0",  # Apple
        "24:A0:74",  # Apple
        "28:37:37",  # Apple
        "28:E1:4C",  # Apple
        "2C:B4:3A",  # Apple
        "30:90:AB",  # Apple
        "34:12:F9",  # Apple
        "38:C9:86",  # Apple
        "3C:15:C2",  # Apple
        "40:30:04",  # Apple
        "44:4C:0C",  # Apple
        "48:60:BC",  # Apple
        "4C:57:CA",  # Apple
        "50:EA:D6",  # Apple
        "54:26:96",  # Apple
        "58:55:CA",  # Apple
        "5C:59:48",  # Apple
        "5C:95:AE",  # Apple
        "60:33:4B",  # Apple
        "64:B0:A6",  # Apple
        "68:96:7B",  # Apple
        "6C:40:08",  # Apple
        "70:11:24",  # Apple
        "70:CD:60",  # Apple
        "74:E2:F5",  # Apple
        "78:67:D7",  # Apple
        "7C:01:91",  # Apple
        "7C:6D:62",  # Apple
        "80:49:71",  # Apple
        "84:38:35",  # Apple
        "88:53:95",  # Apple
        "8C:85:90",  # Apple
        "90:27:E4",  # Apple
        "90:72:40",  # Apple
        "94:E9:6A",  # Apple
        "98:03:D8",  # Apple
        "9C:20:7B",  # Apple
        "A0:99:9B",  # Apple
        "A4:B1:97",  # Apple
        "A8:66:7F",  # Apple
        "AC:BC:32",  # Apple
        "AC:DE:48",  # Apple
        "B0:65:BD",  # Apple
        "B4:F0:AB",  # Apple
        "B8:09:8A",  # Apple
        "B8:E8:56",  # Apple
        "BC:3B:AF",  # Apple
        "BC:52:B7",  # Apple
        "C0:84:7D",  # Apple
        "C4:2C:03",  # Apple
        "C8:2A:14",  # Apple
        "CC:29:F5",  # Apple
        "D0:23:DB",  # Apple
        "D0:A6:37",  # Apple
        "D4:9A:20",  # Apple
        "D8:30:62",  # Apple
        "DC:86:D8",  # Apple
        "E0:F8:47",  # Apple
        "E4:CE:8F",  # Apple
        "E8:80:2E",  # Apple
        "F0:DB:E2",  # Apple
        "F4:F1:51",  # Apple
        "F8:1E:DF",  # Apple
        "FC:25:3F",  # Apple
    ],

    # Microsoft Corporation
    "microsoft": [
        "00:03:FF",  # Microsoft
        "00:0D:3A",  # Microsoft
        "00:12:5A",  # Microsoft
        "00:15:5D",  # Microsoft (Hyper-V)
        "00:17:FA",  # Microsoft
        "00:1D:D8",  # Microsoft
        "00:22:48",  # Microsoft
        "00:25:AE",  # Microsoft
        "00:50:F2",  # Microsoft
        "18:65:90",  # Microsoft
        "1C:3E:84",  # Microsoft
        "28:18:78",  # Microsoft
        "30:59:B7",  # Microsoft (Surface)
        "50:1A:C5",  # Microsoft (Xbox)
        "64:00:F1",  # Microsoft
        "7C:1E:52",  # Microsoft (Surface)
        "98:5F:D3",  # Microsoft (Surface)
        "A0:CE:C8",  # Microsoft (Surface)
        "D0:17:C2",  # Microsoft (Surface)
        "E0:D5:5E",  # Microsoft
    ],

    # Samsung Electronics
    "samsung": [
        "00:00:F0",  # Samsung
        "00:12:47",  # Samsung
        "00:12:FB",  # Samsung
        "00:13:77",  # Samsung
        "00:15:99",  # Samsung
        "00:15:B9",  # Samsung
        "00:16:32",  # Samsung
        "00:16:6B",  # Samsung
        "00:16:6C",  # Samsung
        "00:17:C9",  # Samsung
        "00:17:D5",  # Samsung
        "00:18:AF",  # Samsung
        "00:1A:8A",  # Samsung
        "00:1B:98",  # Samsung
        "00:1C:43",  # Samsung
        "00:1D:25",  # Samsung
        "00:1E:7D",  # Samsung
        "00:1F:CC",  # Samsung
        "00:21:19",  # Samsung
        "00:21:4C",  # Samsung
        "00:23:39",  # Samsung
        "00:23:D6",  # Samsung
        "00:23:D7",  # Samsung
        "00:24:54",  # Samsung
        "00:24:90",  # Samsung
        "00:24:91",  # Samsung
        "00:25:38",  # Samsung
        "00:25:66",  # Samsung
        "00:26:37",  # Samsung
        "00:E0:64",  # Samsung
        "04:18:0F",  # Samsung
        "08:08:C2",  # Samsung
        "08:D4:2B",  # Samsung
        "0C:14:20",  # Samsung
        "0C:89:10",  # Samsung
        "10:30:47",  # Samsung
        "10:77:B1",  # Samsung
        "14:7D:C5",  # Samsung
        "18:3F:47",  # Samsung
        "1C:5A:3E",  # Samsung
        "20:64:32",  # Samsung
        "24:DA:33",  # Samsung
        "28:39:5E",  # Samsung
        "2C:44:01",  # Samsung
        "30:19:66",  # Samsung
        "34:23:BA",  # Samsung
        "38:0A:94",  # Samsung
        "3C:5A:37",  # Samsung
        "40:0E:85",  # Samsung
        "44:4E:1A",  # Samsung
        "48:5A:3F",  # Samsung
        "4C:BC:A5",  # Samsung
        "50:32:37",  # Samsung
        "54:88:0E",  # Samsung
        "58:A2:B5",  # Samsung
        "5C:0A:5B",  # Samsung
        "60:6B:FF",  # Samsung
        "64:77:91",  # Samsung
        "68:EB:AE",  # Samsung
        "6C:2F:2C",  # Samsung
        "70:5A:0F",  # Samsung
        "74:45:8A",  # Samsung
        "78:1F:DB",  # Samsung
        "7C:61:66",  # Samsung
        "80:57:19",  # Samsung
        "84:25:DB",  # Samsung
        "88:32:9B",  # Samsung
        "8C:77:12",  # Samsung
        "90:18:7C",  # Samsung
        "94:51:03",  # Samsung
        "98:52:B1",  # Samsung
        "9C:02:98",  # Samsung
        "A0:07:98",  # Samsung
        "A4:EB:D3",  # Samsung
        "A8:F2:74",  # Samsung
        "AC:36:13",  # Samsung
        "B0:C5:59",  # Samsung
        "B4:79:A7",  # Samsung
        "B8:5E:7B",  # Samsung
        "BC:14:85",  # Samsung
        "C0:BD:D1",  # Samsung
        "C4:42:02",  # Samsung
        "C8:19:F7",  # Samsung
        "CC:05:1B",  # Samsung
        "D0:17:6A",  # Samsung
        "D4:87:D8",  # Samsung
        "D8:57:EF",  # Samsung
        "DC:71:44",  # Samsung
        "E0:99:71",  # Samsung
        "E4:12:1D",  # Samsung
        "E8:03:9A",  # Samsung
        "EC:1D:8B",  # Samsung
        "F0:25:B7",  # Samsung
        "F4:09:D8",  # Samsung
        "F8:04:2E",  # Samsung
        "FC:00:12",  # Samsung
    ],

    # Google (Pixel phones)
    "google": [
        "00:1A:11",  # Google
        "3C:5A:B4",  # Google
        "54:60:09",  # Google
        "68:C6:3A",  # Google (Pixel)
        "74:E5:43",  # Google (Pixel)
        "84:CF:BF",  # Google (Pixel)
        "AC:37:43",  # Google
        "B4:F6:1C",  # Google (Pixel)
        "C4:0B:CB",  # Google (Pixel)
        "DC:A9:04",  # Google (Pixel)
        "F8:8F:CA",  # Google
    ],

    # LG Electronics
    "lg": [
        "00:1C:62",  # LG
        "00:E0:91",  # LG
        "10:68:3F",  # LG
        "34:FC:B9",  # LG
        "58:A2:B5",  # LG
        "B4:E6:2A",  # LG
    ],
}


def get_random_mac_for_vendor(vendor: str) -> str:
    """
    Generate a random MAC address with the specified vendor's OUI.

    Args:
        vendor: Vendor name (apple, microsoft, samsung, google, lg)

    Returns:
        Full MAC address string (XX:XX:XX:XX:XX:XX)
    """
    vendor_lower = vendor.lower()

    if vendor_lower not in MAC_OUI_DATABASE:
        # Fallback to random MAC if vendor unknown
        return generate_random_mac()

    # Pick random OUI from vendor's list
    oui = random.choice(MAC_OUI_DATABASE[vendor_lower])

    # Generate random last 3 bytes
    random_bytes = [random.randint(0, 255) for _ in range(3)]
    random_suffix = ":".join([f"{b:02X}" for b in random_bytes])

    return f"{oui}:{random_suffix}"


def generate_random_mac() -> str:
    """
    Generate a completely random MAC address.
    Sets the locally administered bit to avoid conflicts.

    Returns:
        Random MAC address string
    """
    # Generate 6 random bytes
    mac_bytes = [random.randint(0, 255) for _ in range(6)]

    # Set locally administered bit (bit 1 of first byte)
    # This avoids conflicts with real manufacturer MACs
    mac_bytes[0] = (mac_bytes[0] & 0xFE) | 0x02

    return ":".join([f"{b:02X}" for b in mac_bytes])


def get_vendor_for_personality(personality: str) -> Optional[str]:
    """
    Map DHCP personality to MAC vendor.

    Args:
        personality: DHCP personality (e.g., "iphone", "windows10", "samsung")

    Returns:
        Vendor name for MAC OUI lookup, or None for random
    """
    personality_lower = personality.lower()

    # iOS devices
    if personality_lower in ["iphone", "ipad", "macos", "macbook"]:
        return "apple"

    # Windows devices
    if personality_lower in ["windows10", "windows11", "xbox"]:
        return "microsoft"

    # Samsung devices
    if personality_lower in ["samsung"]:
        return "samsung"

    # Google devices
    if personality_lower in ["pixel"]:
        return "google"

    # Android (generic) - mix of vendors
    if personality_lower == "android":
        return random.choice(["samsung", "google", "lg"])

    # Smart TVs
    if personality_lower == "smart-tv-samsung":
        return "samsung"
    if personality_lower == "smart-tv-lg":
        return "lg"

    # Everything else gets random MAC
    return None


def get_mac_for_personality(personality: Optional[str] = None) -> str:
    """
    Generate appropriate MAC address for a DHCP personality.

    Args:
        personality: DHCP personality name

    Returns:
        MAC address string with appropriate vendor OUI
    """
    if not personality:
        return generate_random_mac()

    vendor = get_vendor_for_personality(personality)

    if vendor:
        return get_random_mac_for_vendor(vendor)
    else:
        return generate_random_mac()
