"""`ai.cloud.daily-cap` (#6347): the daily cap on every path a monthly cap has: the project's own answer and its route (set,
clear, audited, undone), its validation, the plan's refusal words and fix, the pages that fit, and a raise resuming a paused run."""
from __future__ import annotations

import pytest

from fichero_server.llm import spend
from fichero_server.recipes import answers as answers_mod
from fichero_server.recipes import cloud_cap

EST = {"runs": [{"workflow": "describe", "cost_usd": 4.0}]}


@pytest.fixture(autouse=True)
def _no_app_caps(monkeypatch):
    monkeypatch.setattr(spend, "app_cap_usd", lambda key: None)


def _library(db) -> str:
    from fichero_server.api.routes.system import recipes as routes

    return str(routes._library(db))


def _answers(client) -> dict:
    return client.get("/api/recipes/project").json().get("answers") or {}


def test_the_route_sets_clears_and_undoes_the_projects_daily_cap(client, db):
    assert client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"]}, "recipe": None}).status_code == 200
    r = client.put("/api/recipes/project/cloud-cap", json={"daily_cap_usd": 2.5})
    assert r.status_code == 200 and r.json()["daily_cap_usd"] == 2.5
    assert _answers(client)["cloud_daily_cap_usd"] == 2.5 and spend.daily_cap_usd(_library(db)) == 2.5
    assert client.post(f"/api/actions/audit/{r.json()['audit_id']}/undo").status_code == 200
    assert "cloud_daily_cap_usd" not in _answers(client)
    client.put("/api/recipes/project/cloud-cap", json={"daily_cap_usd": 1})
    cleared = client.put("/api/recipes/project/cloud-cap", json={"clear_daily_cap": True})
    assert cleared.status_code == 200 and cleared.json()["daily_cap_usd"] is None
    assert "cloud_daily_cap_usd" not in _answers(client)


def test_the_route_refuses_a_daily_cap_below_zero_or_set_and_cleared_together(client):
    assert client.put("/api/recipes/project/cloud-cap", json={"daily_cap_usd": -1}).status_code == 422
    assert client.put("/api/recipes/project/cloud-cap", json={"daily_cap_usd": 1, "clear_daily_cap": True}).status_code == 422


def test_normalise_checks_the_daily_answer_and_drops_an_empty_one():
    with pytest.raises(ValueError, match="daily"):
        answers_mod.normalise({"cloud_daily_cap_usd": -2}, strict=True)
    with pytest.raises(ValueError, match="daily"):
        answers_mod.normalise({"cloud_daily_cap_usd": True}, strict=True)
    assert answers_mod.normalise({"cloud_daily_cap_usd": 0}, strict=True)["cloud_daily_cap_usd"] == 0  # 0 is a cap
    assert "cloud_daily_cap_usd" not in answers_mod.normalise({"cloud_daily_cap_usd": None}, strict=True)


def test_an_over_day_plan_offers_to_raise_the_daily_cap():
    line = {"over": True, "over_day": True, "needed_daily_cap_usd": 2.25, "fewer_pages": None}
    _, fixes = cloud_cap.fixes_for(line, EST)
    assert fixes[0] == {"kind": "raise-cap", "cap": "daily", "raise_to_usd": 3.0}
    assert cloud_cap.CapFix(**fixes[0]).cap == "daily"


def test_the_refusal_words_name_the_daily_cap(tmp_path):
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\ncloud_daily_cap_usd: 1\n")
    library = str(tmp_path / "P.fichero")
    spend._book(library, 0.25)
    plan = {"cloud_cap": spend.plan_line(library, estimate_usd=2.0, pages=10), "refusals": []}
    cloud_cap.cap_refusals(plan)
    assert "daily cap leaves today" in plan["cloud_cap"]["refusal"] and "Raise the daily cap to US$2.25" in plan["refusals"][0]


def test_the_pages_that_fit_are_held_to_the_days_room(monkeypatch):
    monkeypatch.setattr(cloud_cap, "first_pages_of", lambda db, count, memo=None: [f"p{i}" for i in range(count)])
    line = {"remaining_usd": 100.0, "project_remaining_usd": None, "daily_remaining_usd": 1.0}
    price = lambda pages: {"total_cost_usd": 0.1 * len(pages)}  # noqa: E731
    assert cloud_cap.first_pages_that_fit(None, {}, line, 50, price) == 10  # the day leaves $1, a page costs $0.10


def test_a_raised_daily_cap_counts_as_a_raise_a_lowered_one_does_not(monkeypatch):
    monkeypatch.setattr(spend, "caps_now", lambda library: {"month": 10.0, "day": 5.0, "project": None, "run": None})
    held = {"month": 10.0, "day": 2.0, "project": None, "run": None}
    assert spend.raised_since("lib", held)
    assert not spend.raised_since("lib", {**held, "day": 9.0})
    assert not spend.raised_since("lib", {"month": 10.0, "project": None, "run": None, "day": 5.0})
