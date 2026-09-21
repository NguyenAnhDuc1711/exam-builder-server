"""Application-layer port for storing question images (AD-3).

The application layer knows *that* an image can be uploaded to get back a
URL; it does not know it is Cloudinary. This is what lets `create_question`
(T011) treat an upload failure as "no image" instead of a hard failure
(NFR-2) without importing an SDK. The concrete implementation is
`app.infrastructure.storage.cloudinary_service.CloudinaryImageStorage`.
"""

from abc import ABC, abstractmethod


class UploadError(Exception):
    """An image could not be stored. Raised for any storage-backend failure
    (network error, timeout, rejected upload, etc.) — never a raw SDK
    exception.
    """


class ImageStoragePort(ABC):
    @abstractmethod
    async def upload(self, file: bytes, content_type: str) -> str:
        """Store `file` and return its accessible URL.

        Raises `UploadError` if the upload fails for any reason.
        """
