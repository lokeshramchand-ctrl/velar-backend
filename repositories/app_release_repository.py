import logging
from typing import AsyncIterator

from bson import ObjectId
from bson.errors import InvalidId

from database.mongo import db
from models.schemas import AppPlatform, AppRelease

logger = logging.getLogger(__name__)


class AppReleaseRepository:
    async def store_apk(self, raw_bytes: bytes, filename: str) -> str:
        """Same GridFS pattern as repositories/statement_repository.py's
        store_pdf - reuses this app's existing Mongo connection instead of
        needing a Coolify volume or S3 bucket for a stateless container."""
        file_id = await db.app_releases_bucket.upload_from_stream(filename, raw_bytes)
        return str(file_id)

    async def create_release(self, release: AppRelease) -> AppRelease:
        """Unsets is_latest on every prior release for this platform first,
        so exactly one document is ever the answer to "what's latest" -
        GET /app/latest-version just queries for it directly rather than
        sorting by version_code, which would misbehave the moment an older
        build is ever re-uploaded for a hotfix rollback."""
        await db.app_releases.update_many(
            {"platform": release.platform.value, "is_latest": True},
            {"$set": {"is_latest": False}},
        )
        doc = release.model_dump(by_alias=True, exclude={"id"})
        result = await db.app_releases.insert_one(doc)
        release.id = str(result.inserted_id)
        return release

    async def get_latest(self, platform: AppPlatform) -> AppRelease | None:
        doc = await db.app_releases.find_one({"platform": platform.value, "is_latest": True})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return AppRelease(**doc)

    async def get_by_version_code(self, platform: AppPlatform, version_code: int) -> AppRelease | None:
        doc = await db.app_releases.find_one({"platform": platform.value, "version_code": version_code})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return AppRelease(**doc)

    async def open_download_stream(self, gridfs_file_id: str) -> AsyncIterator[bytes]:
        try:
            oid = ObjectId(gridfs_file_id)
        except (InvalidId, TypeError):
            raise ValueError(f"Invalid GridFS file id: {gridfs_file_id}")
        stream = await db.app_releases_bucket.open_download_stream(oid)
        return stream


app_release_repo = AppReleaseRepository()
