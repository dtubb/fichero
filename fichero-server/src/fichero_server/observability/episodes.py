"""Episode ledger — training-grade provenance for every model call.

Daniel's ratified program (2026-08-11, episode-capture-training-program):
one immutable record per model call (full prompt, raw output, thinking,
model+params, timing, images BY REFERENCE), plus correction and
invalidation records that reference earlier episodes. Four consumers:
live activity animation, fine-tune training exports, correct-and-rerun
staleness, and thesis citations (episode_id is the stable citation key).

Storage: append-only JSONL, one file per month, inside the library
package (`<library>/episodes/YYYY-MM.jsonl`) so provenance travels with
the archive. Records are never edited — corrections and invalidations
are NEW lines that reference old ones. DuckDB reads the files directly
(read_json_auto) for review queues and exports.

Recording is auxiliary: a failure to write is a LOUD log, never a failed
model call — the same contract as activity scoping.

Design: agent-work/reports/episode-ledger-design-2026-08-12.md
"""

from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

#: Library package path episodes append under. Set by the workflow executor
#: (the _vision_activity_db_path pattern); None → recording is a no-op with
#: a debug log, because there is no library to attribute the call to.
_episode_library_path: ContextVar[str | None] = ContextVar(
    "_episode_library_path", default=None
)

#: Workflow-run context (thread_id / workflow_id / node / attempt), set by
#: the executor around tool invocations so the LLM layer needs no plumbing.
_episode_run_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "_episode_run_context", default=None
)

# One lock per process: JSONL appends are single-line writes, but two
# threads interleaving partial lines would corrupt the ledger.
_write_lock = threading.Lock()


def set_library(path: str | None):
    """Point episode recording at a library package. Returns the token for
    ContextVar.reset()."""
    return _episode_library_path.set(path)


def set_run_context(context: dict[str, Any] | None):
    """Attach workflow-run attribution (thread_id, workflow_id, node,
    attempt). Returns the token for ContextVar.reset()."""
    return _episode_run_context.set(context)


def _ledger_file(library_path: str, now: datetime) -> Path:
    folder = Path(library_path) / "episodes"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{now:%Y-%m}.jsonl"


def _append(library_path: str, record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, default=str)
    path = _ledger_file(library_path, datetime.now(timezone.utc))
    with _write_lock, open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def record(
    *,
    kind: str = "model_call",
    subject: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    exchange: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> str | None:
    """Append one episode. Returns the episode_id, or None when recording
    was impossible (no library in context, or the write failed) — callers
    never branch on it; it exists so tests and correction records can
    reference the id."""
    library_path = _episode_library_path.get()
    if not library_path:
        logger.debug("episode not recorded: no library in context")
        return None

    episode_id = f"ep_{uuid4().hex}"
    payload: dict[str, Any] = {
        "episode_id": episode_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "run": _episode_run_context.get(),
        "subject": subject or {},
        "model": model or {},
        "exchange": exchange or {},
        "timing": timing or {},
        "cost": cost or {},
    }
    if extra:
        payload.update(extra)
    try:
        _append(library_path, payload)
    except OSError as exc:
        # Loud, but never fails the model call — provenance is auxiliary.
        logger.error("episode ledger write failed at %s: %s", library_path, exc)
        return None
    return episode_id


def read_for_thread(
    library_path: str, thread_id: str, *, limit: int = 500
) -> list[dict[str, Any]]:
    """Episodes recorded under a workflow run, newest file first, in
    write order within each file. The per-node inspection surface: each
    record carries the node, the full exchange (prompt/output/thinking),
    model identity, and subject — the "investigate each node" view and the
    thesis citation resolver read exactly this."""
    folder = Path(library_path) / "episodes"
    if not folder.is_dir():
        return []
    matches: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.error("episode ledger read failed at %s: %s", path, exc)
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                logger.error("episode ledger has a corrupt line in %s", path)
                continue
            run = record.get("run") or {}
            if run.get("thread_id") == thread_id:
                matches.append(record)
                if len(matches) >= limit:
                    return matches
    return matches


def export_training_pairs(
    library_path: str, *, use_case: str | None = None, gold_only: bool = False
) -> list[dict[str, Any]]:
    """Chat-format training samples from the ledger (the MLX loop's export).

    One sample per model_call episode: system+user messages from the
    recorded exchange, assistant = the HUMAN CORRECTION when one exists
    (gold), otherwise the model output (accepted). Corrected samples also
    carry `rejected` (the model's original output) so a DPO exporter can
    pair chosen/rejected without re-reading the ledger. `use_case` filters
    per workflow step (Daniel's per-step small models); `gold_only` keeps
    only human-corrected pairs.
    """
    folder = Path(library_path) / "episodes"
    if not folder.is_dir():
        return []
    calls: dict[str, dict[str, Any]] = {}
    corrections: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.error("episode ledger read failed at %s: %s", path, exc)
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                logger.error("episode ledger has a corrupt line in %s", path)
                continue
            if rec.get("kind") == "model_call":
                calls[rec.get("episode_id", "")] = rec
            elif rec.get("kind") == "correction":
                target = rec.get("corrects_episode_id")
                if target:
                    corrections[target] = rec

    samples: list[dict[str, Any]] = []
    for episode_id, rec in calls.items():
        exchange = rec.get("exchange") or {}
        prompt = exchange.get("prompt")
        output = exchange.get("output")
        if not prompt or output is None:
            continue
        model = rec.get("model") or {}
        if use_case and model.get("use_case") != use_case:
            continue
        correction = corrections.get(episode_id)
        if gold_only and correction is None:
            continue
        assistant = (
            (correction.get("exchange") or {}).get("corrected_text")
            if correction
            else output
        )
        messages: list[dict[str, str]] = []
        if exchange.get("system"):
            messages.append({"role": "system", "content": exchange["system"]})
        messages.append({"role": "user", "content": prompt})
        messages.append({"role": "assistant", "content": assistant or ""})
        sample: dict[str, Any] = {
            "messages": messages,
            "episode_id": episode_id,
            "use_case": model.get("use_case"),
            "gold": correction is not None,
            "subject": rec.get("subject") or {},
        }
        if correction is not None:
            sample["rejected"] = output
        samples.append(sample)
    return samples


def record_correction(
    *,
    corrects_episode_id: str | None,
    artifact_id: str,
    corrected_text: str,
    actor: str | None = None,
) -> str | None:
    """A human replaced a model output. This IS the gold training pair:
    the export reads the corrected episode's prompt, chosen = the human
    text, rejected = the model output."""
    return record(
        kind="correction",
        subject={"artifact_id": artifact_id},
        exchange={"corrected_text": corrected_text},
        extra={
            "corrects_episode_id": corrects_episode_id,
            "actor": actor,
        },
    )


def record_invalidation(
    *, stale_artifact_ids: list[str], caused_by_episode_id: str | None
) -> str | None:
    """Downstream outputs superseded by a correction or re-run. The batch
    'rerun stale' queue reads these."""
    return record(
        kind="invalidation",
        subject={"stale_artifact_ids": stale_artifact_ids},
        extra={"caused_by_episode_id": caused_by_episode_id},
    )
