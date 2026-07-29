"""
IIIF (International Image Interoperability Framework) loader.

Handles IIIF manifests (v2.x and v3.0) from cultural heritage institutions.
Downloads images from IIIF Image API endpoints.
"""

import logging
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image

from typing import TYPE_CHECKING

from fichero_server.loaders.base import MediaContent, MediaLoader
from fichero_server.security.url_security import is_safe_url

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5


async def _validate_url(url: str) -> None:
    is_safe, error = await is_safe_url(url)
    if not is_safe:
        raise ValueError(f"IIIF URL not allowed: {error}")


async def _get_safe(
    session: "aiohttp.ClientSession",
    url: str,
    *,
    max_redirects: int = _MAX_REDIRECTS,
):
    current_url = url
    for _ in range(max_redirects + 1):
        await _validate_url(current_url)
        resp = await session.get(current_url, allow_redirects=False)
        if resp.status not in (301, 302, 303, 307, 308):
            return resp
        location = resp.headers.get("location")
        resp.release()
        if not location:
            return resp
        current_url = urljoin(str(resp.url), location)
    raise ValueError(f"IIIF redirect limit exceeded ({max_redirects})")


class IIIFLoader(MediaLoader):
    """
    Loader for IIIF manifests.

    Fetches manifest JSON, extracts image URLs, and downloads images
    at a reasonable size for VLM processing.

    Supports both IIIF Presentation API 2.x and 3.0.
    """

    def __init__(self, max_dimension: int = 1500, timeout: int = 30):
        """
        Initialize IIIF loader.

        Args:
            max_dimension: Maximum width/height for downloaded images
            timeout: HTTP request timeout in seconds
        """
        self.max_dimension = max_dimension
        self.timeout = timeout

    def can_handle(self, source: str | Path) -> bool:
        """Check if source looks like a IIIF manifest URL."""
        source_str = str(source)

        # Check for IIIF URL patterns
        if not source_str.startswith(("http://", "https://")):
            return False

        # Common IIIF patterns
        iiif_patterns = [
            "/manifest",
            "/manifest.json",
            "/iiif/",
            "presentation/",
        ]

        return any(pattern in source_str.lower() for pattern in iiif_patterns)

    async def load(self, source: str | Path) -> MediaContent:
        """Load IIIF manifest and download images."""
        import aiohttp

        manifest_url = str(source)

        try:
            await _validate_url(manifest_url)
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                # Fetch manifest
                async with await _get_safe(session, manifest_url) as resp:
                    resp.raise_for_status()
                    manifest = await resp.json()

                # Detect IIIF version and extract canvases
                version = self._detect_version(manifest)
                canvases = self._get_canvases(manifest)

                metadata = {
                    "iiif_version": version,
                    "manifest_url": manifest_url,
                    "label": self._get_label(manifest),
                    "attribution": manifest.get("attribution", ""),
                    "canvas_count": len(canvases),
                }

                # Download images from each canvas
                images = []
                for i, canvas in enumerate(canvases):
                    image_url = self._get_image_url(canvas)
                    if image_url:
                        try:
                            img = await self._download_image(session, image_url)
                            images.append(img)
                            logger.info(f"Downloaded canvas {i + 1}/{len(canvases)}")
                        except Exception as e:
                            logger.warning(f"Failed to download canvas {i + 1}: {e}")

                return MediaContent(
                    source=manifest_url,
                    images=images,
                    metadata=metadata,
                    mime_type="application/ld+json",  # IIIF manifest type
                    needs_vlm=True,  # IIIF images always need VLM
                )

        except Exception as e:
            logger.error(f"Failed to load IIIF manifest {manifest_url}: {e}")
            raise

    def _detect_version(self, manifest: dict) -> str:
        """Detect IIIF Presentation API version."""
        context = manifest.get("@context", "")

        if isinstance(context, list):
            context = " ".join(str(c) for c in context)

        if "presentation/3" in str(context):
            return "3.0"
        elif "items" in manifest:
            return "3.0"
        else:
            return "2.x"

    def _get_canvases(self, manifest: dict) -> list[dict]:
        """Extract canvases from manifest (handles v2.x and v3.0)."""
        # IIIF 3.0
        if "items" in manifest:
            return manifest["items"]

        # IIIF 2.x
        if "sequences" in manifest:
            sequences = manifest["sequences"]
            if sequences and "canvases" in sequences[0]:
                return sequences[0]["canvases"]

        return []

    def _get_image_url(self, canvas: dict) -> str | None:
        """Extract image service URL from canvas."""
        # Try IIIF 3.0 structure
        if "items" in canvas:
            try:
                anno_page = canvas["items"][0]
                anno = anno_page["items"][0]
                body = anno.get("body", {})

                # Get image service. Normalise to a dict first: a body may
                # carry no service (direct-image canvas), an empty list, a
                # single-item list, or a service dict — only a dict has .get.
                service = body.get("service", [])
                if isinstance(service, list):
                    service = service[0] if service else {}

                service_url = (
                    service.get("@id") or service.get("id")
                    if isinstance(service, dict)
                    else None
                )
                if service_url:
                    return self._build_image_url(service_url)

                # Fallback to direct image URL
                return body.get("id")

            except (IndexError, KeyError, TypeError):
                pass

        # Try IIIF 2.x structure
        if "images" in canvas:
            try:
                image = canvas["images"][0]
                resource = image.get("resource", {})

                # Get image service
                service = resource.get("service", {})
                service_url = service.get("@id")
                if service_url:
                    return self._build_image_url(service_url)

                # Fallback to direct image URL
                return resource.get("@id")

            except (IndexError, KeyError, TypeError):
                pass

        return None

    def _build_image_url(self, service_url: str) -> str:
        """Build IIIF Image API URL with size constraint."""
        # Remove trailing slash
        service_url = service_url.rstrip("/")

        # IIIF Image API format: {scheme}://{server}{/prefix}/{identifier}/{region}/{size}/{rotation}/{quality}.{format}
        # We want: /full/!{max},{max}/0/default.jpg
        return f"{service_url}/full/!{self.max_dimension},{self.max_dimension}/0/default.jpg"

    def _get_label(self, manifest: dict) -> str:
        """Extract label from manifest."""
        label = manifest.get("label", "")

        # IIIF 3.0 uses language maps
        if isinstance(label, dict):
            # Try to get English, then any language
            for lang in ["en", "none", "@none"]:
                if lang in label:
                    val = label[lang]
                    return val[0] if isinstance(val, list) else val

            # Get first available
            if label:
                first_val = next(iter(label.values()))
                return first_val[0] if isinstance(first_val, list) else first_val

        return str(label) if label else ""

    async def _download_image(
        self, session: "aiohttp.ClientSession", url: str
    ) -> Image.Image:
        """Download image from URL."""
        async with await _get_safe(session, url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            return Image.open(BytesIO(data))
