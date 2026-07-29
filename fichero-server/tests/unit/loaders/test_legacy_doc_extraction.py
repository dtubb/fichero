"""Legacy binary .doc extracts again (#4215).

kreuzberg rejects VALID pre-2007 Word files with

    Failed to open DOC as OLE container: Malformed MiniFAT
    (mini sector 0 pointed to twice)

The fixture is not the problem — it is a genuine OLE2 Composite Document
written by macOS `textutil`, which reads it back correctly. So a standard
macOS producer emits `.doc` files this engine rejected, and `.doc` is exactly
what older archival material tends to be.

The fix is a fallback to `textutil` — already on every Mac, and the same
component that wrote the file. These tests pin BOTH halves: that the fallback
works, and that it is scoped to `.doc` so no other format quietly starts
routing around the primary extractor.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from fichero_server.loaders.document_loader import DocumentLoader
from tests.fixture_paths import sample_file

FIXTURE = (
    sample_file("sample.doc")
)

macos_only = pytest.mark.skipif(
    sys.platform != "darwin" or not Path("/usr/bin/textutil").exists(),
    reason="the .doc fallback is macOS textutil",
)


def _load(path: Path):
    return asyncio.run(DocumentLoader().load(path))


def test_the_fixture_is_a_real_ole2_document():
    """Magic D0 CF 11 E0 — not a renamed .docx, so the failure was real."""
    assert FIXTURE.read_bytes().startswith(b"\xd0\xcf\x11\xe0")


def test_the_primary_extractor_still_rejects_it():
    """Pins WHY the fallback exists. If this ever starts passing, kreuzberg
    fixed its OLE reader and the fallback can be reconsidered."""
    from kreuzberg import extract_file_sync

    try:
        content = (extract_file_sync(str(FIXTURE)).content or "").strip()
    except Exception as exc:
        assert "MiniFAT" in str(exc) or "OLE" in str(exc), exc
    else:
        pytest.skip(f"kreuzberg now reads legacy .doc: {content[:60]!r}")


@macos_only
class TestTheFallback:
    def test_legacy_doc_text_is_extracted(self):
        content = _load(FIXTURE)

        assert "Asprilla" in (content.text or "")

    def test_the_fallback_is_recorded_not_hidden(self):
        """A silent substitution is the failure mode this repo keeps hitting:
        the document must say which extractor produced its text and why."""
        content = _load(FIXTURE)

        assert content.metadata["extractor"] == "textutil"
        assert "MiniFAT" in content.metadata["extractor_fallback_reason"]

    def test_a_corrupt_doc_still_fails_loudly(self, tmp_path):
        """The fallback must not turn every .doc failure into an empty
        success — a file neither extractor can read still raises."""
        broken = tmp_path / "broken.doc"
        broken.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 512)

        with pytest.raises(Exception):
            _load(broken)

    def test_the_fallback_is_scoped_to_doc(self, tmp_path, monkeypatch):
        """Other formats must keep raising, not silently reroute."""
        called: list[Path] = []
        monkeypatch.setattr(
            DocumentLoader,
            "_load_with_textutil",
            lambda self, path, **kw: called.append(path),
        )
        broken = tmp_path / "broken.docx"
        broken.write_bytes(b"PK\x03\x04not-a-zip")

        with pytest.raises(Exception):
            _load(broken)

        assert not called, "textutil must only be tried for .doc"


@macos_only
def test_an_ingested_doc_carries_its_text(db, test_package, tmp_path):
    """End to end — the user-visible symptom was an empty extraction."""
    import shutil

    from fichero_server.importers.ingest import IngestMode, ingest_file

    source = tmp_path / "petition.doc"
    shutil.copy(FIXTURE, source)

    doc = ingest_file(
        source,
        mode=IngestMode.LINK,
        db=db,
        package_path=Path(test_package),
        extract_text=True,
        auto_embed=False,
    )

    assert "Asprilla" in (doc.page_content or "")
    assert doc.metadata.get("text_extracted") is True
