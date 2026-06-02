"""
Streaming Audio traffic generator - simulates music streaming (Spotify, Apple Music).
"""
import asyncio
import logging
import random
from typing import Dict, Any
import aiohttp
from .base import TrafficGenerator
from .interface_binding import SourceIPBoundConnector

logger = logging.getLogger(__name__)


class StreamingAudioTrafficGenerator(TrafficGenerator):
    """Simulates continuous audio streaming traffic"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False, app_config=None):
        super().__init__(interface, config, mock_mode)

        # Parse config
        self.quality: str = config.get("quality", "high")  # low, normal, high, very_high
        self.session_duration_min: int = config.get("session_duration_min", 1800)  # 30 min default
        self.session_duration_max: int = config.get("session_duration_max", 7200)  # 2 hours default
        self.pause_between_min: int = config.get("pause_between_min", 30)
        self.pause_between_max: int = config.get("pause_between_max", 300)

        # User-Agent for HTTP fingerprinting - must match DHCP personality
        self.user_agent: str = config.get(
            "user_agent",
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        )

        # Get timeout from app_config
        if app_config:
            self.timeout = app_config.bulk_transfer_timeout
        else:
            self.timeout = 60

        # Bandwidth based on quality (Spotify-like)
        self.bitrate_map = {
            "low": 96,      # 96 kbps
            "normal": 160,  # 160 kbps
            "high": 320,    # 320 kbps (premium)
            "very_high": 320  # 320 kbps
        }
        self.bitrate_kbps = self.bitrate_map.get(self.quality, 160)

        # Use public audio stream URL (SomaFM - internet radio)
        # These are real streaming audio sources for testing
        self.stream_urls = [
            "http://ice1.somafm.com/groovesalad-128-mp3",  # Groove Salad (128kbps)
            "http://ice1.somafm.com/dronezone-128-mp3",    # Drone Zone (128kbps)
            "http://ice1.somafm.com/defcon-128-mp3",       # DEF CON Radio (128kbps)
        ]

        # Stats
        self.stats = {
            "sessions_started": 0,
            "sessions_completed": 0,
            "total_streaming_time": 0,
            "bytes_downloaded": 0,
            "average_bitrate_kbps": 0.0,
            "quality": self.quality
        }
        self._bitrate_samples = []

    def get_type(self) -> str:
        return "streaming_audio"

    async def _generate_traffic(self) -> None:
        """Generate streaming audio traffic"""
        logger.info(f"Starting streaming audio traffic for {self.interface} (quality={self.quality})")

        # Create aiohttp session with source IP binding
        connector = await SourceIPBoundConnector.create_for_interface(self.interface)

        async with aiohttp.ClientSession(connector=connector) as session:
            while self.active:
                try:
                    # Start a streaming session
                    await self._stream_session(session)

                    # Pause between sessions (song/playlist change)
                    pause_duration = random.randint(self.pause_between_min, self.pause_between_max)
                    logger.debug(f"Pausing streaming for {pause_duration}s on {self.interface}")
                    await asyncio.sleep(pause_duration)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in audio streaming loop for {self.interface}: {e}")
                    await asyncio.sleep(10)

    async def _stream_session(self, session: aiohttp.ClientSession) -> None:
        """
        Stream audio for one session (like listening to a playlist).

        Args:
            session: aiohttp session
        """
        self.stats["sessions_started"] += 1

        # Random session duration
        session_duration = random.randint(self.session_duration_min, self.session_duration_max)
        start_time = asyncio.get_event_loop().time()

        logger.info(
            f"Starting audio stream session on {self.interface} "
            f"({session_duration}s, {self.bitrate_kbps}kbps)"
        )

        try:
            if self.mock_mode:
                # Simulate streaming
                await asyncio.sleep(session_duration)

                # Simulate data transfer
                bytes_per_second = (self.bitrate_kbps * 1024) / 8
                total_bytes = int(bytes_per_second * session_duration)

                self.stats["sessions_completed"] += 1
                self.stats["total_streaming_time"] += session_duration
                self.stats["bytes_downloaded"] += total_bytes
                self._update_bitrate(self.bitrate_kbps)

                logger.info(f"[MOCK] Completed audio stream ({total_bytes} bytes)")
                return

            # Select random stream URL
            stream_url = random.choice(self.stream_urls)

            # Stream audio data (User-Agent for AP fingerprinting)
            timeout = aiohttp.ClientTimeout(total=None, sock_read=self.timeout)
            headers = {"User-Agent": self.user_agent}
            async with session.get(stream_url, headers=headers, timeout=timeout) as response:
                bytes_downloaded = 0
                chunk_count = 0

                # Stream for the session duration
                end_time = asyncio.get_event_loop().time() + session_duration

                async for chunk in response.content.iter_chunked(4096):
                    if not self.active:
                        break

                    if asyncio.get_event_loop().time() >= end_time:
                        break

                    bytes_downloaded += len(chunk)
                    chunk_count += 1

                    # Log progress every 100 chunks (~400KB)
                    if chunk_count % 100 == 0:
                        logger.debug(
                            f"Streaming audio on {self.interface}: "
                            f"{bytes_downloaded / 1024 / 1024:.2f} MB"
                        )

                # Update stats
                actual_duration = asyncio.get_event_loop().time() - start_time
                actual_bitrate = (bytes_downloaded * 8) / (actual_duration * 1024) if actual_duration > 0 else 0

                self.stats["sessions_completed"] += 1
                self.stats["total_streaming_time"] += int(actual_duration)
                self.stats["bytes_downloaded"] += bytes_downloaded
                self._update_bitrate(actual_bitrate)

                logger.info(
                    f"Completed audio stream on {self.interface}: "
                    f"{bytes_downloaded / 1024 / 1024:.2f} MB in {actual_duration:.0f}s "
                    f"({actual_bitrate:.0f} kbps)"
                )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout during audio streaming on {self.interface}")
        except aiohttp.ClientError as e:
            logger.warning(f"Client error during audio streaming on {self.interface}: {e}")
        except Exception as e:
            logger.error(f"Error during audio streaming on {self.interface}: {e}")

    def _update_bitrate(self, bitrate_kbps: float) -> None:
        """Update average bitrate"""
        self._bitrate_samples.append(bitrate_kbps)

        # Keep only last 20 samples
        if len(self._bitrate_samples) > 20:
            self._bitrate_samples = self._bitrate_samples[-20:]

        self.stats["average_bitrate_kbps"] = sum(self._bitrate_samples) / len(self._bitrate_samples)

    def get_stats(self) -> Dict[str, Any]:
        """Get current traffic statistics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "target_bitrate_kbps": self.bitrate_kbps
        }
