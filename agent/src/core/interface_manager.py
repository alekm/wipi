"""
Interface Manager - Creates and manages virtual Wi-Fi interfaces using iw command.
"""
import asyncio
import logging
import random
import re
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Strict regex for interface names to prevent command injection via iw/ip arguments
# Allows: wlan0, wlan0_1, wlx8c882b200231, etc.
INTERFACE_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_interface_name(name: str) -> None:
    """
    Validate interface name to prevent command injection.

    Args:
        name: Interface name to validate

    Raises:
        ValueError: If name contains invalid characters
    """
    if not name or not INTERFACE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid interface name '{name}': must match ^[a-zA-Z0-9_]+$"
        )


class InterfaceManager:
    """Manages virtual Wi-Fi interfaces using iw command"""

    def __init__(self, base_interface: str = "wlan0", mock_mode: bool = False, config=None):
        """
        Initialize interface manager.

        Args:
            base_interface: Base physical interface (e.g., 'wlan0')
            mock_mode: If True, simulate commands without executing them
            config: Application config object (for enable_vif flag)
        """
        _validate_interface_name(base_interface)
        self.base_interface = base_interface
        self.mock_mode = mock_mode
        self.config = config
        self.interfaces: Dict[str, Dict] = {}  # name -> {mac, state}
        self._vif_max_count_cache: Dict[str, int] = {}  # Cache max interface count per interface

        logger.info(f"InterfaceManager initialized with base interface: {base_interface}, mock_mode: {mock_mode}")

    async def get_max_interfaces(self, interface: str) -> int:
        """
        Get the maximum number of managed interfaces supported by a wireless adapter.

        VIF (Virtual Interface) support can be enabled via ENABLE_VIF environment variable.
        Disabled by default due to routing failures on Pi 4B hardware.

        Args:
            interface: Wireless interface name (e.g., "wlan0")

        Returns:
            int: Maximum interfaces (1 if VIF disabled, hardware limit if enabled)
        """
        _validate_interface_name(interface)
        # Check if VIF support is enabled via config
        enable_vif = False
        if self.config:
            enable_vif = getattr(self.config, 'enable_vif', False)

        if not enable_vif:
            # VIF disabled - use only base interfaces
            self._vif_max_count_cache[interface] = 1
            return 1

        # VIF enabled - detect hardware limit

        # Check cache first
        if interface in self._vif_max_count_cache:
            return self._vif_max_count_cache[interface]

        if self.mock_mode:
            logger.info(f"[MOCK] Would check VIF support for {interface}")
            self._vif_max_count_cache[interface] = 8
            return 8

        try:
            # Get the phy number for this interface
            proc = await asyncio.create_subprocess_exec(
                "/usr/sbin/iw", "dev", interface, "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning(f"Could not get phy info for {interface}")
                self._vif_max_count_cache[interface] = 1
                return 1

            # Parse wiphy number from iw dev output
            phy_num = None
            for line in stdout.decode().splitlines():
                if 'wiphy' in line.lower():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        phy_num = parts[1]
                        break

            if not phy_num:
                logger.warning(f"No phy number found for {interface}")
                self._vif_max_count_cache[interface] = 1
                return 1

            # Check interface combinations to see if multiple managed interfaces are supported
            proc = await asyncio.create_subprocess_exec(
                "/usr/sbin/iw", "phy", f"phy{phy_num}", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.warning(f"Could not get interface combinations for phy{phy_num}")
                self._vif_max_count_cache[interface] = 1
                return 1

            output = stdout.decode()

            # Look for patterns indicating support for multiple managed (station) interfaces
            # Example: "#{ managed } <= 2" or "#{ managed, AP } <= 2"
            # Can also be: "#{ IBSS } <= 1, #{ managed, AP, ... } <= 2"
            max_count = 1  # Default to 1 (no VIF support)
            for line in output.split('\n'):
                if 'managed' not in line:
                    continue

                # Find all brace groups with their limits on this line
                # Pattern: #{ types } <= number
                brace_pattern = r'#\{([^}]+)\}\s*<=\s*(\d+)'
                matches = re.finditer(brace_pattern, line)

                for match in matches:
                    types = match.group(1)
                    count = int(match.group(2))

                    # Check if this brace group includes "managed"
                    if 'managed' in types:
                        if count > max_count:
                            max_count = count
                            logger.debug(f"{interface}: found managed group with limit {count}")

            if max_count > 1:
                logger.info(f"{interface} (phy{phy_num}) supports up to {max_count} managed interfaces")
            else:
                logger.info(f"{interface} (phy{phy_num}) does not support multiple managed interfaces")

            self._vif_max_count_cache[interface] = max_count
            return max_count

        except Exception as e:
            logger.error(f"Error checking VIF support for {interface}: {e}")
            self._vif_max_count_cache[interface] = 1
            return 1

    async def create_interface(self, name: str, mac_address: Optional[str] = None) -> bool:
        """
        Create a virtual interface or use a physical interface directly.

        Args:
            name: Interface name (e.g., 'wlan0', 'wlan0_1', 'wlan1', 'wlan1_1')
            mac_address: MAC address to assign (random if None)

        Returns:
            True if successful, False otherwise
        """
        _validate_interface_name(name)
        try:
            # Determine if this is a physical interface or VIF
            # Physical: wlan0, wlan1, etc. (no underscore)
            # VIF: wlan0_1, wlan1_1, etc. (has underscore)
            is_physical = '_' not in name

            if is_physical:
                # Using a physical interface directly
                if not await self._interface_exists(name):
                    logger.error(f"Physical interface {name} does not exist")
                    return False
                logger.info(f"Using physical interface {name} as client interface")

                # Generate random MAC if not provided
                if not mac_address:
                    mac_address = self._generate_random_mac()

                # Set MAC address (interface must be down)
                if await self._set_mac_address(name, mac_address):
                    logger.info(f"Set MAC {mac_address} for {name}")
                else:
                    logger.warning(f"Failed to set MAC for {name}, using default")
                    mac_address = None

                if not await self._bring_interface_up(name):
                    logger.error(f"Failed to bring up physical interface {name}")
                    return False
                actual_mac = await self._read_mac_address(name)
                if actual_mac and actual_mac != mac_address:
                    logger.warning(f"{name}: attempted MAC {mac_address}, driver using {actual_mac}")
                self.interfaces[name] = {"mac": actual_mac or mac_address, "state": "up"}
                return True

            # Creating a VIF - extract base interface name
            # wlan0_1 -> wlan0, wlan1_1 -> wlan1
            base_iface = name.rsplit('_', 1)[0]

            if name in self.interfaces:
                logger.warning(f"Interface {name} already exists")
                return True

            # Check if base interface exists
            if not await self._interface_exists(base_iface):
                logger.error(f"Base interface {base_iface} does not exist")
                return False

            # Check if base interface supports virtual interfaces
            max_interfaces = await self.get_max_interfaces(base_iface)
            if max_interfaces <= 1:
                logger.warning(
                    f"Base interface {base_iface} does not support virtual interfaces. "
                    f"Cannot create {name}. Use the base interface directly instead."
                )
                return False

            logger.info(f"Creating virtual interface {name} on VIF-capable {base_iface}")

            # Create virtual interface
            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "iw", "dev", base_iface, "interface", "add", name, "type", "station",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error(f"Failed to create interface {name}: {stderr.decode()}")
                    return False
            else:
                logger.info(f"[MOCK] Would execute: {cmd}")

            # Generate random MAC if not provided
            if not mac_address:
                mac_address = self._generate_random_mac()

            # Set MAC address before bringing interface up
            # This is critical for VIFs to avoid MAC conflicts
            if await self._set_mac_address(name, mac_address):
                logger.info(f"Set MAC {mac_address} for {name}")
            else:
                logger.warning(f"Failed to set MAC for {name}, may cause conflicts")
                mac_address = None

            # Bring interface up
            if not await self._bring_interface_up(name):
                logger.error(f"Failed to bring up interface {name}")
                await self.destroy_interface(name)
                return False

            actual_mac = await self._read_mac_address(name)
            if actual_mac and actual_mac != mac_address:
                logger.warning(f"{name}: attempted MAC {mac_address}, driver using {actual_mac}")
            self.interfaces[name] = {
                "mac": actual_mac or mac_address,
                "state": "up"
            }

            logger.info(f"Successfully created interface {name}")
            return True

        except Exception as e:
            logger.error(f"Error creating interface {name}: {e}")
            return False

    async def destroy_interface(self, name: str) -> bool:
        """
        Destroy a virtual interface or bring down a physical interface.

        Args:
            name: Interface name to destroy

        Returns:
            True if successful, False otherwise
        """
        _validate_interface_name(name)
        try:
            if name not in self.interfaces:
                logger.warning(f"Interface {name} not tracked, attempting to delete anyway")

            logger.info(f"Destroying interface {name}")

            # Check if this is a physical interface (no underscore)
            is_physical = '_' not in name

            # For physical interfaces, only bring them down; do not delete
            if is_physical:
                await self._bring_interface_down(name)
            else:
                # For VIFs: bring down then delete
                await self._bring_interface_down(name)

                # Delete virtual interface
                if not self.mock_mode:
                    proc = await asyncio.create_subprocess_exec(
                        "iw", "dev", name, "del",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()

                    if proc.returncode != 0:
                        stderr_str = stderr.decode()
                        # Interface might not exist, which is fine
                        if "No such device" not in stderr_str:
                            logger.error(f"Failed to destroy interface {name}: {stderr_str}")
                            return False
                else:
                    logger.info(f"[MOCK] Would execute: {cmd}")

            if name in self.interfaces:
                del self.interfaces[name]

            logger.info(f"Successfully destroyed interface {name}")
            return True

        except Exception as e:
            logger.error(f"Error destroying interface {name}: {e}")
            return False

    async def destroy_all_interfaces(self) -> None:
        """Destroy all tracked interfaces"""
        logger.info(f"Destroying all {len(self.interfaces)} interfaces")
        for name in list(self.interfaces.keys()):
            await self.destroy_interface(name)

    async def get_interface_stats(self, name: str) -> Optional[Dict]:
        """
        Get interface statistics.

        Args:
            name: Interface name

        Returns:
            Dict with tx_bytes, rx_bytes, tx_packets, rx_packets or None
        """
        try:
            if self.mock_mode:
                # Return mock data
                return {
                    "tx_bytes": random.randint(100000, 1000000),
                    "rx_bytes": random.randint(500000, 5000000),
                    "tx_packets": random.randint(1000, 10000),
                    "rx_packets": random.randint(5000, 50000),
                }

            # Read from /sys/class/net/{interface}/statistics/
            stats = {}
            stat_names = ["tx_bytes", "rx_bytes", "tx_packets", "rx_packets"]

            for stat in stat_names:
                try:
                    with open(f"/sys/class/net/{name}/statistics/{stat}", "r") as f:
                        stats[stat] = int(f.read().strip())
                except FileNotFoundError:
                    logger.warning(f"Stats file not found for {name}/{stat}")
                    return None
                except Exception as e:
                    logger.error(f"Error reading {stat} for {name}: {e}")
                    return None

            return stats

        except Exception as e:
            logger.error(f"Error getting stats for {name}: {e}")
            return None

    async def get_signal_strength(self, name: str) -> Optional[float]:
        """
        Get signal strength in dBm.

        Args:
            name: Interface name

        Returns:
            Signal strength in dBm or None
        """
        _validate_interface_name(name)
        try:
            if self.mock_mode:
                return float(random.randint(-70, -30))

            proc = await asyncio.create_subprocess_exec(
                "iw", "dev", name, "link",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return None

            # Parse output for signal strength
            output = stdout.decode()
            match = re.search(r"signal:\s*(-?\d+)\s*dBm", output)
            if match:
                return float(match.group(1))

            return None

        except Exception as e:
            logger.error(f"Error getting signal strength for {name}: {e}")
            return None

    async def list_interfaces(self) -> List[str]:
        """List all wireless interfaces on the system"""
        try:
            if self.mock_mode:
                return list(self.interfaces.keys())

            proc = await asyncio.create_subprocess_exec(
                "iw", "dev",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"Failed to list interfaces: {stderr.decode()}")
                return []

            # Parse interface names from iw dev output
            interfaces = []
            for line in stdout.decode().splitlines():
                if line.strip().startswith('Interface'):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        interfaces.append(parts[1])
            return interfaces

        except Exception as e:
            logger.error(f"Error listing interfaces: {e}")
            return []

    async def detect_physical_interfaces(self) -> List[str]:
        """
        Detect all physical wireless interfaces (not VIFs).

        Returns:
            List of physical interface names (e.g., ['wlan0', 'wlan1'])
        """
        try:
            if self.mock_mode:
                return ["wlan0", "wlan1"]

            all_interfaces = await self.list_interfaces()

            # Filter out virtual interfaces (those with _ in the name)
            physical = [iface for iface in all_interfaces if '_' not in iface]

            logger.info(f"Detected physical wireless interfaces: {physical}")
            return physical

        except Exception as e:
            logger.error(f"Error detecting physical interfaces: {e}")
            return []

    async def get_all_interface_capabilities(self) -> Dict[str, int]:
        """
        Get VIF capabilities for all physical wireless interfaces.

        Returns:
            Dict mapping interface name to max managed interfaces count
            Example: {"wlan0": 1, "wlan1": 2}
        """
        capabilities = {}
        physical_interfaces = await self.detect_physical_interfaces()

        for iface in physical_interfaces:
            max_count = await self.get_max_interfaces(iface)
            capabilities[iface] = max_count
            logger.info(f"{iface}: max_interfaces={max_count}")

        return capabilities

    async def _interface_exists(self, name: str) -> bool:
        """Check if interface exists"""
        _validate_interface_name(name)
        if self.mock_mode:
            return name == self.base_interface or name in self.interfaces

        try:
            with open(f"/sys/class/net/{name}/operstate", "r") as f:
                return True
        except FileNotFoundError:
            return False

    async def _read_mac_address(self, name: str) -> Optional[str]:
        """Read the MAC address the kernel is actually using for this interface."""
        try:
            with open(f"/sys/class/net/{name}/address", "r") as f:
                return f.read().strip()
        except Exception:
            return None

    async def _set_mac_address(self, name: str, mac_address: str) -> bool:
        """Set MAC address for interface"""
        _validate_interface_name(name)
        try:
            # Interface must be down to change MAC
            await self._bring_interface_down(name)

            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "ip", "link", "set", "dev", name, "address", mac_address,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error(f"Failed to set MAC for {name}: {stderr.decode()}")
                    return False
            else:
                logger.info(f"[MOCK] Would execute: {cmd}")

            return True

        except Exception as e:
            logger.error(f"Error setting MAC for {name}: {e}")
            return False

    async def _bring_interface_up(self, name: str) -> bool:
        """Bring interface up"""
        _validate_interface_name(name)
        try:
            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "ip", "link", "set", name, "up",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error(f"Failed to bring up {name}: {stderr.decode()}")
                    return False
            else:
                logger.info(f"[MOCK] Would execute: {cmd}")

            return True

        except Exception as e:
            logger.error(f"Error bringing up {name}: {e}")
            return False

    async def _bring_interface_down(self, name: str) -> bool:
        """Bring interface down"""
        _validate_interface_name(name)
        try:
            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "ip", "link", "set", name, "down",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    stderr_str = stderr.decode()
                    # Interface might not exist, which is fine
                    if "Cannot find device" not in stderr_str:
                        logger.error(f"Failed to bring down {name}: {stderr_str}")
                        return False
            else:
                logger.info(f"[MOCK] Would execute: {cmd}")

            return True

        except Exception as e:
            logger.error(f"Error bringing down {name}: {e}")
            return False

    @staticmethod
    def _generate_random_mac() -> str:
        """Generate a random MAC address"""
        # Use locally administered unicast MAC address
        # Set bit 1 of first octet to 1 (locally administered)
        # Set bit 0 of first octet to 0 (unicast)
        first_octet = (random.randint(0, 255) | 0x02) & 0xFE

        mac = [first_octet] + [random.randint(0, 255) for _ in range(5)]
        return ":".join(f"{x:02x}" for x in mac)
