"""Tests for canvas arrange strategies + the layout persistence endpoint (#2297).

Two layers:
  * the pure ``compute_arrangement`` geometry (deterministic, no DB), and
  * the ``POST /folders/{folder_id}/arrange`` route + ``canvas.arrange`` action,
    which must persist one canvas_layout row per node.
"""

import math

import pytest

# Importing the route module registers the ``canvas.arrange`` action.
import fichero.api.routes.canvas  # noqa: F401
from fichero import accounts, authz
from fichero.actions.registry import ActionContext, registry
from fichero.spatial_arrange import (
    DEFAULT_SPACING,
    ArrangeStrategy,
    compute_arrangement,
)
from fichero.models import DocType, Document
from fichero.models import ActionAudit
from fichero.canvas_models import CanvasLayout

BASE = "/api/canvas/folders"
IDS = ["a", "b", "c", "d", "e"]


def _seed_folder_docs(db, folder_id: str, ids: list[str]) -> None:
    for item_id in ids:
        db.save(Document(id=item_id, name=item_id, parent_id=folder_id, doc_type=DocType.file))


def _ctx(db, app_db) -> ActionContext:
    library_path = str(db.path.parent)
    user = app_db.create_user(
        username="canvas-editor",
        display_name="Canvas Editor",
        password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role="editor",
    )
    return ActionContext(actor=user.username, library_path=library_path)


# ─────────────────────────────────────────────────────────────────────────────
# Pure geometry
# ─────────────────────────────────────────────────────────────────────────────


def test_row_is_horizontal_evenly_spaced():
    out = compute_arrangement(IDS, "row", spacing=100.0)
    assert [p["x"] for p in out] == [0.0, 100.0, 200.0, 300.0, 400.0]
    assert all(p["y"] == 0.0 and p["z"] == 0.0 for p in out)
    assert [p["z_index"] for p in out] == [0, 1, 2, 3, 4]
    assert [p["item_id"] for p in out] == IDS  # order preserved


def test_column_is_vertical_evenly_spaced():
    out = compute_arrangement(IDS, "column", spacing=50.0)
    assert [p["y"] for p in out] == [0.0, 50.0, 100.0, 150.0, 200.0]
    assert all(p["x"] == 0.0 for p in out)


def test_grid_packs_rows_by_cols():
    # 5 items, 2 columns -> rows: (0,0)(1,0) / (0,1)(1,1) / (0,2)
    out = compute_arrangement(IDS, "grid", spacing=10.0, columns=2)
    coords = [(p["x"], p["y"]) for p in out]
    assert coords == [
        (0.0, 0.0),
        (10.0, 0.0),
        (0.0, 10.0),
        (10.0, 10.0),
        (0.0, 20.0),
    ]


def test_grid_default_cols_is_ceil_sqrt():
    # 4 items, no columns -> ceil(sqrt(4)) == 2 cols -> a 2x2 block
    out = compute_arrangement(["a", "b", "c", "d"], "grid", spacing=10.0)
    coords = [(p["x"], p["y"]) for p in out]
    assert coords == [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (10.0, 10.0)]


def test_circle_points_lie_on_ring():
    out = compute_arrangement(IDS, "circle", spacing=100.0)
    r = (len(IDS) * 100.0) / (2 * math.pi)
    for i, p in enumerate(out):
        dist = math.hypot(p["x"], p["y"])
        assert dist == pytest.approx(r)
        angle = 2 * math.pi * i / len(IDS)
        assert p["x"] == pytest.approx(r * math.cos(angle))
        assert p["y"] == pytest.approx(r * math.sin(angle))


def test_circle_single_item_at_origin():
    out = compute_arrangement(["solo"], "circle")
    assert out == [{"item_id": "solo", "x": 0.0, "y": 0.0, "z": 0.0, "z_index": 0}]


def test_circle_respects_explicit_radius():
    out = compute_arrangement(IDS, "circle", radius=7.0)
    assert all(math.hypot(p["x"], p["y"]) == pytest.approx(7.0) for p in out)


def test_stack_same_xy_increasing_z_index():
    out = compute_arrangement(IDS, "stack", spacing=100.0)
    assert all(p["x"] == 0.0 and p["y"] == 0.0 for p in out)
    assert [p["z_index"] for p in out] == [0, 1, 2, 3, 4]
    # z climbs so later items sit on top
    zs = [p["z"] for p in out]
    assert zs == sorted(zs) and zs[0] < zs[-1]


def test_empty_item_ids_returns_empty():
    assert compute_arrangement([], "grid") == []


def test_unknown_strategy_raises_value_error():
    with pytest.raises(ValueError):
        compute_arrangement(IDS, "spiral")


def test_default_spacing_used_when_omitted():
    out = compute_arrangement(["a", "b"], "row")
    assert out[1]["x"] == DEFAULT_SPACING


