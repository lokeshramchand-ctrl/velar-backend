import logging
from datetime import UTC, datetime
from enum import Enum

from database.mongo import db
from core.dlp_redaction import dlp_redactor

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Security audit event types."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REVOKED = "token_revoked"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    PASSWORD_CHANGED = "password_changed"
    DEVICE_TRUSTED = "device_trusted"
    DEVICE_REVOKED = "device_revoked"
    PDF_UPLOADED = "pdf_uploaded"
    PDF_DELETED = "pdf_deleted"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    API_KEY_ROTATED = "api_key_rotated"
    ADMIN_ACTION = "admin_action"


class AuditLogger:
    """Centralized audit logging for security-relevant events."""

    async def log_event(
        self,
        event_type: AuditEventType | str,
        user_id: str | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        details: dict | None = None,
        severity: str = "INFO",
    ) -> None:
        """Log a security audit event to the audit log collection.

        Args:
            event_type: Type of security event
            user_id: User associated with the event
            device_id: Device associated with the event
            ip_address: IP address of the request
            details: Additional event details (PII automatically redacted)
            severity: Event severity (INFO, WARNING, CRITICAL)
        """
        # Redact sensitive data from details before storing
        redacted_details = dlp_redactor.redact_dict(details or {})

        audit_entry = {
            "event_type": event_type,
            "user_id": user_id,
            "device_id": device_id,
            "ip_address": ip_address,
            "details": redacted_details,
            "severity": severity,
            "timestamp": datetime.now(UTC),
        }

        try:
            await db.audit_logs.insert_one(audit_entry)
            logger.info(
                f"Audit logged: {event_type} | User: {user_id} | Device: {device_id} | IP: {ip_address}"
            )
        except Exception as e:
            logger.error(f"Failed to log audit event {event_type}: {str(e)}")

    async def log_login(
        self,
        user_id: str,
        device_id: str | None,
        ip_address: str | None,
        user_agent: str | None = None,
        success: bool = True,
    ) -> None:
        """Log authentication event."""
        event_type = AuditEventType.LOGIN_SUCCESS if success else AuditEventType.LOGIN_FAILED
        details = {"user_agent": user_agent}
        severity = "INFO" if success else "WARNING"

        await self.log_event(
            event_type=event_type,
            user_id=user_id,
            device_id=device_id,
            ip_address=ip_address,
            details=details,
            severity=severity,
        )

    async def log_token_refresh(
        self,
        user_id: str,
        device_id: str | None,
        ip_address: str | None,
    ) -> None:
        """Log token refresh event."""
        await self.log_event(
            event_type=AuditEventType.TOKEN_REFRESH,
            user_id=user_id,
            device_id=device_id,
            ip_address=ip_address,
        )

    async def log_pdf_upload(
        self,
        user_id: str,
        filename: str,
        file_size_bytes: int,
    ) -> None:
        """Log PDF upload event."""
        await self.log_event(
            event_type=AuditEventType.PDF_UPLOADED,
            user_id=user_id,
            details={
                "filename": filename,
                "file_size_bytes": file_size_bytes,
            },
        )

    async def log_unauthorized_access(
        self,
        user_id: str | None,
        resource: str,
        ip_address: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Log unauthorized access attempt."""
        await self.log_event(
            event_type=AuditEventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            user_id=user_id,
            ip_address=ip_address,
            details={"resource": resource, "reason": reason},
            severity="WARNING",
        )

    async def log_suspicious_activity(
        self,
        user_id: str | None,
        activity: str,
        ip_address: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log suspicious security activity."""
        await self.log_event(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
            user_id=user_id,
            ip_address=ip_address,
            details={**(details or {}), "activity": activity},
            severity="CRITICAL",
        )


audit_logger = AuditLogger()
