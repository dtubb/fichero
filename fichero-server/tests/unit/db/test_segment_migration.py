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
            assert "segmentversions" in tables_after_first_open
            assert db1.conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 0
            assert db1.conn.execute("SELECT COUNT(*) FROM segment_passes").fetchone()[0] == 0
            assert db1.conn.execute("SELECT COUNT(*) FROM segmentversions").fetchone()[0] == 0
            indexes_after_first_open = _segment_index_names(db1.conn)
            for expected in (
                "idx_segments_document_id", "idx_segments_pass_id",
                "idx_segments_parent_segment_id", "idx_segments_kind",
                "idx_segments_tile", "idx_segments_doc_kind",
                "idx_segment_passes_document_id", "idx_segment_passes_run_id",
                "idx_segmentmatchs_from_segment_id", "idx_segmentmatchs_to_segment_id",
                "idx_segmentforwardings_old_segment_id", "idx_segmentcarrys_match_id",
                "idx_segmentversions_segment_id",
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


class TestOldLibraryWithRealResearchData:
    """test-audit B3, 2026-09-20: the schema-arrival test above is a
    two-table toy (its one artifact has `ocr_geometry` NULL; its
    before/after comparison omits `ocr_geometry` and `data`). This class
    builds a library the way TODAY'S code actually makes one -- a document,
    an artifact with REAL `ocr_geometry` boxes (one machine, one
    hand-drawn) and `data`, an annotation, a knowledge claim with a source
    anchor, and an audit chain from two real actions, through the real
    `Database`/action-registry path -- closes it, opens it through
    `Database` TWICE more, and compares EVERY column of EVERY pre-existing
    row, byte for byte, plus that the audit chain still verifies each time.
    This is the test that protects real research data across ordinary
    re-opens (the anchor that backs `verify_audit_chain` is keyed to this
    exact file path, in `settings.base_path` -- not something a copy to
    another path could carry, so the library is built and reopened at ONE
    path throughout, exactly as a real library on disk is)."""

    _CARRIED_TABLES = ("documents", "artifacts", "annotations", "knowledgeclaims", "actionaudits")

    def _build_library(self, db_path) -> dict:
        """Write real rows the way today's code does: model saves for the
        document/artifact/claim, real actions (audited, chained) for the
        annotation create-then-update."""
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
        from fichero_server.models import Artifact, DocType, Document, FileType, Status
        from fichero_server.models.knowledge import KnowledgeClaim

        db = Database(db_path)
        try:
            doc = Document(
                name="marshall-1933-p4.jpg", doc_type=DocType.file, file_type=FileType.image,
                path="/marshall-1933-p4.jpg", status=Status.completed,
            )
            db.save(doc)

            geometry = OCRGeometryResult(
                text="the heirs filed suit",
                provider="apple_vision",
                boxes=[
                    OCRGeometryBox(
                        text="the heirs filed suit", bbox=[0.1, 0.1, 0.6, 0.05], level="line",
                        char_start=0, char_end=20, provider="apple_vision",
                    ),
                    OCRGeometryBox(
                        text="[margin note]", bbox=[0.8, 0.1, 0.15, 0.05], level="word",
                        provider="user", source="manual",
                    ),
                ],
            )
            artifact = Artifact(
                document_id=doc.id, artifact_type="regions", content="the heirs filed suit",
                ocr_geometry=geometry, provider="apple_vision", confidence=0.94,
                data={"page_number": 4, "collection": "marshall-diaries"},
            )
            db.save(artifact)

            claim = KnowledgeClaim(
                text="The heirs filed suit in 1933.",
                source_document_id=doc.id,
                source_excerpt="the heirs filed suit",
                source_char_start=0,
                source_char_end=20,
                time_start="1933-01-01",
                time_end="1933-12-31",
            )
            db.save(claim)

            ctx = ActionContext(actor="daniel", library_path=str(db_path.parent))
            create_result = registry.invoke(
                db, "annotation.create",
                {
                    "document_id": doc.id, "kind": "highlight",
                    "char_start": 0, "char_end": 20, "color": "#FFDD00",
                },
                ctx,
            )
            annotation_id = create_result.result["id"]
            registry.invoke(
                db, "annotation.update",
                {"annotation_id": annotation_id, "update": {"text": "check against the deed"}},
                ctx,
            )

            return {
                "doc_id": doc.id, "artifact_id": artifact.id,
                "claim_id": claim.id, "annotation_id": annotation_id,
            }
        finally:
            db.close()

    def _snapshot(self, conn) -> dict[str, list[tuple]]:
        return {
            table: conn.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
            for table in self._CARRIED_TABLES
        }

    def test_opening_a_real_library_twice_touches_no_pre_existing_row(self, tmp_path):
        from fichero_server.actions.audit_chain import verify_audit_chain

        db_path = tmp_path / "real_library.duckdb"
        ids = self._build_library(db_path)

        db0 = Database(db_path)
        try:
            assert "segments" in _table_names(db0.conn)
            assert "segment_passes" in _table_names(db0.conn)
            before_snapshot = self._snapshot(db0.conn)
            for table in self._CARRIED_TABLES:
                assert before_snapshot[table], f"{table} must carry at least one pre-existing row"
            assert verify_audit_chain(db0).ok
        finally:
            db0.close()

        db1 = Database(db_path)
        try:
            after_first_reopen = self._snapshot(db1.conn)
            assert after_first_reopen == before_snapshot
            assert verify_audit_chain(db1).ok
        finally:
            db1.close()

        db2 = Database(db_path)
        try:
            after_second_open = self._snapshot(db2.conn)
            assert after_second_open == before_snapshot
            assert verify_audit_chain(db2).ok

            # Byte-for-byte at the model layer too, not just raw SQL columns
            # -- catches a value that round-trips through SQL unchanged but
            # decodes differently (a JSON field re-typed, for instance).
            from fichero_server.models import Artifact, Document
            from fichero_server.models.knowledge import Annotation, KnowledgeClaim

            doc_after = db2.get(Document, ids["doc_id"])
            artifact_after = db2.get(Artifact, ids["artifact_id"])
            claim_after = db2.get(KnowledgeClaim, ids["claim_id"])
            annotation_after = db2.get(Annotation, ids["annotation_id"])
            assert doc_after.name == "marshall-1933-p4.jpg"
            assert artifact_after.ocr_geometry.boxes[1].provider == "user"
            assert artifact_after.data == {"page_number": 4, "collection": "marshall-diaries"}
            assert claim_after.source_char_start == 0 and claim_after.source_char_end == 20
            assert annotation_after.text == "check against the deed"
        finally:
            db2.close()

    def test_a_real_pre_migration_library_with_real_data_migrates_clean(self, tmp_path):
        """test-audit B3, strengthened, 2026-09-20: the case that protects
        real research data is a library from BEFORE the segment tables
        existed, not one that already has them. Built at ONE path (the
        anchor problem above still applies), the SAME way today's code
        makes a library, then -- through a raw connection on that same
        file -- every table/index/sequence slices 3-5 added is DROPPED
        (the list comes from `Database._all_schema_models()` itself, never
        hand-typed, so a new segment-domain model is covered automatically).
        Reopening through `Database` TWICE must bring them all back empty,
        leave every pre-existing row byte-identical, and the audit chain
        must still verify after each open."""
        from fichero_server.actions.audit_chain import verify_audit_chain
        from fichero_server.models.segments import (
            Segment,
            SegmentCarry,
            SegmentForwarding,
            SegmentMatch,
            SegmentPass,
            SegmentVersion,
        )

        db_path = tmp_path / "pre_segments_real_library.duckdb"
        self._build_library(db_path)

        probe = Database(db_path)
        segment_models = (Segment, SegmentPass, SegmentMatch, SegmentForwarding, SegmentCarry, SegmentVersion)
        segment_tables = {probe._table_name(model) for model in segment_models}
        probe.close()
        assert segment_tables == {
            "segments", "segment_passes", "segmentmatchs",
            "segmentforwardings", "segmentcarrys", "segmentversions",
        }

        conn = duckdb.connect(str(db_path))
        segment_indexes = _segment_index_names(conn)
        assert segment_indexes, "expected segment indexes to exist before dropping"
        before_snapshot = self._snapshot(conn)
        for table in self._CARRIED_TABLES:
            assert before_snapshot[table]
        for index_name in segment_indexes:
            conn.execute(f'DROP INDEX "{index_name}"')
        for table in segment_tables:
            conn.execute(f'DROP TABLE "{table}"')
        conn.execute("DROP SEQUENCE IF EXISTS segment_forwarding_seq")
        tables_before_reopen = _table_names(conn)
        assert not (tables_before_reopen & segment_tables), "segment tables must actually be gone"
        conn.close()

        db1 = Database(db_path)
        try:
            tables_after = _table_names(db1.conn)
            assert segment_tables <= tables_after
            for table in segment_tables:
                assert db1.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
            assert _segment_index_names(db1.conn) == segment_indexes
            after_first_reopen = self._snapshot(db1.conn)
            assert after_first_reopen == before_snapshot
            assert verify_audit_chain(db1).ok
            first_seq_value = db1.conn.execute(
                "SELECT nextval('segment_forwarding_seq')"
            ).fetchone()[0]
        finally:
            db1.close()

        db2 = Database(db_path)
        try:
            after_second_reopen = self._snapshot(db2.conn)
            assert after_second_reopen == before_snapshot
            assert verify_audit_chain(db2).ok
            second_seq_value = db2.conn.execute(
                "SELECT nextval('segment_forwarding_seq')"
            ).fetchone()[0]
            assert second_seq_value > first_seq_value
        finally:
            db2.close()


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


class TestVersionColumnMigrationOnAnExistingSegmentsTable:
    """#4923: a `segments` table from before `version` existed (this
    branch, two rounds ago -- `version` shipped with slice 3, but the
    reconciliation path is the same one every additive column relies on)
    must open cleanly, backfill the column to the model's own default
    (1), and the row must be genuinely updatable afterward."""

    def test_a_pre_version_column_segment_reads_back_as_version_one_and_is_updatable(
        self, tmp_path,
    ):
        from fichero_server.models import Segment

        db_path = tmp_path / "pre_version.duckdb"

        conn = duckdb.connect(str(db_path))
        conn.execute(_DDL)
        # A `segments` table with every column EXCEPT `version` -- as if
        # built before that field existed.
        conn.execute(
            "CREATE TABLE segments (id VARCHAR PRIMARY KEY, document_id VARCHAR, "
            "pass_id VARCHAR, parent_segment_id VARCHAR, kind VARCHAR, kind_raw VARCHAR, "
            "anchor JSON, baseline JSON, bbox_x DOUBLE, bbox_y DOUBLE, bbox_w DOUBLE, "
            "bbox_h DOUBLE, tile VARCHAR, doc_kind VARCHAR, confidence DOUBLE, "
            "is_furniture BOOLEAN, provenance_kind VARCHAR, created_by VARCHAR, "
            "created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP, "
            "deleted_by VARCHAR, metadata JSON)"
        )
        seg_id = uuid.uuid4().hex
        doc_id = uuid.uuid4().hex
        pass_id = uuid.uuid4().hex
        anchor_json = '{"document_id": "%s", "rect": [0.1, 0.1, 0.1, 0.1]}' % doc_id
        conn.execute(
            "INSERT INTO segments "
            "(id, document_id, pass_id, kind, anchor, bbox_x, bbox_y, bbox_w, bbox_h, "
            "tile, doc_kind, is_furniture, provenance_kind, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, 'word', ?, 0.1, 0.1, 0.1, 0.1, 'x0y0', ?, false, 'workflow', "
            "now(), now(), '{}')",
            [seg_id, doc_id, pass_id, anchor_json, f"{doc_id}:word"],
        )
        conn.close()

        db = Database(db_path)
        try:
            row = db.get(Segment, seg_id)
            assert row is not None
            assert row.version == 1, "a NULL version must backfill to the model's default, 1"
        finally:
            db.close()

        # Genuinely updatable: a second open, then a real compare-and-set
        # update against version 1 succeeds.
        db2 = Database(db_path)
        try:
            from fichero_server.actions.registry import ActionContext, registry

            ctx = ActionContext(actor="daniel", library_path=str(db_path.parent))
            registry.invoke(
                db2, "segment.update",
                {"segment_id": seg_id, "expected_version": 1,
                 "anchor": {"document_id": doc_id, "rect": [0.2, 0.2, 0.1, 0.1]}},
                ctx,
            )
            updated = db2.get(Segment, seg_id)
            assert updated.version == 2
            assert updated.anchor.rect == [0.2, 0.2, 0.1, 0.1]
        finally:
            db2.close()
