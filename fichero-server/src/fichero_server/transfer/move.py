"""Move within one engine (#5657, build order 4): the copy, then the source's verified soft delete.

Order is the safety (spec, "No cross-file transaction"):

1. the source's mirror record is written ``sending`` before the target is touched;
2. the copy (`copy.copy_into_target(finish=False)`) writes and verifies the target and stops at
   ``verified``; the mirror becomes ``verified``;
3. the source step, one audited action in the source (`document.transfer_out`): each item goes to the
   source's Trash through `document.delete` with ``moved_to`` (the Trash says "moved to <project>"),
   and what must be cut there is cut and kept on the record (canvas positions and link items, workspace
   slots, aliases to moved items, synced-folder ties); the mirror becomes ``done``;
4. the target's record becomes ``done``.

If step 3 fails it is tried once more; if it fails again the target's committed copy is removed by the
record's `written` rows and the move is reported as not done, in words. A move never ends as a silent
copy. A crash between 2 and 4 is finished when both projects are open again (`resume_pending_moves`).
Undo works from either project (`undo_move`): the source's items come back from its Trash with every
cut edge, and the target's copy goes to the target's Trash.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.models.transfer import (
    TransferCut,
    TransferMode,
    TransferRecord,
    TransferResult,
    TransferRole,
    TransferState,
)
from fichero_server.transfer.copy import (
    TransferFailed,
    copy_into_target,
    remove_target_rows,
    roll_back_target,
    undo_copy,
)
from fichero_server.transfer.plan import TransferPlan

logger = logging.getLogger(__name__)

PENDING = (TransferState.sending, TransferState.verified)
#: The source step is tried this many times before the copy is taken back (`transfer.action.compensates`).
SOURCE_STEP_ATTEMPTS = 2


def _name(path: str | Path) -> str:
    return Path(path).stem


def _source_context(source_db, actor: str, *, bootstrap: bool, client: str | None = None):
    from fichero_server.actions.registry import ActionContext

    return ActionContext(actor=actor, client=client, library_path=str(Path(source_db.path).parent),
                         is_bootstrap=bootstrap)


# ---------------------------------------------------------------------------------------------
# A second drag while a move is pending (`transfer.action.second-drag-refused`)
# ---------------------------------------------------------------------------------------------


def _ancestors(db, doc_id: str) -> list[str]:
    from fichero_server.models import Document

    chain, current, guard = [], doc_id, 0
    while current and guard < 10_000:
        chain.append(current)
        row = db.get(Document, current)
        current = row.parent_id if row is not None else None
        guard += 1
    return chain


def pending_refusal(source_db, items: list[str], target_db, target_parent_id: str | None) -> str | None:
    """The words refusing a transfer of an item a pending move holds (the item, a folder holding it, or a
    drop into it), read from the source's mirror rows alone; None when nothing is pending."""
    for record in source_db.query(TransferRecord, role=TransferRole.source, mode=TransferMode.move):
        if record.state not in PENDING:
            continue
        held = set(record.items)
        for item in items:
            if held & set(_ancestors(source_db, item)) or any(item in _ancestors(source_db, h) for h in held):
                return f"These items are already being moved to {_name(record.target_project)}."
    if target_parent_id:
        for record in target_db.query(TransferRecord, role=TransferRole.source, mode=TransferMode.move):
            if record.state in PENDING and set(record.items) & set(_ancestors(target_db, target_parent_id)):
                return f"That folder is already being moved to {_name(record.target_project)}."
    return None


# ---------------------------------------------------------------------------------------------
# The source step: to the Trash with "moved to", and the cuts (`transfer.cut.*`)
# ---------------------------------------------------------------------------------------------


def _live_subtree(db, items: list[str]) -> set[str]:
    from fichero_server.models import Document

    found: set[str] = set()
    stack = list(items)
    while stack:
        doc_id = stack.pop()
        if doc_id in found:
            continue
        found.add(doc_id)
        stack.extend(child.id for child in db.query(Document, parent_id=doc_id) if child.deleted_at is None)
    return found


def _cut(kind: str, row: str, field: str, points_to: str, name: str | None, reason: str, whole: bool = True) -> dict:
    return TransferCut(kind=kind, row=row, field=field, points_to=points_to, name=name, whole_row=whole,
                       reason=reason).model_dump(mode="json")


