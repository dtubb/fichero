"""
File storage management for Fichero.

Handles derived files (thumbnails), path resolution, and file organization.
Uses Pydantic Settings for configuration and explicit functions for operations.

Location: ~/Library/Application Support/com.fichero.fichero/
├── library.duckdb          # Database (managed by db.py)
├── vectors/                # LanceDB embeddings
└── thumbnails/             # Sharded thumbnail storage
    └── {id[:2]}/{id}.jpg   # 256 buckets for scale

Usage:
    from fichero.db.storage import settings, ensure_thumbnail, resolve_source

    # Get settings
    print(settings.thumb_dir)

    # Generate thumbnail (explicit, not hidden)
    path = ensure_thumbnail(doc)

    # Resolve source file
    source = resolve_source(doc)

    # Cleanup orphaned thumbnails
    cleanup_orphans(valid_doc_ids)
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    pass

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from fichero.security.path_security import (
    allowed_source_roots,
    resolve_under_allowed_roots,
)
from fichero.core.perf import perf_span
from fichero.db.paths import engine_state_dir

# PIL is bound lazily (#3985): storage is on the engine boot path, but only the
# thumbnail/display render helpers need Pillow, and only when they run. Eagerly
# importing it here put PIL (~80ms) on every engine boot. The `Image is None`
# sentinel is preserved — _load_pil() leaves the globals None when Pillow is
# missing, so callers degrade exactly as before.
Image = None  # type: ignore[assignment]  # bound by _load_pil()
ImageOps = None  # type: ignore[assignment]  # bound by _load_pil()


def _load_pil() -> None:
    """Bind the PIL globals on first render, keeping Pillow off engine boot."""
    global Image, ImageOps
    if Image is not None:
        return
    try:
        from PIL import Image as _Image, ImageOps as _ImageOps
    except ImportError:
        return
    Image, ImageOps = _Image, _ImageOps

if TYPE_CHECKING:
    from fichero.db import Database
    from fichero.models import Document

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_DIMENSION = 1024
DISPLAY_MAX_DIMENSION = 1000
DEFAULT_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
DEFAULT_UPLOAD_CHUNK_SIZE = 1024 * 1024


# =============================================================================
# Configuration (Pydantic Settings)
# =============================================================================


class StorageSettings(BaseSettings):
    """Storage configuration.

    Override via environment variables:
        FICHERO_BASE_PATH=/custom/path
        FICHERO_THUMB_SIZE=150,150
        FICHERO_QUALITY=90
    """

    model_config = SettingsConfigDict(env_prefix="FICHERO_")

    # Base path - can be overridden for testing
    base_path: Path = engine_state_dir()

    # Thumbnail settings
    thumb_width: int = THUMBNAIL_MAX_DIMENSION
    thumb_height: int = THUMBNAIL_MAX_DIMENSION
    display_width: int = DISPLAY_MAX_DIMENSION
    display_height: int = DISPLAY_MAX_DIMENSION
    quality: int = 85

    # Thread pool size for background generation
    max_workers: int = 2

    # Periodic snapshot scheduler polls for due libraries at this cadence.
    scheduled_snapshot_poll_interval_seconds: float = 60.0
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @computed_field
    @property
    def thumb_dir(self) -> Path:
        """Directory for thumbnail storage."""
        return self.base_path / "thumbnails"

    @computed_field
    @property
    def db_path(self) -> Path:
        """Path to DuckDB database (legacy - per library)."""
        return self.base_path / "library.duckdb"

    @computed_field
    @property
    def app_db_path(self) -> Path:
        """Path to app-wide DuckDB database (providers, app settings)."""
        return self.base_path / "app.duckdb"

    @computed_field
    @property
    def global_library_path(self) -> Path:
        """Path to global library database (cross-library searches/chats/workflows)."""
        return self.base_path / "global.fichero"

    @computed_field
    @property
    def vectors_dir(self) -> Path:
        """Directory for LanceDB vectors."""
        return self.base_path / "vectors"

    @computed_field
    @property
    def snapshots_dir(self) -> Path:
        """Directory for library snapshots."""
        return self.base_path / "snapshots"

    @property
    def thumb_size(self) -> tuple[int, int]:
        """Thumbnail dimensions as tuple."""
        return (self.thumb_width, self.thumb_height)

    @property
    def display_size(self) -> tuple[int, int]:
        """Display image dimensions as tuple."""
        return (self.display_width, self.display_height)


# Global settings instance
settings = StorageSettings()


class UploadTooLargeError(ValueError):
    """Raised when an uploaded body exceeds the configured size cap."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        super().__init__(f"Upload exceeds maximum allowed size of {max_bytes} bytes")


