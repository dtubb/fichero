"""
Image loader for standard image formats.

Handles: JPG, PNG, TIFF, BMP, GIF, WebP
Special handling: HEIC (via heif-convert), JXL (via djxl), RAW (via rawpy)
"""

import logging
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

from PIL import Image

from fichero.loaders.base import MediaContent, MediaLoader

logger = logging.getLogger(__name__)
_MAX_IMAGE_PIXELS = 50_000_000

# Standard formats PIL can handle directly
PIL_FORMATS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

# Formats requiring special handling
HEIC_FORMATS = {".heic", ".heif"}
JXL_FORMATS = {".jxl"}
RAW_FORMATS = {".raw", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2"}

ALL_IMAGE_FORMATS = PIL_FORMATS | HEIC_FORMATS | JXL_FORMATS | RAW_FORMATS


class UnsafeImageError(ValueError):
    """Raised when an image exceeds ingest safety limits."""


def _ensure_safe_image(image: Image.Image, source: str | Path) -> Image.Image:
    width = int(getattr(image, "width", 0) or 0)
    height = int(getattr(image, "height", 0) or 0)
    if width * height > _MAX_IMAGE_PIXELS:
        raise UnsafeImageError(
            f"Image too large for ingest: {source} ({width}x{height} pixels)"
        )
    return image


def open_image_checked(path: Path) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as img:
            return _ensure_safe_image(img, path).copy()


class ImageLoader(MediaLoader):
    """
    Loader for image files.

    Uses PIL for standard formats, with fallback to system tools for:
    - HEIC: heif-convert
    - JXL: djxl
    - RAW: rawpy (if available)
    """

    def can_handle(self, source: str | Path) -> bool:
        """Check if source is a supported image format."""
        path = Path(source)
        return path.suffix.lower() in ALL_IMAGE_FORMATS

    async def load(self, source: str | Path) -> MediaContent:
        """Load image and return MediaContent."""
        path = Path(source)
        suffix = path.suffix.lower()

        metadata = {
            "original_format": suffix.lstrip("."),
            "filename": path.name,
        }

        try:
            if suffix in PIL_FORMATS:
                image = self._load_pil(path)
            elif suffix in HEIC_FORMATS:
                image = self._load_heic(path)
            elif suffix in JXL_FORMATS:
                image = self._load_jxl(path)
            elif suffix in RAW_FORMATS:
                image = self._load_raw(path)
            else:
                raise ValueError(f"Unsupported image format: {suffix}")

            # Ensure RGB mode for consistency
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")

            # Add image metadata
            metadata["width"] = image.width
            metadata["height"] = image.height
            metadata["mode"] = image.mode

            return MediaContent(
                source=str(path),
                images=[image],
                metadata=metadata,
                mime_type=self._get_mime_type(suffix),
                needs_vlm=True,  # Images always need VLM for transcription
            )

        except Exception as e:
            logger.error(f"Failed to load image {path}: {e}")
            raise

    def _load_pil(self, path: Path) -> Image.Image:
        """Load image using PIL."""
        return open_image_checked(path)

    def _load_heic(self, path: Path) -> Image.Image:
        """Load HEIC/HEIF image using heif-convert system tool."""
        if not shutil.which("heif-convert"):
            raise RuntimeError(
                "HEIC support requires heif-convert. Install with: brew install libheif"
            )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_png = Path(tmp.name)

        try:
            subprocess.run(
                ["heif-convert", str(path), str(temp_png)],
                capture_output=True,
                check=True,
            )
            return open_image_checked(temp_png)
        finally:
            temp_png.unlink(missing_ok=True)

    def _load_jxl(self, path: Path) -> Image.Image:
        """Load JPEG XL image using djxl system tool."""
        if not shutil.which("djxl"):
            # Try PIL as fallback (may work with pillow-jxl plugin)
            try:
                return open_image_checked(path)
            except Exception:
                raise RuntimeError(
                    "JPEG XL support requires djxl. Install with: brew install jpeg-xl"
                )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_png = Path(tmp.name)

        try:
            subprocess.run(
                ["djxl", str(path), str(temp_png)],
                capture_output=True,
                check=True,
            )
            return open_image_checked(temp_png)
        finally:
            temp_png.unlink(missing_ok=True)

    def _load_raw(self, path: Path) -> Image.Image:
        """Load RAW image using rawpy."""
        try:
            import rawpy
        except ImportError:
            raise RuntimeError(
                "RAW format support requires rawpy. Install with: pip install rawpy"
            )

        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                half_size=False,
                no_auto_bright=False,
                output_bps=8,
            )
            return _ensure_safe_image(Image.fromarray(rgb), path)

    def _get_mime_type(self, suffix: str) -> str:
        """Get MIME type for image format."""
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
            ".jxl": "image/jxl",
            ".raw": "image/x-raw",
            ".cr2": "image/x-canon-cr2",
            ".nef": "image/x-nikon-nef",
            ".arw": "image/x-sony-arw",
            ".dng": "image/x-adobe-dng",
        }
        return mime_types.get(suffix, "image/unknown")
