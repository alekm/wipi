"""
Authentication Dependencies

Provides FastAPI dependencies for requiring authentication on endpoints.
"""
import logging
from typing import Optional

from fastapi import HTTPException, Cookie, Depends, Header
from fastapi.security import HTTPBearer

from ..services.session_manager import get_session_manager, SessionManager, Session

logger = logging.getLogger(__name__)

# HTTP Bearer scheme (not used, but can be added later for API keys)
security = HTTPBearer(auto_error=False)


async def require_auth(
    session_id: Optional[str] = Cookie(None, alias="wipi_session"),
    session_manager: SessionManager = Depends(get_session_manager)
) -> Session:
    """
    Require authentication for an endpoint.

    Validates session cookie and returns session data if authenticated.
    Raises 401 Unauthorized if not authenticated.

    Usage:
        @router.post("/some-endpoint")
        async def my_endpoint(session: Session = Depends(require_auth)):
            # session.user will be "admin"
            ...

    Args:
        session_id: Session ID from cookie
        session_manager: Session manager dependency

    Returns:
        Session object if authenticated

    Raises:
        HTTPException 401 if not authenticated or session expired
    """
    if not session_id:
        logger.warning("Unauthenticated request (no session cookie)")
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )

    session = session_manager.validate_session(session_id)

    if not session:
        logger.warning(f"Invalid or expired session: {session_id[:8]}...")
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Please log in again."
        )

    logger.debug(f"Authenticated request from user '{session.user}'")
    return session


async def optional_auth(
    session_id: Optional[str] = Cookie(None, alias="wipi_session"),
    session_manager: SessionManager = Depends(get_session_manager)
) -> Optional[Session]:
    """
    Optional authentication for an endpoint.

    Returns session data if authenticated, None if not.
    Does not raise an error.

    Usage:
        @router.get("/some-endpoint")
        async def my_endpoint(session: Optional[Session] = Depends(optional_auth)):
            if session:
                # Authenticated
                ...
            else:
                # Not authenticated (demo mode)
                ...

    Args:
        session_id: Session ID from cookie
        session_manager: Session manager dependency

    Returns:
        Session object if authenticated, None otherwise
    """
    if not session_id:
        return None

    session = session_manager.validate_session(session_id)
    return session


async def require_agent_key(
    x_agent_api_key: Optional[str] = Header(None)
) -> str:
    """
    Require valid agent API key for agent-to-controller endpoints.

    Validates the X-Agent-Api-Key header against the configured key.
    This protects agent registration and configuration endpoints from
    unauthorized access.

    Usage:
        @router.post("/pis/register")
        async def register_pi(
            registration: PiRegistration,
            _: str = Depends(require_agent_key)
        ):
            # API key validated
            ...

    Args:
        x_agent_api_key: API key from X-Agent-Api-Key header

    Returns:
        API key if valid

    Raises:
        HTTPException 401 if API key is missing or invalid
    """
    # Import Config here to avoid circular import
    from ..main import Config

    if not x_agent_api_key:
        logger.warning("Agent request without API key")
        raise HTTPException(
            status_code=401,
            detail="Agent API key required. Set X-Agent-Api-Key header."
        )

    if x_agent_api_key != Config.agent_api_key:
        logger.warning(f"Invalid agent API key: {x_agent_api_key[:8]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid agent API key"
        )

    logger.debug("Valid agent API key")
    return x_agent_api_key