# =============================================================================
# Path Helpers
# =============================================================================


def _thumb_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get sharded thumbnail path.

    Uses first 2 chars of ID for sharding:
    thumbnails/a1/a1b2c3d4-e5f6-...jpg

    256 possible buckets = ~234 files each for 60k images.

    Args:
        doc_id: Document ID
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    prefix = doc_id[:2].lower()
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir
    return thumb_dir / prefix / f"{doc_id}.jpg"


def _thumbnail_cache_path(
    doc_id: str,
    size: tuple[int, int],
    source_mtime_ns: int,
    package_path: Path | None = None,
) -> Path:
    """Get the versioned thumbnail cache path for a source revision."""
    prefix = doc_id[:2].lower()
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir
    width, height = size
    return thumb_dir / prefix / f"{doc_id}__{width}x{height}__{source_mtime_ns}.jpg"


def _display_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get path for display-size image.

    Args:
        doc_id: Document ID
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    prefix = doc_id[:2].lower()
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir
    return thumb_dir / prefix / f"{doc_id}_display.jpg"


def _derive_doc_id_from_thumb_name(stem: str) -> str:
    """Extract the document id from legacy and versioned thumbnail names."""
    stem = stem.replace("_display", "")
    if "__" in stem:
        return stem.split("__", 1)[0]
    return stem


def _source_mtime_ns(source: Path) -> int:
    return source.stat().st_mtime_ns


def _sync_alias_to_cache(cache_path: Path, alias_path: Path) -> None:
    """Keep the legacy doc-id.jpg path pointing at the latest cache entry."""
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    if alias_path.exists() or alias_path.is_symlink():
        alias_path.unlink()
    try:
        os.link(cache_path, alias_path)
    except OSError:
        shutil.copy2(cache_path, alias_path)


def _remove_stale_thumbnail_variants(
    doc_id: str, active_path: Path, package_path: Path | None = None
) -> None:
    shard_dir = active_path.parent
    if not shard_dir.exists():
        return
    for candidate in shard_dir.glob(f"{doc_id}__*.jpg"):
        if candidate == active_path:
            continue
        try:
            candidate.unlink()
        except OSError as exc:
            logger.debug("Failed to remove stale thumbnail cache %s: %s", candidate, exc)


def _resolve_thumbnail_cache_candidate(
    doc: "Document",
    package_path: Path | None = None,
    db: "Database | None" = None,
    size: tuple[int, int] | None = None,
) -> tuple[Path | None, Path, Path | None, int | None]:
    """Resolve the active thumbnail cache file and supporting source paths."""
    size = size or settings.thumb_size
    alias_path = _thumb_path(doc.id, package_path)
    source = (
        resolve_edited_source(doc, db)
        if db is not None
        else resolve_source(doc, library_root=package_path)
    )
    pdf_render = _resolve_pdf_render_source(doc, db=db, library_root=package_path)

    if not source and not pdf_render:
        return alias_path if alias_path.exists() else None, alias_path, source, None

    source_path = pdf_render[0] if pdf_render else source
    assert source_path is not None
    source_mtime_ns = _source_mtime_ns(source_path)
    cache_path = _thumbnail_cache_path(doc.id, size, source_mtime_ns, package_path)

    if cache_path.exists():
        return cache_path, alias_path, source, source_mtime_ns

    if alias_path.exists() and alias_path.stat().st_mtime_ns >= source_mtime_ns:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(alias_path, cache_path)
        except OSError:
            shutil.copy2(alias_path, cache_path)
        _sync_alias_to_cache(cache_path, alias_path)
        return cache_path, alias_path, source, source_mtime_ns

    return None, alias_path, source, source_mtime_ns


