"""
Orchestrator Service - Applies scenarios to the Pi fleet.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
import aiohttp

from shared.models import (
    Scenario,
    AgentConfiguration,
    InterfaceConfig,
    AgentStatus,
    ScenarioStatus,
)
from ..models import ScenarioExecutionModel
from .pi_manager import PiManager
from .scenario_manager import ScenarioManager
from .psk_manager import PskManager
from .desired_config_manager import DesiredConfigManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates scenario application across the Pi fleet"""

    def __init__(self, pi_manager: PiManager, scenario_manager: ScenarioManager, psk_manager: PskManager, config=None, desired_config_manager: Optional[DesiredConfigManager] = None):
        """
        Initialize Orchestrator.

        Args:
            pi_manager: Pi Manager instance
            scenario_manager: Scenario Manager instance
            psk_manager: PSK Manager instance
            config: Configuration object with timeout settings
            desired_config_manager: Optional desired config manager for pull-based architecture
        """
        self.pi_manager = pi_manager
        self.scenario_manager = scenario_manager
        self.psk_manager = psk_manager
        self.desired_config_manager = desired_config_manager or DesiredConfigManager()
        self.active_executions: Dict[str, ScenarioStatus] = {}

        # Set timeouts from config or use defaults
        if config:
            self.configure_timeout = config.orchestrator_configure_timeout
            self.apply_timeout = config.orchestrator_apply_timeout
            self.stop_timeout = config.orchestrator_stop_timeout
            self.status_timeout = config.orchestrator_status_timeout
        else:
            self.configure_timeout = 10
            self.apply_timeout = 120
            self.stop_timeout = 30
            self.status_timeout = 5

        logger.info("Orchestrator initialized")

    async def apply_scenario(self, db: Session, scenario_id: str) -> Optional[ScenarioStatus]:
        """
        Apply a scenario to the Pi fleet.

        Args:
            db: Database session
            scenario_id: Scenario ID to apply

        Returns:
            ScenarioStatus or None if scenario not found
        """
        try:
            # Get scenario
            scenario = self.scenario_manager.get_scenario(db, scenario_id)
            if not scenario:
                logger.error(f"Scenario {scenario_id} not found")
                return None

            logger.info(f"Applying scenario: {scenario.name} ({scenario_id})")

            # Validate scenario
            online_pis = self.pi_manager.get_online_pis(db)
            available_pi_ids = [pi.pi_id for pi in online_pis]

            validation = self.scenario_manager.validate_scenario(scenario, available_pi_ids)
            if not validation["valid"]:
                logger.error(f"Scenario validation failed: {validation['errors']}")
                return None

            if validation["warnings"]:
                for warning in validation["warnings"]:
                    logger.warning(f"Scenario validation warning: {warning}")

            # Create execution record
            execution_id = str(uuid.uuid4())
            execution = ScenarioExecutionModel(
                execution_id=execution_id,
                scenario_id=scenario_id,
                scenario_name=scenario.name,
                state="applying",
                total_interfaces=sum(len(pa.interfaces) for pa in scenario.pis)
            )
            db.add(execution)
            db.commit()

            # Create scenario status
            scenario_status = ScenarioStatus(
                scenario_id=scenario_id,
                scenario_name=scenario.name,
                state="applying",
                started_at=datetime.utcnow(),
                total_interfaces=execution.total_interfaces,
                connected_interfaces=0
            )

            self.active_executions[execution_id] = scenario_status

            # Apply configuration to each Pi
            tasks = []
            for pi_assignment in scenario.pis:
                task = self._configure_pi(db, pi_assignment.pi_id, pi_assignment)
                tasks.append(task)

            # Wait for all configurations to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check results
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Scenario application: {success_count}/{len(tasks)} Pis configured successfully")

            # Update execution state
            if success_count == len(tasks):
                execution.state = "running"
                scenario_status.state = "running"
            elif success_count > 0:
                execution.state = "running"
                scenario_status.state = "running"
                scenario_status.error_message = f"Only {success_count}/{len(tasks)} Pis configured"
            else:
                execution.state = "error"
                scenario_status.state = "error"
                scenario_status.error_message = "Failed to configure any Pis"

            db.commit()

            logger.info(f"Scenario {scenario.name} is now {scenario_status.state}")

            return scenario_status

        except Exception as e:
            logger.error(f"Error applying scenario {scenario_id}: {e}")
            return None

    def set_desired_scenario(self, db: Session, scenario_id: str) -> bool:
        """
        Set desired configuration for a scenario (non-blocking, pull-based).

        This method stores the desired configuration for each Pi in the scenario
        and returns immediately. Agents will pull the configuration autonomously.

        Args:
            db: Database session
            scenario_id: Scenario ID to apply

        Returns:
            True if desired config set successfully, False otherwise
        """
        try:
            # Get scenario
            scenario = self.scenario_manager.get_scenario(db, scenario_id)
            if not scenario:
                logger.error(f"Scenario {scenario_id} not found")
                return False

            logger.info(f"Setting desired config for scenario: {scenario.name} ({scenario_id})")

            # Validate scenario
            online_pis = self.pi_manager.get_online_pis(db)
            available_pi_ids = [pi.pi_id for pi in online_pis]

            validation = self.scenario_manager.validate_scenario(scenario, available_pi_ids)
            if not validation["valid"]:
                logger.error(f"Scenario validation failed: {validation['errors']}")
                return False

            if validation["warnings"]:
                for warning in validation["warnings"]:
                    logger.warning(f"Scenario validation warning: {warning}")

            # Store desired configuration for each Pi
            success_count = 0
            for pi_assignment in scenario.pis:
                try:
                    # Convert pi_assignment interfaces to InterfaceConfig
                    interfaces = []
                    for idx, iface in enumerate(pi_assignment.interfaces):
                        # Resolve PSK: prefer explicit password, otherwise PSK set
                        password = iface.password
                        if password is None and iface.psk_set_id:
                            psk_index = iface.psk_index if iface.psk_index is not None else idx
                            password = self.psk_manager.resolve_psk(db, iface.psk_set_id, psk_index)
                            if not password:
                                logger.error(
                                    f"Failed to resolve PSK for interface {iface.name} on Pi {pi_assignment.pi_id} "
                                    f"from PSK set {iface.psk_set_id}"
                                )
                                continue

                        interface_config = InterfaceConfig(
                            name=iface.name,
                            ssid=iface.ssid,
                            password=password,
                            mac_address=iface.mac_address,
                            traffic=iface.traffic,
                            dhcp_personality=iface.dhcp_personality,
                        )
                        interfaces.append(interface_config)

                    # Create agent configuration
                    agent_config = AgentConfiguration(interfaces=interfaces)

                    # Store desired config
                    self.desired_config_manager.set_desired_config(
                        db, pi_assignment.pi_id, agent_config
                    )

                    success_count += 1

                except Exception as e:
                    logger.error(f"Error setting desired config for Pi {pi_assignment.pi_id}: {e}")

            logger.info(
                f"Set desired config for {success_count}/{len(scenario.pis)} Pis in scenario {scenario.name}"
            )

            return success_count > 0

        except Exception as e:
            logger.error(f"Error setting desired scenario {scenario_id}: {e}")
            return False

    async def stop_scenario(self, db: Session, scenario_id: str) -> bool:
        """
        Stop a running scenario.

        Args:
            db: Database session
            scenario_id: Scenario ID to stop

        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            logger.info(f"Stopping scenario: {scenario_id}")

            # Get scenario
            scenario = self.scenario_manager.get_scenario(db, scenario_id)
            if not scenario:
                logger.error(f"Scenario {scenario_id} not found")
                return False

            # Send empty configuration to all Pis in scenario
            tasks = []
            for pi_assignment in scenario.pis:
                task = self._stop_pi(db, pi_assignment.pi_id)
                tasks.append(task)

            # Wait for all to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = sum(1 for r in results if r is True)
            logger.info(f"Scenario stop: {success_count}/{len(tasks)} Pis stopped successfully")

            # Update execution state
            for execution_id, status in self.active_executions.items():
                if status.scenario_id == scenario_id:
                    status.state = "stopped"

            return success_count > 0

        except Exception as e:
            logger.error(f"Error stopping scenario {scenario_id}: {e}")
            return False

    async def get_scenario_status(self, db: Session, scenario_id: str) -> Optional[ScenarioStatus]:
        """
        Get current status of a scenario.

        Args:
            db: Database session
            scenario_id: Scenario ID

        Returns:
            ScenarioStatus or None
        """
        # Check active executions
        for execution_id, status in self.active_executions.items():
            if status.scenario_id == scenario_id:
                # Update with latest Pi statuses
                await self._update_scenario_status(db, status)
                return status

        return None

    async def _configure_pi(self, db: Session, pi_id: str, pi_assignment) -> bool:
        """
        Configure a Pi with its assigned interfaces.

        Args:
            db: Database session
            pi_id: Pi ID
            pi_assignment: Pi assignment from scenario

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get Pi info
            pi_info = self.pi_manager.get_pi(db, pi_id)
            if not pi_info:
                logger.error(f"Pi {pi_id} not found")
                return False

            # Convert pi_assignment interfaces to InterfaceConfig
            interfaces = []
            for idx, iface in enumerate(pi_assignment.interfaces):
                # Resolve PSK: prefer explicit password, otherwise PSK set
                password = iface.password
                if password is None and iface.psk_set_id:
                    psk_index = iface.psk_index if iface.psk_index is not None else idx
                    password = self.psk_manager.resolve_psk(db, iface.psk_set_id, psk_index)
                    if not password:
                        logger.error(
                            f"Failed to resolve PSK for interface {iface.name} on Pi {pi_id} "
                            f"from PSK set {iface.psk_set_id}"
                        )
                        return False

                interface_config = InterfaceConfig(
                    name=iface.name,
                    ssid=iface.ssid,
                    password=password,
                    mac_address=iface.mac_address,
                    traffic=iface.traffic,
                    dhcp_personality=iface.dhcp_personality,
                )
                interfaces.append(interface_config)

            # Create agent configuration
            agent_config = AgentConfiguration(interfaces=interfaces)

            # Send configuration to Pi
            pi_url = f"http://{pi_info.ip_address}:8080"

            async with aiohttp.ClientSession() as session:
                # Step 1: Send configuration
                logger.info(f"Sending configuration to {pi_id} ({pi_url})")
                async with session.post(
                    f"{pi_url}/configure",
                    json=agent_config.model_dump(),
                    timeout=aiohttp.ClientTimeout(total=self.configure_timeout)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to configure {pi_id}: HTTP {response.status}")
                        return False

                # Step 2: Apply configuration
                logger.info(f"Applying configuration on {pi_id}")
                async with session.post(
                    f"{pi_url}/apply",
                    timeout=aiohttp.ClientTimeout(total=self.apply_timeout)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to apply configuration on {pi_id}: HTTP {response.status}")
                        return False

                logger.info(f"Successfully configured {pi_id} with {len(interfaces)} interfaces")
                return True

        except aiohttp.ClientError as e:
            logger.error(f"Network error configuring {pi_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error configuring {pi_id}: {e}")
            return False

    async def _stop_pi(self, db: Session, pi_id: str) -> bool:
        """
        Stop all interfaces on a Pi.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get Pi info
            pi_info = self.pi_manager.get_pi(db, pi_id)
            if not pi_info:
                logger.error(f"Pi {pi_id} not found")
                return False

            # Send empty configuration
            agent_config = AgentConfiguration(interfaces=[])
            pi_url = f"http://{pi_info.ip_address}:8080"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{pi_url}/configure",
                    json=agent_config.model_dump(),
                    timeout=aiohttp.ClientTimeout(total=self.configure_timeout)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to send stop config to {pi_id}")
                        return False

                async with session.post(
                    f"{pi_url}/apply",
                    timeout=aiohttp.ClientTimeout(total=self.stop_timeout)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to apply stop config on {pi_id}")
                        return False

                logger.info(f"Successfully stopped {pi_id}")
                return True

        except Exception as e:
            logger.error(f"Error stopping {pi_id}: {e}")
            return False

    async def _update_scenario_status(self, db: Session, scenario_status: ScenarioStatus) -> None:
        """Update scenario status with latest Pi statuses"""
        try:
            # Get scenario
            scenario = self.scenario_manager.get_scenario(db, scenario_status.scenario_id)
            if not scenario:
                return

            # Collect status from all Pis
            pi_statuses = {}
            connected_count = 0

            for pi_assignment in scenario.pis:
                try:
                    pi_info = self.pi_manager.get_pi(db, pi_assignment.pi_id)
                    if not pi_info:
                        continue

                    pi_url = f"http://{pi_info.ip_address}:8080"

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{pi_url}/status",
                            timeout=aiohttp.ClientTimeout(total=self.status_timeout)
                        ) as response:
                            if response.status == 200:
                                status_data = await response.json()
                                agent_status = AgentStatus(**status_data)
                                pi_statuses[pi_assignment.pi_id] = agent_status

                                # Count connected interfaces
                                for iface in agent_status.interfaces:
                                    if iface.state == "connected":
                                        connected_count += 1

                except Exception as e:
                    logger.warning(f"Could not get status from {pi_assignment.pi_id}: {e}")

            scenario_status.pi_statuses = pi_statuses
            scenario_status.connected_interfaces = connected_count

        except Exception as e:
            logger.error(f"Error updating scenario status: {e}")
