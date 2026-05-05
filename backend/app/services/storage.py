import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.core.config import get_settings


@dataclass
class StoredImage:
    storage_path: str
    public_url: str
    width: int | None
    height: int | None


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def save_upload(self, upload: UploadFile, folder: str = "uploads") -> StoredImage:
        suffix = Path(upload.filename or "upload.jpg").suffix or ".jpg"
        file_name = f"{uuid.uuid4()}{suffix.lower()}"
        target_root = self.settings.upload_root if folder == "uploads" else self.settings.generated_root
        target_root.mkdir(parents=True, exist_ok=True)
        destination = target_root / file_name
        raw_bytes = await upload.read()
        width, height, image_bytes = self._normalize_image(raw_bytes)
        destination.write_bytes(image_bytes)
        rel_path = destination.relative_to(self.settings.media_root).as_posix()
        return StoredImage(
            storage_path=rel_path,
            public_url=f"{self.settings.base_url}/media/{rel_path}",
            width=width,
            height=height,
        )

    def save_generated_image(self, image_bytes: bytes, stem: str) -> StoredImage:
        safe_stem = "".join(ch if ch.isalnum() else "-" for ch in stem.lower()).strip("-") or "generated"
        destination = self.settings.generated_root / f"{safe_stem}-{uuid.uuid4().hex[:8]}.png"
        width, height, normalized = self._normalize_image(image_bytes, force_png=True)
        destination.write_bytes(normalized)
        rel_path = destination.relative_to(self.settings.media_root).as_posix()
        return StoredImage(
            storage_path=rel_path,
            public_url=f"{self.settings.base_url}/media/{rel_path}",
            width=width,
            height=height,
        )

    def _normalize_image(self, image_bytes: bytes, force_png: bool = False) -> tuple[int | None, int | None, bytes]:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.thumbnail((1600, 1600))
                output = io.BytesIO()
                normalized.save(output, format="PNG" if force_png else "JPEG", quality=90, optimize=True)
                return normalized.width, normalized.height, output.getvalue()
        except Exception:
            return None, None, image_bytes
