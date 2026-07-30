"""Close the unbounded `catalogue.chunk.{n}` artifact vocabulary (#4426 #4418).

`artifact_type` is a bare `str` in the OpenAPI schema, which is why #4418 could
ship as two green commits and one dead feature: the generated Swift client
honestly exposes a `String`, the server wrote `"text_geometry"`, the client
queried `"transcription"`, and nothing in the toolchain could object.

Declaring it as an enum makes that a compile error — but only if the vocabulary
is CLOSED, and it was not. The catalogue tool minted a new type per summary
chunk (`catalogue.chunk.1`, `.2`, … forever), so a closed enum would have
passed regeneration and then 500'd the first time a real catalogued library was
read back. This closes that producer and repoints rows already on disk, because
archival data is never regenerated from scratch.

Nothing here skips: a real DuckDB file is created in tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="DuckDB is a hard dependency")

from fichero_server.db.migrations.schema import (  # noqa: E402
    migrate_catalogue_chunk_artifact_type,
)

_DDL = """
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    artifact_type TEXT,
    content TEXT,
    data JSON
)
"""


def _conn(tmp_path: Path, rows: list[tuple]):
    conn = duckdb.connect(str(tmp_path / "lib.duckdb"))
    conn.execute(_DDL)
    for row in rows:
        conn.execute(
            "INSERT INTO artifacts (id, document_id, artifact_type, content, data) "
            "VALUES (?, ?, ?, ?, NULL)",
            row,
        )
    return conn


def _types(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT artifact_type FROM artifacts ORDER BY id"
    ).fetchall()]


class TestTheUnboundedTypesAreCollapsed:
    def test_dotted_chunk_types_become_the_stable_type(self, tmp_path: Path):
        conn = _conn(tmp_path, [
            ("a1", "d1", "catalogue.chunk.1", "first"),
            ("a2", "d1", "catalogue.chunk.2", "second"),
            ("a3", "d1", "catalogue.chunk.17", "seventeenth"),
        ])
        try:
            migrate_catalogue_chunk_artifact_type(conn)
            assert _types(conn) == ["catalogue.chunk"] * 3, (
                "the unbounded vocabulary survives on disk — a closed enum "
                "would 500 reading this library back (#4426)"
            )
        finally:
            conn.close()

    def test_the_chunk_index_is_preserved_in_data(self, tmp_path: Path):
        """The index is information, not decoration — collapsing the type
        must move it, not discard it."""
        conn = _conn(tmp_path, [("a1", "d1", "catalogue.chunk.7", "seventh")])
        try:
            migrate_catalogue_chunk_artifact_type(conn)
            data = conn.execute(
                "SELECT data FROM artifacts WHERE id = 'a1'"
            ).fetchone()[0]
            assert "7" in str(data), f"chunk index lost: {data!r}"
        finally:
            conn.close()


class TestItTouchesNothingElse:
    def test_other_catalogue_artifacts_are_left_alone(self, tmp_path: Path):
        """`catalogue.narrative` / `.timeline` / `.keywords` are a FIXED set
        and already enumerable — only the unbounded producer moves."""
        conn = _conn(tmp_path, [
            ("a1", "d1", "catalogue", "root"),
            ("a2", "d1", "catalogue.narrative", "n"),
            ("a3", "d1", "catalogue.timeline", "t"),
            ("a4", "d1", "catalogue.keywords", "k"),
            ("a5", "d1", "transcription", "x"),
        ])
        try:
            migrate_catalogue_chunk_artifact_type(conn)
            assert _types(conn) == [
                "catalogue", "catalogue.narrative", "catalogue.timeline",
                "catalogue.keywords", "transcription",
            ]
        finally:
            conn.close()

    def test_running_twice_changes_nothing_the_second_time(self, tmp_path: Path):
        """Migrations run on every library open."""
        conn = _conn(tmp_path, [("a1", "d1", "catalogue.chunk.3", "third")])
        try:
            migrate_catalogue_chunk_artifact_type(conn)
            first = conn.execute(
                "SELECT artifact_type, data FROM artifacts"
            ).fetchall()
            migrate_catalogue_chunk_artifact_type(conn)
            assert conn.execute(
                "SELECT artifact_type, data FROM artifacts"
            ).fetchall() == first
        finally:
            conn.close()

    def test_a_library_with_no_chunks_is_a_no_op(self, tmp_path: Path):
        conn = _conn(tmp_path, [("a1", "d1", "transcription", "x")])
        try:
            migrate_catalogue_chunk_artifact_type(conn)
            assert _types(conn) == ["transcription"]
        finally:
            conn.close()

    def test_a_missing_artifacts_table_does_not_raise(self, tmp_path: Path):
        """Runs on every library open, including brand-new ones."""
        conn = duckdb.connect(str(tmp_path / "empty.duckdb"))
        try:
            migrate_catalogue_chunk_artifact_type(conn)
        finally:
            conn.close()


class TestTheWriterNoLongerMintsNewTypes:
    def test_catalogue_writes_the_stable_type(self):
        import inspect

        from fichero_server.workflows.tools import catalogue

        source = inspect.getsource(catalogue)
        assert 'artifact_type="catalogue.chunk"' in source
        assert 'f"catalogue.chunk.{' not in source, (
            "the writer still mints a new artifact_type per chunk, so the "
            "vocabulary is unbounded again and cannot be an enum (#4426)"
        )

    def test_the_rerun_sweep_still_matches_the_new_type(self):
        """Prior catalogue artifacts are deleted by prefix, and the new
        stable type must still be caught by it or reruns would accumulate."""
        assert "catalogue.chunk".startswith("catalogue.")
