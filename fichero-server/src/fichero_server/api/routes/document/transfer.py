"""`POST /api/documents/transfer` — copy a selection into another open project, or plan it (#5657).

Spec: `docs/contributor_manual/specs/source/moving-between-projects.md`. The library header names the
TARGET project; the body names the SOURCE. Every surface (the app's drop, the CLI, MCP) calls this one
route, which runs one audited action, `document.transfer`, in the target; its inverse,
`document.untransfer`, sends the copies to the target's Trash. A dry run writes nothing and returns the
same report a copy would.

Built: plan (`dry_run`), copy and move within one engine (a move's source step is its own audited action
in the source, `document.transfer_out`). Not built: a background job for large transfers. Between machines: the section at the end of this file.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as PathParam
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
    IncomingLand,
    IncomingStatus,
    IncomingTransfer,
    MachineTransferRequest,
    TransferMode,
    TransferRequest,
    TransferResult,
    TransferState,
)
from fichero_server.security import authz
from fichero_server.transfer import copy as transfer_copy
from fichero_server.transfer.plan import build_plan

router = APIRouter()
machines_router = APIRouter()

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


def landing_parent(db: Database, parent_id: str | None) -> tuple[str, Document | None]:
    """The folder the items land in, and the Sources folder to make with the copy when the target has none
    (made in its transaction, so a failure leaves none)."""
    target_parent_id = _target_parent(db, parent_id)
    if target_parent_id:
        return target_parent_id, None
    from fichero_server.importers.sources_folder import SOURCES_FOLDER_NAME
    from fichero_server.models import Status

    made = Document(name=SOURCES_FOLDER_NAME, doc_type=DocType.folder, status=Status.completed)
    return made.id, made


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
    target_parent_id, sources_folder = landing_parent(db, params.target_parent_id)
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


# =============================================================================================
# Between machines (copy only)
# =============================================================================================
# A copy to another engine, and the routes that receive one (#5657, "Between machines (copy only)").
#
# The sending engine: `POST /api/documents/transfer/to-machine` (the library header names the SOURCE project)
# packages the selection and pushes it to a paired machine (`GET /api/machines`, `POST /api/machines/pair`).
# The receiving engine (its library header names the TARGET project, its device token the paired person):
# `POST /api/documents/transfer/incoming` opens the copy and says which objects it lacks, `PUT
# …/incoming/{id}/objects/{sha256}` takes one (re-hashed on arrival), `POST …/incoming/{id}/land` lands it
# all or nothing as the audited action `document.transfer_in` (undo: `document.untransfer`), and `DELETE
# …/incoming/{id}` abandons it, removing what arrived. Logic: `transfer/remote.py`, `transfer/machines.py`.


# --- paired machines ------------------------------------------------------------------------------------

#: A copy's id and an object's hash in a URL: never a path (`transfer.machine.incoming-confined`).
TRANSFER_ID = PathParam(pattern=r"^[0-9a-f]{32}$")
SHA256 = PathParam(pattern=r"^[0-9a-f]{64}$")


def _engine_owner(request: Request) -> None:
    """Pairing out, listing the paired machines and sending to one use credentials this engine holds for the
    whole Mac: only its owner may (the host app on loopback, or an owner's session), never a paired device or
    a collaborator. Refused 403 otherwise."""
    from fichero_server.api.routes.auth.pairing import _owner_for_pairing
    from fichero_server.db.app import get_app_db

    _owner_for_pairing(request, get_app_db())


class PairMachineRequest(BaseModel):
    address: str
    code: str


class MachineOut(BaseModel):
    id: str
    name: str
    url: str
    paired_at: str


@machines_router.get("/machines", response_model=list[MachineOut], summary="The other Fichero engines this one is paired with")
async def list_machines(request: Request) -> list[MachineOut]:
    _engine_owner(request)
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        machines,
    )
    return [MachineOut(**m.public()) for m in await asyncio.to_thread(machines.machines)]


@machines_router.delete("/machines/{machine_id}", summary="Forget a paired machine: remove its saved token on this Mac")
async def forget_machine(request: Request, machine_id: str = PathParam(pattern=r"^[0-9a-f]{32}$")) -> dict[str, bool]:
    """Owner only. Removes this Mac's saved token; the device stays listed on the far Mac until it revokes it."""
    _engine_owner(request)
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        machines,
    )

    try:
        await asyncio.to_thread(machines.forget, machine_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"forgotten": True}


