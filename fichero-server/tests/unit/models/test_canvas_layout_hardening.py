from __future__ import annotations

from fichero_server.api.routes.interpretation.canvas import (
    CanvasLayoutItem,
    CanvasLayoutSaveRequest,
    _load_canvas_layout,
    save_canvas_layout_impl,
)
from fichero_server.models.canvas import CanvasItem, CanvasItemKind, CanvasLayout
from fichero_server.db import Database
from fichero_server.db.migrations.schema import migrate_canvas_layout_table
from fichero_server.knowledge.knowledge_models import KnowledgeEntity
from fichero_server.models import DocType, Document


def _doc(db, folder_id: str, doc_id: str) -> None:
    db.save(Document(id=doc_id, name=doc_id, parent_id=folder_id, doc_type=DocType.file))


def test_save_canvas_layout_impl_persists_mixed_placeable_ids_in_library_scope(db) -> None:
    _doc(db, "folder-doc", "doc-1")
    db.save(CanvasItem(id="canvas-1", folder_id="folder-doc", kind=CanvasItemKind.note, text="n"))
    db.save(KnowledgeEntity(id="entity-1", canonical_name="Entity One"))

    rows, skipped = save_canvas_layout_impl(
        "__library__",
        CanvasLayoutSaveRequest(
            items=[
                CanvasLayoutItem(item_id="doc-1", x=10.0),
                CanvasLayoutItem(item_id="canvas-1", x=20.0),
                CanvasLayoutItem(item_id="entity-1", x=30.0),
            ]
        ),
        db,
    )

    assert skipped == []
    assert [row.id for row in rows] == [
        "__library__::doc-1",
        "__library__::canvas-1",
        "__library__::entity-1",
    ]
    assert {row.item_id: row.x for row in _load_canvas_layout(db, "__library__")} == {
        "doc-1": 10.0,
        "canvas-1": 20.0,
        "entity-1": 30.0,
    }


def test_save_canvas_layout_impl_reports_bad_ids_without_404ing_batch(db) -> None:
    _doc(db, "folder-ok", "doc-ok")

    rows, skipped = save_canvas_layout_impl(
        "folder-ok",
        CanvasLayoutSaveRequest(
            items=[
                CanvasLayoutItem(item_id="doc-ok", x=1.0),
                CanvasLayoutItem(item_id="missing-1", x=2.0),
                CanvasLayoutItem(item_id="missing-2", x=3.0),
            ]
        ),
        db,
    )

    assert [row.item_id for row in rows] == ["doc-ok"]
    assert [item.item_id for item in skipped] == ["missing-1", "missing-2"]
    assert [item.detail for item in skipped] == [
        "unknown canvas item id",
        "unknown canvas item id",
    ]


def test_load_canvas_layout_keeps_library_scope_isolated_from_folder_scope(db) -> None:
    _doc(db, "folder-a", "doc-1")
    save_canvas_layout_impl(
        "__library__",
        CanvasLayoutSaveRequest(items=[CanvasLayoutItem(item_id="doc-1", x=7.0)]),
        db,
    )
    save_canvas_layout_impl(
        "folder-a",
        CanvasLayoutSaveRequest(items=[CanvasLayoutItem(item_id="doc-1", x=9.0)]),
        db,
    )

    assert {row.item_id: row.x for row in _load_canvas_layout(db, "__library__")} == {
        "doc-1": 7.0
    }
    assert {row.item_id: row.x for row in _load_canvas_layout(db, "folder-a")} == {
        "doc-1": 9.0
    }


def test_canvas_layout_backfill_rerun_preserves_existing_rows(tmp_path) -> None:
    db = Database(tmp_path / "canvas-layout-hardening.duckdb")
    try:
        db.save(
            Document(
                id="legacy-doc",
                name="legacy-doc",
                parent_id="legacy-folder",
                doc_type=DocType.file,
                position_x=3.0,
                position_y=4.0,
            )
        )
        db.save(
            CanvasLayout(
                id=CanvasLayout.make_id("legacy-folder", "legacy-doc"),
                folder_id="legacy-folder",
                item_id="legacy-doc",
                x=99.0,
                y=88.0,
            )
        )

        migrate_canvas_layout_table(db.conn)
        migrate_canvas_layout_table(db.conn)

        row = db.get(CanvasLayout, CanvasLayout.make_id("legacy-folder", "legacy-doc"))
        assert row is not None
        assert row.x == 99.0
        assert row.y == 88.0
        assert len(db.query(CanvasLayout, folder_id="legacy-folder")) == 1
    finally:
        db.close()
