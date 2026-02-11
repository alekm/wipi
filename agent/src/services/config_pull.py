"""
Config Pull Service - Autonomously polls controller for configuration changes.
"""
import asyncio
import logging
from typing import Optional

import aiohttp
from shared.models import AgentConfiguration

from .config_store import ConfigStore

logger = logging.getLogger(__name__)


class ConfigPullService:
    """
    Background service that polls the controller for configuration changes
    and applies them autonomously. Also monitors interface health and
    reapplies configuration if interfaces fail.
    """

    def __init__(
        self,
        agent_id: str,
        controller_url: str,
        config_store: ConfigStore,
        apply_callback,
        agent_api_key: str,
        poll_interval: int = 30,
        interface_manager=None,
        wpa_manager=None
    ):
        """
        Initialize config pull service.

        Args:
            agent_id: This agent's ID (e.g., "wipi-01")
            controller_url: Controller base URL (e.g., "http://172.16.254.4:8000")
            config_store: ConfigStore instance for persistence
            apply_callback: Async function to call when applying new config
            agent_api_key: API key for authentication with controller
            poll_interval: How often to poll in seconds (default: 30)
            interface_manager: InterfaceManager instance for health checks
            wpa_manager: WPAManager instance for health checks
        """
        self.agent_id = agent_id
        self.controller_url = controller_url.rstrip('/')
        self.config_store = config_store
        self.apply_callback = apply_callback
        self.agent_api_key = agent_api_key
        self.poll_interval = poll_interval
        self.interface_manager = interface_manager
        self.wpa_manager = wpa_manager

        self.running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(f"ConfigPullService initialized: poll_interval={poll_interval}s")

    async def start(self) -> None:
        """Start the background polling loop."""
        if self.running:
            logger.warning("Config pull service already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Config pull service started")

    async def stop(self) -> None:
        """Stop the background polling loop."""
        if not self.running:
            return

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Config pull service stopped")

    async def recover_config_on_startup(self) -> bool:
        """
        Load persisted config from disk and apply it.
        Called once during agent startup for recovery after restart.

        Returns:
            True if config was recovered and applied, False otherwise
        """
        try:
            logger.info("Checking for persisted config on startup...")

            # Load from disk
            persisted = self.config_store.load_config()
            if not persisted:
                logger.info("No persisted config found on startup")
                return False

            config_hash = persisted['hash']
            config_dict = persisted['config']

            logger.info(f"Found persisted config on startup: {config_hash[:8]}...")

            # Verify with controller that this is still the desired config
            try:
                headers = {"X-Agent-Api-Key": self.agent_api_key}
                async with aiohttp.ClientSession() as session:
                    url = f"{self.controller_url}/api/pis/{self.agent_id}/configuration"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), headers=headers) as response:
                        if response.status == 200:
                            controller_data = await response.json()
                            controller_hash = controller_data.get('hash', '')

                            if controller_hash == config_hash:
                                logger.info(f"Persisted config matches controller (hash={config_hash[:8]}...)")
                                # Config is still valid, apply it
                                agent_config = AgentConfiguration(**config_dict)
                                await self.apply_callback(agent_config)
                                logger.info("Successfully recovered and applied persisted config")
                                return True
                            else:
                                logger.info(
                                    f"Persisted config hash mismatch: "
                                    f"local={config_hash[:8]}... controller={controller_hash[:8]}..."
                                )
                                # Controller has newer config, will be picked up by poll loop
                                return False
                        else:
                            logger.warning(f"Failed to verify config with controller: HTTP {response.status}")
                            # Apply persisted config anyway - better than nothing
                            agent_config = AgentConfiguration(**config_dict)
                            await self.apply_callback(agent_config)
                            logger.info("Applied persisted config (controller verification failed)")
                            return True

            except Exception as e:
                logger.error(f"Error verifying config with controller: {e}")
                # Apply persisted config anyway - better than nothing
                agent_config = AgentConfiguration(**config_dict)
                await self.apply_callback(agent_config)
                logger.info("Applied persisted config (controller unavailable)")
                return True

        except Exception as e:
            logger.error(f"Error recovering config on startup: {e}")
            return False

    async def _poll_loop(self) -> None:
        """Main polling loop - checks for config changes periodically."""
        logger.info("Config pull loop started")

        while self.running:
            try:
                await self._check_and_apply_config()
            except asyncio.CancelledError:
                logger.info("Config pull loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in config pull loop: {e}")

            # Sleep until next poll
            await asyncio.sleep(self.poll_interval)

        logger.info("Config pull loop exiting")

    async def _check_interface_health(self, desired_config: dict) -> bool:
        """
        Check if any configured interfaces are unhealthy (disconnected/error).

        Args:
            desired_config: The desired configuration dict

        Returns:
            True if any interfaces are unhealthy, False if all healthy
        """
        if not self.interface_manager or not self.wpa_manager:
            # Can't check health without managers
            return False

        try:
            interfaces = desired_config.get('interfaces', [])
            if not interfaces:
                # No interfaces configured, nothing to check
                return False

            # Check each configured interface
            for iface_config in interfaces:
                iface_name = iface_config.get('name')
                if not iface_name:
                    continue

                # Check if interface exists and is tracked
                if iface_name not in self.interface_manager.interfaces:
                    logger.warning(f"Interface {iface_name} not tracked - may need reapplication")
                    return True

                # Check WPA connection status
                wpa_status = await self.wpa_manager.get_connection_status(iface_name)
                if not wpa_status or not wpa_status.get("connected"):
                    logger.info(f"Interface {iface_name} disconnected - needs reapplication")
                    return True

            # All interfaces healthy
            return False

        except Exception as e:
            logger.error(f"Error checking interface health: {e}")
            # On error, assume healthy to avoid flapping
            return False

    async def _check_and_apply_config(self) -> None:
        """
        Fetch config from controller, compare hash, and apply if changed
        OR if interfaces are unhealthy.
        """
        try:
            # Get current hash
            current_hash = self.config_store.get_current_hash()

            # Fetch desired config from controller
            headers = {"X-Agent-Api-Key": self.agent_api_key}
            async with aiohttp.ClientSession() as session:
                url = f"{self.controller_url}/api/pis/{self.agent_id}/configuration"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch config from controller: HTTP {response.status}")
                        return

                    data = await response.json()
                    desired_hash = data.get('hash', '')
                    desired_config = data.get('config', {})

                    # Check if config changed
                    config_changed = desired_hash != current_hash

                    # Check if interfaces are unhealthy (even if config unchanged)
                    interfaces_unhealthy = await self._check_interface_health(desired_config)

                    # If config unchanged AND interfaces healthy, nothing to do
                    if not config_changed and not interfaces_unhealthy:
                        logger.debug(f"Config unchanged and interfaces healthy: {desired_hash[:8]}...")
                        return

                    # Config changed OR interfaces unhealthy - apply it
                    if config_changed:
                        logger.info(
                            f"New configuration detected: {desired_hash[:8]}... "
                            f"(previous: {current_hash[:8] if current_hash else 'none'}...)"
                        )
                    else:
                        logger.info(
                            f"Configuration unchanged but interfaces unhealthy - reapplying: {desired_hash[:8]}..."
                        )

                    # Skip empty configs
                    if desired_hash == "empty" or not desired_config.get('interfaces'):
                        logger.info("Received empty config - clearing interfaces")
                        agent_config = AgentConfiguration(interfaces=[])
                    else:
                        agent_config = AgentConfiguration(**desired_config)

                    # Apply configuration
                    try:
                        await self.apply_callback(agent_config)
                        logger.info(f"Successfully applied config: {desired_hash[:8]}...")

                        # Save to disk
                        self.config_store.save_config(desired_config, desired_hash)

                        # Report success to controller
                        await self._report_config_applied(desired_hash, success=True)

                    except Exception as e:
                        logger.error(f"Failed to apply config: {e}")
                        # Report failure to controller
                        await self._report_config_applied(desired_hash, success=False, error_message=str(e))

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching config: {e}")
        except Exception as e:
            logger.error(f"Error checking and applying config: {e}")

    async def _report_config_applied(
        self,
        config_hash: str,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """Report to controller that config was applied (or failed)."""
        try:
            headers = {"X-Agent-Api-Key": self.agent_api_key}
            async with aiohttp.ClientSession() as session:
                url = f"{self.controller_url}/api/pis/{self.agent_id}/config_applied"
                payload = {
                    "config_hash": config_hash,
                    "success": success,
                    "error_message": error_message
                }

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        logger.debug(f"Reported config applied: {config_hash[:8]}... (success={success})")
                    else:
                        logger.warning(f"Failed to report config applied: HTTP {response.status}")

        except Exception as e:
            logger.warning(f"Error reporting config applied: {e}")
