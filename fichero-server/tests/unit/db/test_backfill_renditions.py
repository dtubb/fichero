"""Backfilling Rendition rows for documents imported before the type existed.

The interesting behaviour is what it REFUSES to do: it will not invent a role
it does not know, and it will not convert a pixel bbox against an unrecorded
frame. Both refusals are the whole point — a wrong answer here is worse than
an absent one, because a wrong one looks like data.
"""

from __future__ import annotations

from fichero_server.db.migrations.runner import MigrationRunner
from fichero_server.models import Document, Rendition


def _doc(db, **kwargs) -> Document:
    doc = Document(name=kwargs.pop("name", "page"), **kwargs)
    db.save(doc)
    return doc


class TestFromMetadataImages:
    def test_creates_one_rendition_per_image_entry(self, db):
        doc = _doc(
            db,
            metadata={
                "images": [
                    {"role": "enhanced", "source_path": "/p/e.jpg"},
                    {"role": "original", "source_path": "/p/o.jpg"},
                ],
                "preferred_image_role": "enhanced",
            },
        )

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        rows = db.query(Rendition, document_id=doc.id)
        assert result.migrated == 2
        assert sorted(r.role for r in rows) == ["enhanced", "original"]

    def test_preferred_image_role_becomes_primary(self, db):
        doc = _doc(
            db,
            metadata={
                "images": [
                    {"role": "enhanced", "source_path": "/p/e.jpg"},
                    {"role": "original", "source_path": "/p/o.jpg"},
                ],
                "preferred_image_role": "original",
            },
        )

        MigrationRunner(db).backfill_renditions_from_metadata()

        primary = [r for r in db.query(Rendition, document_id=doc.id) if r.is_primary]
        assert [r.role for r in primary] == ["original"]

    def test_malformed_entries_are_skipped_not_fatal(self, db):
        doc = _doc(
            db,
            metadata={
                "images": [
                    {"role": "enhanced", "source_path": "/p/e.jpg"},
                    {"role": "no_path"},
                    "not-a-dict",
                ]
            },
        )

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        assert result.migrated == 1
        assert len(db.query(Rendition, document_id=doc.id)) == 1


class TestFromDocumentPath:
    def test_role_is_unknown_not_original(self, db):
        """Nothing recorded what that file IS. Calling an enhanced scan
        'original' would be inventing provenance."""
        doc = _doc(db, path="/p/scan.jpg")

        MigrationRunner(db).backfill_renditions_from_metadata()

        rows = db.query(Rendition, document_id=doc.id)
        assert [r.role for r in rows] == ["unknown"]

    def test_metadata_images_wins_over_path(self, db):
        doc = _doc(
            db,
            path="/p/scan.jpg",
            metadata={"images": [{"role": "enhanced", "source_path": "/p/e.jpg"}]},
        )

        MigrationRunner(db).backfill_renditions_from_metadata()

        rows = db.query(Rendition, document_id=doc.id)
        assert [r.role for r in rows] == ["enhanced"]

    def test_document_with_neither_produces_nothing(self, db):
        _doc(db, name="a folder")

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        assert result.migrated == 0


class TestDryRunAndIdempotence:
    def test_dry_run_reports_without_writing(self, db):
        doc = _doc(db, metadata={"images": [{"role": "enhanced", "source_path": "/p/e.jpg"}]})

        result = MigrationRunner(db).backfill_renditions_from_metadata(dry_run=True)

        assert result.migrated == 1
        assert result.dry_run is True
        assert db.query(Rendition, document_id=doc.id) == []

    def test_second_run_skips_existing_paths(self, db):
        doc = _doc(db, metadata={"images": [{"role": "enhanced", "source_path": "/p/e.jpg"}]})
        runner = MigrationRunner(db)
        runner.backfill_renditions_from_metadata()

        second = runner.backfill_renditions_from_metadata()

        assert second.migrated == 0
        assert second.skipped == 1
        assert len(db.query(Rendition, document_id=doc.id)) == 1

    def test_does_not_duplicate_a_rendition_ingest_already_created(self, db):
        doc = _doc(db, metadata={"images": [{"role": "enhanced", "source_path": "/p/e.jpg"}]})
        db.save(Rendition(document_id=doc.id, role="enhanced", path="/p/e.jpg"))

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        assert result.migrated == 0
        assert len(db.query(Rendition, document_id=doc.id)) == 1


class TestRefusals:
    def test_pixel_source_bbox_is_counted_never_converted(self, db):
        """metadata['source_bbox'] is pixels against an unrecorded frame.
        Converting it would need dimensions nothing stored — so it stays
        absent and is COUNTED, so the re-anchoring pass knows the job size
        rather than discovering it."""
        _doc(db, path="/p/a.jpg", metadata={"source_bbox": [0, 0, 100, 200]})

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        assert result.details["source_bbox_unconvertible"] == 1

    def test_region_in_parent_is_left_alone(self, db):
        doc = _doc(db, path="/p/a.jpg", metadata={"source_bbox": [0, 0, 100, 200]})

        MigrationRunner(db).backfill_renditions_from_metadata()

        assert db.get(Document, doc.id).region_in_parent is None

    def test_details_separate_the_two_provenance_paths(self, db):
        _doc(db, metadata={"images": [{"role": "enhanced", "source_path": "/p/e.jpg"}]})
        _doc(db, name="plain", path="/p/plain.jpg")

        result = MigrationRunner(db).backfill_renditions_from_metadata()

        assert result.details["from_metadata_images"] == 1
        assert result.details["from_document_path"] == 1
