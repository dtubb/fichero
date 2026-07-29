"""
Fichero Media Loaders

Unified system for loading various media formats into normalized MediaContent.
Each format uses the optimal library:

- Images (JPG, PNG, TIFF, etc.): PIL/Pillow
- RAW images (CR2, NEF, ARW): rawpy
- HEIC/HEIF (iPhone): heif-convert system tool
- PDFs → Images: PyMuPDF (fast, no poppler dependency)
- PDFs → Text: Kreuzberg (when text extraction is needed)
- Office docs (DOCX, XLSX, PPTX): Kreuzberg
- EPUB: Kreuzberg
- IIIF manifests: Custom HTTP loader
- Audio: Future (Whisper)
- Video: Future (ffmpeg frame extraction)

Usage:
    from fichero_server.loaders import load_media, MediaContent

    # Load any supported file
    content = await load_media("/path/to/file.pdf")

    # Access normalized output
    print(content.text)      # Extracted text (if any)
    print(content.images)    # List of PIL Images
    print(content.metadata)  # Format-specific metadata
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero_server.loaders.base import MediaContent, MediaLoader

# Which submodule owns each re-exported name. Resolved on first access (#3985).
#
# These re-exports used to be eager, so importing ANYTHING from this package —
# including the `kreuzberg_cache` submodule, which api.main imports at engine
# startup purely for a cache-migration side effect — ran unified.py and its
# image/pdf loaders, dragging PIL (and rawpy/PyMuPDF) onto the boot path. PIL is
# only needed when media is actually loaded. Mirrors workflows/__init__ (#3950).
# Importing a real submodule (`from fichero_server.loaders import kreuzberg_cache`)
# still works: __getattr__ raises AttributeError for unknown names, so the
# import machinery falls through to importing the submodule directly.
_LAZY_EXPORTS: dict[str, str] = {
    "MediaContent": "base",
    "MediaLoader": "base",
    "load_media": "unified",
    "UnifiedLoader": "unified",
}


def __getattr__(name: str) -> Any:
    """Resolve a re-export from its owning submodule on first access (PEP 562)."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"fichero_server.loaders.{module_name}")
    value = getattr(module, name)
    globals()[name] = value  # cache: __getattr__ won't fire for this name again
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "MediaContent",
    "MediaLoader",
    "load_media",
    "UnifiedLoader",
]