def cut_in_source(db, moved: set[str], *, source: str, target: str, transfer_id: str, ctx) -> tuple[list[dict], list[str]]:
    """Cut what cannot follow the moved items, keeping each as it was (for undo) with the listed cut.
    Returns ``(source_cuts, aliases_trashed)``."""
    from fichero_server import sync_folder
    from fichero_server.actions.registry import registry
    from fichero_server.models import Document
    from fichero_server.models.canvas import CanvasItem, CanvasItemKind, CanvasLayout

    cuts: list[dict] = []
    ids = sorted(moved)
    # The moved items' places on a canvas that stays (`transfer.cut.canvas-position`).
    for layout in db.query_in(CanvasLayout, "item_id", ids):
        if layout.folder_id not in moved:
            db.delete(layout)
            cuts.append({"model": "CanvasLayout", "row": layout.model_dump(mode="json"),
                         "cut": _cut("CanvasLayout", layout.id, "item_id", layout.item_id, None,
                                     f"its place on a canvas in {source}; the item moved to {target}")})
    # A canvas link item with one end moved and the other staying (`transfer.cut.canvas-links`).
    links = {item.id: item for field in ("source_item_id", "target_item_id") for item in db.query_in(CanvasItem, field, ids)}
    for item in links.values():
        if item.kind == CanvasItemKind.link and item.folder_id not in moved:
            end = item.source_item_id if item.source_item_id in moved else item.target_item_id
            db.delete(item)
            cuts.append({"model": "CanvasItem", "row": item.model_dump(mode="json"),
                         "cut": _cut("CanvasItem", item.id, "source_item_id" if end == item.source_item_id else "target_item_id",
                                     end, item.text or None, f"a canvas link in {source} to an item moved to {target}")})
    # A workspace's slot naming a moved item: the workspace stays, the slot goes (`transfer.cut.workspace-slot`).
    for workspace in db.query(Document, is_workspace=True):
        if workspace.id in moved or workspace.deleted_at is not None:
            continue
        slots = list(workspace.curated_items or [])
        kept = [slot for slot in slots if not (isinstance(slot, dict) and slot.get("target_id") in moved)]
        if len(kept) == len(slots):
            continue
        for slot in slots:
            if slot not in kept:
                cuts.append({"model": "workspace", "row": None,
                             "cut": _cut("Document", workspace.id, "curated_items", str(slot.get("target_id")), workspace.name,
                                         f"a slot of the workspace {workspace.name}; the item moved to {target}", whole=False)})
        cuts[-1]["row"] = {"document": workspace.id, "curated_items": slots}
        workspace.curated_items = kept
        workspace.updated_at = utc_now()
        db.save(workspace)
    # An alias outside the set pointing at a moved item goes to the Trash with the move (`transfer.alias.source-aliases`).
    aliases: list[str] = []
    for alias in db.query_in(Document, "alias_target_id", ids):
        if alias.id in moved or alias.deleted_at is not None or alias.node_kind != "alias":
            continue
        done = registry.invoke(db, "document.delete",
                               {"doc_id": alias.id, "moved_to": {"project": target, "transfer_id": transfer_id}}, ctx)
        aliases.extend(done.result["deleted_document_ids"])
        cuts.append({"model": "alias", "row": None,
                     "cut": _cut("Document", alias.id, "alias_target_id", alias.alias_target_id, alias.name,
                                 f"alias to {alias.alias_target_id}, moved to {target}: in {source}'s Trash")})
    # A moved document's tie to a synced folder: severed, its file left as it is (`transfer.cut.sync-folder-tie`).
    for tie in sync_folder.sever(db, ids):
        cuts.append({"model": "sync_files", "row": tie,
                     "cut": _cut("sync_files", tie["document_id"], "folder_id", tie["folder_id"], tie["rel_path"],
                                 f"no longer synced to its folder in {source}; the file stays on disk", whole=False)})
    return cuts, aliases


def put_back_cuts(db, cuts: list[dict]) -> None:
    """Undo of a move: every edge the source step cut, as it was."""
    from fichero_server import sync_folder
    from fichero_server.models import Document
    from fichero_server.models.canvas import CanvasItem, CanvasLayout

    ties = []
    for cut in cuts:
        model, row = cut["model"], cut["row"]
        if model == "CanvasLayout":
            db.save(CanvasLayout.model_validate(row))
        elif model == "CanvasItem":
            db.save(CanvasItem.model_validate(row))
        elif model == "workspace" and row:
            workspace = db.get(Document, row["document"])
            if workspace is not None:
                workspace.curated_items = row["curated_items"]
                db.save(workspace)
        elif model == "sync_files":
            ties.append(row)
    sync_folder.retie(db, ties)
    # Aliases were sent to the Trash with the items; they come back with them (`record.trashed`).


