"""Regression (#2183): workflow source tools must emit ABSOLUTE on-disk paths.

COPY ingests store a library-relative ``files/fi/<hash>_<name>.pdf`` path; downstream
vision/transcribe tools open it directly, so it must be resolved against the library
root, not the engine CWD. LINK ingests (absolute path outside the library) must still
emit their raw path — never worse than before.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.models import Document
from fichero_server.workflows.tools.sources import _resolve_abs_path


def _make_library(tmp_path) -> Path:
    lib = tmp_path / "Test.fichero"
    (lib / "files" / "fi").mkdir(parents=True)
    return lib


def test_copy_ingest_relative_path_resolves_to_absolute(tmp_path) -> None:
    """A library-relative COPY path resolves to the absolute on-disk file."""
    lib = _make_library(tmp_path)
    pdf = lib / "files" / "fi" / "abcd1234_doc.pdf"
    pdf.write_bytes(b"%PDF-1.2 test")

    doc = Document(id="d1", name="doc.pdf", path="files/fi/abcd1234_doc.pdf")
    result = _resolve_abs_path(doc, str(lib))

    assert Path(result).is_absolute(), f"expected absolute, got {result!r}"
    assert Path(result) == pdf
    assert Path(result).exists()


def test_unresolvable_path_falls_back_to_raw(tmp_path) -> None:
    """When resolve_source can't resolve (missing/out-of-root), return the raw
    stored path unchanged — strictly never worse than before."""
    lib = _make_library(tmp_path)
    # A library-relative path whose file does NOT exist on disk.
    doc = Document(id="d2", name="missing.pdf", path="files/fi/nope_missing.pdf")
    result = _resolve_abs_path(doc, str(lib))
    assert result == "files/fi/nope_missing.pdf"


def test_none_library_root_returns_raw_path(tmp_path) -> None:
    """No library root → can't re-root a relative path; return it unchanged."""
    doc = Document(id="d3", name="x.pdf", path="files/fi/x.pdf")
    assert _resolve_abs_path(doc, None) == "files/fi/x.pdf"
