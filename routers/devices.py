import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from core.jwt_auth import get_current_user
from repositories.refresh_token_repository import refresh_token_repo
from repositories.user_repository import user_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["Devices"])


class DeviceInfo(BaseModel):
    device_id: str
    device_name: str
    user_agent: str | None = None
    ip_address: str | None = None
    last_login: datetime
    is_trusted: bool
    created_at: datetime


class RegisterDeviceRequest(BaseModel):
    device_id: str = Field(description="Unique device identifier")
    device_name: str = Field(description="User-friendly device name", default="Unknown Device")


class TrustDeviceRequest(BaseModel):
    is_trusted: bool = Field(description="Mark device as trusted")


@router.post("", response_model=DeviceInfo, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: RegisterDeviceRequest,
    current_user = Depends(get_current_user)
):
    """Register a new device for the current user."""
    user = await user_repo.get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check if device already registered
    for device in user.devices:
        if device.device_id == payload.device_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device already registered"
            )

    # Create new device session
    from models.schemas import DeviceSession
    new_device = DeviceSession(
        device_id=payload.device_id,
        device_name=payload.device_name,
        last_login=datetime.now(UTC),
        is_trusted=False,
    )

    # Add to user devices list
    user.devices.append(new_device)
    await user_repo.update_user(user.id, {"devices": [d.model_dump() for d in user.devices]})

    logger.info(f"Device registered: {payload.device_id}")
    return DeviceInfo(
        device_id=new_device.device_id,
        device_name=new_device.device_name,
        user_agent=new_device.user_agent,
        ip_address=new_device.ip_address,
        last_login=new_device.last_login,
        is_trusted=new_device.is_trusted,
        created_at=new_device.created_at,
    )


@router.get("", response_model=list[DeviceInfo])
async def list_devices(current_user = Depends(get_current_user)):
    """List all registered devices for the current user."""
    user = await user_repo.get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return [
        DeviceInfo(
            device_id=device.device_id,
            device_name=device.device_name,
            user_agent=device.user_agent,
            ip_address=device.ip_address,
            last_login=device.last_login,
            is_trusted=device.is_trusted,
            created_at=device.created_at,
        )
        for device in user.devices
    ]


@router.patch("/{device_id}", response_model=DeviceInfo)
async def update_device(
    device_id: str,
    payload: TrustDeviceRequest,
    current_user = Depends(get_current_user)
):
    """Update device trust status."""
    user = await user_repo.get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = next((d for d in user.devices if d.device_id == device_id), None)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device.is_trusted = payload.is_trusted
    await user_repo.update_user(user.id, {"devices": [d.model_dump() for d in user.devices]})

    logger.info(f"Device trust status updated: {device_id}, is_trusted={payload.is_trusted}")
    return DeviceInfo(
        device_id=device.device_id,
        device_name=device.device_name,
        user_agent=device.user_agent,
        ip_address=device.ip_address,
        last_login=device.last_login,
        is_trusted=device.is_trusted,
        created_at=device.created_at,
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: str,
    current_user = Depends(get_current_user)
):
    """Revoke a device and all its active sessions."""
    user = await user_repo.get_by_id(current_user["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    device = next((d for d in user.devices if d.device_id == device_id), None)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    # Revoke all refresh tokens for this device
    await refresh_token_repo.revoke_by_device(user.id, device_id)

    # Remove device from user's device list
    user.devices = [d for d in user.devices if d.device_id != device_id]
    await user_repo.update_user(user.id, {"devices": [d.model_dump() for d in user.devices]})

    logger.info(f"Device revoked: {device_id}")
