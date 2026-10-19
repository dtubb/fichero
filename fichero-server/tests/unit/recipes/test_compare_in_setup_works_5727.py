"""`source.try.compare-in-setup-works` (#5727): the Compare step in Set Up, end to end on a scratch project with enough
corrected lines: Set Up asks what a comparison would cost and whether it is ready, starts it, reads the table, and
Use This sets the winner. One path through the routes Set Up calls, in the order it calls them."""
from __future__ import annotations

from tests.unit.recipes.test_bakeoff_readers import (  # noqa: F401  (fixtures)
    _corrected, _run, _set_up, folder, readers)


def test_compare_in_set_up_runs_from_the_offer_to_use_this(client, db, tmp_path, folder, readers, with_material):  # noqa: F811
    _set_up(client)
    before = client.get("/api/recipes/project/bakeoffs").json()
    assert before["readiness"]["ready"] is False and before["next_run"]["sentence"]

    for i in (1, 2, 3):
        _corrected(db, tmp_path, f"SM_NPQ_C01_00{i}", folder)
    offered = client.get("/api/recipes/project/bakeoffs").json()
    assert offered["readiness"]["ready"] is True and offered["next_run"]["pages"] == 3

    started, done = _run(client, db)
    measured = [r for r in done["rows"] if r["measured"]]
    assert len(measured) >= 2 and done["winner"] == measured[0]["card"]

    used = client.post(f"/api/recipes/project/bakeoffs/{started['id']}/use", json={"card": done["winner"]})
    assert used.status_code == 200, used.text
    assert client.get("/api/recipes/project/bakeoffs").json()["items"][0]["id"] == started["id"]
