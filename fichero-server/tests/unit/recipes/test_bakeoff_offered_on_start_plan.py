"""`source.onboard.auto.reader-measured-before-bulk` (#5660 item 7): the Start plan OFFERS a comparison of readers
on the sample, cost first; it never runs it by itself."""
from __future__ import annotations

from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401


def test_the_start_plan_offers_the_bakeoff_cost_first_and_never_runs_it(client, db, folder, with_material):  # noqa: F811
    _set_up(client)
    body = client.get("/api/recipes/project/start").json()
    offer = body["bakeoff_offer"]
    assert offer["sentence"].startswith(("The comparison costs", "Every reader compared runs on this Mac"))
    assert offer["run_cost_usd"] >= 0 and offer["pages"] == 0
    assert offer["ready"] is False and offer["readiness_sentence"], "no corrected lines yet: says what to correct"
    assert all("bakeoff" not in (r.get("job") or "") for r in body["runs"])


def test_no_reading_step_no_offer(client, db, folder):  # noqa: F811
    answers = {"purposes": ["find-documents"], "languages": ["en"], "scripts": ["Latn"], "materials": ["print"]}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    if not any(s.get("job") == "read-a-line" for s in recipe.get("steps", [])):
        client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
        assert client.get("/api/recipes/project/start").json()["bakeoff_offer"] is None


def test_the_offer_is_kept_briefly_so_a_polled_plan_does_not_rescan_the_project(monkeypatch):
    from fichero_server.api.routes.system import recipes as r

    calls = []
    monkeypatch.setattr(r, "_compute_bakeoff_offer", lambda db, setup, volume: calls.append(1) or {"n": len(calls)})
    r._offers.clear()
    db, setup = object(), {"answers": {"a": 1}}
    assert r._bakeoff_offer(db, setup, 10) == r._bakeoff_offer(db, setup, 10) == {"n": 1}
    r._bakeoff_offer(db, {"answers": {"a": 2}}, 10)
    assert len(calls) == 2
