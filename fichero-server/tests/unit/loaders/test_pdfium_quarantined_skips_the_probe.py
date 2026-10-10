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
    monkeypatch.delenv("APP_SANDBOX_CONTAINER_ID", raising=False)
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
    monkeypatch.delenv("APP_SANDBOX_CONTAINER_ID", raising=False)
    monkeypatch.setattr(kreuzberg_cache, "_KREUZBERG_PDF_USABLE", None)
    calls = []
    monkeypatch.setattr(kreuzberg_cache, "_run_worker", lambda env, timeout: calls.append(timeout) or (0, b""))
    assert kreuzberg_cache.kreuzberg_pdf_usable() is True and calls == [60]


# The sandboxed app (2026-10-10, 07:53: macOS showed "libpdfium.dylib Not Opened"). kreuzberg always extracts its
# own pdfium to $TMPDIR, which the sandbox quarantines, and its probe's worker cannot start there. So in the
# sandbox kreuzberg never touches pdfium: no copy, no probe, and a quarantined leftover is removed.


def test_in_the_sandbox_kreuzberg_pdf_is_off_without_a_probe(tmp_path, monkeypatch):
    from fichero_server.loaders import kreuzberg_cache

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("APP_SANDBOX_CONTAINER_ID", "app.fichero.fichero")
    monkeypatch.setattr(kreuzberg_cache, "_KREUZBERG_PDF_USABLE", None)
    probed = []
    monkeypatch.setattr(kreuzberg_cache, "_run_worker", lambda env, timeout: probed.append(timeout) or (0, b""))

    assert kreuzberg_cache.kreuzberg_pdf_usable() is False
    assert probed == [], "the probe ran in the sandbox, where kreuzberg would extract a quarantined pdfium"
    assert not (tmp_path / "kreuzberg-pdfium").exists()


def test_in_the_sandbox_prepare_writes_no_copy_and_removes_a_quarantined_one(tmp_path, monkeypatch):
    from fichero_server.loaders import kreuzberg_cache

    bind = tmp_path / "kreuzberg-pdfium" / "libpdfium.dylib"
    bind.parent.mkdir()
    bind.write_bytes(b"left from an earlier run")
    _quarantine(bind)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("APP_SANDBOX_CONTAINER_ID", "app.fichero.fichero")
    linked = []
    monkeypatch.setattr(kreuzberg_cache.os, "link", lambda a, b: linked.append(b))
    monkeypatch.setattr(kreuzberg_cache.shutil, "copy2", lambda a, b: linked.append(b))

    kreuzberg_cache.prepare_pdfium()

    assert not bind.exists(), "a quarantined pdfium stayed where something could load it"
    assert linked == [], "the sandboxed engine wrote a pdfium copy, which macOS would quarantine"
