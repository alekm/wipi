"""
WPA Manager - Manages wpa_supplicant processes for Wi-Fi authentication.
"""
import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class WPAManager:
    """Manages wpa_supplicant processes for interfaces"""

    def __init__(self, config_dir: str = "/var/run/wipi", mock_mode: bool = False, config=None):
        """
        Initialize WPA manager.

        Args:
            config_dir: Directory to store wpa_supplicant config files
            mock_mode: If True, simulate commands without executing them
            config: Configuration object with timeout settings
        """
        self.config_dir = Path(config_dir)
        self.mock_mode = mock_mode
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.configs: Dict[str, str] = {}  # interface -> config_path

        # Set timeouts from config or use defaults
        if config:
            self.connection_timeout = config.wpa_connection_timeout
            self.process_timeout = config.wpa_process_timeout
        else:
            self.connection_timeout = 30
            self.process_timeout = 5

        # Create config directory if it doesn't exist
        if not self.mock_mode:
            self.config_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"WPAManager initialized with config_dir: {config_dir}, mock_mode: {mock_mode}")

    async def start_wpa_supplicant(self, interface: str, ssid: str, password: str) -> bool:
        """
        Start wpa_supplicant for an interface.

        Args:
            interface: Interface name
            ssid: SSID to connect to
            password: Wi-Fi password

        Returns:
            True if successful, False otherwise
        """
        try:
            if interface in self.processes:
                logger.warning(f"wpa_supplicant already running for {interface}")
                return True

            # Generate config file
            config_path = self._generate_config(interface, ssid, password)
            if not config_path:
                logger.error(f"Failed to generate config for {interface}")
                return False

            self.configs[interface] = config_path

            logger.info(f"Starting wpa_supplicant for {interface}")

            # Start wpa_supplicant
            cmd = [
                "wpa_supplicant",
                "-B",  # Run in background
                "-i", interface,
                "-c", config_path,
                "-f", f"{self.config_dir}/{interface}_wpa.log"
            ]

            if not self.mock_mode:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                # wpa_supplicant with -B usually returns immediately; cap wait so we don't block forever
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(self.process_timeout))
                except asyncio.TimeoutError:
                    # Process didn't exit in 5s: on some systems -B keeps parent alive or daemon runs in foreground.
                    # Assume it's running and continue (don't kill it or we'd kill the daemon).
                    logger.warning(
                        f"wpa_supplicant for {interface} did not exit within 5s, assuming it is running"
                    )
                    self.processes[interface] = None
                    return True

                if proc.returncode != 0:
                    err = (stderr or b"").decode().strip()
                    logger.error(f"Failed to start wpa_supplicant for {interface}: {err}")
                    return False

                # Find the actual wpa_supplicant process
                # Since -B forks, we need to find it by interface
                self.processes[interface] = None  # Placeholder, tracked by pidfile

                logger.info(f"wpa_supplicant started for {interface}")
            else:
                logger.info(f"[MOCK] Would execute: {' '.join(cmd)}")
                self.processes[interface] = None

            return True

        except Exception as e:
            logger.error(
                f"Error starting wpa_supplicant for {interface}: {type(e).__name__}: {e}"
            )
            return False

    async def stop_wpa_supplicant(self, interface: str) -> bool:
        """
        Stop wpa_supplicant for an interface.

        Args:
            interface: Interface name

        Returns:
            True if successful, False otherwise
        """
        try:
            if interface not in self.processes and interface not in self.configs:
                logger.warning(f"wpa_supplicant not tracked for {interface}")
                return True

            logger.info(f"Stopping wpa_supplicant for {interface}")

            if not self.mock_mode:
                # Kill wpa_supplicant by interface
                # Use pkill to find and kill the process
                proc = await asyncio.create_subprocess_exec(
                    "pkill", "-f", f"wpa_supplicant.*{interface}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                # Wait a bit for clean shutdown
                await asyncio.sleep(0.5)
            else:
                logger.info(f"[MOCK] Would kill wpa_supplicant for {interface}")

            # Clean up config file
            if interface in self.configs:
                config_path = self.configs[interface]
                if not self.mock_mode and os.path.exists(config_path):
                    os.remove(config_path)
                del self.configs[interface]

            if interface in self.processes:
                del self.processes[interface]

            logger.info(f"wpa_supplicant stopped for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error stopping wpa_supplicant for {interface}: {e}")
            return False

    async def stop_all(self) -> None:
        """Stop all wpa_supplicant processes"""
        logger.info(f"Stopping all {len(self.processes)} wpa_supplicant processes")
        for interface in list(self.processes.keys()):
            await self.stop_wpa_supplicant(interface)

    async def get_connection_status(self, interface: str) -> Optional[Dict]:
        """
        Get connection status for an interface.

        Args:
            interface: Interface name

        Returns:
            Dict with status, ssid, bssid, etc. or None
        """
        try:
            if self.mock_mode:
                # Return mock connected status
                return {
                    "state": "COMPLETED",
                    "ssid": "MockNetwork",
                    "bssid": "00:11:22:33:44:55",
                    "connected": True
                }

            # Use wpa_cli to get status
            cmd = ["wpa_cli", "-i", interface, "status"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"Failed to get status for {interface}: {stderr.decode()}")
                return None

            # Parse wpa_cli status output
            output = stdout.decode()
            status = {}

            for line in output.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    status[key.strip()] = value.strip()

            # Determine if connected
            state = status.get("wpa_state", "")
            status["connected"] = state == "COMPLETED"

            return status

        except Exception as e:
            logger.error(f"Error getting connection status for {interface}: {e}")
            return None

    async def wait_for_connection(self, interface: str, timeout: int = 30) -> bool:
        """
        Wait for interface to connect.

        Args:
            interface: Interface name
            timeout: Maximum time to wait in seconds

        Returns:
            True if connected, False otherwise
        """
        logger.info(f"Waiting for {interface} to connect (timeout: {timeout}s)")

        start_time = asyncio.get_event_loop().time()
        while True:
            status = await self.get_connection_status(interface)

            if status and status.get("connected"):
                logger.info(f"{interface} connected to {status.get('ssid')}")
                return True

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for {interface} to connect")
                return False

            # Wait before checking again
            await asyncio.sleep(1)

    def _generate_config(self, interface: str, ssid: str, password: str) -> Optional[str]:
        """
        Generate wpa_supplicant config file.

        Args:
            interface: Interface name
            ssid: SSID
            password: Password

        Returns:
            Path to config file or None
        """
        try:
            config_path = self.config_dir / f"{interface}_wpa.conf"

            # Generate PSK using wpa_passphrase
            # For simplicity, we'll create a basic config
            # In production, you might want to use wpa_passphrase for proper PSK
            config_content = f"""
ctrl_interface=/var/run/wpa_supplicant
update_config=1

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
    scan_ssid=1
}}
"""

            if not self.mock_mode:
                with open(config_path, 'w') as f:
                    f.write(config_content)

                # Set appropriate permissions
                os.chmod(config_path, 0o600)
            else:
                logger.info(f"[MOCK] Would write config to {config_path}")

            logger.info(f"Generated wpa_supplicant config for {interface}")
            return str(config_path)

        except Exception as e:
            logger.error(f"Error generating config for {interface}: {e}")
            return None

    async def get_available_networks(self, interface: str) -> list:
        """
        Scan and get available networks.

        Args:
            interface: Interface name

        Returns:
            List of available SSIDs
        """
        try:
            if self.mock_mode:
                return ["MockNetwork1", "MockNetwork2", "TestSSID"]

            # Trigger scan
            cmd = ["wpa_cli", "-i", interface, "scan"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            # Wait for scan to complete
            await asyncio.sleep(2)

            # Get scan results
            cmd = ["wpa_cli", "-i", interface, "scan_results"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"Failed to get scan results: {stderr.decode()}")
                return []

            # Parse scan results
            output = stdout.decode()
            networks = []

            for line in output.split('\n')[1:]:  # Skip header
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 5:
                        ssid = parts[4]
                        if ssid and ssid not in networks:
                            networks.append(ssid)

            return networks

        except Exception as e:
            logger.error(f"Error scanning networks: {e}")
            return []
