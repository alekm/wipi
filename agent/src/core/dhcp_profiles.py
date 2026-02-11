"""
DHCP Fingerprinting Profiles - Mimic different device types.

These profiles define DHCP options and hostname patterns to make
Raspberry Pis appear as different device types to network equipment.
"""
import random
from typing import Dict, List, Optional


class DHCPProfile:
    """DHCP fingerprint profile for a device type."""

    def __init__(
        self,
        name: str,
        hostname_pattern: str,
        vendor_class: Optional[str] = None,
        request_options: Optional[List[int]] = None,
        user_agent: Optional[str] = None,
        description: str = ""
    ):
        self.name = name
        self.hostname_pattern = hostname_pattern
        self.vendor_class = vendor_class
        self.request_options = request_options or []
        self.user_agent = user_agent
        self.description = description

    def generate_hostname(self) -> str:
        """Generate a hostname based on the pattern."""
        if "{random}" in self.hostname_pattern:
            # Generate random suffix
            random_suffix = random.randint(1000, 9999)
            return self.hostname_pattern.replace("{random}", str(random_suffix))
        return self.hostname_pattern

    def get_dhclient_config(self, hostname: Optional[str] = None) -> str:
        """Generate dhclient.conf content for this profile."""
        if hostname is None:
            hostname = self.generate_hostname()

        config_lines = [
            f"# DHCP fingerprint profile: {self.name}",
            f"# {self.description}",
            "",
            f'send host-name "{hostname}";',
        ]

        # Only add FQDN options for Apple devices
        if self.name in ["Apple iPhone", "Apple iPad", "macOS (MacBook/iMac)", "MacBook"]:
            config_lines.extend([
                f'send fqdn.fqdn "{hostname}";',
                'send fqdn.encoded on;',
                'send fqdn.no-client-update on;',
                'send fqdn.server-update on;',
            ])

        # Add vendor class identifier if specified
        if self.vendor_class:
            config_lines.append(f'send vendor-class-identifier "{self.vendor_class}";')

        # Add request parameters in specific order
        if self.request_options:
            # Map DHCP option numbers to dhclient parameter names
            # Only including options that dhclient knows natively (no custom definitions needed)
            option_names = {
                1: "subnet-mask",
                3: "routers",
                6: "domain-name-servers",
                12: "host-name",
                15: "domain-name",
                26: "interface-mtu",
                28: "broadcast-address",
                31: "router-discovery",
                33: "static-routes",
                42: "ntp-servers",
                44: "netbios-name-servers",
                46: "netbios-dd-server",
                47: "netbios-node-type",
                51: "dhcp-lease-time",
                58: "dhcp-renewal-time",
                59: "dhcp-rebinding-time",
                119: "domain-search",
                # Removed: 78, 79, 95, 121, 249, 252 (require custom definitions)
            }

            # Build request list
            requested = []
            for opt in self.request_options:
                if opt in option_names:
                    requested.append(option_names[opt])

            if requested:
                # Format with line wrapping for readability
                config_lines.append("")
                config_lines.append("request " + ",\n        ".join(requested) + ";")

        return "\n".join(config_lines) + "\n"


