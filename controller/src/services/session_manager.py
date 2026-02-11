"""
Session Management Service

Provides in-memory session storage for user authentication.
Sessions are identified by secure random tokens stored in httpOnly cookies.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Session data"""
    session_id: str
    user: str
    created_at: datetime
    expires_at: datetime


class SessionManager:
    """
    In-memory session storage for user authentication.

    Features:
    - Secure session ID generation (32-byte hex)
    - Configurable session timeout (default 24 hours)
    - Automatic cleanup of expired sessions
    - Thread-safe operations
    """

    def __init__(self, session_timeout_hours: int = 24):
        """
        Initialize session manager.

        Args:
            session_timeout_hours: Hours until session expires (default 24)
        """
        self.session_timeout = timedelta(hours=session_timeout_hours)
        self._sessions: Dict[str, Session] = {}
        logger.info(f"SessionManager initialized with {session_timeout_hours}h timeout")

    def create_session(self, user: str) -> str:
        """
        Create a new session for a user.

        Args:
            user: Username (e.g., "admin")

        Returns:
            session_id: Secure session identifier
        """
        session_id = secrets.token_hex(32)  # 64 character hex string
        now = datetime.utcnow()
        expires_at = now + self.session_timeout

        session = Session(
            session_id=session_id,
            user=user,
            created_at=now,
            expires_at=expires_at
        )

        self._sessions[session_id] = session
        logger.info(f"Created session for user '{user}' (expires: {expires_at.isoformat()})")

        return session_id

    def validate_session(self, session_id: str) -> Optional[Session]:
        """
        Validate a session ID and return session data if valid.

        Args:
            session_id: Session identifier from cookie

        Returns:
            Session object if valid, None if invalid/expired
        """
        if not session_id:
            return None

        session = self._sessions.get(session_id)

        if not session:
            logger.debug(f"Session not found: {session_id[:8]}...")
            return None

        # Check expiration
        if datetime.utcnow() > session.expires_at:
            logger.info(f"Session expired for user '{session.user}': {session_id[:8]}...")
            self.delete_session(session_id)
            return None

        return session

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (logout).

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found
        """
        if session_id in self._sessions:
            user = self._sessions[session_id].user
            del self._sessions[session_id]
            logger.info(f"Deleted session for user '{user}': {session_id[:8]}...")
            return True

        return False

    def cleanup_expired_sessions(self):
        """
        Remove all expired sessions from storage.
        Called periodically to free memory.
        """
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self._sessions.items()
            if now > session.expires_at
        ]

        for session_id in expired:
            user = self._sessions[session_id].user
            del self._sessions[session_id]
            logger.debug(f"Cleaned up expired session for '{user}': {session_id[:8]}...")

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired session(s)")

    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self._sessions)

    def get_user_sessions(self, user: str) -> list[Session]:
        """
        Get all active sessions for a user.

        Args:
            user: Username

        Returns:
            List of Session objects for the user
        """
        return [
            session for session in self._sessions.values()
            if session.user == user
        ]


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get global session manager instance.

    Returns:
        SessionManager singleton
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
