import asyncio
import io

import cloudinary
import cloudinary.uploader

from app.ports.image_storage import ImageStoragePort, UploadError
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
)


class CloudinaryImageStorage(ImageStoragePort):
    async def upload(self, file: bytes, content_type: str) -> str:
        try:
            result = await asyncio.to_thread(
                cloudinary.uploader.upload, io.BytesIO(file)
            )
            return result["secure_url"]
        except Exception as exc:  # noqa: BLE001 - intentionally catch-all
            raise UploadError(str(exc)) from exc
