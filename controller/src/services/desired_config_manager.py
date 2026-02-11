"""
Desired Configuration Manager - Stores desired state for pull-based architecture.
"""
import hashlib
import json
import logging
from typing import Optional, Dict

from sqlalchemy.orm import Session

from shared.models import AgentConfiguration
from ..models import DesiredConfigurationModel

logger = logging.getLogger(__name__)


class DesiredConfigManager:
    """Manages desired configuration state for agents (pull-based architecture)"""

    def set_desired_config(self, db: Session, pi_id: str, config: AgentConfiguration) -> str:
        """
        Store desired configuration for a Pi and compute hash.

        Args:
            db: Database session
            pi_id: Pi ID
            config: Agent configuration to store

        Returns:
            Configuration hash (SHA256)
        """
        try:
            # Serialize config to JSON (deterministic order for consistent hashing)
            config_dict = config.model_dump()
            config_json = json.dumps(config_dict, sort_keys=True)

            # Compute hash
            config_hash = hashlib.sha256(config_json.encode()).hexdigest()

            # Store or update in database
            existing = db.query(DesiredConfigurationModel).filter(
                DesiredConfigurationModel.pi_id == pi_id
            ).first()

            if existing:
                existing.config_hash = config_hash
                existing.config_json = config_json
            else:
                new_config = DesiredConfigurationModel(
                    pi_id=pi_id,
                    config_hash=config_hash,
                    config_json=config_json
                )
                db.add(new_config)

            db.commit()

            logger.info(f"Set desired config for {pi_id}: hash={config_hash[:8]}...")

            return config_hash

        except Exception as e:
            logger.error(f"Error setting desired config for {pi_id}: {e}")
            db.rollback()
            raise

    def get_desired_config(self, db: Session, pi_id: str) -> Optional[Dict]:
        """
        Retrieve desired configuration for a Pi.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            Dict with 'config' (AgentConfiguration dict) and 'hash', or None if not found
        """
        try:
            config_model = db.query(DesiredConfigurationModel).filter(
                DesiredConfigurationModel.pi_id == pi_id
            ).first()

            if not config_model:
                return None

            config_dict = json.loads(config_model.config_json)

            return {
                "config": config_dict,
                "hash": config_model.config_hash
            }

        except Exception as e:
            logger.error(f"Error getting desired config for {pi_id}: {e}")
            return None

    def get_config_hash(self, db: Session, pi_id: str) -> Optional[str]:
        """
        Get configuration hash without loading full config.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            Configuration hash or None if not found
        """
        try:
            config_model = db.query(DesiredConfigurationModel).filter(
                DesiredConfigurationModel.pi_id == pi_id
            ).first()

            return config_model.config_hash if config_model else None

        except Exception as e:
            logger.error(f"Error getting config hash for {pi_id}: {e}")
            return None

    def delete_desired_config(self, db: Session, pi_id: str) -> bool:
        """
        Delete desired configuration for a Pi.

        Args:
            db: Database session
            pi_id: Pi ID

        Returns:
            True if deleted, False if not found
        """
        try:
            config_model = db.query(DesiredConfigurationModel).filter(
                DesiredConfigurationModel.pi_id == pi_id
            ).first()

            if not config_model:
                return False

            db.delete(config_model)
            db.commit()

            logger.info(f"Deleted desired config for {pi_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting desired config for {pi_id}: {e}")
            db.rollback()
            return False