# =============================================================================
# Source Resolution
# =============================================================================


def resolve_source(
    doc: "Document", library_root: "Path | str | None" = None
) -> Path | None:
    """Resolve the source file for a document.

    Priority:
    1. macOS bookmark (survives moves/renames)
    2. doc.path
    3. metadata.source_path
    4. metadata.full_path
    5. metadata.local_path
    6. library-relative fallback — re-root a copied-in ``files/…`` path under the
       CURRENT library package, so a renamed/moved ``.fichero`` still resolves
       images even though the stored absolute path baked in the old name.

    Args:
        doc: Document to resolve source for
        library_root: the current ``.fichero`` package dir (e.g. ``db.path.parent``)

    Returns:
        Path to existing file, or None if not found
    """
    allowed_roots = allowed_source_roots(library_root, storage_base=settings.base_path)

    def confined_existing(candidate: Path) -> Path | None:
        if not candidate.exists():
            return None
        return resolve_under_allowed_roots(candidate, allowed_roots)

    def library_confined_existing(candidate: Path) -> Path | None:
        if library_root is None or not candidate.exists():
            return None
        library_roots = allowed_source_roots(
            library_root,
            storage_base=None,
            include_engine_temp=False,
        )
        return resolve_under_allowed_roots(candidate, library_roots)

    def package_candidate(path_value: object) -> Path | None:
        if not path_value or library_root is None:
            return None
        try:
            p = Path(path_value).expanduser()
        except TypeError:
            return None
        root = Path(library_root).expanduser()
        if not p.is_absolute():
            return root / p
        if "/files/" in str(p):
            tail = str(p).split("/files/", 1)[1]
            return root / "files" / tail
        return p

    # Prefer copied/in-package storage before macOS bookmarks. Remote engines
    # should use package-confined files and avoid resolving client-host bookmarks.
    package_candidates = [doc.path] + [
        (doc.metadata or {}).get(k)
        for k in ("source_path", "full_path", "display_path", "local_path")
    ]
    for path_value in package_candidates:
        if candidate := package_candidate(path_value):
            if confined := library_confined_existing(candidate):
                return confined

    # Try bookmark next when enabled (embedded macOS only by default).
    if bookmark_data := _get_bookmark(doc):
        try:
            from fichero.bookmarks import is_available as bookmarks_available
            from fichero.bookmarks import resolve_bookmark

            if bookmarks_available() and (path := resolve_bookmark(bookmark_data)):
                if confined := confined_existing(path):
                    return confined
        except ImportError:
            pass  # bookmarks module not available

    # Fall back to paths
    if doc.path:
        try:
            p = Path(doc.path).expanduser()
        except TypeError:
            p = None
        if p is not None:
            # A relative path (e.g. "files/nc/<id>_<name>.jpg") is stored for
            # COPY/MOVE ingests so the library bundle can be renamed/moved
            # without breaking image paths (#1663). Resolve it against the
            # CURRENT library root rather than the process CWD.
            if not p.is_absolute() and library_root is not None:
                candidate = Path(library_root).expanduser() / p
                if confined := confined_existing(candidate):
                    return confined
            elif p.is_absolute():
                if confined := confined_existing(p):
                    return confined

    # Check metadata fields
    if doc.metadata:
        for key in ["source_path", "full_path", "display_path", "local_path"]:
            if path_str := doc.metadata.get(key):
                try:
                    p = Path(path_str).expanduser()
                except TypeError:
                    continue
                if not p.is_absolute() and library_root is not None:
                    p = Path(library_root).expanduser() / p
                if confined := confined_existing(p):
                    return confined

    # Library-relative fallback: the library was renamed/moved, so the stored
    # absolute path (which bakes in the old package name) no longer exists, but
    # the copied-in file still lives under <library_root>/files/<tail>.
    if library_root is not None:
        root = Path(library_root).expanduser()
        candidates = [doc.path] + [
            (doc.metadata or {}).get(k)
            for k in ("source_path", "full_path", "display_path", "local_path")
        ]
        for path_str in candidates:
            if not path_str or "/files/" not in str(path_str):
                continue
            tail = str(path_str).split("/files/", 1)[1]
            p = root / "files" / tail
            if confined := confined_existing(p):
                return confined

    return None


