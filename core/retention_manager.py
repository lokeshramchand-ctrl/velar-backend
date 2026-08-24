import logging
from datetime import UTC, datetime, timedelta

from core.config import settings
from database.mongo import db

logger = logging.getLogger(__name__)


class RetentionManager:
    """Manage data retention and automatic deletion of expired data."""

    async def cleanup_expired_pdfs(self) -> dict[str, int]:
        """Delete PDFs older than PDF_RETENTION_DAYS.

        Returns:
            Dictionary with counts of deleted items
        """
        retention_days = settings.PDF_RETENTION_DAYS
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        # Delete PDFs from statements
        result = await db.statements.update_many(
            {"pdf_upload_date": {"$lt": cutoff_date}, "pdf_file_id": {"$exists": True}},
            {"$unset": {"pdf_file_id": "", "pdf_upload_date": ""}}
        )

        logger.info(f"Cleaned up {result.modified_count} statements with expired PDFs")

        return {"pdfs_deleted": result.modified_count}

    async def cleanup_expired_audit_logs(self, retention_days: int = 90) -> dict[str, int]:
        """Delete audit logs older than retention_days.

        Args:
            retention_days: Number of days to retain audit logs (default: 90)

        Returns:
            Dictionary with counts of deleted items
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        result = await db.audit_logs.delete_many(
            {"timestamp": {"$lt": cutoff_date}}
        )

        logger.info(f"Deleted {result.deleted_count} audit logs older than {retention_days} days")

        return {"audit_logs_deleted": result.deleted_count}

    async def cleanup_expired_request_nonces(self) -> dict[str, int]:
        """Delete expired request nonces (should be handled by TTL index, but cleanup as fallback).

        Returns:
            Dictionary with counts of deleted items
        """
        cutoff_date = datetime.now(UTC)

        result = await db.request_nonces.delete_many(
            {"expires_at": {"$lt": cutoff_date}}
        )

        logger.info(f"Deleted {result.deleted_count} expired request nonces")

        return {"nonces_deleted": result.deleted_count}

    async def cleanup_revoked_refresh_tokens(self, retention_days: int = 7) -> dict[str, int]:
        """Delete revoked refresh tokens older than retention_days.

        Args:
            retention_days: Number of days to retain revoked tokens (default: 7)

        Returns:
            Dictionary with counts of deleted items
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        result = await db.refresh_tokens.delete_many(
            {
                "$and": [
                    {"revoked_at": {"$exists": True}},
                    {"revoked_at": {"$lt": cutoff_date}}
                ]
            }
        )

        logger.info(f"Deleted {result.deleted_count} revoked refresh tokens older than {retention_days} days")

        return {"revoked_tokens_deleted": result.deleted_count}

    async def run_full_retention_cleanup(self) -> dict[str, int]:
        """Run all retention/cleanup tasks and return combined results.

        Returns:
            Dictionary with total counts of all cleanup operations
        """
        logger.info("Starting full retention cleanup cycle")

        results = {}

        try:
            pdf_cleanup = await self.cleanup_expired_pdfs()
            results.update(pdf_cleanup)
        except Exception as e:
            logger.error(f"Error during PDF cleanup: {e}")

        try:
            audit_cleanup = await self.cleanup_expired_audit_logs()
            results.update(audit_cleanup)
        except Exception as e:
            logger.error(f"Error during audit log cleanup: {e}")

        try:
            nonce_cleanup = await self.cleanup_expired_request_nonces()
            results.update(nonce_cleanup)
        except Exception as e:
            logger.error(f"Error during nonce cleanup: {e}")

        try:
            token_cleanup = await self.cleanup_revoked_refresh_tokens()
            results.update(token_cleanup)
        except Exception as e:
            logger.error(f"Error during token cleanup: {e}")

        logger.info(f"Retention cleanup completed: {results}")
        return results


retention_manager = RetentionManager()
