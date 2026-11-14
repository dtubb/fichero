"""A run never repeats work already done (#6584, `activity.run.never-repeats-done-work`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. WHY (owner 2026-11-13): a run of 10 pages whose model fails after
6, retried, must make exactly 4 more model calls, never 10. Driven through the public surface: a real run started with
`POST /api/workflow-execution/execute`, Retry on its row in Activity; only the model is a stub (a cloud model answering from
memory that stops answering after six).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import threading

import pytest

from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    CloudModel,
    _execute,
    _png,
    _status,
    _wait_for,
    no_embedding_model,
    workflow,
)


class _FailsAfterSix(CloudModel):
    """Answers six calls, then refuses until `recovered` is set (the provider's outage)."""

    def __init__(self):
        super().__init__()
        self.recovered = threading.Event()

    async def __call__(self, images, prompt, config, **kwargs):
        with self.lock:
            n = self.calls + 1
        if n > 6 and not self.recovered.is_set():
            with self.lock:
                self.calls += 1
            raise RuntimeError("the model could not read this page")
        return await super().__call__(images, prompt, config, **kwargs)


@pytest.fixture
def cloud(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = _FailsAfterSix()
    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    return model


@pytest.fixture
def ten_pages(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i in range(10):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / f"p{i}.png")))
        db.save(doc)
        docs.append(doc)
    return docs


def test_a_run_that_failed_after_six_of_ten_pages_retried_makes_exactly_four_calls(client, db, workflow, ten_pages, cloud,
                                                                                    no_embedding_model):
    run = _execute(client, workflow, ten_pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed", "partial"))
    assert cloud.calls == 10, "the first run called the model once per page"
    account = client.get(f"/api/activity/jobs/{run}").json()
    assert account["done"] == 6 and account["failed"] == 4, account
    cloud.recovered.set()

    r = client.post(f"/api/activity/jobs/{run}/retry")

    assert r.status_code == 200, r.text
    again = r.json()["id"]
    assert again != run and r.json()["replaces"] == run
    assert _wait_for(lambda: _status(client, again) == "completed"), _status(client, again)
    assert cloud.calls == 14, f"the retry read {cloud.calls - 10} pages; only the 4 not done may be read"
    assert client.get(f"/api/activity/jobs/{again}").json()["done"] == 4
