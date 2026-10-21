"""`activity.run.page-states` (#5960): `GET /jobs/{id}/pages?stage=` returns one entry per PAGE (not per step row): document id,
name, its state in each stage, at most one reason; paged, in reading order. The page grid reads this, never the step tree.

The function is pure over a job tree (the dict `GET /jobs/{id}` builds), so the shapes are written out here; the route
only reads the tree and pages the answer."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity_pages import page_states


def _page(doc: str, name: str, state: str, reason: str | None = None) -> dict:
    return {"id": f"p-{doc}-{state}-{name}", "kind": "page", "state": state, "reason": reason, "document_id": doc,
            "display_name": name, "children": []}


def _stage_run(child_id: str, steps: dict[str, list[dict]]) -> dict:
    return {"id": child_id, "kind": "workflow", "state": "running", "reason": None, "document_id": None,
            "children": [{"id": f"{child_id}:{step}", "kind": "workflow-step", "state": "running", "reason": None,
                          "document_id": None, "children": pages} for step, pages in steps.items()]}


def _tree() -> dict:
    """A recipe run: Find Lines (three pages, one step each ... two steps for page b) then Read (a done, b failed, c waiting)."""
    lines = _stage_run("w1", {
        "find-lines": [_page("a", "IMG_001", "done"), _page("b", "IMG_002", "done"), _page("c", "IMG_003", "done")],
        "refine-shapes": [_page("a", "IMG_001", "done"), _page("b", "IMG_002", "done"), _page("c", "IMG_003", "done")]})
    read = _stage_run("w2", {
        "read-a-line": [_page("a", "IMG_001", "done"), _page("b", "IMG_002", "failed", "Kraken could not read its lines"),
                        _page("c", "IMG_003", "waiting", "waiting for the model lane")]})
    return {"id": "r1", "kind": "run-a-recipe", "state": "running", "children": [lines, read],
            "stages": [{"steps": ["find-lines", "refine-shapes"], "child_id": "w1"}, {"steps": ["read-a-line"], "child_id": "w2"}]}


def test_one_entry_per_page_not_per_step_row():
    out = page_states(_tree(), stage=None)
    assert [p["name"] for p in out] == ["IMG_001", "IMG_002", "IMG_003"], "in reading order, each page once"


def test_a_stage_filters_the_pages_and_gives_that_stages_state():
    out = {p["name"]: p for p in page_states(_tree(), stage="read")}
    assert {n: p["state"] for n, p in out.items()} == {"IMG_001": "done", "IMG_002": "failed", "IMG_003": "waiting"}
    assert out["IMG_002"]["reason"] == "Kraken could not read its lines"
    assert out["IMG_001"]["reason"] is None


def test_every_entry_carries_its_state_in_each_stage_and_one_reason():
    page = {p["name"]: p for p in page_states(_tree(), stage=None)}["IMG_002"]
    assert page["stages"] == {"find-lines": "done", "read": "failed"}
    assert page["state"] == "failed", "with no stage asked, the worst state wins"
    assert page["reason"] == "Kraken could not read its lines"


def test_a_page_with_two_step_rows_is_one_state_by_priority():
    tree = _stage_run("w", {"find-lines": [_page("a", "A", "done")], "put-in-order": [_page("a", "A", "running")]})
    assert [p["state"] for p in page_states({"id": "w", "kind": "workflow", "children": tree["children"]}, stage=None)] == ["running"]


def test_states_are_only_done_running_waiting_failed():
    kinds = {"paused": "waiting", "not run": "waiting", "cancelled": "waiting", "interrupted": "failed", "completed": "done"}
    for raw, wanted in kinds.items():
        tree = {"id": "w", "kind": "workflow", "children": [_page("a", "A", raw)]}
        assert page_states(tree, stage=None)[0]["state"] == wanted, raw


def test_the_route_exists_with_stage_offset_and_limit():
    operation = app.openapi()["paths"]["/api/activity/jobs/{job_id}/pages"]["get"]
    assert {"stage", "offset", "limit"} <= {p["name"] for p in operation["parameters"]}


def test_a_page_in_two_runs_of_one_stage_keeps_the_worst_cells_reason():
    first = _stage_run("w1", {"read-a-line": [_page("a", "A", "failed", "the model refused")]})
    second = _stage_run("w2", {"read-a-line": [_page("a", "A", "waiting", "waiting for the model lane")]})
    tree = {"id": "r", "kind": "run-a-recipe", "children": [first, second],
            "stages": [{"steps": ["read-a-line"], "child_id": "w1"}, {"steps": ["read-a-line"], "child_id": "w2"}]}
    page = page_states(tree, stage="read")[0]
    assert (page["state"], page["reason"]) == ("failed", "the model refused"), "not the later, better cell's words"
    tree["children"] = [second, first]
    tree["stages"] = [{"steps": ["read-a-line"], "child_id": "w2"}, {"steps": ["read-a-line"], "child_id": "w1"}]
    assert page_states(tree, stage="read")[0]["reason"] == "the model refused", "whichever run came first"


def test_the_pages_of_one_read_share_one_build_of_the_tree(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fichero_server.api.routes.system import activity

    built = []

    async def tree(job_id, depth, db):
        built.append(job_id)
        return SimpleNamespace(model_dump=_tree)

    monkeypatch.setattr(activity, "get_job_tree", tree)
    monkeypatch.setattr(activity, "_PAGE_LISTS", {})
    db = SimpleNamespace(path="/lib/P.fichero/fichero.duckdb")
    first = asyncio.run(activity._run_page_list(db, "r1", "read"))
    again = asyncio.run(activity._run_page_list(db, "r1", "read"))
    other_stage = asyncio.run(activity._run_page_list(db, "r1", None))
    assert first is again and len(built) == 2, "the same read within the window builds once; another stage builds its own"
    assert len(other_stage) == 3
