"""
Database models for controller.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import relationship
from ..db.database import Base


class PiModel(Base):
    """Pi registration and tracking model"""
    __tablename__ = "pis"

    id = Column(Integer, primary_key=True, index=True)
    pi_id = Column(String, unique=True, index=True, nullable=False)
    agent_id = Column(String, nullable=False)
    hostname = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    capabilities = Column(Text, default="{}")  # JSON string
    version = Column(String, default="1.0.0")
    status = Column(String, default="online")  # online, offline, error
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ScenarioModel(Base):
    """Scenario storage model"""
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    definition = Column(Text, nullable=False)  # JSON string of scenario
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ScenarioExecutionModel(Base):
    """Track scenario execution history"""
    __tablename__ = "scenario_executions"

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String, unique=True, index=True, nullable=False)
    scenario_id = Column(String, nullable=False)
    scenario_name = Column(String, nullable=False)
    state = Column(String, default="applying")  # applying, running, stopping, stopped, error
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    stopped_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    total_interfaces = Column(Integer, default=0)
    connected_interfaces = Column(Integer, default=0)


class RuckusOneConfigModel(Base):
    """Ruckus One API configuration (persistent storage)"""
    __tablename__ = "ruckus_one_config"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False)
    client_id = Column(String, nullable=False)
    client_secret = Column(String, nullable=True)  # Legacy plaintext field (deprecated)
    client_secret_encrypted = Column(String, nullable=True)  # Encrypted client secret (preferred)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def get_client_secret(self, encryption_service) -> str:
        """
        Get decrypted client secret.

        Prefers encrypted field, falls back to plaintext for backward compatibility.

        Args:
            encryption_service: EncryptionService instance

        Returns:
            Decrypted client secret
        """
        if self.client_secret_encrypted:
            return encryption_service.try_decrypt(self.client_secret_encrypted)
        else:
            # Legacy plaintext field
            return self.client_secret or ""

    def set_client_secret(self, plaintext: str, encryption_service):
        """
        Set client secret with encryption.

        Args:
            plaintext: Plaintext client secret
            encryption_service: EncryptionService instance
        """
        if encryption_service.is_enabled():
            # Encrypt and store in encrypted field
            self.client_secret_encrypted = encryption_service.encrypt(plaintext)
            self.client_secret = None  # Clear legacy field
        else:
            # Store in plaintext (encryption disabled)
            self.client_secret = plaintext
            self.client_secret_encrypted = None


class DesiredConfigurationModel(Base):
    """Stores desired configuration per Pi for pull-based architecture"""
    __tablename__ = "desired_configurations"

    id = Column(Integer, primary_key=True, index=True)
    pi_id = Column(String, unique=True, index=True, nullable=False)
    config_hash = Column(String, nullable=False)  # SHA256 of config JSON
    config_json = Column(Text, nullable=False)    # AgentConfiguration as JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DetectionSnapshotModel(Base):
    """Time-series snapshot of Ruckus One detection accuracy.

    One row per personality per sample, plus a "__overall__" row for the fleet
    total. Lets us distinguish R1 cloud lag (transient not_detected) from genuine
    mis-fingerprinting (sustained detected_incorrectly) over time.
    """
    __tablename__ = "detection_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    personality = Column(String, nullable=False, index=True)  # "__overall__" = fleet total
    total = Column(Integer, default=0, nullable=False)
    detected_correctly = Column(Integer, default=0, nullable=False)
    detected_incorrectly = Column(Integer, default=0, nullable=False)
    not_detected = Column(Integer, default=0, nullable=False)
    detected_as = Column(Text, default="{}")  # JSON {osType: count}


class ResidentSimulationConfigModel(Base):
    """Persist resident simulation configuration"""
    __tablename__ = "resident_simulation_config"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=False, nullable=False)
    psk_set_id = Column(String, nullable=True)
    target_active_apartments = Column(Integer, default=64, nullable=False)
    rotation_hours = Column(Float, default=6.0, nullable=False)
    max_interfaces_per_pi = Column(Integer, default=8, nullable=False)
    last_rotation_at = Column(DateTime, nullable=True)
    next_rotation_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