def resolve_edited_source(
    doc: "Document", db: "Database", *, page: int = 1
) -> Path | None:
    """Return the cached replay of a document's saved edit chain, if any."""
    from fichero.image_ops import apply_operation
    from fichero.models import ImageEditChain

    source = resolve_source(doc, library_root=db.path.parent)
    if source is None:
        return None
    chains = list(db.query(ImageEditChain, document_id=doc.id))
    if not chains:
        return source
    chain = chains[0]
    operations = [op for op in chain.operations if int(op.get("page", page)) == page]
    if not operations:
        return source
    version = int(chain.updated_at.timestamp() * 1_000_000)
    cache = db.path.parent / "storage" / "edited" / doc.id[:2] / f"{doc.id}__p{page}__{version}.png"
    if cache.exists():
        return cache
    _load_pil()
    if Image is None:
        raise RuntimeError("Pillow is required to render saved image edits")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).copy()
    for op in operations:
        image = apply_operation(image, op)
    cache.parent.mkdir(parents=True, exist_ok=True)
    image.save(cache, format="PNG")
    return cache


def _get_bookmark(doc: "Document") -> bytes | None:
    """Extract bookmark data from document metadata."""
    if not doc.metadata:
        return None
    b64 = doc.metadata.get("bookmark")
    if b64:
        try:
            return base64.b64decode(b64, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Document {doc.id} has invalid bookmark metadata") from exc
    return None


def _resolve_pdf_render_source(
    doc: "Document",
    *,
    db: "Database | None" = None,
    library_root: Path | None = None,
) -> tuple[Path, int] | None:
    """Return ``(pdf_path, page_index)`` when ``doc`` should render from a PDF.

    Top-level PDF documents render page 0. Page-child documents render their
    own ``sequence`` from the parent PDF path instead of trusting any stale
    per-page ``metadata.pdf_path`` left behind from ingest.
    """
    from fichero.models import Document as DocumentModel, DocType, FileType

    if doc.doc_type == DocType.page:
        if db is None or not doc.parent_id:
            return None
        parent = db.get(DocumentModel, doc.parent_id)
        if not parent or parent.file_type != FileType.pdf:
            return None
        source = resolve_source(parent, library_root=library_root)
        if not source:
            return None
        try:
            page_number = int(doc.sequence or (doc.metadata or {}).get("page_number") or 1)
        except (TypeError, ValueError):
            page_number = 1
        return source, max(page_number - 1, 0)

    if getattr(doc, "file_type", None) != FileType.pdf:
        return None

    source = resolve_source(doc, library_root=library_root)
    if not source:
        return None
    return source, 0


# =============================================================================
# Thumbnail Generation
# =============================================================================


def ensure_thumbnail(
    doc: "Document",
    force: bool = False,
    package_path: Path | None = None,
    db: "Database | None" = None,
) -> Path | None:
    """Generate thumbnail if needed.

    Args:
        doc: Document to generate thumbnail for
        force: If True, regenerate even if exists
        package_path: Path to .fichero package (if None, uses global base_path)

    Returns:
        Path to thumbnail, or None on failure
    """
    with perf_span(
        "library.thumbnail.ensure",
        logger=logger,
        doc_id=doc.id,
        force=force,
    ) as perf:
        _load_pil()
        if Image is None:
            logger.error("Pillow not installed - cannot generate thumbnails")
            perf["cache_state"] = "pillow_missing"
            return None

        cached_path, alias_path, source, source_mtime_ns = _resolve_thumbnail_cache_candidate(
            doc,
            package_path=package_path,
            db=db,
            size=settings.thumb_size,
        )

        if not force and cached_path and cached_path.exists():
            perf["cache_state"] = "hit"
            perf["thumbnail_path"] = cached_path.name
            perf["source_mtime_ns"] = source_mtime_ns
            return cached_path

        pdf_render = _resolve_pdf_render_source(doc, db=db, library_root=package_path)
        source_path = pdf_render[0] if pdf_render else source
        if not source_path:
            logger.warning(f"No source found for {doc.id}")
            perf["cache_state"] = "missing_source"
            return None

        source_mtime_ns = _source_mtime_ns(source_path)
        cache_path = _thumbnail_cache_path(doc.id, settings.thumb_size, source_mtime_ns, package_path)
        perf["cache_state"] = "regenerated" if force else "miss"
        perf["source_mtime_ns"] = source_mtime_ns

        if pdf_render:
            pdf_path, page_index = pdf_render
            result = _generate_pdf_image(pdf_path, page_index, cache_path, settings.thumb_size)
        else:
            result = _generate_image(source_path, cache_path, settings.thumb_size)

        if result:
            _sync_alias_to_cache(result, alias_path or _thumb_path(doc.id, package_path))
            _remove_stale_thumbnail_variants(doc.id, result, package_path)
            perf["thumbnail_path"] = result.name
        return result


def ensure_display(
    doc: "Document",
    force: bool = False,
    package_path: Path | None = None,
    db: "Database | None" = None,
) -> Path | None:
    """Generate display-size image if needed.

    Args:
        doc: Document to generate display image for
        force: If True, regenerate even if exists
        package_path: Path to .fichero package (if None, uses global base_path)

    Returns:
        Path to display image, or None on failure
    """
    _load_pil()
    if Image is None:
        return None

    path = _display_path(doc.id, package_path)
    source = (
        resolve_edited_source(doc, db)
        if db is not None
        else resolve_source(doc, library_root=package_path)
    )
    pdf_render = _resolve_pdf_render_source(
        doc, db=db, library_root=package_path
    )

    if not source and not pdf_render:
        return None

    if path.exists() and not force:
        source_mtime = pdf_render[0].stat().st_mtime if pdf_render else source.stat().st_mtime
        if source_mtime <= path.stat().st_mtime:
            return path

    if pdf_render:
        pdf_path, page_index = pdf_render
        return _generate_pdf_image(pdf_path, page_index, path, settings.display_size)

    return _generate_image(source, path, settings.display_size)


def _generate_pdf_image(
    source: Path,
    page_index: int,
    dest: Path,
    size: tuple[int, int],
) -> Path | None:
    """Render a PDF page to a cached JPEG."""
    _load_pil()
    if Image is None:
        return None

    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed - cannot render PDF: %s", source.name)
        return None

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)

        with fitz.open(str(source)) as pdf:
            if page_index < 0 or page_index >= pdf.page_count:
                logger.warning(
                    "PDF page %s out of range for %s (page_count=%s)",
                    page_index,
                    source.name,
                    pdf.page_count,
                )
                return None

            page = pdf.load_page(page_index)
            rect = page.rect
            width_scale = size[0] / max(rect.width, 1)
            height_scale = size[1] / max(rect.height, 1)
            scale = max(min(width_scale, height_scale), 0.1)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(dest, "JPEG", quality=settings.quality)

        logger.info(
            "Generated PDF-derived image: %s from %s page %s",
            dest,
            source.name,
            page_index + 1,
        )
        return dest
    except Exception as exc:
        logger.warning(
            "PDF image generation failed for %s page %s: %s",
            source.name,
            page_index + 1,
            exc,
        )
        return None


