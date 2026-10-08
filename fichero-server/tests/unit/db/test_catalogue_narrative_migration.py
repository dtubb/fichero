"""A narrative an earlier Catalogue run wrote over a document's text becomes its description reading
(#5599, ruled 2026-10-08; `source.extract.catalogue-never-overwrites-text`).

WHY: before #5599 the catalogue wrote its narrative into the target's page_content, so a folder
catalogued on old code still shows the narrative as its text. The migration moves it into a
description reading (the shape the catalogue writes now) and clears the folder's text; a file's
text is its own transcription, so a file is described but its text is left and reported; a text a
person changed or saved is never touched. Real projects (Marshall) hold years of work, so every
test here also pins what is NOT changed, and that a second run changes nothing.

Nothing touches a real library: every package is made in tmp_path.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fichero_server.db import Database, db_manager
from fichero_server.db.migrations.runner import (
    MigrationRunner,
    MigrationRunRecord,
    move_catalogue_narratives_on_open,
)
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document
from fichero_server.models.knowledge import MutationLog, ProvenanceKind

NARRATIVE = "## Summary\n\nLetters of the Marshall family, 1890-1912, about the farm.\n"


def _db(tmp_path: Path) -> Database:
    return Database(path=tmp_path / "Lib.fichero" / "fichero.duckdb")


def _catalogued(db: Database, *, doc_type=DocType.folder, text=NARRATIVE, run_id="run-1",
                metadata=None, name="Box 1") -> tuple[Document, Artifact]:
    """A document as an old Catalogue run left it: its narrative artifact, and (when `text` is the
    narrative) the same narrative written over its page_content."""
    doc = Document(name=name, doc_type=doc_type, page_content=text, metadata=metadata or {})
    db.save(doc)
    art = Artifact(document_id=doc.id, artifact_type="catalogue.narrative", content=NARRATIVE.strip(),
                   provider="anthropic", model="claude", run_id=run_id)
    db.save(art)
    return doc, art


def _descriptions(db: Database, doc_id: str) -> list[ContentRepresentation]:
    return [r for r in db.query(ContentRepresentation, document_id=doc_id)
            if r.kind == "description" and r.retracted_at is None]


def test_an_overwritten_folder_gets_a_description_reading_its_text_cleared_and_logged(tmp_path):
    db = _db(tmp_path)
    folder, art = _catalogued(db)

    result = MigrationRunner(db).move_catalogue_narratives_to_descriptions()

    assert result.migrated == 1 and result.details["moved_document_ids"] == [folder.id]
    [reading] = _descriptions(db, folder.id)
    assert reading.content == NARRATIVE.strip()
    assert reading.derived_from_artifact_id == art.id
    assert reading.producer_run_id == "run-1", "the catalogue's own run is the provenance"
    assert reading.provenance_kind is ProvenanceKind.workflow, "a machine's reading, never a person's"
    assert db.get(Document, folder.id).page_content is None
    # Recorded: the run summary and one mutation per change, so it can be reported and rolled back.
    run_id = result.details["run_id"]
    [record] = db.query(MigrationRunRecord, run_id=run_id)
    assert record.migrated == 1
    logged = {(m.entity_type, m.operation.value) for m in db.query(MutationLog, run_id=run_id)}
    assert logged == {("ContentRepresentation", "create"), ("Document", "update")}
    # And the log keeps what the text was, so a rollback brings it back.
    MigrationRunner(db).rollback(run_id)
    assert db.get(Document, folder.id).page_content == NARRATIVE
    assert _descriptions(db, folder.id) == []


def test_an_artifact_with_no_run_is_marked_as_the_migrations(tmp_path):
    db = _db(tmp_path)
    folder, _ = _catalogued(db, run_id=None)
    result = MigrationRunner(db).move_catalogue_narratives_to_descriptions()
    [reading] = _descriptions(db, folder.id)
    assert reading.producer_run_id == result.details["run_id"]
    assert reading.producer_run_id.startswith("catalogue_narrative_")


def test_a_person_edited_folder_is_never_touched(tmp_path):
    db = _db(tmp_path)
    changed = "My own description of the box: letters, a ledger, two photographs."
    edited, _ = _catalogued(db, text=changed, name="Edited")
    saved, _ = _catalogued(db, name="Saved", metadata={"page_content_user_edited_at": "2026-09-01T00:00:00"})

    result = MigrationRunner(db).move_catalogue_narratives_to_descriptions()

    assert db.get(Document, edited.id).page_content == changed
    assert _descriptions(db, edited.id) == []
    assert db.get(Document, saved.id).page_content == NARRATIVE, "a text a person saved stays theirs"
    assert _descriptions(db, saved.id) == []
    assert result.migrated == 0
    assert result.details["left_person_edited_document_ids"] == [saved.id]
    assert db.query(MigrationRunRecord) == [], "nothing changed, so no run is recorded"


def test_a_file_target_is_described_but_its_text_left_and_reported(tmp_path):
    db = _db(tmp_path)
    pdf, _ = _catalogued(db, doc_type=DocType.file, name="letter.pdf")

    result = MigrationRunner(db).move_catalogue_narratives_to_descriptions()

    assert db.get(Document, pdf.id).page_content == NARRATIVE, "a file's text is its own; never cleared"
    assert len(_descriptions(db, pdf.id)) == 1
    assert result.migrated == 0
    assert result.details["left_file_document_ids"] == [pdf.id]


def test_running_twice_changes_nothing_the_second_time(tmp_path):
    db = _db(tmp_path)
    folder, _ = _catalogued(db, name="Folder")
    pdf, _ = _catalogued(db, doc_type=DocType.file, name="letter.pdf")
    runner = MigrationRunner(db)
    runner.move_catalogue_narratives_to_descriptions()
    snapshot = (
        db.get(Document, folder.id).model_dump(), db.get(Document, pdf.id).model_dump(),
        len(db.query(ContentRepresentation)), len(db.query(MutationLog)), len(db.query(MigrationRunRecord)),
    )

    second = runner.move_catalogue_narratives_to_descriptions()

    assert second.migrated == 0 and second.details["readings_made"] == 0
    assert second.audit_id is None
    assert (
        db.get(Document, folder.id).model_dump(), db.get(Document, pdf.id).model_dump(),
        len(db.query(ContentRepresentation)), len(db.query(MutationLog)), len(db.query(MigrationRunRecord)),
    ) == snapshot
    assert second.details["left_file_document_ids"] == [pdf.id], "the file is still reported"


def test_an_existing_description_holding_the_text_is_not_doubled(tmp_path):
    db = _db(tmp_path)
    folder, art = _catalogued(db)
    db.save(ContentRepresentation(document_id=folder.id, kind="description", content=NARRATIVE.strip(),
                                  source_anchor={"document_id": folder.id}, derived_from_artifact_id=art.id,
                                  provenance_kind=ProvenanceKind.workflow))
    MigrationRunner(db).move_catalogue_narratives_to_descriptions()
    assert len(_descriptions(db, folder.id)) == 1
    assert db.get(Document, folder.id).page_content is None


def test_a_document_with_no_narrative_artifact_is_never_read(tmp_path):
    db = _db(tmp_path)
    plain = Document(name="Page", doc_type=DocType.folder, page_content=NARRATIVE)
    db.save(plain)
    db.save(Artifact(document_id=plain.id, artifact_type="catalogue.timeline", content=NARRATIVE.strip()))
    result = MigrationRunner(db).move_catalogue_narratives_to_descriptions()
    assert result.migrated == 0 and db.get(Document, plain.id).page_content == NARRATIVE


def test_the_open_report_names_what_moved_and_what_was_left(tmp_path, caplog):
    db = _db(tmp_path)
    _catalogued(db, name="Folder")
    pdf, _ = _catalogued(db, doc_type=DocType.file, name="letter.pdf")
    with caplog.at_level(logging.INFO, logger="fichero_server.db.migrations.runner"):
        move_catalogue_narratives_on_open(db)
    [line] = [r.getMessage() for r in caplog.records if "Catalogue narrative migration" in r.getMessage()]
    assert "moved 1 folder text(s)" in line and "left 1 file(s)" in line and pdf.id in line


def test_a_library_opened_on_new_code_migrates_once_through_the_real_open(tmp_path):
    package = tmp_path / "Old Project.fichero"
    db = db_manager.get_database(package, create=True)
    folder, _ = _catalogued(db)
    db_manager.close_database(package)

    db = db_manager.get_database(package)
    try:
        assert db.get(Document, folder.id).page_content is None
        assert len(_descriptions(db, folder.id)) == 1
        records = db.query(MigrationRunRecord)
        assert len(records) == 1
    finally:
        db_manager.close_database(package)

    db = db_manager.get_database(package)
    try:
        assert len(_descriptions(db, folder.id)) == 1
        assert len(db.query(MigrationRunRecord)) == 1, "a second open changes nothing"
    finally:
        db_manager.close_database(package)
