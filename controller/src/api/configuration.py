"""
Configuration API - Endpoints for pull-based configuration architecture.

Agents use these endpoints to pull their desired configuration and report application status.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..middleware.auth import require_agent_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pis", tags=["Configuration"])


@router.get("/{pi_id}/configuration")
async def get_pi_configuration(
    pi_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_agent_key)
):
    """
    Get desired configuration for a Pi (pull-based architecture).

    Agents poll this endpoint to check for configuration changes.

    Args:
        pi_id: Pi ID
        db: Database session

    Returns:
        Configuration dict with 'config' (AgentConfiguration) and 'hash'
    """
    try:
        desired_config_manager = request.app.state.desired_config_manager

        config_data = desired_config_manager.get_desired_config(db, pi_id)

        if not config_data:
            # No configuration set yet - return empty config
            return {
                "config": {"interfaces": []},
                "hash": "empty"
            }

        return config_data

    except Exception as e:
        logger.error(f"Error getting configuration for {pi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pi_id}/config_applied")
async def report_config_applied(
    pi_id: str,
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    _: str = Depends(require_agent_key)
):
    """
    Agent reports that it has applied a configuration.

    Args:
        pi_id: Pi ID
        payload: Dict with 'config_hash', 'success' (bool), 'error_message' (optional)
        db: Database session

    Returns:
        Success confirmation
    """
    try:
        config_hash = payload.get("config_hash")
        success = payload.get("success", False)
        error_message = payload.get("error_message")

        if success:
            logger.info(f"Pi {pi_id} successfully applied config: {config_hash[:8]}...")
        else:
            logger.error(f"Pi {pi_id} failed to apply config {config_hash[:8]}...: {error_message}")

        # Future: Could store application status in database for tracking

        return {
            "status": "acknowledged",
            "pi_id": pi_id,
            "config_hash": config_hash
        }

    except Exception as e:
        logger.error(f"Error processing config_applied from {pi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
