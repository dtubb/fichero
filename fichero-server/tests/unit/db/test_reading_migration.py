"""Source-model slice 8 — the reading tables, their indexes, and an OLD
library opened twice (#4934, #4929, #4932).

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8" — "`ContentRepresentation`
gains (all optional, added on open; no data migration)" and the last test in
its list: "Old library: opens twice; existing representations read unchanged
with every new field empty."

Shaped like `test_segment_migration.py`: a real DuckDB file is hand-built with
a `contentrepresentations` table holding TODAY's columns and one row -- a
library made before this slice -- then closed and opened through the real
`Database` class TWICE. The point is that the one row does not move.

The indexes matter for a reason worth stating: `document_text` asks "this
line's readings" once PER LINE. Without an index on
`contentrepresentations.segment_id` a fifty-line folio is fifty table scans,
and `source.store.bounded-reads` is the rule that forbids exactly that.
"""

from __future__ import annotations

import json
import uuid

import duckdb
import pytest

from fichero_server.db import Database
from fichero_server.models import ContentRepresentation, LibraryReadingKind

pytestmark = pytest.mark.source_model

#: Exactly the columns `ContentRepresentation` had BEFORE this slice.
_DDL = """
CREATE TABLE contentrepresentations (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR,
    kind VARCHAR,
    content VARCHAR,
    language VARCHAR,
    script VARCHAR,
    source_anchor JSON,
    parent_representation_id VARCHAR,
    derived_from_representation_id VARCHAR,
    producer_run_id VARCHAR,
    producer_tool VARCHAR,
    producer_model VARCHAR,
    review_state VARCHAR,
    created_at TIMESTAMP
);
"""

_OLD_COLS = (
    "id, document_id, kind, content, language, script, "
    "parent_representation_id, derived_from_representation_id, "
    "producer_run_id, producer_tool, producer_model, review_state, created_at"
)

#: Every index slice 8 adds, and the query each one exists for.
_SLICE_8_INDEXES = (
    "idx_contentrepresentations_segment_id",
    "idx_contentrepresentations_document_id",
    "idx_readingchoices_segment_id",
    "idx_readingchoices_document_id",
    "idx_segmentpasschoices_document_id",
    "idx_libraryreadingkinds_key",
)


def _build_old_library(path) -> str:
    conn = duckdb.connect(str(path))
    conn.execute(_DDL)
    representation_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO contentrepresentations VALUES "
        "(?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, now())",
        [
            representation_id,
            "doc-old",
            "transcription",
            "en el nombre de dios",
            "es",
            "Latn",
            json.dumps({"document_id": "doc-old", "page_id": "page-old"}),
            "transcribe",
            "qwen-vl",
            "source",
        ],
    )
    conn.close()
    return representation_id


def _index_names(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()}


def _table_names(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


def _old_row(conn, representation_id: str):
    return conn.execute(
        f"SELECT {_OLD_COLS} FROM contentrepresentations WHERE id = ?", [representation_id]
    ).fetchone()


class TestAnOldLibraryOpensTwiceAndNothingMoves:
    def test_the_one_existing_reading_reads_unchanged_with_every_new_field_empty(
        self, tmp_path
    ):
        db_path = tmp_path / "old.duckdb"
        representation_id = _build_old_library(db_path)

        # Snapshot through a raw connection, before any Database touches the
        # file, so the snapshot cannot be influenced by this slice.
        conn = duckdb.connect(str(db_path))
        before_row = _old_row(conn, representation_id)
        before_tables = _table_names(conn)
        assert "readingchoices" not in before_tables
        assert "libraryreadingkinds" not in before_tables
        conn.close()

        first = Database(db_path)
        try:
            assert _old_row(first.conn, representation_id) == before_row

            stored = first.get(ContentRepresentation, representation_id)
            assert stored.content == "en el nombre de dios"
            assert stored.kind == "transcription"
            for field in (
                "segment_id", "level", "read_from_rendition_id", "guideline",
                "provenance_kind", "machine_confidence", "char_confidences",
                "char_positions", "corrects_representation_id",
                "derived_from_artifact_id", "pair_id", "pair_role",
                "campaign_ids", "sign_map", "retracted_at",
            ):
                assert getattr(stored, field) is None, f"{field} was invented on open"

            tables = _table_names(first.conn)
            assert "readingchoices" in tables
            assert "libraryreadingkinds" in tables
            indexes_after_first_open = _index_names(first.conn)
            for expected in _SLICE_8_INDEXES:
                assert expected in indexes_after_first_open, expected
            kinds_after_first_open = {
                row.key for row in first.query(LibraryReadingKind)
            }
            assert "transcription" in kinds_after_first_open
            assert "coordinate" in kinds_after_first_open
        finally:
            first.close()

        second = Database(db_path)
        try:
            # Nothing raised, nothing duplicated, nothing about the old row
            # moved, and the seed did not seed a second time.
            assert _old_row(second.conn, representation_id) == before_row
            # Nothing slice 8 built is lost, and nothing it built waited for a
            # second open. Deliberately a SUPERSET check, not equality: an
            # unrelated migration (`idx_documents_parent_id`) does only appear
            # on a second open, which is the same ordering bug this test's
            # subject had -- noted for its own owner, not papered over here.
            second_indexes = _index_names(second.conn)
            assert indexes_after_first_open <= second_indexes
            for expected in _SLICE_8_INDEXES:
                assert expected in second_indexes, expected
            rows = second.query(LibraryReadingKind)
            assert len(rows) == len({row.key for row in rows}), "a kind was seeded twice"
            assert {row.key for row in rows} == kinds_after_first_open
            assert (
                second.conn.execute("SELECT COUNT(*) FROM readingchoices").fetchone()[0] == 0
            ), "opening a library must not invent a choice"
        finally:
            second.close()

    def test_a_fresh_library_gets_the_same_indexes_and_seeds(self, db):
        """The migration is not an upgrade-only path: a library made today
        needs every index too, or the first dense page read is slow in exactly
        the way the old library's would have been."""
        indexes = _index_names(db.conn)
        for expected in _SLICE_8_INDEXES:
            assert expected in indexes, expected
        assert {row.key for row in db.query(LibraryReadingKind)} >= {
            "transcription", "as_read_aloud", "music", "drawing",
        }