def source_step(source_db, transfer_id: str, ctx) -> dict:
    """The move's source step, as one audited action in the source (`document.transfer_out`). A seam:
    the compensation test fails here on purpose."""
    from fichero_server.actions.registry import registry

    return registry.invoke(source_db, "document.transfer_out", {"transfer_id": transfer_id}, ctx).result


def run_source_step(source_db, transfer_id: str, ctx) -> tuple[list[str], list[dict]]:
    """The body of `document.transfer_out`: in the source's transaction, items to the Trash with
    "moved to", cuts made and kept, the mirror ``done``. Returns ``(trashed, source_cuts)``."""
    from fichero_server.actions.registry import ActionRefused, registry

    mirror = source_db.get(TransferRecord, transfer_id)
    if mirror is None or mirror.role != TransferRole.source or mirror.mode != TransferMode.move:
        raise ActionRefused(f"No move {transfer_id} was sent from this project.")
    if mirror.state != TransferState.verified:
        raise ActionRefused(f"The move {transfer_id} is {mirror.state.value}: its copy is not checked, so nothing here is removed.")
    source, target = _name(mirror.source_project), _name(mirror.target_project)
    moved = _live_subtree(source_db, mirror.items)
    trashed: list[str] = []
    for item in mirror.items:
        done = registry.invoke(source_db, "document.delete",
                               {"doc_id": item, "moved_to": {"project": target, "transfer_id": transfer_id}}, ctx)
        trashed.extend(done.result["deleted_document_ids"])
    cuts, aliases = cut_in_source(source_db, moved, source=source, target=target, transfer_id=transfer_id, ctx=ctx)
    mirror.trashed = [*trashed, *aliases]
    mirror.source_cuts = cuts
    mirror.state = TransferState.done
    mirror.updated_at = utc_now()
    source_db.save(mirror)
    return mirror.trashed, cuts


# ---------------------------------------------------------------------------------------------
# The move
# ---------------------------------------------------------------------------------------------


def move_between(source_db, target_db, plan: TransferPlan, *, actor: str, bootstrap: bool,
                 client: str | None = None) -> TransferResult:
    """Copy, verify, then send the source's items to its Trash; never a silent copy. Raises `TransferFailed`."""
    mirror = TransferRecord(
        id=plan.transfer_id, role=TransferRole.source, state=TransferState.sending, mode=TransferMode.move,
        source_project=str(plan.source_package), target_project=str(plan.target_package),
        items=list(plan.items), created_by=actor,
    )
    source_db.save(mirror)  # the mirror journal: the pending move is visible in the source from here
    try:
        copy_into_target(source_db, target_db, plan, mode=TransferMode.move, actor=actor, finish=False)
    except TransferFailed as failed:
        mirror.state, mirror.error, mirror.updated_at = TransferState.rolled_back, failed.result.error, utc_now()
        source_db.save(mirror)
        raise
    mirror.state, mirror.updated_at = TransferState.verified, utc_now()
    source_db.save(mirror)
    return finish_move(source_db, target_db, plan.transfer_id, ctx=_source_context(source_db, actor, bootstrap=bootstrap, client=client))


def finish_move(source_db, target_db, transfer_id: str, *, ctx) -> TransferResult:
    """Steps 3 and 4: the source step (tried twice), then the target's record ``done``; on failure the
    target's copy is removed and the move reported as not done."""
    record = target_db.get(TransferRecord, transfer_id)
    source, target = _name(record.source_project), _name(record.target_project)
    mirror = source_db.get(TransferRecord, transfer_id)
    if mirror.state != TransferState.done:
        failure: Exception | None = None
        for _attempt in range(SOURCE_STEP_ATTEMPTS):
            try:
                source_step(source_db, transfer_id, ctx)
                failure = None
                break
            except Exception as exc:  # noqa: BLE001 -- every failure compensates, named in the result
                failure = exc
                logger.warning("move %s: the source step failed (%s)", transfer_id, exc)
        if failure is not None:
            reason = f"{type(failure).__name__}: {failure}"
            remove_target_rows(target_db, record)
            roll_back_target(target_db, record, f"the source step failed twice: {reason}")
            mirror = source_db.get(TransferRecord, transfer_id)
            mirror.state, mirror.error, mirror.updated_at = TransferState.rolled_back, reason, utc_now()
            source_db.save(mirror)
            result = TransferResult.model_validate({**(record.result or {}), "state": "rolled_back", "copies": [],
                                                    "audit": None, "error": reason})
            record.result = result.model_dump(mode="json")
            target_db.save(record)
            raise TransferFailed(
                f"The move to {target} was not done: {source}'s items could not be sent to its Trash ({reason}). "
                f"The copy in {target} was taken back; {source} is unchanged.", result) from failure
        mirror = source_db.get(TransferRecord, transfer_id)
    result = TransferResult.model_validate(record.result)
    result.state = TransferState.done
    result.cuts = [*result.cuts, *(TransferCut.model_validate(c["cut"]) for c in mirror.source_cuts)]
    record.state, record.result, record.updated_at = TransferState.done, result.model_dump(mode="json"), utc_now()
    target_db.save(record)
    return result


