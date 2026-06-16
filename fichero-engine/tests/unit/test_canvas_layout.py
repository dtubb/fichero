"""Unit tests for folder-scoped canvas layout persistence (#2293 slice 1).

The spatial 2D/3D library canvas must remember where each item was placed,
scoped to a FOLDER (not a mind-palace room), so switching view modes does not
lose positions.
"""

from fichero.spatial_models import CanvasLayout

BASE = "/api/mind-palace/folders"


def test_round_trip_upsert_then_load(client):
    """Saving a batch then loading returns the same positions."""
    folder = "folder-A"
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
    assert len(saved) == 2

    load = client.get(f"{BASE}/{folder}/canvas-layout")
    assert load.status_code == 200
    rows = {r["item_id"]: r for r in load.json()["items"]}
    assert rows["doc-1"]["x"] == 10.0
    assert rows["doc-1"]["y"] == 20.0
    assert rows["doc-1"]["z_index"] == 3
    assert rows["doc-2"]["angle"] == 1.5
    assert rows["doc-2"]["w"] == 100.0


def test_defaults_for_omitted_fields(client):
    """Omitted spatial fields fall back to documented defaults."""
    folder = "folder-defaults"
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


def test_upsert_is_idempotent_no_duplicate_rows(client):
    """Re-saving the same (folder, item) overwrites — never duplicates."""
    folder = "folder-idem"
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


def test_layout_is_folder_scoped(client):
    """Positions in one folder never leak into another folder's load."""
    client.put(
        f"{BASE}/folder-x/canvas-layout",
        json={"items": [{"item_id": "shared-id", "x": 1.0}]},
    )
    client.put(
        f"{BASE}/folder-y/canvas-layout",
        json={"items": [{"item_id": "shared-id", "x": 2.0}]},
    )
    x_rows = client.get(f"{BASE}/folder-x/canvas-layout").json()["items"]
    y_rows = client.get(f"{BASE}/folder-y/canvas-layout").json()["items"]
    assert len(x_rows) == 1 and x_rows[0]["x"] == 1.0
    assert len(y_rows) == 1 and y_rows[0]["x"] == 2.0


def test_load_empty_folder_returns_empty_list(client):
    """A folder that was never arranged loads as [] (and creates the table)."""
    resp = client.get(f"{BASE}/never-touched/canvas-layout")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_table_creation_is_idempotent(db):
    """_ensure_table via save works on a fresh DB and tolerates re-saves."""
    row = CanvasLayout(
        id=CanvasLayout.make_id("f", "i"),
        folder_id="f",
        item_id="i",
        x=3.0,
    )
    db.save(row)
    db.save(row)  # second save must not raise (idempotent upsert)
    fetched = db.query(CanvasLayout, folder_id="f")
    assert len(fetched) == 1
    assert fetched[0].x == 3.0
    assert fetched[0].id == "f::i"
