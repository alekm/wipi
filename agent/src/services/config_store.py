"""
Config Store - Persists agent configuration to disk for recovery after restarts.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class ConfigStore:
    """Handles persistence of agent configuration to local filesystem"""

    def __init__(self, config_file: str = "/etc/wipi/current_config.json"):
        """
        Initialize config store.

        Args:
            config_file: Path to store configuration file
        """
        self.config_file = Path(config_file)
        self.config_dir = self.config_file.parent

        # Ensure directory exists
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create config directory {self.config_dir}: {e}")

    def save_config(self, config: Dict, config_hash: str) -> bool:
        """
        Save configuration to disk.

        Args:
            config: Configuration dictionary (AgentConfiguration)
            config_hash: SHA256 hash of the configuration

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            data = {
                "config": config,
                "hash": config_hash
            }

            # Write atomically using temp file
            temp_file = self.config_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_file.replace(self.config_file)

            logger.info(f"Saved config to disk: {config_hash[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to save config to disk: {e}")
            return False

    def load_config(self) -> Optional[Dict]:
        """
        Load configuration from disk.

        Returns:
            Dict with 'config' and 'hash', or None if not found
        """
        try:
            if not self.config_file.exists():
                logger.debug(f"No config file found at {self.config_file}")
                return None

            with open(self.config_file, 'r') as f:
                data = json.load(f)

            logger.info(f"Loaded config from disk: {data['hash'][:8]}...")
            return data

        except Exception as e:
            logger.error(f"Failed to load config from disk: {e}")
            return None

    def get_current_hash(self) -> Optional[str]:
        """
        Get current config hash without loading full config.

        Returns:
            Config hash or None if not found
        """
        try:
            if not self.config_file.exists():
                return None

            with open(self.config_file, 'r') as f:
                data = json.load(f)

            return data.get('hash')

        except Exception as e:
            logger.error(f"Failed to get current hash: {e}")
            return None

    def clear_config(self) -> bool:
        """
        Remove stored configuration.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if self.config_file.exists():
                self.config_file.unlink()
                logger.info("Cleared stored config")
            return True

        except Exception as e:
            logger.error(f"Failed to clear config: {e}")
            return False
