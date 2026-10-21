"""`ai.where.accept-unpriced-cloud-model` (#5987, ## 792): one audited accept action, keyed by project + provider + model, which a
recipe's Start uses too; the cap's plan line names what is unaccepted and lists assumed spend apart."""
from __future__ import annotations

import asyncio
import contextlib

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend, usage
from fichero_server.recipes.project import read_project_setup

MYSTERY = LLMConfig(provider="acme", model="mystery", api_key="k")
OTHER_PROVIDER = LLMConfig(provider="other", model="mystery", api_key="k")
ACCEPT = "/api/recipes/cloud/accept-unpriced"


@pytest.fixture(autouse=True)
def _no_price_for_anything(monkeypatch):
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": None)
    spend._RESERVED.clear()

    @contextlib.asynccontextmanager
    async def lane(config, *, library=None, subject=None):
        yield

    monkeypatch.setattr(llm, "_model_call_slot", lane)


def _library(db):
    from fichero_server.api.routes.system import recipes as routes

    return str(routes._library(db))


async def _call(library, config):
    async with llm.model_call_slot(config, library=library):
        pass


def test_refused_then_accepted_then_allowed_on_a_call_and_on_a_run_thread(client, db):
    library = _library(db)
    with pytest.raises(spend.CloudModelUnpriced):
        asyncio.run(_call(library, MYSTERY))
    said = client.post(ACCEPT, json={"provider": "acme", "model": "mystery"})
    assert said.status_code == 200, said.text
    assert said.json()["accepted"] == ["acme/mystery"]
    asyncio.run(_call(library, MYSTERY))
    asyncio.run(asyncio.to_thread(asyncio.run, _call(library, MYSTERY)))  # a workflow run's own thread
    with pytest.raises(spend.CloudModelUnpriced):  # the same model id under another provider
        asyncio.run(_call(library, OTHER_PROVIDER))
    assert read_project_setup(library)["answers"] is None, "accepting must not make a Set Up"


def test_withdrawing_the_yes_refuses_again(client, db):
    library = _library(db)
    client.post(ACCEPT, json={"provider": "acme", "model": "mystery"})
    client.post(ACCEPT, json={"provider": "acme", "model": "mystery", "withdraw": True})
    with pytest.raises(spend.CloudModelUnpriced):
        asyncio.run(_call(library, MYSTERY))


def test_accepting_is_audited_and_a_recipe_start_uses_the_same_action(client, db, monkeypatch):
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.models import ActionAudit

    assert client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "cloud_allowed": True},
                                                    "recipe": None}).status_code == 200
    plan = {"refusals": ["stop here"], "cloud_cap": {"unpriced_models": ["acme/mystery"]}, "estimate": {"pages": 1}, "workflows": []}
    monkeypatch.setattr(routes, "_start_plan", lambda *a, **k: plan)
    refused = client.post("/api/recipes/project/start", json={"accept_unpriced": ["acme/other"]})
    assert refused.status_code == 422 and "did not ask about acme/other" in refused.json()["detail"]
    client.post("/api/recipes/project/start", json={"accept_unpriced": ["acme/mystery"]})  # then refused for "stop here"
    assert spend.accepted_models(_library(db)) == ["acme/mystery"]
    assert any(a.action_name == "cloud.accept_unpriced" for a in db.all(ActionAudit)), "the yes is one audited action"


def test_the_plan_line_names_unaccepted_models_and_lists_assumed_spend_apart(tmp_path):
    library = str(tmp_path / "P.fichero")
    line = spend.plan_line(library, estimate_usd=None, cloud_models=[("acme", "mystery")])
    assert line["unpriced_models"] == ["acme/mystery"] and line["unpriced"] is True
    spend.set_accepted(library, "acme", "mystery", True)
    spend._book(library, spend.UNPRICED_CALL_USD, assumed_price=True)
    line = spend.plan_line(library, estimate_usd=2.0, cloud_models=[("acme", "mystery")])
    assert line["unpriced_models"] == [] and line["assumed_calls"] == 1
    assert line["assumed_usd"] == pytest.approx(spend.UNPRICED_CALL_USD)
    assert line["spent_usd"] == pytest.approx(spend.UNPRICED_CALL_USD) and line["cap_usd"] == 10.0
    assert spend.plan_line(library, estimate_usd=9.9)["over"] is True and line["over"] is False


def test_an_acceptance_whose_audit_fails_is_not_kept(client, db, monkeypatch):
    """The file is written inside the action, before the audit row commits: an audit that fails leaves no yes behind."""
    from fichero_server.actions import audit_chain

    library = _library(db)
    assert client.post(ACCEPT, json={"provider": "acme", "model": "kept"}).status_code == 200

    def audit_fails(*args, **kwargs):
        raise RuntimeError("audit down")
    monkeypatch.setattr(audit_chain, "save_chained_audit", audit_fails)  # the registry imports it per call
    with pytest.raises(RuntimeError):
        client.post(ACCEPT, json={"provider": "acme", "model": "lost"})
    assert spend.accepted_models(library) == ["acme/kept"]


def test_a_failed_audit_puts_back_only_its_own_model_not_a_concurrent_accept(client, db, monkeypatch):
    """## 843 LOW 1: the put-back is that one key, so an accept of another model that landed meanwhile is not undone."""
    from fichero_server.actions import audit_chain

    library = _library(db)

    def audit_fails(*args, **kwargs):
        spend.set_accepted(library, "acme", "meanwhile", True)  # another person's yes, landed during this call
        raise RuntimeError("audit down")
    monkeypatch.setattr(audit_chain, "save_chained_audit", audit_fails)
    with pytest.raises(RuntimeError):
        client.post(ACCEPT, json={"provider": "acme", "model": "lost"})
    assert spend.accepted_models(library) == ["acme/meanwhile"]


def test_a_redo_whose_audit_fails_keeps_no_yes_either(client, db, monkeypatch):
    """## 843 LOW 2: an undo/redo reaches the action through `registry.invoke(..., inverse_of=...)`, so the same put-back holds."""
    from fichero_server.actions import audit_chain
    from fichero_server.actions.registry import registry

    library = _library(db)
    assert client.post(ACCEPT, json={"provider": "acme", "model": "first"}).status_code == 200
    assert client.post(ACCEPT, json={"provider": "acme", "model": "first", "withdraw": True}).status_code == 200
    assert spend.accepted_models(library) == []

    def audit_fails(*args, **kwargs):
        raise RuntimeError("audit down")
    monkeypatch.setattr(audit_chain, "save_chained_audit", audit_fails)
    from fichero_server.actions.registry import ActionContext
    with pytest.raises(RuntimeError):
        registry.invoke(db, "cloud.accept_unpriced", {"provider": "acme", "model": "first"},
                        ActionContext(actor="owner", library_path=library, is_bootstrap=True), inverse_of="x")
    assert spend.accepted_models(library) == []
