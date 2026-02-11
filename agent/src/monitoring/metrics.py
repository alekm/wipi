"""
System metrics collection for agent monitoring.
"""
import asyncio
import logging
import platform
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects system-level metrics"""

    def __init__(self, mock_mode: bool = False):
        """
        Initialize metrics collector.

        Args:
            mock_mode: If True, return mock metrics
        """
        self.mock_mode = mock_mode
        logger.info(f"MetricsCollector initialized with mock_mode: {mock_mode}")

    async def get_system_metrics(self) -> Dict:
        """
        Get current system metrics.

        Returns:
            Dict with cpu_percent, memory_percent, temperature_celsius, uptime_seconds
        """
        try:
            if self.mock_mode:
                return {
                    "cpu_percent": 25.5,
                    "memory_percent": 40.2,
                    "temperature_celsius": 45.0,
                    "uptime_seconds": 86400.0
                }

            import psutil

            # Get CPU usage (1 second average)
            cpu_percent = psutil.cpu_percent(interval=1)

            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Get temperature (Raspberry Pi specific)
            temperature = await self._get_temperature()

            # Get uptime
            uptime_seconds = self._get_uptime()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "temperature_celsius": temperature,
                "uptime_seconds": uptime_seconds
            }

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "temperature_celsius": None,
                "uptime_seconds": 0.0
            }

    async def _get_temperature(self) -> Optional[float]:
        """Get CPU temperature (Raspberry Pi specific)"""
        try:
            # Try Raspberry Pi thermal zone
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_millidegrees = int(f.read().strip())
                return temp_millidegrees / 1000.0
        except FileNotFoundError:
            # Not a Raspberry Pi or thermal zone not available
            logger.debug("Thermal zone not found, temperature unavailable")
            return None
        except Exception as e:
            logger.warning(f"Error reading temperature: {e}")
            return None

    def _get_uptime(self) -> float:
        """Get system uptime in seconds"""
        try:
            import psutil
            boot_time = psutil.boot_time()
            import time
            uptime = time.time() - boot_time
            return uptime
        except Exception as e:
            logger.warning(f"Error getting uptime: {e}")
            return 0.0

    async def get_network_stats(self, interface: str) -> Optional[Dict]:
        """
        Get network statistics for an interface.

        Args:
            interface: Interface name

        Returns:
            Dict with tx/rx bytes and packets or None
        """
        try:
            if self.mock_mode:
                import random
                return {
                    "tx_bytes": random.randint(100000, 1000000),
                    "rx_bytes": random.randint(500000, 5000000),
                    "tx_packets": random.randint(1000, 10000),
                    "rx_packets": random.randint(5000, 50000)
                }

            import psutil
            net_stats = psutil.net_io_counters(pernic=True)

            if interface not in net_stats:
                logger.warning(f"Interface {interface} not found in network stats")
                return None

            stats = net_stats[interface]
            return {
                "tx_bytes": stats.bytes_sent,
                "rx_bytes": stats.bytes_recv,
                "tx_packets": stats.packets_sent,
                "rx_packets": stats.packets_recv
            }

        except Exception as e:
            logger.error(f"Error getting network stats for {interface}: {e}")
            return None
