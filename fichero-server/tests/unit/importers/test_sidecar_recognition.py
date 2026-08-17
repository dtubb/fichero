"""Sidecar suffixes are skipped by folder ingest, never imported as documents.

The Marshall staging convention (2026-08-16, _import/README.md) puts three
derived sidecars beside every page; before these suffixes were recognized a
plain folder ingest created ~450 junk text/JSON documents per diary.
"""
from pathlib import Path

from fichero_server.importers.ingest import _is_sidecar_file


def test_staging_sidecar_suffixes_are_recognized(tmp_path: Path) -> None:
    for name in (
        "NCM_Diary_1923IMG_010_part_1.jpg.iffy.json",
        "NCM_Diary_1923IMG_010_part_1.jpg.transcript.txt",
        "NCM_Diary_1923IMG_010_part_1.jpg.entities.json",
        "NCM_Diary_1923IMG_010_part_1.jpg.renditions.json",
        "photo.xmp",
    ):
        assert _is_sidecar_file(tmp_path / name), name


def test_primary_documents_are_not_sidecars(tmp_path: Path) -> None:
    for name in (
        "NCM_Diary_1923IMG_010_part_1.jpg",
        # A plain transcript folder's .txt is a real document — only the
        # double-suffix ".jpg.transcript.txt" form is a sidecar.
        "transcript.txt",
        "notes.json",
    ):
        assert not _is_sidecar_file(tmp_path / name), name


def test_iffy_original_date_dates_the_document_on_arrival() -> None:
    """A sidecar stating original_date makes the document DATED at ingest
    (Daniel 2026-08-17, maps corpus: '1715' must not read as Undated until
    an Extract Dates run). Never overwrites an existing date."""
    from fichero_server.importers.ingest import _apply_iffy_to_document
    from fichero_server.models import Document

    doc = Document(id="m1", name="cartagena_harbor_1715.jpg")
    _apply_iffy_to_document(doc, {"iffy_original_date": "1715", "iffy_identifier": "MP-PANAMA,122"})
    assert doc.date_original == "1715"
    assert doc.date_jdn is not None and doc.date_jdn_end is not None
    assert doc.date_jdn < doc.date_jdn_end, "a bare year spans the whole year"
    assert doc.date_meta and doc.date_meta.get("source") == "iffy_sidecar"
    assert doc.metadata.get("iffy_identifier") == "MP-PANAMA,122"

    # Existing dates are never clobbered by the sidecar.
    dated = Document(id="m2", name="x.jpg", date_original="March 3, 1920", date_jdn=2422387)
    _apply_iffy_to_document(dated, {"iffy_original_date": "1715"})
    assert dated.date_original == "March 3, 1920"
    assert dated.date_jdn == 2422387

    # An unparseable date stays honest: metadata only, no guessed columns.
    fuzzy = Document(id="m3", name="y.jpg")
    _apply_iffy_to_document(fuzzy, {"iffy_original_date": "sometime colonial"})
    assert fuzzy.date_original is None and fuzzy.date_jdn is None


def test_transcript_sidecar_lands_in_page_content(tmp_path, monkeypatch):
    """x.jpg.transcript.txt beside x.jpg becomes the document's text on a
    PLAIN folder/file ingest (no manifest needed), and machine extraction
    is skipped so OCR never competes with the curated transcript."""
    from fichero_server.importers import ingest as ingest_mod

    image = tmp_path / "NCM_Diary_1923IMG_010_part_1.jpg"
    image.write_bytes(b"not-an-image")
    (tmp_path / "NCM_Diary_1923IMG_010_part_1.jpg.transcript.txt").write_text(
        "SATURDAY, FEBRUARY 3, 1923\nCame Assiga here on way to Fatmina.\n"
    )

    class _Db:
        saved = []

        def save(self, doc):
            self.saved.append(doc)

        def embed(self, doc):
            pass

    called = []
    monkeypatch.setattr(ingest_mod, "_extract_text_content", lambda *a, **k: called.append(a))
    doc = ingest_mod.ingest_file(
        image, db=_Db(), mode=ingest_mod.IngestMode.LINK,
        extract_text=True, auto_embed=False, extract_metadata=False,
    )
    assert doc.page_content and doc.page_content.startswith("SATURDAY, FEBRUARY 3, 1923")
    assert doc.metadata.get("transcript_source") == "sidecar"
    assert not called, "extraction must not run over a sidecar transcript"