def _generate_image(source: Path, dest: Path, size: tuple[int, int]) -> Path | None:
    """Generate a resized image.

    Args:
        source: Source image path
        dest: Destination path
        size: (width, height) tuple

    Returns:
        Path to generated image, or None on failure
    """
    _load_pil()
    # Text-based formats get a rendered text thumbnail.
    _text_suffixes = {".json", ".txt", ".md", ".rst", ".csv", ".xml", ".yaml", ".yml", ".toml"}
    if source.suffix.lower() in _text_suffixes:
        return _generate_text_thumbnail(source, dest, size)

    # Skip non-image suffixes up-front — PIL would raise
    # UnidentifiedImageError and the traceback clutters the log.
    # Thumbnail generation for videos, audio, office docs, etc. is
    # handled by different pipelines (or absent entirely); letting
    # the storage endpoint return 404 is the right behaviour.
    _non_image_suffixes = {
        ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm",
        ".mp3", ".wav", ".aiff", ".m4a", ".flac",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz",
    }
    if source.suffix.lower() in _non_image_suffixes:
        logger.debug(f"Skipping thumbnail for non-image type: {source.name}")
        return None

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Opening image: {source} (suffix: {source.suffix})")
        with Image.open(source) as img:
            logger.debug(f"Image opened successfully: mode={img.mode}, size={img.size}")

            # Handle EXIF rotation
            if ImageOps:
                img = ImageOps.exif_transpose(img)

            # Create thumbnail (modifies in place, maintains aspect ratio)
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Convert to RGB for JPEG (handles RGBA, P mode, etc.)
            if img.mode not in ("RGB", "L"):
                logger.debug(f"Converting from {img.mode} to RGB")
                img = img.convert("RGB")

            img.save(dest, "JPEG", quality=settings.quality)

        logger.info(f"Generated thumbnail: {dest} from {source.name}")
        return dest

    except Exception as e:
        # PIL can't handle some JPEGs (CMYK, unusual encodings, old-format).
        # On macOS, try sips as a fallback normalisation step (#624).
        if source.suffix.lower() in (".jpg", ".jpeg"):
            converted = _sips_convert(source)
            if converted:
                try:
                    with Image.open(converted) as img:
                        img.thumbnail(size, Image.Resampling.LANCZOS)
                        if img.mode not in ("RGB", "L"):
                            img = img.convert("RGB")
                        img.save(dest, "JPEG", quality=settings.quality)
                    logger.info(f"Generated thumbnail via sips fallback: {source.name}")
                    return dest
                except Exception as fallback_exc:
                    logger.debug(
                        "sips fallback image open failed for %s: %s",
                        source.name,
                        fallback_exc,
                    )
                finally:
                    try:
                        converted.unlink(missing_ok=True)
                    except OSError as unlink_exc:
                        logger.debug(
                            "Failed to remove temporary sips conversion %s: %s",
                            converted,
                            unlink_exc,
                        )

        logger.warning(
            f"Image generation failed for {source.name} ({source.suffix}): {e}"
        )
        return None


