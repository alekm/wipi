"""
Pi management API endpoints.
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from shared.models import PiRegistration, PiInfo, SuccessResponse
from ..db import get_db
from ..services import PiManager
from ..services.audit_log import audit_log
from ..middleware.auth import require_auth, require_agent_key
from ..services.session_manager import Session as AuthSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pis", tags=["Pis"])


@router.post("/register", response_model=PiInfo)
async def register_pi(
    registration: PiRegistration,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_agent_key)
) -> PiInfo:
    """
    Register a Pi with the controller.

    This endpoint is called by the Pi agent on startup.

    Args:
        registration: Pi registration data
        request: FastAPI request object
        db: Database session

    Returns:
        PiInfo with registration details
    """
    try:
        pi_manager: PiManager = request.app.state.pi_manager

        logger.info(f"Registering Pi: {registration.agent_id} from {registration.ip_address}")

        pi_info = pi_manager.register_pi(db, registration)

        return pi_info

    except Exception as e:
        logger.error(f"Error registering Pi: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register Pi: {str(e)}")


@router.get("", response_model=List[PiInfo])
async def list_pis(
    request: Request,
    db: Session = Depends(get_db),
    online_only: bool = False
) -> List[PiInfo]:
    """
    List all registered Pis.

    Args:
        request: FastAPI request object
        db: Database session
        online_only: If True, return only online Pis

    Returns:
        List of PiInfo objects
    """
    try:
        pi_manager: PiManager = request.app.state.pi_manager

        if online_only:
            pis = pi_manager.get_online_pis(db)
        else:
            pis = pi_manager.get_all_pis(db)

        return pis

    except Exception as e:
        logger.error(f"Error listing Pis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list Pis: {str(e)}")


@router.get("/{pi_id}", response_model=PiInfo)
async def get_pi(
    pi_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> PiInfo:
    """
    Get information about a specific Pi.

    Args:
        pi_id: Pi ID
        request: FastAPI request object
        db: Database session

    Returns:
        PiInfo object
    """
    try:
        pi_manager: PiManager = request.app.state.pi_manager

        pi_info = pi_manager.get_pi(db, pi_id)
        if not pi_info:
            raise HTTPException(status_code=404, detail=f"Pi {pi_id} not found")

        return pi_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Pi {pi_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get Pi: {str(e)}")


@router.delete("/{pi_id}", response_model=SuccessResponse)
async def delete_pi(
    pi_id: str,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> SuccessResponse:
    """
    Delete a Pi from the controller.

    Args:
        pi_id: Pi ID
        request: FastAPI request object
        db: Database session

    Returns:
        Success response
    """
    try:
        pi_manager: PiManager = request.app.state.pi_manager

        # Get Pi details before deletion for audit log
        pi = pi_manager.get_pi(db, pi_id)
        hostname = pi.hostname if pi else None

        success = pi_manager.delete_pi(db, pi_id)
        if not success:
            audit_log.log_pi_delete(pi_id, hostname, success=False, error="Pi not found")
            raise HTTPException(status_code=404, detail=f"Pi {pi_id} not found")

        # Audit log successful deletion
        audit_log.log_pi_delete(pi_id, hostname, success=True)

        return SuccessResponse(
            success=True,
            message=f"Pi {pi_id} deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        # Audit log deletion failure
        audit_log.log_pi_delete(pi_id, None, success=False, error=str(e))
        logger.error(f"Error deleting Pi {pi_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete Pi: {str(e)}")


@router.get("/{pi_id}/status")
async def get_pi_status(
    pi_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current status of a Pi from monitoring cache.

    Args:
        pi_id: Pi ID
        request: FastAPI request object
        db: Database session

    Returns:
        AgentStatus object
    """
    try:
        from ..services import MonitoringService
        monitoring: MonitoringService = request.app.state.monitoring

        status = monitoring.get_latest_status(pi_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"No status available for Pi {pi_id}")

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Pi status for {pi_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get Pi status: {str(e)}")
