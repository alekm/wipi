"""
Configure endpoint - Store configuration (not yet applied).
"""
import logging
from fastapi import APIRouter, HTTPException
from shared.models import AgentConfiguration, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Global configuration storage (in-memory for now)
# In production, this might be persisted to disk
stored_configuration: AgentConfiguration = AgentConfiguration(interfaces=[])


@router.post("/configure", response_model=SuccessResponse)
async def configure(config: AgentConfiguration) -> SuccessResponse:
    """
    Store configuration for the agent (not yet applied).

    This endpoint receives and validates the configuration but does not
    apply it. Use the /apply endpoint to actually apply the configuration.

    Args:
        config: Agent configuration with interface definitions

    Returns:
        Success response
    """
    global stored_configuration

    try:
        logger.info(f"Received configuration with {len(config.interfaces)} interfaces")

        # Validate configuration
        if not config.interfaces:
            logger.warning("Received empty configuration")

        # Log interface details
        for iface in config.interfaces:
            logger.info(
                f"Interface: {iface.name}, SSID: {iface.ssid}, "
                f"Traffic: {iface.traffic.type if iface.traffic else 'none'}, "
                f"Personality: {iface.dhcp_personality or 'NONE'}"
            )

        # Store configuration
        stored_configuration = config

        logger.info("Configuration stored successfully")

        return SuccessResponse(
            success=True,
            message=f"Configuration stored with {len(config.interfaces)} interfaces",
            data={"interface_count": len(config.interfaces)}
        )

    except Exception as e:
        logger.error(f"Error storing configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store configuration: {str(e)}")


@router.get("/configure", response_model=AgentConfiguration)
async def get_configuration() -> AgentConfiguration:
    """
    Get the currently stored configuration.

    Returns:
        Current stored configuration
    """
    global stored_configuration
    return stored_configuration
