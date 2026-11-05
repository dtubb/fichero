"""`ai.cloud.one-run-overrides` (#6349, #6350): a recipe Start takes `allow_cloud_once` and `over_cap_once` like the execute request:
kept on the run's row, handed to the run when it starts, ended with it, written to no setting."""
from __future__ import annotations

import json

import pytest

from fichero_server.api.routes.system.recipes import StartParams, StartRequest
from fichero_server.llm import run_overrides
from fichero_server.recipes import runner


@pytest.fixture(autouse=True)
def _clean():
    yield
    run_overrides._RUNS.clear()


def _queued_detail(monkeypatch, **flags) -> dict:
    seen: dict = {}
    monkeypatch.setattr(runner.jobs, "enqueue_remote", lambda db, kind, key, **kw: seen.update(json.loads(kw["detail"])) or "job-1")
    monkeypatch.setattr(runner, "_recipe_title", lambda db: "R")
    monkeypatch.setattr(runner, "_pages_counted", lambda db, documents, reads: 0)
    runner.enqueue(None, {"runs": [], "skipped": []}, documents=None, started_by="owner", **flags)
    return seen


def test_the_request_and_the_action_take_both_flags():
    assert StartRequest(allow_cloud_once=True, over_cap_once=True).allow_cloud_once is True
    assert StartRequest().over_cap_once is False
    assert StartParams(allow_cloud_once=True).allow_cloud_once is True


def test_the_flags_are_kept_on_the_runs_row_only_when_asked(monkeypatch):
    assert "allow_cloud_once" not in _queued_detail(monkeypatch)
    detail = _queued_detail(monkeypatch, allow_cloud_once=True, over_cap_once=True)
    assert detail["allow_cloud_once"] is True and detail["over_cap_once"] is True


def test_the_run_holds_them_from_its_row_and_a_step_run_gets_them(monkeypatch):
    monkeypatch.setattr(runner.jobs, "read_job", lambda db, job_id: {"detail": json.dumps({"allow_cloud_once": True})})
    runner._hold_the_run_overrides(None, "job-1")
    assert run_overrides.for_run("job-1") == {"allow_cloud": True, "over_cap": False}
    assert run_overrides.for_run("job-2") == {}, "another run is not told"


def test_a_run_that_asked_for_none_holds_none(monkeypatch):
    monkeypatch.setattr(runner.jobs, "read_job", lambda db, job_id: {"detail": "{}"})
    runner._hold_the_run_overrides(None, "job-1")
    assert run_overrides.for_run("job-1") == {}
