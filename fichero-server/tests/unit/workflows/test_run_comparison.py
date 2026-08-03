"""Two runs of the same input must disagree legibly, or say why they can't (#4341).

The properties that matter, each with a test:

1. Identical workflows produce an empty diff and say ``identical=True``.
2. Genuinely different outputs name the SPECIFIC differences — which line,
   which entity — not merely a similarity score.
3. A failed run on one side is reported as failed. It must never come back as
   ``identical=True`` with an empty difference list, because
   empty-because-broken and empty-because-identical are different findings.
   Same distinction as #4284's ``produced_nothing`` vs ``not_run``.
4. Two runs over different documents are flagged, because a diff between runs
   on different material describes the material.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from fichero_server.workflows.run_comparison import (
    MAX_LINES_PER_DIFFERENCE,
    MAX_TEXT_DIFFERENCES,
    RunComparisonError,
    RunSide,
    compare_runs,
    diff_structured,
    diff_text,
)
from fichero_server.workflows.run_steps import (
    STEP_COMPLETED,
    STEP_FAILED,
    STEP_NOT_RUN,
    RunStep,
)

_T0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)


def _artifact(**overrides):
    """A stand-in for models.Artifact with the fields run_comparison reads."""
    base = dict(
        id="art-1",
        artifact_type="transcription",
        document_id="doc-1",
        source_document_id=None,
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


def _step(node_id="node-1", status=STEP_COMPLETED, **overrides):
    return RunStep(
        node_id=node_id,
        node_name=overrides.pop("node_name", node_id),
        tool=overrides.pop("tool", "transcribe"),
        status=status,
        **overrides,
    )


def _side(thread_id, **overrides):
    base = dict(
        thread_id=thread_id,
        workflow_id=f"wf-{thread_id}",
        workflow_name=f"Workflow {thread_id}",
        status="completed",
        steps=[_step()],
        artifacts=[],
        resolved_scope={"resolved_ids": ["doc-1"], "resolved_count": 1},
    )
    base.update(overrides)
    return RunSide(**base)


# =============================================================================
# 1. Identical workflows produce an empty diff
# =============================================================================


def test_identical_outputs_report_no_differences():
    text = "En el nombre de Dios\nsea notorio a todos"
    left = _side("t-left", artifacts=[_artifact(id="a", content=text)])
    right = _side("t-right", artifacts=[_artifact(id="b", content=text)])

    result = compare_runs(left, right)

    assert result.comparable is True
    assert result.identical is True
    assert result.difference_count == 0
    assert result.only_left == [] and result.only_right == []
    assert len(result.compared) == 1
    assert result.compared[0].identical is True
    assert result.compared[0].text_diff is None


def test_identical_structured_output_reports_no_differences():
    data = {"people": ["Ospina", "Restrepo"], "locations": ["Popayán"]}
    left = _side("t-left", artifacts=[_artifact(id="a", content=None, data=data)])
    right = _side(
        "t-right",
        # Same members in a different order is the same finding.
        artifacts=[
            _artifact(
                id="b",
                content=None,
                data={"people": ["Ospina", "Restrepo"], "locations": ["Popayán"]},
            )
        ],
    )

    result = compare_runs(left, right)

    assert result.identical is True
    assert result.compared[0].set_differences == []
    assert result.compared[0].value_differences == []


# =============================================================================
# 2. Different outputs name the specific differences
# =============================================================================


def test_transcription_difference_names_the_line_not_just_a_score():
    left = _side(
        "t-left",
        artifacts=[
            _artifact(id="a", content="linea uno\nfirmado Ospina\nlinea tres")
        ],
    )
    right = _side(
        "t-right",
        artifacts=[
            _artifact(id="b", content="linea uno\nfirmado Ocampo\nlinea tres")
        ],
    )

    result = compare_runs(left, right)

    assert result.identical is False
    assert result.difference_count == 1
    comparison = result.compared[0]
    assert comparison.identical is False

    diff = comparison.text_diff
    assert diff is not None
    # The point of the whole feature: WHICH line, and what each side read.
    assert diff.difference_count == 1
    difference = diff.differences[0]
    assert difference.kind == "changed"
    assert difference.left_start_line == 2
    assert difference.right_start_line == 2
    assert difference.left_lines == ["firmado Ospina"]
    assert difference.right_lines == ["firmado Ocampo"]
    # A ratio alone would not have told anyone to look at line 2.
    assert 0.0 < diff.similarity < 1.0


def test_added_and_removed_lines_are_distinguished():
    left = _side("t-left", artifacts=[_artifact(id="a", content="uno\ndos")])
    right = _side("t-right", artifacts=[_artifact(id="b", content="uno\ndos\ntres")])

    diff = compare_runs(left, right).compared[0].text_diff

    assert diff is not None
    assert [d.kind for d in diff.differences] == ["added"]
    assert diff.differences[0].right_lines == ["tres"]
    assert diff.differences[0].left_lines == []
    assert diff.differences[0].left_start_line is None


def test_extraction_difference_names_what_each_side_missed():
    left = _side(
        "t-left",
        artifacts=[
            _artifact(
                id="a",
                artifact_type="entities",
                content=None,
                data={"people": ["Ospina", "Restrepo"], "locations": ["Popayán"]},
            )
        ],
    )
    right = _side(
        "t-right",
        artifacts=[
            _artifact(
                id="b",
                artifact_type="entities",
                content=None,
                data={"people": ["Ospina", "Ocampo"], "locations": ["Popayán"]},
            )
        ],
    )

    result = compare_runs(left, right)

    assert result.identical is False
    diffs = {d.field_name: d for d in result.compared[0].set_differences}
    assert set(diffs) == {"people"}, "a field both sides agreed on is not a difference"
    people = diffs["people"]
    assert people.only_left == ["Restrepo"]
    assert people.only_right == ["Ocampo"]
    assert people.shared_count == 1


def test_claim_shaped_items_are_identified_by_their_triple():
    def claims(items):
        return {"claims": items}

    left_only = {"subject": "Ospina", "predicate": "residedIn", "object": "Popayán"}
    shared = {"subject": "Ospina", "predicate": "bornIn", "object": "Cali"}
    left = _side(
        "t-left",
        artifacts=[
            _artifact(id="a", artifact_type="claims", content=None, data=claims([shared, left_only]))
        ],
    )
    right = _side(
        "t-right",
        artifacts=[
            _artifact(id="b", artifact_type="claims", content=None, data=claims([shared]))
        ],
    )

    set_diffs = compare_runs(left, right).compared[0].set_differences

    assert len(set_diffs) == 1
    assert set_diffs[0].only_left == ["Ospina residedIn Popayán"]
    assert set_diffs[0].only_right == []


def test_artifact_only_one_side_produced_is_a_difference():
    left = _side(
        "t-left",
        artifacts=[
            _artifact(id="a", content="texto"),
            _artifact(id="b", artifact_type="summary", content="resumen", sequence=2),
        ],
    )
    right = _side("t-right", artifacts=[_artifact(id="c", content="texto")])

    result = compare_runs(left, right)

    assert result.identical is False
    assert result.difference_count == 1
    assert [ref.artifact_type for ref in result.only_left] == ["summary"]
    assert result.only_right == []


def test_many_scattered_differences_are_capped_and_the_cap_is_declared():
    # Every other line differs, so difflib yields one opcode per differing
    # line rather than one block covering everything.
    count = MAX_TEXT_DIFFERENCES + 20
    left_text = "\n".join(
        f"linea {i}" if i % 2 else f"linea {i} izquierda" for i in range(count * 2)
    )
    right_text = "\n".join(
        f"linea {i}" if i % 2 else f"linea {i} derecha" for i in range(count * 2)
    )
    left = _side("t-left", artifacts=[_artifact(id="a", content=left_text)])
    right = _side("t-right", artifacts=[_artifact(id="b", content=right_text)])

    diff = compare_runs(left, right).compared[0].text_diff

    assert diff is not None
    assert len(diff.differences) == MAX_TEXT_DIFFERENCES
    # A truncated diff that claims to be the whole diff is the same lie this
    # module exists to prevent.
    assert diff.differences_truncated is True
    assert diff.difference_count > MAX_TEXT_DIFFERENCES


def test_a_difference_spanning_the_whole_document_is_bounded_and_says_so():
    # Two texts that agree nowhere collapse into ONE difflib opcode. Capping
    # the number of differences would not bound this at all — without a
    # per-difference line cap the single difference carries both documents.
    lines = MAX_LINES_PER_DIFFERENCE + 40
    left_text = "\n".join(f"linea {i} izquierda" for i in range(lines))
    right_text = "\n".join(f"renglon {i} derecha" for i in range(lines))
    left = _side("t-left", artifacts=[_artifact(id="a", content=left_text)])
    right = _side("t-right", artifacts=[_artifact(id="b", content=right_text)])

    diff = compare_runs(left, right).compared[0].text_diff

    assert diff is not None
    assert diff.difference_count == 1
    difference = diff.differences[0]
    assert len(difference.left_lines) == MAX_LINES_PER_DIFFERENCE
    assert len(difference.right_lines) == MAX_LINES_PER_DIFFERENCE
    # The true extent is still reported, so nobody reads 25 lines as the whole
    # disagreement.
    assert difference.left_line_count == lines
    assert difference.right_line_count == lines
    assert difference.lines_truncated is True


# =============================================================================
# 3. A failed side is reported as failed, never as "no differences"
# =============================================================================


@pytest.mark.parametrize(
    "status",
    ["failed", "cancelled", "running", "accepted", "paused"],
)
def test_non_completed_side_is_not_comparable(status):
    left = _side("t-left", status=status, error="node blew up", artifacts=[])
    right = _side("t-right", artifacts=[_artifact(id="b", content="texto")])

    result = compare_runs(left, right)

    assert result.comparable is False
    assert result.incomparable_reason
    assert "t-left" in result.incomparable_reason
    # The load-bearing assertion: broken must not read as agreement.
    assert result.identical is None
    assert result.difference_count == 0
    assert result.compared == []


def test_failed_side_reason_carries_the_error():
    left = _side("t-left", status="failed", error="vision model timed out")
    right = _side("t-right")

    reason = compare_runs(left, right).incomparable_reason

    assert reason is not None
    assert "vision model timed out" in reason


def test_failed_right_side_is_named_as_the_right_side():
    left = _side("t-left")
    right = _side("t-right", status="failed", error="boom")

    result = compare_runs(left, right)

    assert result.comparable is False
    assert result.incomparable_reason is not None
    assert result.incomparable_reason.startswith("Right run t-right")


def test_unknown_status_is_refused_rather_than_assumed_complete():
    left = _side("t-left", status="weird-new-state")
    right = _side("t-right")

    result = compare_runs(left, right)

    assert result.comparable is False
    assert result.identical is None
    assert "weird-new-state" in (result.incomparable_reason or "")


def test_side_summary_surfaces_step_level_failures_even_when_comparable():
    left = _side(
        "t-left",
        steps=[
            _step("node-1", STEP_COMPLETED),
            _step("node-2", STEP_FAILED),
            _step("node-3", STEP_NOT_RUN),
            _step("node-4", STEP_COMPLETED, produced_nothing=True),
        ],
        artifacts=[_artifact(id="a", content="texto")],
    )
    right = _side("t-right", artifacts=[_artifact(id="b", content="texto")])

    summary = compare_runs(left, right).left

    assert summary.steps_total == 4
    assert summary.steps_failed == 1
    assert summary.steps_not_run == 1
    assert summary.steps_produced_nothing == 1
    assert summary.artifact_count == 1


def test_comparing_a_run_against_itself_is_refused():
    side = _side("t-same")

    with pytest.raises(RunComparisonError, match="same run"):
        compare_runs(side, _side("t-same"))


# =============================================================================
# 4. Same-input honesty
# =============================================================================


def test_same_resolved_scope_is_confirmed():
    left = _side("t-left")
    right = _side("t-right")

    result = compare_runs(left, right)

    assert result.same_input is True
    assert "same 1 document" in result.input_note


def test_different_resolved_scope_is_flagged():
    left = _side("t-left", resolved_scope={"resolved_ids": ["doc-1", "doc-2"]})
    right = _side("t-right", resolved_scope={"resolved_ids": ["doc-2", "doc-3"]})

    result = compare_runs(left, right)

    assert result.same_input is False
    assert "did NOT see the same input" in result.input_note


def test_missing_resolved_scope_reports_unknown_not_yes():
    left = _side("t-left", resolved_scope=None)
    right = _side("t-right")

    result = compare_runs(left, right)

    # Unknown is not the same claim as "yes, same documents".
    assert result.same_input is None
    assert "left" in result.input_note


def test_cost_notice_states_that_comparing_means_running_twice():
    result = compare_runs(_side("t-left"), _side("t-right"))

    assert "twice" in result.cost_notice
    assert "double" in result.cost_notice


# =============================================================================
# Pure helpers
# =============================================================================


def test_diff_text_on_equal_input_has_no_differences():
    diff = diff_text("igual", "igual")

    assert diff.difference_count == 0
    assert diff.differences == []
    assert diff.similarity == 1.0


def test_diff_structured_reports_a_field_only_one_side_has():
    set_diffs, value_diffs = diff_structured({"people": ["Ospina"]}, {})

    assert value_diffs == []
    assert len(set_diffs) == 1
    assert set_diffs[0].field_name == "people"
    assert set_diffs[0].only_left == ["Ospina"]
    assert set_diffs[0].only_right == []


def test_diff_structured_reports_non_list_fields_as_value_differences():
    set_diffs, value_diffs = diff_structured({"language": "es"}, {"language": "en"})

    assert set_diffs == []
    assert len(value_diffs) == 1
    assert value_diffs[0].field_name == "language"
    assert value_diffs[0].left == "es"
    assert value_diffs[0].right == "en"


def test_diff_structured_ignores_fields_both_sides_agree_on():
    set_diffs, value_diffs = diff_structured(
        {"people": ["Ospina"], "language": "es"},
        {"people": ["Ospina"], "language": "es"},
    )

    assert set_diffs == [] and value_diffs == []
