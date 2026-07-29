"""Direct DuckDB coverage for legacy schema migrations."""

from __future__ import annotations

import duckdb

from fichero_server.db.migrations.schema import (
    migrate_canvas_layout_table,
    migrate_document_table,
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


def test_document_and_saved_search_upgrades_are_idempotent_and_skip_missing_tables():
    conn = duckdb.connect(":memory:")

    migrate_document_table(conn)
    migrate_saved_search_table(conn)

    conn.execute("CREATE TABLE documents (id VARCHAR)")
    conn.execute("CREATE TABLE saved_searches (id VARCHAR)")
    conn.execute("INSERT INTO documents VALUES ('document-1')")
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
