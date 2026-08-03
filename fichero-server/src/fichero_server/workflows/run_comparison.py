"""Diff two workflow runs of the same input (#4341).

The archive's hard question is not "did the workflow finish" but "is this
transcription any good". Nobody can read ten thousand pages to find out. What
you CAN do is run a page through two workflows — ensemble against single pass,
one prompt against a tweaked one — and look at the places they disagree, on the
theory that where two independent attempts agree there is usually little to
check, and where they diverge there usually is.

So this module produces a DIFF, not two blobs and a score. A similarity number
tells a historian nothing about which line to go and look at; a list saying
line 14 reads "Ospina" on the left and "Ocampo" on the right tells them exactly
where to put their eyes.

Three rules it exists to enforce:

**Broken and identical must never look alike.** If either run failed, was
cancelled, or is still going, the answer is ``comparable=False`` with a named
reason — never ``identical=True`` and an empty difference list. An empty diff
from a dead run is the same lie as #4284's step that "produced nothing"
because it never ran. ``identical`` is ``None`` whenever the comparison could
not be made, so a caller cannot read a falsy default as agreement.

**Two runs on different documents are not a comparison.** ``resolved_scope``
(#4384/#4396) already records the document set each run actually touched, so
the mismatch is detectable; ``same_input`` reports it, and reports ``None``
rather than ``True`` for runs recorded before that column existed.

**One capture path.** Everything here is derived from #4284's per-step records
and the artifact rows they already join. No new table, no second recorder, no
scraping a "response" back out of final state.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from fichero_server.workflows.run_steps import (
    STEP_FAILED,
    STEP_NOT_RUN,
    RunStep,
)

# A page of contested handwriting can differ on every line; a bad prompt can
# differ on every line of a whole book. Cap the reported differences so one
# comparison cannot return a megabyte, and SAY SO when the cap bites — a
# silently truncated diff reads as "these are all the differences", which is
# the failure this module is about.
MAX_TEXT_DIFFERENCES = 200
MAX_SET_LABELS = 200

# Two texts that agree nowhere collapse into a SINGLE difflib opcode spanning
# every line, so capping the number of differences does not bound the response
# at all — the one difference carries both documents whole. Bound the lines
# inside a difference too, and declare the clip.
MAX_LINES_PER_DIFFERENCE = 25

# How much of a differing line ships. Long lines are usually whole paragraphs
# in this corpus; the point is to locate the disagreement, not to re-transmit
# the artifact, which stays addressable at GET /api/artifacts/{id}.
MAX_LINE_CHARS = 400

#: Run statuses whose outputs can be meaningfully compared. Anything else —
#: failed, cancelled, still running, accepted-but-not-started — means one side
#: has no trustworthy output, and saying "no differences" about it would be
#: a fabrication.
COMPARABLE_RUN_STATUSES = frozenset({"completed"})

#: Keys checked, in order, for a human-readable label of a structured item.
#: Entities land as ``{"people": ["Ospina", ...]}`` so the plain-string case
#: dominates; claim/segment shapes are dicts and need a name.
_LABEL_KEYS = ("name", "text", "label", "title", "value", "id")

COST_NOTICE = (
    "Comparing means running the same input twice, so a fresh comparison "
    "costs roughly double a single run. Comparing two runs that already "
    "happened costs nothing extra."
)


class RunComparisonError(ValueError):
    """The comparison could not be attempted at all."""


@dataclass
class RunSide:
    """One side of a comparison: a run, its steps, and what it produced.

    ``artifacts`` are the artifact rows themselves rather than #4284's
    ``RunStepArtifact`` previews, because those truncate content at 2000 chars
    and carry ``has_structured_data`` instead of the data. Diffing a preview
    would report agreement past the truncation point. Read duck-typed, exactly
    as ``run_steps`` reads them, so tests need no ORM.
    """

    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str
    steps: Sequence[RunStep] = ()
    artifacts: Sequence[Any] = ()
    error: str | None = None
    resolved_scope: dict[str, Any] | None = None
    duration_ms: int | None = None


@dataclass
class SideSummary:
    """What one side did, in the terms #4284 already reports."""

    thread_id: str
    workflow_id: str
    workflow_name: str
    status: str
    error: str | None = None
    duration_ms: int | None = None
    artifact_count: int = 0
    steps_total: int = 0
    steps_failed: int = 0
    steps_not_run: int = 0
    steps_produced_nothing: int = 0
    resolved_document_count: int | None = None


