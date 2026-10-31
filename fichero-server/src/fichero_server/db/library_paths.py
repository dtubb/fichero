"""Shared library-path normalization helpers."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path


def nfc_path(path: str | Path) -> str:
    """Normalize a library path string to NFC without changing meaning."""
    return unicodedata.normalize("NFC", str(path))


def canonical_library_key(path: str | Path) -> str:
    """The one spelling of a library path used as a key (#6309): NFC (the form `DatabaseManager`
    keys on; macOS hands back NFD for accented names), then symlinks resolved (`/var` vs
    `/private/var`). The change hub's subscribe and emit seams both call this and nothing else."""
    text = nfc_path(path)
    return os.path.realpath(text) if text else text
