"""#4983 phase 1 proof: every migration made ATOMIC still succeeds on the
REAL (old-shape, populated) table it will actually meet on a real library.

The risk this file exists to rule out: before this phase, all 15 migrations
in `db/migrations/schema.py` were non-atomic, so each statement committed
the instant it ran — a migration could partially succeed and nobody noticed.
Wrapping 14 of them in one transaction (`_run_atomic_migration`) makes a
migration that fails now roll back EVERYTHING instead of partially
applying — correct — but only if DuckDB can actually commit that
migration's real statement sequence against a table that already has rows
in every pre-existing column. `migrate_workflow_table`'s `DEFAULT []`
finding proved DuckDB 1.5.5 has at least one real limit here; this file
checks every OTHER newly-atomic migration against the SAME risk before any
of them runs on a real library at every open.

Each test: build the OLD (pre-migration) schema for the table(s) that
migration touches, POPULATE it with rows carrying real values in every
pre-existing column, run the migration through its real call shape
(`migrate_x(conn, failures)`), then assert (a) no failure recorded, (b)
every column/index/backfill row the migration promises exists, (c) the
pre-existing rows are byte-identical for their original columns.

Real DuckDB FILE in a temp dir, not `:memory:`: the `migrate_workflow_table`
finding was re-verified against a file-backed connection during phase 1
and reproduced identically, so `:memory:` was not hiding or changing that
behaviour — but a file is what every real library actually is, and this
file's whole point is "does this really work in production," so it uses
the same storage the maintainer's library uses, not the faster substitute.
"""

from __future__ import annotations

import duckdb
import pytest

from fichero_server.db.migrations.schema import (
    migrate_activity_tables,
    migrate_canvas_layout_table,
    migrate_catalogue_chunk_artifact_type,
    migrate_checkpoint_tables,
    migrate_document_language_fields,
    migrate_document_table,
    migrate_known_libraries_table,
    migrate_library_entity_types_table,
    migrate_library_identity_table,
    migrate_provider_refs_table,
    migrate_reference_provenance_table,
    migrate_references_table,
    migrate_saved_search_table,
    migrate_spatial_node_layout_fields,
)


