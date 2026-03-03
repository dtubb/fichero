"""
File ingestion for Fichero.

Two modes:
- LINK: Reference external files with macOS bookmarks (default)
- COPY: Import files into library storage (uses APFS clones when possible)

Text extraction:
- extract_text=True uses loaders to extract text from PDFs, DOCX, etc.
- Extracted text goes into doc.page_content for search indexing

Usage:
    from fichero.ingest import ingest_file, ingest_folder, IngestMode

    # Link external file (default - uses bookmarks)
    doc = ingest_file(Path("/Users/bob/docs/letter.pdf"))

    # With text extraction for search
    doc = ingest_file(Path("/path/to/doc.pdf"), extract_text=True)

    # Copy into library
    doc = ingest_file(Path("/path/to/file.jpg"), mode=IngestMode.COPY)

    # Batch import folder
    docs = ingest_folder(Path("/path/to/folder"), mode=IngestMode.LINK)

    # Ingest with specific parent folder
    folder = db.query(Document, doc_type=DocType.folder)[0]
    doc = ingest_file(path, parent_id=folder.id)
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import logging
import mimetypes
import shutil
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator
from uuid import uuid4

from fichero.models import Document, DocType, FileType, Status

if TYPE_CHECKING:
    from fichero.db import Database

logger = logging.getLogger(__name__)


# File types that support text extraction via loaders
_TEXT_EXTRACTABLE = {
    FileType.pdf,
    FileType.word,
    FileType.text,
    FileType.epub,
}


# =============================================================================
# Enums
# =============================================================================

class IngestMode(str, Enum):
    """How to handle file ingestion."""
    LINK = "link"  # Reference with macOS bookmark (file stays in place)
    COPY = "copy"  # Copy into library storage (file duplicated)
    MOVE = "move"  # Move into library storage (file relocated, original deleted)


# =============================================================================
# File Type Detection
# =============================================================================

# Extension to FileType mapping
_FILE_TYPE_MAP = {
    # Images
    ".jpg": FileType.image,
    ".jpeg": FileType.image,
    ".png": FileType.image,
    ".gif": FileType.image,
    ".webp": FileType.image,
    ".tiff": FileType.image,
    ".tif": FileType.image,
    ".bmp": FileType.image,
    ".heic": FileType.image,
    ".heif": FileType.image,
    ".jxl": FileType.image,
    ".avif": FileType.image,
    # RAW formats
    ".raw": FileType.image,
    ".cr2": FileType.image,
    ".cr3": FileType.image,
    ".nef": FileType.image,
    ".arw": FileType.image,
    ".dng": FileType.image,
    ".orf": FileType.image,
    ".rw2": FileType.image,
    # PDF
    ".pdf": FileType.pdf,
    # Audio
    ".mp3": FileType.audio,
    ".wav": FileType.audio,
    ".m4a": FileType.audio,
    ".aac": FileType.audio,
    ".flac": FileType.audio,
    ".ogg": FileType.audio,
    ".wma": FileType.audio,
    # Video
    ".mp4": FileType.video,
    ".mov": FileType.video,
    ".avi": FileType.video,
    ".mkv": FileType.video,
    ".webm": FileType.video,
    # Text
    ".txt": FileType.text,
    ".md": FileType.text,
    ".rst": FileType.text,
    ".rtf": FileType.text,
    # Word
    ".doc": FileType.word,
    ".docx": FileType.word,
    ".odt": FileType.word,
    # Ebooks
    ".epub": FileType.epub,
    ".mobi": FileType.epub,
}


def detect_file_type(path: Path) -> FileType:
    """Detect file type from extension.

    Args:
        path: Path to file

    Returns:
        Detected FileType, or FileType.other if unknown
    """
    suffix = path.suffix.lower()
    file_type = _FILE_TYPE_MAP.get(suffix, FileType.other)
    logger.debug(f"Detected file type for {path.name}: suffix='{suffix}' -> type={file_type.value}")
    return file_type


# =============================================================================
# Single File Ingestion
# =============================================================================

def _resolve_default_db():
    """
    Resolve legacy module-level db fallback for callers/tests that do not
    pass an explicit db argument.
    """
    from fichero import db as db_module

    candidate = getattr(db_module, "db", None)
    return candidate if hasattr(candidate, "save") else None


def ingest_file(
    path: Path,
    mode: IngestMode = IngestMode.LINK,
    parent_id: str | None = None,
    extract_metadata: bool = True,
    extract_text: bool = False,
    auto_embed: bool = False,
    save: bool = True,
    db: "Database | None" = None,
    package_path: Path | None = None,
) -> Document:
    """Ingest a single file.

    Args:
        path: Path to file
        mode: LINK (bookmark) or COPY (import)
        parent_id: Parent collection ID
        extract_metadata: Run metadata extraction (size, checksum, etc.)
        extract_text: Use loaders to extract text content for search
        auto_embed: Create embedding for search after saving
        save: If True, save to database
        db: Database instance (required if save=True)
        package_path: Library package path for COPY mode (stores files in {package}/files/)

    Returns:
        Created Document
    """
    from fichero.bookmarks import create_bookmark

    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    if save and db is None:
        db = _resolve_default_db()
    if save and db is None:
        raise ValueError("db parameter required when save=True")

    # Determine file type
    file_type = detect_file_type(path)

    # Build metadata
    metadata: dict = {}

    if mode in (IngestMode.COPY, IngestMode.MOVE):
        # Copy file into library storage
        dest = _copy_to_library(path) if package_path is None else _copy_to_library(path, package_path)
        doc = Document(
            name=path.name,
            path=str(dest),
            doc_type=DocType.file,
            file_type=file_type,
            parent_id=parent_id,
            metadata=metadata,
            status=Status.pending,
        )

        # For MOVE mode, delete original file after successful copy
        if mode == IngestMode.MOVE:
            try:
                path.unlink()
                logger.info("Moved file (original deleted): %s", path)
            except Exception as e:
                logger.warning("Failed to delete original file after move: %s", e)
                # Continue anyway - file was successfully copied
    else:
        # Link with bookmark
        bookmark = create_bookmark(path)
        if bookmark:
            metadata["bookmark"] = base64.b64encode(bookmark).decode()

        doc = Document(
            name=path.name,
            path=str(path),
            doc_type=DocType.file,
            file_type=file_type,
            parent_id=parent_id,
            metadata=metadata,
            status=Status.pending,
        )

    # Extract metadata if requested
    if extract_metadata:
        _extract_file_metadata(doc, path)

    # Extract text content using loaders
    if extract_text and file_type in _TEXT_EXTRACTABLE:
        _extract_text_content(doc, path)

    if save:
        db.save(doc)
        logger.info("Ingested: %s (%s)", path.name, mode.value)

        # Create embedding for search
        if auto_embed and doc.page_content:
            db.embed(doc)

    return doc


def _copy_to_library(source: Path, package_path: Path | None = None) -> Path:
    """Copy file to library storage.

    Uses APFS clonefile() for instant copies on same volume.
    Falls back to shutil.copy2() for cross-volume copies.

    Args:
        source: Source file path
        package_path: Library package path (stores in {package}/files/)
                     If None, falls back to global storage for backward compat

    Returns:
        Destination path in library
    """
    from fichero.storage import settings

    # Create sharded destination directory
    shard = source.stem[:2].lower() if len(source.stem) >= 2 else "00"

    if package_path:
        # Multi-library: Store in package
        dest_dir = package_path / "files" / shard
    else:
        # Backward compatibility: Global storage
        dest_dir = settings.base_path / "imported" / shard

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    unique_prefix = uuid4().hex[:8]
    dest = dest_dir / f"{unique_prefix}_{source.name}"

    # Try APFS clone first (macOS only, instant, no disk space until modified)
    if _try_apfs_clone(source, dest):
        logger.debug("APFS clone: %s", source.name)
        return dest

    # Fallback to regular copy
    shutil.copy2(source, dest)
    logger.debug("Copied: %s", source.name)
    return dest


def _try_apfs_clone(source: Path, dest: Path) -> bool:
    """Attempt APFS clonefile() for instant copy.

    Returns True if successful, False otherwise.
    """
    try:
        libc = ctypes.CDLL("libc.dylib")
        # clonefile(const char *src, const char *dst, int flags)
        result = libc.clonefile(
            str(source).encode(),
            str(dest).encode(),
            0  # flags = 0
        )
        return result == 0
    except Exception:
        return False


def _extract_file_metadata(doc: Document, path: Path) -> None:
    """Extract basic metadata from file.

    Updates doc.metadata in place.
    """
    try:
        stat = path.stat()
        doc.metadata["file_size"] = stat.st_size

        # MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            doc.metadata["mime_type"] = mime_type

        # Checksum (for deduplication)
        doc.metadata["checksum"] = _file_checksum(path)

        # Image dimensions (if applicable)
        if doc.file_type == FileType.image:
            _extract_image_metadata(doc, path)

    except Exception as e:
        logger.warning("Metadata extraction failed for %s: %s", path, e)


def _file_checksum(path: Path, algorithm: str = "sha256") -> str:
    """Calculate file checksum.

    Reads file in chunks to handle large files.
    """
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _extract_image_metadata(doc: Document, path: Path) -> None:
    """Extract image dimensions and other metadata."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            doc.metadata["width"] = img.width
            doc.metadata["height"] = img.height

            # EXIF data
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()
                if exif:
                    # Extract common EXIF fields
                    # 306 = DateTime, 271 = Make, 272 = Model
                    if 306 in exif:
                        doc.metadata["exif_datetime"] = exif[306]
                    if 271 in exif:
                        doc.metadata["exif_make"] = exif[271]
                    if 272 in exif:
                        doc.metadata["exif_model"] = exif[272]

    except ImportError:
        logger.debug("Pillow not available for image metadata")
    except Exception as e:
        logger.debug("Image metadata extraction failed: %s", e)


