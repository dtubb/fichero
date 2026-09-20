"""Source-model slice 3 — Segment/SegmentPass tables and indices (#4921).

Schema on OPEN, not on first read (the ruled default, review-corrected):
`Segment`/`SegmentPass` are registered in `Database._all_schema_models()`,
so `_materialize_schema()` creates both empty tables and all eight indexes
the moment a library opens -- with every other table, additive, idempotent,
safe to run twice, and touching no existing row. A GET therefore creates
nothing (slice 1's seam test is pinned in its strong form again in
`test_segments_route.py`).

Shaped like `tests/unit/db/test_catalogue_chunk_artifact_type_migration.py`:
a real DuckDB file is hand-built with TODAY's `documents`/`artifacts` tables
and neither new table -- "a library made before this slice" -- closed, then
opened through the real `Database` class TWICE.
"""

from __future__ import annotations

import uuid

import duckdb
import pytest

from fichero_server.db import Database

pytestmark = pytest.mark.source_model

_DDL = """
CREATE TABLE documents (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    doc_type VARCHAR,
    file_type VARCHAR,
    path VARCHAR,
    status VARCHAR,
    page_content VARCHAR
);
CREATE TABLE artifacts (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR,
    artifact_type VARCHAR,
    content VARCHAR,
    data JSON,
    ocr_geometry JSON,
    version INTEGER,
    provider VARCHAR,
    model VARCHAR,
    confidence DOUBLE,
    reviewed BOOLEAN
);
"""


def _build_old_library(path) -> tuple[str, str]:
    """A real DuckDB file shaped like a library made before this slice:
    today's `documents`/`artifacts` tables, no `segments`, no
    `segment_passes`. Returns (doc_id, artifact_id)."""
    conn = duckdb.connect(str(path))
    conn.execute(_DDL)
    doc_id = uuid.uuid4().hex
    artifact_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO documents (id, name, doc_type, file_type, path, status, page_content) "
        "VALUES (?, 'old.jpg', 'file', 'image', '/old.jpg', 'completed', NULL)",
        [doc_id],
    )
    conn.execute(
        "INSERT INTO artifacts (id, document_id, artifact_type, content, version, reviewed) "
        "VALUES (?, ?, 'regions', 'alpha', 1, false)",
        [artifact_id, doc_id],
    )
    conn.close()
    return doc_id, artifact_id


def _table_names(conn) -> set[str]:
    return {t[0] for t in conn.execute("SHOW TABLES").fetchall()}


def _segment_index_names(conn) -> set[str]:
    all_indexes = {r[0] for r in conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()}
    return {name for name in all_indexes if "segment" in name}


#: Only the ORIGINAL columns of each hand-built table -- `_ensure_table`'s
#: ADD COLUMN reconciliation additively grows `documents`/`artifacts` to
#: match the current models (every other field this slice does not touch),
#: so a `SELECT *` after open legitimately gains columns. That is the
#: additive-schema promise working, not a row changing; comparing PRE-
#: EXISTING columns only is what proves no EXISTING value moved.
_DOCUMENT_COLS = "id, name, doc_type, file_type, path, status, page_content"
_ARTIFACT_COLS = "id, document_id, artifact_type, content, version, reviewed"


def _row(conn, table: str, id_: str):
    cols = _DOCUMENT_COLS if table == "documents" else _ARTIFACT_COLS
    return conn.execute(f"SELECT {cols} FROM {table} WHERE id = ?", [id_]).fetchall()


