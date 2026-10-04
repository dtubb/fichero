"""Synced folders, from the API (#4952, `specs/source/synced-folder.md`): tie, follow, untie.

Thin over `fichero_server.sync_folder`. Tying and untying are audited actions (`sync.tie`,
`sync.untie`), so the app, the CLI, MCP and an agent do it the one way. The folder is a path on the
engine's disk (the engine may be on another machine; the app never assumes it can see it).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database

router = APIRouter(prefix="/sync-folders")


class TieRequest(BaseModel):
    path: str = Field(description="A full path to a folder on the engine's disk; made if it is not there")
    formats: list[str] = Field(description="What to write there: pagexml, alto and/or tei")


class TieParams(TieRequest):
    pass


class UntieParams(BaseModel):
    folder_id: str


class Tied(BaseModel):
    id: str


class SyncFolderStatus(BaseModel):
    """`source.sync.status-in-inspector`: where it is, what it holds, and what needs a look."""

    id: str
    path: str
    formats: list[str]
    adopted: bool = Field(description="an existing folder adopted by an Index import: kept in its own layout, "
                                      "its files written back in place")
    last_written: datetime | None = None
    pending: int = Field(description="files waiting to be written (their jobs are in Activity)")
    files: list[str] = Field(description="files Fichero wrote, relative to the folder")
    in_the_way: list[str] = Field(description="files in the way that Fichero did not write: left alone")
    changed_outside: list[str] = Field(description="files Fichero wrote that were changed outside: left alone")
    deleted_outside: list[str] = Field(description="files Fichero wrote that were deleted outside: written again "
                                                   "on the next change to their source")


class SyncFolderList(BaseModel):
    folders: list[SyncFolderStatus]


@action("sync.tie", TieParams, domains=["library"], undoable=False)
def _action_tie(db: Database, params: TieParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    folder_id = sync_folder.tie(db, params.path, params.formats)
    return {"id": folder_id}, ChangeSpec(domains=["library"], after={"id": folder_id, "path": params.path,
                                                                     "formats": params.formats},
                                         emit_type="sync.tied")


@action("sync.untie", UntieParams, domains=["library"], undoable=False)
def _action_untie(db: Database, params: UntieParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import sync_folder

    sync_folder.untie(db, params.folder_id)
    return {"id": params.folder_id}, ChangeSpec(domains=["library"], after={"id": params.folder_id},
                                                emit_type="sync.untied")


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
