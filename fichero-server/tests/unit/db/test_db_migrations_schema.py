"""Direct DuckDB coverage for legacy schema migrations."""

from __future__ import annotations

import logging

import duckdb

from fichero_server.db.migrations.schema import (
    migrate_canvas_layout_table,
    migrate_document_table,
    migrate_references_table,
    migrate_saved_search_table,
    migrate_workflow_table,
)


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}


def test_legacy_workflow_schema_upgrades_once_and_preserves_rows():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE workflows (id VARCHAR, steps JSON)")
    conn.execute("INSERT INTO workflows VALUES ('workflow-1', '[]')")

    migrate_workflow_table(conn)
    migrate_workflow_table(conn)

    assert {"format", "nodes", "edges", "folder_path", "is_system"} <= _columns(conn, "workflows")
    assert conn.execute("SELECT id, format, folder_path, is_system FROM workflows").fetchone() == (
        "workflow-1",
        "steps",
        "/",
        False,
    )


def test_migrate_workflow_table_records_the_failure_before_it_raises():
    """#4983 item 3: `migrate_workflow_table` still RAISES (it cannot be
    made atomic — the DuckDB `DEFAULT []` limit), but must record into
    `failures` before doing so, so an operator inspecting
    `Database.migration_failures` sees this one too."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE workflows (id VARCHAR, steps JSON)")
    conn.execute("INSERT INTO workflows VALUES ('workflow-1', '[]')")
    conn.close()  # a closed connection makes every statement raise

    failures: list = []
    try:
        migrate_workflow_table(conn, failures)
    except Exception:
        pass
    else:
        raise AssertionError("expected migrate_workflow_table to raise")

    assert len(failures) == 1
    assert failures[0].migration == "migrate_workflow_table"


def test_document_and_saved_search_upgrades_are_idempotent_and_skip_missing_tables():
    conn = duckdb.connect(":memory:")

    migrate_document_table(conn)
    migrate_saved_search_table(conn)

    # #4983 phase 1: `documents` needs `parent_id` — the migration is now
    # ATOMIC (one transaction for its ALTER + ALTER + CREATE INDEX), so a
    # minimal fixture missing a column the CREATE INDEX references would
    # correctly roll back sort_order/exclude_from_search too, not just the
    # index. A real `documents` table always has `parent_id`.
    conn.execute("CREATE TABLE documents (id VARCHAR, parent_id VARCHAR)")
    conn.execute("CREATE TABLE saved_searches (id VARCHAR)")
    conn.execute("INSERT INTO documents VALUES ('document-1', NULL)")
    conn.execute("INSERT INTO saved_searches VALUES ('search-1')")

    migrate_document_table(conn)
    migrate_saved_search_table(conn)
    migrate_document_table(conn)
    migrate_saved_search_table(conn)

    assert "sort_order" in _columns(conn, "documents")
    assert {"folder_path", "sort_order", "sort_direction"} <= _columns(conn, "saved_searches")
    assert conn.execute("SELECT sort_order FROM documents").fetchone() == (0,)
    assert conn.execute(
        "SELECT folder_path, sort_order, sort_direction FROM saved_searches"
    ).fetchone() == ("/", 0, "desc")


def test_canvas_layout_backfills_positioned_children_once_only():
    conn = duckdb.connect(":memory:")
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
        ('child', 'folder', 1.5, 2.5, NULL, NULL, 3,
         '{"canvas_w": 40, "canvas_style": "sticky"}', CURRENT_TIMESTAMP),
        ('plain', 'folder', NULL, NULL, NULL, NULL, 0, '{}', CURRENT_TIMESTAMP),
        ('root', NULL, 9, 9, 9, 0, 1, '{}', CURRENT_TIMESTAMP)
        """
    )

    migrate_canvas_layout_table(conn)
    migrate_canvas_layout_table(conn)

    assert conn.execute(
        "SELECT id, folder_id, item_id, x, y, z_index, w, style FROM canvas_layout"
    ).fetchall() == [("folder::child", "folder", "child", 1.5, 2.5, 3, 40.0, "sticky")]


# ---------------------------------------------------------------------------
# #4983 phase 1: atomic + loud + recorded
# ---------------------------------------------------------------------------


