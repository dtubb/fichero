"""prepare_pdfium (#4555): the sandboxed engine's pdfium must be loadable.

Live-diagnosed 2026-08-09: kreuzberg's extracted libpdfium.dylib carried
com.apple.quarantine (stamped by the sandboxed engine's own write), and
Gatekeeper refuses quarantined ad-hoc code regardless of entitlements —
"library load disallowed by system policy", every PDF imported textless.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
import types
from pathlib import Path

import pytest


def _set_quarantine(path):
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    value = b"0082;0;test;"
    # macOS setxattr(path, name, value, size, position, options)
    assert libc.setxattr(str(path).encode(), b"com.apple.quarantine", value, len(value), 0, 0) == 0


def _has_quarantine(path):
    out = subprocess.run(["/usr/bin/xattr", str(path)], capture_output=True, text=True)
    return "com.apple.quarantine" in out.stdout

from fichero_server.loaders import kreuzberg_cache


@pytest.fixture
def fake_wheel(tmp_path, monkeypatch):
    """A fake kreuzberg wheel dir with a bundled dylib + isolated TMPDIR."""
    wheel = tmp_path / "wheel" / "kreuzberg"
    wheel.mkdir(parents=True)
    (wheel / "libpdfium.dylib").write_bytes(b"MACHO-FAKE")
    fake = types.ModuleType("kreuzberg")
    fake.__file__ = str(wheel / "__init__.py")
    monkeypatch.setitem(sys.modules, "kreuzberg", fake)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "t"))
    (tmp_path / "t").mkdir()
    return tmp_path / "t"


def test_links_the_bundled_dylib_when_extraction_is_missing(fake_wheel):
    kreuzberg_cache.prepare_pdfium()

    target = fake_wheel / "kreuzberg-pdfium" / "libpdfium.dylib"
    # A HARDLINK to the signed bundle: same inode, so no quarantine xattr
    # can exist on it separately, and no symlink for AMFI to kill over.
    assert not target.is_symlink()
    wheel_dylib = Path(sys.modules["kreuzberg"].__file__).parent / "libpdfium.dylib"
    assert target.stat().st_ino == wheel_dylib.stat().st_ino
    assert target.read_bytes() == b"MACHO-FAKE"


def test_replaces_a_quarantined_extraction_with_the_bundle_link(fake_wheel):
    target_dir = fake_wheel / "kreuzberg-pdfium"
    target_dir.mkdir()
    target = target_dir / "libpdfium.dylib"
    target.write_bytes(b"EXTRACTED")
    if sys.platform == "darwin":
        _set_quarantine(target)
        assert _has_quarantine(target), "fixture failed to quarantine"

    kreuzberg_cache.prepare_pdfium()

    # The doomed quarantined extraction is REPLACED by the bundle hardlink.
    assert not target.is_symlink()
    assert target.read_bytes() == b"MACHO-FAKE"


def test_never_raises_when_the_wheel_has_no_dylib(tmp_path, monkeypatch):
    fake = types.ModuleType("kreuzberg")
    fake.__file__ = str(tmp_path / "empty" / "__init__.py")
    (tmp_path / "empty").mkdir()
    monkeypatch.setitem(sys.modules, "kreuzberg", fake)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "t2"))
    (tmp_path / "t2").mkdir()

    kreuzberg_cache.prepare_pdfium()  # must not raise

    assert not (tmp_path / "t2" / "kreuzberg-pdfium" / "libpdfium.dylib").exists()


class TestKreuzbergPdfGate:
    """kreuzberg_pdf_usable (2026-08-09): a hanging pdfium bind froze the
    whole engine (sync FFI holds the GIL), so PDF extraction is probed in a
    throwaway SUBPROCESS and kreuzberg is skipped for PDFs when it fails."""

    def _reset(self):
        kreuzberg_cache._KREUZBERG_PDF_USABLE = None

    def test_probe_success_enables(self, monkeypatch):
        self._reset()
        import subprocess as sp

        monkeypatch.setattr(
            sp, "run",
            lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b""),
        )
        assert kreuzberg_cache.kreuzberg_pdf_usable() is True

    def test_probe_failure_disables_and_is_cached(self, monkeypatch):
        self._reset()
        calls = []
        import subprocess as sp

        def fake_run(*a, **k):
            calls.append(1)
            return types.SimpleNamespace(returncode=2, stderr=b"library load disallowed")

        monkeypatch.setattr(sp, "run", fake_run)
        assert kreuzberg_cache.kreuzberg_pdf_usable() is False
        assert kreuzberg_cache.kreuzberg_pdf_usable() is False
        assert len(calls) == 1, "the probe must run once per process"

    def test_probe_hang_disables_without_wedging(self, monkeypatch):
        self._reset()
        import subprocess as sp

        def hang(*a, **k):
            raise sp.TimeoutExpired(cmd="probe", timeout=60)

        monkeypatch.setattr(sp, "run", hang)
        assert kreuzberg_cache.kreuzberg_pdf_usable() is False
