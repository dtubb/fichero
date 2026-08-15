"""
Per-step run records: what each workflow step actually produced (#4284).

Before this module a run recorded two things that never met. ``workflow_runs``
carried a ``progress_timeline`` — node started, node finished, how long — and
the ``artifacts`` table carried the OUTPUTS, tagged with ``run_id`` and
``step_name`` since #4313. Nothing joined them, so the activity view could show
that a step ran but never what it produced, and a step that ran and produced
NOTHING was indistinguishable from a step that never ran at all: both were
simply absent from the artifact list.

Two functions live here:

``close_open_steps``
    Called from the runner's terminal paths. When a run dies or is cancelled
    mid-node, the timeline entry for the node still in flight is left at
    ``status="running"`` forever — the record claims a step is running for a run
    that ended hours ago. Closing them out is what makes the FAILING step
    legible: it is the one marked failed, not the one that silently stops
    having entries.

``build_run_steps``
    Derives exactly one record per planned step of a run, joining the snapshot
    (what was SUPPOSED to run), the timeline (what DID run), and the artifacts
    (what it PRODUCED). A planned step with no timeline entry is reported as
    ``not_run`` — an explicit status, never a gap.

Nothing here writes a new table. Everything is derived from columns that
already exist, which is deliberate: per-step outputs on a real archive can grow
without bound, and adding a second copy of every step's output is a storage
decision that needs Daniel's eye, not a side effect of making runs legible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

# How much of an artifact's text ships inline with the step record. The full
# content stays addressable at GET /api/artifacts/{artifact_id}; this is a
# preview so the activity view can render a run without pulling every
# transcription pass into one response. It TRUNCATES the response, never the
# stored artifact — no data is dropped on the way in.
ARTIFACT_PREVIEW_CHARS = 2000

# Status a step record can carry. Distinct from the run-level RunStatus: these
# describe one node.
STEP_NOT_RUN = "not_run"
STEP_RUNNING = "running"
STEP_COMPLETED = "completed"
STEP_SKIPPED = "skipped"
STEP_FAILED = "failed"
STEP_CANCELLED = "cancelled"

_TERMINAL_STEP_STATUSES = frozenset(
    {STEP_COMPLETED, STEP_SKIPPED, STEP_FAILED, STEP_CANCELLED}
)

# progress_timeline entries use the runner's own vocabulary ('success' for a
# node that finished). Translate it once, here, and RAISE on anything
# unrecognised — a status we cannot read must not be quietly rendered as
# 'completed', because a green step nobody can justify is exactly the
# confident-sounding-output-with-no-origin this work exists to prevent.
_TIMELINE_TO_STEP_STATUS = {
    "success": STEP_COMPLETED,
    "completed": STEP_COMPLETED,
    "running": STEP_RUNNING,
    "skipped": STEP_SKIPPED,
    "failed": STEP_FAILED,
    "error": STEP_FAILED,
    "cancelled": STEP_CANCELLED,
}

# File-level timeline entries speak a narrower vocabulary than node entries.
_RUN_STATUS_TO_FILE_STATUS = {
    STEP_FAILED: "error",
    STEP_CANCELLED: "cancelled",
}


class UnknownStepStatusError(ValueError):
    """A timeline entry carried a status this module cannot interpret."""


@dataclass
class RunStepArtifact:
    """One artifact produced by one step, with the provenance to trace it."""

    artifact_id: str
    artifact_type: str
    document_id: str
    document_name: str | None = None
    source_document_id: str | None = None
    source_document_name: str | None = None
    # Provenance: which run, which step, which workflow, which model.
    run_id: str | None = None
    workflow_id: str | None = None
    step_name: str | None = None
    node_name: str | None = None
    provider: str | None = None
    model: str | None = None
    sequence: int | None = None
    created_at: str | None = None
    # Content, previewed rather than inlined whole (see ARTIFACT_PREVIEW_CHARS).
    content_chars: int = 0
    content_preview: str | None = None
    content_truncated: bool = False
    has_structured_data: bool = False


@dataclass
class RunStep:
    """What one step of a run was asked to do, did, and produced."""

    node_id: str
    node_name: str
    tool: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    skip_reason: str | None = None
    # True when the run ended while this step was still in flight, so its
    # terminal status was assigned by the run dying rather than by the step
    # reporting an outcome of its own.
    terminated_by_run: bool = False
    # Per-file tallies for fan-out steps, aggregated from file timeline entries.
    files_total: int = 0
    files_succeeded: int = 0
    files_failed: int = 0
    artifact_count: int = 0
    # A step that reached a terminal state having produced no artifact. The
    # honest version of the gap: 'ran, produced nothing' is a finding, not an
    # absence.
    produced_nothing: bool = False
    artifacts: list[RunStepArtifact] = field(default_factory=list)


def _is_node_entry(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") is None


def _is_file_entry(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("type") == "file"


def _timeline_steps(progress_timeline: Any) -> list[dict[str, Any]]:
    if not isinstance(progress_timeline, dict):
        return []
    steps = progress_timeline.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _step_status_from_timeline(raw: Any) -> str:
    if raw is None:
        raise UnknownStepStatusError(
            "progress_timeline entry has no status; refusing to guess an outcome"
        )
    key = str(raw)
    try:
        return _TIMELINE_TO_STEP_STATUS[key]
    except KeyError as exc:
        raise UnknownStepStatusError(
            f"unrecognised progress_timeline step status {key!r}; "
            "refusing to report it as an outcome it may not be"
        ) from exc


def close_open_steps(
    progress_timeline: Any,
    *,
    status: str,
    error: str | None = None,
    completed_at: datetime | None = None,
) -> int:
    """Give every still-running timeline entry the run's terminal outcome.

    A run that fails or is cancelled inside a node leaves that node's entry at
    ``status="running"``. Left alone the record says a step is running long
    after the run is over, and the step that actually broke is the one the
    activity view cannot point at. Returns the number of entries closed so the
    caller can log it.

    Mutates ``progress_timeline`` in place. Safe to call more than once: only
    entries still marked running are touched.
    """
    if status not in _TERMINAL_STEP_STATUSES:
        raise ValueError(
            f"close_open_steps needs a terminal status, got {status!r}"
        )
    entries = _timeline_steps(progress_timeline)
    if not entries:
        return 0

    when = completed_at or datetime.now(timezone.utc)
    when_iso = when.isoformat()
    file_status = _RUN_STATUS_TO_FILE_STATUS[status]
    closed = 0

    for entry in entries:
        if entry.get("status") != "running":
            continue
        entry["completed_at"] = when_iso
        entry["status"] = file_status if _is_file_entry(entry) else status
        entry["terminated_by_run"] = True
        if error:
            entry["error"] = error
        started_raw = entry.get("started_at")
        if isinstance(started_raw, str):
            try:
                started = datetime.fromisoformat(started_raw)
            except ValueError:
                started = None
            if started is not None:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                entry["duration_ms"] = (when - started).total_seconds() * 1000
        closed += 1
    return closed


def _artifact_record(
    artifact: Any,
    *,
    node_name_map: dict[str, str],
    document_names: dict[str, str],
) -> RunStepArtifact:
    content = getattr(artifact, "content", None) or ""
    step_name = getattr(artifact, "step_name", None)
    created_at = getattr(artifact, "created_at", None)
    source_id = getattr(artifact, "source_document_id", None)
    return RunStepArtifact(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        document_id=artifact.document_id,
        document_name=document_names.get(artifact.document_id),
        source_document_id=source_id,
        source_document_name=document_names.get(source_id) if source_id else None,
        run_id=getattr(artifact, "run_id", None),
        workflow_id=getattr(artifact, "workflow_id", None),
        step_name=step_name,
        # step_name may be a node ID (map to its display name) or already
        # the display name the graph ran under (stands as-is).
        node_name=node_name_map.get(step_name, step_name) if step_name else None,
        provider=getattr(artifact, "provider", None),
        model=getattr(artifact, "model", None),
        sequence=getattr(artifact, "sequence", None),
        created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        content_chars=len(content),
        content_preview=content[:ARTIFACT_PREVIEW_CHARS] if content else None,
        content_truncated=len(content) > ARTIFACT_PREVIEW_CHARS,
        has_structured_data=getattr(artifact, "data", None) is not None,
    )


def _artifact_sort_key(artifact: Any) -> tuple[int, str]:
    sequence = getattr(artifact, "sequence", None)
    created = getattr(artifact, "created_at", None)
    return (sequence if sequence is not None else 0, str(created or ""))


def build_run_steps(
    *,
    planned_nodes: Sequence[dict[str, Any]],
    progress_timeline: Any,
    artifacts: Iterable[Any],
    node_name_map: dict[str, str] | None = None,
    document_names: dict[str, str] | None = None,
) -> list[RunStep]:
    """One record per step of a run: planned, observed, and produced.

    ``planned_nodes`` are the snapshot nodes (dicts with at least ``node_id``;
    ``node_name``/``tool`` optional). Every one yields exactly one record, so a
    run of N planned steps always yields N records — a step that never started
    is reported ``not_run`` rather than dropped. Any node that appears in the
    timeline or in an artifact but NOT in the snapshot is appended after them,
    because silently discarding evidence that something ran would be the same
    lie in the other direction.
    """
    names = dict(node_name_map or {})
    doc_names = dict(document_names or {})

    # The graph registers nodes under their DISPLAY names, and LangGraph
    # events (and artifact step_names) are recorded in that name space —
    # while ``planned_nodes`` carry the snapshot's node IDS. Without mapping
    # names back to ids, no planned step ever matched its timeline entry:
    # every step of a completed run read "did not run" and its real
    # execution appeared as a duplicate unplanned row (2026-08-12).
    id_by_name = {name: node_id for node_id, name in names.items()}

    def _canonical(key: Any) -> str:
        return id_by_name.get(str(key), str(key))

    node_entries: dict[str, dict[str, Any]] = {}
    file_entries: dict[str, list[dict[str, Any]]] = {}
    for entry in _timeline_steps(progress_timeline):
        node_id = entry.get("node_id")
        if not node_id:
            continue
        if _is_file_entry(entry):
            file_entries.setdefault(_canonical(node_id), []).append(entry)
        elif _is_node_entry(entry):
            # Last entry wins: a retried node writes a second entry and the
            # later one is the outcome that stands.
            node_entries[_canonical(node_id)] = entry

    artifacts_by_step: dict[str, list[Any]] = {}
    unattributed: list[Any] = []
    for artifact in artifacts:
        step_name = getattr(artifact, "step_name", None)
        if step_name:
            artifacts_by_step.setdefault(_canonical(step_name), []).append(artifact)
        else:
            unattributed.append(artifact)

    ordered: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for node in planned_nodes:
        node_id = node.get("node_id") or node.get("id")
        if not node_id or str(node_id) in seen:
            continue
        node_id = str(node_id)
        seen.add(node_id)
        ordered.append(
            (
                node_id,
                str(node.get("node_name") or names.get(node_id) or node_id),
                str(node.get("tool") or "unknown"),
            )
        )
    for node_id in list(node_entries) + list(artifacts_by_step):
        if node_id in seen:
            continue
        seen.add(node_id)
        # Ran (or produced) but was not in the snapshot. Reported, not hidden.
        ordered.append((node_id, names.get(node_id) or node_id, "unknown"))

    steps: list[RunStep] = []
    for node_id, node_name, tool in ordered:
        entry = node_entries.get(node_id)
        status = (
            _step_status_from_timeline(entry.get("status")) if entry else STEP_NOT_RUN
        )
        files = file_entries.get(node_id, [])
        node_artifacts = sorted(artifacts_by_step.get(node_id, []), key=_artifact_sort_key)
        step = RunStep(
            node_id=node_id,
            node_name=node_name,
            tool=tool,
            status=status,
            started_at=entry.get("started_at") if entry else None,
            completed_at=entry.get("completed_at") if entry else None,
            duration_ms=entry.get("duration_ms") if entry else None,
            error=entry.get("error") if entry else None,
            skip_reason=entry.get("skip_reason") if entry else None,
            terminated_by_run=bool(entry.get("terminated_by_run")) if entry else False,
            files_total=len(files),
            files_succeeded=sum(1 for f in files if f.get("status") == "success"),
            files_failed=sum(1 for f in files if f.get("status") in ("error", "failed")),
            artifact_count=len(node_artifacts),
            produced_nothing=status in _TERMINAL_STEP_STATUSES and not node_artifacts,
            artifacts=[
                _artifact_record(a, node_name_map=names, document_names=doc_names)
                for a in node_artifacts
            ],
        )
        steps.append(step)

    if unattributed:
        # Artifacts the run produced that name no step. Real output with
        # incomplete provenance — surfaced under a named pseudo-step so it is
        # visibly unattributed rather than invisibly missing.
        ordered_unattributed = sorted(unattributed, key=_artifact_sort_key)
        steps.append(
            RunStep(
                node_id="",
                node_name="(unattributed)",
                tool="unknown",
                status=STEP_COMPLETED,
                artifact_count=len(ordered_unattributed),
                produced_nothing=False,
                artifacts=[
                    _artifact_record(a, node_name_map=names, document_names=doc_names)
                    for a in ordered_unattributed
                ],
            )
        )

    return steps
