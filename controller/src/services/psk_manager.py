"""
PSK Manager Service - Manages reusable PSK sets for scenarios.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict

from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Text

from ..db.database import Base
from .encryption import get_encryption_service

logger = logging.getLogger(__name__)


class PskSetModel(Base):
    """PSK set storage model"""
    __tablename__ = "psk_sets"

    id = Column(Integer, primary_key=True, index=True)
    psk_set_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    ssid = Column(String, nullable=False)
    description = Column(Text, default="")
    psk_list = Column(Text, nullable=True)  # Legacy plaintext JSON field (deprecated)
    psk_list_encrypted = Column(Text, nullable=True)  # Encrypted JSON list of PSKs (preferred)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def get_psk_list_json(self, encryption_service) -> str:
        """
        Get decrypted PSK list as JSON string.

        Prefers encrypted field, falls back to plaintext for backward compatibility.

        Args:
            encryption_service: EncryptionService instance

        Returns:
            JSON string of PSK list
        """
        if self.psk_list_encrypted:
            return encryption_service.try_decrypt(self.psk_list_encrypted)
        else:
            # Legacy plaintext field
            return self.psk_list or "[]"

    def set_psk_list_json(self, psk_list_json: str, encryption_service):
        """
        Set PSK list from JSON string with encryption.

        Args:
            psk_list_json: JSON string of PSK list
            encryption_service: EncryptionService instance
        """
        if encryption_service.is_enabled():
            # Encrypt and store in encrypted field
            self.psk_list_encrypted = encryption_service.encrypt(psk_list_json)
            self.psk_list = None  # Clear legacy field
        else:
            # Store in plaintext (encryption disabled)
            self.psk_list = psk_list_json
            self.psk_list_encrypted = None


class PskSet:
    """In-memory PSK set representation"""

    def __init__(
        self,
        psk_set_id: str,
        name: str,
        ssid: str,
        description: str,
        psks: List[str],
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = psk_set_id
        self.name = name
        self.ssid = ssid
        self.description = description
        self.psks = psks
        self.created_at = created_at
        self.updated_at = updated_at


class PskManager:
    """Manages PSK sets used by scenarios"""

    def __init__(self):
        logger.info("PskManager initialized")

    def create_psk_set(
        self,
        db: Session,
        psk_set_id: str,
        name: str,
        ssid: str,
        description: str,
        psks: List[str],
    ) -> PskSet:
        """Create a new PSK set (encrypts PSKs if encryption enabled)."""
        try:
            existing = db.query(PskSetModel).filter(PskSetModel.psk_set_id == psk_set_id).first()
            if existing:
                raise ValueError(f"PSK set with ID {psk_set_id} already exists")

            encryption_service = get_encryption_service()
            model = PskSetModel(
                psk_set_id=psk_set_id,
                name=name,
                ssid=ssid,
                description=description,
            )
            # Use encryption-aware setter
            model.set_psk_list_json(json.dumps(psks), encryption_service)

            db.add(model)
            db.commit()
            db.refresh(model)

            logger.info(f"Created PSK set {psk_set_id} ({name}) for SSID {ssid} (encrypted: {encryption_service.is_enabled()})")
            return self._model_to_psk_set(model)
        except Exception as e:
            logger.error(f"Error creating PSK set {psk_set_id}: {e}")
            db.rollback()
            raise

    def update_psk_set(
        self,
        db: Session,
        psk_set_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        psks: Optional[List[str]] = None,
    ) -> Optional[PskSet]:
        """Update an existing PSK set (encrypts PSKs if encryption enabled)."""
        try:
            model = db.query(PskSetModel).filter(PskSetModel.psk_set_id == psk_set_id).first()
            if not model:
                return None

            if name is not None:
                model.name = name
            if description is not None:
                model.description = description
            if psks is not None:
                encryption_service = get_encryption_service()
                model.set_psk_list_json(json.dumps(psks), encryption_service)

            db.commit()
            db.refresh(model)

            logger.info(f"Updated PSK set {psk_set_id}")
            return self._model_to_psk_set(model)
        except Exception as e:
            logger.error(f"Error updating PSK set {psk_set_id}: {e}")
            db.rollback()
            raise

    def delete_psk_set(self, db: Session, psk_set_id: str) -> bool:
        """Delete a PSK set."""
        try:
            model = db.query(PskSetModel).filter(PskSetModel.psk_set_id == psk_set_id).first()
            if not model:
                return False

            db.delete(model)
            db.commit()

            logger.info(f"Deleted PSK set {psk_set_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting PSK set {psk_set_id}: {e}")
            db.rollback()
            return False

    def get_psk_set(self, db: Session, psk_set_id: str) -> Optional[PskSet]:
        """Get a PSK set by ID."""
        model = db.query(PskSetModel).filter(PskSetModel.psk_set_id == psk_set_id).first()
        if not model:
            return None
        return self._model_to_psk_set(model)

    def list_psk_sets(self, db: Session) -> List[PskSet]:
        """List all PSK sets."""
        models = db.query(PskSetModel).all()
        return [self._model_to_psk_set(m) for m in models]

    def resolve_psk(
        self,
        db: Session,
        psk_set_id: str,
        index: Optional[int] = None,
    ) -> Optional[str]:
        """
        Resolve a concrete PSK from a PSK set.

        If index is provided, wraps around the list. If not, returns the first PSK.
        """
        psk_set = self.get_psk_set(db, psk_set_id)
        if not psk_set or not psk_set.psks:
            logger.error(f"PSK set {psk_set_id} not found or empty")
            return None

        if index is None:
            return psk_set.psks[0]

        try:
            return psk_set.psks[index % len(psk_set.psks)]
        except Exception as e:
            logger.error(f"Error resolving PSK from set {psk_set_id} with index {index}: {e}")
            return None

    def _model_to_psk_set(self, model: PskSetModel) -> PskSet:
        """Convert DB model to PskSet (decrypts PSKs if encrypted)."""
        try:
            encryption_service = get_encryption_service()
            psk_list_json = model.get_psk_list_json(encryption_service)
            psks = json.loads(psk_list_json) if psk_list_json else []
        except json.JSONDecodeError:
            psks = []

        return PskSet(
            psk_set_id=model.psk_set_id,
            name=model.name,
            ssid=model.ssid,
            description=model.description,
            psks=psks,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

