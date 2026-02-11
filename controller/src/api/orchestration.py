"""
Orchestration API endpoints - Apply and stop scenarios.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session

from shared.models import ScenarioStatus, SuccessResponse, ApplyScenarioRequest, StopScenarioRequest
from ..db import get_db
from ..services import Orchestrator
from ..middleware.auth import require_auth
from ..services.session_manager import Session as AuthSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Orchestration"])


@router.post("/scenarios/{scenario_id}/apply", response_model=ScenarioStatus)
async def apply_scenario(
    scenario_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> ScenarioStatus:
    """
    Apply a scenario to the Pi fleet.

    This will configure all Pis according to the scenario definition.

    Args:
        scenario_id: Scenario ID to apply
        request: FastAPI request object
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        ScenarioStatus with application status
    """
    try:
        orchestrator: Orchestrator = request.app.state.orchestrator

        logger.info(f"Received request to apply scenario: {scenario_id}")

        # Apply scenario asynchronously
        scenario_status = await orchestrator.apply_scenario(db, scenario_id)

        if not scenario_status:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found or failed to apply")

        return scenario_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to apply scenario: {str(e)}")


@router.post("/scenarios/{scenario_id}/stop", response_model=SuccessResponse)
async def stop_scenario(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> SuccessResponse:
    """
    Stop a running scenario.

    This will stop all traffic and destroy all virtual interfaces on all Pis
    involved in the scenario.

    Args:
        scenario_id: Scenario ID to stop
        request: FastAPI request object
        db: Database session

    Returns:
        Success response
    """
    try:
        orchestrator: Orchestrator = request.app.state.orchestrator

        logger.info(f"Received request to stop scenario: {scenario_id}")

        success = await orchestrator.stop_scenario(db, scenario_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found or failed to stop")

        return SuccessResponse(
            success=True,
            message=f"Scenario {scenario_id} stopped successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop scenario: {str(e)}")


@router.get("/scenarios/{scenario_id}/status", response_model=ScenarioStatus)
async def get_scenario_status(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> ScenarioStatus:
    """
    Get current status of a scenario.

    Args:
        scenario_id: Scenario ID
        request: FastAPI request object
        db: Database session

    Returns:
        ScenarioStatus with current status
    """
    try:
        orchestrator: Orchestrator = request.app.state.orchestrator

        scenario_status = await orchestrator.get_scenario_status(db, scenario_id)

        if not scenario_status:
            raise HTTPException(status_code=404, detail=f"No active status for scenario {scenario_id}")

        return scenario_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scenario status for {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scenario status: {str(e)}")


@router.get("/status")
async def get_overall_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get overall fleet status.

    Returns:
        Overall status including all Pis and active scenarios
    """
    try:
        from ..services import PiManager, MonitoringService

        pi_manager: PiManager = request.app.state.pi_manager
        monitoring: MonitoringService = request.app.state.monitoring

        # Get Pi fleet info
        all_pis = pi_manager.get_all_pis(db)
        online_pis = pi_manager.get_online_pis(db)

        # Get all cached statuses
        pi_statuses = monitoring.get_all_statuses()

        # Count total interfaces
        total_interfaces = 0
        connected_interfaces = 0

        for pi_id, status in pi_statuses.items():
            total_interfaces += len(status.interfaces)
            connected_interfaces += sum(
                1 for iface in status.interfaces if iface.state == "connected"
            )

        return {
            "timestamp": None,
            "fleet": {
                "total_pis": len(all_pis),
                "online_pis": len(online_pis),
                "offline_pis": len(all_pis) - len(online_pis)
            },
            "interfaces": {
                "total": total_interfaces,
                "connected": connected_interfaces,
                "disconnected": total_interfaces - connected_interfaces
            },
            "pis": pi_statuses
        }

    except Exception as e:
        logger.error(f"Error getting overall status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get overall status: {str(e)}")