@dataclass
class ArtifactRef:
    """Enough of an artifact to go and look at it."""

    artifact_id: str
    document_id: str
    document_name: str | None = None
    artifact_type: str = ""
    step_name: str | None = None
    provider: str | None = None
    model: str | None = None
    content_chars: int = 0


@dataclass
class TextDifference:
    """One place two transcriptions of the same page disagree."""

    kind: str  # "changed" | "added" | "removed"
    left_start_line: int | None
    right_start_line: int | None
    left_lines: list[str] = field(default_factory=list)
    right_lines: list[str] = field(default_factory=list)
    # True line counts of the block. They exceed the carried lines when a
    # difference spans more than MAX_LINES_PER_DIFFERENCE, which the flag says
    # out loud rather than leaving the reader to count.
    left_line_count: int = 0
    right_line_count: int = 0
    lines_truncated: bool = False


@dataclass
class TextDiff:
    """Line-level differences between two texts, plus a secondary ratio."""

    left_chars: int
    right_chars: int
    similarity: float
    differences: list[TextDifference] = field(default_factory=list)
    difference_count: int = 0
    differences_truncated: bool = False


@dataclass
class SetDifference:
    """What one side found under a structured field and the other missed."""

    field_name: str
    only_left: list[str] = field(default_factory=list)
    only_right: list[str] = field(default_factory=list)
    shared_count: int = 0
    only_left_count: int = 0
    only_right_count: int = 0
    labels_truncated: bool = False


@dataclass
class ValueDifference:
    """A structured field that is not a set and simply differs."""

    field_name: str
    left: str | None
    right: str | None


@dataclass
class ArtifactComparison:
    """Two artifacts of the same type about the same document, diffed."""

    document_id: str
    document_name: str | None
    artifact_type: str
    left: ArtifactRef
    right: ArtifactRef
    identical: bool
    text_diff: TextDiff | None = None
    set_differences: list[SetDifference] = field(default_factory=list)
    value_differences: list[ValueDifference] = field(default_factory=list)


@dataclass
class RunComparison:
    """The whole answer: where two runs of the same input disagree."""

    left: SideSummary
    right: SideSummary
    comparable: bool
    # Why the outputs cannot be trusted against each other. Set whenever
    # ``comparable`` is False, and the ONLY thing a caller should render then.
    incomparable_reason: str | None = None
    # None when at least one side predates resolved_scope (#4384): unknown is
    # not the same claim as "yes, same documents".
    same_input: bool | None = None
    input_note: str = ""
    # None whenever the comparison could not be made, so an empty difference
    # list from a broken run can never be read as agreement.
    identical: bool | None = None
    difference_count: int = 0
    compared: list[ArtifactComparison] = field(default_factory=list)
    only_left: list[ArtifactRef] = field(default_factory=list)
    only_right: list[ArtifactRef] = field(default_factory=list)
    cost_notice: str = COST_NOTICE


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def _resolved_ids(scope: dict[str, Any] | None) -> list[str] | None:
    if not isinstance(scope, dict):
        return None
    ids = scope.get("resolved_ids")
    if not isinstance(ids, list):
        return None
    return [str(i) for i in ids]


