"""Time, cost and errors roll up a run's tree (#5353).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.jobs-are-a-tree`:
"a job's children (steps, pages) are jobs; progress, time, cost and errors roll up the tree", and
the job's `cost` field: "tokens and money from the vendored price list (`llm/model_types.py`),
summed up the tree". Written from the spec's text, and driven through the public surface: a real
entity-extraction run started with `POST /api/workflow-execution/execute` and read with
`GET /api/activity/jobs/{run}`. Only the model is a stub: a cloud chat model that answers from
memory and reports the tokens it used, reached through the real `llm.chat` path.
"""
from __future__ import annotations

import pytest

from fichero_server.llm.usage import price_call
from tests.unit.jobs.test_runs_are_jobs import _execute, _status, _tree, _wait_for, no_embedding_model  # noqa: F401
from tests.unit.jobs.test_text_calls_on_the_lane import ChatModel, pages  # noqa: F401

TOKENS = {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}


def _workflow(db, model):
    from fichero_server.models import Workflow

    wf = Workflow(
        id=f"wf-entities-{model}", name="Entities", provider="openai", model=model,
        nodes=[
            {"id": "files-source", "tool": "files", "label": "Files", "inputs": {}, "config": {}},
            {"id": "entities", "tool": "extract_entities_only", "label": "Entities",
             "inputs": {"documents": "$.nodes.files-source.documents"}, "config": {}},
        ],
        edges=[{"id": "e1", "source": "files-source", "target": "entities", "source_port": "documents",
                "target_port": "documents"}],
    )
    db.save(wf)
    return wf


class CountedModel(ChatModel):
    """Reports its tokens, as a cloud model's answer does; fails on the letter it is told to."""

    fail_on: str | None = None

    async def ainvoke(self, messages, *a, **k):
        if self.fail_on and any(self.fail_on in str(getattr(m, "content", "")) for m in messages):
            raise RuntimeError("the provider refused this letter")
        answer = await super().ainvoke(messages, *a, **k)
        answer.usage_metadata = dict(TOKENS)
        return answer


@pytest.fixture
def cloud(monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    model = CountedModel()
    monkeypatch.setattr(llm, "get_langchain_model", lambda config, *a, **k: model)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    return model


def _finished_tree(client, db, pages, model):
    run = _execute(client, _workflow(db, model), pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    return _tree(client, run)


def _calls(tree):
    return [c for step in tree["children"] for c in step["children"]]


def test_activity_jobs_are_a_tree__cost_rolls_up_from_the_price_list(client, db, pages, cloud):
    """Behaviour `activity.jobs-are-a-tree`, cost: each call's tokens priced from the vendored list,
    summed up the tree to its step and its run."""
    tree = _finished_tree(client, db, pages, "gpt-5")
    one = price_call({"provider": "openai", "model": "gpt-5", **TOKENS}).cost_usd
    assert one  # the list prices this model
    assert [c["cost_usd"] for c in _calls(tree)] == pytest.approx([one] * 3)
    assert tree["cost_usd"] == pytest.approx(3 * one)
    assert tree["tokens"] == 3 * TOKENS["total_tokens"]
    entities = next(s for s in tree["children"] if s["subject"].endswith("Entities"))
    assert entities["cost_usd"] == pytest.approx(3 * one)


def test_activity_jobs_are_a_tree__an_unpriced_model_costs_null_never_a_guess(client, db, pages, cloud):
    """Behaviour `activity.jobs-are-a-tree`, cost: a model the price list does not know costs null,
    and so does every row above it: never zero, never a guess."""
    tree = _finished_tree(client, db, pages, "a-model-nobody-prices")
    assert {c["cost_usd"] for c in _calls(tree)} == {None}
    assert tree["cost_usd"] is None
    assert tree["tokens"] == 3 * TOKENS["total_tokens"]


def test_activity_jobs_are_a_tree__errors_and_time_roll_up(client, db, pages, cloud):
    """Behaviour `activity.jobs-are-a-tree`, errors and time: a call that failed is counted on its
    step and its run, with its reason on its own row; each row says how long it took, and a step
    took at least as long as its longest call."""
    cloud.fail_on = "Letter 1:"
    cloud.seconds = 0.2
    tree = _finished_tree(client, db, pages, "gpt-5")
    failed = [c for c in _calls(tree) if c["state"] == "failed"]
    assert len(failed) == 1 and "refused this letter" in failed[0]["reason"]
    assert tree["failed"] == 1
    entities = next(s for s in tree["children"] if s["subject"].endswith("Entities"))
    assert entities["failed"] == 1
    assert all(c["seconds"] >= 0.2 for c in _calls(tree) if c["state"] == "done")
    assert entities["seconds"] >= max(c["seconds"] for c in entities["children"])


def test_activity_job_tree_to_a_depth__rows_below_are_left_out_counts_kept(client, db, pages, cloud):
    """`activity.job-tree-to-a-depth` (#5605): "`?depth=1` returns a run and its steps; each step keeps its
    rolled-up counts and says how many children it left out." A 214-page run's whole tree was 235k characters."""
    whole = _finished_tree(client, db, pages, "gpt-4o-mini")
    run = whole["id"]
    cut = client.get(f"/api/activity/jobs/{run}", params={"depth": 1}).json()
    assert [s["id"] for s in cut["children"]] == [s["id"] for s in whole["children"]]
    for step, full in zip(cut["children"], whole["children"]):
        assert step["children"] == [] and step["children_omitted"] == len(full["children"])
        assert (step["done"], step["total"], step["failed"]) == (full["done"], full["total"], full["failed"])
    assert sum(s["children_omitted"] for s in cut["children"]) > 0, "the run's model calls are rows under its steps"
    root = client.get(f"/api/activity/jobs/{run}", params={"depth": 0}).json()
    assert root["children"] == [] and root["children_omitted"] == len(whole["children"])
    assert (root["done"], root["total"]) == (whole["done"], whole["total"])
