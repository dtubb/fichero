"""`ai.where.accept-unpriced-cloud-model` (#6259, maintainer's ruling 2026-10-28): a cloud model with no listed price never
blocks Start. The plan lists it apart at the assumed price, Start goes on, and pressing Start is the yes, recorded by the one
audited accept action. Also `ai.where.cloud-spend-cap`: Set Up's cap is read and written by PUT /api/recipes/project."""
from __future__ import annotations

import pytest

from fichero_server.llm import spend, usage


@pytest.fixture(autouse=True)
def _no_price_for_anything(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": None)


def _library(db):
    from fichero_server.api.routes.system import recipes as routes

    return str(routes._library(db))


def test_the_plan_line_lists_an_unpriced_model_apart_at_the_assumed_price(tmp_path):
    line = spend.plan_line(str(tmp_path / "P.fichero"), estimate_usd=None, cloud_models=[("acme", "mystery")])
    assert line["unpriced_models"] == ["acme/mystery"]
    assert "acme/mystery" in line["note"] and f"US${spend.UNPRICED_CALL_USD:.2f}" in line["note"]


def _unpriced_plan(client, monkeypatch, refusals):
    from fichero_server.api.routes.system import recipes as routes

    assert client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "cloud_allowed": True},
                                                    "recipe": None}).status_code == 200
    plan = {"refusals": refusals, "cloud_cap": {"unpriced_models": ["acme/mystery"]}, "estimate": {"pages": 1}, "workflows": []}
    monkeypatch.setattr(routes, "_start_plan", lambda *a, **k: plan)
    return routes


def test_start_goes_on_and_records_the_yes_for_every_unpriced_model_it_names(client, db, monkeypatch):
    from fichero_server.models import ActionAudit

    routes = _unpriced_plan(client, monkeypatch, [])
    invoke = routes.registry.invoke
    monkeypatch.setattr(routes.registry, "invoke", lambda db, name, *a, **k: None if name == "project.start" else invoke(db, name, *a, **k))
    monkeypatch.setattr(routes, "_as_started", lambda db, plan: (_ for _ in ()).throw(LookupError("started")))
    with pytest.raises(LookupError, match="started"):  # the run itself is stubbed: only the yes is asked of it
        client.post("/api/recipes/project/start", json={})  # no accept_unpriced sent: the Start itself is the yes
    assert spend.accepted_models(_library(db)) == ["acme/mystery"]
    assert any(a.action_name == "cloud.accept_unpriced" for a in db.all(ActionAudit))


def test_a_refused_start_still_keeps_the_yes_and_a_fixed_start_does_not_ask_again(client, db, monkeypatch):
    """`ai.where.accept-unpriced-cloud-model`: the yes is taken before Start's own action, so it outlives a refused Start."""
    from fichero_server.models import ActionAudit

    routes = _unpriced_plan(client, monkeypatch, ["over the cap"])
    plan = {"refusals": ["over the cap"], "estimate": {"pages": 1}, "workflows": []}

    def _plan(*a, **k):  # the plan lists only the models not yet accepted, as spend.plan_line does
        asked = [m for m in ["acme/mystery"] if m not in spend.accepted_models(_library(db))]
        return {**plan, "cloud_cap": {"unpriced_models": asked}}

    monkeypatch.setattr(routes, "_start_plan", _plan)
    assert client.post("/api/recipes/project/start", json={}).status_code == 422
    assert spend.accepted_models(_library(db)) == ["acme/mystery"]
    accepted = [a for a in db.all(ActionAudit) if a.action_name == "cloud.accept_unpriced"]
    assert len(accepted) == 1
    plan["refusals"] = []  # the person fixes the cap and presses Start again
    invoke = routes.registry.invoke
    monkeypatch.setattr(routes.registry, "invoke", lambda db, name, *a, **k: None if name == "project.start" else invoke(db, name, *a, **k))
    monkeypatch.setattr(routes, "_as_started", lambda db, plan: (_ for _ in ()).throw(LookupError("started")))
    with pytest.raises(LookupError, match="started"):
        client.post("/api/recipes/project/start", json={})
    assert len([a for a in db.all(ActionAudit) if a.action_name == "cloud.accept_unpriced"]) == 1, "it was not asked again"


def test_the_plan_does_not_refuse_an_unpriced_model():
    from fichero_server.api.routes.system import recipes as routes

    plan = {"refusals": [], "cloud_cap": {"unpriced_models": ["acme/mystery"], "over": False}}
    routes._cap_refusals(plan)
    assert plan["refusals"] == []


@pytest.mark.parametrize("cap,ok", [(25, True), (0, True), (-1, False), ("ten", False)])
def test_set_up_reads_and_writes_the_cloud_spending_cap(client, cap, ok):
    said = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "cloud_spend_cap_usd": cap},
                                                    "recipe": None})
    assert (said.status_code == 200) is ok, said.text
    if ok:
        assert client.get("/api/recipes/project").json()["answers"]["cloud_spend_cap_usd"] == cap
