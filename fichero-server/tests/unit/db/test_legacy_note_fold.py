"""Folding the old `models.Note` rows into `Annotation(kind=note)`.

The duplicate type is deleted, so these tests write the legacy shape as RAW
SQL — which is also exactly how such a row would exist in a real library:
written by an older build, its columns still present on the shared `notes`
table because `_ensure_table` never drops anything.
"""

from __future__ import annotations

from fichero_server.db.migrations.runner import MigrationRunner, MigrationStatus
from fichero_server.models.anchors import AnchorSpace
from fichero_server.models.knowledge import Annotation, AnnotationKind, Note


def _legacy_columns(db) -> None:
    """Recreate the columns an older build left on `notes`."""
    db.conn.execute("CREATE TABLE IF NOT EXISTS notes (id VARCHAR PRIMARY KEY)")
    for column, ddl in (
        ("target_type", "VARCHAR"), ("target_id", "VARCHAR"),
        ("content", "VARCHAR"), ("note_type", "VARCHAR"),
        ("bbox", "INTEGER[]"),
        ("created_at", "TIMESTAMP"), ("updated_at", "TIMESTAMP"),
    ):
        try:
            db.conn.execute(f"ALTER TABLE notes ADD COLUMN {column} {ddl}")
        except Exception:
            pass  # already present


def _insert_legacy(db, note_id, target_type="Document", target_id="doc-1",
                   content="an old note", note_type="comment", bbox=None):
    db.conn.execute(
        "INSERT INTO notes (id, target_type, target_id, content, note_type, bbox) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [note_id, target_type, target_id, content, note_type, bbox],
    )


class TestTheCommonCase:
    def test_a_library_with_no_legacy_rows_reports_why(self, db):
        """Nothing ever constructed `models.Note`, so this is what almost every
        real library will do. It must say so rather than return a bare zero."""
        result = MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert result.status is MigrationStatus.completed
        assert result.migrated == 0
        assert "reason" in result.details

    def test_a_real_note_is_left_alone(self, db):
        """`knowledge.Note` rows share the table and must not be touched — they
        have no `target_type`, which is exactly how they are told apart."""
        note = Note(title="Context", body="a real note")
        db.save(note)

        MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert db.get(Note, note.id) is not None


class TestConversion:
    def test_a_legacy_row_becomes_an_annotation(self, db):
        _legacy_columns(db)
        _insert_legacy(db, "note-1")

        result = MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert result.migrated == 1
        annotation = db.get(Annotation, "note-1")
        assert annotation is not None
        assert annotation.kind is AnnotationKind.note
        assert annotation.text == "an old note"
        assert annotation.document_id == "doc-1"

    def test_the_pixel_bbox_is_recorded_AS_PIXELS(self, db):
        """The old field was documented as pixel ints. Reading it as fractions
        would be the defect this program removed."""
        _legacy_columns(db)
        _insert_legacy(db, "note-2", bbox=[10, 20, 30, 40])

        MigrationRunner(db).migrate_legacy_notes_to_annotations()

        anchor = db.get(Annotation, "note-2").anchor
        assert anchor is not None
        assert anchor.space is AnchorSpace.pixel
        assert anchor.rect == [10.0, 20.0, 30.0, 40.0]

    def test_an_unmappable_note_type_is_kept_verbatim(self, db):
        """AnnotationKind has no `correction`. Flattening it onto the nearest
        member would silently reclassify the note."""
        _legacy_columns(db)
        _insert_legacy(db, "note-3", note_type="correction")

        MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert db.get(Annotation, "note-3").metadata["legacy_note_type"] == "correction"

    def test_the_row_leaves_the_notes_table(self, db):
        _legacy_columns(db)
        _insert_legacy(db, "note-4")

        MigrationRunner(db).migrate_legacy_notes_to_annotations()

        rows = db.conn.execute(
            "SELECT count(*) FROM notes WHERE id = 'note-4'"
        ).fetchone()
        assert rows[0] == 0


class TestRefusalsAndIdempotence:
    def test_an_artifact_targeted_note_is_skipped_and_COUNTED(self, db):
        """Annotation anchors to documents. Re-pointing an Artifact note at a
        document it was never about would be worse than leaving it."""
        _legacy_columns(db)
        _insert_legacy(db, "note-5", target_type="Artifact", target_id="art-1")

        result = MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert result.migrated == 0
        assert result.skipped == 1
        assert any("note-5" in s for s in result.details["skipped_targets"])
        assert db.get(Annotation, "note-5") is None

    def test_running_twice_converts_nothing_extra(self, db):
        _legacy_columns(db)
        _insert_legacy(db, "note-6")
        runner = MigrationRunner(db)

        first = runner.migrate_legacy_notes_to_annotations()
        second = runner.migrate_legacy_notes_to_annotations()

        assert (first.migrated, second.migrated) == (1, 0)
        assert len(db.query(Annotation, document_id="doc-1")) == 1

    def test_a_dry_run_changes_nothing(self, db):
        _legacy_columns(db)
        _insert_legacy(db, "note-7")

        result = MigrationRunner(db).migrate_legacy_notes_to_annotations(dry_run=True)

        assert result.migrated == 1  # what WOULD move
        assert db.get(Annotation, "note-7") is None
        still_there = db.conn.execute(
            "SELECT count(*) FROM notes WHERE id = 'note-7'"
        ).fetchone()
        assert still_there[0] == 1


class TestALibraryWithoutTheTable:
    def test_a_missing_notes_table_is_completed_not_failed(self, db):
        """PRAGMA raises a CatalogException on a table that never existed, so
        the migration reported FAILED for a library that simply had nothing to
        migrate. A no-op must not look like a fault — an operator reading a
        migration report cannot tell the difference."""
        db.conn.execute("DROP TABLE IF EXISTS notes")

        result = MigrationRunner(db).migrate_legacy_notes_to_annotations()

        assert result.status is MigrationStatus.completed
        assert result.error_message is None
        assert result.details["reason"] == "no notes table in this library"
