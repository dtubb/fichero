"""A step's capture run, below the run machinery (spec: recipe-steps-at-scale, #5940; the manager's ruling, 2026-10-28).

The batch's requests are the step's own calls: the step's validated workflow, with its node config, is run in-process
under `provider_batch.capturing()`. It is not a run: nothing registers it, so a real run started meanwhile neither joins
it nor counts its pages covered, and Activity shows nothing; it writes nothing to the library.
"""
from __future__ import annotations

import asyncio

import pytest
from PIL import Image

import fichero_server.llm as llm
from fichero_server.recipes.start import _shipped
from fichero_server.remote_read import capture


@pytest.fixture(autouse=True)
def _close_the_library(tmp_path):
    yield
    from fichero_server.db import db_manager

    db_manager.close_database(tmp_path)


def _pages(tmp_path, n=2):
    from fichero_server.db import db_manager
    from fichero_server.models import DocType, Document, FileType

    from fichero_server.workflows.default_workflows import seed_default_workflows

    db = db_manager.get_database(tmp_path)
    seed_default_workflows(db)  # a library holds its shipped presets
    ids = []
    for i in range(n):
        image = tmp_path / f"p{i}.png"
        Image.new("RGB", (64 + i, 48), "white").save(image)
        doc = Document(name=image.name, doc_type=DocType.file, file_type=FileType.image, path=str(image))
        db.save(doc)
        ids.append(doc.id)
    return db, ids


def _card():
    name, workflow_id = _shipped("transcribe_htr")
    return {"steps": ["read"], "card": "workflow", "job": "read-a-page", "workflow": name, "workflow_id": workflow_id,
            "provider_override": "anthropic", "model_override": "claude-opus-5-5", "runs_on": "cloud:anthropic"}


def test_the_capture_is_the_steps_own_calls_and_no_run_anyone_can_see_or_join(tmp_path, monkeypatch):
    """WHY: a real run of the same reader started while the capture runs must not take it for a run reading these
    pages (it would count them covered and wait on a run that lands nothing); Activity shows no run; no row, pass or
    reading is written; and nothing is called."""
    from fichero_server.execution.runner import live_run_reading, reader_key
    from fichero_server.workflows.activity import get_activity_tracker

    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda config, kind: None)
    monkeypatch.setattr(llm, "get_langchain_model", lambda config: (_ for _ in ()).throw(AssertionError("a plain call")))
    monkeypatch.setattr(llm, "get_api_key", lambda provider: "test-key-not-real")  # validation asks for a key
    db, ids = _pages(tmp_path)
    tables = ("jobs", "workflowrunrecords", "artifacts", "contentrepresentations", "segment_passes", "checkpoints")
    before = {t: db.execute_fetchone(f"SELECT count(*) FROM {t}")[0] for t in tables}  # noqa: S608 -- fixed names
    seen_mid_capture = []

    def probe(prompt, images):  # runs inside the capture, as a real run started now would look
        workflow, request = capture.step_workflow(db, _card(), ids)
        seen_mid_capture.append(live_run_reading(str(db.path), workflow.id, ids, reader_key(workflow, request)))
        return "En la villa"

    calls = asyncio.run(capture.capture_step(db, _card(), ids, answer=probe))

    assert len(calls) == 2 and len({c.key for c in calls}) == 2, "each page's call, under its own key"
    assert seen_mid_capture and all(live is None for live in seen_mid_capture), "no run to join, no page covered"
    runs = asyncio.run(get_activity_tracker(str(db.path)).store.list_workflow_runs(limit=10))
    assert list(runs or []) == [], "Activity shows no run"
    assert {t: db.execute_fetchone(f"SELECT count(*) FROM {t}")[0] for t in tables} == before


def test_a_step_sent_as_a_batch_asks_each_page_once_and_lands_the_batchs_answer_through_its_own_run(tmp_path, monkeypatch):
    """WHY (design A, #5940, never-rerun-a-model-pass): the capture's keys are the replay's keys, so a page the batch
    answered is never asked again as a plain call, and its reading lands through the step's own run as any reading does."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.llm import provider_batch as pb
    from fichero_server.llm import spend
    from fichero_server.recipes import runner
    from fichero_server.remote_read import cloud_batch

    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda config, kind: None)
    monkeypatch.setattr(llm, "get_langchain_model", lambda config: (_ for _ in ()).throw(AssertionError("a plain call")))
    monkeypatch.setattr(llm, "get_api_key", lambda provider: "test-key-not-real")
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / "batch" / job_id)
    monkeypatch.setattr(spend, "reserve_batch", lambda *a, **k: 0.0)
    monkeypatch.setattr(spend, "settle_batch", lambda *a, **k: None)
    monkeypatch.setattr("fichero_server.recipes.places.project_says_cloud", lambda answers: True)
    monkeypatch.setattr(cloud_batch, "_project_must_agree", lambda db, what: None)
    db, ids = _pages(tmp_path)
    card = _card()
    parent = jobs.enqueue(db, "batch", "recipe-under-test", started_by="owner")  # the step's row; nothing runs it

    class Provider:  # answers every request it was sent
        name, cap_bytes = "Anthropic", 10**9
        sent: list[str] = []

        def submit(self, model, requests, *, max_tokens):
            self.sent += [r.key for r in requests]
            return {"batch_id": "b1"}

        def poll(self, ids):
            return {"state": "ended"}

        def lines(self, ids):
            return [pb.BatchLine(k, True, text="En la villa de Mosquera") for k in self.sent]

        def cancel(self, ids):
            pass

    provider = Provider()
    monkeypatch.setattr(cloud_batch, "client_for", lambda name: provider)  # the only fake: the provider itself

    # The real route: the row run by the engine's scheduler, waited on as the runner waits, then the step's own run.
    out = runner._run_card(db, {**card, "place": "batch"}, ids, {}, parent, {}, "owner")

    assert out[1] == "done", out
    assert len(provider.sent) == 2
    landed = [r for r in db.execute_fetchall("SELECT * FROM artifacts") if "En la villa de Mosquera" in json.dumps(r, default=str)]
    assert len(landed) >= 2, "each page's batch answer lands through the step's own run"
