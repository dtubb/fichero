"""Cost on every row, not only recipe runs (#6598, `activity.pane.cost-per-row-and-totals`, decision 20).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. A job of its own with cloud calls lists its dollars; a call priced at
$0 reads 0.0 (free), distinct from null (local work, or nothing priced).
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import live_stages
from fichero_server.recipes.run_view import StepTiming

KIND = "t-cost-job"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Cost job"))
    jobs.load_kinds()
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, client, usage):
    job = jobs.enqueue(db, KIND, "one", started_by="owner", detail=json.dumps({"usage": usage}))
    return {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}[job]


def _cloud(**kw):
    return {"provider": "anthropic", "model": "m-priced", "kind": "chat", "input_tokens": 1000, "output_tokens": 100, **kw}


def _price(monkeypatch, per_token):
    from fichero_server.llm import usage

    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider=None: {
        "input_cost_per_token": per_token, "output_cost_per_token": per_token})


def test_a_job_of_its_own_with_a_priced_cloud_call_lists_its_cost(held, client, monkeypatch):
    _price(monkeypatch, 0.001)
    assert _row(held, client, [_cloud()])["cost_usd"] == pytest.approx(1.1)


def test_a_call_priced_at_zero_reads_free_not_null(held, client, monkeypatch):
    _price(monkeypatch, 0.0)
    assert _row(held, client, [_cloud()])["cost_usd"] == 0.0


def test_a_local_job_lists_null(held, client):
    local = {"provider": "mlx", "model": "qwen", "kind": "chat", "input_tokens": 10, "output_tokens": 5}
    assert _row(held, client, [local])["cost_usd"] is None
    assert _row(held, client, [])["cost_usd"] is None


def test_a_stage_priced_at_zero_counts_as_free_not_null():
    status = {"steps": [{"timing": StepTiming(cost_usd=0.0)}]}
    assert live_stages.cost_so_far(status) == 0.0
    assert live_stages.cost_so_far({"steps": [{"timing": StepTiming()}]}) is None
