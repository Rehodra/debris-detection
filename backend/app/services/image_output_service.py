"""Persist generated prediction images and optionally upload them to Cloudinary."""

import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("marinescan.services.image_output")


class ImageOutputService:
    def __init__(self) -> None:
        self.output_dir = Path(__file__).resolve().parents[2] / "pred_img"

    def save_and_upload(self, jpeg_bytes: bytes, prefix: str = "prediction") -> dict[str, Optional[str]]:
        """Save a JPEG locally and upload it when Cloudinary credentials are configured."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}_{uuid.uuid4().hex}.jpg"
        output_path = self.output_dir / filename
        output_path.write_bytes(jpeg_bytes)

        cloudinary_url = self._upload_to_cloudinary(jpeg_bytes, filename)
        return {
            "local_path": str(output_path),
            "local_url": self._local_url(filename),
            "cloudinary_url": cloudinary_url,
        }

    @staticmethod
    def _local_url(filename: str) -> str:
        from app.core.config import settings

        return f"{settings.API_BASE_URL.rstrip('/')}/pred_img/{filename}"

    @staticmethod
    def as_data_url(jpeg_bytes: bytes) -> str:
        """Return a browser-ready JPEG data URL."""
        import base64

        return f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode('utf-8')}"

    def _upload_to_cloudinary(self, jpeg_bytes: bytes, filename: str) -> Optional[str]:
        from app.core.config import settings

        cloud_name = settings.CLOUDINARY_CLOUD_NAME
        api_key = settings.CLOUDINARY_API_KEY
        api_secret = settings.CLOUDINARY_API_SECRET
        if not all((cloud_name, api_key, api_secret)):
            return None

        try:
            import cloudinary
            import cloudinary.uploader

            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True,
            )
            result = cloudinary.uploader.upload(
                jpeg_bytes,
                public_id=f"marinescan/predictions/{Path(filename).stem}",
                resource_type="image",
            )
            return result.get("secure_url")
        except ImportError:
            logger.warning("Cloudinary credentials are configured but the cloudinary package is not installed.")
        except Exception:
            logger.exception("Cloudinary upload failed; local prediction image is still available.")
        return None


image_output_service = ImageOutputService()