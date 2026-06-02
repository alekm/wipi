"""
API Polling traffic generator - simulates social media/app background activity.
"""
import asyncio
import logging
import random
from typing import Dict, Any, List
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class ApiPollingTrafficGenerator(TrafficGenerator):
    """Simulates frequent API polling traffic (social media, messaging apps)"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False):
        super().__init__(interface, config, mock_mode)

        # Parse config
        self.poll_interval_min: int = config.get("poll_interval_min", 5)   # seconds
        self.poll_interval_max: int = config.get("poll_interval_max", 30)  # seconds
        self.burst_mode: bool = config.get("burst_mode", True)  # Occasional bursts of activity
        self.timeout: int = config.get("timeout", 10)
        # User-Agent for HTTP fingerprinting - must match DHCP personality
        self.user_agent: str = config.get(
            "user_agent",
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        )

        # API endpoints that return JSON (simulating social media feeds, notifications, etc.)
        # Using public APIs that return JSON responses
        self.api_endpoints = [
            "https://api.github.com/events",                    # GitHub public events
            "https://api.github.com/users/github",              # User info
            "https://api.coindesk.com/v1/bpi/currentprice.json",  # Bitcoin price
            "https://www.reddit.com/r/programming/hot.json?limit=10",  # Reddit hot posts
            "https://hacker-news.firebaseio.com/v0/topstories.json",   # HN top stories
            "https://jsonplaceholder.typicode.com/posts",       # Fake API for testing
            "https://jsonplaceholder.typicode.com/comments",    # Fake comments API
        ]

        # Stats
        self.stats = {
            "polls_made": 0,
            "polls_successful": 0,
            "polls_failed": 0,
            "bytes_downloaded": 0,
            "average_response_time": 0.0,
            "burst_count": 0,
            "average_poll_interval": 0.0
        }
        self._response_times: List[float] = []
        self._poll_intervals: List[float] = []

    def get_type(self) -> str:
        return "api_polling"

    async def _generate_traffic(self) -> None:
        """Generate API polling traffic"""
        logger.info(f"Starting API polling traffic for {self.interface}")

        # Create aiohttp session with source IP binding
        connector = await SourceIPBoundConnector.create_for_interface(self.interface)

        async with aiohttp.ClientSession(connector=connector) as session:
            while self.active:
                try:
                    # Determine if this is a burst period (10% chance)
                    is_burst = self.burst_mode and random.random() < 0.1

                    if is_burst:
                        # Burst mode: rapid-fire requests (simulating feed refresh, notifications)
                        await self._burst_poll(session)
                    else:
                        # Normal polling
                        await self._poll_once(session)

                    # Wait before next poll
                    interval = random.randint(self.poll_interval_min, self.poll_interval_max)

                    # In burst mode, much shorter interval
                    if is_burst:
                        interval = random.randint(1, 3)
                        self.stats["burst_count"] += 1

                    self._update_poll_interval(interval)
                    await asyncio.sleep(interval)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in API polling loop for {self.interface}: {e}")
                    await asyncio.sleep(5)

    async def _poll_once(self, session: aiohttp.ClientSession) -> None:
        """
        Poll one API endpoint.

        Args:
            session: aiohttp session
        """
        # Select random endpoint
        endpoint = random.choice(self.api_endpoints)
        await self._fetch_api(session, endpoint)

    async def _burst_poll(self, session: aiohttp.ClientSession) -> None:
        """
        Burst polling - multiple rapid requests simulating feed refresh.

        Args:
            session: aiohttp session
        """
        burst_count = random.randint(3, 8)
        logger.debug(f"Starting burst poll ({burst_count} requests) on {self.interface}")

        # Fire off multiple requests with minimal delay
        for _ in range(burst_count):
            if not self.active:
                break

            endpoint = random.choice(self.api_endpoints)
            await self._fetch_api(session, endpoint)

            # Very short delay between burst requests
            await asyncio.sleep(random.uniform(0.1, 0.5))

    async def _fetch_api(self, session: aiohttp.ClientSession, url: str) -> None:
        """
        Fetch an API endpoint and update stats.

        Args:
            session: aiohttp session
            url: API URL to fetch
        """
        self.stats["polls_made"] += 1
        start_time = asyncio.get_event_loop().time()

        try:
            if self.mock_mode:
                # Simulate request
                await asyncio.sleep(random.uniform(0.1, 0.5))
                response_time = asyncio.get_event_loop().time() - start_time
                bytes_downloaded = random.randint(500, 5000)  # Small JSON responses

                self.stats["polls_successful"] += 1
                self.stats["bytes_downloaded"] += bytes_downloaded
                self._update_response_time(response_time)

                logger.debug(f"[MOCK] Polled API {url} in {response_time:.2f}s ({bytes_downloaded} bytes)")
                return

            headers = {
                "User-Agent": self.user_agent,
                "Accept": "application/json"
            }

            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # Read response
                content = await response.read()
                response_time = asyncio.get_event_loop().time() - start_time

                self.stats["polls_successful"] += 1
                self.stats["bytes_downloaded"] += len(content)
                self._update_response_time(response_time)

                logger.debug(
                    f"Polled API {url} [{response.status}] in {response_time:.3f}s "
                    f"({len(content)} bytes)"
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout polling API {url}")
            self.stats["polls_failed"] += 1
        except aiohttp.ClientError as e:
            logger.debug(f"Client error polling API {url}: {e}")
            self.stats["polls_failed"] += 1
        except Exception as e:
            logger.warning(f"Error polling API {url}: {e}")
            self.stats["polls_failed"] += 1

    def _update_response_time(self, response_time: float) -> None:
        """Update average response time"""
        self._response_times.append(response_time)

        # Keep only last 100 response times
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]

        self.stats["average_response_time"] = sum(self._response_times) / len(self._response_times)

    def _update_poll_interval(self, interval: float) -> None:
        """Update average poll interval"""
        self._poll_intervals.append(interval)

        # Keep only last 50 intervals
        if len(self._poll_intervals) > 50:
            self._poll_intervals = self._poll_intervals[-50:]

        self.stats["average_poll_interval"] = sum(self._poll_intervals) / len(self._poll_intervals)

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "poll_interval_range": f"{self.poll_interval_min}-{self.poll_interval_max}s",
            "burst_mode": self.burst_mode
        }
