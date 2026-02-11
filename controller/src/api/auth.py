"""
Authentication API endpoints.

Provides login, logout, and session validation for admin access.
"""
import logging
import hashlib
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, Cookie, Depends, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.session_manager import get_session_manager, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

# Admin password hash from environment variable
ADMIN_PASSWORD_HASH = os.environ.get(
    "WIPI_ADMIN_PASSWORD_HASH",
    "8f4179b458b4e4622c32089b025ff4e4b531137642dfdf5143b5f29af3c32e84"  # Default: Ruckus123!
)


class LoginRequest(BaseModel):
    """Login request model"""
    password: str = Field(description="Admin password")


class LoginResponse(BaseModel):
    """Login response model"""
    success: bool
    user: str
    message: str


class MeResponse(BaseModel):
    """Current user response model"""
    authenticated: bool
    user: Optional[str] = None
    mode: str  # "admin" or "demo"


def validate_password(password: str) -> bool:
    """
    Validate password against stored hash.

    Args:
        password: Plain text password

    Returns:
        True if password is correct, False otherwise
    """
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return password_hash == ADMIN_PASSWORD_HASH


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session_manager: SessionManager = Depends(get_session_manager)
) -> LoginResponse:
    """
    Authenticate user and create session.

    Rate limited to 5 attempts per minute per IP address.
    Validates password, creates session, and sets httpOnly cookie.

    Args:
        body: Login request with password
        response: FastAPI response object for setting cookie
        session_manager: Session manager dependency

    Returns:
        LoginResponse with authentication status
    """
    # Validate password
    if not validate_password(body.password):
        logger.warning("Failed login attempt with incorrect password")
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Create session
    session_id = session_manager.create_session(user="admin")

    # Set httpOnly cookie (not accessible to JavaScript, more secure)
    response.set_cookie(
        key="wipi_session",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True when using HTTPS
        samesite="lax",
        max_age=86400,  # 24 hours in seconds
        path="/"
    )

    logger.info("User 'admin' logged in successfully")

    return LoginResponse(
        success=True,
        user="admin",
        message="Login successful"
    )


@router.post("/logout")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    session_id: Optional[str] = Cookie(None, alias="wipi_session"),
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Logout user and destroy session.

    Rate limited to 10 attempts per minute per IP address.

    Args:
        response: FastAPI response object for clearing cookie
        session_id: Session ID from cookie
        session_manager: Session manager dependency

    Returns:
        Success response
    """
    # Delete session if it exists
    if session_id:
        session_manager.delete_session(session_id)

    # Clear cookie
    response.delete_cookie(key="wipi_session", path="/")

    logger.info("User logged out")

    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=MeResponse)
async def get_current_user(
    session_id: Optional[str] = Cookie(None, alias="wipi_session"),
    session_manager: SessionManager = Depends(get_session_manager)
) -> MeResponse:
    """
    Get current user session status.

    Used by UI to check if user is authenticated on page load.

    Args:
        session_id: Session ID from cookie
        session_manager: Session manager dependency

    Returns:
        MeResponse with authentication status
    """
    # Validate session
    if session_id:
        session = session_manager.validate_session(session_id)
        if session:
            return MeResponse(
                authenticated=True,
                user=session.user,
                mode="admin"
            )

    # Not authenticated
    return MeResponse(
        authenticated=False,
        user=None,
        mode="demo"
    )
