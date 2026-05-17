"""Research Agents CRUD routes — Projects, Plans, Tasks, Steps."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.research_models import (
    PlanStatus,
    ProjectStatus,
    ResearchPlan,
    ResearchProject,
    ResearchStep,
    ResearchTask,
    StepStatus,
    StepTool,
    TaskStatus,
)
from fichero.models import ResearchCrudListResponse

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD
# ─────────────────────────────────────────────────────────────────────────────


class DeletedWithIdResponse(BaseModel):
    status: str
    id: str


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    created_by: str = "human"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None


@router.post("/projects", response_model=ResearchProject)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchProject:
    project = ResearchProject(
        name=request.name,
        description=request.description,
        created_by=request.created_by,
        metadata=request.metadata,
    )
    db.save(project)
    return project


@router.get("/projects", response_model=ResearchCrudListResponse)
async def list_projects(
    status: ProjectStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchProject]:
    projects = db.query(ResearchProject)
    if status is not None:
        projects = [p for p in projects if p.status == status]
    items = sorted(projects, key=lambda p: p.created_at, reverse=True)
    return ResearchCrudListResponse(items=items, count=len(items))


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
    if request.name is not None:
        project.name = request.name
    if request.description is not None:
        project.description = request.description
    if request.status is not None:
        project.status = request.status
    if request.metadata is not None:
        project.metadata = request.metadata
    project.updated_at = datetime.now()
    db.save(project)
    return project


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> DeletedWithIdResponse:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    db.delete(project)
    return DeletedWithIdResponse(status="deleted", id=project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Plan CRUD
# ─────────────────────────────────────────────────────────────────────────────


class PlanCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""
    order_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: PlanStatus | None = None
    order_index: int | None = None
    metadata: dict[str, Any] | None = None


@router.post("/plans", response_model=ResearchPlan)
async def create_plan(
    request: PlanCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchPlan:
    plan = ResearchPlan(
        project_id=request.project_id,
        name=request.name,
        description=request.description,
        order_index=request.order_index,
        metadata=request.metadata,
    )
    db.save(plan)
    return plan


@router.get("/projects/{project_id}/plans", response_model=ResearchCrudListResponse)
async def list_plans(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchCrudListResponse:
    plans = db.query(ResearchPlan, project_id=project_id)
    items = sorted(plans, key=lambda p: p.order_index)
    return ResearchCrudListResponse(items=items, count=len(items))


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
    if request.name is not None:
        plan.name = request.name
    if request.description is not None:
        plan.description = request.description
    if request.order_index is not None:
        plan.order_index = request.order_index
    if request.metadata is not None:
        plan.metadata = request.metadata
    plan.updated_at = datetime.now()
    db.save(plan)
    return plan


# ─────────────────────────────────────────────────────────────────────────────
# Task CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TaskCreateRequest(BaseModel):
    plan_id: str
    name: str
    description: str = ""
    priority: int = 0
    assigned_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: int | None = None
    assigned_to: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/tasks", response_model=ResearchTask)
async def create_task(
    request: TaskCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchTask:
    task = ResearchTask(
        plan_id=request.plan_id,
        name=request.name,
        description=request.description,
        priority=request.priority,
        assigned_to=request.assigned_to,
        metadata=request.metadata,
    )
    db.save(task)
    return task


@router.get("/plans/{plan_id}/tasks", response_model=ResearchCrudListResponse)
async def list_tasks(
    plan_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchCrudListResponse:
    tasks = db.query(ResearchTask, plan_id=plan_id)
    items = sorted(tasks, key=lambda t: (t.priority, t.created_at))
    return ResearchCrudListResponse(items=items, count=len(items))


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
    if request.name is not None:
        task.name = request.name
    if request.description is not None:
        task.description = request.description
    if request.status is not None:
        task.status = request.status
        if request.status == TaskStatus.completed:
            task.completed_at = datetime.now()
    if request.priority is not None:
        task.priority = request.priority
    if request.assigned_to is not None:
        task.assigned_to = request.assigned_to
    if request.metadata is not None:
        task.metadata = request.metadata
    task.updated_at = datetime.now()
    db.save(task)
    return task


# ─────────────────────────────────────────────────────────────────────────────
# Step CRUD
# ─────────────────────────────────────────────────────────────────────────────


class StepCreateRequest(BaseModel):
    task_id: str
    tool: StepTool
    label: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    order_index: int = 0


class StepUpdateRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    status: StepStatus | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    order_index: int | None = None


@router.post("/steps", response_model=ResearchStep)
async def create_step(
    request: StepCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    step = ResearchStep(
        task_id=request.task_id,
        tool=request.tool,
        label=request.label,
        description=request.description,
        order_index=request.order_index,
    )
    db.save(step)
    return step


@router.get("/tasks/{task_id}/steps", response_model=ResearchCrudListResponse)
async def list_steps(
    task_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchCrudListResponse:
    steps = db.query(ResearchStep, task_id=task_id)
    items = sorted(steps, key=lambda s: s.order_index)
    return ResearchCrudListResponse(items=items, count=len(items))


@router.patch("/steps/{step_id}", response_model=ResearchStep)
async def update_step(
    step_id: str,
    request: StepUpdateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchStep:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")
    if request.label is not None:
        step.label = request.label
    if request.description is not None:
        step.description = request.description
    if request.status is not None:
        step.status = request.status
        if request.status == StepStatus.completed:
            step.completed_at = datetime.now()
    if request.result is not None:
        step.result = request.result
    if request.error is not None:
        step.error = request.error
    if request.order_index is not None:
        step.order_index = request.order_index
    step.updated_at = datetime.now()
    db.save(step)
    return step
