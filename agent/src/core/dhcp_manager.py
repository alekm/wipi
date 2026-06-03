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
        self.dhcp_client = dhcp_client
        self.mock_mode = mock_mode
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.ip_addresses: Dict[str, str] = {}  # interface -> IP address

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
        try:
            if interface in self.processes:
                logger.warning(f"DHCP client already running for {interface}")
                return True

            existing_ip = await self.get_ip_address(interface)
            if existing_ip:
                logger.info(f"{interface} already has IP {existing_ip}, skipping DHCP client startup")
                self.ip_addresses[interface] = existing_ip
                self.processes[interface] = None
                gateway = await self._get_gateway(interface, existing_ip)
                if gateway:
                    await self._setup_policy_routing(interface, existing_ip, gateway)
                else:
                    logger.warning(f"Could not determine gateway for {interface}, source IP binding may not route correctly")
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
        try:
            if self.mock_mode:
                if interface in self.ip_addresses:
                    return self.ip_addresses[interface]
                import random
                mock_ip = f"192.168.1.{random.randint(100, 250)}"
                self.ip_addresses[interface] = mock_ip
                return mock_ip

            proc = await asyncio.create_subprocess_exec(
                "ip", "-4", "addr", "show", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return None

            ip_address = None
            for line in stdout.decode().splitlines():
                if 'inet ' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
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
        logger.info(f"Waiting for {interface} to get IP address (timeout: {timeout}s)")

        start_time = asyncio.get_event_loop().time()
        while True:
            ip_address = await self.get_ip_address(interface)

            if ip_address:
                logger.info(f"{interface} got IP address: {ip_address}")
                return ip_address

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for {interface} to get IP")
                return None

            await asyncio.sleep(1)

    async def renew_lease(self, interface: str) -> bool:
        try:
            logger.info(f"Renewing DHCP lease for {interface}")

            if self.mock_mode:
                logger.info(f"[MOCK] Would renew DHCP lease for {interface}")
                return True

            if self.dhcp_client == "dhclient":
                await self._stop_dhclient(interface)
                await asyncio.sleep(0.5)
                return await self._start_dhclient(interface)
            elif self.dhcp_client == "udhcpc":
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

    # ── Policy routing ──────────────────────────────────────────────────────

    def _get_table_id(self, interface: str) -> int:
        """Map interface name to a unique routing table ID (100–199)."""
        m = re.search(r'(\d+)$', interface)
        if m:
            return 100 + int(m.group(1)) % 100
        import hashlib
        return 100 + int(hashlib.md5(interface.encode()).hexdigest()[:2], 16) % 100

    async def _run_cmd(self, *args) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _get_gateway_from_lease(self, interface: str) -> Optional[str]:
        """Parse the DHCP-assigned gateway from our per-interface lease file."""
        lease_file = f"/tmp/dhclient-{interface}.leases"
        try:
            with open(lease_file) as f:
                content = f.read()
            matches = re.findall(r'option routers ([0-9.]+);', content)
            if matches:
                return matches[-1]
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Error reading lease file for {interface}: {e}")
        return None

    async def _get_gateway(self, interface: str, ip: str) -> Optional[str]:
        """
        Discover the gateway for an interface, trying three methods in order:
        1. Per-interface dhclient lease file
        2. Kernel routing table (default route on this interface)
        3. Infer x.x.x.1 from the interface subnet
        """
        # 1. Lease file (most accurate)
        gw = await self._get_gateway_from_lease(interface)
        if gw:
            logger.debug(f"Gateway for {interface}: {gw} (from lease file)")
            return gw

        # 2. Kernel routing table
        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "route", "show", "dev", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().splitlines():
                if "default via" in line:
                    parts = line.split()
                    idx = parts.index("via") + 1
                    gw = parts[idx]
                    logger.debug(f"Gateway for {interface}: {gw} (from routing table)")
                    return gw
        except Exception:
            pass

        # 3. Infer x.x.x.1 from the interface's subnet
        try:
            import ipaddress
            proc = await asyncio.create_subprocess_exec(
                "ip", "-4", "addr", "show", interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().splitlines():
                if "inet " in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        network = ipaddress.ip_interface(parts[1]).network
                        gw = str(network.network_address + 1)
                        logger.info(f"Inferred gateway {gw} for {interface} from subnet {network}")
                        return gw
        except Exception:
            pass

        return None

    async def _setup_policy_routing(self, interface: str, ip: str, gateway: str) -> None:
        """
        Add a policy routing rule so traffic sourced from `ip` uses a
        dedicated routing table that routes via the correct gateway.
        Without this, traffic from secondary interfaces leaks out through
        the primary interface's default route.
        """
        table_id = self._get_table_id(interface)

        # Remove any stale rule for this source IP
        await self._run_cmd("ip", "rule", "del", "from", ip, "table", str(table_id))

        if await self._run_cmd("ip", "rule", "add", "from", ip, "table", str(table_id), "priority", "100"):
            logger.info(f"Policy routing: from {ip} → table {table_id}")
        else:
            logger.warning(f"Failed to add policy routing rule for {interface} ({ip})")

        await self._run_cmd("ip", "route", "add", "default", "via", gateway, "dev", interface, "table", str(table_id))
        logger.info(f"Policy routing: table {table_id} default via {gateway} dev {interface}")

    async def _teardown_policy_routing(self, interface: str) -> None:
        """Remove policy routing for an interface when it's torn down."""
        ip = self.ip_addresses.get(interface)
        if not ip:
            return
        table_id = self._get_table_id(interface)
        await self._run_cmd("ip", "rule", "del", "from", ip, "table", str(table_id))
        await self._run_cmd("ip", "route", "flush", "table", str(table_id))
        logger.info(f"Removed policy routing for {interface} ({ip})")

    # ── dhclient ────────────────────────────────────────────────────────────

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

            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    "pkill", "-9", "-f", f"dhclient.*{interface}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                await asyncio.sleep(2)

            await asyncio.sleep(1)

            conf_file = None
            if not self.mock_mode:
                conf_file = f"/tmp/dhclient_{interface}.conf"

                if personality:
                    profile = get_profile(personality)
                    if profile:
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
                    conf_content = f"""# Auto-generated dhclient config for {interface}
send host-name "{hostname}";
"""
                else:
                    conf_file = None

                if conf_file:
                    with open(conf_file, 'w') as f:
                        f.write(conf_content)
                    logger.debug(f"Created dhclient config {conf_file}")

            lease_file = f"/tmp/dhclient-{interface}.leases"
            cmd = [dhclient_bin, "-v", "-lf", lease_file]
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

                ip_address = await self.wait_for_ip(interface, timeout=self.ip_timeout)
                if ip_address:
                    logger.info(f"dhclient successfully obtained IP {ip_address} for {interface}")
                    self.processes[interface] = None
                    gateway = await self._get_gateway(interface, ip_address)
                    if gateway:
                        await self._setup_policy_routing(interface, ip_address, gateway)
                    else:
                        logger.warning(f"Could not determine gateway for {interface}, source IP binding may not route correctly")
                    return True
                else:
                    logger.error(f"dhclient for {interface} failed to obtain IP within {self.ip_timeout}s")
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
            await self._teardown_policy_routing(interface)

            if not self.mock_mode:
                cmd = [_get_dhclient_path(), "-r", interface]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

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

                ip_address = await self.wait_for_ip(interface, timeout=self.ip_timeout)
                if ip_address:
                    gateway = await self._get_gateway(interface, ip_address)
                    if gateway:
                        await self._setup_policy_routing(interface, ip_address, gateway)
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
            await self._teardown_policy_routing(interface)

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
