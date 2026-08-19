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


def _entity_sidecar(tmp_path, image_name: str, entities: list[dict]) -> None:
    import json

    (tmp_path / image_name).write_bytes(b"img")
    (tmp_path / f"{image_name}.entities.json").write_text(
        json.dumps({"schema": "fichero-page-entities-v0-proposed", "entities": entities})
    )


def _file_doc(doc_id: str, tmp_path, image_name: str):
    from fichero_server.models import DocType, Document

    return Document(
        id=doc_id,
        name=image_name,
        doc_type=DocType.file,
        metadata={"source_path": str(tmp_path / image_name)},
    )


def test_entity_sidecar_payload_dedupes_and_scopes_pages(tmp_path):
    """x.jpg.entities.json beside x.jpg becomes ONE bulk-upsert payload:
    deduped by canonical name across the batch, each entity carrying the
    ids of the pages it appeared on (the manifest importer's shape)."""
    from fichero_server.importers.ingest import entity_sidecar_payload

    _entity_sidecar(tmp_path, "p1.jpg", [
        {"name": "Istmina", "type": "location", "raw_type": "GPE",
         "sources": ["andy-ner"], "start": 10, "end": 17},
        {"name": "N. C. Marshall", "type": "person"},
        {"name": "", "type": "person"},               # nameless → skipped
        {"name": "Skimmer", "type": "steamboat"},     # unknown type → other
    ])
    _entity_sidecar(tmp_path, "p2.jpg", [
        {"name": "Istmina", "type": "location"},
    ])
    docs = [_file_doc("d1", tmp_path, "p1.jpg"), _file_doc("d2", tmp_path, "p2.jpg")]

    payload = entity_sidecar_payload(docs)

    by_name = {e["canonical_name"]: e for e in payload}
    assert set(by_name) == {"Istmina", "N. C. Marshall", "Skimmer"}
    assert by_name["Istmina"]["source_document_ids"] == ["d1", "d2"]
    assert by_name["Istmina"]["entity_type"] == "location"
    assert by_name["Istmina"]["metadata"]["raw_type"] == "GPE"
    assert by_name["Skimmer"]["entity_type"] == "other"
    assert by_name["N. C. Marshall"]["source_document_ids"] == ["d1"]


def test_entity_sidecar_payload_skips_failed_missing_and_malformed(tmp_path):
    from fichero_server.models import Status
    from fichero_server.importers.ingest import entity_sidecar_payload

    # No sidecar at all.
    (tmp_path / "plain.jpg").write_bytes(b"img")
    plain = _file_doc("d1", tmp_path, "plain.jpg")
    # Malformed sidecar: warns, never raises (documents already committed).
    (tmp_path / "bad.jpg").write_bytes(b"img")
    (tmp_path / "bad.jpg.entities.json").write_text("{not json")
    bad = _file_doc("d2", tmp_path, "bad.jpg")
    # Failed-ingest stub must not contribute entities.
    _entity_sidecar(tmp_path, "failed.jpg", [{"name": "Ghost", "type": "person"}])
    failed = _file_doc("d3", tmp_path, "failed.jpg")
    failed.status = Status.failed

    assert entity_sidecar_payload([plain, bad, failed]) == []


def test_import_actions_route_sidecar_entities_through_bulk_upsert(monkeypatch, tmp_path):
    """The import.folder/import.file actions hand the payload to ONE audited
    entity.bulk_upsert with the SAME ctx (library-scoped emit), and skip the
    invoke entirely when the batch carries no sidecars."""
    from types import SimpleNamespace

    from fichero_server.api.routes.ingest import core

    _entity_sidecar(tmp_path, "p1.jpg", [{"name": "Istmina", "type": "location"}])
    doc = _file_doc("d1", tmp_path, "p1.jpg")

    calls = []

    def fake_invoke(db, name, params, ctx):
        calls.append((name, params, ctx))
        return SimpleNamespace(result={"created_ids": ["e1"], "reused_ids": [], "warnings": []})

    monkeypatch.setattr(core.registry, "invoke", fake_invoke)
    ctx = object()
    core._upsert_sidecar_entities("db", [doc], ctx)

    assert len(calls) == 1
    name, params, seen_ctx = calls[0]
    assert name == "entity.bulk_upsert"
    assert params["entities"][0]["canonical_name"] == "Istmina"
    assert seen_ctx is ctx

    # Empty batch → no action invoke at all.
    core._upsert_sidecar_entities("db", [], ctx)
    assert len(calls) == 1
