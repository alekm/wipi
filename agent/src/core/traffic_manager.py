"""
Traffic Manager - Coordinates traffic generators for interfaces.
"""
import asyncio
import logging
from typing import Dict, Optional, Any
from ..traffic.base import TrafficGenerator
from ..traffic.http_browser import HttpBrowserTrafficGenerator
from ..traffic.video_stream import VideoStreamTrafficGenerator
from ..traffic.bulk_transfer import BulkTransferTrafficGenerator
from ..traffic.idle import IdleTrafficGenerator
from ..traffic.speedtest import SpeedTestTrafficGenerator
from ..traffic.youtube import YouTubeTrafficGenerator
from ..traffic.streaming_audio import StreamingAudioTrafficGenerator
from ..traffic.api_polling import ApiPollingTrafficGenerator

logger = logging.getLogger(__name__)


class TrafficManager:
    """Manages traffic generators for all interfaces"""

    def __init__(self, mock_mode: bool = False, config=None):
        """
        Initialize traffic manager.

        Args:
            mock_mode: If True, traffic generators run in mock mode
            config: Configuration object with timeout settings
        """
        self.mock_mode = mock_mode
        self.config = config
        self.generators: Dict[str, TrafficGenerator] = {}

        logger.info(f"TrafficManager initialized with mock_mode: {mock_mode}")

    async def start_traffic(
        self,
        interface: str,
        traffic_type: str,
        config: Dict[str, Any]
    ) -> bool:
        """
        Start traffic generation for an interface.

        Args:
            interface: Interface name
            traffic_type: Type of traffic (http_browser, video_stream, bulk_transfer, idle)
            config: Traffic-specific configuration

        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Stop existing traffic if any
            if interface in self.generators:
                logger.info(f"Stopping existing traffic for {interface}")
                await self.stop_traffic(interface)

            # Create traffic generator based on type
            generator = self._create_generator(interface, traffic_type, config)
            if not generator:
                logger.error(f"Failed to create traffic generator for {interface}")
                return False

            # Start the generator
            if not await generator.start():
                logger.error(f"Failed to start traffic generator for {interface}")
                return False

            self.generators[interface] = generator
            logger.info(f"Started {traffic_type} traffic for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error starting traffic for {interface}: {e}")
            return False

    async def stop_traffic(self, interface: str) -> bool:
        """
        Stop traffic generation for an interface.

        Args:
            interface: Interface name

        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            if interface not in self.generators:
                logger.warning(f"No traffic generator found for {interface}")
                return True

            generator = self.generators[interface]
            await generator.stop()

            del self.generators[interface]
            logger.info(f"Stopped traffic for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error stopping traffic for {interface}: {e}")
            return False

    async def stop_all_traffic(self) -> None:
        """Stop all traffic generators"""
        logger.info(f"Stopping all {len(self.generators)} traffic generators")
        for interface in list(self.generators.keys()):
            await self.stop_traffic(interface)

    def get_traffic_status(self, interface: str) -> Optional[Dict[str, Any]]:
        """
        Get traffic status for an interface.

        Args:
            interface: Interface name

        Returns:
            Dict with traffic status or None
        """
        if interface not in self.generators:
            return None

        generator = self.generators[interface]
        return generator.get_stats()

    def get_all_traffic_status(self) -> Dict[str, Dict[str, Any]]:
        """Get traffic status for all interfaces"""
        status = {}
        for interface, generator in self.generators.items():
            status[interface] = generator.get_stats()
        return status

    def is_traffic_active(self, interface: str) -> bool:
        """
        Check if traffic is active for an interface.

        Args:
            interface: Interface name

        Returns:
            True if traffic is active, False otherwise
        """
        if interface not in self.generators:
            return False

        return self.generators[interface].is_active()

    def _create_generator(
        self,
        interface: str,
        traffic_type: str,
        config: Dict[str, Any]
    ) -> Optional[TrafficGenerator]:
        """
        Create a traffic generator based on type.

        Args:
            interface: Interface name
            traffic_type: Type of traffic
            config: Traffic configuration

        Returns:
            TrafficGenerator instance or None
        """
        try:
            # Pass app_config to generators that need timeout configuration
            if traffic_type == "http_browser":
                return HttpBrowserTrafficGenerator(interface, config, self.mock_mode)
            elif traffic_type == "video_stream":
                return VideoStreamTrafficGenerator(interface, config, self.mock_mode)
            elif traffic_type == "bulk_transfer":
                return BulkTransferTrafficGenerator(interface, config, self.mock_mode, app_config=self.config)
            elif traffic_type == "idle":
                return IdleTrafficGenerator(interface, config, self.mock_mode)
            elif traffic_type == "speedtest":
                return SpeedTestTrafficGenerator(interface, config, self.mock_mode, app_config=self.config)
            elif traffic_type == "youtube":
                return YouTubeTrafficGenerator(interface, config, self.mock_mode, app_config=self.config)
            elif traffic_type == "streaming_audio":
                return StreamingAudioTrafficGenerator(interface, config, self.mock_mode, app_config=self.config)
            elif traffic_type == "api_polling":
                return ApiPollingTrafficGenerator(interface, config, self.mock_mode)
            else:
                logger.error(f"Unknown traffic type: {traffic_type}")
                return None

        except Exception as e:
            logger.error(f"Error creating traffic generator: {e}")
            return None

    async def restart_traffic(self, interface: str) -> bool:
        """
        Restart traffic for an interface (stops and starts with same config).

        Args:
            interface: Interface name

        Returns:
            True if restarted successfully, False otherwise
        """
        if interface not in self.generators:
            logger.warning(f"No traffic generator to restart for {interface}")
            return False

        # Get current config
        generator = self.generators[interface]
        traffic_type = generator.get_type()
        config = generator.config

        # Stop and restart
        await self.stop_traffic(interface)
        return await self.start_traffic(interface, traffic_type, config)
