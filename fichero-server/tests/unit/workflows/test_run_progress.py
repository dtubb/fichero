"""A run's progress, counted from its state and its checkpoint's pending writes (#5401).

The status a run reported was its whole state: 526 KB for a 50-photo Gemini run over MCP, which an
agent cannot read. Progress is what a person or an agent polls for instead.
"""
from __future__ import annotations

import json

from fichero_server.workflows.run_progress import MAX_FAILURES_LISTED, summarize_run_state


def _item(i, total, *, error=None, cancelled=False, result_error=None):
    item = {"file": f"/photos/SM_NPQ_C02_{i:03d}.jpg", "index": i, "total": total}
    if error:
        item.update(success=False, error=error)
    elif cancelled:
        item.update(success=False, cancelled=True, error="cancelled")
    else:
        item["result"] = {"artifacts": ["a"], "error": result_error}
    return item


def test_a_running_fan_out_is_counted_from_pending_writes():
    """WHY: LangGraph does not advance the checkpoint until every fanned-out file is done; the finished
    files are only in the pending writes. Counting only the state would say 0 of 104 for the whole
    14 minutes of the C02 run and then jump to 104."""
    state = {"files": [f"f{i}" for i in range(104)], "current_node": "files-source",
             "completed_nodes": ["files-source"], "parallel_results": {}}
    writes = [(f"task-{i}", "parallel_results", {"transcribe": [_item(i, 104)]}) for i in range(30)]
    writes.append(("task-x", "__pregel_tasks", ["ignored"]))

    progress = summarize_run_state(state, writes)

    assert progress.files_total == 104 and progress.current_node == "files-source"
    (step,) = progress.steps
    assert (step.node, step.total, step.done, step.succeeded, step.failed) == ("transcribe", 104, 30, 30, 0)


def test_failures_are_counted_and_named_by_file():
    """WHY: the C02 run ended 'completed' with 6 of 104 photos failed on a provider hang, and only
    activity rows said which (#5116). The failed files must be in the status an agent polls, by
    name, so it can rerun just those."""
    items = [_item(i, 10) for i in range(7)] + [
        _item(7, 10, error="vision exceeded 600.0s — provider hang"),
        _item(8, 10, result_error="empty response"),
        _item(9, 10, cancelled=True),
    ]
    (step,) = summarize_run_state({"parallel_results": {"transcribe": items}}).steps
    assert (step.done, step.succeeded, step.failed, step.cancelled) == (10, 7, 2, 1)
    assert [f.file for f in step.failures] == ["SM_NPQ_C02_007.jpg", "SM_NPQ_C02_008.jpg"]
    assert "provider hang" in step.failures[0].error


def test_a_retried_file_counts_once():
    """WHY: a file whose branch is retried writes twice; counting both would report more files done
    than the run has."""
    items = [_item(0, 2, error="timeout"), _item(0, 2), _item(1, 2)]
    (step,) = summarize_run_state({"parallel_results": {"t": items}}).steps
    assert (step.done, step.succeeded, step.failed) == (2, 2, 0)


def test_the_failure_list_is_bounded_but_the_counts_are_not():
    """WHY: a run where every page fails must still answer in a few KB; the counts stay exact."""
    items = [_item(i, 500, error="boom") for i in range(500)]
    (step,) = summarize_run_state({"parallel_results": {"t": items}}).steps
    assert step.failed == 500 and len(step.failures) == MAX_FAILURES_LISTED


def test_progress_of_a_large_run_is_small():
    """WHY this is the point of #5401: the status of a 104-file run must be pollable by an agent.
    The whole state was 526 KB at 50 files; progress must stay under a few KB at 104."""
    state = {"files": [f"/photos/{'x' * 80}_{i}.jpg" for i in range(104)],
             "parallel_results": {"transcribe": [_item(i, 104) for i in range(104)]},
             "outputs": {"files-source": {"documents": [{"metadata": "y" * 2000}] * 104}}}
    size = len(summarize_run_state(state).model_dump_json())
    assert size < 2000, size
    assert len(json.dumps(state)) > 100 * size


def test_an_empty_or_odd_state_is_not_an_error():
    """WHY: status is polled from the first second of a run, before anything is in its state, and
    pending writes carry other channels; progress must answer, not raise."""
    progress = summarize_run_state(None, [("t", "parallel_results", None), ("t",), "junk"])
    assert progress.steps == [] and progress.files_total == 0
