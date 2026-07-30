"""Research Agents CRUD routes — Projects, Plans, Tasks, Steps."""

from datetime import datetime
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.db import Database
# NOTE: fichero_server.llm is imported inside _draft_plan below, not here (#3950).
from fichero_server.models.research import (
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
from fichero_server.models import ResearchCrudListResponse
# NOTE: react_agent is imported inside _draft_plan below, not here (#3950).
# Importing any module in the tools package runs tools/__init__.py, which
# imports every tool and with them Quartz, MCP and langgraph.
#
# The `from fichero_server.workflows.tools import research as _research_tools` side
# effect that used to sit here has been REMOVED, not deferred: it registered
# the research tools, but tools/__init__.py:107 already imports `research`, so
# the tool-loading path owns that registration (#3951 — a tool registers by
# being imported in tools/__init__.py, and nowhere else). Registration no
# longer depends on this route module happening to be imported.

# Passthrough wrapper (#3950).
#
# `react_agent` must stay a MODULE ATTRIBUTE: tests patch
# `fichero_server.api.routes.research_crud.react_agent`, which needs the attribute to
# exist AND the call site to resolve it as a module global. Importing any
# module in the tools package runs tools/__init__.py (every tool, Quartz, MCP,
# langgraph), so the import itself stays deferred to first call.


async def react_agent(*args, **kwargs):
    """Passthrough to tools.agent.react_agent; imports it on first call (#3950)."""
    from fichero_server.workflows.tools.agent import react_agent as _impl  # noqa: PLC0415

    return await _impl(*args, **kwargs)


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


def create_project_impl(
    db: Database, request: ProjectCreateRequest
) -> ResearchProject:
    project = ResearchProject(
        name=request.name,
        description=request.description,
        created_by=request.created_by,
        library_destination_folder_id=request.library_destination_folder_id,
        metadata=request.metadata,
    )
    db.save(project)
    return project


def update_project_impl(
    db: Database, project_id: str, request: ProjectUpdateRequest
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
    return project


def delete_project_impl(db: Database, project_id: str) -> dict[str, Any]:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    before = project.model_dump(mode="json")
    db.delete(project)
    return before


def restore_project_impl(db: Database, snapshot: dict[str, Any]) -> ResearchProject:
    project = ResearchProject(**snapshot)
    db.save(project)
    return project


@router.post("/projects", response_model=ResearchProject)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchProject:
    result = registry.invoke(
        db,
        "research.project.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ResearchProject.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchProject:
    result = registry.invoke(
        db,
        "research.project.update",
        {"project_id": project_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return ResearchProject.model_validate(result.result)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> DeletedWithIdResponse:
    registry.invoke(db, "research.project.delete", {"project_id": project_id}, ctx)
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


def create_plan_impl(
    db: Database,
    request: PlanCreateRequest,
    *,
    planning_payload: dict[str, Any] | None = None,
) -> ResearchPlan:
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
    return plan


def update_plan_impl(
    db: Database, plan_id: str, request: PlanUpdateRequest
) -> ResearchPlan:
    plan = db.get(ResearchPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    if request.name is not None:
        plan.name = request.name
    if request.description is not None:
        plan.description = request.description
    if request.status is not None:
        plan.status = request.status
    if request.order_index is not None:
        plan.order_index = request.order_index
    if request.metadata is not None:
        plan.metadata = request.metadata
    plan.updated_at = datetime.now()
    db.save(plan)
    return plan


def delete_plan_impl(db: Database, plan_id: str) -> dict[str, Any]:
    plan = db.get(ResearchPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_id}")
    before = plan.model_dump(mode="json")
    db.delete(plan)
    return before


def restore_plan_impl(db: Database, snapshot: dict[str, Any]) -> ResearchPlan:
    plan = ResearchPlan(**snapshot)
    db.save(plan)
    return plan


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
    from fichero_server.db.app import get_app_db

    # LLMConfig only — react_agent is a module-level passthrough below,
    # because tests patch it; a local import here would shadow the patch.
    from fichero_server.llm import LLMConfig  # noqa: PLC0415

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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchPlan:
    planning_payload: dict[str, Any] | None = None
    if request.term:
        project = db.get(ResearchProject, request.project_id)
        planning_payload = await _build_term_plan(
            request.term,
            project_name=project.name if project else None,
            project_description=project.description if project else None,
        )
    result = registry.invoke(
        db,
        "research.plan.create",
        {
            **request.model_dump(mode="json"),
            "planning_payload": planning_payload,
        },
        ctx,
    )
    return ResearchPlan.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchPlan:
    result = registry.invoke(
        db,
        "research.plan.update",
        {"plan_id": plan_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return ResearchPlan.model_validate(result.result)


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


def create_task_impl(
    db: Database, request: TaskCreateRequest
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


def update_task_impl(
    db: Database, task_id: str, request: TaskUpdateRequest
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


def delete_task_impl(db: Database, task_id: str) -> dict[str, Any]:
    task = db.get(ResearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    before = task.model_dump(mode="json")
    db.delete(task)
    return before


def restore_task_impl(db: Database, snapshot: dict[str, Any]) -> ResearchTask:
    task = ResearchTask(**snapshot)
    db.save(task)
    return task


@router.post("/tasks", response_model=ResearchTask)
async def create_task(
    request: TaskCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchTask:
    result = registry.invoke(
        db,
        "research.task.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ResearchTask.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchTask:
    result = registry.invoke(
        db,
        "research.task.update",
        {"task_id": task_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return ResearchTask.model_validate(result.result)


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


def create_step_impl(
    db: Database, request: StepCreateRequest
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
    return step


def update_step_impl(
    db: Database, step_id: str, request: StepUpdateRequest
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


def delete_step_impl(db: Database, step_id: str) -> dict[str, Any]:
    step = db.get(ResearchStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step not found: {step_id}")
    before = step.model_dump(mode="json")
    db.delete(step)
    return before


def restore_step_impl(db: Database, snapshot: dict[str, Any]) -> ResearchStep:
    step = ResearchStep(**snapshot)
    db.save(step)
    return step


@router.post("/steps", response_model=ResearchStep)
async def create_step(
    request: StepCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchStep:
    result = registry.invoke(
        db,
        "research.step.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ResearchStep.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ResearchStep:
    result = registry.invoke(
        db,
        "research.step.update",
        {"step_id": step_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return ResearchStep.model_validate(result.result)


class ResearchProjectDeleteParams(BaseModel):
    project_id: str


class ResearchProjectUpdateParams(ProjectUpdateRequest):
    project_id: str


class ResearchProjectRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class ResearchPlanCreateParams(PlanCreateRequest):
    planning_payload: dict[str, Any] | None = None


class ResearchPlanUpdateParams(PlanUpdateRequest):
    plan_id: str


class ResearchPlanDeleteParams(BaseModel):
    plan_id: str


class ResearchPlanRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class ResearchTaskUpdateParams(TaskUpdateRequest):
    task_id: str


class ResearchTaskDeleteParams(BaseModel):
    task_id: str


class ResearchTaskRestoreParams(BaseModel):
    snapshot: dict[str, Any]


class ResearchStepUpdateParams(StepUpdateRequest):
    step_id: str


class ResearchStepDeleteParams(BaseModel):
    step_id: str


class ResearchStepRestoreParams(BaseModel):
    snapshot: dict[str, Any]


def _research_spec(
    verb: str,
    row_id: str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    mirrors_document: bool = True,
) -> ChangeSpec:
    """Change spec for a research row mutation.

    ``mirrors_document``: projects, plans and tasks are mirrored into the
    document tree by the DB layer (``_save_research_workspace_document`` and
    siblings) sharing the row's id — so their mutations ALSO emit a
    ``document.<verb>`` event. Without it the sidebar (which listens on the
    ``document`` domain) never learned an agent-created workspace existed
    (#4335). Steps have no document mirror and pass ``False``.
    """
    def _emit(ctx: ActionContext, spec: ChangeSpec) -> None:
        if not ctx.library_path or not spec.emit_type:
            return
        emit_change(
            ctx.library_path,
            type=spec.emit_type,
            entity_ids=spec.entity_ids,
            actor=ctx.actor,
            origin_window=ctx.origin_window,
            origin_user=ctx.actor,
        )
        if mirrors_document:
            emit_change(
                ctx.library_path,
                type=f"document.{verb}",
                entity_ids=spec.entity_ids,
                actor=ctx.actor,
                origin_window=ctx.origin_window,
                origin_user=ctx.actor,
            )

    return ChangeSpec(
        domains=["research"],
        target_ids=[row_id],
        before=before,
        after=after,
        emit_type=f"research.{verb}",
        entity_ids=[row_id],
        emit_fn=_emit,
    )


def _invert_create_project(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.project.delete", {"project_id": after["id"]})


def _invert_restore_snapshot(before, after, ctx):
    if not before:
        return None
    snapshot = after if after and after.get("id") != before.get("id") else before
    return None if snapshot is None else ("__restore__", {"snapshot": snapshot})


@action("research.project.create", ProjectCreateRequest, domains=["research"], undoable=True, invert=_invert_create_project)
def _action_create_project(db, params: ProjectCreateRequest, ctx: ActionContext):
    project = create_project_impl(db, params)
    return project, _research_spec("created", project.id, after=project.model_dump(mode="json"))


def _invert_update_project(before, after, ctx):
    if not before:
        return None
    return ("research.project.restore", {"snapshot": before})


@action("research.project.update", ResearchProjectUpdateParams, domains=["research"], undoable=True, invert=_invert_update_project)
def _action_update_project(db, params: ResearchProjectUpdateParams, ctx: ActionContext):
    before = db.get(ResearchProject, params.project_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {params.project_id}")
    updated = update_project_impl(
        db,
        params.project_id,
        ProjectUpdateRequest.model_validate(params.model_dump(exclude={"project_id"})),
    )
    return updated, _research_spec(
        "updated",
        updated.id,
        before=before.model_dump(mode="json"),
        after=updated.model_dump(mode="json"),
    )


def _invert_delete_project(before, after, ctx):
    return None if not before else ("research.project.restore", {"snapshot": before})


@action("research.project.delete", ResearchProjectDeleteParams, domains=["research"], undoable=True, invert=_invert_delete_project)
def _action_delete_project(db, params: ResearchProjectDeleteParams, ctx: ActionContext):
    before = delete_project_impl(db, params.project_id)
    return {"status": "deleted", "id": params.project_id}, _research_spec(
        "deleted",
        params.project_id,
        before=before,
        after={"id": params.project_id},
    )


@action("research.project.restore", ResearchProjectRestoreParams, domains=["research"], undoable=False)
def _action_restore_project(db, params: ResearchProjectRestoreParams, ctx: ActionContext):
    project = restore_project_impl(db, params.snapshot)
    return project, _research_spec("updated", project.id, after=project.model_dump(mode="json"))


def _invert_create_plan(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.plan.delete", {"plan_id": after["id"]})


@action("research.plan.create", ResearchPlanCreateParams, domains=["research"], undoable=True, invert=_invert_create_plan)
def _action_create_plan(db, params: ResearchPlanCreateParams, ctx: ActionContext):
    plan = create_plan_impl(
        db,
        PlanCreateRequest.model_validate(params.model_dump(exclude={"planning_payload"})),
        planning_payload=params.planning_payload,
    )
    return plan, _research_spec("created", plan.id, after=plan.model_dump(mode="json"))


def _invert_update_plan(before, after, ctx):
    return None if not before else ("research.plan.restore", {"snapshot": before})


@action("research.plan.update", ResearchPlanUpdateParams, domains=["research"], undoable=True, invert=_invert_update_plan)
def _action_update_plan(db, params: ResearchPlanUpdateParams, ctx: ActionContext):
    before = db.get(ResearchPlan, params.plan_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"Plan not found: {params.plan_id}")
    updated = update_plan_impl(
        db,
        params.plan_id,
        PlanUpdateRequest.model_validate(params.model_dump(exclude={"plan_id"})),
    )
    return updated, _research_spec(
        "updated",
        updated.id,
        before=before.model_dump(mode="json"),
        after=updated.model_dump(mode="json"),
    )


@action("research.plan.delete", ResearchPlanDeleteParams, domains=["research"], undoable=True, invert=lambda before, after, ctx: None if not before else ("research.plan.restore", {"snapshot": before}))
def _action_delete_plan(db, params: ResearchPlanDeleteParams, ctx: ActionContext):
    before = delete_plan_impl(db, params.plan_id)
    return {"status": "deleted", "id": params.plan_id}, _research_spec("deleted", params.plan_id, before=before, after={"id": params.plan_id})


@action("research.plan.restore", ResearchPlanRestoreParams, domains=["research"], undoable=False)
def _action_restore_plan(db, params: ResearchPlanRestoreParams, ctx: ActionContext):
    plan = restore_plan_impl(db, params.snapshot)
    return plan, _research_spec("updated", plan.id, after=plan.model_dump(mode="json"))


def _invert_create_task(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.task.delete", {"task_id": after["id"]})


@action("research.task.create", TaskCreateRequest, domains=["research"], undoable=True, invert=_invert_create_task)
def _action_create_task(db, params: TaskCreateRequest, ctx: ActionContext):
    task = create_task_impl(db, params)
    return task, _research_spec("created", task.id, after=task.model_dump(mode="json"))


@action("research.task.update", ResearchTaskUpdateParams, domains=["research"], undoable=True, invert=lambda before, after, ctx: None if not before else ("research.task.restore", {"snapshot": before}))
def _action_update_task(db, params: ResearchTaskUpdateParams, ctx: ActionContext):
    before = db.get(ResearchTask, params.task_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {params.task_id}")
    updated = update_task_impl(
        db,
        params.task_id,
        TaskUpdateRequest.model_validate(params.model_dump(exclude={"task_id"})),
    )
    return updated, _research_spec("updated", updated.id, before=before.model_dump(mode="json"), after=updated.model_dump(mode="json"))


@action("research.task.delete", ResearchTaskDeleteParams, domains=["research"], undoable=True, invert=lambda before, after, ctx: None if not before else ("research.task.restore", {"snapshot": before}))
def _action_delete_task(db, params: ResearchTaskDeleteParams, ctx: ActionContext):
    before = delete_task_impl(db, params.task_id)
    return {"status": "deleted", "id": params.task_id}, _research_spec("deleted", params.task_id, before=before, after={"id": params.task_id})


@action("research.task.restore", ResearchTaskRestoreParams, domains=["research"], undoable=False)
def _action_restore_task(db, params: ResearchTaskRestoreParams, ctx: ActionContext):
    task = restore_task_impl(db, params.snapshot)
    return task, _research_spec("updated", task.id, after=task.model_dump(mode="json"))


def _invert_create_step(before, after, ctx):
    if not after or not after.get("id"):
        return None
    return ("research.step.delete", {"step_id": after["id"]})


@action("research.step.create", StepCreateRequest, domains=["research"], undoable=True, invert=_invert_create_step)
def _action_create_step(db, params: StepCreateRequest, ctx: ActionContext):
    step = create_step_impl(db, params)
    return step, _research_spec("created", step.id, after=step.model_dump(mode="json"), mirrors_document=False)


@action("research.step.update", ResearchStepUpdateParams, domains=["research"], undoable=True, invert=lambda before, after, ctx: None if not before else ("research.step.restore", {"snapshot": before}))
def _action_update_step(db, params: ResearchStepUpdateParams, ctx: ActionContext):
    before = db.get(ResearchStep, params.step_id)
    if before is None:
        raise HTTPException(status_code=404, detail=f"Step not found: {params.step_id}")
    updated = update_step_impl(
        db,
        params.step_id,
        StepUpdateRequest.model_validate(params.model_dump(exclude={"step_id"})),
    )
    return updated, _research_spec("updated", updated.id, before=before.model_dump(mode="json"), after=updated.model_dump(mode="json"), mirrors_document=False)


@action("research.step.delete", ResearchStepDeleteParams, domains=["research"], undoable=True, invert=lambda before, after, ctx: None if not before else ("research.step.restore", {"snapshot": before}))
def _action_delete_step(db, params: ResearchStepDeleteParams, ctx: ActionContext):
    before = delete_step_impl(db, params.step_id)
    return {"status": "deleted", "id": params.step_id}, _research_spec("deleted", params.step_id, before=before, after={"id": params.step_id}, mirrors_document=False)


@action("research.step.restore", ResearchStepRestoreParams, domains=["research"], undoable=False)
def _action_restore_step(db, params: ResearchStepRestoreParams, ctx: ActionContext):
    step = restore_step_impl(db, params.snapshot)
    return step, _research_spec("updated", step.id, after=step.model_dump(mode="json"), mirrors_document=False)
