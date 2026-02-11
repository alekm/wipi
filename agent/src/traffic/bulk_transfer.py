"""
Bulk transfer traffic generator - large downloads/uploads at maximum throughput.
"""
import asyncio
import logging
import random
from typing import Dict, Any, Optional
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class BulkTransferTrafficGenerator(TrafficGenerator):
    """Generates bulk transfer traffic (large downloads/uploads)"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False, app_config=None):
        super().__init__(interface, config, mock_mode)

        # Set timeout from app config or use default
        if app_config:
            self.transfer_timeout = app_config.bulk_transfer_timeout
        else:
            self.transfer_timeout = 300

        # Parse config
        self.url: str = config.get("url", "http://httpbin.org/bytes/10485760")  # 10MB default
        self.direction: str = config.get("direction", "download")
        self.repeat: bool = config.get("repeat", False)
        self.max_bandwidth: Optional[str] = config.get("max_bandwidth", None)
        self.user_agent: str = config.get(
            "user_agent",
            "Mozilla/5.0 (X11; Linux armv7l) WiPi/1.0"
        )

        # Parse max bandwidth if specified
        self.max_bytes_per_second: Optional[int] = None
        if self.max_bandwidth:
            self.max_bytes_per_second = self._parse_bandwidth(self.max_bandwidth)

        # Stats
        self.stats = {
            "transfers_completed": 0,
            "transfers_failed": 0,
            "bytes_transferred": 0,
            "average_speed_mbps": 0.0
        }
        self._transfer_speeds: list = []

    def get_type(self) -> str:
        return "bulk_transfer"

    def _parse_bandwidth(self, bandwidth_str: str) -> int:
        """Parse bandwidth string to bytes per second"""
        bandwidth_str = bandwidth_str.lower().strip()
        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*(mbps|kbps|gbps)?', bandwidth_str)
        if not match:
            return 0

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
        """Generate bulk transfer traffic"""
        logger.info(
            f"Starting bulk {self.direction} traffic for {self.interface} "
            f"from/to {self.url}"
        )

        while self.active:
            try:
                if self.direction == "download":
                    await self._download()
                elif self.direction == "upload":
                    await self._upload()
                else:
                    logger.error(f"Invalid direction: {self.direction}")
                    break

                if not self.repeat:
                    logger.info(f"Single transfer completed for {self.interface}")
                    break

                # Small delay between repeated transfers
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in bulk transfer loop for {self.interface}: {e}")
                self.stats["transfers_failed"] += 1
                await asyncio.sleep(5)

    async def _download(self) -> None:
        """Perform a bulk download"""
        start_time = asyncio.get_event_loop().time()
        bytes_downloaded = 0

        try:
            if self.mock_mode:
                # Simulate download
                mock_size = 10 * 1024 * 1024  # 10 MB
                mock_duration = 5.0  # 5 seconds
                await asyncio.sleep(mock_duration)

                bytes_downloaded = mock_size
                self.stats["transfers_completed"] += 1
                self.stats["bytes_transferred"] += bytes_downloaded

                speed_mbps = (mock_size * 8) / mock_duration / 1024 / 1024
                self._update_speed(speed_mbps)

                logger.info(
                    f"[MOCK] Downloaded {mock_size / 1024 / 1024:.1f} MB "
                    f"at {speed_mbps:.2f} Mbps"
                )
                return

            connector = await SourceIPBoundConnector.create_for_interface(self.interface)
            timeout = aiohttp.ClientTimeout(total=self.transfer_timeout)  # 5 minute timeout

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                headers = {"User-Agent": self.user_agent}
                async with session.get(self.url, headers=headers) as response:
                    response.raise_for_status()

                    async for chunk in response.content.iter_chunked(65536):  # 64 KB chunks
                        if not self.active:
                            break

                        bytes_downloaded += len(chunk)

                        # Rate limiting if max_bandwidth is set
                        if self.max_bytes_per_second:
                            elapsed = asyncio.get_event_loop().time() - start_time
                            expected_time = bytes_downloaded / self.max_bytes_per_second
                            if expected_time > elapsed:
                                await asyncio.sleep(expected_time - elapsed)

            elapsed = asyncio.get_event_loop().time() - start_time
            speed_mbps = (bytes_downloaded * 8) / elapsed / 1024 / 1024

            self.stats["transfers_completed"] += 1
            self.stats["bytes_transferred"] += bytes_downloaded
            self._update_speed(speed_mbps)

            logger.info(
                f"Downloaded {bytes_downloaded / 1024 / 1024:.1f} MB in {elapsed:.1f}s "
                f"at {speed_mbps:.2f} Mbps on {self.interface}"
            )

        except aiohttp.ClientError as e:
            logger.error(f"Download error on {self.interface}: {e}")
            self.stats["transfers_failed"] += 1
        except Exception as e:
            logger.error(f"Unexpected download error on {self.interface}: {e}")
            self.stats["transfers_failed"] += 1

    async def _upload(self) -> None:
        """Perform a bulk upload"""
        start_time = asyncio.get_event_loop().time()

        # Generate data to upload (10 MB default)
        upload_size = 10 * 1024 * 1024
        bytes_uploaded = 0

        try:
            if self.mock_mode:
                # Simulate upload
                mock_duration = 5.0
                await asyncio.sleep(mock_duration)

                bytes_uploaded = upload_size
                self.stats["transfers_completed"] += 1
                self.stats["bytes_transferred"] += bytes_uploaded

                speed_mbps = (upload_size * 8) / mock_duration / 1024 / 1024
                self._update_speed(speed_mbps)

                logger.info(
                    f"[MOCK] Uploaded {upload_size / 1024 / 1024:.1f} MB "
                    f"at {speed_mbps:.2f} Mbps"
                )
                return

            # Generate random data
            # In production, you might want to generate this in chunks to save memory
            data = bytes(random.getrandbits(8) for _ in range(upload_size))

            connector = await SourceIPBoundConnector.create_for_interface(self.interface)
            timeout = aiohttp.ClientTimeout(total=self.transfer_timeout)

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(self.url, data=data) as response:
                    response.raise_for_status()
                    await response.read()

            bytes_uploaded = upload_size
            elapsed = asyncio.get_event_loop().time() - start_time
            speed_mbps = (bytes_uploaded * 8) / elapsed / 1024 / 1024

            self.stats["transfers_completed"] += 1
            self.stats["bytes_transferred"] += bytes_uploaded
            self._update_speed(speed_mbps)

            logger.info(
                f"Uploaded {bytes_uploaded / 1024 / 1024:.1f} MB in {elapsed:.1f}s "
                f"at {speed_mbps:.2f} Mbps on {self.interface}"
            )

        except aiohttp.ClientError as e:
            logger.error(f"Upload error on {self.interface}: {e}")
            self.stats["transfers_failed"] += 1
        except Exception as e:
            logger.error(f"Unexpected upload error on {self.interface}: {e}")
            self.stats["transfers_failed"] += 1

    def _update_speed(self, speed_mbps: float) -> None:
        """Update average speed statistics"""
        self._transfer_speeds.append(speed_mbps)

        # Keep only last 10 transfers
        if len(self._transfer_speeds) > 10:
            self._transfer_speeds = self._transfer_speeds[-10:]

        self.stats["average_speed_mbps"] = sum(self._transfer_speeds) / len(self._transfer_speeds)

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "url": self.url,
            "direction": self.direction,
            "repeat": self.repeat
        }
