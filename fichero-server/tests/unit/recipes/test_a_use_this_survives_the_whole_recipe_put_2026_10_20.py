"""Fable runner review #6: Use This writes an override to the saved recipe; Set Up then PUT the recipe it had loaded,
whole, and the newer choice was dropped. The engine keeps the newer override per (step, scope, folder) for every client
(`source.project.setup-saves-what-is-sent`)."""
from __future__ import annotations

from fichero_server.recipes.bakeoff import keep_newer_overrides


def _o(card, at, step="read", scope="project", folder=None):
    return {"step": step, "scope": scope, "folder_id": folder, "card": card, "at": at, "model": {"hf": card}}


def test_an_override_only_the_stored_recipe_holds_is_kept():
    sent = {"steps": [], "overrides": []}
    kept = keep_newer_overrides({"overrides": [_o("a", "2026-10-20T10:00:00")]}, sent)
    assert [o["card"] for o in kept["overrides"]] == ["a"]


def test_the_saved_override_for_the_same_step_and_scope_wins_whatever_time_the_client_sends():
    stored = {"overrides": [_o("saved", "2026-10-20T10:00:00")]}
    for at in ("2999-01-01T00:00:00", "2026-10-20T11:00:00", "", None):  # a future or skewed client clock never wins
        sent = {"overrides": [_o("client", at)]}
        assert [o["card"] for o in keep_newer_overrides(stored, sent)["overrides"]] == ["saved"]


def test_different_steps_and_scopes_are_all_kept():
    stored = {"overrides": [_o("a", "t1", step="regions")]}
    sent = {"overrides": [_o("b", "t2", step="read")]}
    assert {o["card"] for o in keep_newer_overrides(stored, sent)["overrides"]} == {"a", "b"}


def test_no_stored_recipe_changes_nothing():
    sent = {"overrides": [_o("b", "t2")]}
    assert keep_newer_overrides(None, sent) == {"overrides": [_o("b", "t2")]}


def test_through_the_route_a_whole_recipe_put_does_not_drop_a_newer_choice(client):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"], "pages": 100}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    step = recipe["steps"][0]["id"]
    older = {**recipe, "overrides": []}
    chosen = {**recipe, "overrides": [_o("zenodo:x", "2026-10-20T10:05:00", step=step)]}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": chosen}).status_code == 200
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": older}).status_code == 200  # Set Up's stale save
    saved = client.get("/api/recipes/project").json()["recipe"]
    assert [o["card"] for o in saved["overrides"]] == ["zenodo:x"]


def test_through_the_route_a_future_client_time_does_not_beat_the_saved_choice(client):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"], "pages": 100}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    step = recipe["steps"][0]["id"]
    saved = {**recipe, "overrides": [_o("zenodo:saved", "2026-10-20T10:05:00", step=step)]}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": saved}).status_code == 200
    stale = {**recipe, "overrides": [_o("zenodo:stale", "2999-01-01T00:00:00", step=step)]}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": stale}).status_code == 200
    assert [o["card"] for o in client.get("/api/recipes/project").json()["recipe"]["overrides"]] == ["zenodo:saved"]
