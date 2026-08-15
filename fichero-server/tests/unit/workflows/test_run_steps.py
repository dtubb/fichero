"""Per-step run records must be complete, traceable, and honest (#4284).

Three properties are load-bearing and each has a test here:

1. A run of N planned steps yields N records — never fewer, because a step
   that produced nothing must not vanish into the same absence as a step that
   never ran.
2. Every artifact record carries the whole provenance chain: run, workflow,
   step, source document, provider, model.
3. A step that was in flight when the run died is recorded as failed, not left
   claiming 'running' forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from fichero_server.workflows.run_steps import (
    ARTIFACT_PREVIEW_CHARS,
    STEP_COMPLETED,
    STEP_FAILED,
    STEP_NOT_RUN,
    STEP_SKIPPED,
    UnknownStepStatusError,
    build_run_steps,
    close_open_steps,
)

_T0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)


def _artifact(**overrides):
    """A stand-in for models.Artifact with the fields run_steps reads."""
    base = dict(
        id="art-1",
        artifact_type="transcription",
        document_id="doc-1",
        source_document_id="doc-parent",
        run_id="thread-1",
        workflow_id="wf-1",
        step_name="node-1",
        provider="qwen",
        model="qwen-vl-max",
        sequence=1,
        created_at=_T0,
        content="hello",
        data=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _node_entry(node_id: str, status: str, **extra):
    entry = {
        "node_id": node_id,
        "started_at": _T0.isoformat(),
        "status": status,
    }
    entry.update(extra)
    return entry


def _planned(*node_ids):
    return [
        {"node_id": n, "node_name": n.title(), "tool": "transcribe"} for n in node_ids
    ]


# =============================================================================
# 1. N planned steps yield N records
# =============================================================================


def test_run_with_n_steps_yields_n_records():
    steps = build_run_steps(
        planned_nodes=_planned("node-1", "node-2", "node-3"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[],
    )
    assert len(steps) == 3, "every planned step must yield exactly one record"
    assert [s.node_id for s in steps] == ["node-1", "node-2", "node-3"]


def test_timeline_recorded_under_display_names_folds_onto_planned_ids():
    """LangGraph events carry the graph's DISPLAY names, not snapshot ids.

    Without the name→id fold, every step of a completed run read "did not
    run" and its real execution appeared as an extra unplanned row
    (2026-08-12 trace screenshot).
    """
    steps = build_run_steps(
        planned_nodes=[
            {"node_id": "uuid-1", "node_name": "Transcribe", "tool": "transcribe"}
        ],
        progress_timeline={"steps": [_node_entry("Transcribe", "success")]},
        artifacts=[_artifact(step_name="Transcribe")],
        node_name_map={"uuid-1": "Transcribe"},
    )
    assert len(steps) == 1, "the executed step must fold onto its planned row"
    assert steps[0].node_id == "uuid-1"
    assert steps[0].status == STEP_COMPLETED
    assert steps[0].artifact_count == 1


def test_step_that_never_ran_is_not_run_not_absent():
    steps = build_run_steps(
        planned_nodes=_planned("node-1", "node-2"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[_artifact()],
    )
    by_id = {s.node_id: s for s in steps}
    assert by_id["node-2"].status == STEP_NOT_RUN
    # A step that never ran did not 'produce nothing' — it produced no answer
    # at all. Conflating the two is the gap this issue exists to close.
    assert by_id["node-2"].produced_nothing is False
    assert by_id["node-2"].artifact_count == 0


def test_completed_step_with_no_artifact_says_it_produced_nothing():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[],
    )
    assert steps[0].status == STEP_COMPLETED
    assert steps[0].produced_nothing is True, (
        "a step that ran to completion and produced nothing must SAY so, not "
        "look identical to a step that never ran"
    )


def test_failed_step_is_recorded_as_failed_with_its_error():
    steps = build_run_steps(
        planned_nodes=_planned("node-1", "node-2"),
        progress_timeline={
            "steps": [
                _node_entry("node-1", "success"),
                _node_entry("node-2", "failed", error="provider refused"),
            ]
        },
        artifacts=[],
    )
    failed = [s for s in steps if s.node_id == "node-2"][0]
    assert failed.status == STEP_FAILED
    assert failed.error == "provider refused"
    assert failed.produced_nothing is True


def test_skipped_step_keeps_its_reason():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={
            "steps": [_node_entry("node-1", "skipped", skip_reason="empty query")]
        },
        artifacts=[],
    )
    assert steps[0].status == STEP_SKIPPED
    assert steps[0].skip_reason == "empty query"


def test_node_that_ran_but_was_not_in_the_snapshot_is_still_reported():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={
            "steps": [
                _node_entry("node-1", "success"),
                _node_entry("ghost", "success"),
            ]
        },
        artifacts=[],
    )
    assert [s.node_id for s in steps] == ["node-1", "ghost"]
    assert steps[1].tool == "unknown"


def test_unknown_timeline_status_raises_rather_than_guessing():
    with pytest.raises(UnknownStepStatusError):
        build_run_steps(
            planned_nodes=_planned("node-1"),
            progress_timeline={"steps": [_node_entry("node-1", "weird-new-status")]},
            artifacts=[],
        )


def test_file_level_tallies_are_aggregated_onto_the_step():
    timeline = {
        "steps": [
            _node_entry("node-1", "success"),
            {"type": "file", "node_id": "node-1", "status": "success"},
            {"type": "file", "node_id": "node-1", "status": "error"},
            {"type": "file", "node_id": "node-1", "status": "error"},
        ]
    }
    steps = build_run_steps(
        planned_nodes=_planned("node-1"), progress_timeline=timeline, artifacts=[]
    )
    assert steps[0].files_total == 3
    assert steps[0].files_succeeded == 1
    assert steps[0].files_failed == 2


# =============================================================================
# 2. Full provenance on every artifact
# =============================================================================


def test_artifact_carries_full_provenance():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[_artifact()],
        node_name_map={"node-1": "Transcribe"},
        document_names={"doc-1": "page-3.png", "doc-parent": "diary.pdf"},
    )
    step = steps[0]
    assert step.artifact_count == 1
    assert step.produced_nothing is False
    art = step.artifacts[0]
    # Which run, which workflow, which step.
    assert art.run_id == "thread-1"
    assert art.workflow_id == "wf-1"
    assert art.step_name == "node-1"
    assert art.node_name == "Transcribe"
    # Which input.
    assert art.document_id == "doc-1"
    assert art.document_name == "page-3.png"
    assert art.source_document_id == "doc-parent"
    assert art.source_document_name == "diary.pdf"
    # Which model/provider produced it.
    assert art.provider == "qwen"
    assert art.model == "qwen-vl-max"
    # And where in the pipeline it sits.
    assert art.sequence == 1
    assert art.created_at == _T0.isoformat()


def test_artifact_preview_truncates_the_response_and_says_so():
    long_content = "x" * (ARTIFACT_PREVIEW_CHARS + 500)
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[_artifact(content=long_content)],
    )
    art = steps[0].artifacts[0]
    assert art.content_chars == len(long_content), (
        "the record must report the artifact's TRUE size, not the preview's"
    )
    assert len(art.content_preview) == ARTIFACT_PREVIEW_CHARS
    assert art.content_truncated is True


def test_short_artifact_is_not_marked_truncated():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[_artifact(content="short")],
    )
    art = steps[0].artifacts[0]
    assert art.content_preview == "short"
    assert art.content_truncated is False


def test_artifacts_are_ordered_by_pipeline_sequence():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[
            _artifact(id="art-b", sequence=2),
            _artifact(id="art-a", sequence=1),
        ],
    )
    assert [a.artifact_id for a in steps[0].artifacts] == ["art-a", "art-b"]


def test_artifact_with_no_step_name_is_surfaced_as_unattributed():
    steps = build_run_steps(
        planned_nodes=_planned("node-1"),
        progress_timeline={"steps": [_node_entry("node-1", "success")]},
        artifacts=[_artifact(id="orphan", step_name=None)],
    )
    assert steps[-1].node_name == "(unattributed)"
    assert [a.artifact_id for a in steps[-1].artifacts] == ["orphan"], (
        "output whose producing step is unknown must be visibly unattributed, "
        "never silently dropped"
    )


# =============================================================================
# 3. In-flight steps are settled when the run ends
# =============================================================================


def test_close_open_steps_marks_the_in_flight_node_failed():
    timeline = {
        "steps": [
            _node_entry("node-1", "success", completed_at=_T0.isoformat()),
            _node_entry("node-2", "running"),
        ]
    }
    closed = close_open_steps(
        timeline,
        status="failed",
        error="engine died",
        completed_at=_T0 + timedelta(seconds=5),
    )
    assert closed == 1
    assert timeline["steps"][0]["status"] == "success", "settled steps are untouched"
    dead = timeline["steps"][1]
    assert dead["status"] == "failed"
    assert dead["error"] == "engine died"
    assert dead["terminated_by_run"] is True
    assert dead["duration_ms"] == pytest.approx(5000)


def test_closed_step_reads_back_as_failed_and_terminated_by_run():
    timeline = {"steps": [_node_entry("node-1", "running")]}
    close_open_steps(timeline, status="failed", error="boom")
    steps = build_run_steps(
        planned_nodes=_planned("node-1"), progress_timeline=timeline, artifacts=[]
    )
    assert steps[0].status == STEP_FAILED
    assert steps[0].terminated_by_run is True
    assert steps[0].error == "boom"


def test_close_open_steps_settles_file_entries_in_their_own_vocabulary():
    timeline = {
        "steps": [
            _node_entry("node-1", "running"),
            {
                "type": "file",
                "node_id": "node-1",
                "status": "running",
                "started_at": _T0.isoformat(),
            },
        ]
    }
    assert close_open_steps(timeline, status="cancelled") == 2
    assert timeline["steps"][0]["status"] == "cancelled"
    assert timeline["steps"][1]["status"] == "cancelled"


def test_close_open_steps_is_idempotent():
    timeline = {"steps": [_node_entry("node-1", "running")]}
    assert close_open_steps(timeline, status="failed") == 1
    assert close_open_steps(timeline, status="failed") == 0


def test_close_open_steps_refuses_a_non_terminal_status():
    with pytest.raises(ValueError):
        close_open_steps({"steps": []}, status="running")


def test_close_open_steps_tolerates_a_missing_timeline():
    assert close_open_steps(None, status="failed") == 0
    assert close_open_steps({}, status="failed") == 0
