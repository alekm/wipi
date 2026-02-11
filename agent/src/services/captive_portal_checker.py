"""
Captive Portal Checker - Makes periodic HTTP requests to ensure User-Agent visibility.

Real devices constantly check for captive portals. This service mimics that behavior
to ensure the AP sees HTTP traffic (and User-Agent headers) from every client,
regardless of their main traffic type.
"""
import asyncio
import logging
from typing import Optional
import aiohttp
from ..traffic.interface_binding import SourceIPBoundConnector, get_interface_ip

logger = logging.getLogger(__name__)


class CaptivePortalChecker:
    """
    Background service that makes periodic HTTP captive portal checks for all interfaces.
    Ensures AP sees User-Agent from every client for better device fingerprinting.
    """

    # Captive portal URLs used by real devices
    CAPTIVE_PORTAL_URLS = {
        "iphone": "http://captive.apple.com/hotspot-detect.html",
        "ipad": "http://captive.apple.com/hotspot-detect.html",
        "macos": "http://captive.apple.com/hotspot-detect.html",
        "android": "http://connectivitycheck.gstatic.com/generate_204",
        "samsung": "http://connectivitycheck.gstatic.com/generate_204",
        "pixel": "http://connectivitycheck.gstatic.com/generate_204",
        "windows10": "http://www.msftconnecttest.com/connecttest.txt",
        "windows11": "http://www.msftconnecttest.com/connecttest.txt",
    }

    DEFAULT_URL = "http://captive.apple.com/hotspot-detect.html"

    def __init__(
        self,
        interface_manager,
        dhcp_manager,
        check_interval: int = 45,
        timeout: int = 5
    ):
        """
        Initialize captive portal checker.

        Args:
            interface_manager: InterfaceManager instance to get active interfaces
            dhcp_manager: DHCPManager instance (for getting interface IPs)
            check_interval: Seconds between checks (default: 45)
            timeout: HTTP request timeout in seconds (default: 5)
        """
        self.interface_manager = interface_manager
        self.dhcp_manager = dhcp_manager
        self.check_interval = check_interval
        self.timeout = timeout
        self.running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(f"CaptivePortalChecker initialized: interval={check_interval}s")

    async def start(self) -> None:
        """Start the background checking loop."""
        if self.running:
            logger.warning("Captive portal checker already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("Captive portal checker started")

    async def stop(self) -> None:
        """Stop the background checking loop."""
        if not self.running:
            return

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Captive portal checker stopped")

    async def _check_loop(self) -> None:
        """Main background loop - periodically check captive portal for all interfaces."""
        logger.info("Captive portal check loop started")

        while self.running:
            try:
                await self._check_all_interfaces()
            except asyncio.CancelledError:
                logger.info("Captive portal check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in captive portal check loop: {e}")

            # Sleep until next check
            await asyncio.sleep(self.check_interval)

        logger.info("Captive portal check loop exiting")

    async def _check_all_interfaces(self) -> None:
        """Check captive portal for all active interfaces."""
        try:
            # Get all tracked interfaces
            tracked_interfaces = list(self.interface_manager.interfaces.keys())

            if not tracked_interfaces:
                logger.debug("No interfaces to check")
                return

            # Check each interface in parallel
            tasks = []
            for iface_name in tracked_interfaces:
                task = asyncio.create_task(self._check_interface(iface_name))
                tasks.append(task)

            # Wait for all checks to complete
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error checking interfaces: {e}")

    async def _check_interface(self, interface_name: str) -> None:
        """
        Make a captive portal check for a single interface.

        Args:
            interface_name: Name of the interface to check
        """
        try:
            # Get interface IP (need it to bind to the interface)
            ip_address = await self.dhcp_manager.get_ip_address(interface_name)
            if not ip_address:
                logger.debug(f"No IP for {interface_name}, skipping captive portal check")
                return

            # Get the stored configuration to find User-Agent
            user_agent = None
            personality = None

            # Import here to avoid circular import
            from ..api import configure

            for iface_config in configure.stored_configuration.interfaces:
                if iface_config.name == interface_name:
                    personality = iface_config.dhcp_personality
                    # Get user_agent from traffic config if available
                    if iface_config.traffic and iface_config.traffic.config:
                        user_agent = iface_config.traffic.config.get("user_agent")
                    break

            if not user_agent:
                # Fallback to default if not in config
                user_agent = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

            # Get appropriate captive portal URL for this personality
            url = self.CAPTIVE_PORTAL_URLS.get(personality, self.DEFAULT_URL)

            # Create connector bound to this interface's IP
            connector = SourceIPBoundConnector(source_ip=ip_address)

            # Make HTTP request
            async with aiohttp.ClientSession(connector=connector) as session:
                headers = {"User-Agent": user_agent}
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=False  # Captive portal checks don't follow redirects
                ) as response:
                    # We don't care about the response, just that we made the request
                    logger.debug(
                        f"Captive portal check for {interface_name}: "
                        f"{response.status} (personality={personality})"
                    )

        except asyncio.TimeoutError:
            logger.debug(f"Captive portal check timeout for {interface_name}")
        except Exception as e:
            logger.debug(f"Captive portal check error for {interface_name}: {e}")
