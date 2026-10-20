"""Fable runner review #6 (reviews 152, 154): Use This writes an override to the saved recipe; Set Up then PUT the recipe
it had loaded, whole, and the newer choice was dropped. The engine keeps the saved overrides and drops any a PUT carries
that the saved recipe does not hold, so a PUT neither loses a Use This nor adds an override around Use This's rules nor
brings back an undone one (`source.project.setup-saves-what-is-sent`)."""
from __future__ import annotations

from fichero_server.recipes.bakeoff import keep_saved_overrides
from tests.unit.recipes.test_bakeoff_readers import (  # noqa: F401  (fixtures)
    PPOCR, _corrected, _run, _set_up, folder, readers)


def _o(card, at, step="read", scope="project", folder=None):
    return {"step": step, "scope": scope, "folder_id": folder, "card": card, "at": at, "model": {"hf": card}}


def test_the_saved_override_wins_whatever_time_the_client_sends():
    stored = {"overrides": [_o("saved", "2026-10-20T10:00:00")]}
    for at in ("2999-01-01T00:00:00", "", None):
        sent = {"overrides": [_o("client", at)]}
        assert [o["card"] for o in keep_saved_overrides(stored, sent)["overrides"]] == ["saved"]


def test_an_override_only_the_client_holds_is_dropped_and_one_only_the_project_holds_is_kept():
    assert keep_saved_overrides({"overrides": []}, {"overrides": [_o("new", "t", scope="folder", folder="f1")]})["overrides"] == []
    assert keep_saved_overrides(None, {"overrides": [_o("new", "t")]})["overrides"] == []
    kept = keep_saved_overrides({"overrides": [_o("a", "t1", step="regions")]}, {"overrides": [_o("b", "t2", step="read")]})
    assert [o["card"] for o in kept["overrides"]] == ["a"]


def _use_this(client, db, tmp_path, folder):
    recipe = _set_up(client)
    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    started, _done = _run(client, db)
    used = client.post(f"/api/recipes/project/bakeoffs/{started['id']}/use", json={"card": PPOCR, "scope": "project"})
    assert used.status_code == 200, used.text
    return recipe


def _put(client, recipe, overrides):
    got = client.get("/api/recipes/project").json()
    return client.put("/api/recipes/project", json={"answers": got["answers"], "recipe": {**recipe, "overrides": overrides}})


def test_through_the_routes_a_stale_whole_recipe_put_does_not_drop_a_use_this(client, db, tmp_path, folder, readers, with_material):  # noqa: F811
    recipe = _use_this(client, db, tmp_path, folder)  # the app loaded `recipe` before Use This
    assert _put(client, recipe, []).status_code == 200
    saved = client.get("/api/recipes/project").json()["recipe"]
    assert [(o["scope"], o["card"]) for o in saved["overrides"]] == [("project", PPOCR)]


def test_a_future_client_time_does_not_beat_the_saved_choice(client, db, tmp_path, folder, readers, with_material):  # noqa: F811
    recipe = _use_this(client, db, tmp_path, folder)
    saved = client.get("/api/recipes/project").json()["recipe"]["overrides"][0]
    stale = {**saved, "card": "zenodo:stale", "at": "2999-01-01T00:00:00"}
    assert _put(client, recipe, [stale]).status_code == 200
    assert [o["card"] for o in client.get("/api/recipes/project").json()["recipe"]["overrides"]] == [PPOCR]


def test_a_put_cannot_add_an_override_around_use_this(client, db, tmp_path, folder, readers, with_material):  # noqa: F811
    recipe = _set_up(client)
    step = recipe["steps"][0]["id"]
    for scope, folder_id in (("project", None), ("folder", folder.id)):
        assert _put(client, recipe, [_o("zenodo:x", "t", step=step, scope=scope, folder=folder_id)]).status_code == 200
    assert client.get("/api/recipes/project").json()["recipe"]["overrides"] == []


def test_undo_then_a_stale_put_leaves_no_override(client, db, tmp_path, folder, readers, with_material):  # noqa: F811
    from fichero_server.models import ActionAudit

    recipe = _use_this(client, db, tmp_path, folder)
    use = recipe.copy()
    echoed = client.get("/api/recipes/project").json()["recipe"]["overrides"]
    newest = max((a for a in db.query(ActionAudit) if a.action_name == "project.save_setup"), key=lambda a: a.created_at)
    assert client.post(f"/api/actions/audit/{newest.id}/undo").status_code == 200
    assert client.get("/api/recipes/project").json()["recipe"]["overrides"] == []
    assert _put(client, use, echoed).status_code == 200  # Set Up's stale copy still echoes the undone choice
    assert client.get("/api/recipes/project").json()["recipe"]["overrides"] == []
