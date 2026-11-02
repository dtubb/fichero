"""`workflows.run.cost-tracking-per-node` (docs/contributor_manual/specs/ui/workflows.md, Step 2.2, #4343): each step of a run
says what it spent, beside the run's own total.

WHY: the runner already copied a step's tokens and cost onto its timeline entry (the seam the trace left open), but the step
record never read them, so the trace could not show them. Present only when the step called a model; unpriced is null, never 0.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.workflows.run_steps import build_run_steps

_T0 = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc).isoformat()


def _entry(node_id, **extra):
    return {"node_id": node_id, "started_at": _T0, "completed_at": _T0, "status": "success", **extra}


def _steps(*entries):
    planned = [{"node_id": e["node_id"], "node_name": e["node_id"], "tool": "transcribe"} for e in entries]
    return {s.node_id: s for s in build_run_steps(planned_nodes=planned, progress_timeline={"steps": list(entries)}, artifacts=[])}


def test_a_step_that_called_a_model_carries_its_calls_tokens_and_cost():
    step = _steps(_entry("a", model_calls=3, total_tokens=1200, cost_usd=0.0042, cost_priced=True))["a"]
    assert (step.model_calls, step.total_tokens, step.cost_usd, step.cost_priced) == (3, 1200, 0.0042, True)


def test_a_step_that_called_nothing_shows_nothing_not_a_zero():
    step = _steps(_entry("a"))["a"]
    assert (step.model_calls, step.total_tokens, step.cost_usd, step.cost_priced) == (None, None, None, None)


def test_an_unpriced_step_has_tokens_and_a_null_cost_never_a_zero():
    step = _steps(_entry("a", model_calls=1, total_tokens=500, cost_priced=False))["a"]
    assert step.total_tokens == 500 and step.cost_usd is None and step.cost_priced is False


def test_a_step_that_never_ran_has_no_spend():
    planned = [{"node_id": "z", "node_name": "z", "tool": "transcribe"}]
    step = build_run_steps(planned_nodes=planned, progress_timeline={"steps": []}, artifacts=[])[0]
    assert step.status == "not_run" and step.model_calls is None and step.cost_usd is None


def test_the_run_response_serves_the_per_step_fields():
    from fichero_server.api.routes.workflow_execution.threads import WorkflowRunStepResponse

    fields = set(WorkflowRunStepResponse.model_fields)
    assert {"model_calls", "total_tokens", "cost_usd", "cost_priced"} <= fields