class _FailOnSQL:
    """Wraps a real DuckDB connection, raising once a statement matching
    `trigger` is executed — a deterministic way to fail a SPECIFIC
    statement inside a multi-statement migration, rather than relying on a
    pre-existing schema state the migration's own idempotency checks might
    just skip past instead of erroring on."""

    def __init__(self, conn, trigger: str):
        self._conn = conn
        self._trigger = trigger
        self.armed = True

    def execute(self, sql, *args, **kwargs):
        if self.armed and self._trigger in sql:
            self.armed = False
            raise RuntimeError(f"synthetic failure: statement contains {self._trigger!r}")
        return self._conn.execute(sql, *args, **kwargs)


def test_second_statement_failure_rolls_back_the_whole_migration(caplog):
    """A multi-statement migration whose SECOND statement fails must leave
    the schema exactly as it was — not the first statement applied and the
    rest missing — is logged at ERROR, is recorded, and the library still
    opens (no exception)."""
    real_conn = duckdb.connect(":memory:")
    real_conn.execute("CREATE TABLE documents (id VARCHAR, parent_id VARCHAR)")
    real_conn.execute("INSERT INTO documents VALUES ('document-1', NULL)")
    conn = _FailOnSQL(real_conn, "ADD COLUMN exclude_from_search")

    failures: list = []
    with caplog.at_level(logging.ERROR, logger="fichero_server.db.migrations.schema"):
        migrate_document_table(conn, failures)  # must not raise

    assert "sort_order" not in _columns(real_conn, "documents"), (
        "the first ALTER (sort_order) must have been rolled back with the "
        "second statement's failure — not left half-applied"
    )
    assert any("migrate_document_table" in r.message for r in caplog.records)
    assert len(failures) == 1
    assert failures[0].migration == "migrate_document_table"
    assert failures[0].error_type == "RuntimeError"
    # The original row is untouched — nothing rewrote or lost it.
    assert real_conn.execute("SELECT id FROM documents").fetchall() == [("document-1",)]


def test_idempotent_rerun_after_the_cause_is_removed_completes():
    """After whatever made the migration fail is fixed, a re-run completes
    and adds exactly what it should — nothing it already had is cleared."""
    real_conn = duckdb.connect(":memory:")
    real_conn.execute("CREATE TABLE documents (id VARCHAR, parent_id VARCHAR)")
    real_conn.execute("INSERT INTO documents VALUES ('document-1', NULL)")
    failing_conn = _FailOnSQL(real_conn, "ADD COLUMN exclude_from_search")

    failures: list = []
    migrate_document_table(failing_conn, failures)  # fails on the 2nd ALTER
    assert len(failures) == 1
    assert "sort_order" not in _columns(real_conn, "documents")

    # The cause is gone now (the synthetic trigger only fires once); re-run
    # on the real connection directly.
    migrate_document_table(real_conn, failures)  # now completes

    assert len(failures) == 1, "the earlier failure record is not cleared"
    assert {"sort_order", "exclude_from_search"} <= _columns(real_conn, "documents")
    # The pre-existing row survived both attempts.
    assert real_conn.execute(
        "SELECT id, sort_order FROM documents"
    ).fetchall() == [("document-1", 0)]


def test_references_unique_index_failure_is_recorded_by_migration_name():
    """The two `CREATE UNIQUE INDEX` statements (DOI, ISBN) are the only
    thing enforcing 'no duplicate reference' — a failure to create one
    (duplicate data already present) must be recorded (naming the
    migration; DuckDB's own ConstraintException text does not name the
    column, only that indexed data has duplicates) — never silently
    absent, which is what happened before this phase."""
    conn = duckdb.connect(":memory:")
    # Pre-seed a duplicate DOI directly into a hand-built table shaped like
    # `references`, so `CREATE UNIQUE INDEX idx_references_doi` fails.
    conn.execute(
        """
        CREATE TABLE "references" (
            id VARCHAR PRIMARY KEY, bibtex TEXT, doi VARCHAR, isbn VARCHAR,
            authors JSON, year INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO "references" VALUES
        ('r1', 'a', 'dup-doi', NULL, '[]', 2020, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('r2', 'b', 'dup-doi', NULL, '[]', 2021, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )

    failures: list = []
    migrate_references_table(conn, failures)  # must not raise

    assert len(failures) == 1
    assert failures[0].migration == "migrate_references_table"
    assert failures[0].error_type == "ConstraintException"
    assert "duplicate" in failures[0].message.lower()
    # Atomic: the table's own CREATE TABLE IF NOT EXISTS was a no-op (table
    # pre-existed), and the perf index never got created either, since the
    # whole migration rolled back with the failed unique index.
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'references'"
        ).fetchall()
    }
    assert "idx_references_authors_year" not in indexes
