"""`recipes-run.steps.models-fetched-before-the-step` (#6673): the run's first stage fetches every model its steps name, and a
fetch that fails does not end the run (`source.recipe.download-failure-waits`): the steps on that model wait, page by page, for
the model to download, and the steps after them wait for those; never a step failing on every page "not on this Mac yet"."""
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


def test_a_failed_fetch_does_not_end_the_run(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [dict(MODEL)])
    seams["ends"] = lambda *a: "Model download failed: the Kraken reader McCATMuS did not download (no network)"
    runner._fetch_models_first(None, "job", {"runs": [READ]}, "owner")  # no RunEnded


def _failed(model="the Kraken reader McCATMuS"):
    why = runner._DownloadFailed(f"Model download failed: {model} did not download (no network). Retry it in Activity")
    why.model = model
    return why


def test_the_steps_on_a_model_that_did_not_download_wait_and_the_step_after_them_waits_for_them(monkeypatch):
    LINES = {"card": "workflow", "job": "find-lines", "steps": ["lines"], "takes": ["page_image"], "gives": ["lines"]}
    NEXT = {"card": "workflow", "job": "correct", "steps": ["correct"], "takes": ["line_readings"], "gives": ["corrected"]}
    READER = {**READ, "takes": ["lines"], "gives": ["line_readings"]}
    cards = [LINES, READER, NEXT]
    ran: list[str] = []
    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_stop_asked", lambda *a: False)
    monkeypatch.setattr(runner, "_let_go_after_the_last_served_step", lambda *a: None)
    monkeypatch.setattr(runner, "_wait_out_a_pause", lambda *a: None)
    monkeypatch.setattr(runner, "_after_the_step", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_recount_on_the_folder", lambda *a: None)
    monkeypatch.setattr(runner, "_await_downloads", lambda db, job, detail, card: _failed() if "read" in card["steps"] else None)

    def pages(db, card, step, batch, tree, detail):
        scratch: dict = {}
        index = detail["steps"].index(step)
        docs, waiting = runner._held_for_inputs(detail["runs"], detail["steps"], index, ["p1", "p2"])
        if waiting:
            scratch["waiting_on"] = waiting
        return docs, scratch, {}

    monkeypatch.setattr(runner, "_step_pages", pages)
    monkeypatch.setattr(runner, "_run_card", lambda db, card, *a, **k: (ran.append(card["steps"][0]), (card["steps"][0], "done", None))[1])
    detail = {"runs": cards, "steps": [{"state": "waiting"} for _ in cards], "batch_states": [None] * 3, "redo": []}
    problems = runner._run_batch(None, "job", detail, {"units": ["p1", "p2"], "folder": "f"}, {}, "test", final=True)
    lines, read, correct = detail["steps"]
    assert ran == ["lines"]  # the step that needs no model ran
    assert read["state"] == "waiting" and read["why"] == "waiting for the Kraken reader McCATMuS to download"
    assert correct["state"] == "waiting" and correct["why"] == "waiting for the Kraken reader McCATMuS to download"
    assert runner._step_counts(correct) == {"done": 0, "waiting": 2, "failed": 0}
    assert any("McCATMuS did not download" in p for p in problems)


def test_a_model_that_cannot_be_fetched_at_all_ends_the_run_naming_it(monkeypatch, seams):
    monkeypatch.setattr(start, "missing_models", lambda runs: [dict(MODEL)])

    def refuse(db, runtime, model, started_by):
        raise ValueError("no such reader")

    monkeypatch.setattr(local_models, "enqueue_download", refuse)
    with pytest.raises(runner.RunEnded, match=r"McCATMuS cannot be downloaded: no such reader"):
        runner._fetch_models_first(None, "job", {"runs": [READ]}, "owner")
