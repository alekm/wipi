"""
Ruckus One Integration API Endpoints
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..services.ruckus_one import RuckusOneClient, RuckusOneMonitor
from ..services.monitoring import MonitoringService
from ..services.audit_log import audit_log
from ..services.encryption import get_encryption_service
from ..db import get_db
from ..models.db_models import RuckusOneConfigModel
from ..middleware.auth import require_auth
from ..services.session_manager import Session as AuthSession

logger = logging.getLogger(__name__)

router = APIRouter()

# Global R1 client (initialized on first use)
_r1_client: Optional[RuckusOneClient] = None
_r1_monitor: Optional[RuckusOneMonitor] = None
_r1_config: Optional[dict] = None


def _load_config_from_db(db: Session) -> Optional[dict]:
    """Load R1 config from database (decrypts client_secret if encrypted)"""
    config = db.query(RuckusOneConfigModel).first()
    if config:
        encryption_service = get_encryption_service()
        return {
            "tenant_id": config.tenant_id,
            "client_id": config.client_id,
            "client_secret": config.get_client_secret(encryption_service),
            "enabled": config.enabled
        }
    return None


def _save_config_to_db(db: Session, config_dict: dict):
    """Save R1 config to database (encrypts client_secret if encryption enabled)"""
    encryption_service = get_encryption_service()

    # Check if config exists
    existing = db.query(RuckusOneConfigModel).first()

    if existing:
        # Update existing
        existing.tenant_id = config_dict["tenant_id"]
        existing.client_id = config_dict["client_id"]
        existing.set_client_secret(config_dict["client_secret"], encryption_service)
        existing.enabled = config_dict.get("enabled", True)
    else:
        # Create new
        new_config = RuckusOneConfigModel(
            tenant_id=config_dict["tenant_id"],
            client_id=config_dict["client_id"],
            enabled=config_dict.get("enabled", True)
        )
        new_config.set_client_secret(config_dict["client_secret"], encryption_service)
        db.add(new_config)

    db.commit()


class RuckusOneConfig(BaseModel):
    """Ruckus One API configuration"""
    tenant_id: str
    client_id: str
    client_secret: str
    enabled: bool = True


def get_r1_monitor(db: Session = None) -> Optional[RuckusOneMonitor]:
    """Get or create Ruckus One monitor instance"""
    global _r1_client, _r1_monitor, _r1_config

    # Try to load config from database if not in memory
    if not _r1_config and db:
        _r1_config = _load_config_from_db(db)

    # If not configured, return None
    if not _r1_config or not _r1_config.get("enabled"):
        return None

    # Create client and monitor if needed
    if not _r1_client:
        # Import Config here to avoid circular import
        from ..main import Config

        _r1_client = RuckusOneClient(
            tenant_id=_r1_config["tenant_id"],
            client_id=_r1_config["client_id"],
            client_secret=_r1_config["client_secret"],
            api_timeout=Config.ruckus_one_api_timeout
        )
        _r1_monitor = RuckusOneMonitor(_r1_client)

    return _r1_monitor


@router.post("/config")
async def configure_ruckus_one(
    config: RuckusOneConfig,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
):
    """Configure Ruckus One API credentials (persisted to database)"""
    global _r1_client, _r1_monitor, _r1_config

    try:
        config_dict = config.dict()

        # Save to database for persistence
        _save_config_to_db(db, config_dict)

        # Update in-memory config
        _r1_config = config_dict

        # Reset client and monitor to force recreation with new credentials
        _r1_client = None
        _r1_monitor = None

        logger.info(f"Ruckus One API configured and saved (enabled: {config.enabled})")

        # Audit log configuration change
        audit_log.log_ruckus_one_config(
            enabled=config.enabled,
            tenant_id=config.tenant_id,
            success=True
        )

        return {"status": "configured", "enabled": config.enabled, "persisted": True}

    except Exception as e:
        # Audit log configuration failure
        audit_log.log_ruckus_one_config(
            enabled=config.enabled,
            tenant_id=config.tenant_id,
            success=False,
            error=str(e)
        )
        raise


@router.get("/config")
async def get_ruckus_one_config(db: Session = Depends(get_db)):
    """Get current Ruckus One configuration (without secrets)"""
    global _r1_config

    # Load from database if not in memory
    if not _r1_config:
        _r1_config = _load_config_from_db(db)

    if not _r1_config:
        return {"enabled": False, "configured": False}

    return {
        "enabled": _r1_config.get("enabled", False),
        "tenant_id": _r1_config.get("tenant_id"),
        "client_id": _r1_config.get("client_id"),
        "configured": True
    }


@router.get("/status")
async def get_ruckus_one_status(request: Request, db: Session = Depends(get_db)):
    """
    Get correlated status showing WiPi interfaces matched with Ruckus One detection.
    """
    monitor = get_r1_monitor(db)

    if not monitor:
        raise HTTPException(status_code=503, detail="Ruckus One not configured")

    try:
        # Get monitoring service from app state
        monitoring_service = request.app.state.monitoring

        if not monitoring_service:
            raise HTTPException(status_code=503, detail="Monitoring service not available")

        # Get all Pi statuses with interface details
        pi_statuses = monitoring_service.get_all_statuses()

        # Extract all interfaces from all Pis
        all_interfaces = []
        for pi_id, pi_status in pi_statuses.items():
            # Convert AgentStatus to dict if needed
            if hasattr(pi_status, 'dict'):
                pi_status_dict = pi_status.dict()
            else:
                pi_status_dict = pi_status

            interfaces = pi_status_dict.get("interfaces", [])
            for iface in interfaces:
                # Add pi_id to interface data
                iface_with_pi = iface.copy()
                iface_with_pi["pi_id"] = pi_id
                all_interfaces.append(iface_with_pi)

        # Get correlated status
        result = monitor.get_correlated_status(all_interfaces)

        return result

    except Exception as e:
        logger.error(f"Error getting Ruckus One status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_detection_history(hours: int = 24, db: Session = Depends(get_db)):
    """Aggregated detection-accuracy time series from persisted snapshots.

    Returns per-personality and overall accuracy averaged over the window, so
    transient R1 cloud lag can be separated from sustained mis-detection.
    """
    from datetime import datetime, timedelta
    from ..models.db_models import DetectionSnapshotModel

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(DetectionSnapshotModel)
        .filter(DetectionSnapshotModel.timestamp >= cutoff)
        .order_by(DetectionSnapshotModel.timestamp.asc())
        .all()
    )

    by_personality: dict = {}
    samples = 0
    seen_ts = set()
    for r in rows:
        seen_ts.add(r.timestamp)
        agg = by_personality.setdefault(r.personality, {
            "total": 0, "detected_correctly": 0,
            "detected_incorrectly": 0, "not_detected": 0,
        })
        agg["total"] += r.total
        agg["detected_correctly"] += r.detected_correctly
        agg["detected_incorrectly"] += r.detected_incorrectly
        agg["not_detected"] += r.not_detected

    for agg in by_personality.values():
        t = agg["total"] or 1
        agg["accuracy"] = round(agg["detected_correctly"] / t, 3)
        agg["detection_rate"] = round((t - agg["not_detected"]) / t, 3)

    return {
        "window_hours": hours,
        "samples": len(seen_ts),
        "overall": by_personality.get("__overall__", {}),
        "by_personality": {k: v for k, v in by_personality.items() if k != "__overall__"},
    }


@router.get("/clients")
async def get_ruckus_one_clients(db: Session = Depends(get_db)):
    """Get raw client list from Ruckus One API"""
    monitor = get_r1_monitor(db)

    if not monitor:
        raise HTTPException(status_code=503, detail="Ruckus One not configured")

    try:
        clients = monitor.r1_client.get_clients()
        return {"clients": clients, "count": len(clients)}

    except Exception as e:
        logger.error(f"Error getting Ruckus One clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))
