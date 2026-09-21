"""Cloudinary implementation of `ImageStoragePort` (AD-3).

Every exception the Cloudinary SDK can raise (network errors, timeouts,
`cloudinary.exceptions.Error`, etc.) is caught here and re-raised as
`UploadError` — no raw SDK exception is allowed to escape this module, so
callers (the `create_question` use case) only ever need to handle one
exception type.
"""

import asyncio
import io

import cloudinary
import cloudinary.uploader

from app.application.ports.image_storage import ImageStoragePort, UploadError
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
)


class CloudinaryImageStorage(ImageStoragePort):
    async def upload(self, file: bytes, content_type: str) -> str:
        try:
            # The SDK's `upload` is synchronous/blocking; run it off the
            # event loop thread so a slow Cloudinary call doesn't stall
            # other requests.
            result = await asyncio.to_thread(
                cloudinary.uploader.upload, io.BytesIO(file)
            )
            return result["secure_url"]
        except Exception as exc:  # noqa: BLE001 - intentionally catch-all
            raise UploadError(str(exc)) from exc