# Define DHCP profiles for different device types
DHCP_PROFILES: Dict[str, DHCPProfile] = {
    "windows10": DHCPProfile(
        name="Windows 10/11 Desktop",
        hostname_pattern="DESKTOP-{random}",
        vendor_class="MSFT 5.0",
        request_options=[1, 15, 3, 6, 44, 46, 47, 31, 33, 121, 249, 43],
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="Windows 10/11 desktop or laptop"
    ),

    "windows11": DHCPProfile(
        name="Windows 11 Desktop",
        hostname_pattern="DESKTOP-{random}",
        vendor_class="MSFT 5.0",
        request_options=[1, 15, 3, 6, 44, 46, 47, 31, 33, 121, 249, 43],
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="Windows 11 desktop or laptop"
    ),

    "macos": DHCPProfile(
        name="macOS (MacBook/iMac)",
        hostname_pattern="MacBook-Pro-{random}",
        vendor_class=None,  # macOS typically doesn't send vendor class
        request_options=[1, 3, 6, 15, 119, 252],
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        description="Apple macOS device"
    ),

    "macbook": DHCPProfile(
        name="MacBook",
        hostname_pattern="MacBook-{random}",
        vendor_class=None,
        request_options=[1, 3, 6, 15, 119, 252],
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        description="Apple MacBook laptop"
    ),

    "iphone": DHCPProfile(
        name="Apple iPhone",
        hostname_pattern="iPhone-{random}",
        vendor_class=None,  # iOS typically doesn't send vendor class in DHCP
        request_options=[1, 3, 6, 12, 15, 119, 78, 79, 95, 252],  # iOS with option 12 (hostname)
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        description="Apple iPhone"
    ),

    "ipad": DHCPProfile(
        name="Apple iPad",
        hostname_pattern="iPad-{random}",
        vendor_class=None,  # iOS typically doesn't send vendor class in DHCP
        request_options=[1, 3, 6, 12, 15, 119, 78, 79, 95, 252],  # iOS with option 12 (hostname)
        user_agent="Mozilla/5.0 (iPad; CPU OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
        description="Apple iPad tablet"
    ),

    "android": DHCPProfile(
        name="Android Phone/Tablet",
        hostname_pattern="android-{random}",
        vendor_class="android-dhcp-11",
        request_options=[1, 121, 33, 3, 6, 28, 51, 58, 59],  # Real Android fingerprint from Fingerbank
        user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        description="Generic Android device"
    ),

    "samsung": DHCPProfile(
        name="Samsung Galaxy",
        hostname_pattern="Galaxy-{random}",
        vendor_class="android-dhcp-13",
        request_options=[1, 3, 6, 15, 28, 33, 51, 58, 59, 121],  # Real Samsung Android fingerprint from Fingerbank
        user_agent="Mozilla/5.0 (Linux; Android 14; SM-S911U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        description="Samsung Galaxy phone/tablet"
    ),

    "pixel": DHCPProfile(
        name="Google Pixel",
        hostname_pattern="Pixel-{random}",
        vendor_class="android-dhcp-13",
        request_options=[1, 3, 6, 15, 26, 28, 51, 58, 59],
        user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        description="Google Pixel phone"
    ),

    "echo": DHCPProfile(
        name="Amazon Echo",
        hostname_pattern="Echo-{random}",
        vendor_class="dhcpcd-6.8.2:Linux-3.18.22-WeTek-4.9+",
        request_options=[1, 3, 6, 15, 12],
        user_agent="Mozilla/5.0 (Linux; Android 5.1.1; AFTA Build/LVY48F) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/41.0.2272.118 Safari/537.36",
        description="Amazon Echo smart speaker"
    ),

    "echo-dot": DHCPProfile(
        name="Amazon Echo Dot",
        hostname_pattern="Echo-Dot-{random}",
        vendor_class="dhcpcd-6.8.2:Linux-3.18.22-WeTek-4.9+",
        request_options=[1, 3, 6, 15, 12],
        user_agent="Mozilla/5.0 (Linux; Android 5.1.1; AFTA Build/LVY48F) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/41.0.2272.118 Safari/537.36",
        description="Amazon Echo Dot"
    ),

    "xbox": DHCPProfile(
        name="Xbox One/Series",
        hostname_pattern="XboxOne-{random}",
        vendor_class="MSFT 5.0",
        request_options=[1, 3, 6, 15, 44, 46, 47],
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; Xbox; Xbox Series X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edge/44.18363.8131",
        description="Microsoft Xbox gaming console"
    ),

    "playstation": DHCPProfile(
        name="PlayStation 5",
        hostname_pattern="PlayStation-{random}",
        vendor_class=None,
        request_options=[1, 3, 6, 15, 12],
        user_agent="Mozilla/5.0 (PlayStation; PlayStation 5/6.00) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
        description="Sony PlayStation console"
    ),

    "smart-tv-samsung": DHCPProfile(
        name="Samsung Smart TV",
        hostname_pattern="Samsung-TV-{random}",
        vendor_class="Samsung",
        request_options=[1, 3, 6, 12, 15, 28, 42],
        user_agent="Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/85.0.4183.93 TV Safari/537.36",
        description="Samsung Smart TV"
    ),

    "smart-tv-lg": DHCPProfile(
        name="LG Smart TV",
        hostname_pattern="LG-webOS-{random}",
        vendor_class="LG",
        request_options=[1, 3, 6, 12, 15, 28, 42],
        user_agent="Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36 WebAppManager",
        description="LG webOS Smart TV"
    ),

    "linux": DHCPProfile(
        name="Linux Desktop",
        hostname_pattern="ubuntu-{random}",
        vendor_class="dhcpcd-9.4.1",
        request_options=[1, 28, 2, 3, 15, 6, 119, 12, 44, 47, 26, 121, 42],
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        description="Generic Linux desktop"
    ),

    "chromecast": DHCPProfile(
        name="Google Chromecast",
        hostname_pattern="Chromecast-{random}",
        vendor_class=None,
        request_options=[1, 3, 6, 15, 12],
        user_agent="Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.225 Safari/537.36 CrKey/1.56.500000",
        description="Google Chromecast streaming device"
    ),

    "roku": DHCPProfile(
        name="Roku Streaming Stick",
        hostname_pattern="Roku-{random}",
        vendor_class=None,
        request_options=[1, 3, 6, 15, 12, 42],
        user_agent="Roku/DVP-11.5 (11.5.0.4312)",
        description="Roku streaming device"
    ),
}


def get_profile(personality: str) -> Optional[DHCPProfile]:
    """Get a DHCP profile by personality name."""
    return DHCP_PROFILES.get(personality.lower())


def get_random_profile() -> DHCPProfile:
    """Get a random DHCP profile."""
    return random.choice(list(DHCP_PROFILES.values()))


def list_profiles() -> List[str]:
    """List all available profile names."""
    return list(DHCP_PROFILES.keys())
