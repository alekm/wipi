"""
HTTP Browser traffic generator - simulates web browsing behavior.
"""
import asyncio
import logging
import random
from typing import Dict, Any, List
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class HttpBrowserTrafficGenerator(TrafficGenerator):
    """Simulates HTTP web browsing traffic"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False):
        super().__init__(interface, config, mock_mode)

        # Parse config
        self.urls: List[str] = config.get("urls", ["http://httpbin.org/html"])
        self.interval: int = config.get("interval", 30)
        self.timeout: int = config.get("timeout", 10)
        self.user_agent: str = config.get(
            "user_agent",
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        )

        # Stats
        self.stats = {
            "requests_made": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "bytes_downloaded": 0,
            "average_response_time": 0.0
        }
        self._response_times: List[float] = []

    def get_type(self) -> str:
        return "http_browser"

    async def _generate_traffic(self) -> None:
        """Generate HTTP browsing traffic"""
        logger.info(f"Starting HTTP browsing traffic for {self.interface}")

        # Create aiohttp session with source IP binding
        connector = await SourceIPBoundConnector.create_for_interface(self.interface)

        async with aiohttp.ClientSession(connector=connector) as session:
            while self.active:
                try:
                    # Select random URL
                    url = random.choice(self.urls)

                    await self._fetch_url(session, url)

                    # Random delay to simulate browsing behavior
                    # Add some variance to the interval
                    delay = self.interval + random.uniform(-5, 5)
                    delay = max(1, delay)  # Minimum 1 second

                    await asyncio.sleep(delay)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in HTTP traffic loop for {self.interface}: {e}")
                    await asyncio.sleep(5)

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> None:
        """
        Fetch a URL and update stats.

        Args:
            session: aiohttp session
            url: URL to fetch
        """
        self.stats["requests_made"] += 1
        start_time = asyncio.get_event_loop().time()

        try:
            if self.mock_mode:
                # Simulate request
                await asyncio.sleep(random.uniform(0.5, 2.0))
                response_time = asyncio.get_event_loop().time() - start_time
                bytes_downloaded = random.randint(1000, 50000)

                self.stats["requests_successful"] += 1
                self.stats["bytes_downloaded"] += bytes_downloaded
                self._update_response_time(response_time)

                logger.debug(f"[MOCK] Fetched {url} in {response_time:.2f}s ({bytes_downloaded} bytes)")
                return

            headers = {
                "User-Agent": self.user_agent
            }

            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # Read response
                content = await response.read()
                response_time = asyncio.get_event_loop().time() - start_time

                self.stats["requests_successful"] += 1
                self.stats["bytes_downloaded"] += len(content)
                self._update_response_time(response_time)

                logger.debug(
                    f"Fetched {url} [{response.status}] in {response_time:.2f}s "
                    f"({len(content)} bytes)"
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            self.stats["requests_failed"] += 1
        except aiohttp.ClientError as e:
            logger.warning(f"Client error fetching {url}: {e}")
            self.stats["requests_failed"] += 1
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.stats["requests_failed"] += 1

    def _update_response_time(self, response_time: float) -> None:
        """Update average response time"""
        self._response_times.append(response_time)

        # Keep only last 100 response times
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]

        self.stats["average_response_time"] = sum(self._response_times) / len(self._response_times)

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "urls": self.urls,
            "interval": self.interval
        }