class TestSchemaArrivesAtOpen:
    def test_opening_an_old_library_twice_adds_the_tables_and_indexes_touches_no_row(
        self, tmp_path,
    ):
        db_path = tmp_path / "old.duckdb"
        doc_id, artifact_id = _build_old_library(db_path)

        # Snapshot via a raw connection before ANY Database ever opens this
        # file, so the snapshot cannot itself be influenced by this slice.
        conn = duckdb.connect(str(db_path))
        before_tables = _table_names(conn)
        assert "segments" not in before_tables
        assert "segment_passes" not in before_tables
        before_doc_row = _row(conn, "documents", doc_id)
        before_artifact_row = _row(conn, "artifacts", artifact_id)
        conn.close()

        db1 = Database(db_path)
        try:
            tables_after_first_open = _table_names(db1.conn)
            assert "segments" in tables_after_first_open
            assert "segment_passes" in tables_after_first_open
            assert db1.conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
            assert db1.conn.execute("SELECT COUNT(*) FROM segment_passes").fetchone()[0] == 0
            indexes_after_first_open = _segment_index_names(db1.conn)
            for expected in (
                "idx_segments_document_id", "idx_segments_pass_id",
                "idx_segments_parent_segment_id", "idx_segments_kind",
                "idx_segments_tile", "idx_segments_doc_kind",
                "idx_segment_passes_document_id", "idx_segment_passes_run_id",
                "idx_segmentmatchs_from_segment_id", "idx_segmentmatchs_to_segment_id",
                "idx_segmentforwardings_old_segment_id", "idx_segmentcarrys_match_id",
            ):
                assert expected in indexes_after_first_open, expected
            assert _row(db1.conn, "documents", doc_id) == before_doc_row
            assert _row(db1.conn, "artifacts", artifact_id) == before_artifact_row

            # #4922 second look: the append sequence (a native DuckDB
            # sequence, created at open alongside the indexes) exists,
            # works and is monotonic; `segmentforwardings` carries the
            # `sequence` column.
            first_value = db1.conn.execute("SELECT nextval('segment_forwarding_seq')").fetchone()[0]
            second_value = db1.conn.execute("SELECT nextval('segment_forwarding_seq')").fetchone()[0]
            assert second_value > first_value
            forwarding_cols = {
                r[0] for r in db1.conn.execute("DESCRIBE segmentforwardings").fetchall()
            }
            assert "sequence" in forwarding_cols
        finally:
            db1.close()

        # Open a SECOND time: nothing raised, nothing duplicated, nothing
        # about the old rows moved.
        db2 = Database(db_path)
        try:
            tables_after_second_open = _table_names(db2.conn)
            assert tables_after_second_open == tables_after_first_open
            assert db2.conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
            assert db2.conn.execute("SELECT COUNT(*) FROM segment_passes").fetchone()[0] == 0
            assert _segment_index_names(db2.conn) == indexes_after_first_open
            assert _row(db2.conn, "documents", doc_id) == before_doc_row
            assert _row(db2.conn, "artifacts", artifact_id) == before_artifact_row

            # The sequence survives a close/reopen and keeps counting up --
            # never resets, never repeats a value already given out.
            third_value = db2.conn.execute("SELECT nextval('segment_forwarding_seq')").fetchone()[0]
            assert third_value > second_value
        finally:
            db2.close()

    def test_the_seam_still_returns_the_same_provisional_segments_as_before(self, client, db):
        """The new tables existing from the moment the library opened must
        not change what an UNCONVERTED document's slice-1 seam returns."""
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
        from fichero_server.models import Artifact, DocType, Document, FileType, Status
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import bbox_and_tile_from_anchor
        from fichero_server.models import Segment, SegmentPass

        doc = Document(
            name="legacy.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/legacy.jpg", status=Status.completed,
        )
        db.save(doc)
        geometry = OCRGeometryResult(
            text="alpha", provider="apple_vision",
            boxes=[OCRGeometryBox(text="alpha", bbox=[0.1, 0.1, 0.2, 0.05], level="word")],
        )
        artifact = Artifact(document_id=doc.id, artifact_type="regions", content="alpha", ocr_geometry=geometry)
        db.save(artifact)

        before = client.get(f"/api/segments/document/{doc.id}").json()
        assert before["segments"][0]["provisional"] is True
        assert before["segments"][0]["id"] == f"legacy:{artifact.id}:0"

        # A real pass/segment on a DIFFERENT document -- the coexistence
        # slice 3 introduces -- must not change this document's answer.
        other_doc = Document(
            name="other.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/other.jpg", status=Status.completed,
        )
        db.save(other_doc)
        anchor = SourceAnchor(document_id=other_doc.id, rect=[0.3, 0.3, 0.1, 0.1])
        pass_row = SegmentPass(document_id=other_doc.id, name="real", provenance_kind=ProvenanceKind.human)
        db.save(pass_row)
        x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
        db.save(Segment(
            document_id=other_doc.id, pass_id=pass_row.id, kind="word", anchor=anchor,
            bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
            doc_kind=f"{other_doc.id}:word",
            provenance_kind=ProvenanceKind.human,
        ))

        after = client.get(f"/api/segments/document/{doc.id}").json()
        assert after == before, "an unconverted document's seam answer changed"


