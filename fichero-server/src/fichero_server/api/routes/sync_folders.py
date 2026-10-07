"""Synced folders, from the API (#4952, `specs/source/synced-folder.md`): tie, follow, take in, untie.

Thin over `fichero_server.sync_folder`. Tying and untying are audited actions (`sync.tie`,
`sync.untie`), so the app, the CLI, MCP and an agent do it the one way. A folder is kept as `index`
or `keep-arranged` (#5480): `GET /{id}/arrangement` is the dry run, `PUT /{id}/mode` the yes, and
every arrangement is the audited, undoable `sync.arrange` (undo puts each file back). Documents
duplicated by #5495 (the same file held twice) are listed by `GET /duplicates` (the dry run) and
sent to the trash by `POST /duplicates/remove`, the audited, undoable `sync.remove_duplicates`. The folder is a path on the
engine's disk (the engine may be on another machine; the app never assumes it can see it).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database

router = APIRouter(prefix="/sync-folders")


SyncMode = Literal["index", "keep-arranged"]


class TieRequest(BaseModel):
    path: str = Field(description="A full path to a folder on the engine's disk; made if it is not there")
    formats: list[str] = Field(description="What to write there: pagexml, alto and/or tei (may be none when "
                                           "the folder is kept arranged)")
    mode: SyncMode = Field(default="index", description="index: files stay where they are; keep-arranged: "
                                                        "Fichero also moves and renames files inside the folder "
                                                        "to follow the project's folders")


class ModeRequest(BaseModel):
    mode: SyncMode = Field(description="index or keep-arranged")


class ModeParams(ModeRequest):
    folder_id: str


class ArrangeMove(BaseModel):
    """One file moved inside the folder: paths relative to it."""

    document_id: str
    from_path: str
    to_path: str


class ArrangeParams(BaseModel):
    folder_id: str
    moves: list[ArrangeMove] | None = Field(default=None, description="The moves to make (an undo's); "
                                                                      "omitted: the folder's own plan")


class FollowParams(BaseModel):
    folder_id: str
    document_id: str
    from_path: str
    to_path: str


class ArrangementPreview(BaseModel):
    """`source.onboard.keep-arranged`: what an arrangement would move now, before anything moves."""

    mode: SyncMode
    moves: list[ArrangeMove] = Field(description="each file that would move: from, to (inside the folder)")
    refused: str | None = Field(default=None, description="why it would not be arranged, in words")


class TieParams(TieRequest):
    pass


class UntieParams(BaseModel):
    folder_id: str


class IntakeParams(BaseModel):
    folder_id: str
    on: bool


class IntakeRequest(BaseModel):
    on: bool = Field(description="Take files in from the folder: their edits come in as passes")


class IntakeState(BaseModel):
    """`source.sync.intake-is-opt-in`: whether intake is on, and what it would bring in now."""

    on: bool
    would_bring_in: dict[str, int] = Field(description="files changed outside that would come in, by format")


class Tied(BaseModel):
    id: str


class SyncFolderStatus(BaseModel):
    """`source.sync.status-in-inspector`: where it is, what it holds, and what needs a look."""

    id: str
    path: str
    formats: list[str]
    mode: SyncMode = Field(description="index, or keep-arranged: files follow the project's folders")
    intake: bool = Field(description="files changed in the folder come in as passes")
    conflicts: list[str] = Field(description="files changed both in the folder and in Fichero since the last "
                                             "write: both kept as passes, the file no longer written")
    adopted: bool = Field(description="an existing folder adopted by an Index import: kept in its own layout, "
                                      "its files written back in place")
    last_written: datetime | None = None
    pending: int = Field(description="files waiting to be written (their jobs are in Activity)")
    files: list[str] = Field(description="files Fichero wrote, relative to the folder")
    in_the_way: list[str] = Field(description="files in the way that Fichero did not write: left alone")
    changed_outside: list[str] = Field(description="files Fichero wrote that were changed outside: left alone")
    taken_in: list[str] = Field(description="files that arrived in the folder and came in through the import")
    not_read_back: list[str] = Field(description="files that arrived in a form Fichero does not read back: listed only")
    deleted_outside: list[str] = Field(description="files Fichero wrote that were deleted outside: written again "
                                                   "on the next change to their source")


class SyncFolderList(BaseModel):
    folders: list[SyncFolderStatus]


class DuplicateDocument(BaseModel):
    """One document holding a file that another document of the project holds too."""

    id: str
    name: str
    parent_id: str | None = None
    created_at: datetime
    passes: int = Field(description="passes the document carries (work a removal would take to the trash)")


class DuplicateGroup(BaseModel):
    """One file in a synced folder held by more than one document (#5495)."""

    path: str = Field(description="the file, on the engine's disk")
    keep: DuplicateDocument = Field(description="the document kept: the first made, in its folder")
    remove: list[DuplicateDocument] = Field(description="the documents the repair would send to the trash")


class DuplicateReport(BaseModel):
    """The dry run of the duplicate repair: nothing is changed by asking."""

    groups: list[DuplicateGroup]


class RemoveDuplicatesParams(BaseModel):
    document_ids: list[str] = Field(min_length=1, description="documents to send to the trash, each one the dry "
                                                              "run lists under `remove`")


class RemovedDuplicates(BaseModel):
    removed: list[str] = Field(description="documents sent to the trash (with anything under them)")


@action("sync.tie", TieParams, domains=["library"], undoable=False)
def _action_tie(db: Database, params: TieParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    folder_id = sync_folder.tie(db, params.path, params.formats, params.mode)
    return {"id": folder_id}, ChangeSpec(domains=["library"], after={"id": folder_id, "path": params.path,
                                                                     "formats": params.formats,
                                                                     "mode": params.mode},
                                         emit_type="sync.tied")


@action("sync.untie", UntieParams, domains=["library"], undoable=False)
def _action_untie(db: Database, params: UntieParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    sync_folder.untie(db, params.folder_id)
    return {"id": params.folder_id}, ChangeSpec(domains=["library"], after={"id": params.folder_id},
                                                emit_type="sync.untied")


@action("sync.intake", IntakeParams, domains=["library"], undoable=False)
def _action_intake(db: Database, params: IntakeParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    sync_folder.set_intake(db, params.folder_id, params.on)
    return {"id": params.folder_id, "on": params.on}, ChangeSpec(
        domains=["library"], after={"id": params.folder_id, "intake": params.on}, emit_type="sync.intake")


@action("sync.mode", ModeParams, domains=["library"], undoable=False)
def _action_mode(db: Database, params: ModeParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    sync_folder.set_mode(db, params.folder_id, params.mode)
    return {"id": params.folder_id, "mode": params.mode}, ChangeSpec(
        domains=["library"], after={"id": params.folder_id, "mode": params.mode}, emit_type="sync.mode")


def _invert_arrange(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    """Undo puts every file back where it was, last moved first."""
    if not after or not after.get("moves"):
        return None
    return ("sync.arrange", {"folder_id": after["folder_id"], "moves": [
        {"document_id": m["document_id"], "from_path": m["to_path"], "to_path": m["from_path"]}
        for m in reversed(after["moves"])]})


@action("sync.arrange", ArrangeParams, domains=["library", "document"], undoable=True, invert=_invert_arrange)
def _action_arrange(db: Database, params: ArrangeParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """Move files inside a kept-arranged folder: every move listed (from, to), never over a file."""
    from fichero_server import sync_folder

    moves = None if params.moves is None else [m.model_dump() for m in params.moves]
    done = sync_folder.arrange(db, params.folder_id, moves)
    ids = list(dict.fromkeys(m["document_id"] for m in done))
    return {"id": params.folder_id, "moves": done}, ChangeSpec(
        domains=["library", "document"], target_ids=ids, after={"folder_id": params.folder_id, "moves": done},
        document_ids=ids, emit_type="sync.arranged")


@action("sync.follow", FollowParams, domains=["library", "document"], undoable=False)
def _action_follow(db: Database, params: FollowParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """A file moved by hand inside the folder: its document's record follows it (no move back)."""
    from fichero_server import sync_folder

    sync_folder.follow(db, params.folder_id, params.document_id, params.from_path, params.to_path)
    return {"id": params.document_id}, ChangeSpec(
        domains=["library", "document"], target_ids=[params.document_id],
        after=params.model_dump(), document_ids=[params.document_id], emit_type="sync.followed")


def _invert_remove_duplicates(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    """Undo brings every removed duplicate back from the trash, as it was."""
    if not before or not before.get("documents"):
        return None
    return ("document.restore", {"doc_ids": [d["id"] for d in before["documents"]], "documents": before["documents"]})


@action("sync.remove_duplicates", RemoveDuplicatesParams, domains=["document"], undoable=True,
        invert=_invert_remove_duplicates)
def _action_remove_duplicates(db: Database, params: RemoveDuplicatesParams,
                              ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    """Send documents duplicated by #5495 to the trash: only ones the dry run lists, never a kept one."""
    from fichero_server import sync_folder

    removed, snapshots = sync_folder.remove_duplicates(db, params.document_ids, ctx.actor)
    return {"removed": removed}, ChangeSpec(
        domains=["document"], target_ids=removed, before={"documents": snapshots}, after={"document_ids": removed},
        document_ids=removed, emit_type="document.deleted")


@router.get("/duplicates", response_model=DuplicateReport,
            summary="Documents holding the same file of a synced folder (a dry run: nothing changes)")
async def get_duplicates(db: Database = Depends(get_library_database)) -> DuplicateReport:
    """Each file in a synced folder that more than one document holds (as an engine restart once
    took an Index folder's files in again, #5495): the document kept (the first made, in its
    folder) and those the repair would send to the trash, each with the passes it carries."""
    from fichero_server import sync_folder

    return DuplicateReport(groups=[DuplicateGroup(**g) for g in sync_folder.duplicates(db)])


@router.post("/duplicates/remove", response_model=RemovedDuplicates,
             summary="Send duplicates of a synced folder's files to the trash (undoable)")
async def remove_duplicates(
    request: RemoveDuplicatesParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RemovedDuplicates:
    """One audited, undoable action: the documents named, each one the dry run lists under `remove`,
    go to the trash (nothing is deleted for good). Refused (409) in words if any is a kept document
    or no longer a duplicate; then nothing is removed."""
    try:
        result = registry.invoke(db, "sync.remove_duplicates", request.model_dump(), ctx)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RemovedDuplicates(**result.result)


def _intake_state(db: Database, folder_id: str) -> IntakeState:
    from fichero_server import sync_folder

    folder = next((f for f in sync_folder.status(db) if f["id"] == folder_id), None)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"No synced folder {folder_id}")
    return IntakeState(on=folder["intake"], would_bring_in=sync_folder.would_bring_in(db, folder_id))


@router.get("/{folder_id}/intake", response_model=IntakeState, summary="Whether intake is on, and what it would bring in")
async def get_intake(folder_id: str, db: Database = Depends(get_library_database)) -> IntakeState:
    """The preview shown before intake is switched on: the files it would bring in, by format."""
    return _intake_state(db, folder_id)


@router.put("/{folder_id}/intake", response_model=IntakeState, summary="Switch intake on or off for a synced folder")
async def put_intake(
    folder_id: str,
    request: IntakeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> IntakeState:
    """Switched on, the folder is read now and whenever it may have changed: each file Fichero
    wrote or adopted that was changed outside comes in as a new pass ("edited outside Fichero"),
    overwriting nothing; one whose page changed too is a conflict, both kept."""
    _intake_state(db, folder_id)  # 404 for a folder that is not tied
    registry.invoke(db, "sync.intake", {"folder_id": folder_id, "on": request.on}, ctx)
    return _intake_state(db, folder_id)


def _status_of(db: Database, folder_id: str) -> SyncFolderStatus:
    from fichero_server import sync_folder

    folder = next((f for f in sync_folder.status(db) if f["id"] == folder_id), None)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"No synced folder {folder_id}")
    return SyncFolderStatus(**folder)


@router.get("/{folder_id}/arrangement", response_model=ArrangementPreview,
            summary="What keeping the folder arranged would move now (a dry run: nothing moves)")
async def get_arrangement(folder_id: str, db: Database = Depends(get_library_database)) -> ArrangementPreview:
    """Shown before the first arrangement: each file that would move to follow the project's folders,
    and why it would be refused (say, a folder Fichero cannot write to)."""
    from fichero_server import sync_folder

    status = _status_of(db, folder_id)
    moves, refused = sync_folder.plan(db, folder_id)
    return ArrangementPreview(mode=status.mode, moves=[ArrangeMove(**m) for m in moves], refused=refused)


@router.put("/{folder_id}/mode", response_model=SyncFolderStatus,
            summary="Keep a synced folder as Index or Keep arranged")
async def put_mode(
    folder_id: str,
    request: ModeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> SyncFolderStatus:
    """Keep arranged: Fichero moves and renames files only inside the folder, to follow the project's
    folders (a clash takes a numeric suffix; nothing is overwritten or deleted), each arrangement
    undoable; a file moved by hand stays and the project follows it. Refused (422) in words for a
    folder that cannot be written to, or that no project folder came from."""
    _status_of(db, folder_id)
    try:
        registry.invoke(db, "sync.mode", {"folder_id": folder_id, "mode": request.mode}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _status_of(db, folder_id)


@router.post("", response_model=Tied, summary="Tie the project to a folder on the engine's disk")
async def tie_folder(
    request: TieRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> Tied:
    """Write the project's outputs into the folder and keep them current as the work goes on: one
    subfolder per format, one file per source named by its title and lasting id, its loss report
    beside it. Writing is background work (paused by Pause Background Work); a file Fichero did not
    write is never overwritten. Refused (422) for a path that is not a full path on the engine's
    disk or a format a synced folder does not hold."""
    try:
        result = registry.invoke(db, "sync.tie", request.model_dump(), ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Tied(**result.result)


@router.get("", response_model=SyncFolderList, summary="The project's synced folders and their state")
async def list_folders(db: Database = Depends(get_library_database)) -> SyncFolderList:
    from fichero_server import sync_folder

    return SyncFolderList(folders=[SyncFolderStatus(**f) for f in sync_folder.status(db)])


@router.delete("/{folder_id}", response_model=Tied, summary="Untie a synced folder (its files stay on disk)")
async def untie_folder(
    folder_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> Tied:
    result = registry.invoke(db, "sync.untie", {"folder_id": folder_id}, ctx)
    return Tied(**result.result)