def _generate_text_thumbnail(source: Path, dest: Path, size: tuple[int, int]) -> Path | None:
    """Render a text file's content as a thumbnail image.

    Pretty-prints JSON; shows raw text for other formats. Renders up to the
    first 60 lines in monospaced text on a white background.
    """
    _load_pil()
    if Image is None:
        return None

    try:
        raw = source.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Text thumbnail: could not read {source.name}: {e}")
        return None

    # Pretty-print JSON; strip to first 60 lines for all formats.
    if source.suffix.lower() == ".json":
        try:
            import json
            raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except Exception:
            pass  # fall through to plain text

    lines = raw.splitlines()[:60]
    text = "\n".join(lines)

    try:
        from PIL import ImageDraw, ImageFont

        w, h = size
        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Use a basic monospaced font; fall back to default if unavailable.
        font_size = max(8, w // 28)
        font = None
        for candidate in ("Courier New", "Courier", "Monaco", "monospace"):
            try:
                font = ImageFont.truetype(candidate, font_size)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        # Draw text with a small left margin
        margin = 6
        draw.text((margin, margin), text, fill=(30, 30, 30), font=font)

        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=settings.quality)
        logger.info(f"Generated text thumbnail: {dest} from {source.name}")
        return dest
    except Exception as e:
        logger.warning(f"Text thumbnail failed for {source.name}: {e}")
        return None


def _sips_convert(source: Path) -> Path | None:
    """Use macOS sips to re-encode a JPEG that PIL can't open.

    Returns a temp path to the converted file, or None if sips is unavailable
    or the conversion fails. Caller is responsible for deleting the temp file.
    """
    import subprocess
    import tempfile

    try:
        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", str(source), "--out", str(tmp)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and tmp.exists():
            return tmp
        logger.debug(
            "sips thumbnail conversion failed for %s: returncode=%s stderr=%s",
            source.name,
            result.returncode,
            result.stderr.decode("utf-8", errors="replace").strip(),
        )
    except FileNotFoundError as exc:
        logger.debug("sips thumbnail conversion unavailable for %s: %s", source.name, exc)
    except subprocess.TimeoutExpired as exc:
        logger.debug("sips thumbnail conversion timed out for %s: %s", source.name, exc)
    return None