def _extract_text_content(doc: Document, path: Path) -> None:
    """Extract text content using loaders.

    Uses the unified loader system to extract text from PDFs, DOCX, etc.
    Sets doc.page_content with extracted text.
    """
    try:
        from fichero.loaders import load_media

        # Run async loader in sync context
        content = _run_async(load_media(path))

        if content and content.text:
            doc.page_content = content.text
            doc.metadata["text_extracted"] = True
            doc.metadata["text_length"] = len(content.text)
            logger.debug("Extracted %s chars from %s", len(content.text), path.name)
        else:
            doc.metadata["text_extracted"] = False

    except ImportError as e:
        logger.debug("Loader not available: %s", e)
    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", path, e)
        doc.metadata["text_extracted"] = False


def _run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Already in async context - use thread pool
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# =============================================================================
# Folder Ingestion
# =============================================================================

def ingest_folder(
    folder: Path,
    mode: IngestMode = IngestMode.LINK,
    parent_id: str | None = None,
    recursive: bool = True,
    create_collection: bool = True,
    extract_text: bool = False,
    auto_embed: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    db: "Database | None" = None,
    package_path: Path | None = None,
) -> list[Document]:
    """Ingest all files from a folder.

    Args:
        folder: Folder to ingest
        mode: LINK or COPY
        parent_id: Parent collection ID (overrides create_collection)
        recursive: If True, ingest subdirectories
        create_collection: If True, create a collection for the folder
        extract_text: Extract text content using loaders
        auto_embed: Create embeddings for search
        on_progress: Progress callback (current, total)
        db: Database instance (required)
        package_path: Library package path for COPY mode

    Returns:
        List of created Documents
    """
    folder = Path(folder).resolve()

    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")

    if db is None:
        db = _resolve_default_db()
    if db is None:
        raise ValueError("db parameter is required")

    # Create folder if requested
    folder_id = parent_id
    if create_collection and not parent_id:
        folder_doc = Document(
            name=folder.name,
            path=str(folder),
            doc_type=DocType.folder,
            status=Status.completed,
        )
        db.save(folder_doc)
        folder_id = folder_doc.id
        logger.info(f"Created folder: {folder.name}")

    # Gather files
    if recursive:
        files = list(folder.rglob("*"))
    else:
        files = list(folder.glob("*"))

    # Filter to actual files
    files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    total = len(files)
    documents = []

    for i, file_path in enumerate(files):
        try:
            # For recursive, create subfolder structure
            subfolder_id = folder_id
            if recursive and file_path.parent != folder:
                subfolder_id = _ensure_folder_hierarchy(
                    file_path.parent,
                    folder,
                    folder_id,
                    db,
                )

            doc = ingest_file(
                file_path,
                mode=mode,
                parent_id=subfolder_id,
                extract_metadata=True,
                extract_text=extract_text,
                auto_embed=auto_embed,
                save=True,
                db=db,
                package_path=package_path,
            )
            documents.append(doc)

        except Exception as e:
            logger.warning(f"Failed to ingest {file_path}: {e}")

        if on_progress:
            on_progress(i + 1, total)

    logger.info(f"Ingested {len(documents)} files from {folder.name}")
    return documents


