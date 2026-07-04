"""Unit tests for canvas layout table persistence (#3078)."""

from fichero.db import Database
from fichero.db_migrations import migrate_canvas_layout_table
from fichero.knowledge.knowledge_models import KnowledgeEntity
from fichero.models import DocType, Document
from fichero.models import ActionAudit
from fichero.spatial_models import CanvasItem, CanvasItemKind, CanvasLayout

BASE = "/api/mind-palace/folders"


def _make_doc(db, folder_id: str, doc_id: str) -> Document:
    doc = Document(id=doc_id, name=doc_id, parent_id=folder_id, doc_type=DocType.file)
    db.save(doc)
    return doc


def test_round_trip_upsert_then_load(client, db):
    """Saving a document batch then loading returns the same positions."""
    folder = "folder-A"
    _make_doc(db, folder, "doc-1")
    _make_doc(db, folder, "doc-2")
    resp = client.put(
        f"{BASE}/{folder}/canvas-layout",
        json={
            "items": [
                {"item_id": "doc-1", "x": 10.0, "y": 20.0, "z_index": 3},
                {"item_id": "doc-2", "x": -5.0, "y": 7.5, "angle": 1.5, "w": 100.0},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["count"] == 2
    assert saved["skipped"] == []

    load = client.get(f"{BASE}/{folder}/canvas-layout")
    assert load.status_code == 200
    rows = {r["item_id"]: r for r in load.json()["items"]}
    assert rows["doc-1"]["x"] == 10.0
    assert rows["doc-1"]["y"] == 20.0
    assert rows["doc-1"]["z_index"] == 3
    assert rows["doc-2"]["angle"] == 1.5
    assert rows["doc-2"]["w"] == 100.0


def test_defaults_for_omitted_fields(client, db):
    """Omitted spatial fields fall back to documented defaults."""
    folder = "folder-defaults"
    _make_doc(db, folder, "only-id")
    resp = client.put(
        f"{BASE}/{folder}/canvas-layout",
        json={"items": [{"item_id": "only-id"}]},
    )
    assert resp.status_code == 200
    row = client.get(f"{BASE}/{folder}/canvas-layout").json()["items"][0]
    assert row["x"] == 0.0
    assert row["y"] == 0.0
    assert row["z"] == 0.0
    assert row["angle"] == 0.0
    assert row["z_index"] == 0
    # nullable extents / style default to None
    assert row["w"] is None
    assert row["h"] is None
    assert row["d"] is None
    assert row["style"] is None


def test_upsert_is_idempotent_no_duplicate_rows(client, db):
    """Re-saving the same (folder, item) overwrites — never duplicates."""
    folder = "folder-idem"
    _make_doc(db, folder, "node")
    client.put(
        f"{BASE}/{folder}/canvas-layout",
        json={"items": [{"item_id": "node", "x": 1.0, "y": 1.0}]},
    )
    # move the same item
    client.put(
        f"{BASE}/{folder}/canvas-layout",
        json={"items": [{"item_id": "node", "x": 99.0, "y": 88.0}]},
    )
    rows = client.get(f"{BASE}/{folder}/canvas-layout").json()["items"]
    assert len(rows) == 1, "duplicate row created for same (folder_id, item_id)"
    assert rows[0]["x"] == 99.0
    assert rows[0]["y"] == 88.0


def test_layout_is_folder_scoped(client, db):
    """Positions in one folder never leak into another folder's load."""
    _make_doc(db, "folder-x", "shared-id")
    _make_doc(db, "folder-y", "shared-id-y")
    client.put(
        f"{BASE}/folder-x/canvas-layout",
        json={"items": [{"item_id": "shared-id", "x": 1.0}]},
    )
    client.put(
        f"{BASE}/folder-y/canvas-layout",
        json={"items": [{"item_id": "shared-id-y", "x": 2.0}]},
    )
    x_rows = client.get(f"{BASE}/folder-x/canvas-layout").json()["items"]
    y_rows = client.get(f"{BASE}/folder-y/canvas-layout").json()["items"]
    assert len(x_rows) == 1 and x_rows[0]["x"] == 1.0
    assert len(y_rows) == 1 and y_rows[0]["x"] == 2.0


def test_load_empty_folder_returns_empty_list(client):
    """A scope that was never arranged loads as an empty list."""
    resp = client.get(f"{BASE}/never-touched/canvas-layout")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_mixed_document_canvas_item_entity_batch_and_library_scope_save(client, db):
    _make_doc(db, "folder-doc", "doc-1")
    db.save(CanvasItem(id="canvas-1", folder_id="folder-doc", kind=CanvasItemKind.note, text="n"))
    db.save(KnowledgeEntity(id="entity-1", canonical_name="Entity One"))

    resp = client.put(
        f"{BASE}/__library__/canvas-layout",
        json={
            "items": [
                {"item_id": "doc-1", "x": 10.0},
                {"item_id": "canvas-1", "x": 20.0},
                {"item_id": "entity-1", "x": 30.0},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 3
    assert body["skipped"] == []

    loaded = client.get(f"{BASE}/__library__/canvas-layout").json()["items"]
    by_id = {row["item_id"]: row for row in loaded}
    assert by_id["doc-1"]["x"] == 10.0
    assert by_id["canvas-1"]["x"] == 20.0
    assert by_id["entity-1"]["x"] == 30.0


def test_unknown_item_is_reported_but_other_rows_persist(client, db):
    _make_doc(db, "folder-partial", "doc-ok")

    resp = client.put(
        f"{BASE}/folder-partial/canvas-layout",
        json={
            "items": [
                {"item_id": "doc-ok", "x": 10.0},
                {"item_id": "missing-item", "x": 20.0},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["skipped"] == [
        {"item_id": "missing-item", "detail": "unknown canvas item id"}
    ]
    loaded = client.get(f"{BASE}/folder-partial/canvas-layout").json()["items"]
    assert loaded == [body["items"][0]]


def test_empty_save_batch_returns_empty_success(client):
    resp = client.put(f"{BASE}/empty-scope/canvas-layout", json={"items": []})
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "count": 0, "skipped": []}


def test_document_position_storage_is_idempotent(db):
    """Document position attrs persist directly on the document row."""
    row = Document(id="i", name="i", parent_id="f", doc_type=DocType.file, position_x=3.0)
    db.save(row)
    row.position_x = 9.0
    db.save(row)
    fetched = db.get(Document, "i")
    assert fetched is not None
    assert fetched.position_x == 9.0


def test_save_canvas_layout_route_writes_action_audit(client, db):
    folder = "folder-audit"
    _make_doc(db, folder, "doc-audit")

    resp = client.put(
        f"{BASE}/{folder}/canvas-layout",
        json={"items": [{"item_id": "doc-audit", "x": 11.0, "y": 22.0}]},
    )
    assert resp.status_code == 200, resp.text

    audit = db.all(ActionAudit)[-1]
    assert audit.action_name == "canvas.layout.save"
    assert len(audit.target_ids) == 1
    assert audit.target_ids[0].endswith("::doc-audit")


def test_canvas_layout_migration_backfills_legacy_document_positions_and_is_idempotent(tmp_path):
    db = Database(tmp_path / "canvas-layout.duckdb")
    db.save(
        Document(
            id="legacy-doc",
            name="legacy-doc",
            parent_id="legacy-folder",
            doc_type=DocType.file,
            position_x=3.0,
            position_y=4.0,
            metadata={"canvas_w": 99.0, "canvas_style": "card"},
        )
    )

    migrate_canvas_layout_table(db.conn)
    migrate_canvas_layout_table(db.conn)

    row = db.get(CanvasLayout, CanvasLayout.make_id("legacy-folder", "legacy-doc"))
    assert row is not None
    assert row.x == 3.0
    assert row.y == 4.0
    assert row.w == 99.0
    assert row.style == "card"
    assert len(db.query(CanvasLayout, folder_id="legacy-folder")) == 1
    db.close()