def resume_pending_moves(db) -> list[str]:
    """On opening a project: finish a move a crash left between its checked copy and its source step,
    when the other project is open too; else it waits, and says so in the log (`transfer.action.journal-recovers`)."""
    from fichero_server.db.manager import db_manager

    touched: list[str] = []
    for record in db.query(TransferRecord, mode=TransferMode.move):
        if record.state not in PENDING:
            continue
        other = record.source_project if record.role == TransferRole.target else record.target_project
        if not db_manager.is_open(other):
            logger.info("move %s waits for %s to be open to finish", record.id, _name(other))
            continue
        other_db = db_manager.get_database(other)
        source_db, target_db = (other_db, db) if record.role == TransferRole.target else (db, other_db)
        landed = target_db.get(TransferRecord, record.id)
        mirror = source_db.get(TransferRecord, record.id)
        if landed is None or landed.state in (TransferState.writing, TransferState.rolled_back):
            if mirror is not None and mirror.state in PENDING:
                mirror.state, mirror.updated_at = TransferState.rolled_back, utc_now()
                mirror.error = "the copy never finished in the target; nothing here was removed"
                source_db.save(mirror)
                touched.append(record.id)
            continue
        if landed.state == TransferState.verified and mirror is not None:
            if mirror.state == TransferState.sending:
                mirror.state = TransferState.verified  # the copy finished; the crash came before the mirror caught up
                source_db.save(mirror)
            try:
                finish_move(source_db, target_db, record.id,
                            ctx=_source_context(source_db, landed.created_by or "system", bootstrap=True))
            except TransferFailed as failed:
                logger.warning("move %s could not be finished on open: %s", record.id, failed)
            touched.append(record.id)
    return touched


# ---------------------------------------------------------------------------------------------
# Undo of a move, from either project (`transfer.action.undo-move`)
# ---------------------------------------------------------------------------------------------


def undo_move(db, transfer_id: str, *, actor: str, trash, restore) -> dict[str, Any]:
    """Put the source's items back from its Trash with every cut edge, and send the target's copy to
    its Trash. `trash` is `document.delete`'s impl and `restore` `document.restore`'s. Refused in words
    when the other project is not open, when the move is not finished or already undone, and when the
    source's items were emptied from its Trash since (the move is then permanent)."""
    from fichero_server.actions.registry import ActionRefused
    from fichero_server.db.manager import db_manager
    from fichero_server.models import Document

    record = db.get(TransferRecord, transfer_id)
    other = record.source_project if record.role == TransferRole.target else record.target_project
    if not db_manager.is_open(other):
        raise ActionRefused(f"Open {_name(other)} to undo this move: it changed both projects.")
    other_db = db_manager.get_database(other)
    source_db, target_db = (other_db, db) if record.role == TransferRole.target else (db, other_db)
    landed, mirror = target_db.get(TransferRecord, transfer_id), source_db.get(TransferRecord, transfer_id)
    source = _name(record.source_project)
    if TransferState.undone in (landed.state, mirror.state):
        raise ActionRefused("This move was already undone.")
    if landed.state != TransferState.done or mirror.state != TransferState.done:
        raise ActionRefused(f"This move is {landed.state.value}: only a finished move can be undone.")
    if any(source_db.get(Document, item) is None for item in mirror.trashed):
        raise ActionRefused(f"The moved items were emptied from {source}'s Trash: the move is permanent and cannot be undone.")
    with source_db.transaction():
        restored = restore(source_db, doc_ids=list(mirror.trashed))
        put_back_cuts(source_db, mirror.source_cuts)
        mirror.state, mirror.updated_at = TransferState.undone, utc_now()
        source_db.save(mirror)
    with target_db.transaction():
        trashed = undo_copy(target_db, None, transfer_id, actor=actor, trash=trash)
    return {"restored": restored, "trashed": trashed, "source_db": source_db, "target_db": target_db}