@machines_router.post("/machines/pair", response_model=MachineOut, summary="Pair with another Mac's Fichero by its pairing code")
async def pair_machine(request: Request, body: PairMachineRequest) -> MachineOut:
    """`address`: the other Mac's tailnet name (`name.tailnet.ts.net`); `code`: the pairing code its Fichero
    shows. This engine becomes a paired device there; its token is kept in this Mac's Keychain. The owner
    only. The code is the other Mac's: single use and rate-limited there (`POST /api/pair`)."""
    _engine_owner(request)
    from fichero_server.api.routes.auth.pairing import _record_device_audit
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        machines,
    )

    try:
        found = await asyncio.to_thread(machines.pair, body.address, body.code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{body.address} is not a tailnet address: {exc}") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from fichero_server.api.auth import actor_from_request

    # Engine-wide, like device pairing: no project is involved, so none is required (#5659 hands-on pass).
    _record_device_audit(action_name="machine.pair", actor=actor_from_request(request), params={"address": body.address},
                         device_id=found.id, after=found.public())
    return MachineOut(**found.public())


# --- the sending side -----------------------------------------------------------------------------------


class TransferToMachineParams(BaseModel):
    items: list[str]
    machine: str
    target_project: str
    target_parent_id: str | None = None
    transfer_id: str


@action("document.transfer_to_machine", TransferToMachineParams, domains=["document"], undoable=False, atomic=False)
def _action_to_machine(db: Database, params: TransferToMachineParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """In the SOURCE: the copy to another machine. The source is never changed, beyond its record."""
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        machines,
        remote,
    )
    try:
        far = machines.machine(params.machine)
    except LookupError as exc:
        raise ActionRefused(str(exc)) from exc
    result = remote.send(db, items=params.items, machine=far, target_project=params.target_project,
                         target_parent_id=params.target_parent_id, transfer_id=params.transfer_id, actor=ctx.actor)
    return result.model_dump(mode="json"), ChangeSpec(domains=["document"], target_ids=list(params.items),
                                                      after={"transfer_id": params.transfer_id})


@router.post("/transfer/to-machine", response_model=TransferResult)
async def transfer_to_machine(
    request: Request,
    body: MachineTransferRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> TransferResult:
    """Copy items (each with its subtree) from this project into a project on a paired machine. Always a copy.

    Refused in words, sending nothing: no yes for the pages to leave (403), this engine working offline,
    a machine not paired, an unknown or trashed item, an alias, a locked node, another version of Fichero
    there. A send that stops (502) keeps what arrived there; `resume` with its id sends only the rest."""
    from fichero_server.llm import is_local_only
    from fichero_server.models.transfer import (
        TransferRecord,
        TransferRole,
        TransferState,
    )
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        remote,
    )

    _engine_owner(request)
    source = str(Path(db.path).parent)
    if not body.pages_may_leave:
        raise HTTPException(status_code=403, detail="These pages go to another machine only with your yes (pages_may_leave).")
    from fichero_server.recipes import places

    if (no := places.refusal("another-mac")):
        raise HTTPException(status_code=403, detail=no)  # the app's places cap the request's yes (#5831)
    if is_local_only():
        raise HTTPException(status_code=403, detail="Fichero is working offline on this Mac: nothing is sent to another machine.")
    items, transfer_id = body.items, remote.new_transfer_id()
    if body.resume:
        record = db.get(TransferRecord, body.resume)
        if record is None or record.role != TransferRole.source or record.state != TransferState.sending:
            raise HTTPException(status_code=409, detail=f"There is no stopped copy {body.resume} to send again.")
        items, transfer_id = list(record.items), record.id
    try:
        _check_can_read(ctx, source, items)
        await asyncio.to_thread(_check_items, db, items, Path(source).stem, TransferMode.copy, ctx, None, None)
        invoked = await asyncio.to_thread(registry.invoke, db, "document.transfer_to_machine", {
            "items": items, "machine": body.machine, "target_project": body.target_project,
            "target_parent_id": body.target_parent_id, "transfer_id": transfer_id}, ctx)
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=f"You may not copy these: {exc}") from exc
    except ActionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except remote.MachineTransferStopped as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TransferResult.model_validate(invoked.result)


# --- the receiving side ---------------------------------------------------------------------------------


class TransferInParams(BaseModel):
    transfer_id: str
    target_parent_id: str | None = None


@action("document.transfer_in", TransferInParams, domains=["document"], undoable=True, invert=_invert_transfer,
        atomic=False)  # the copy owns its journal, its transaction and its roll-back
