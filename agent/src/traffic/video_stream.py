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

        # Extract number
        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*(mbps|kbps|gbps)?', bandwidth_str)
        if not match:
            logger.warning(f"Invalid bandwidth format: {bandwidth_str}, defaulting to 5mbps")
            return 5 * 1024 * 1024 // 8

        value = float(match.group(1))
        unit = match.group(2) or 'mbps'

        if unit == 'mbps':
            return int(value * 1024 * 1024 // 8)  # Convert Mbps to bytes/sec
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

                        # Update average bitrate
                        if elapsed > 0:
                            self.stats["average_bitrate"] = (
                                self.stats["bytes_streamed"] * 8 / elapsed / 1024 / 1024
                            )

                        # Check duration
                        if self.duration and elapsed >= self.duration:
                            break

            except Exception as e:
                logger.error(f"Error streaming from {self.url}: {e}")
                self.stats["stalls"] += 1

    async def _stream_synthetic(self) -> None:
        """Generate synthetic streaming traffic"""
        start_time = asyncio.get_event_loop().time()
        chunk_size = 8192  # 8 KB chunks
        chunks_per_second = self.bytes_per_second / chunk_size

        logger.info(f"Generating synthetic stream at {chunks_per_second:.1f} chunks/sec")

        chunk_count = 0

        while self.active:
            try:
                if self.mock_mode:
                    # Simulate bandwidth
                    await asyncio.sleep(1.0 / chunks_per_second)
                    self.stats["bytes_streamed"] += chunk_size
                else:
                    # Generate actual data to simulate memory/CPU load
                    # In production, you might send this to a sink endpoint
                    data = bytes(random.getrandbits(8) for _ in range(chunk_size))

                    # Rate limiting
                    await asyncio.sleep(1.0 / chunks_per_second)

                    self.stats["bytes_streamed"] += len(data)

                chunk_count += 1

                # Update stats every second
                if chunk_count % int(chunks_per_second) == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    self.stats["seconds_streamed"] = int(elapsed)

                    if elapsed > 0:
                        self.stats["average_bitrate"] = (
                            self.stats["bytes_streamed"] * 8 / elapsed / 1024 / 1024
                        )

                    logger.debug(
                        f"Streaming on {self.interface}: "
                        f"{self.stats['bytes_streamed'] / 1024 / 1024:.1f} MB, "
                        f"{self.stats['average_bitrate']:.2f} Mbps"
                    )

                # Check duration
                if self.duration:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= self.duration:
                        logger.info(f"Stream duration ({self.duration}s) reached")
                        break

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in video stream loop for {self.interface}: {e}")
                self.stats["stalls"] += 1
                await asyncio.sleep(1)

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "bandwidth_target": self.bandwidth,
            "duration": self.duration
        }