def _summarise(side: RunSide) -> SideSummary:
    resolved = _resolved_ids(side.resolved_scope)
    return SideSummary(
        thread_id=side.thread_id,
        workflow_id=side.workflow_id,
        workflow_name=side.workflow_name,
        status=side.status,
        error=side.error,
        duration_ms=side.duration_ms,
        artifact_count=len(list(side.artifacts)),
        steps_total=len(side.steps),
        steps_failed=sum(1 for s in side.steps if s.status == STEP_FAILED),
        steps_not_run=sum(1 for s in side.steps if s.status == STEP_NOT_RUN),
        steps_produced_nothing=sum(1 for s in side.steps if s.produced_nothing),
        resolved_document_count=len(resolved) if resolved is not None else None,
    )


def _incomparable_reason(label: str, side: RunSide) -> str | None:
    """Why this side's output cannot stand as one half of a comparison."""
    status = (side.status or "").strip() or "unknown"
    if status in COMPARABLE_RUN_STATUSES:
        return None
    if status == "failed":
        detail = f": {side.error}" if side.error else ""
        return (
            f"{label} run {side.thread_id} failed{detail}. Its output is "
            "incomplete, so an empty diff would mean 'broken', not 'identical'."
        )
    if status == "cancelled":
        return (
            f"{label} run {side.thread_id} was cancelled before it finished, "
            "so it has no complete output to compare."
        )
    if status in ("running", "accepted", "paused"):
        return (
            f"{label} run {side.thread_id} is still {status}; compare again "
            "once it reaches a terminal state."
        )
    return (
        f"{label} run {side.thread_id} is in state {status!r}, which is not a "
        "completed run; refusing to report its output as comparable."
    )


def _input_verdict(left: RunSide, right: RunSide) -> tuple[bool | None, str]:
    """Did these two runs actually see the same documents?

    A diff between runs over different material describes the material, not
    the workflows, so this is reported alongside every comparison rather than
    assumed.
    """
    left_ids = _resolved_ids(left.resolved_scope)
    right_ids = _resolved_ids(right.resolved_scope)
    if left_ids is None or right_ids is None:
        missing = [
            name
            for name, ids in (("left", left_ids), ("right", right_ids))
            if ids is None
        ]
        return None, (
            "Cannot confirm both runs saw the same input: no resolved scope "
            f"recorded for the {' and '.join(missing)} run (#4384 predates it). "
            "Read the differences as provisional."
        )
    left_set, right_set = set(left_ids), set(right_ids)
    if left_set == right_set:
        return True, f"Both runs resolved to the same {len(left_set)} document(s)."
    only_left = len(left_set - right_set)
    only_right = len(right_set - left_set)
    return False, (
        f"The two runs did NOT see the same input: {only_left} document(s) only "
        f"on the left, {only_right} only on the right, {len(left_set & right_set)} "
        "shared. Differences below may reflect the documents rather than the "
        "workflows."
    )


# ---------------------------------------------------------------------------
# Text diff
# ---------------------------------------------------------------------------


def _clip(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + "…"


def diff_text(left: str, right: str) -> TextDiff:
    """Line-level differences, named, with the ratio as a footnote.

    ``difflib`` opcodes give the ranges that differ; each becomes one
    ``TextDifference`` carrying both sides' lines and their 1-based line
    numbers, because "check line 14" is the actionable form.
    """
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)

    differences: list[TextDifference] = []
    total = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        total += 1
        if len(differences) >= MAX_TEXT_DIFFERENCES:
            continue
        kind = {"replace": "changed", "delete": "removed", "insert": "added"}[tag]
        left_block = left_lines[i1:i2]
        right_block = right_lines[j1:j2]
        differences.append(
            TextDifference(
                kind=kind,
                left_start_line=i1 + 1 if i2 > i1 else None,
                right_start_line=j1 + 1 if j2 > j1 else None,
                left_lines=[_clip(x) for x in left_block[:MAX_LINES_PER_DIFFERENCE]],
                right_lines=[_clip(x) for x in right_block[:MAX_LINES_PER_DIFFERENCE]],
                left_line_count=len(left_block),
                right_line_count=len(right_block),
                lines_truncated=(
                    len(left_block) > MAX_LINES_PER_DIFFERENCE
                    or len(right_block) > MAX_LINES_PER_DIFFERENCE
                ),
            )
        )

    return TextDiff(
        left_chars=len(left),
        right_chars=len(right),
        similarity=matcher.ratio(),
        differences=differences,
        difference_count=total,
        differences_truncated=total > len(differences),
    )


