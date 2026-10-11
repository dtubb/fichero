"""`POST /api/documents/transfer` — copy a selection into another open project, or plan it (#5657).

Spec: `docs/contributor_manual/specs/source/moving-between-projects.md`. The library header names the
TARGET project; the body names the SOURCE. Every surface (the app's drop, the CLI, MCP) calls this one
route, which runs one audited action, `document.transfer`, in the target; its inverse,
`document.untransfer`, sends the copies to the target's Trash. A dry run writes nothing and returns the
same report a copy would.

Built: plan (`dry_run`), copy and move within one engine (a move's source step is its own audited action
in the source, `document.transfer_out`). Not built: a background job for large transfers, between machines.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.actions.registry import (
    ActionContext,
    ActionRefused,
    ChangeSpec,
    action,
    registry,
)
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.models.transfer import (
    TransferMode,
    TransferRequest,
    TransferResult,
    TransferState,
)
from fichero_server.security import authz
from fichero_server.transfer import copy as transfer_copy
from fichero_server.transfer.plan import build_plan

router = APIRouter()

ALIASES_STAY = "Aliases stay within a project."


def _new_id() -> str:
    return uuid.uuid4().hex


def _source_database(source: str, target_db: Database) -> Database:
    """The source project's open database, refused in words when it is not open or is the target."""
    from fichero_server.db.manager import db_manager

    name = Path(source).stem or source
    if not db_manager.is_open(source):
        raise HTTPException(status_code=409, detail=f"{name} is not open. Open it in Fichero, then transfer again.")
    source_db = db_manager.get_database(source)
    if source_db is target_db:
        raise HTTPException(
            status_code=400,
            detail=f"{name} is both the source and the target. Within one project, drag to move or ⌥-drag to duplicate.",
        )
    return source_db


def _check_items(source_db: Database, items: list[str], source_name: str, mode: TransferMode,
                 ctx: ActionContext, target_db: Database, target_parent_id: str | None) -> None:
    from fichero_server.api.routes.document.documents import (
        _reject_if_document_read_only,
    )
    from fichero_server.transfer.move import pending_refusal

    for item in items:
        doc = source_db.get(Document, item)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"There is no item {item} in {source_name}.")
        if doc.deleted_at is not None:
            raise HTTPException(status_code=409, detail=f"{doc.name} is in {source_name}'s Trash; put it back first.")
        if doc.node_kind == "alias":
            raise HTTPException(status_code=409, detail=f"{ALIASES_STAY} {doc.name} is an alias; copy its original instead.")
        _reject_if_document_read_only(doc, "transferred")
        if mode == TransferMode.move and not ctx.is_bootstrap:
            # A move removes the items from the source: the person must be able to write there too.
            authz.assert_can_write(ctx.actor, str(Path(source_db.path).parent), item)
    refusal = pending_refusal(source_db, items, target_db, target_parent_id)
    if refusal:
        raise HTTPException(status_code=409, detail=refusal)

def _target_parent(target_db: Database, parent_id: str | None) -> str:
    """The folder the items land in; "" when none is named and the target has no Sources folder yet."""
    target_name = Path(target_db.path).parent.stem
    if parent_id is None:
        from fichero_server.importers.sources_folder import find_sources_folder

        found = find_sources_folder(target_db)
        return found.id if found is not None else ""
    parent = target_db.get(Document, parent_id)
    if parent is None or parent.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"There is no folder {parent_id} in {target_name}.")
    if parent.doc_type != DocType.folder or parent.node_kind == "alias":
        raise HTTPException(status_code=400, detail=f"{parent.name} is not a folder: items can only be dropped into a folder.")
    if isinstance(parent.attributes, dict) and parent.attributes.get("read_only"):
        raise HTTPException(status_code=403, detail=f"{parent.name} is read-only: nothing can be added to it.")
    return parent.id


def _check_can_read(ctx: ActionContext, source: str, items: list[str]) -> None:
    if ctx.is_bootstrap:
        return
    for item in items:
        authz.assert_can_read(ctx.actor, source, item)


class DocumentTransferParams(BaseModel):
    """`document.transfer`'s params: the request minus `dry_run` (a dry run is not an action)."""

    items: list[str]
    source: str
    target_parent_id: str | None = None
    mode: TransferMode = TransferMode.copy


class DocumentUntransferParams(BaseModel):
    transfer_id: str