# =============================================================================
# Batch Generation (Background)
# =============================================================================

# Background executor (lazy-initialized)
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the background executor."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.max_workers, thread_name_prefix="thumb"
            )
    return _executor


def ensure_thumbnails(
    docs: list["Document"],
    on_progress: Callable[[str, Path | None], None] | None = None,
) -> list[Future]:
    """Batch generate thumbnails in background threads.

    Args:
        docs: Documents to generate thumbnails for
        on_progress: Callback when each thumbnail is ready.
            Called with (doc_id, path) - path is None on failure.

    Returns:
        List of futures for tracking completion
    """
    executor = _get_executor()
    futures = []

    for doc in docs:
        if not _thumb_path(doc.id).exists():
            future = executor.submit(ensure_thumbnail, doc)
            if on_progress:
                # Capture doc.id for callback
                doc_id = doc.id
                future.add_done_callback(
                    lambda f, did=doc_id: on_progress(did, f.result())
                )
            futures.append(future)

    return futures


def ensure_displays(
    docs: list["Document"],
    on_progress: Callable[[str, Path | None], None] | None = None,
) -> list[Future]:
    """Batch generate display images in background threads."""
    executor = _get_executor()
    futures = []

    for doc in docs:
        if not _display_path(doc.id).exists():
            future = executor.submit(ensure_display, doc)
            if on_progress:
                doc_id = doc.id
                future.add_done_callback(
                    lambda f, did=doc_id: on_progress(did, f.result())
                )
            futures.append(future)

    return futures


# =============================================================================
# Cleanup
# =============================================================================


def cleanup_orphans(valid_doc_ids: set[str]) -> int:
    """Remove thumbnails for documents that no longer exist.

    Args:
        valid_doc_ids: Set of document IDs that still exist

    Returns:
        Number of files removed
    """
    removed = 0
    thumb_dir = settings.thumb_dir

    if not thumb_dir.exists():
        return 0

    for shard in thumb_dir.iterdir():
        if not shard.is_dir():
            continue

        for thumb_file in shard.iterdir():
            if not thumb_file.is_file():
                continue

            # Extract doc ID from filename
            doc_id = _derive_doc_id_from_thumb_name(thumb_file.stem)

            if doc_id not in valid_doc_ids:
                try:
                    thumb_file.unlink()
                    removed += 1
                except OSError as e:
                    logger.warning(f"Failed to remove {thumb_file}: {e}")

        # Remove empty shard directories
        if not any(shard.iterdir()):
            try:
                shard.rmdir()
            except OSError:
                pass

    if removed > 0:
        logger.info(f"Cleaned up {removed} orphaned thumbnails")

    return removed


def clear_all() -> int:
    """Remove all thumbnails. Use with caution.

    Returns:
        Number of files removed
    """

    thumb_dir = settings.thumb_dir
    if not thumb_dir.exists():
        return 0

    count = sum(1 for _ in thumb_dir.rglob("*.jpg"))

    shutil.rmtree(thumb_dir)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Cleared {count} thumbnails")
    return count


# =============================================================================
# Stats
# =============================================================================


def stats(package_path: Path | None = None) -> dict:
    """Get storage statistics.

    Args:
        package_path: Package path for library-specific stats.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Dict with count, size_mb, shards
    """
    if package_path:
        thumb_dir = package_path / "storage" / "thumbnails"
    else:
        thumb_dir = settings.thumb_dir

    if not thumb_dir.exists():
        return {"count": 0, "size_mb": 0.0, "shards": 0}

    count = 0
    size = 0

    for f in thumb_dir.rglob("*.jpg"):
        count += 1
        size += f.stat().st_size

    return {
        "count": count,
        "size_mb": round(size / (1024 * 1024), 2),
        "shards": sum(1 for d in thumb_dir.iterdir() if d.is_dir()),
    }


