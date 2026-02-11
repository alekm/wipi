"""
Pi Manager Service - Manages the Pi fleet.
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from shared.models import PiRegistration, PiInfo, AgentStatus
from ..models import PiModel

logger = logging.getLogger(__name__)


class PiManager:
    """Manages Pi registration and tracking"""

    def __init__(self):
        """Initialize Pi Manager"""
        self.pi_timeout_seconds = 60  # Consider Pi offline after 60 seconds
        logger.info("PiManager initialized")

    def register_pi(self, db: Session, registration: PiRegistration) -> PiInfo:
        """
        Register or update a Pi.

        Args:
            db: Database session
            registration: Pi registration data

        Returns:
            PiInfo object
        """
        try:
            # Check if Pi already exists
            pi = db.query(PiModel).filter(PiModel.pi_id == registration.agent_id).first()

            if pi:
                # Update existing Pi
                logger.info(f"Updating existing Pi: {registration.agent_id}")
                pi.agent_id = registration.agent_id
                pi.hostname = registration.hostname
                pi.ip_address = registration.ip_address
                pi.capabilities = json.dumps(registration.capabilities)
                pi.version = registration.version
                pi.status = "online"
                pi.last_seen = datetime.utcnow()
                pi.updated_at = datetime.utcnow()
            else:
                # Create new Pi
                logger.info(f"Registering new Pi: {registration.agent_id}")
                pi = PiModel(
                    pi_id=registration.agent_id,
                    agent_id=registration.agent_id,
                    hostname=registration.hostname,
                    ip_address=registration.ip_address,
                    capabilities=json.dumps(registration.capabilities),
                    version=registration.version,
                    status="online",
                    last_seen=datetime.utcnow()
                )
                db.add(pi)

            db.commit()
            db.refresh(pi)

            return self._pi_model_to_info(pi)

        except Exception as e:
            logger.error(f"Error registering Pi {registration.agent_id}: {e}")
            db.rollback()
            raise

    def get_pi(self, db: Session, pi_id: str) -> Optional[PiInfo]:
        """
        Get a Pi by ID.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            PiInfo object or None
        """
        pi = db.query(PiModel).filter(PiModel.pi_id == pi_id).first()
        if pi:
            return self._pi_model_to_info(pi)
        return None

    def get_all_pis(self, db: Session) -> List[PiInfo]:
        """
        Get all registered Pis.

        Args:
            db: Database session

        Returns:
            List of PiInfo objects
        """
        pis = db.query(PiModel).all()
        return [self._pi_model_to_info(pi) for pi in pis]

    def get_online_pis(self, db: Session) -> List[PiInfo]:
        """
        Get all online Pis.

        Returns Pis that are either:
        1. Recently seen (last_seen within timeout period), OR
        2. Explicitly marked as online (allows monitoring to revive stale Pis)

        Args:
            db: Database session

        Returns:
            List of PiInfo objects
        """
        cutoff = datetime.utcnow() - timedelta(seconds=self.pi_timeout_seconds)
        pis = db.query(PiModel).filter(
            # Include Pis that are recently seen OR explicitly marked online
            (PiModel.last_seen >= cutoff) | (PiModel.status == "online")
        ).all()
        return [self._pi_model_to_info(pi) for pi in pis]

    def update_pi_heartbeat(self, db: Session, pi_id: str, capabilities: Optional[Dict] = None) -> bool:
        """
        Update Pi heartbeat timestamp and optionally capabilities.

        Args:
            db: Database session
            pi_id: Pi ID
            capabilities: Optional capabilities dict to update

        Returns:
            True if updated, False otherwise
        """
        try:
            pi = db.query(PiModel).filter(PiModel.pi_id == pi_id).first()
            if pi:
                pi.last_seen = datetime.utcnow()
                pi.status = "online"
                if capabilities is not None:
                    pi.capabilities = json.dumps(capabilities)
                db.commit()
                return True
            return False

        except Exception as e:
            logger.error(f"Error updating heartbeat for {pi_id}: {e}")
            db.rollback()
            return False

    def mark_pi_offline(self, db: Session, pi_id: str) -> bool:
        """
        Mark a Pi as offline.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            True if updated, False otherwise
        """
        try:
            pi = db.query(PiModel).filter(PiModel.pi_id == pi_id).first()
            if pi:
                pi.status = "offline"
                db.commit()
                logger.info(f"Marked Pi {pi_id} as offline")
                return True
            return False

        except Exception as e:
            logger.error(f"Error marking Pi {pi_id} offline: {e}")
            db.rollback()
            return False

    def check_and_update_pi_status(self, db: Session) -> None:
        """
        Check all Pis and update their status based on last_seen.

        Args:
            db: Database session
        """
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=self.pi_timeout_seconds)

            # Get all Pis that haven't been seen recently
            stale_pis = db.query(PiModel).filter(
                PiModel.last_seen < cutoff,
                PiModel.status == "online"
            ).all()

            for pi in stale_pis:
                logger.warning(f"Pi {pi.pi_id} has not been seen since {pi.last_seen}, marking offline")
                pi.status = "offline"

            if stale_pis:
                db.commit()

        except Exception as e:
            logger.error(f"Error checking Pi status: {e}")
            db.rollback()

    def delete_pi(self, db: Session, pi_id: str) -> bool:
        """
        Delete a Pi from the database.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            pi = db.query(PiModel).filter(PiModel.pi_id == pi_id).first()
            if pi:
                db.delete(pi)
                db.commit()
                logger.info(f"Deleted Pi {pi_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error deleting Pi {pi_id}: {e}")
            db.rollback()
            return False

    def _pi_model_to_info(self, pi: PiModel) -> PiInfo:
        """Convert database model to PiInfo"""
        try:
            capabilities = json.loads(pi.capabilities) if pi.capabilities else {}
        except json.JSONDecodeError:
            capabilities = {}

        return PiInfo(
            pi_id=pi.pi_id,
            agent_id=pi.agent_id,
            hostname=pi.hostname,
            ip_address=pi.ip_address,
            capabilities=capabilities,
            version=pi.version,
            last_seen=pi.last_seen,
            status=pi.status
        )
