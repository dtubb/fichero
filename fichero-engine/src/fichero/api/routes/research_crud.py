"""Research Agents CRUD routes — Projects, Plans, Tasks, Steps."""

from datetime import datetime
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from fichero.api.auth import request_actor
from fichero.api.change_stream import emit_change
from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.llm import LLMConfig
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
from fichero.workflows.tools.agent import react_agent
from fichero.workflows.tools import research as _research_tools  # noqa: F401

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
    library_destination_folder_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    library_destination_folder_id: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/projects", response_model=ResearchProject)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchProject:
    project = ResearchProject(
        name=request.name,
        description=request.description,
        created_by=request.created_by,
        library_destination_folder_id=request.library_destination_folder_id,
        metadata=request.metadata,
    )
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
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
    if request.library_destination_folder_id is not None:
        project.library_destination_folder_id = request.library_destination_folder_id
    if request.metadata is not None:
        project.metadata = request.metadata
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


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> DeletedWithIdResponse:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    db.delete(project)
    emit_change(
        x_fichero_library_path,
        type="research.deleted",
        entity_ids=[project_id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return DeletedWithIdResponse(status="deleted", id=project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Plan CRUD
# ─────────────────────────────────────────────────────────────────────────────


class PlanCreateRequest(BaseModel):
    project_id: str
    name: str
    description: str = ""
    order_index: int = 0
    term: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: PlanStatus | None = None
    order_index: int | None = None
    metadata: dict[str, Any] | None = None


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an agent response."""
    candidates: list[str] = []

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    stripped = text.strip()
    candidates.append(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(stripped[start : end + 1].strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _fallback_term_plan(term: str) -> dict[str, Any]:
    """Deterministic fallback when the agent response cannot be parsed."""
    base = term.strip()
    return {
        "archives": [
            f"{base} archives",
            f"{base} records",
        ],
        "locations": [base],
        "multilingual_terms": {
            "en": [base, f"{base} archive", f"{base} records"],
            "es": [base, f"archivo {base}", f"registros {base}"],
            "fr": [base, f"archives {base}", f"dossiers {base}"],
        },
        "summary": "Fallback plan generated without structured agent output.",
    }


async def _build_term_plan(
    term: str,
    *,
    project_name: str | None = None,
    project_description: str | None = None,
) -> dict[str, Any]:
    """Use the existing ReAct agent to draft a minimal research plan."""
    from fichero.app_db import get_app_db

    defaults = get_app_db().get_ai_defaults()
    llm_config = LLMConfig(
        provider=defaults.get("default_text_provider") or "apple",
        model=defaults.get("default_text_model") or "apple-intelligence",
    )
    context: dict[str, Any] = {"term": term}
    if project_name:
        context["project_name"] = project_name
    if project_description:
        context["project_description"] = project_description

    prompt = (
        "Plan a small research starting point for the given term.\n"
        "Use the research_web_search tool if it helps you ground the plan.\n"
        "Return JSON only with these keys:\n"
        "- archives: array of archive names or archive-oriented search targets\n"
        "- locations: array of places or geographic hints worth searching\n"
        "- multilingual_terms: object mapping language codes to arrays of search terms\n"
        "- summary: short planning summary\n"
        "Keep the output concise and practical."
    )
    task = f"Term: {term}\nCreate the smallest usable research plan for this term."

    result = await react_agent(
        inputs={
            "task": task,
            "context": context,
            "tools": ["research_web_search"],
            "system_prompt": prompt,
            "max_iterations": 3,
        },
        state={},
        llm_config=llm_config,
    )

    payload = _extract_json_payload(result.get("result", "") or "")
    if payload is None:
        payload = _fallback_term_plan(term)

    payload.setdefault("term", term)
    payload.setdefault("summary", "")
    payload.setdefault("archives", [])
    payload.setdefault("locations", [])
    payload.setdefault("multilingual_terms", {})
    payload["agent_result"] = {
        "result": result.get("result", ""),
        "tool_calls": result.get("tool_calls", []),
        "iterations": result.get("iterations", 0),
    }
    return payload


@router.post("/plans", response_model=ResearchPlan)
async def create_plan(
    request: PlanCreateRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchPlan:
    project = db.get(ResearchProject, request.project_id)
    planning_payload: dict[str, Any] | None = None
    if request.term:
        planning_payload = await _build_term_plan(
            request.term,
            project_name=project.name if project else None,
            project_description=project.description if project else None,
        )

    plan = ResearchPlan(
        project_id=request.project_id,
        name=request.name,
        description=request.description,
        order_index=request.order_index,
        metadata={
            **request.metadata,
            **(
                {
                    "research_term": request.term,
                    "research_plan": planning_payload,
                }
                if planning_payload is not None
                else {}
            ),
        },
    )
    db.save(plan)
    emit_change(
        x_fichero_library_path,
        type="research.created",
        entity_ids=[plan.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
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
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[plan.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
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
    emit_change(
        x_fichero_library_path,
        type="research.created",
        entity_ids=[task.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return task


@router.get("/plans/{plan_id}/tasks", response_model=ResearchCrudListResponse)
async def list_tasks(
    plan_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchCrudListResponse:
    tasks = db.query(ResearchTask, plan_id=plan_id)
    items = sorted(tasks, key=lambda t: (t.priority, t.created_at))
    return ResearchCrudListResponse(items=items, count=len(items))


@router.get("/projects/{project_id}/tasks", response_model=ResearchCrudListResponse)
async def list_project_tasks(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> ResearchCrudListResponse:
    """All tasks across every plan in a project.

    The Researcher Tasks pane is project-scoped, but tasks hang off plans
    (task.plan_id -> plan.project_id). Aggregate them here so the frontend
    has a single project-level list endpoint.
    """
    plan_ids = {p.id for p in db.query(ResearchPlan, project_id=project_id)}
    tasks = [t for t in db.query(ResearchTask) if t.plan_id in plan_ids]
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
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
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[task.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
) -> ResearchStep:
    step = ResearchStep(
        task_id=request.task_id,
        tool=request.tool,
        label=request.label,
        description=request.description,
        config=request.config,
        order_index=request.order_index,
    )
    db.save(step)
    emit_change(
        x_fichero_library_path,
        type="research.created",
        entity_ids=[step.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
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
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
    actor: str = Depends(request_actor),
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
    emit_change(
        x_fichero_library_path,
        type="research.updated",
        entity_ids=[step.id],
        actor=actor,
        origin_window=x_fichero_origin_window,
        origin_user=actor,
    )
    return step
