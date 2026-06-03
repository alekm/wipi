"""
Video streaming traffic generator - simulates sustained video bandwidth.
"""
import asyncio
import logging
import random
from typing import Dict, Any, Optional
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class VideoStreamTrafficGenerator(TrafficGenerator):
    """Simulates video streaming traffic with sustained bandwidth"""

    # Public HTTP sinks for synthetic traffic — no auth, no rate limits
    SYNTHETIC_URLS = [
        "http://ipv4.download.thinkbroadband.com/5MB.zip",
        "http://speedtest.tele2.net/1MB.zip",
        "http://ipv4.download.thinkbroadband.com/1MB.zip",
    ]

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False):
        super().__init__(interface, config, mock_mode)

        # Parse config
        self.bandwidth: str = config.get("bandwidth", "5mbps")
        self.duration: Optional[int] = config.get("duration", None)  # None = continuous
        self.url: Optional[str] = config.get("url", None)  # None = synthetic traffic

        # Parse bandwidth to bytes per second
        self.bytes_per_second = self._parse_bandwidth(self.bandwidth)

        # Stats
        self.stats = {
            "bytes_streamed": 0,
            "seconds_streamed": 0,
            "stalls": 0,
            "average_bitrate": 0.0
        }

    def get_type(self) -> str:
        return "video_stream"

    def _parse_bandwidth(self, bandwidth_str: str) -> int:
        """Parse bandwidth string (e.g., '5mbps') to bytes per second"""
        bandwidth_str = bandwidth_str.lower().strip()

        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*(mbps|kbps|gbps)?', bandwidth_str)
        if not match:
            logger.warning(f"Invalid bandwidth format: {bandwidth_str}, defaulting to 5mbps")
            return 5 * 1024 * 1024 // 8

        value = float(match.group(1))
        unit = match.group(2) or 'mbps'

        if unit == 'mbps':
            return int(value * 1024 * 1024 // 8)
        elif unit == 'kbps':
            return int(value * 1024 // 8)
        elif unit == 'gbps':
            return int(value * 1024 * 1024 * 1024 // 8)

        return int(value)

    async def _generate_traffic(self) -> None:
        """Generate video streaming traffic"""
        logger.info(
            f"Starting video streaming traffic for {self.interface} "
            f"at {self.bandwidth} ({self.bytes_per_second} bytes/sec)"
        )

        if self.url:
            await self._stream_from_url()
        else:
            await self._stream_synthetic()

    async def _stream_from_url(self) -> None:
        """Stream from actual URL"""
        connector = await SourceIPBoundConnector.create_for_interface(self.interface)

        async with aiohttp.ClientSession(connector=connector) as session:
            start_time = asyncio.get_event_loop().time()

            try:
                async with session.get(self.url) as response:
                    async for chunk in response.content.iter_chunked(8192):
                        if not self.active:
                            break

                        self.stats["bytes_streamed"] += len(chunk)
                        elapsed = asyncio.get_event_loop().time() - start_time
                        self.stats["seconds_streamed"] = int(elapsed)

                        if elapsed > 0:
                            self.stats["average_bitrate"] = (
                                self.stats["bytes_streamed"] * 8 / elapsed / 1024 / 1024
                            )

                        if self.duration and elapsed >= self.duration:
                            break

            except Exception as e:
                logger.error(f"Error streaming from {self.url}: {e}")
                self.stats["stalls"] += 1

    async def _stream_synthetic(self) -> None:
        """Generate synthetic streaming traffic by downloading from public sinks"""
        logger.info(f"Generating synthetic stream at {self.bandwidth} on {self.interface}")

        while self.active:
            try:
                url = random.choice(self.SYNTHETIC_URLS)
                await self._stream_from_sink(url)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in synthetic stream loop for {self.interface}: {e}")
                self.stats["stalls"] += 1
                await asyncio.sleep(5)

    async def _stream_from_sink(self, url: str) -> None:
        """Download from a public sink URL with rate limiting to match target bandwidth"""
        start_time = asyncio.get_event_loop().time()
        bytes_downloaded = 0

        connector = await SourceIPBoundConnector.create_for_interface(self.interface)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    async for chunk in response.content.iter_chunked(8192):
                        if not self.active:
                            break

                        bytes_downloaded += len(chunk)
                        elapsed = asyncio.get_event_loop().time() - start_time

                        # Rate-limit to target bandwidth
                        if self.bytes_per_second > 0 and elapsed > 0:
                            expected_time = bytes_downloaded / self.bytes_per_second
                            if expected_time > elapsed:
                                await asyncio.sleep(expected_time - elapsed)

                        self.stats["bytes_streamed"] += len(chunk)
                        self.stats["seconds_streamed"] = int(elapsed)

                        if elapsed > 0:
                            self.stats["average_bitrate"] = (
                                self.stats["bytes_streamed"] * 8 / elapsed / 1024 / 1024
                            )

                        if self.duration and elapsed >= self.duration:
                            break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error downloading sink {url} on {self.interface}: {e}")
            self.stats["stalls"] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "bandwidth_target": self.bandwidth,
            "duration": self.duration
        }
