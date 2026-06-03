"""
Speed Test Traffic Generator - Tests network speed using fast.com and speedtest.net
"""
import asyncio
import logging
import random
import time
from typing import Dict, Any
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class SpeedTestTrafficGenerator(TrafficGenerator):
    """
    Generates traffic by running periodic speed tests.

    Uses:
    - fast.com (Netflix CDN) - Should show as "netflix" in Ruckus One
    - speedtest.net (Ookla) - May show as "speedtest" or CDN provider

    Config:
        service: "fast" or "speedtest" or "both" (default: "both")
        interval: Seconds between tests (default: 300)
        duration: Seconds to run each test (default: 30)
    """

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False, app_config=None):
        super().__init__(interface, config, mock_mode)

        # Set timeouts from app config or use defaults
        if app_config:
            self.download_timeout = app_config.speedtest_timeout
            self.ping_timeout = app_config.speedtest_ping_timeout
        else:
            self.download_timeout = 60
            self.ping_timeout = 10

        self.service = config.get("service", "both")
        self.interval = config.get("interval", 300)  # 5 minutes between tests
        self.duration = config.get("duration", 30)  # 30 seconds per test
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (X11; Linux armv7l) WiPi/1.0"
        )

        self.stats = {
            "tests_run": 0,
            "tests_failed": 0,
            "last_speed_mbps": 0,
            "service": self.service,
            "interval": self.interval,
        }

    def get_type(self) -> str:
        return "speedtest"

    async def _generate_traffic(self) -> None:
        """Main traffic generation loop"""
        logger.info(
            f"Starting speed test traffic on {self.interface} "
            f"(service: {self.service}, interval: {self.interval}s)"
        )

        while self.active:
            try:
                # Decide which service to use
                if self.service == "both":
                    use_fast = random.choice([True, False])
                elif self.service == "fast":
                    use_fast = True
                else:
                    use_fast = False

                if use_fast:
                    await self._run_fast_speedtest()
                else:
                    await self._run_ookla_speedtest()

                self.stats["tests_run"] += 1

            except Exception as e:
                logger.error(f"Error running speed test on {self.interface}: {e}")
                self.stats["tests_failed"] += 1

            # Wait before next test
            await asyncio.sleep(self.interval)

    async def _run_fast_speedtest(self) -> None:
        """
        Run speed test using fast.com (Netflix CDN).

        This should trigger "netflix" classification in Ruckus One.
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Would run fast.com speed test on {self.interface}")
            self.stats["last_speed_mbps"] = random.uniform(50, 150)
            return

        logger.info(f"Running fast.com speed test on {self.interface}")

        try:
            # Fast.com uses Netflix CDN infrastructure
            # We'll download from fast.com to trigger Netflix detection
            start_time = time.time()
            bytes_downloaded = 0

            connector = await SourceIPBoundConnector.create_for_interface(self.interface)

            async with aiohttp.ClientSession(connector=connector) as session:
                # Download from fast.com for specified duration
                url = "https://fast.com"
                headers = {"User-Agent": self.user_agent}

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=self.download_timeout)) as response:
                    logger.debug(f"fast.com response status: {response.status}")

                    # Read initial content
                    initial_data = await response.read()
                    bytes_downloaded += len(initial_data)

                # Now try to fetch speed test assets
                # Fast.com uses api.fast.com to get test URLs
                try:
                    async with session.get(
                        "https://api.fast.com/netflix/speedtest/v2?https=true&token=YXNkZmFzZGxmbnNkYWZoYXNkZmhrYWxm&urlCount=5",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.ping_timeout)
                    ) as api_response:
                        if api_response.status == 200:
                            data = await api_response.json()
                            # Download from Netflix CDN URLs
                            if "targets" in data:
                                end_time = time.time() + self.duration
                                for target in data["targets"][:3]:  # Use first 3 URLs
                                    if time.time() >= end_time:
                                        break
                                    url = target["url"]
                                    try:
                                        async with session.get(
                                            url,
                                            headers=headers,
                                            timeout=aiohttp.ClientTimeout(total=self.duration)
                                        ) as dl_response:
                                            # Stream download
                                            async for chunk in dl_response.content.iter_chunked(8192):
                                                bytes_downloaded += len(chunk)
                                                if time.time() >= end_time:
                                                    break
                                    except Exception as e:
                                        logger.debug(f"Error downloading from {url}: {e}")
                                        continue
                except Exception as e:
                    logger.debug(f"Could not get fast.com API data: {e}")

            elapsed = time.time() - start_time
            if elapsed > 0:
                mbps = (bytes_downloaded * 8) / (elapsed * 1_000_000)
                self.stats["last_speed_mbps"] = round(mbps, 2)
                logger.info(
                    f"fast.com test complete on {self.interface}: "
                    f"{mbps:.2f} Mbps ({bytes_downloaded / 1_000_000:.2f} MB in {elapsed:.1f}s)"
                )

        except Exception as e:
            logger.error(f"Error running fast.com speed test: {e}")
            raise

    async def _run_ookla_speedtest(self) -> None:
        """
        Run speed test using speedtest.net (Ookla).

        This may trigger "speedtest" or CDN provider classification.
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Would run speedtest.net on {self.interface}")
            self.stats["last_speed_mbps"] = random.uniform(50, 150)
            return

        logger.info(f"Running speedtest.net test on {self.interface}")

        try:
            start_time = time.time()
            bytes_downloaded = 0

            connector = await SourceIPBoundConnector.create_for_interface(self.interface)

            async with aiohttp.ClientSession(connector=connector) as session:
                # Download from Speedtest.net
                # They have test files of various sizes
                test_urls = [
                    "http://speedtest.tele2.net/100MB.zip",
                    "http://speedtest.tele2.net/10MB.zip",
                ]
                headers = {"User-Agent": self.user_agent}

                end_time = time.time() + self.duration

                for url in test_urls:
                    if time.time() >= end_time:
                        break

                    try:
                        async with session.get(
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=self.duration)
                        ) as response:
                            # Stream download for duration
                            async for chunk in response.content.iter_chunked(8192):
                                bytes_downloaded += len(chunk)
                                if time.time() >= end_time:
                                    break
                    except Exception as e:
                        logger.debug(f"Error downloading from {url}: {e}")
                        continue

            elapsed = time.time() - start_time
            if elapsed > 0:
                mbps = (bytes_downloaded * 8) / (elapsed * 1_000_000)
                self.stats["last_speed_mbps"] = round(mbps, 2)
                logger.info(
                    f"speedtest.net test complete on {self.interface}: "
                    f"{mbps:.2f} Mbps ({bytes_downloaded / 1_000_000:.2f} MB in {elapsed:.1f}s)"
                )

        except Exception as e:
            logger.error(f"Error running speedtest.net: {e}")
            raise