def _ensure_folder_hierarchy(
    subfolder: Path,
    base_folder: Path,
    base_id: str,
    db: "Database",
) -> str:
    """Ensure folder hierarchy exists in database.

    Args:
        subfolder: Path to subfolder
        base_folder: Base folder path
        base_id: ID of base folder document
        db: Database instance

    Returns:
        The ID of the deepest folder Document.
    """

    # Get relative path
    rel_path = subfolder.relative_to(base_folder)

    current_parent = base_id
    for part in rel_path.parts:
        # Check if folder already exists
        existing = db.query(Document, parent_id=current_parent, name=part)
        if existing:
            current_parent = existing[0].id
        else:
            # Create folder
            folder_doc = Document(
                name=part,
                doc_type=DocType.folder,
                parent_id=current_parent,
                status=Status.completed,
            )
            db.save(folder_doc)
            current_parent = folder_doc.id

    return current_parent


# =============================================================================
# File Discovery
# =============================================================================

def discover_files(
    folder: Path,
    extensions: set[str] | None = None,
    recursive: bool = True,
) -> Iterator[Path]:
    """Discover files in a folder.

    Args:
        folder: Folder to search
        extensions: Set of extensions to include (e.g., {".jpg", ".png"})
        recursive: If True, search subdirectories

    Yields:
        Path objects for each matching file
    """
    folder = Path(folder)

    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for path in folder.glob(pattern):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        yield path


def count_files(
    folder: Path,
    extensions: set[str] | None = None,
    recursive: bool = True,
) -> int:
    """Count files in a folder.

    Args:
        folder: Folder to count
        extensions: Set of extensions to include
        recursive: If True, count subdirectories

    Returns:
        Number of matching files
    """
    return sum(1 for _ in discover_files(folder, extensions, recursive))


# =============================================================================
# Deduplication
# =============================================================================

def find_duplicates(documents: list[Document]) -> dict[str, list[Document]]:
    """Find duplicate documents by checksum.

    Args:
        documents: List of documents to check

    Returns:
        Dict mapping checksum to list of duplicate documents
    """
    by_checksum: dict[str, list[Document]] = {}

    for doc in documents:
        checksum = doc.metadata.get("checksum")
        if checksum:
            if checksum not in by_checksum:
                by_checksum[checksum] = []
            by_checksum[checksum].append(doc)

    # Return only actual duplicates (more than one document)
    return {k: v for k, v in by_checksum.items() if len(v) > 1}


__all__ = [
    "IngestMode",
    "detect_file_type",
    "ingest_file",
    "ingest_folder",
    "discover_files",
    "count_files",
    "find_duplicates",
]