class TestSequenceMigrationOnAnExistingForwardingTable:
    """#4922 second look: a library already carrying `segmentforwardings`
    rows written BEFORE the `sequence` column existed (this branch, one
    round ago) must open cleanly, backfill nothing, and still order those
    rows correctly against new ones."""

    def test_a_pre_sequence_note_has_a_null_sequence_after_open(self, tmp_path):
        from fichero_server.models.segments import SegmentForwarding

        db_path = tmp_path / "pre_sequence.duckdb"

        # A library already upgraded to segmentforwardings, but from BEFORE
        # the sequence column existed: build the table by hand, without it.
        conn = duckdb.connect(str(db_path))
        conn.execute(_DDL)
        conn.execute(
            "CREATE TABLE segmentforwardings (id VARCHAR PRIMARY KEY, document_id VARCHAR, "
            "old_segment_id VARCHAR, kind VARCHAR, new_segment_ids JSON, actor VARCHAR, "
            "audit_id VARCHAR, reason VARCHAR, created_at TIMESTAMP)"
        )
        old_note_id = uuid.uuid4().hex
        old_segment_id = uuid.uuid4().hex
        target_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO segmentforwardings "
            "(id, document_id, old_segment_id, kind, new_segment_ids, actor, audit_id, reason, created_at) "
            "VALUES (?, 'doc-1', ?, 'merged', ?, 'daniel', 'old-audit', NULL, now())",
            [old_note_id, old_segment_id, f'["{target_id}"]'],
        )
        conn.close()

        db = Database(db_path)
        try:
            forwarding_cols = {r[0] for r in db.conn.execute("DESCRIBE segmentforwardings").fetchall()}
            assert "sequence" in forwarding_cols
            old_row = db.get(SegmentForwarding, old_note_id)
            assert old_row is not None
            assert old_row.sequence is None
            # Opening at all does not crash, and no backfill invents a value.
            assert db.conn.execute(
                "SELECT sequence FROM segmentforwardings WHERE id = ?", [old_note_id],
            ).fetchone()[0] is None
        finally:
            db.close()

    def test_a_new_note_outranks_a_null_sequence_note_for_the_same_id(self):
        """A `SegmentForwarding` row read back with `sequence=None` (as a
        pre-migration row would) is treated as OLDER than one with a real
        sequence, regardless of what `created_at` alone would say."""
        from datetime import timedelta

        from fichero_server.core.timeutil import utc_now
        from fichero_server.models.segments import SegmentForwarding, _newest

        now = utc_now()
        old_note = SegmentForwarding(
            document_id="doc-1", old_segment_id="seg-1", kind="merged",
            new_segment_ids=["seg-2"], actor="daniel", audit_id="a1",
            created_at=now + timedelta(hours=1),  # LATER by clock time
            sequence=None,  # but pre-dates the column
        )
        new_note = SegmentForwarding(
            document_id="doc-1", old_segment_id="seg-1", kind="restored",
            new_segment_ids=[], actor="daniel", audit_id="a2",
            created_at=now,  # EARLIER by clock time
            sequence=1,  # but written after (a null sequence is always oldest)
        )
        assert _newest([old_note, new_note]) is new_note
