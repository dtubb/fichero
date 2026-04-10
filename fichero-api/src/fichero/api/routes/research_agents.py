"""Agent Research API routes — Layer 0 systematic discovery with sandboxed tools."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.research_models import (
    CheckItemStatus,
    NoteType,
    ResearchChecklistItem,
    ResearchNote,
    ResearchPlan,
    ResearchProject,
    ResearchResult,
    ResearchSource,
    ResearchStatus,
    ResearchStep,
    ResearchTask,
    SourceType,
    StepType,
    WebSearchResult,
)


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    research_question: str = ""
    goals: list[str] = Field(default_factory=list)
    scope_notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    research_question: str | None = None
    goals: list[str] | None = None
    scope_notes: str | None = None
    status: ResearchStatus | None = None
    metadata: dict[str, Any] | None = None


class PlanCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""
    phase_number: int = 1
    objectives: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    due_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    phase_number: int | None = None
    objectives: list[str] | None = None
    success_criteria: list[str] | None = None
    deliverables: list[str] | None = None
    dependencies: list[str] | None = None
    status: ResearchStatus | None = None
    due_date: datetime | None = None
    metadata: dict[str, Any] | None = None


class TaskCreateRequest(BaseModel):
    plan_id: str
    project_id: str
    name: str
    description: str = ""
    task_number: int = 1
    priority: int = Field(default=1, ge=1, le=5)
    estimated_hours: float | None = None
    assigned_to: str = "user"
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    task_number: int | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    estimated_hours: float | None = None
    assigned_to: str | None = None
    status: ResearchStatus | None = None
    dependencies: list[str] | None = None
    result: ResearchResult | None = None
    result_notes: str | None = None
    metadata: dict[str, Any] | None = None


class StepCreateRequest(BaseModel):
    task_id: str
    plan_id: str
    project_id: str
    step_number: int = 1
    step_type: StepType
    name: str = ""
    description: str = ""
    query: str | None = None
    url: str | None = None
    target_source_id: str | None = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepUpdateRequest(BaseModel):
    step_number: int | None = None
    name: str | None = None
    description: str | None = None
    query: str | None = None
    url: str | None = None
    notes: str | None = None
    status: ResearchStatus | None = None
    result: ResearchResult | None = None
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


class SourceCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""
    source_type: SourceType
    location: str
    search_scope: str = ""
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    source_type: SourceType | None = None
    location: str | None = None
    search_scope: str | None = None
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    last_searched: datetime | None = None
    findings_count: int | None = None
    status: ResearchStatus | None = None
    metadata: dict[str, Any] | None = None


class NoteCreateRequest(BaseModel):
    project_id: str
    plan_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    note_type: NoteType
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    author_id: str = "user"
    is_key_finding: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteUpdateRequest(BaseModel):
    content: str | None = None
    note_type: NoteType | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_ids: list[str] | None = None
    claim_ids: list[str] | None = None
    is_key_finding: bool | None = None
    metadata: dict[str, Any] | None = None


class ChecklistItemCreateRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    description: str
    category: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChecklistItemUpdateRequest(BaseModel):
    description: str | None = None
    category: str | None = None
    status: CheckItemStatus | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_notes: str | None = None
    metadata: dict[str, Any] | None = None


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=10, ge=1, le=50)
    project_id: str | None = None
    source_filter: list[SourceType] = Field(default_factory=list)


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult]
    total_found: int
    search_time_ms: int | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class BrowserNavigateRequest(BaseModel):
    url: str
    wait_for_selector: str | None = None
    project_id: str | None = None


class BrowserNavigateResponse(BaseModel):
    url: str
    title: str
    success: bool
    loaded_at: datetime = Field(default_factory=datetime.now)


class DocumentFetchRequest(BaseModel):
    url: str
    project_id: str | None = None
    extract_claims: bool = False
    create_source: bool = True


class DocumentFetchResponse(BaseModel):
    url: str
    document_id: str | None = None  # If created as Source
    title: str | None = None
    content_preview: str | None = None
    claims_extracted: int = 0
    success: bool
    message: str = ""
    fetched_at: datetime = Field(default_factory=datetime.now)


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/projects", response_model=ResearchProject)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchProject:
    now = datetime.now()
    project = ResearchProject(
        name=request.name.strip(),
        description=request.description.strip(),
        research_question=request.research_question.strip(),
        goals=list(request.goals),
        scope_notes=request.scope_notes.strip(),
        status=ResearchStatus.draft,
        owner_id="user",
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(project)
    return project


@router.get("/projects", response_model=list[ResearchProject])
async def list_projects(
    status: ResearchStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchProject]:
    rows = db.all(ResearchProject)
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return rows


@router.get("/projects/{project_id}", response_model=ResearchProject)
async def get_project(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchProject:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return project


@router.patch("/projects/{project_id}", response_model=ResearchProject)
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchProject:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(project, key, value)
    project.updated_at = datetime.now()
    db.save(project)
    return project


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    project.status = ResearchStatus.archived
    project.updated_at = datetime.now()
    db.save(project)
    return {"status": "archived"}


# ─────────────────────────────────────────────────────────────────────────────
# Plan CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/plans", response_model=ResearchPlan)
async def create_plan(
    request: PlanCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchPlan:
    # Verify project exists
    project = db.get(ResearchProject, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    now = datetime.now()
    plan = ResearchPlan(
        project_id=request.project_id,
        name=request.name.strip(),
        description=request.description.strip(),
        phase_number=request.phase_number,
        objectives=list(request.objectives),
        success_criteria=list(request.success_criteria),
        deliverables=list(request.deliverables),
        dependencies=list(request.dependencies),
        due_date=request.due_date,
        status=ResearchStatus.draft,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(plan)
    return plan


@router.get("/plans", response_model=list[ResearchPlan])
async def list_plans(
    project_id: str | None = None,
    status: ResearchStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchPlan]:
    rows = db.all(ResearchPlan)
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return sorted(rows, key=lambda x: x.phase_number)


@router.get("/plans/{plan_id}", response_model=ResearchPlan)
async def get_plan(
    plan_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchPlan:
    plan = db.get(ResearchPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    return plan


@router.patch("/plans/{plan_id}", response_model=ResearchPlan)
async def update_plan(
    plan_id: str,
    request: PlanUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchPlan:
    plan = db.get(ResearchPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(plan, key, value)
    plan.updated_at = datetime.now()
    db.save(plan)
    return plan


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    plan = db.get(ResearchPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    plan.status = ResearchStatus.archived
    plan.updated_at = datetime.now()
    db.save(plan)
    return {"status": "archived"}


# ─────────────────────────────────────────────────────────────────────────────
# Task CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tasks", response_model=ResearchTask)
async def create_task(
    request: TaskCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchTask:
    # Verify plan exists
    plan = db.get(ResearchPlan, request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {request.plan_id}")

    now = datetime.now()
    task = ResearchTask(
        plan_id=request.plan_id,
        project_id=request.project_id,
        name=request.name.strip(),
        description=request.description.strip(),
        task_number=request.task_number,
        priority=request.priority,
        estimated_hours=request.estimated_hours,
        assigned_to=request.assigned_to,
        dependencies=list(request.dependencies),
        status=ResearchStatus.draft,
        result=ResearchResult.pending,
        result_notes="",
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(task)
    return task


@router.get("/tasks", response_model=list[ResearchTask])
async def list_tasks(
    plan_id: str | None = None,
    project_id: str | None = None,
    assigned_to: str | None = None,
    status: ResearchStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchTask]:
    rows = db.all(ResearchTask)
    if plan_id is not None:
        rows = [r for r in rows if r.plan_id == plan_id]
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if assigned_to is not None:
        rows = [r for r in rows if r.assigned_to == assigned_to]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return sorted(rows, key=lambda x: (x.priority, x.task_number))


@router.get("/tasks/{task_id}", response_model=ResearchTask)
async def get_task(
    task_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchTask:
    task = db.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return task


@router.patch("/tasks/{task_id}", response_model=ResearchTask)
async def update_task(
    task_id: str,
    request: TaskUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchTask:
    task = db.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(task, key, value)
    task.updated_at = datetime.now()
    db.save(task)
    return task


@router.post("/tasks/{task_id}/complete", response_model=ResearchTask)
async def complete_task(
    task_id: str,
    result_notes: str = "",
    db: Database = Depends(get_library_database),
) -> ResearchTask:
    task = db.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    task.status = ResearchStatus.complete
    task.result = ResearchResult.success
    task.result_notes = result_notes
    task.updated_at = datetime.now()
    db.save(task)
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    task = db.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    task.status = ResearchStatus.archived
    task.updated_at = datetime.now()
    db.save(task)
    return {"status": "archived"}


# ─────────────────────────────────────────────────────────────────────────────
# Step CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/steps", response_model=ResearchStep)
async def create_step(
    request: StepCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    # Verify task exists
    task = db.get(ResearchTask, request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {request.task_id}")

    now = datetime.now()
    step = ResearchStep(
        task_id=request.task_id,
        plan_id=request.plan_id,
        project_id=request.project_id,
        step_number=request.step_number,
        step_type=request.step_type,
        name=request.name.strip(),
        description=request.description.strip(),
        query=request.query,
        url=request.url,
        target_source_id=request.target_source_id,
        notes=request.notes.strip(),
        status=ResearchStatus.draft,
        result=ResearchResult.pending,
        result_data={},
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(step)
    return step


@router.get("/steps", response_model=list[ResearchStep])
async def list_steps(
    task_id: str | None = None,
    plan_id: str | None = None,
    project_id: str | None = None,
    step_type: StepType | None = None,
    status: ResearchStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchStep]:
    rows = db.all(ResearchStep)
    if task_id is not None:
        rows = [r for r in rows if r.task_id == task_id]
    if plan_id is not None:
        rows = [r for r in rows if r.plan_id == plan_id]
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if step_type is not None:
        rows = [r for r in rows if r.step_type == step_type]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return sorted(rows, key=lambda x: x.step_number)


@router.get("/steps/{step_id}", response_model=ResearchStep)
async def get_step(
    step_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")
    return step


@router.patch("/steps/{step_id}", response_model=ResearchStep)
async def update_step(
    step_id: str,
    request: StepUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(step, key, value)
    step.updated_at = datetime.now()
    db.save(step)
    return step


@router.post("/steps/{step_id}/execute", response_model=ResearchStep)
async def execute_step(
    step_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    """Mark a step as in-progress with sandboxed execution placeholder."""
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")

    step.status = ResearchStatus.in_progress
    step.updated_at = datetime.now()
    db.save(step)
    return step


class StepCompleteRequest(BaseModel):
    result: ResearchResult = ResearchResult.success
    result_data: dict[str, Any] = Field(default_factory=dict)


@router.post("/steps/{step_id}/complete", response_model=ResearchStep)
async def complete_step(
    step_id: str,
    request: StepCompleteRequest,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")

    step.status = ResearchStatus.complete
    step.result = request.result
    step.result_data = request.result_data
    step.execution_time_ms = 0  # Would be calculated from actual execution
    step.updated_at = datetime.now()
    db.save(step)
    return step


@router.delete("/steps/{step_id}")
async def delete_step(
    step_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")
    step.status = ResearchStatus.archived
    step.updated_at = datetime.now()
    db.save(step)
    return {"status": "archived"}


# ─────────────────────────────────────────────────────────────────────────────
# Source CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/sources", response_model=ResearchSource)
async def create_source(
    request: SourceCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchSource:
    now = datetime.now()
    source = ResearchSource(
        project_id=request.project_id,
        name=request.name.strip(),
        description=request.description.strip(),
        source_type=request.source_type,
        location=request.location.strip(),
        search_scope=request.search_scope.strip(),
        relevance_score=request.relevance_score,
        findings_count=0,
        status=ResearchStatus.active,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(source)
    return source


@router.get("/sources", response_model=list[ResearchSource])
async def list_sources(
    project_id: str | None = None,
    source_type: SourceType | None = None,
    status: ResearchStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchSource]:
    rows = db.all(ResearchSource)
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if source_type is not None:
        rows = [r for r in rows if r.source_type == source_type]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return rows


@router.get("/sources/{source_id}", response_model=ResearchSource)
async def get_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchSource:
    source = db.get(ResearchSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    return source


@router.patch("/sources/{source_id}", response_model=ResearchSource)
async def update_source(
    source_id: str,
    request: SourceUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchSource:
    source = db.get(ResearchSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(source, key, value)
    source.updated_at = datetime.now()
    db.save(source)
    return source


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    source = db.get(ResearchSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
    source.status = ResearchStatus.archived
    source.updated_at = datetime.now()
    db.save(source)
    return {"status": "archived"}


# ─────────────────────────────────────────────────────────────────────────────
# Note CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/notes", response_model=ResearchNote)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchNote:
    now = datetime.now()
    note = ResearchNote(
        project_id=request.project_id,
        plan_id=request.plan_id,
        task_id=request.task_id,
        step_id=request.step_id,
        note_type=request.note_type,
        content=request.content.strip(),
        confidence=request.confidence,
        source_ids=list(request.source_ids),
        claim_ids=list(request.claim_ids),
        author_id=request.author_id,
        is_key_finding=request.is_key_finding,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(note)
    return note


@router.get("/notes", response_model=list[ResearchNote])
async def list_notes(
    project_id: str | None = None,
    task_id: str | None = None,
    note_type: NoteType | None = None,
    is_key_finding: bool | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchNote]:
    rows = db.all(ResearchNote)
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if task_id is not None:
        rows = [r for r in rows if r.task_id == task_id]
    if note_type is not None:
        rows = [r for r in rows if r.note_type == note_type]
    if is_key_finding is not None:
        rows = [r for r in rows if r.is_key_finding == is_key_finding]
    return sorted(rows, key=lambda x: x.created_at, reverse=True)


@router.get("/notes/{note_id}", response_model=ResearchNote)
async def get_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchNote:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    return note


@router.patch("/notes/{note_id}", response_model=ResearchNote)
async def update_note(
    note_id: str,
    request: NoteUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchNote:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(note, key, value)
    note.updated_at = datetime.now()
    db.save(note)
    return note


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, str]:
    note = db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note not found: {note_id}")
    db.delete(note)
    return {"status": "deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Checklist CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/checklist-items", response_model=ResearchChecklistItem)
async def create_checklist_item(
    request: ChecklistItemCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchChecklistItem:
    now = datetime.now()
    item = ResearchChecklistItem(
        project_id=request.project_id,
        task_id=request.task_id,
        step_id=request.step_id,
        description=request.description.strip(),
        category=request.category.strip(),
        status=CheckItemStatus.pending,
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(item)
    return item


@router.get("/checklist-items", response_model=list[ResearchChecklistItem])
async def list_checklist_items(
    project_id: str | None = None,
    task_id: str | None = None,
    status: CheckItemStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchChecklistItem]:
    rows = db.all(ResearchChecklistItem)
    if project_id is not None:
        rows = [r for r in rows if r.project_id == project_id]
    if task_id is not None:
        rows = [r for r in rows if r.task_id == task_id]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    return rows


@router.get("/checklist-items/{item_id}", response_model=ResearchChecklistItem)
async def get_checklist_item(
    item_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchChecklistItem:
    item = db.get(ResearchChecklistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Checklist item not found: {item_id}")
    return item


@router.patch("/checklist-items/{item_id}", response_model=ResearchChecklistItem)
async def update_checklist_item(
    item_id: str,
    request: ChecklistItemUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchChecklistItem:
    item = db.get(ResearchChecklistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Checklist item not found: {item_id}")

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    item.updated_at = datetime.now()
    db.save(item)
    return item


@router.post("/checklist-items/{item_id}/complete", response_model=ResearchChecklistItem)
async def complete_checklist_item(
    item_id: str,
    verified_by: str = "user",
    verification_notes: str = "",
    db: Database = Depends(get_library_database),
) -> ResearchChecklistItem:
    item = db.get(ResearchChecklistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Checklist item not found: {item_id}")

    item.status = CheckItemStatus.complete
    item.verified_by = verified_by
    item.verified_at = datetime.now()
    item.verification_notes = verification_notes
    item.updated_at = datetime.now()
    db.save(item)
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tools (placeholders - full implementation requires HTTP/browser libs)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/web-search", response_model=WebSearchResponse)
async def web_search(
    request: WebSearchRequest,
    db: Database = Depends(get_library_database),
) -> WebSearchResponse:
    """Sandboxed web search - placeholder implementation.

    Returns example results. Full implementation requires:
    - HTTP client with robots.txt respect
    - Rate limiting
    - Search engine APIs or crawlers
    """
    # Placeholder: return example results
    example_results = [
        WebSearchResult(
            url="https://example.com/article1",
            title="Example Article on Research Topic",
            snippet="This is an example search result snippet...",
            source="web_search",
            relevance_score=0.85,
        ),
        WebSearchResult(
            url="https://example.org/paper1",
            title="Academic Paper Example",
            snippet="Abstract of the academic paper...",
            source="web_search",
            relevance_score=0.78,
        ),
    ]

    return WebSearchResponse(
        query=request.query,
        results=example_results[: request.max_results],
        total_found=len(example_results),
        search_time_ms=150,
    )


@router.post("/tools/browser-navigate", response_model=BrowserNavigateResponse)
async def browser_navigate(
    request: BrowserNavigateRequest,
    db: Database = Depends(get_library_database),
) -> BrowserNavigateResponse:
    """Sandboxed browser navigation - placeholder implementation.

    Returns example response. Full implementation requires:
    - Playwright or Selenium browser automation
    - Isolated process execution
    - Action logging
    """
    return BrowserNavigateResponse(
        url=request.url,
        title=f"Page at {request.url}",
        success=True,
    )


@router.post("/tools/document-fetch", response_model=DocumentFetchResponse)
async def document_fetch(
    request: DocumentFetchRequest,
    db: Database = Depends(get_library_database),
) -> DocumentFetchResponse:
    """Fetch document and create Layer 1 Source - placeholder implementation.

    Returns example response. Full implementation requires:
    - HTTP client with content extraction
    - Document processing pipeline
    - Claim extraction (optional)
    """
    return DocumentFetchResponse(
        url=request.url,
        document_id=None,  # Would be created from actual fetch
        title=f"Document from {request.url}",
        content_preview="[Document content would appear here after fetch]",
        claims_extracted=0,
        success=True,
        message="Document fetch placeholder - real implementation requires HTTP/browser libraries",
    )
