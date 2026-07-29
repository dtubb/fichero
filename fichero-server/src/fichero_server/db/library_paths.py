"""Shared library-path normalization helpers."""

from __future__ import annotations

import unicodedata
from pathlib import Path


def nfc_path(path: str | Path) -> str:
    """Normalize a library path string to NFC without changing meaning."""
    return unicodedata.normalize("NFC", str(path))