# ---------------------------------------------------------------------------
# Structured diff
# ---------------------------------------------------------------------------


def _item_label(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in _LABEL_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        # Claim-shaped items have no single name; the triple IS the identity.
        triple = [item.get(k) for k in ("subject", "predicate", "object")]
        if all(isinstance(part, str) and part for part in triple):
            return " ".join(str(part) for part in triple)
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)


def _labels(value: Any) -> list[str] | None:
    """Set-comparable labels for a structured field, or None if it is not a set."""
    if not isinstance(value, list):
        return None
    return [_item_label(item) for item in value]


def _scalar(value: Any) -> str:
    if isinstance(value, str):
        return _clip(value)
    return _clip(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))


def diff_structured(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> tuple[list[SetDifference], list[ValueDifference]]:
    """Which items each side found under each field, and what the other missed.

    An entities artifact is ``{"people": [...], "locations": [...]}``, so the
    per-field set difference IS the answer a historian wants: this workflow
    found Ospina and that one did not. Fields that are not lists cannot be
    treated as sets and are reported as plain value differences instead of
    being forced into a shape they do not have.
    """
    left = left or {}
    right = right or {}
    set_diffs: list[SetDifference] = []
    value_diffs: list[ValueDifference] = []

    for key in sorted(set(left) | set(right)):
        left_value = left.get(key)
        right_value = right.get(key)
        if left_value == right_value:
            continue
        left_labels = _labels(left_value)
        right_labels = _labels(right_value)
        if left_labels is None and right_labels is None:
            value_diffs.append(
                ValueDifference(
                    field_name=key,
                    left=None if key not in left else _scalar(left_value),
                    right=None if key not in right else _scalar(right_value),
                )
            )
            continue
        left_set = set(left_labels or [])
        right_set = set(right_labels or [])
        only_left = sorted(left_set - right_set)
        only_right = sorted(right_set - left_set)
        if not only_left and not only_right:
            # Same members, different order or duplicate counts. Real, but not
            # a finding about what was found; keep it visible as a value diff.
            value_diffs.append(
                ValueDifference(
                    field_name=key,
                    left=_scalar(left_value),
                    right=_scalar(right_value),
                )
            )
            continue
        set_diffs.append(
            SetDifference(
                field_name=key,
                only_left=only_left[:MAX_SET_LABELS],
                only_right=only_right[:MAX_SET_LABELS],
                shared_count=len(left_set & right_set),
                only_left_count=len(only_left),
                only_right_count=len(only_right),
                labels_truncated=(
                    len(only_left) > MAX_SET_LABELS or len(only_right) > MAX_SET_LABELS
                ),
            )
        )

    return set_diffs, value_diffs


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------


def _ref(artifact: Any, document_names: dict[str, str]) -> ArtifactRef:
    content = getattr(artifact, "content", None) or ""
    document_id = str(getattr(artifact, "document_id", "") or "")
    return ArtifactRef(
        artifact_id=str(getattr(artifact, "id", "") or ""),
        document_id=document_id,
        document_name=document_names.get(document_id),
        artifact_type=str(getattr(artifact, "artifact_type", "") or ""),
        step_name=getattr(artifact, "step_name", None),
        provider=getattr(artifact, "provider", None),
        model=getattr(artifact, "model", None),
        content_chars=len(content),
    )


def _pair_key(artifact: Any) -> tuple[str, str]:
    return (
        str(getattr(artifact, "document_id", "") or ""),
        str(getattr(artifact, "artifact_type", "") or ""),
    )


def _order_key(artifact: Any) -> tuple[int, str]:
    sequence = getattr(artifact, "sequence", None)
    created = getattr(artifact, "created_at", None)
    return (sequence if sequence is not None else 0, str(created or ""))


def _group(artifacts: Sequence[Any]) -> dict[tuple[str, str], list[Any]]:
    grouped: dict[tuple[str, str], list[Any]] = {}
    for artifact in artifacts:
        grouped.setdefault(_pair_key(artifact), []).append(artifact)
    for items in grouped.values():
        items.sort(key=_order_key)
    return grouped


def _compare_artifacts(
    left: Any,
    right: Any,
    document_names: dict[str, str],
) -> ArtifactComparison:
    left_content = getattr(left, "content", None) or ""
    right_content = getattr(right, "content", None) or ""
    left_data = getattr(left, "data", None)
    right_data = getattr(right, "data", None)

    text_diff = None
    if left_content or right_content:
        candidate = diff_text(left_content, right_content)
        if candidate.difference_count:
            text_diff = candidate

    set_diffs, value_diffs = diff_structured(left_data, right_data)
    document_id = str(getattr(left, "document_id", "") or "")

    return ArtifactComparison(
        document_id=document_id,
        document_name=document_names.get(document_id),
        artifact_type=str(getattr(left, "artifact_type", "") or ""),
        left=_ref(left, document_names),
        right=_ref(right, document_names),
        identical=not (text_diff or set_diffs or value_diffs),
        text_diff=text_diff,
        set_differences=set_diffs,
        value_differences=value_diffs,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compare_runs(
    left: RunSide,
    right: RunSide,
    *,
    document_names: dict[str, str] | None = None,
) -> RunComparison:
    """Diff what two runs produced from the same input.

    Refuses to answer rather than answering wrongly: if either run is not
    completed, the result carries ``comparable=False``, a reason naming which
    side and why, and ``identical=None``. A caller that renders
    ``identical`` without checking ``comparable`` therefore gets a visible
    ``None``, not a silent "no differences".
    """
    if left.thread_id and left.thread_id == right.thread_id:
        raise RunComparisonError(
            f"both sides name the same run ({left.thread_id}); a run compared "
            "against itself is not a comparison"
        )

    names = dict(document_names or {})
    summary_left = _summarise(left)
    summary_right = _summarise(right)
    same_input, input_note = _input_verdict(left, right)

    reason = _incomparable_reason("Left", left) or _incomparable_reason("Right", right)
    if reason:
        return RunComparison(
            left=summary_left,
            right=summary_right,
            comparable=False,
            incomparable_reason=reason,
            same_input=same_input,
            input_note=input_note,
            identical=None,
        )

    grouped_left = _group(left.artifacts)
    grouped_right = _group(right.artifacts)

    compared: list[ArtifactComparison] = []
    only_left: list[ArtifactRef] = []
    only_right: list[ArtifactRef] = []

    for key in sorted(set(grouped_left) | set(grouped_right)):
        left_items = grouped_left.get(key, [])
        right_items = grouped_right.get(key, [])
        paired = min(len(left_items), len(right_items))
        for index in range(paired):
            compared.append(
                _compare_artifacts(left_items[index], right_items[index], names)
            )
        # A workflow that produced three passes where the other produced one is
        # itself a difference; the surplus is reported, never dropped.
        only_left.extend(_ref(a, names) for a in left_items[paired:])
        only_right.extend(_ref(a, names) for a in right_items[paired:])

    difference_count = (
        sum(1 for c in compared if not c.identical) + len(only_left) + len(only_right)
    )

    return RunComparison(
        left=summary_left,
        right=summary_right,
        comparable=True,
        incomparable_reason=None,
        same_input=same_input,
        input_note=input_note,
        identical=difference_count == 0,
        difference_count=difference_count,
        compared=compared,
        only_left=only_left,
        only_right=only_right,
    )