@pytest.fixture
def conn(tmp_path):
    """A real, file-backed DuckDB connection — not `:memory:` (see module
    docstring)."""
    c = duckdb.connect(str(tmp_path / "atomicity_proof.duckdb"))
    yield c
    c.close()


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def _indexes(conn, table: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = ?", [table]
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# ALTER-on-populated-table migrations — the highest-risk shape, the same
# family as the migrate_workflow_table finding (multiple ALTER ADD COLUMN
# statements against a table that already has rows).
# ---------------------------------------------------------------------------


def test_migrate_document_table_on_a_populated_old_documents_table(conn):
    conn.execute("CREATE TABLE documents (id VARCHAR, parent_id VARCHAR)")
    conn.execute(
        "INSERT INTO documents VALUES ('doc-1', NULL), ('doc-2', 'doc-1'), ('doc-3', 'doc-1')"
    )

    failures: list = []
    migrate_document_table(conn, failures)

    assert failures == []
    assert {"sort_order", "exclude_from_search"} <= _columns(conn, "documents")
    assert "idx_documents_parent_id" in _indexes(conn, "documents")
    assert conn.execute(
        "SELECT id, parent_id FROM documents ORDER BY id"
    ).fetchall() == [("doc-1", None), ("doc-2", "doc-1"), ("doc-3", "doc-1")]


def test_migrate_document_language_fields_on_a_populated_old_documents_table(conn):
    conn.execute("CREATE TABLE documents (id VARCHAR, parent_id VARCHAR)")
    conn.execute("INSERT INTO documents VALUES ('doc-1', NULL), ('doc-2', 'doc-1')")

    failures: list = []
    migrate_document_language_fields(conn, failures)

    assert failures == []
    assert {"language", "language_meta"} <= _columns(conn, "documents")
    assert conn.execute(
        "SELECT id, parent_id FROM documents ORDER BY id"
    ).fetchall() == [("doc-1", None), ("doc-2", "doc-1")]


def test_migrate_saved_search_table_on_a_populated_old_table(conn):
    conn.execute("CREATE TABLE saved_searches (id VARCHAR)")
    conn.execute("INSERT INTO saved_searches VALUES ('search-1'), ('search-2')")

    failures: list = []
    migrate_saved_search_table(conn, failures)

    assert failures == []
    assert {"folder_path", "sort_order", "sort_direction"} <= _columns(
        conn, "saved_searches"
    )
    assert conn.execute(
        "SELECT id FROM saved_searches ORDER BY id"
    ).fetchall() == [("search-1",), ("search-2",)]


def test_migrate_spatial_node_layout_fields_on_a_populated_old_table(conn):
    # Old shape: whatever spatialnode looked like before #2293 — the
    # migration only checks for the ABSENCE of its 6 new columns, so a
    # minimal old table with unrelated pre-existing data is a faithful
    # "old library" stand-in.
    conn.execute("CREATE TABLE spatialnode (id VARCHAR, label VARCHAR)")
    conn.execute("INSERT INTO spatialnode VALUES ('node-1', 'Alpha'), ('node-2', 'Beta')")

    failures: list = []
    migrate_spatial_node_layout_fields(conn, failures)

    assert failures == []
    assert {"pos_w", "pos_h", "z_index", "depth", "angle", "style_data"} <= _columns(
        conn, "spatialnode"
    )
    assert conn.execute(
        "SELECT id, label FROM spatialnode ORDER BY id"
    ).fetchall() == [("node-1", "Alpha"), ("node-2", "Beta")]


# ---------------------------------------------------------------------------
# CREATE-TABLE-IF-NOT-EXISTS migrations, tested on their SECOND run — i.e.
# the table already exists, already has rows, and the migration must be a
# no-op on the table itself while still (idempotently) ensuring indexes.
# ---------------------------------------------------------------------------


def test_migrate_provider_refs_table_idempotent_with_existing_rows(conn):
    migrate_provider_refs_table(conn, [])  # first run: creates the table
    conn.execute(
        "INSERT INTO provider_refs (id, provider_id) VALUES ('ref-1', 'openai')"
    )

    failures: list = []
    migrate_provider_refs_table(conn, failures)  # second run: table has a row

    assert failures == []
    assert "idx_provider_refs_provider" in _indexes(conn, "provider_refs")
    assert conn.execute(
        "SELECT id, provider_id FROM provider_refs"
    ).fetchall() == [("ref-1", "openai")]


def test_migrate_activity_tables_idempotent_with_existing_rows(conn):
    migrate_activity_tables(conn, [])
    conn.execute(
        "INSERT INTO activities (id, type, level, timestamp, message) "
        "VALUES ('a1', 'workflow_started', 'info', CURRENT_TIMESTAMP, 'hi')"
    )

    failures: list = []
    migrate_activity_tables(conn, failures)

    assert failures == []
    for idx in (
        "idx_activities_timestamp",
        "idx_activities_type",
        "idx_activities_workflow_id",
        "idx_activities_batch_id",
        "idx_activities_thread_id",
        "idx_activities_level",
    ):
        assert idx in _indexes(conn, "activities")
    assert conn.execute("SELECT id, message FROM activities").fetchall() == [
        ("a1", "hi")
    ]


def test_migrate_checkpoint_tables_idempotent_with_existing_rows(conn):
    migrate_checkpoint_tables(conn, [])
    conn.execute(
        "INSERT INTO checkpoints (thread_id, checkpoint_id) VALUES ('t1', 'c1')"
    )

    failures: list = []
    migrate_checkpoint_tables(conn, failures)

    assert failures == []
    assert conn.execute(
        "SELECT thread_id, checkpoint_id FROM checkpoints"
    ).fetchall() == [("t1", "c1")]


def test_migrate_known_libraries_table_idempotent_with_existing_rows(conn):
    migrate_known_libraries_table(conn, [])
    conn.execute(
        "INSERT INTO known_libraries (id, path, added_at, last_accessed) "
        "VALUES ('lib-1', '/tmp/x.fichero', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )

    failures: list = []
    migrate_known_libraries_table(conn, failures)

    assert failures == []
    assert conn.execute("SELECT id, path FROM known_libraries").fetchall() == [
        ("lib-1", "/tmp/x.fichero")
    ]


def test_migrate_references_table_idempotent_with_existing_rows(conn):
    migrate_references_table(conn, [])
    conn.execute(
        "INSERT INTO \"references\" (id, bibtex, doi, created_at, updated_at) "
        "VALUES ('ref-1', '@book{a}', '10.1/a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )

    failures: list = []
    migrate_references_table(conn, failures)

    assert failures == []
    assert {"idx_references_doi", "idx_references_isbn", "idx_references_authors_year"} <= (
        _indexes(conn, "references")
    )
    assert conn.execute(
        "SELECT id, doi FROM \"references\""
    ).fetchall() == [("ref-1", "10.1/a")]


def test_migrate_reference_provenance_table_idempotent_with_existing_rows(conn):
    migrate_reference_provenance_table(conn, [])
    conn.execute(
        "INSERT INTO reference_provenance "
        "(id, reference_id, document_id, citation_location, created_at) "
        "VALUES ('prov-1', 'ref-1', 'doc-1', 'unknown', CURRENT_TIMESTAMP)"
    )

    failures: list = []
    migrate_reference_provenance_table(conn, failures)

    assert failures == []
    assert {"idx_reference_provenance_reference", "idx_reference_provenance_document"} <= (
        _indexes(conn, "reference_provenance")
    )
    assert conn.execute(
        "SELECT id, reference_id FROM reference_provenance"
    ).fetchall() == [("prov-1", "ref-1")]


def test_migrate_library_entity_types_table_idempotent_with_existing_rows(conn):
    migrate_library_entity_types_table(conn, [])
    conn.execute(
        "INSERT INTO library_entity_types "
        "(id, library_id, entity_type_key, created_at, updated_at) "
        "VALUES ('let-1', 'lib-1', 'person', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )

    failures: list = []
    migrate_library_entity_types_table(conn, failures)

    assert failures == []
    assert "idx_library_entity_types_library" in _indexes(conn, "library_entity_types")
    assert conn.execute(
        "SELECT id, entity_type_key FROM library_entity_types"
    ).fetchall() == [("let-1", "person")]


def test_migrate_library_identity_table_idempotent_with_existing_row(conn):
    migrate_library_identity_table(conn, [])  # mints the one row
    first_uuid = conn.execute("SELECT library_uuid FROM library_identity").fetchone()[0]

    failures: list = []
    migrate_library_identity_table(conn, failures)  # must not mint a second

    assert failures == []
    rows = conn.execute("SELECT library_uuid FROM library_identity").fetchall()
    assert rows == [(first_uuid,)]


# ---------------------------------------------------------------------------
# Migrations that read/rewrite an existing, populated FOREIGN table
# (documents, artifacts) rather than their own.
# ---------------------------------------------------------------------------


def test_migrate_canvas_layout_table_backfills_from_a_populated_documents_table(conn):
    conn.execute(
        """
        CREATE TABLE documents (
            id VARCHAR, parent_id VARCHAR, position_x DOUBLE, position_y DOUBLE,
            position_z DOUBLE, rotation_z DOUBLE, z_index INTEGER, metadata JSON,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO documents VALUES
        ('child', 'folder', 1.5, 2.5, NULL, NULL, 3, '{}', CURRENT_TIMESTAMP),
        ('unpositioned', 'folder', NULL, NULL, NULL, NULL, 0, '{}', CURRENT_TIMESTAMP)
        """
    )

    failures: list = []
    migrate_canvas_layout_table(conn, failures)

    assert failures == []
    assert conn.execute(
        "SELECT id, folder_id, item_id FROM canvas_layout"
    ).fetchall() == [("folder::child", "folder", "child")]
    # The source rows are untouched — the backfill only READS documents.
    assert conn.execute("SELECT id FROM documents ORDER BY id").fetchall() == [
        ("child",), ("unpositioned",)
    ]


def test_migrate_catalogue_chunk_artifact_type_on_a_populated_artifacts_table(conn):
    conn.execute(
        """
        CREATE TABLE artifacts (
            id VARCHAR, document_id VARCHAR, artifact_type VARCHAR, data JSON
        )
        """
    )
    conn.execute(
        """
        INSERT INTO artifacts VALUES
        ('a1', 'doc-1', 'catalogue.chunk.1', NULL),
        ('a2', 'doc-1', 'catalogue.chunk.2', NULL),
        ('a3', 'doc-1', 'transcription', NULL)
        """
    )

    failures: list = []
    migrate_catalogue_chunk_artifact_type(conn, failures)

    assert failures == []
    rows = {
        r[0]: (r[1], r[2])
        for r in conn.execute("SELECT id, artifact_type, data FROM artifacts").fetchall()
    }
    assert rows["a1"][0] == "catalogue.chunk"
    assert rows["a2"][0] == "catalogue.chunk"
    assert rows["a3"] == ("transcription", None)  # untouched
