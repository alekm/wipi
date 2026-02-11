"""
Scenario management API endpoints.
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from shared.models import Scenario, SuccessResponse
from ..db import get_db
from ..services import ScenarioManager, PiManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scenarios", tags=["Scenarios"])


@router.post("", response_model=Scenario)
async def create_scenario(
    scenario: Scenario,
    request: Request,
    db: Session = Depends(get_db)
) -> Scenario:
    """
    Create a new scenario.

    Args:
        scenario: Scenario definition
        request: FastAPI request object
        db: Database session

    Returns:
        Created scenario with ID
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager

        created_scenario = scenario_manager.create_scenario(db, scenario)

        return created_scenario

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating scenario: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create scenario: {str(e)}")


@router.get("", response_model=List[Scenario])
async def list_scenarios(
    request: Request,
    db: Session = Depends(get_db)
) -> List[Scenario]:
    """
    List all scenarios.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        List of scenarios
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager

        scenarios = scenario_manager.get_all_scenarios(db)

        return scenarios

    except Exception as e:
        logger.error(f"Error listing scenarios: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list scenarios: {str(e)}")


@router.get("/{scenario_id}", response_model=Scenario)
async def get_scenario(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> Scenario:
    """
    Get a specific scenario.

    Args:
        scenario_id: Scenario ID
        request: FastAPI request object
        db: Database session

    Returns:
        Scenario object
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager

        scenario = scenario_manager.get_scenario(db, scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

        return scenario

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scenario: {str(e)}")


@router.put("/{scenario_id}", response_model=Scenario)
async def update_scenario(
    scenario_id: str,
    scenario: Scenario,
    request: Request,
    db: Session = Depends(get_db)
) -> Scenario:
    """
    Update a scenario.

    Args:
        scenario_id: Scenario ID to update
        scenario: Updated scenario data
        request: FastAPI request object
        db: Database session

    Returns:
        Updated scenario
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager

        updated_scenario = scenario_manager.update_scenario(db, scenario_id, scenario)
        if not updated_scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

        return updated_scenario

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update scenario: {str(e)}")


@router.delete("/{scenario_id}", response_model=SuccessResponse)
async def delete_scenario(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db)
) -> SuccessResponse:
    """
    Delete a scenario.

    Args:
        scenario_id: Scenario ID
        request: FastAPI request object
        db: Database session

    Returns:
        Success response
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager

        success = scenario_manager.delete_scenario(db, scenario_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

        return SuccessResponse(
            success=True,
            message=f"Scenario {scenario_id} deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete scenario: {str(e)}")


@router.post("/{scenario_id}/validate")
async def validate_scenario(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Validate a scenario against the current Pi fleet.

    Args:
        scenario_id: Scenario ID
        request: FastAPI request object
        db: Database session

    Returns:
        Validation results
    """
    try:
        scenario_manager: ScenarioManager = request.app.state.scenario_manager
        pi_manager: PiManager = request.app.state.pi_manager

        scenario = scenario_manager.get_scenario(db, scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

        online_pis = pi_manager.get_online_pis(db)
        available_pi_ids = [pi.pi_id for pi in online_pis]

        validation = scenario_manager.validate_scenario(scenario, available_pi_ids)

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating scenario {scenario_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate scenario: {str(e)}")