def test_strategy_enum_has_only_geometric_members():
    # umap / cluster_by_type are deliberately NOT here (deferred — #2290 / ontology).
    assert {s.value for s in ArrangeStrategy} == {
        "grid",
        "row",
        "column",
        "circle",
        "stack",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /folders/{folder_id}/arrange
# ─────────────────────────────────────────────────────────────────────────────


def test_arrange_persists_document_positions(client, db):
    folder = "folder-arrange"
    _seed_folder_docs(db, folder, IDS)
    resp = client.post(
        f"{BASE}/{folder}/arrange",
        json={"node_ids": IDS, "strategy": "row", "spacing": 100.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 5
    assert len(body["items"]) == 5
    assert body["skipped"] == []

    loaded = client.get(f"{BASE}/{folder}/layout").json()
    assert loaded["count"] == 5
    by_id = {r["item_id"]: r for r in loaded["items"]}
    assert by_id["a"]["x"] == 0.0
    assert by_id["b"]["x"] == 100.0
    assert by_id["e"]["x"] == 400.0


def test_arrange_empty_node_ids_is_400(client):
    resp = client.post(
        f"{BASE}/folder-empty/arrange",
        json={"node_ids": [], "strategy": "grid"},
    )
    assert resp.status_code == 400, resp.text


def test_arrange_unknown_strategy_is_422(client):
    resp = client.post(
        f"{BASE}/folder-bad/arrange",
        json={"node_ids": ["a"], "strategy": "spiral"},
    )
    # strategy is an enum field -> Pydantic/FastAPI validation error.
    assert resp.status_code == 422, resp.text


def test_arrange_is_idempotent_overwrites(client, db):
    folder = "folder-reardange"
    _seed_folder_docs(db, folder, ["a", "b"])
    client.post(
        f"{BASE}/{folder}/arrange",
        json={"node_ids": ["a", "b"], "strategy": "row", "spacing": 10.0},
    )
    # re-arrange the SAME nodes with a different strategy
    client.post(
        f"{BASE}/{folder}/arrange",
        json={"node_ids": ["a", "b"], "strategy": "column", "spacing": 10.0},
    )
    rows = client.get(f"{BASE}/{folder}/layout").json()["items"]
    assert len(rows) == 2, "re-arrange must overwrite, not duplicate"
    by_id = {r["item_id"]: r for r in rows}
    # column: x collapses to 0, y spreads
    assert by_id["a"]["x"] == 0.0 and by_id["b"]["x"] == 0.0
    assert by_id["b"]["y"] == 10.0


def test_arrange_is_folder_scoped(client, db):
    _seed_folder_docs(db, "f1", ["shared"])
    _seed_folder_docs(db, "f2", ["shared-2"])
    client.post(
        f"{BASE}/f1/arrange",
        json={"node_ids": ["shared"], "strategy": "row"},
    )
    client.post(
        f"{BASE}/f2/arrange",
        json={"node_ids": ["shared-2"], "strategy": "row"},
    )
    f1 = client.get(f"{BASE}/f1/layout").json()["items"]
    f2 = client.get(f"{BASE}/f2/layout").json()["items"]
    assert len(f1) == 1 and len(f2) == 1


def test_arrange_skips_unknown_ids_but_persists_known_ones(client, db):
    folder = "folder-partial-arrange"
    _seed_folder_docs(db, folder, ["known"])
    resp = client.post(
        f"{BASE}/{folder}/arrange",
        json={"node_ids": ["known", "missing"], "strategy": "row", "spacing": 10.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["skipped"] == [
        {"item_id": "missing", "detail": "unknown canvas item id"}
    ]
    loaded = client.get(f"{BASE}/{folder}/layout").json()["items"]
    assert len(loaded) == 1
    assert loaded[0]["item_id"] == "known"


# ─────────────────────────────────────────────────────────────────────────────
# Action layer: canvas.arrange (agent / chat / App-Intents path) — #1848
# ─────────────────────────────────────────────────────────────────────────────


def test_canvas_arrange_action_is_registered():
    assert "canvas.arrange" in registry.names()


def test_canvas_arrange_action_persists_and_audits(db, app_db):
    ctx = _ctx(db, app_db)
    _seed_folder_docs(db, "f-act", ["x", "y", "z"])
    result = registry.invoke(
        db,
        "canvas.arrange",
        {"folder_id": "f-act", "node_ids": ["x", "y", "z"], "strategy": "stack"},
        ctx,
    )
    assert result.ok
    assert result.audit_id
    assert "canvas" in result.changed_domains

    rows = [db.get(CanvasLayout, CanvasLayout.make_id("f-act", item_id)) for item_id in ["x", "y", "z"]]
    assert all(row is not None for row in rows)
    assert {row.z_index for row in rows if row is not None} == {0, 1, 2}
    assert all(row.x == 0.0 and row.y == 0.0 for row in rows if row is not None)


def test_canvas_arrange_action_rejects_empty(db, app_db):
    with pytest.raises(ValueError):
        registry.invoke(
            db,
            "canvas.arrange",
            {"folder_id": "f-empty", "node_ids": [], "strategy": "grid"},
            _ctx(db, app_db),
        )


def test_arrange_route_writes_action_audit(client, db):
    folder = "folder-arrange-audit"
    _seed_folder_docs(db, folder, ["a", "b"])

    resp = client.post(
        f"{BASE}/{folder}/arrange",
        json={"node_ids": ["a", "b"], "strategy": "row", "spacing": 25.0},
    )
    assert resp.status_code == 200, resp.text

    audit = db.all(ActionAudit)[-1]
    assert audit.action_name == "canvas.arrange"
    assert len(audit.target_ids) == 2
