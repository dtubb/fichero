# ruff: noqa: F811
"""Each failure kind's pause-or-fail rule is a column of the one table, and the runner acts on it (#6675, #6569, #6354).

Spec: docs/contributor_manual/specs/compute/runner-reliability.md `runner.kinds.pause-or-fail-is-the-tables`,
`runner.pause.one-path`. A run whose provider has no credit (a 402 with no in-flight reason) or refuses the key (a 401)
settles `paused` with that kind's failure, its done pages kept and nothing more sent to the provider; a bug fails that page
and the run ends partial; a hold that gave up for memory pauses. Only the cloud model is a stub.
"""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import failure as failure_mod
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401, F811 -- fixtures are used by name
    CloudModel, _execute, _status, _wait_for, no_embedding_model, workflow,
)

PAGES = 10
BAD_PAGE = 4


class _Answer(Exception):
    def __init__(self, status: int, words: str):
        super().__init__(words)
        self.status_code = status


class _FailsFromPage4(CloudModel):
    """Answers the first pages; from the fourth call on it raises what `make` gives."""

    def __init__(self, make):
        super().__init__()
        self.make = make
        self.after_bad: list[int] = []

    async def __call__(self, images, prompt, config, **kwargs):
        n = self.calls + 1
        if n >= BAD_PAGE:
            self.calls = n
            self.after_bad.append(n)
            raise self.make()
        return await super().__call__(images, prompt, config, **kwargs)


@pytest.fixture
def pages10(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType
    from tests.unit.jobs.test_runs_are_jobs import _png

    docs = []
    for i in range(PAGES):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, path=str(_png(tmp_path / f"p{i}.png")))
        db.save(doc)
        docs.append(doc)
    return docs


@pytest.fixture(autouse=True)
def _one_page_at_a_time(monkeypatch):
    import fichero_server.workflows.circuit_breaker as cb
    from fichero_server.llm import retry

    monkeypatch.setattr(cb, "compute_backoff_delay", lambda *a, **k: 0.0)
    monkeypatch.setattr(retry, "_DEAD", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_CREDIT", {})
    monkeypatch.setattr(retry, "_LAST_CREDIT", {})


def _failure_of(client, run):
    rows = client.get("/api/activity/jobs").json()["jobs"]
    return next(r for r in rows if r["id"] == run).get("failure")


def _run(client, workflow, pages, monkeypatch, make):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = _FailsFromPage4(make)
    monkeypatch.setattr(llm, "vision", model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed", "paused", "partial"))
    return run, model


def test_a_402_with_no_credit_pauses_the_run_with_no_credit_and_sends_nothing_more(client, workflow, pages10, monkeypatch):
    run, model = _run(client, workflow, pages10, monkeypatch, lambda: _Answer(402, "402: Insufficient credits."))
    assert _status(client, run) == "paused"
    failure = _failure_of(client, run)
    assert failure["kind"] == "no-credit" and failure["pauses"] is True
    assert model.calls < PAGES, "pages after the 402 were not sent to the provider"


def test_a_401_pauses_the_run_with_key_refused(client, workflow, pages10, monkeypatch):
    run, model = _run(client, workflow, pages10, monkeypatch, lambda: _Answer(401, "401: Invalid API key"))
    assert _status(client, run) == "paused"
    assert _failure_of(client, run)["kind"] == "key-refused"
    assert model.calls < PAGES


def test_a_bug_fails_that_page_and_the_run_ends_partial(client, workflow, pages10, monkeypatch):
    run, model = _run(client, workflow, pages10, monkeypatch, lambda: RuntimeError("a slip in Fichero"))
    assert _status(client, run) != "paused"
    assert model.calls == PAGES, "a bug on one page does not stop the others"


def test_the_two_columns_are_on_every_kind():
    for kind in failure_mod.KINDS:
        built = failure_mod.of_kind(kind)
        assert built.pauses == (kind in failure_mod.PAUSES), kind
        assert built.engine_retries == (kind in failure_mod.ENGINE_RETRIES), kind
    assert {"no-credit", "key-refused", "rate-limited", "cap-refused", "network", "memory", "library-closed",
            "export-folder-gone"} <= failure_mod.PAUSES
    assert not ({"unexpected", "model-error", "files-unavailable", "runtime-unavailable"} & failure_mod.PAUSES)


def test_a_memory_error_after_the_hold_gave_up_is_a_pausing_kind():
    from fichero_server.execution.throttle import MemoryShortError

    kind, _ = failure_mod.kind_of(MemoryShortError("not enough memory"))
    assert kind == "memory" and kind in failure_mod.PAUSES


@pytest.mark.parametrize(("status", "words", "cause"), [(402, "insufficient credit", "out-of-credit"), (401, "invalid x-api-key", "key-refused")])
def test_a_page_that_met_no_credit_or_a_refused_key_pauses_its_run_not_the_systemic_rule(status, words, cause):
    """The parallel node's quota branch is the second route to the pause: it raises WorkflowPaused with the run asked to pause."""
    from fichero_server.execution.cancellation import WorkflowPaused, clear_pause, pause_requested
    from fichero_server.llm import LLMConfig, retry
    from fichero_server.workflows.builder import _make_parallel_node_function
    from fichero_server.workflows.types import NodeDef

    async def refused(inputs, state, llm_config):
        raise _Answer(status, words)

    run_id = f"run-6675-{status}"
    try:
        fn = _make_parallel_node_function(node_def=NodeDef(id="node-1", tool="vision", config={}, name="Vision", node_type="vision"),
                                          tool_fn=refused, llm_config=LLMConfig(provider="openai", model="gpt-4o"),
                                          workflow_config=None)
        state = {"parallel_file": "/nonexistent/a.png", "parallel_document": None, "parallel_index": 0, "parallel_total": 1,
                 "library_path": "", "task_id": run_id, "workflow_id": ""}
        with pytest.raises(WorkflowPaused):
            asyncio.run(fn(state))
        assert pause_requested(run_id)
    finally:
        clear_pause(run_id)
        retry._PAUSED_FOR_CREDIT.pop(run_id, None)
        retry._DEAD.clear()
        retry._LAST_CREDIT.clear()
