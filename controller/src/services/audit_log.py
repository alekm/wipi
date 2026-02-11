"""
Audit Logging Service

Provides structured logging for all admin actions to enable security auditing
and compliance tracking.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional
import json

logger = logging.getLogger("wipi.audit")


class AuditLogger:
    """
    Centralized audit logging for admin actions.

    All audit logs are written in structured format with:
    - Timestamp
    - Action type
    - User/source (currently "admin", can be extended for multi-user)
    - Resource type and ID
    - Details (action-specific metadata)
    - Result (success/failure)
    """

    @staticmethod
    def log_action(
        action: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
        user: str = "admin",
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        Log an admin action.

        Args:
            action: Action performed (e.g., "delete", "create", "update")
            resource_type: Type of resource (e.g., "pi", "scenario", "ruckus_one_config")
            resource_id: Identifier of the resource
            details: Additional context (sanitized, no secrets)
            user: User who performed the action (default: "admin")
            success: Whether the action succeeded
            error: Error message if action failed
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user": user,
            "success": success,
            "details": details or {},
        }

        if error:
            audit_entry["error"] = error

        # Log as structured JSON
        logger.info(json.dumps(audit_entry))

    @staticmethod
    def log_pi_delete(pi_id: str, hostname: Optional[str] = None, success: bool = True, error: Optional[str] = None):
        """Log Pi deletion"""
        AuditLogger.log_action(
            action="delete",
            resource_type="pi",
            resource_id=pi_id,
            details={"hostname": hostname} if hostname else {},
            success=success,
            error=error
        )

    @staticmethod
    def log_ruckus_one_config(enabled: bool, tenant_id: str, success: bool = True, error: Optional[str] = None):
        """Log Ruckus One configuration change (secrets redacted)"""
        AuditLogger.log_action(
            action="configure",
            resource_type="ruckus_one_config",
            resource_id="global",
            details={
                "enabled": enabled,
                "tenant_id": tenant_id,
                # client_id and client_secret intentionally omitted
            },
            success=success,
            error=error
        )

    @staticmethod
    def log_simulation_update(
        enabled: bool,
        psk_set_id: Optional[str] = None,
        target_apartments: Optional[int] = None,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Log resident simulation configuration change"""
        details = {"enabled": enabled}
        if psk_set_id:
            details["psk_set_id"] = psk_set_id
        if target_apartments is not None:
            details["target_apartments"] = target_apartments

        AuditLogger.log_action(
            action="update",
            resource_type="resident_simulation",
            resource_id="global",
            details=details,
            success=success,
            error=error
        )

    @staticmethod
    def log_scenario_deploy(scenario_id: str, pi_count: int, success: bool = True, error: Optional[str] = None):
        """Log scenario deployment"""
        AuditLogger.log_action(
            action="deploy",
            resource_type="scenario",
            resource_id=scenario_id,
            details={"pi_count": pi_count},
            success=success,
            error=error
        )

    @staticmethod
    def log_scenario_stop(pi_count: int, success: bool = True, error: Optional[str] = None):
        """Log scenario stop"""
        AuditLogger.log_action(
            action="stop",
            resource_type="scenario",
            resource_id="all",
            details={"pi_count": pi_count},
            success=success,
            error=error
        )

    @staticmethod
    def log_psk_set_create(psk_set_id: str, name: str, psk_count: int, success: bool = True, error: Optional[str] = None):
        """Log PSK set creation (passphrases redacted)"""
        AuditLogger.log_action(
            action="create",
            resource_type="psk_set",
            resource_id=psk_set_id,
            details={
                "name": name,
                "psk_count": psk_count,
                # PSK values intentionally omitted
            },
            success=success,
            error=error
        )

    @staticmethod
    def log_psk_set_update(psk_set_id: str, psk_count: int, success: bool = True, error: Optional[str] = None):
        """Log PSK set update (passphrases redacted)"""
        AuditLogger.log_action(
            action="update",
            resource_type="psk_set",
            resource_id=psk_set_id,
            details={
                "psk_count": psk_count,
                # PSK values intentionally omitted
            },
            success=success,
            error=error
        )

    @staticmethod
    def log_psk_set_delete(psk_set_id: str, success: bool = True, error: Optional[str] = None):
        """Log PSK set deletion"""
        AuditLogger.log_action(
            action="delete",
            resource_type="psk_set",
            resource_id=psk_set_id,
            success=success,
            error=error
        )


# Convenience instance
audit_log = AuditLogger()
