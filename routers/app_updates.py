import hashlib
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from core.config import settings
from core.security import validate_admin_key
from models.schemas import AppPlatform, AppRelease, AppReleaseResponse
from repositories.app_release_repository import app_release_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["App Updates"])


def _to_response(release: AppRelease) -> AppReleaseResponse:
    return AppReleaseResponse(
        platform=release.platform,
        version_code=release.version_code,
        version_name=release.version_name,
        release_notes=release.release_notes,
        min_supported_version_code=release.min_supported_version_code,
        sha256=release.sha256,
        size_bytes=release.size_bytes,
        uploaded_at=release.uploaded_at,
        # Relative, like every other endpoint this app calls - the client
        # already prepends its own configured AppConfig.apiBaseUrl (see
        # frontend/lib/core/network/api_client.dart), so this never hardcodes
        # a host/scheme that could drift from wherever this instance is
        # actually reachable.
        download_url=f"/app/releases/{release.version_code}/download",
    )


@router.get("/latest-version", response_model=AppReleaseResponse)
async def get_latest_version(platform: AppPlatform = AppPlatform.ANDROID):
    """Polled by the app on launch (frontend's app_update_controller.dart) to
    decide whether to show the "update available" sheet. X-Velar-API-Key
    alone gates this - it's read-only version metadata, not sensitive, and
    every installed app already holds that key."""
    release = await app_release_repo.get_latest(platform)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No release published for this platform yet")
    return _to_response(release)


@router.get("/releases/{version_code}/download")
async def download_release(version_code: int, platform: AppPlatform = AppPlatform.ANDROID):
    release = await app_release_repo.get_by_version_code(platform, version_code)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    grid_out = await app_release_repo.open_download_stream(release.gridfs_file_id)

    async def _iter_chunks():
        # AsyncIOMotorGridOut needs no explicit close - its underlying cursor
        # is cleaned up once exhausted (or garbage collected on early client
        # disconnect), unlike a raw pymongo GridOut in sync code.
        async for chunk in grid_out:
            yield chunk

    return StreamingResponse(
        _iter_chunks(),
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f'attachment; filename="velar-v{release.version_name}.apk"',
            "Content-Length": str(release.size_bytes),
            "X-Sha256": release.sha256,
        },
    )


@router.post("/releases", response_model=AppReleaseResponse, dependencies=[Depends(validate_admin_key)])
async def publish_release(
    apk: UploadFile = File(...),
    version_code: int = Form(...),
    version_name: str = Form(...),
    release_notes: str = Form(""),
    min_supported_version_code: int | None = Form(None),
    platform: AppPlatform = Form(AppPlatform.ANDROID),
):
    """Uploads a new build and marks it latest. Operator-only (same
    X-Velar-Admin-Key gate as routers/pipelines.py) - this is how a new build
    actually gets in front of installed devices, so it can't be gated by
    VELAR_API_KEY alone (shipped inside every client app binary)."""
    if not apk.filename or not apk.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a .apk file")

    raw_bytes = await apk.read()
    if len(raw_bytes) > settings.MAX_APK_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"APK exceeds the maximum allowed size of {settings.MAX_APK_UPLOAD_BYTES} bytes",
        )
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    existing = await app_release_repo.get_by_version_code(platform, version_code)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"version_code {version_code} already published for {platform.value} - bump it and re-upload",
        )

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    gridfs_file_id = await app_release_repo.store_apk(raw_bytes, f"{platform.value}-v{version_code}.apk")

    release = AppRelease(
        platform=platform,
        version_code=version_code,
        version_name=version_name,
        release_notes=release_notes,
        min_supported_version_code=min_supported_version_code,
        gridfs_file_id=gridfs_file_id,
        sha256=sha256,
        size_bytes=len(raw_bytes),
        is_latest=True,
    )
    release = await app_release_repo.create_release(release)
    logger.info("Published app release %s version_code=%s size=%d bytes", platform.value, version_code, len(raw_bytes))
    return _to_response(release)
