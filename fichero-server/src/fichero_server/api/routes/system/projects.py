"""Projects / research workspaces API (#918).

Group documents, entities, claims, notes, interpretations under a
named workspace. Same KG row can sit in multiple projects (an
entity referenced by Chapter 3 and the JLAR review both).
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.library_header import require_library_path
from fichero_server.api.auth import request_actor
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    Project,
    ProjectInclusion,
    ProjectStatus,
)
from fichero_server.models import ProjectInclusionListResponse, ProjectListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects")


VALID_TARGET_TYPES = {
    "document",
    "entity",
    "claim",
    "note",
    "interpretation",
    "annotation",
}


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    status: ProjectStatus = ProjectStatus.active
    members: list[str] = []


@router.post("", response_model=Project)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> Project:
    project = Project(**request.model_dump())
    db.save(project)
    emit_change(
        x_fichero_library_path,
        type="research.created",
        entity_ids=[project.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return project


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status: ProjectStatus | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[Project]:
    rows = db.query(Project)
    if status is not None:
        rows = [r for r in rows if r.status == status]
    rows.sort(key=lambda r: r.updated_at, reverse=True)
    return ProjectListResponse(items=rows, count=len(rows))


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    return project


class ProjectPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None
    status: ProjectStatus | None = None
    members: list[str] | None = None


@router.patch("/{project_id}", response_model=Project)
async def patch_project(
    project_id: str,
    request: ProjectPatchRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    project.updated_at = datetime.now()
    db.save(project)
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[project.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    # Cascade — drop all ProjectInclusion rows for this project.
    for incl in db.query(ProjectInclusion):
        if incl.project_id == project_id:
            db.delete(incl)
    db.delete(project)
    emit_change(
        x_fichero_library_path,
        type="research.deleted",
        entity_ids=[project_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )


# =============================================================================
# Inclusions — add/remove items
# =============================================================================


class InclusionRequest(BaseModel):
    target_id: str
    target_type: str
    role: str | None = None
    notes: str | None = None


@router.post(
    "/{project_id}/include",
    response_model=ProjectInclusion,
    summary="Add a KG item (document / entity / claim / note / interpretation / annotation) to a project",
)
async def include_item(
    project_id: str,
    request: InclusionRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ProjectInclusion:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    if request.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(
            400,
            f"target_type must be one of {sorted(VALID_TARGET_TYPES)}",
        )
    # Dedup: don't create the same (project, target) twice.
    for existing in db.query(ProjectInclusion):
        if (
            existing.project_id == project_id
            and existing.target_id == request.target_id
            and existing.target_type == request.target_type
        ):
            return existing
    incl = ProjectInclusion(
        project_id=project_id,
        target_id=request.target_id,
        target_type=request.target_type,
        role=request.role,
        notes=request.notes,
    )
    db.save(incl)
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[project_id, request.target_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return incl


@router.delete(
    "/{project_id}/include/{inclusion_id}",
    status_code=204,
)
async def remove_inclusion(
    project_id: str,
    inclusion_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> None:
    incl = db.get(ProjectInclusion, inclusion_id)
    if incl is None:
        raise HTTPException(404, f"Inclusion not found: {inclusion_id}")
    if incl.project_id != project_id:
        raise HTTPException(400, f"Inclusion does not belong to project {project_id}")
    db.delete(incl)
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[project_id, inclusion_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )


@router.get(
    "/{project_id}/items",
    response_model=ProjectInclusionListResponse,
    summary="List every item included in a project, optionally filtered by type",
)
async def list_items(
    project_id: str,
    target_type: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> ProjectInclusionListResponse:
    if db.get(Project, project_id) is None:
        raise HTTPException(404, f"Project not found: {project_id}")
    rows = [i for i in db.query(ProjectInclusion) if i.project_id == project_id]
    if target_type is not None:
        rows = [r for r in rows if r.target_type == target_type]
    rows.sort(key=lambda r: r.added_at, reverse=True)
    return ProjectInclusionListResponse(items=rows, count=len(rows))


@router.get(
    "/membership/{target_id}",
    response_model=ProjectListResponse,
    summary="Which projects include this KG row?",
)
async def project_membership(
    target_id: str,
    target_type: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[Project]:
    inclusions = [
        i
        for i in db.query(ProjectInclusion)
        if i.target_id == target_id
        and (target_type is None or i.target_type == target_type)
    ]
    project_ids = {i.project_id for i in inclusions}
    projects = [db.get(Project, pid) for pid in project_ids]
    items = [p for p in projects if p is not None]
    return ProjectListResponse(items=items, count=len(items))