async def save_uploaded_file(
    file,
    *,
    max_bytes: int | None = None,
    content_length: int | str | None = None,
    chunk_size: int = DEFAULT_UPLOAD_CHUNK_SIZE,
) -> Path:
    """Save an uploaded FastAPI file to a temporary location.

    Args:
        file: FastAPI UploadFile object

    Returns:
        Path to saved temporary file

    Note:
        The caller is responsible for cleanup of the temp file.
        Use this with ingest_file(mode=IngestMode.COPY) which will
        copy the file to library storage.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    max_allowed = settings.max_upload_bytes if max_bytes is None else int(max_bytes)
    if max_allowed <= 0:
        raise ValueError("max_bytes must be positive")

    if content_length not in (None, ""):
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError):
            declared_length = None
        if declared_length is not None and declared_length > max_allowed:
            raise UploadTooLargeError(max_allowed)

    # Create temp file with same extension as uploaded file
    suffix = Path(file.filename).suffix if file.filename else ""

    # Create temp file (not auto-deleted, caller must clean up)
    fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix="fichero_upload_")
    temp_path = Path(temp_path)

    try:
        total_bytes = 0
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_allowed:
                    raise UploadTooLargeError(max_allowed)
                f.write(chunk)

        logger.debug(f"Saved upload to temp: {temp_path}")
        return temp_path

    except Exception as e:
        # Clean up on error
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise e


def shutdown() -> None:
    """Shutdown background executor. Call on app exit."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False)
            _executor = None


# =============================================================================
# Convenience - Document Path Properties
# =============================================================================


def expected_thumbnail_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get expected thumbnail path (may not exist yet).

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific path.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Path to expected thumbnail location
    """
    return _thumb_path(doc_id, package_path)


def expected_display_path(doc_id: str, package_path: Path | None = None) -> Path:
    """Get expected display image path (may not exist yet).

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific path.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        Path to expected display image location
    """
    return _display_path(doc_id, package_path)


def has_thumbnail(doc_id: str, package_path: Path | None = None) -> bool:
    """Check if thumbnail exists on disk.

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific check.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        True if thumbnail file exists
    """
    return _thumb_path(doc_id, package_path).exists()


def has_display(doc_id: str, package_path: Path | None = None) -> bool:
    """Check if display image exists on disk.

    Args:
        doc_id: Document ID
        package_path: Package path for library-specific check.
                     If None, uses global thumb_dir (backward compat).

    Returns:
        True if display image file exists
    """
    return _display_path(doc_id, package_path).exists()


def get_thumbnail(
    doc: "Document",
    package_path: Path | None = None,
    db: "Database | None" = None,
) -> Path | None:
    """Get thumbnail path if it exists, else None.

    Does NOT generate - use ensure_thumbnail() for that.

    Args:
        doc: Document to get thumbnail for
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    path, _, _, _ = _resolve_thumbnail_cache_candidate(
        doc,
        package_path=package_path,
        db=db,
        size=settings.thumb_size,
    )
    return path


def get_display(
    doc: "Document", package_path: Path | None = None, db: "Database | None" = None
) -> Path | None:
    """Get display image path if it exists, else None.

    Args:
        doc: Document to get display image for
        package_path: Path to .fichero package (if None, uses global base_path)
    """
    path = _display_path(doc.id, package_path)
    source = (
        resolve_edited_source(doc, db)
        if db is not None
        else resolve_source(doc, library_root=package_path)
    )
    return path if path.exists() and source and path.stat().st_mtime_ns >= source.stat().st_mtime_ns else None


# =============================================================================
# Snapshot functions — implemented in storage_snapshots.py, re-exported here
# =============================================================================

from fichero.db.storage_snapshots import (  # noqa: F401, E402 (re-exported)
    _delete_snapshot_record,
    _enforce_retention,
    _load_all_snapshot_records,
    _save_snapshot_record,
    _snapshot_records_path,
    auto_snapshot_before_risky_operation,
    delete_snapshot,
    has_scheduled_snapshots_enabled,
    list_snapshots,
    periodic_snapshot_loop,
    restore_snapshot,
    run_due_scheduled_snapshots,
    snapshot_library,
    start_periodic_snapshot_task,
    stop_periodic_snapshot_task,
)
