"""`recipes-run.steps.models-fetched-before-the-step` (#6673): the run's first stage fetches every model its steps name, and a
fetch that fails ends the run before any step, naming the model (never a step failing on every page "not on this Mac yet")."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import local_models
from fichero_server.recipes import runner, start

READ = {"card": "workflow", "job": "read-a-line", "steps": ["read"], "model_override": "kraken-mccatmus",
        "provider_override": "kraken"}
MODEL = {"runtime": "kraken", "model": "kraken-mccatmus", "name": "the Kraken reader McCATMuS", "steps": ["read"]}


@pytest.fixture
def seams(monkeypatch):
    seen: dict = {"queued": []}
    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: seen.setdefault("reason", k.get("reason")))
    monkeypatch.setattr(start, "runtime_to_set_up", lambda runs: [])
    monkeypatch.setattr(start, "local_models_to_download", lambda runs: [])
    monkeypatch.setattr(start, "mark_downloads_under_way", lambda db, downloads: None)

    def enqueue(db, runtime, model, started_by):
        seen["queued"].append(model)
        return "dl-1"

    monkeypatch.setattr(local_models, "enqueue_download", enqueue)
    seen["ends"] = lambda *a: None
    monkeypatch.setattr(runner, "_await_downloads", lambda *a: seen["ends"](*a))
    return seen


def test_a_model_missing_on_this_mac_is_fetched_and_waited_for_before_the_first_step(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [dict(MODEL)])
    detail = {"runs": [READ], "awaited": []}
    runner._fetch_models_first(None, "job", detail, "owner")
    assert seams["queued"] == ["kraken-mccatmus"]
    assert detail["awaited"] == [{"steps": ["read"], "job_id": "dl-1", "name": "the Kraken reader McCATMuS"}]


def test_a_model_already_here_queues_nothing(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [])
    runner._fetch_models_first(None, "job", {"runs": [READ]}, "owner")
    assert seams["queued"] == []


def test_a_failed_fetch_ends_the_run_before_any_step_naming_the_model(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [dict(MODEL)])
    seams["ends"] = lambda *a: "Model download failed: the Kraken reader McCATMuS did not download (no network)"
    with pytest.raises(runner.RunEnded, match=r"McCATMuS did not download.*ended before any step"):
        runner._fetch_models_first(None, "job", {"runs": [READ]}, "owner")


def test_a_model_that_cannot_be_fetched_at_all_ends_the_run_naming_it(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [dict(MODEL)])

    def refuse(db, runtime, model, started_by):
        raise ValueError("no such reader")

    monkeypatch.setattr(local_models, "enqueue_download", refuse)
    with pytest.raises(runner.RunEnded, match=r"McCATMuS cannot be downloaded: no such reader"):
        runner._fetch_models_first(None, "job", {"runs": [READ]}, "owner")
