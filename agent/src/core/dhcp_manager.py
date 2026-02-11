"""
DHCP Manager - Manages DHCP client processes for interfaces.
"""
import asyncio
import logging
import os
import re
import shutil
from typing import Dict, Optional

from .dhcp_profiles import get_profile, get_random_profile

logger = logging.getLogger(__name__)

# Full path to dhclient so it works when systemd gives a minimal PATH
DHCLIENT_PATH: Optional[str] = None


def _get_dhclient_path() -> str:
    global DHCLIENT_PATH
    if DHCLIENT_PATH is not None:
        return DHCLIENT_PATH
    for path in ("/usr/sbin/dhclient", "/sbin/dhclient"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            DHCLIENT_PATH = path
            return DHCLIENT_PATH
    found = shutil.which("dhclient")
    DHCLIENT_PATH = found or "dhclient"
    return DHCLIENT_PATH


class DHCPManager:
    """Manages DHCP client processes for interfaces"""

    def __init__(self, dhcp_client: str = "dhclient", mock_mode: bool = False, config=None):
        """
        Initialize DHCP manager.

        Args:
            dhcp_client: DHCP client to use ('dhclient' or 'udhcpc')
            mock_mode: If True, simulate commands without executing them
            config: Configuration object with timeout settings
        """
        self.dhcp_client = dhcp_client
        self.mock_mode = mock_mode
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.ip_addresses: Dict[str, str] = {}  # interface -> IP address

        # Set timeouts from config or use defaults
        if config:
            self.ip_timeout = config.dhcp_ip_timeout
            self.process_timeout = config.dhcp_process_timeout
        else:
            self.ip_timeout = 30
            self.process_timeout = 5

        logger.info(f"DHCPManager initialized with client: {dhcp_client}, mock_mode: {mock_mode}")

    async def start_dhcp(
        self,
        interface: str,
        hostname: Optional[str] = None,
        personality: Optional[str] = None
    ) -> bool:
        """
        Start DHCP client for an interface.

        Args:
            interface: Interface name
            hostname: Optional hostname to send in DHCP request
            personality: Optional DHCP personality (e.g., 'windows10', 'iphone', 'xbox')

        Returns:
            True if successful, False otherwise
        """
        try:
            if interface in self.processes:
                logger.warning(f"DHCP client already running for {interface}")
                return True

            # Check if interface already has an IP address
            existing_ip = await self.get_ip_address(interface)
            if existing_ip:
                logger.info(f"{interface} already has IP {existing_ip}, skipping DHCP client startup")
                self.ip_addresses[interface] = existing_ip
                # Mark as managed so stop_dhcp works
                self.processes[interface] = None
                return True

            logger.info(
                f"Starting DHCP client for {interface}" +
                (f" with hostname {hostname}" if hostname else "") +
                (f" as {personality}" if personality else "")
            )

            if self.dhcp_client == "dhclient":
                return await self._start_dhclient(interface, hostname, personality)
            elif self.dhcp_client == "udhcpc":
                return await self._start_udhcpc(interface, hostname, personality)
            else:
                logger.error(f"Unsupported DHCP client: {self.dhcp_client}")
                return False

        except Exception as e:
            logger.error(f"Error starting DHCP for {interface}: {e}")
            return False

    async def stop_dhcp(self, interface: str) -> bool:
        """
        Stop DHCP client for an interface.

        Args:
            interface: Interface name

        Returns:
            True if successful, False otherwise
        """
        try:
            if interface not in self.processes and interface not in self.ip_addresses:
                logger.warning(f"DHCP client not tracked for {interface}")
                return True

            logger.info(f"Stopping DHCP client for {interface}")

            if self.dhcp_client == "dhclient":
                return await self._stop_dhclient(interface)
            elif self.dhcp_client == "udhcpc":
                return await self._stop_udhcpc(interface)
            else:
                logger.error(f"Unsupported DHCP client: {self.dhcp_client}")
                return False

        except Exception as e:
            logger.error(f"Error stopping DHCP for {interface}: {e}")
            return False

    async def stop_all(self) -> None:
        """Stop all DHCP clients"""
        logger.info(f"Stopping all {len(self.processes)} DHCP clients")
        for interface in list(self.processes.keys()):
            await self.stop_dhcp(interface)

    async def get_ip_address(self, interface: str) -> Optional[str]:
        """
        Get IP address for an interface.

        Args:
            interface: Interface name

        Returns:
            IP address string or None
        """
        try:
            if self.mock_mode:
                # Return mock IP
                if interface in self.ip_addresses:
                    return self.ip_addresses[interface]
                # Generate mock IP
                import random
                mock_ip = f"192.168.1.{random.randint(100, 250)}"
                self.ip_addresses[interface] = mock_ip
                return mock_ip

            # Get IP using ip command
            proc = await asyncio.create_subprocess_exec(
                "ip", "-4", "addr", "show", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return None

            # Parse IP address from output (look for "inet 10.0.0.1/24")
            ip_address = None
            for line in stdout.decode().splitlines():
                if 'inet ' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        # Extract IP without CIDR notation
                        ip_address = parts[1].split('/')[0]
                        break

            if ip_address:
                self.ip_addresses[interface] = ip_address
                return ip_address

            return None

        except Exception as e:
            logger.error(f"Error getting IP for {interface}: {e}")
            return None

    async def wait_for_ip(self, interface: str, timeout: int = 30) -> Optional[str]:
        """
        Wait for interface to get an IP address.

        Args:
            interface: Interface name
            timeout: Maximum time to wait in seconds

        Returns:
            IP address string or None
        """
        logger.info(f"Waiting for {interface} to get IP address (timeout: {timeout}s)")

        start_time = asyncio.get_event_loop().time()
        while True:
            ip_address = await self.get_ip_address(interface)

            if ip_address:
                logger.info(f"{interface} got IP address: {ip_address}")
                return ip_address

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for {interface} to get IP")
                return None

            # Wait before checking again
            await asyncio.sleep(1)

    async def renew_lease(self, interface: str) -> bool:
        """
        Renew DHCP lease for an interface.

        Args:
            interface: Interface name

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Renewing DHCP lease for {interface}")

            if self.mock_mode:
                logger.info(f"[MOCK] Would renew DHCP lease for {interface}")
                return True

            if self.dhcp_client == "dhclient":
                # Release and renew
                await self._stop_dhclient(interface)
                await asyncio.sleep(0.5)
                return await self._start_dhclient(interface)
            elif self.dhcp_client == "udhcpc":
                # Send SIGUSR1 to renew
                proc = await asyncio.create_subprocess_exec(
                    "pkill", "-USR1", "-f", f"udhcpc.*{interface}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Error renewing DHCP lease for {interface}: {e}")
            return False

    async def _start_dhclient(
        self,
        interface: str,
        hostname: Optional[str] = None,
        personality: Optional[str] = None
    ) -> bool:
        """Start dhclient for interface and wait for IP address."""
        try:
            dhclient_bin = _get_dhclient_path()
            logger.info(f"Starting dhclient for {interface} using {dhclient_bin}")

            # Kill any existing dhclient for this interface
            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "pkill", "-9", "-f", f"dhclient.*{interface}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                # Wait longer to ensure processes are fully terminated
                await asyncio.sleep(2)

            # Brief delay so interface is ready after wpa_supplicant
            await asyncio.sleep(1)

            # Create dhclient.conf with fingerprint profile if specified
            conf_file = None
            if not self.mock_mode:
                conf_file = f"/tmp/dhclient_{interface}.conf"

                if personality:
                    # Use DHCP fingerprint profile
                    profile = get_profile(personality)
                    if profile:
                        # Generate hostname from profile if not explicitly provided
                        if not hostname:
                            hostname = profile.generate_hostname()
                        conf_content = profile.get_dhclient_config(hostname)
                        logger.info(f"Using DHCP profile '{personality}' for {interface} as {hostname}")
                    else:
                        logger.warning(f"Unknown DHCP personality '{personality}', using default")
                        conf_content = f"""# Auto-generated dhclient config for {interface}
send host-name "{hostname or 'unknown'}";
"""
                elif hostname:
                    # Just set hostname without fingerprinting
                    conf_content = f"""# Auto-generated dhclient config for {interface}
send host-name "{hostname}";
"""
                else:
                    # No config needed
                    conf_file = None

                if conf_file:
                    with open(conf_file, 'w') as f:
                        f.write(conf_content)
                    logger.debug(f"Created dhclient config {conf_file}")

            # Start dhclient in background mode (not one-shot)
            # We'll wait for IP address instead of waiting for process to exit
            cmd = [dhclient_bin, "-v"]
            if conf_file:
                cmd.extend(["-cf", conf_file])
            cmd.append(interface)

            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                logger.info(f"dhclient started for {interface}, waiting for IP address...")

                # Wait for interface to get an IP address
                ip_address = await self.wait_for_ip(interface, timeout=self.ip_timeout)
                if ip_address:
                    logger.info(f"dhclient successfully obtained IP {ip_address} for {interface}")
                    self.processes[interface] = None
                    return True
                else:
                    logger.error(f"dhclient for {interface} failed to obtain IP within 30s")
                    # Kill dhclient since it failed
                    await asyncio.create_subprocess_exec(
                        "pkill", "-9", "-f", f"dhclient.*{interface}"
                    )
                    return False
            else:
                logger.info(f"[MOCK] Would execute: {' '.join(cmd)}")
                self.processes[interface] = None
                return True

        except Exception as e:
            logger.error(f"Error starting dhclient for {interface}: {e}")
            return False

    async def _stop_dhclient(self, interface: str) -> bool:
        """Stop dhclient for interface"""
        try:
            if not self.mock_mode:
                # Release DHCP lease
                cmd = [_get_dhclient_path(), "-r", interface]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                # Kill any remaining dhclient processes
                proc = await asyncio.create_subprocess_exec(
                    "pkill", "-f", f"dhclient.*{interface}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
            else:
                logger.info(f"[MOCK] Would stop dhclient for {interface}")

            if interface in self.processes:
                del self.processes[interface]
            if interface in self.ip_addresses:
                del self.ip_addresses[interface]

            logger.info(f"dhclient stopped for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error stopping dhclient for {interface}: {e}")
            return False

    async def _start_udhcpc(
        self,
        interface: str,
        hostname: Optional[str] = None,
        personality: Optional[str] = None
    ) -> bool:
        """Start udhcpc for interface"""
        try:
            # Get hostname from personality if specified
            if personality and not hostname:
                profile = get_profile(personality)
                if profile:
                    hostname = profile.generate_hostname()

            cmd = ["udhcpc", "-i", interface, "-f", "-S"]
            if hostname:
                cmd.extend(["-h", hostname])

            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                self.processes[interface] = proc

                logger.info(f"udhcpc started for {interface}")
            else:
                logger.info(f"[MOCK] Would execute: {' '.join(cmd)}")
                self.processes[interface] = None

            return True

        except Exception as e:
            logger.error(f"Error starting udhcpc for {interface}: {e}")
            return False

    async def _stop_udhcpc(self, interface: str) -> bool:
        """Stop udhcpc for interface"""
        try:
            if interface in self.processes and self.processes[interface]:
                proc = self.processes[interface]
                if not self.mock_mode:
                    try:
                        proc.terminate()
                        await asyncio.wait_for(proc.wait(), timeout=self.process_timeout)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
            else:
                # Kill by process name
                if not self.mock_mode:
                    proc = await asyncio.create_subprocess_exec(
                        "pkill", "-f", f"udhcpc.*{interface}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()

            if interface in self.processes:
                del self.processes[interface]
            if interface in self.ip_addresses:
                del self.ip_addresses[interface]

            logger.info(f"udhcpc stopped for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error stopping udhcpc for {interface}: {e}")
            return False