def _invert_transfer(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    if not after or not after.get("transfer_id"):
        return None
    return ("document.untransfer", {"transfer_id": after["transfer_id"]})


def _emit(ctx: ActionContext, spec: ChangeSpec) -> None:
    from fichero_server.api.routes.document.documents import _emit_document_change_spec

    _emit_document_change_spec(ctx, spec)


@action(
    "document.transfer",
    DocumentTransferParams,
    domains=["document"],
    undoable=True,
    invert=_invert_transfer,
    atomic=False,  # two databases: the copy owns its journal, its target transaction and its roll-back
)
def _action_transfer(db: Database, params: DocumentTransferParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    source_db = _source_database(params.source, db)
    source_name = Path(source_db.path).parent.stem
    _check_items(source_db, params.items, source_name, params.mode, ctx, db, params.target_parent_id)
    target_parent_id = _target_parent(db, params.target_parent_id)
    sources_folder = None
    if not target_parent_id:
        # The target has no Sources folder: made with the copy, in its transaction, so a failure leaves none.
        from fichero_server.importers.sources_folder import SOURCES_FOLDER_NAME
        from fichero_server.models import Status

        sources_folder = Document(name=SOURCES_FOLDER_NAME, doc_type=DocType.folder, status=Status.completed)
        target_parent_id = sources_folder.id
    audit_id = _new_id()
    plan = build_plan(source_db, db, items=params.items, target_parent_id=target_parent_id,
                      transfer_id=_new_id(), audit_id=audit_id, actor=ctx.actor)
    plan.parent_to_make = sources_folder
    if params.mode == TransferMode.move:
        from fichero_server.transfer.move import move_between

        result = move_between(source_db, db, plan, actor=ctx.actor, bootstrap=ctx.is_bootstrap, client=ctx.client)
    else:
        result = transfer_copy.copy_into_target(source_db, db, plan, mode=params.mode, actor=ctx.actor)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=list(result.copies),
        after={"transfer_id": result.transfer_id, "copies": list(result.copies)},
        audit_id=audit_id,
        emit_type="document.created",
        document_ids=[*result.copies, target_parent_id],
        emit_fn=_emit,
    )
    return result.model_dump(mode="json"), spec


@action("document.untransfer", DocumentUntransferParams, domains=["document"])
def _action_untransfer(db: Database, params: DocumentUntransferParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """Undo a transfer from this project: a copy's copies go to the target's Trash; a move's source items
    come back from the source's Trash with their cut edges, and its copy goes to the target's Trash."""
    from fichero_server.api.routes.document.documents import (
        delete_document_impl,
        restore_documents_impl,
    )
    from fichero_server.db.manager import db_manager
    from fichero_server.models.transfer import TransferRecord
    from fichero_server.transfer.move import undo_move

    record = db.get(TransferRecord, params.transfer_id)
    if record is None:
        raise ActionRefused(f"No transfer {params.transfer_id} is recorded in this project.")
    restored: list[str] = []
    if record.mode == TransferMode.move:
        done = undo_move(db, params.transfer_id, actor=ctx.actor, trash=delete_document_impl, restore=restore_documents_impl)
        trashed, restored = done["trashed"], done["restored"]
    else:
        source_db = (db_manager.get_database(record.source_project)
                     if db_manager.is_open(record.source_project) else None)
        try:
            trashed = transfer_copy.undo_copy(db, source_db, params.transfer_id, actor=ctx.actor, trash=delete_document_impl)
        except (LookupError, ValueError) as exc:
            raise ActionRefused(str(exc)) from exc
    here = trashed if record.role.value == "target" else restored
    spec = ChangeSpec(
        domains=["document"],
        target_ids=here,
        after={"transfer_id": params.transfer_id, "trashed": trashed, "restored": restored},
        emit_type="document.deleted" if record.role.value == "target" else "document.created",
        document_ids=here,
        emit_fn=_emit,
    )
    return {"transfer_id": params.transfer_id, "trashed": trashed, "restored": restored}, spec


class DocumentTransferOutParams(BaseModel):
    transfer_id: str


@action(
    "document.transfer_out",
    DocumentTransferOutParams,
    domains=["document"],
    undoable=True,
    invert=_invert_transfer,
)
def _action_transfer_out(db: Database, params: DocumentTransferOutParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """A move's source step, in the SOURCE (#5657): its items to the Trash "moved to <project>", the
    edges that cannot follow cut and kept. Its audit row is what undo finds in the source's window."""
    from fichero_server.transfer.move import run_source_step

    trashed, cuts = run_source_step(db, params.transfer_id, ctx)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=trashed,
        after={"transfer_id": params.transfer_id, "trashed": trashed},
        emit_type="document.deleted",
        document_ids=trashed,
        emit_fn=_emit,
    )
    return {"transfer_id": params.transfer_id, "trashed": trashed, "cuts": len(cuts)}, spec


@router.post("/transfer", response_model=TransferResult)
async def transfer_documents(
    body: TransferRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> TransferResult:
    """Copy items (each with its subtree) from the source project into this one, or plan it.

    `dry_run: true` writes nothing and returns the plan: counts by kind, files and bytes, vocabulary
    matched or to be made, entity matches to be proposed, every cut, everything left behind.
    Otherwise the copy is written, verified and recorded in both projects; undo (`POST
    /api/actions/audit/{audit_id}/undo` in this project) sends the copies to this project's Trash.
    `mode: move` then sends the source's items to the source's Trash ("moved to <this project>") and
    cuts what cannot follow; undo works from either project's audit row.
    Refused in words, changing nothing: the source not open, the same project, an unknown or trashed
    item, an alias, a locked node, a target that is not a folder, an item a pending move holds."""
    try:
        _check_can_read(ctx, body.source, body.items)
        if body.dry_run:
            return await asyncio.to_thread(_dry_run, db, body, ctx)
        invoked = await asyncio.to_thread(
            registry.invoke, db, "document.transfer", body.model_dump(mode="json", exclude={"dry_run"}), ctx)
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=f"You may not do this transfer: {exc}") from exc
    except ActionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except transfer_copy.TransferFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TransferResult.model_validate(invoked.result)


def _dry_run(db: Database, body: TransferRequest, ctx: ActionContext) -> TransferResult:
    source_db = _source_database(body.source, db)
    source_name = Path(source_db.path).parent.stem
    _check_items(source_db, body.items, source_name, body.mode, ctx, db, body.target_parent_id)
    target_parent_id = _target_parent(db, body.target_parent_id)
    plan = build_plan(source_db, db, items=body.items, target_parent_id=target_parent_id,
                      transfer_id=_new_id(), audit_id=_new_id(), actor=ctx.actor)
    return transfer_copy.result_of(plan, mode=body.mode, dry_run=True, state=TransferState.planned,
                                   actor=ctx.actor, source=source_name, target=Path(db.path).parent.stem)
