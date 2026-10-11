"""Copy within one engine: write the plan into the target, verify it, keep the record (#5657, build order 3).

Two DuckDB files share no transaction, so the order is the safety (spec, "No cross-file transaction"):

1. the target's record is written ``writing`` BEFORE any row (the journal);
2. in-package originals are copied under the target's ``files/`` and checked by sha256;
3. every planned row is written in ONE target transaction, then read back inside it: per-kind counts,
   and every id a written row names must resolve (``verified``);
4. any failure rolls the transaction back, removes the files it copied, and leaves the record
   ``rolled_back`` with the reason; the source is never written on a failure;
5. on success the record is ``done`` in the target and a ``done`` record is written in the source.

A move (build order 4) is this copy, then the source's verified soft delete with "moved to", then
compensation if that delete fails: `copy_into_target` returns before anything touches the source's
items, so a move adds its step after it and calls `roll_back_target` when that step fails.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel

from fichero_server.core.timeutil import utc_now
from fichero_server.models.transfer import (
    TransferCount,
    TransferMode,
    TransferRecord,
    TransferResult,
    TransferRole,
    TransferState,
)
from fichero_server.transfer.id_map_classification import CLASSIFICATION, MAPPED
from fichero_server.transfer.membership import EXTERNAL_ENDS
from fichero_server.transfer.plan import TransferPlan

logger = logging.getLogger(__name__)


class TransferFailed(RuntimeError):
    """The copy did not finish; the target was rolled back and the source is unchanged."""

    def __init__(self, message: str, result: TransferResult) -> None:
        super().__init__(message)
        self.result = result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _save_row(db, row: BaseModel) -> None:
    """One row into the target. A seam: the half-done test fails here on purpose."""
    db.save(row)


def result_of(plan: TransferPlan, *, mode: TransferMode, dry_run: bool, state: TransferState, actor: str,
              source: str, target: str, written: dict[str, int] | None = None, error: str | None = None) -> TransferResult:
    counts = plan.counts()
    if written is not None:
        counts = [TransferCount(kind=c.kind, planned=c.planned, written=written.get(c.kind, 0)) for c in counts]
    return TransferResult(
        transfer_id=plan.transfer_id, mode=mode, dry_run=dry_run, state=state, source=source, target=target,
        target_parent_id=plan.target_parent_id, actor=actor, counts=counts,
        files=len(plan.files), bytes=sum(f.size for f in plan.files), linked_files=list(plan.linked_files),
        vocabulary=list(plan.vocabulary), proposals=plan.proposals(), entities_new=plan.entities_new,
        cuts=list(plan.cuts), left_behind=list(plan.left_behind),
        copies=[] if dry_run else plan.copies, error=error,
    )


def _mapped_values(row: BaseModel, key_prefix: str | None = None):
    """Every (key, id) a built row holds in a MAPPED scalar or list field, nested models included."""
    cls_name = type(row).__name__
    for name in type(row).model_fields:
        key = f"{cls_name}.{name}"
        value = getattr(row, name)
        if CLASSIFICATION.get(key, ("",))[0] == MAPPED and key not in EXTERNAL_ENDS and name != "id":
            if isinstance(value, str):
                yield key, value
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                for v in value:
                    yield key, v
        elif key in EXTERNAL_ENDS:
            kind_field, external = EXTERNAL_ENDS[key]
            if getattr(row, kind_field) != external:
                yield key, value
        if isinstance(value, BaseModel):
            yield from _mapped_values(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, BaseModel):
                    yield from _mapped_values(item)


#: MAPPED fields whose value is not a row id (dicts of ids handled deep, the page id that IS its row's id).
_NOT_A_ROW_ID = {"PageLineMap.id"}


def _verify(target_db, plan: TransferPlan) -> dict[str, int]:
    """Read back what was written, inside the write's transaction (`transfer.action.verify-then-delete`)."""
    written: dict[str, int] = {}
    by_kind: dict[str, list[str]] = {}
    for kind, row in plan.built:
        by_kind.setdefault(kind, []).append(row.id)
    for kind, ids in by_kind.items():
        found = target_db.query_in(plan.models[kind], "id", ids)
        written[kind] = len(found)
        if len(found) != len(ids):
            raise RuntimeError(f"{kind}: {len(ids)} planned, {len(found)} read back")
    resolvable = {row.id for _kind, row in plan.built} | {plan.target_parent_id} | {
        m.id for m in plan.vocabulary_to_make}
    for kind, row in plan.built:
        for key, value in _mapped_values(row):
            if key in _NOT_A_ROW_ID or not value or value in resolvable:
                continue
            raise RuntimeError(f"{kind} {row.id}: {key} names {value}, which is not in the target")
    for planned in plan.files:
        copied = plan.target_package / planned.relative
        if not copied.is_file() or _sha256(copied) != _sha256(planned.source_path):
            raise RuntimeError(f"file of {planned.document}: the copy's sha256 differs from the source's")
    return written


def _remove_files(paths: list[str]) -> None:
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - reported, never swallowed silently
            logger.warning("transfer roll-back could not remove %s: %s", path, exc)