def _action_transfer_in(db: Database, params: TransferInParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """In the TARGET: land a copy from another machine, stamped with this engine's caller."""
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        remote,
    )
    target_parent_id, sources_folder = landing_parent(db, params.target_parent_id)
    audit_id = remote.new_transfer_id()
    try:
        result = remote.land(db, params.transfer_id, target_parent_id=target_parent_id, parent_to_make=sources_folder,
                             actor=ctx.actor, audit_id=audit_id)
    except (LookupError, ValueError) as exc:
        raise ActionRefused(str(exc)) from exc
    spec = ChangeSpec(domains=["document"], target_ids=list(result.copies),
                      after={"transfer_id": result.transfer_id, "copies": list(result.copies)}, audit_id=audit_id,
                      emit_type="document.created", document_ids=[*result.copies, target_parent_id], emit_fn=_emit)
    return result.model_dump(mode="json"), spec


@router.post("/transfer/incoming", response_model=IncomingStatus)
async def open_incoming(body: IncomingTransfer, db: Database = Depends(get_library_database_for_write)) -> IncomingStatus:
    """Another machine opens a copy into this project: what it will send, and which objects are still missing
    here (all of them the first time; on a resumed send, only those that had not arrived)."""
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        remote,
    )
    from fichero_server.workflows.library_sync import LibrarySyncError
    try:
        missing = await asyncio.to_thread(remote.open_incoming, db, body)
    except remote.VersionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except remote.TooBig as exc:
        raise HTTPException(status_code=413, detail=f"This machine will not take this copy: {exc}.") from exc
    except LibrarySyncError as exc:
        raise HTTPException(status_code=422, detail=f"The copy's package is not readable: {exc}") from exc
    return IncomingStatus(transfer_id=body.transfer_id, objects=len(body.manifest.get("objects", [])), missing=missing)


@router.put("/transfer/incoming/{transfer_id}/objects/{sha256}", response_model=IncomingStatus,
            openapi_extra={"requestBody": {"required": True, "content": {"application/octet-stream": {
                "schema": {"type": "string", "format": "binary"}}}}})
async def receive_object(request: Request, transfer_id: str = TRANSFER_ID, sha256: str = SHA256,
                         db: Database = Depends(get_library_database_for_write)) -> IncomingStatus:
    """One object of a copy arrives; it counts only once re-hashed here and found whole (422 otherwise: send it
    again). A body longer than the size the copy declared for it is refused (413) before it is kept, and never
    read past that size. ponytail: held in memory up to `remote.MAX_OBJECT_BYTES`; stream to disk if more."""
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        remote,
    )
    from fichero_server.workflows.library_sync import LibrarySyncError
    try:
        limit = await asyncio.to_thread(remote.expected_size, db, transfer_id, sha256)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    too_big = HTTPException(status_code=413, detail=f"This object was declared as {limit} bytes; more was sent.")
    try:
        if int(request.headers.get("content-length") or 0) > limit:
            raise too_big
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Content-Length is not a number.") from exc
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_big
        chunks.append(chunk)
    data = b"".join(chunks)
    try:
        await asyncio.to_thread(remote.receive, db, transfer_id, sha256, data)
        missing = await asyncio.to_thread(remote.missing, db, transfer_id)
        total = await asyncio.to_thread(remote.objects, db, transfer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LibrarySyncError as exc:
        raise HTTPException(status_code=422, detail=f"The object arrived damaged and was not kept: {exc}") from exc
    return IncomingStatus(transfer_id=transfer_id, objects=total, missing=missing)


@router.post("/transfer/incoming/{transfer_id}/land", response_model=TransferResult)
async def land_incoming(body: IncomingLand, transfer_id: str = TRANSFER_ID,
                        db: Database = Depends(get_library_database_for_write),
                        ctx: ActionContext = Depends(action_context)) -> TransferResult:
    """Land a copy whose objects have all arrived: all or nothing. A failure rolls back what it wrote here and
    keeps the objects, so landing again needs nothing sent again."""
    try:
        invoked = await asyncio.to_thread(registry.invoke, db, "document.transfer_in",
                                          {"transfer_id": transfer_id, "target_parent_id": body.target_parent_id}, ctx)
    except ActionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except transfer_copy.TransferFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TransferResult.model_validate(invoked.result)


class Abandoned(BaseModel):
    transfer_id: str
    removed: int
    said: str


@router.delete("/transfer/incoming/{transfer_id}", response_model=Abandoned)
async def abandon_incoming(transfer_id: str = TRANSFER_ID,
                           db: Database = Depends(get_library_database_for_write)) -> Abandoned:
    """Abandon a copy that will not land: what arrived of it is removed from this machine."""
    from fichero_server.transfer import (  # lazy: app-import budget (#3950)
        remote,
    )
    try:
        removed = await asyncio.to_thread(remote.abandon, db, transfer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Abandoned(transfer_id=transfer_id, removed=removed,
                     said=f"The copy {transfer_id} was abandoned: the {removed} objects that had arrived were removed.")
