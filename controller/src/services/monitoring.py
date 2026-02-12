"""
Monitoring Service - Polls Pi fleet and aggregates status.
"""
import asyncio
import logging
from typing import Dict
import aiohttp
from sqlalchemy.orm import Session

from shared.models import AgentStatus
from .pi_manager import PiManager

logger = logging.getLogger(__name__)


class MonitoringService:
    """Background monitoring service for Pi fleet"""

    def __init__(self, pi_manager: PiManager, poll_interval: int = 10, poll_timeout: int = 5):
        """
        Initialize Monitoring Service.

        Args:
            pi_manager: Pi Manager instance
            poll_interval: Polling interval in seconds
        """
        self.pi_manager = pi_manager
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.running = False
        self.monitoring_task: asyncio.Task = None
        self.latest_statuses: Dict[str, AgentStatus] = {}
        self.failure_counts: Dict[str, int] = {}  # Track consecutive failures per Pi
        self.max_failures = 3  # Mark offline after 3 consecutive failures
        logger.info(f"MonitoringService initialized with poll_interval: {poll_interval}s, poll_timeout: {poll_timeout}s")

    async def start(self, db_session_maker):
        """
        Start the monitoring service.

        Args:
            db_session_maker: Database session maker for creating sessions
        """
        if self.running:
            logger.warning("Monitoring service already running")
            return

        self.running = True
        self.db_session_maker = db_session_maker
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Monitoring service started")

    async def stop(self):
        """Stop the monitoring service"""
        if not self.running:
            return

        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Monitoring service stopped")

    def get_latest_status(self, pi_id: str) -> AgentStatus:
        """
        Get latest cached status for a Pi.

        Args:
            pi_id: Pi ID

        Returns:
            AgentStatus or None
        """
        return self.latest_statuses.get(pi_id)

    def get_all_statuses(self) -> Dict[str, AgentStatus]:
        """Get all latest statuses"""
        return self.latest_statuses.copy()

    def _get_agent_url(self, db: Session, pi_id: str, ip_address: str) -> str:
        """
        Get agent URL with port from capabilities.

        Args:
            db: Database session
            pi_id: Pi ID
            ip_address: Pi IP address

        Returns:
            str: Agent URL (e.g., "http://172.16.254.147:8080")
        """
        import json

        # Default port fallback
        port = 8080

        # Try to get port from Pi capabilities in database
        try:
            pi_info = self.pi_manager.get_pi(db, pi_id)
            if pi_info and pi_info.capabilities:
                # Capabilities is stored as JSON string in database
                caps = json.loads(pi_info.capabilities) if isinstance(pi_info.capabilities, str) else pi_info.capabilities
                port = caps.get("api_port", 8080)
        except (json.JSONDecodeError, AttributeError, TypeError):
            # Fall back to default if parsing fails or Pi not found
            logger.debug(f"Could not get port from capabilities for {pi_id}, using default 8080")

        return f"http://{ip_address}:{port}"

    def _handle_pi_failure(self, db: Session, pi_id: str):
        """
        Handle a failed poll attempt for a Pi.

        Args:
            db: Database session
            pi_id: Pi ID that failed to respond
        """
        # Increment failure count
        self.failure_counts[pi_id] = self.failure_counts.get(pi_id, 0) + 1

        # Mark offline after consecutive failures
        if self.failure_counts[pi_id] >= self.max_failures:
            logger.warning(f"Marking {pi_id} as offline after {self.failure_counts[pi_id]} consecutive failures")
            self.pi_manager.mark_pi_offline(db, pi_id)

            # Remove from cache
            if pi_id in self.latest_statuses:
                del self.latest_statuses[pi_id]

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Monitoring loop started")

        while self.running:
            try:
                await self._poll_all_pis()
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _poll_all_pis(self):
        """Poll all online Pis for status"""
        try:
            # Create database session
            db = self.db_session_maker()

            try:
                # Get online Pis
                online_pis = self.pi_manager.get_online_pis(db)

                if not online_pis:
                    logger.debug("No online Pis to poll")
                    return

                logger.debug(f"Polling {len(online_pis)} Pis")

                # Poll all Pis concurrently
                tasks = [self._poll_pi(db, pi.pi_id, pi.ip_address) for pi in online_pis]
                await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error polling Pis: {e}")

    async def _poll_pi(self, db: Session, pi_id: str, ip_address: str):
        """
        Poll a single Pi for status.

        Args:
            db: Database session
            pi_id: Pi ID
            ip_address: Pi IP address
        """
        try:
            # Get agent URL with port from capabilities
            pi_url = self._get_agent_url(db, pi_id, ip_address)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{pi_url}/status",
                    timeout=aiohttp.ClientTimeout(total=self.poll_timeout)
                ) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        agent_status = AgentStatus(**status_data)

                        # Update cache
                        self.latest_statuses[pi_id] = agent_status

                        # Reset failure count on success
                        self.failure_counts[pi_id] = 0

                        # Update heartbeat and capabilities
                        self.pi_manager.update_pi_heartbeat(
                            db,
                            pi_id,
                            capabilities=agent_status.capabilities
                        )

                        logger.debug(
                            f"Polled {pi_id}: {len(agent_status.interfaces)} interfaces, "
                            f"CPU: {agent_status.system.cpu_percent:.1f}%"
                        )
                    else:
                        logger.warning(f"Failed to poll {pi_id}: HTTP {response.status}")
                        self._handle_pi_failure(db, pi_id)

        except aiohttp.ClientError as e:
            logger.warning(f"Network error polling {pi_id}: {e}")
            self._handle_pi_failure(db, pi_id)
        except Exception as e:
            logger.error(f"Error polling {pi_id}: {e}")
            self._handle_pi_failure(db, pi_id)
