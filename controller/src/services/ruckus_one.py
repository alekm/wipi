"""
Ruckus One API Integration Service
"""
import logging
import time
from typing import Optional, Dict, Any, List
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RuckusOneClient:
    """Client for Ruckus One API integration"""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        base_url: str = "https://api.ruckus.cloud",
        api_timeout: int = 10
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.api_timeout = api_timeout

        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def _get_token(self) -> str:
        """Get OAuth2 bearer token, using cached token if still valid"""
        # Return cached token if still valid (with 60s buffer)
        if self._token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at - timedelta(seconds=60):
                return self._token

        # Request new token
        auth_url = f"{self.base_url}/oauth2/token/{self.tenant_id}"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": self.base_url
        }

        try:
            response = requests.post(auth_url, data=data, timeout=self.api_timeout)
            response.raise_for_status()

            token_data = response.json()
            self._token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
            self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            logger.info("Successfully authenticated with Ruckus One API")
            return self._token

        except Exception as e:
            logger.error(f"Failed to get Ruckus One token: {e}")
            raise

    def get_clients(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get list of all connected clients from Ruckus One"""
        token = self._get_token()

        url = f"{self.base_url}/clients"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, params={"size": limit}, timeout=self.api_timeout)
            response.raise_for_status()

            clients = response.json()
            logger.debug(f"Retrieved {len(clients)} clients from Ruckus One")
            return clients

        except Exception as e:
            logger.error(f"Failed to get clients from Ruckus One: {e}")
            raise

    def get_client_by_mac(self, mac_address: str) -> Optional[Dict[str, Any]]:
        """Get a specific client by MAC address"""
        # Normalize MAC address (remove colons, lowercase)
        mac_normalized = mac_address.replace(":", "").lower()

        clients = self.get_clients()

        for client in clients:
            client_mac = client.get("mac", "").replace(":", "").lower()
            if client_mac == mac_normalized:
                return client

        return None


class RuckusOneMonitor:
    """
    Service that correlates WiPi interface data with Ruckus One client detection.
    """

    def __init__(self, r1_client: RuckusOneClient):
        self.r1_client = r1_client
        self._last_update: Optional[datetime] = None
        self._cache: Dict[str, Any] = {}

    def get_correlated_status(self, pi_interfaces: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Correlate WiPi interface data with Ruckus One client detection.

        Args:
            pi_interfaces: List of interface dicts from Pi status API

        Returns:
            Dict with correlation data including detection success/failure
        """
        try:
            # Get all clients from Ruckus One
            r1_clients = self.r1_client.get_clients()

            # Build MAC -> client mapping
            r1_by_mac = {}
            for client in r1_clients:
                mac = client.get("mac", "").lower().replace(":", "")
                r1_by_mac[mac] = client

            # Correlate with WiPi interfaces
            correlations = []
            detection_stats = {
                "total": 0,
                "detected_correctly": 0,
                "detected_incorrectly": 0,
                "not_detected": 0,
                "by_personality": {}
            }

            for iface in pi_interfaces:
                mac = iface.get("mac_address", "").lower().replace(":", "")
                if not mac:
                    continue

                detection_stats["total"] += 1

                # Get expected personality from WiPi config
                expected_personality = iface.get("dhcp_personality", "unknown")

                # Track stats by personality
                if expected_personality not in detection_stats["by_personality"]:
                    detection_stats["by_personality"][expected_personality] = {
                        "total": 0,
                        "detected_correctly": 0,
                        "detected_incorrectly": 0,
                        "not_detected": 0,
                        "detected_as": {}
                    }

                personality_stats = detection_stats["by_personality"][expected_personality]
                personality_stats["total"] += 1

                # Find matching R1 client
                r1_client = r1_by_mac.get(mac)

                if r1_client:
                    detected_os = r1_client.get("osType") or "Unknown"

                    # Track what this personality was detected as
                    if detected_os not in personality_stats["detected_as"]:
                        personality_stats["detected_as"][detected_os] = 0
                    personality_stats["detected_as"][detected_os] += 1

                    # Check if detection matches expected personality
                    detection_correct = self._check_detection_match(
                        expected_personality, detected_os
                    )

                    if detection_correct:
                        detection_stats["detected_correctly"] += 1
                        personality_stats["detected_correctly"] += 1
                    else:
                        detection_stats["detected_incorrectly"] += 1
                        personality_stats["detected_incorrectly"] += 1

                    correlations.append({
                        "pi_id": iface.get("pi_id"),
                        "interface": iface.get("name"),
                        "mac_address": iface.get("mac_address"),
                        "ip_address": iface.get("ip_address"),
                        "expected_personality": expected_personality,
                        "r1_detected_os": detected_os,
                        "r1_hostname": r1_client.get("hostname"),
                        "r1_username": r1_client.get("username"),
                        "ssid": r1_client.get("ssid"),
                        "connected_since": r1_client.get("connectedSince"),
                        "detection_correct": detection_correct,
                        "traffic": iface.get("traffic"),
                        "state": iface.get("state")
                    })
                else:
                    detection_stats["not_detected"] += 1
                    personality_stats["not_detected"] += 1
                    correlations.append({
                        "pi_id": iface.get("pi_id"),
                        "interface": iface.get("name"),
                        "mac_address": iface.get("mac_address"),
                        "ip_address": iface.get("ip_address"),
                        "expected_personality": expected_personality,
                        "r1_detected_os": None,
                        "r1_hostname": None,
                        "r1_username": None,
                        "detection_correct": False,
                        "traffic": iface.get("traffic"),
                        "state": iface.get("state")
                    })

            self._last_update = datetime.utcnow()

            return {
                "timestamp": self._last_update.isoformat(),
                "correlations": correlations,
                "detection_stats": detection_stats
            }

        except Exception as e:
            logger.error(f"Error correlating R1 status: {e}")
            raise

    def _check_detection_match(self, personality: str, detected_os: str) -> bool:
        """Check if detected OS matches expected personality.

        Acceptable detections are matched as case-insensitive substrings of the
        osType string Ruckus One reports. Confirmed real R1 osType values are
        noted inline; the rest are plausible variants R1 may emit.
        """
        if not personality or not detected_os:
            return False

        personality = personality.lower()
        detected_os = detected_os.lower()

        # Every personality the simulator/profiles can assign must appear here,
        # otherwise it can never be counted as correctly detected.
        matches = {
            "iphone": ["ios", "iphone"],                 # confirmed R1: "iOS"
            "ipad": ["ios", "ipados", "ipad"],           # R1 may report "iPadOS"
            "android": ["android"],                      # confirmed R1: "Android"
            "samsung": ["android", "samsung"],           # Samsung -> Android
            "pixel": ["android", "pixel"],               # Pixel -> Android
            "macos": ["macos", "mac os", "os x", "osx"],
            "macbook": ["macos", "mac os", "os x", "osx"],
            "windows10": ["windows"],
            "windows11": ["windows"],
            "xbox": ["xbox", "windows"],
            "playstation": ["playstation", "sony"],
            "linux": ["linux"],
            "chromecast": ["chromecast", "android", "google"],
            "roku": ["roku"],
            "echo": ["amazon", "echo", "fire"],
            "echo-dot": ["amazon", "echo", "fire"],
            "smart-tv-samsung": ["tizen", "samsung", "smart"],
            "smart-tv-lg": ["webos", "lg", "smart"],
        }

        acceptable = matches.get(personality, [])
        return any(accept in detected_os for accept in acceptable)
