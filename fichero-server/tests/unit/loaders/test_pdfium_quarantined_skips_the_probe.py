"""A quarantined pdfium copy is not probed for a minute (2026-10-10, found in the Dev Embedded app).

In the sandbox the engine could neither hard-link the bundled pdfium to kreuzberg's bind path nor strip the
quarantine from its copy, and kreuzberg's probe then hung its whole 60 s timeout on the first PDF of every run
before the fitz split took over. A quarantined copy now means kreuzberg is off for the run at once.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="extended attributes as macOS sets them")


def _quarantine(path) -> None:
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    value = b"0081;00000000;Fichero;"
    assert libc.setxattr(str(path).encode(), b"com.apple.quarantine", value, len(value), 0, 0) == 0


def test_a_quarantined_pdfium_turns_kreuzberg_off_without_probing(tmp_path, monkeypatch):
    from fichero_server.loaders import kreuzberg_cache

    bind = tmp_path / "kreuzberg-pdfium" / "libpdfium.dylib"
    bind.parent.mkdir()
    bind.write_bytes(b"not really a library")
    _quarantine(bind)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(kreuzberg_cache, "_KREUZBERG_PDF_USABLE", None)

    probed = []  # recorded, not raised: the probe's caller swallows exceptions
    monkeypatch.setattr(kreuzberg_cache, "_run_worker", lambda env, timeout: probed.append(timeout) or (0, b""))
    assert kreuzberg_cache.kreuzberg_pdf_usable() is False
    assert probed == [], "the 60 s probe ran against a quarantined pdfium"


def test_a_clean_pdfium_is_still_probed(tmp_path, monkeypatch):
    from fichero_server.loaders import kreuzberg_cache

    bind = tmp_path / "kreuzberg-pdfium" / "libpdfium.dylib"
    bind.parent.mkdir()
    bind.write_bytes(b"x")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(kreuzberg_cache, "_KREUZBERG_PDF_USABLE", None)
    calls = []
    monkeypatch.setattr(kreuzberg_cache, "_run_worker", lambda env, timeout: calls.append(timeout) or (0, b""))
    assert kreuzberg_cache.kreuzberg_pdf_usable() is True and calls == [60]
