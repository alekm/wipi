"""
Interface binding utilities for traffic generators.

Uses source IP binding to ensure traffic routes through the correct interface
via policy routing rules.
"""
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)


async def get_interface_ip(interface: str) -> str:
    """
    Get the IPv4 address of a network interface.

    Args:
        interface: Interface name (e.g., 'wlan0')

    Returns:
        IP address string, or None if not found
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", "-4", "addr", "show", interface,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            # Parse IP address from output (look for "inet 10.0.0.1/24")
            for line in stdout.decode().splitlines():
                if 'inet ' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        # Extract IP without CIDR notation
                        ip = parts[1].split('/')[0]
                        if ip:
                            return ip

        return None
    except Exception as e:
        logger.error(f"Error getting IP for {interface}: {e}")
        return None


class SourceIPBoundConnector(aiohttp.TCPConnector):
    """
    TCPConnector that binds to a specific source IP address.

    Combined with policy routing, this ensures traffic routes through
    the correct network interface.
    """

    def __init__(self, source_ip: str, *args, **kwargs):
        """
        Initialize connector with source IP binding.

        Args:
            source_ip: Source IP address to bind to
        """
        # Set local_addr to bind all connections to this source IP
        kwargs['local_addr'] = (source_ip, 0)  # 0 = any source port
        super().__init__(*args, **kwargs)
        self._source_ip = source_ip
        logger.info(f"Created source IP bound connector: {source_ip}")

    @classmethod
    async def create_for_interface(cls, interface: str, *args, **kwargs):
        """
        Create a connector bound to the IP address of a specific interface.

        Args:
            interface: Network interface name (e.g., 'wlan0')

        Returns:
            SourceIPBoundConnector instance, or regular TCPConnector if IP not found
        """
        source_ip = await get_interface_ip(interface)

        if source_ip:
            logger.info(f"Binding traffic to {interface} IP: {source_ip}")
            return cls(source_ip, *args, **kwargs)
        else:
            logger.warning(f"Could not get IP for {interface}, using default routing")
            return aiohttp.TCPConnector(*args, **kwargs)
