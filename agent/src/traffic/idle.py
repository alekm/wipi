"""
Idle traffic generator - minimal keepalive traffic.
"""
import asyncio
import logging
from typing import Dict, Any
from .base import TrafficGenerator

logger = logging.getLogger(__name__)


class IdleTrafficGenerator(TrafficGenerator):
    """Generates minimal keepalive traffic"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False):
        super().__init__(interface, config, mock_mode)

        self.keepalive_interval: int = config.get("keepalive_interval", 60)

        self.stats = {
            "pings_sent": 0,
            "pings_successful": 0,
            "pings_failed": 0
        }

    def get_type(self) -> str:
        return "idle"

    async def _generate_traffic(self) -> None:
        """Generate minimal keepalive traffic"""
        logger.info(f"Starting idle keepalive traffic for {self.interface}")

        while self.active:
            try:
                await self._send_ping()
                await asyncio.sleep(self.keepalive_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in idle traffic loop for {self.interface}: {e}")
                await asyncio.sleep(5)

    async def _send_ping(self) -> None:
        """Send a ping to gateway or DNS server"""
        self.stats["pings_sent"] += 1

        try:
            if self.mock_mode:
                await asyncio.sleep(0.1)
                self.stats["pings_successful"] += 1
                logger.debug(f"[MOCK] Sent keepalive ping on {self.interface}")
                return

            # Ping default gateway (8.8.8.8 as fallback)
            proc = await asyncio.create_subprocess_exec(
                "ping", "-I", self.interface, "-c", "1", "-W", "2", "8.8.8.8",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                self.stats["pings_successful"] += 1
                logger.debug(f"Keepalive ping successful on {self.interface}")
            else:
                self.stats["pings_failed"] += 1
                logger.debug(f"Keepalive ping failed on {self.interface}")

        except Exception as e:
            logger.warning(f"Error sending ping on {self.interface}: {e}")
            self.stats["pings_failed"] += 1
