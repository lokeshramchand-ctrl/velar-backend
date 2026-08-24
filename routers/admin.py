import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.jwt_auth import get_current_user, require_scope
from core.rate_limiter import limiter
from core.retention_manager import retention_manager
from core.security import validate_admin_key

logger = logging.getLogger(__name__)

# Admin API router - separate from public API, stricter rate limits, requires admin scope
# Can be mounted on a separate port/host in production (see app.py for conditional mounting)
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(validate_admin_key)]  # Every admin endpoint requires ADMIN_API_KEY
)


@router.get("/health", status_code=status.HTTP_200_OK)
async def admin_health():
    """Admin health check - verifies ADMIN_API_KEY is valid."""
    return {"status": "ok", "service": "admin-api"}


@router.get("/users", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def list_all_users(
    payload = Depends(require_scope("admin")),
    current_user = Depends(get_current_user)
):
    """List all users in the system. Requires admin scope.

    CAUTION: Returns all users - implement pagination in production.
    """
    from repositories.user_repository import user_repo

    all_users = await user_repo.get_all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "device_count": len(user.devices),
            "created_at": user.created_at,
        }
        for user in all_users
    ]


@router.get("/users/{user_id}", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def get_user_details(
    user_id: str,
    payload = Depends(require_scope("admin")),
    current_user = Depends(get_current_user)
):
    """Get detailed info for a specific user including all devices."""
    from repositories.user_repository import user_repo

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "devices": [
            {
                "device_id": device.device_id,
                "device_name": device.device_name,
                "user_agent": device.user_agent,
                "ip_address": device.ip_address,
                "last_login": device.last_login,
                "is_trusted": device.is_trusted,
                "attestation_verified": getattr(device, "attestation_verified", False),
                "created_at": device.created_at,
            }
            for device in user.devices
        ],
    }


@router.patch("/users/{user_id}/active", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def toggle_user_active(
    user_id: str,
    active: bool,
    payload = Depends(require_scope("admin")),
    current_user = Depends(get_current_user)
):
    """Enable or disable a user account. Requires admin scope."""
    from repositories.user_repository import user_repo

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = active
    updated = await user_repo.update_user(user.id, {"is_active": active})
    logger.info(f"Admin {current_user['sub']} toggled user {user_id} active={active}")

    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_user(
    user_id: str,
    payload = Depends(require_scope("admin")),
    current_user = Depends(get_current_user)
):
    """Soft-delete a user account (mark is_active=False). Requires admin scope.

    Data is retained for compliance/audit; set GDPR_HARD_DELETE for true removal.
    """
    from repositories.user_repository import user_repo

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Soft delete: mark account inactive, revoke all sessions
    from repositories.refresh_token_repository import refresh_token_repo
    await refresh_token_repo.revoke_all_for_user(user_id)
    await user_repo.update_user(user_id, {"is_active": False})

    logger.info(f"Admin {current_user['sub']} deleted user {user_id}")


@router.post("/retention/cleanup", status_code=status.HTTP_200_OK)
@limiter.limit("2/minute")
async def trigger_retention_cleanup(
    payload = Depends(require_scope("admin")),
    current_user = Depends(get_current_user)
):
    """Trigger immediate data retention and cleanup cycle. Requires admin scope.

    Cleans up:
    - PDFs older than PDF_RETENTION_DAYS (default: 90 days)
    - Audit logs older than 90 days
    - Expired request nonces
    - Revoked refresh tokens older than 7 days

    Note: MongoDB TTL indexes handle automatic cleanup automatically, but this
    endpoint is available for manual/immediate triggering if needed.
    """
    try:
        results = await retention_manager.run_full_retention_cleanup()
        logger.info(f"Admin {current_user['sub']} triggered retention cleanup. Results: {results}")
        return {
            "status": "success",
            "message": "Retention cleanup completed",
            "results": results
        }
    except Exception as e:
        logger.error(f"Error during admin retention cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retention cleanup failed: {str(e)}"
        )
