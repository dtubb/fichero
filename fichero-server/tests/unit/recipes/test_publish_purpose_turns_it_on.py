"""`source.job.publish`: a project can turn publishing on (live 2026-10-17: no purpose or layer brought a `publish`
step, so a person who wanted the site could not get one from setup). Adding the `publish` layer later puts the step in
the recipe after the export; it names no folder until the person says where, and the Start plan says so."""
from __future__ import annotations

from tests.unit.api.test_add_a_layer_later import (  # noqa: F401  (fixtures)
    _kraken_readers_on_this_mac,
    hold_the_run,
    project,
)


def test_the_publish_layer_is_offered_and_adds_a_publish_step_after_the_checks(client, project):  # noqa: F811
    offered = client.get("/api/recipes/project/start").json()
    assert "publish" in offered["addable"], offered

    r = client.post("/api/recipes/project/layers", json={"layers": ["publish"]})
    assert r.status_code == 200, r.text
    steps = client.get("/api/recipes/project").json()["recipe"]["steps"]
    jobs = [s["job"] for s in steps]
    assert "publish" in jobs and jobs[-1] == "publish"  # last: the site is the whole project, written at the end
    plan = r.json()
    skipped = [s for s in plan.get("skipped", []) if "folder" in (s.get("why") or "")]
    assert skipped, plan  # no `where` yet: the plan says so rather than publishing nowhere
