"""
Resident simulation control API.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import ResidentSimulator, ResidentSimulationConfig
from ..services.audit_log import audit_log
from ..middleware.auth import require_auth
from ..services.session_manager import Session as AuthSession

logger = logging.getLogger(__name__)


class ResidentConfigRequest(BaseModel):
  enabled: bool = Field(default=True, description="Enable or disable resident simulation")
  psk_set_id: str = Field(description="PSK set to draw apartments from")
  target_active_apartments: int = Field(default=64, ge=1)
  rotation_hours: float = Field(default=6.0, gt=0)
  max_interfaces_per_pi: int = Field(default=8, ge=1)


class ResidentStatusResponse(BaseModel):
  enabled: bool
  psk_set_id: Optional[str]
  target_active_apartments: int
  rotation_hours: float
  max_interfaces_per_pi: int
  active_apartments: int
  total_apartments: int
  last_rotation_at: Optional[str]
  next_rotation_at: Optional[str]


router = APIRouter(prefix="/api/resident_simulation", tags=["Resident Simulation"])


@router.get("/status", response_model=ResidentStatusResponse)
async def get_resident_status(
    request: Request,
    db: Session = Depends(get_db),  # noqa: U100
) -> ResidentStatusResponse:
  """
  Get current resident simulation status and configuration.
  """
  sim: ResidentSimulator = request.app.state.resident_simulator
  status = sim.get_status()
  return ResidentStatusResponse(
    enabled=status.enabled,
    psk_set_id=status.psk_set_id,
    target_active_apartments=status.target_active_apartments,
    rotation_hours=status.rotation_hours,
    max_interfaces_per_pi=status.max_interfaces_per_pi,
    active_apartments=status.active_apartments,
    total_apartments=status.total_apartments,
    last_rotation_at=status.last_rotation_at.isoformat() if status.last_rotation_at else None,
    next_rotation_at=status.next_rotation_at.isoformat() if status.next_rotation_at else None,
  )


@router.post("/config", response_model=ResidentStatusResponse)
async def update_resident_config(
    body: ResidentConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
) -> ResidentStatusResponse:
  """
  Update resident simulation configuration and start/stop the loop accordingly.
  """
  try:
    sim: ResidentSimulator = request.app.state.resident_simulator

    # Simple validation: ensure PSK set exists
    psk_sets_api = request.app.state.psk_manager
    psk_set = psk_sets_api.get_psk_set(db, body.psk_set_id)
    if not psk_set:
      raise HTTPException(status_code=400, detail=f"PSK set {body.psk_set_id} not found")

    new_cfg = ResidentSimulationConfig(
      enabled=body.enabled,
      psk_set_id=body.psk_set_id,
      target_active_apartments=body.target_active_apartments,
      rotation_hours=body.rotation_hours,
      max_interfaces_per_pi=body.max_interfaces_per_pi,
    )
    sim.update_config(new_cfg)

    if body.enabled:
      await sim.start()
      # Immediately apply the new configuration to all Pis
      logger.info("Triggering immediate rotation after config update")
      await sim.rotate_now()
    else:
      await sim.stop()

    # Audit log configuration change
    audit_log.log_simulation_update(
      enabled=body.enabled,
      psk_set_id=body.psk_set_id,
      target_apartments=body.target_active_apartments,
      success=True
    )

    status = sim.get_status()
    return ResidentStatusResponse(
      enabled=status.enabled,
      psk_set_id=status.psk_set_id,
      target_active_apartments=status.target_active_apartments,
      rotation_hours=status.rotation_hours,
      max_interfaces_per_pi=status.max_interfaces_per_pi,
      active_apartments=status.active_apartments,
      total_apartments=status.total_apartments,
      last_rotation_at=status.last_rotation_at.isoformat() if status.last_rotation_at else None,
      next_rotation_at=status.next_rotation_at.isoformat() if status.next_rotation_at else None,
    )
  except HTTPException:
    raise
  except Exception as e:
    # Audit log update failure
    audit_log.log_simulation_update(
      enabled=body.enabled,
      psk_set_id=body.psk_set_id,
      target_apartments=body.target_active_apartments,
      success=False,
      error=str(e)
    )
    raise
  except Exception as e:
    logger.error(f"Error updating resident simulation config: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to update resident simulation config: {str(e)}")


@router.post("/rotate")
async def trigger_rotation(
    request: Request,
    db: Session = Depends(get_db),  # noqa: U100
    session: AuthSession = Depends(require_auth)
):
  """
  Manually trigger an immediate apartment rotation and scenario application.

  This bypasses the normal rotation schedule and immediately generates
  and applies a new scenario with fresh apartment assignments.
  """
  try:
    sim: ResidentSimulator = request.app.state.resident_simulator

    if not sim.config.enabled:
      raise HTTPException(status_code=400, detail="Resident simulation is not enabled")

    if not sim.config.psk_set_id:
      raise HTTPException(status_code=400, detail="No PSK set configured")

    # Trigger immediate rotation
    logger.info("Manual rotation triggered via API")
    await sim.rotate_now()

    return {"success": True, "message": "Rotation triggered successfully"}

  except HTTPException:
    raise
  except Exception as e:
    logger.error(f"Error triggering rotation: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to trigger rotation: {str(e)}")


@router.post("/stop")
async def stop_simulation(
    request: Request,
    db: Session = Depends(get_db),
    session: AuthSession = Depends(require_auth)
):
  """
  Stop the resident simulation and clear all agent configurations.

  This stops the simulation loop, disables the config, and sends empty
  configurations to all Pis to tear down their interfaces.
  """
  try:
    sim: ResidentSimulator = request.app.state.resident_simulator
    orchestrator = request.app.state.orchestrator

    # Stop the simulation loop
    logger.info("Stopping resident simulation via API")
    await sim.stop()

    # Disable config and clear state
    from ..services import ResidentSimulationConfig
    sim.config = ResidentSimulationConfig(enabled=False)
    sim._current_indices = []
    sim._last_rotation_at = None
    sim._persist_config()

    # Get all online Pis and send empty configurations
    pis = sim.pi_manager.get_online_pis(db)
    logger.info(f"Clearing configurations for {len(pis)} Pis")

    for pi in pis:
      try:
        # Clear desired config
        sim.orchestrator.desired_config_manager.delete_desired_config(db, pi.pi_id)
      except Exception as e:
        logger.error(f"Error clearing desired config for {pi.pi_id}: {e}")

    return {
      "success": True,
      "message": f"Simulation stopped and {len(pis)} Pi configurations cleared"
    }

  except Exception as e:
    logger.error(f"Error stopping simulation: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to stop simulation: {str(e)}")

