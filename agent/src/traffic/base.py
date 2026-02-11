"""
Base traffic generator class.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TrafficGenerator(ABC):
    """Abstract base class for traffic generators"""

    def __init__(self, interface: str, config: Dict[str, Any], mock_mode: bool = False):
        """
        Initialize traffic generator.

        Args:
            interface: Network interface to bind to
            config: Traffic-specific configuration
            mock_mode: If True, simulate traffic without actual network activity
        """
        self.interface = interface
        self.config = config
        self.mock_mode = mock_mode
        self.active = False
        self.task: Optional[asyncio.Task] = None
        self.stats: Dict[str, Any] = {}

        logger.info(f"TrafficGenerator initialized for {interface} with config: {config}")

    @abstractmethod
    async def _generate_traffic(self) -> None:
        """
        Main traffic generation loop.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def get_type(self) -> str:
        """
        Get traffic type identifier.
        Must be implemented by subclasses.
        """
        pass

    async def start(self) -> bool:
        """
        Start traffic generation.

        Returns:
            True if started successfully, False otherwise
        """
        if self.active:
            logger.warning(f"Traffic generator already active for {self.interface}")
            return True

        try:
            logger.info(f"Starting {self.get_type()} traffic generator for {self.interface}")
            self.active = True
            self.task = asyncio.create_task(self._run_with_error_handling())
            return True

        except Exception as e:
            logger.error(f"Error starting traffic generator for {self.interface}: {e}")
            self.active = False
            return False

    async def stop(self) -> None:
        """Stop traffic generation"""
        if not self.active:
            logger.info(f"Traffic generator already stopped for {self.interface}")
            return

        try:
            logger.info(f"Stopping {self.get_type()} traffic generator for {self.interface}")
            self.active = False

            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                self.task = None

            logger.info(f"Traffic generator stopped for {self.interface}")

        except Exception as e:
            logger.error(f"Error stopping traffic generator for {self.interface}: {e}")

    async def _run_with_error_handling(self) -> None:
        """Run traffic generation with error handling"""
        try:
            await self._generate_traffic()
        except asyncio.CancelledError:
            logger.info(f"Traffic generation cancelled for {self.interface}")
            raise
        except Exception as e:
            logger.error(f"Error in traffic generation for {self.interface}: {e}")
            self.active = False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current traffic statistics.

        Returns:
            Dict with traffic-specific stats
        """
        return {
            "type": self.get_type(),
            "active": self.active,
            **self.stats
        }

    def is_active(self) -> bool:
        """Check if traffic generator is active"""
        return self.active

    async def _bind_to_interface(self, sock) -> bool:
        """
        Bind a socket to the specific interface using SO_BINDTODEVICE.

        Args:
            sock: Socket to bind

        Returns:
            True if successful, False otherwise
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Would bind socket to {self.interface}")
            return True

        try:
            import socket as socket_module
            # SO_BINDTODEVICE requires root privileges
            sock.setsockopt(
                socket_module.SOL_SOCKET,
                25,  # SO_BINDTODEVICE
                self.interface.encode()
            )
            logger.debug(f"Socket bound to interface {self.interface}")
            return True

        except Exception as e:
            logger.error(f"Failed to bind socket to {self.interface}: {e}")
            return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} interface={self.interface} active={self.active}>"