def roll_back_target(target_db, record: TransferRecord, reason: str) -> None:
    """Remove what a transfer wrote in the target that a transaction cannot (its files); record why.

    The rows were written in one target transaction, so a failure before its commit leaves none.
    A move's compensation after a committed copy (build order 4) removes the rows by the id map first."""
    _remove_files(record.files_written)
    record.state = TransferState.rolled_back
    record.error = reason
    record.updated_at = utc_now()
    target_db.save(record)


def copy_into_target(source_db, target_db, plan: TransferPlan, *, mode: TransferMode, actor: str) -> TransferResult:
    """Write the plan into the target, verify, and record it in both projects. Raises `TransferFailed`."""
    from fichero_server.models.knowledge import EntityMatchCandidate, PendingMatchMethod

    source_name, target_name = plan.source_package.stem, plan.target_package.stem
    record = TransferRecord(
        id=plan.transfer_id, role=TransferRole.target, state=TransferState.writing, mode=mode,
        source_project=str(plan.source_package), target_project=str(plan.target_package),
        items=list(plan.items), copies=plan.copies, id_map=dict(plan.id_map),
        source_audits=dict(plan.source_audits), created_by=actor,
    )
    target_db.save(record)  # the journal: committed before any row

    try:
        for planned in plan.files:
            destination = plan.target_package / planned.relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(planned.source_path, destination)
            record.files_written.append(str(destination))
        proposals: list[EntityMatchCandidate] = [
            EntityMatchCandidate(
                survivor_entity_id=match.target_entity, candidate_entity_id=plan.id_map[match.carried],
                score=1.0, method=PendingMatchMethod.transfer,
                reason=f"carried from {source_name}: {match.reason}",
            )
            for match in plan.matches
        ]
        with target_db.transaction():
            for made in plan.vocabulary_to_make:
                _save_row(target_db, made)
            for _kind, row in plan.built:
                _save_row(target_db, row)
            for proposal in proposals:
                _save_row(target_db, proposal)
            written = _verify(target_db, plan)
            record.proposals = [p.id for p in proposals]
            record.state = TransferState.verified
            record.updated_at = utc_now()
            target_db.save(record)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        roll_back_target(target_db, record, reason)
        result = result_of(plan, mode=mode, dry_run=False, state=TransferState.rolled_back, actor=actor,
                           source=source_name, target=target_name, error=reason)
        record.result = result.model_dump(mode="json")
        target_db.save(record)
        raise TransferFailed(
            f"The copy to {target_name} did not finish and was rolled back: nothing it wrote is left there "
            f"and {source_name} is unchanged. ({reason})", result) from exc

    proposal_ids = dict(zip((m.carried for m in plan.matches), record.proposals))
    result = result_of(plan, mode=mode, dry_run=False, state=TransferState.done, actor=actor,
                       source=source_name, target=target_name, written=written)
    for proposal in result.proposals:
        proposal.proposal = proposal_ids.get(proposal.carried_entity)
    record.state = TransferState.done
    record.result = result.model_dump(mode="json")
    record.updated_at = utc_now()
    target_db.save(record)
    # The source's record of the same transfer (`transfer.action.record-in-both`): items, mode, target.
    source_db.save(TransferRecord(
        id=plan.transfer_id, role=TransferRole.source, state=TransferState.done, mode=mode,
        source_project=str(plan.source_package), target_project=str(plan.target_package),
        items=list(plan.items), created_by=actor, result={"copies": plan.copies, "target": target_name},
    ))
    return result


def undo_copy(target_db, source_db, transfer_id: str, *, actor: str, trash) -> list[str]:
    """Undo a copy: the copies go to the target's Trash and the merges it proposed are withdrawn
    (`transfer.action.undo-copy`). `trash(db, doc_id, actor=...)` is the one soft delete
    (`document.delete`'s impl). Returns every node id trashed. The source keeps its record, marked undone."""
    from fichero_server.models import Document
    from fichero_server.models.knowledge import EntityMatchCandidate, PendingMatchState

    record = target_db.get(TransferRecord, transfer_id)
    if record is None or record.role != TransferRole.target:
        raise LookupError(f"No transfer {transfer_id} landed in this project.")
    if record.state != TransferState.done:
        raise ValueError(f"The transfer {transfer_id} is {record.state.value}; only a finished copy can be undone.")
    trashed: list[str] = []
    for copy_id in record.copies:
        node = target_db.get(Document, copy_id)
        if node is None or node.deleted_at is not None:
            continue
        ids, _snapshots = trash(target_db, copy_id, actor=actor)
        trashed.extend(ids)
    for proposal_id in record.proposals:
        proposal = target_db.get(EntityMatchCandidate, proposal_id)
        if proposal is not None and proposal.state == PendingMatchState.pending:
            proposal.state = PendingMatchState.withdrawn
            proposal.decided_by = actor
            proposal.decided_at = utc_now()
            target_db.save(proposal)
    record.state = TransferState.undone
    record.updated_at = utc_now()
    target_db.save(record)
    if source_db is not None:
        mirror = source_db.get(TransferRecord, transfer_id)
        if mirror is not None:
            mirror.state = TransferState.undone
            mirror.updated_at = utc_now()
            source_db.save(mirror)
    return trashed
