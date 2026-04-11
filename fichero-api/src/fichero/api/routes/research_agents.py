"""Research Agents API routes (dev tier, Layer 0 — Agent Research)."""

import ipaddress
import re
import socket
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.research_models import (
    BrowserNavigateRequest,
    BrowserNavigateResponse,
    ChecklistItem,
    DocumentFetchRequest,
    DocumentFetchResponse,
    PlanStatus,
    ProjectStatus,
    ResearchChecklist,
    ResearchNote,
    ResearchNoteType,
    ResearchPlan,
    ResearchProject,
    ResearchStep,
    ResearchTask,
    SearchSource,
    SearchSourceType,
    StepStatus,
    StepTool,
    TaskStatus,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD
# ─────────────────────────────────────────────────────────────────────────────


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


@router.get("/projects", response_model=list[ResearchProject])
async def list_projects(
    status: ProjectStatus | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchProject]:
    projects = db.query(ResearchProject)
    if status is not None:
        projects = [p for p in projects if p.status == status]
    return sorted(projects, key=lambda p: p.created_at, reverse=True)


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
) -> dict[str, str]:
    project = db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    db.delete(project)
    return {"status": "deleted", "id": project_id}


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


# 仰制


@router.get("/projects/{project_id}/plans", response_model=list[ResearchPlan])
async def list_plans(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> list[ResearchPlan]:
    plans = db.query(ResearchPlan, project_id=project_id)
    return sorted(plans, key=lambda p: p.order_index)


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


@router.get("/plans/{plan_id}/tasks", response_model=list[ResearchTask])
async def list_tasks(
    plan_id: str,
    db: Database = Depends(get_library_database),
) -> list[ResearchTask]:
    tasks = db.query(ResearchTask, plan_id=plan_id)
    return sorted(tasks, key=lambda t: (t.priority, t.created_at))


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


@router.get("/tasks/{task_id}/steps", response_model=list[ResearchStep])
async def list_steps(
    task_id: str,
    db: Database = Depends(get_library_database),
) -> list[ResearchStep]:
    steps = db.query(ResearchStep, task_id=task_id)
    return sorted(steps, key=lambda s: s.order_index)


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


# ─────────────────────────────────────────────────────────────────────────────
# Search Sources
# ─────────────────────────────────────────────────────────────────────────────


class SearchSourceCreateRequest(BaseModel):
    project_id: str
    source_type: SearchSourceType
    label: str
    url: str | None = None
    path: str | None = None
    description: str = ""
    access_status: str = "public"
    reliability: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/sources", response_model=SearchSource)
async def create_search_source(
    request: SearchSourceCreateRequest,
    db: Database = Depends(get_library_database),
) -> SearchSource:
    source = SearchSource(
        project_id=request.project_id,
        source_type=request.source_type,
        label=request.label,
        url=request.url,
        path=request.path,
        description=request.description,
        access_status=request.access_status,
        reliability=request.reliability,
        metadata=request.metadata,
    )
    db.save(source)
    return source


@router.get("/projects/{project_id}/sources", response_model=list[SearchSource])
async def list_search_sources(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> list[SearchSource]:
    return db.query(SearchSource, project_id=project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Research Notes
# ─────────────────────────────────────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    note_type: ResearchNoteType = ResearchNoteType.observation
    content: str
    tags: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    linked_claim_ids: list[str] = Field(default_factory=list)
    created_by: str = "human"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NoteUpdateRequest(BaseModel):
    content: str | None = None
    note_type: ResearchNoteType | None = None
    tags: list[str] | None = None
    linked_source_ids: list[str] | None = None
    linked_claim_ids: list[str] | None = None
    metadata: dict[str, Any] | None = None


@router.post("/notes", response_model=ResearchNote)
async def create_note(
    request: NoteCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchNote:
    note = ResearchNote(
        project_id=request.project_id,
        task_id=request.task_id,
        step_id=request.step_id,
        note_type=request.note_type,
        content=request.content,
        tags=request.tags,
        linked_source_ids=request.linked_source_ids,
        linked_claim_ids=request.linked_claim_ids,
        created_by=request.created_by,
        metadata=request.metadata,
    )
    db.save(note)
    return note


@router.get("/projects/{project_id}/notes", response_model=list[ResearchNote])
async def list_notes(
    project_id: str,
    task_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[ResearchNote]:
    notes = db.query(ResearchNote, project_id=project_id)
    if task_id is not None:
        notes = [n for n in notes if n.task_id == task_id]
    return sorted(notes, key=lambda n: n.created_at, reverse=True)


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
    if request.content is not None:
        note.content = request.content
    if request.note_type is not None:
        note.note_type = request.note_type
    if request.tags is not None:
        note.tags = request.tags
    if request.linked_source_ids is not None:
        note.linked_source_ids = request.linked_source_ids
    if request.linked_claim_ids is not None:
        note.linked_claim_ids = request.linked_claim_ids
    if request.metadata is not None:
        note.metadata = request.metadata
    note.updated_at = datetime.now()
    db.save(note)
    return note


# ─────────────────────────────────────────────────────────────────────────────
# Research Checklists
# ─────────────────────────────────────────────────────────────────────────────


class ChecklistCreateRequest(BaseModel):
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    title: str
    items: list[ChecklistItem] = Field(default_factory=list)
    created_by: str = "human"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChecklistItemToggleRequest(BaseModel):
    checked: bool
    notes: str = ""


@router.post("/checklists", response_model=ResearchChecklist)
async def create_checklist(
    request: ChecklistCreateRequest,
    db: Database = Depends(get_library_database),
) -> ResearchChecklist:
    checklist = ResearchChecklist(
        project_id=request.project_id,
        task_id=request.task_id,
        step_id=request.step_id,
        title=request.title,
        items=request.items,
        created_by=request.created_by,
        metadata=request.metadata,
    )
    db.save(checklist)
    return checklist


@router.get("/projects/{project_id}/checklists", response_model=list[ResearchChecklist])
async def list_checklists(
    project_id: str,
    db: Database = Depends(get_library_database),
) -> list[ResearchChecklist]:
    return db.query(ResearchChecklist, project_id=project_id)


@router.patch(
    "/checklists/{checklist_id}/items/{item_id}", response_model=ResearchChecklist
)
async def toggle_checklist_item(
    checklist_id: str,
    item_id: str,
    request: ChecklistItemToggleRequest,
    db: Database = Depends(get_library_database),
) -> ResearchChecklist:
    checklist = db.get(ResearchChecklist, checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404, detail=f"Checklist not found: {checklist_id}"
        )
    for item in checklist.items:
        if item.id == item_id:
            item.checked = request.checked
            item.notes = request.notes
            if request.checked:
                item.checked_at = datetime.now()
                item.checked_by = "human"
            break
    checklist.updated_at = datetime.now()
    db.save(checklist)
    return checklist


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Web Search
# ─────────────────────────────────────────────────────────────────────────────

# URL schemes that are never allowed in sandboxed requests
_SANDBOX_BLOCKED_SCHEMES = frozenset(
    [
        "file",
        "ftp",
        "ftps",
        "s3",
        "smb",
        "ssh",
        "telnet",
        "gopher",
        "ldap",
        "ldaps",
    ]
)

# Internal/private IP networks that should be blocked
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),       # private A
    ipaddress.ip_network("172.16.0.0/12"),    # private B
    ipaddress.ip_network("192.168.0.0/16"),   # private C
    ipaddress.ip_network("169.254.0.0/16"),   # link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),        # current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]

# Cloud metadata endpoints
_CLOUD_METADATA_HOSTS = frozenset(
    [
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.googleapis.com",
        "169.254.170.2",
        "169.254.170.1",
    ]
)


def _is_internal_ip(hostname: str | None) -> bool:
    """Check if a hostname or IP is internal/private."""
    if not hostname:
        return False
    
    if hostname.lower() in _CLOUD_METADATA_HOSTS:
        return True
    
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return True
        return False
    except ValueError:
        pass
    
    try:
        addrs = socket.getaddrinfo(hostname, None)
        for addr_info in addrs:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for network in _BLOCKED_NETWORKS:
                    if ip in network:
                        return True
            except ValueError:
                continue
    except (socket.gaierror, socket.herror):
        pass
    
    return False


def _is_safe_url(url: str, allow_userinfo: bool = False) -> tuple[bool, str]:
    """Comprehensive URL safety check for sandboxed requests."""
    if not url:
        return False, "URL is empty"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    scheme = parsed.scheme.lower()
    if not scheme:
        return False, "URL must have a scheme (http:// or https://)"

    if scheme in _SANDBOX_BLOCKED_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' is not allowed"

    if scheme not in ("http", "https"):
        return False, f"URL scheme '{parsed.scheme}' is not allowed (only http/https)"

    if not allow_userinfo and (parsed.username or parsed.password):
        return False, "URLs with embedded credentials are not allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must have a hostname"

    if _is_internal_ip(hostname):
        return False, f"Internal addresses are not allowed: {hostname}"

    if re.match(r"^0[xX][0-9a-fA-F]+", hostname) or re.match(r"^\d+$", hostname):
        if _is_internal_ip(hostname):
            return False, "Numeric IP addresses are not allowed"

    # Basic traversal hardening for path confusion vectors.
    if "/../" in parsed.path or parsed.path.endswith("/.."):
        return False, "Path traversal patterns are not allowed"

    # Disallow blocked schemes in query/fragment payloads used as redirect gadgets.
    query_and_fragment = f"{parsed.query} {parsed.fragment}".lower()
    if any(f"{blocked}://" in query_and_fragment for blocked in _SANDBOX_BLOCKED_SCHEMES):
        return False, "Embedded blocked URL schemes are not allowed"

    return True, ""


def _is_sandbox_violation(url: str) -> bool:
    """Check if URL violates sandbox constraints."""
    is_safe, _ = _is_safe_url(url)
    return not is_safe


async def _safe_http_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    max_redirects: int = 5,
) -> httpx.Response:
    """GET with explicit redirect validation to prevent SSRF redirect bypass."""
    current_url = url
    for _ in range(max_redirects + 1):
        is_safe, error = _is_safe_url(current_url)
        if not is_safe:
            raise HTTPException(status_code=400, detail=f"URL not allowed: {error}")

        response = await client.get(
            current_url,
            headers=headers,
            params=params,
            follow_redirects=False,
        )

        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise HTTPException(status_code=400, detail="Redirect missing location")
            next_url = urljoin(str(current_url), location)
            is_safe, error = _is_safe_url(next_url)
            if not is_safe:
                raise HTTPException(
                    status_code=400,
                    detail=f"Redirect target not allowed: {error}",
                )
            current_url = next_url
            params = None
            continue

        response.raise_for_status()
        return response

    raise HTTPException(status_code=400, detail="Too many redirects")


@router.post("/tools/web-search", response_model=WebSearchResponse)
async def execute_web_search(
    request: WebSearchRequest,
) -> WebSearchResponse:
    """Execute a web search using httpx (sandboxed — no filesystem/CLI escape)."""
    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 2 characters",
        )

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(request.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as client:
            # DuckDuckGo HTML lite (no API key needed)
            params = {
                "q": request.query,
                "kl": request.language or "en-us",
            }
            resp = await _safe_http_get(
                client,
                "https://html.duckduckgo.com/html/",
                params=params,
            )
            html = resp.text if isinstance(resp.text, str) else str(resp.text)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Web search timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Search provider error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Parse DuckDuckGo HTML results (simple regex, no external parser)
    results: list[WebSearchResult] = []
    import re

    # DuckDuckGo HTML format: <a href="..." class="result__a">Title</a>
    # followed by <a href="..." class="result__url">url</a> and <p class="result__snippet">snippet</p>
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__url"[^>]*>(.*?)</a>.*?'
        r'<p[^>]+class="result__snippet"[^>]*>(.*?)</p>',
        re.DOTALL | re.IGNORECASE,
    )
    for i, match in enumerate(link_pattern.finditer(html)):
        if i >= request.max_results:
            break
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        url = match.group(2).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        # Validate search results using comprehensive security check
        if url:
            is_safe, _ = _is_safe_url(url)
            if is_safe:
                results.append(
                    WebSearchResult(
                        title=title[:500] if title else "",
                        url=url,
                        snippet=snippet[:1000] if snippet else "",
                    )
                )

    return WebSearchResponse(
        query=request.query,
        results=results,
        total_results=len(results),
        execution_time_ms=elapsed_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Browser Navigate
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/browser-navigate", response_model=BrowserNavigateResponse)
async def execute_browser_navigate(
    request: BrowserNavigateRequest,
) -> BrowserNavigateResponse:
    """Navigate to a URL and extract content (sandboxed — no filesystem/CLI escape)."""
    if _is_sandbox_violation(request.url):
        raise HTTPException(
            status_code=400,
            detail="URL scheme not allowed in sandboxed browser",
        )
    
    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = _is_safe_url(request.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {error_msg}")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(request.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=10),
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = await _safe_http_get(client, request.url, headers=headers)
            html_content = resp.text if isinstance(resp.text, str) else str(resp.text)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Browser navigation timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Navigation error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Browser navigation failed: {str(e)}"
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Extract title and links
    import re

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL
    )
    title = title_match.group(1).strip() if title_match else None
    title = re.sub(r"<[^>]+>", "", title or "").strip()

    # Extract href links
    link_pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
    links: list[str] = []
    for match in link_pattern.finditer(html_content):
        href = match.group(1)
        # Validate extracted links using comprehensive security check
        if href.startswith("http"):
            is_safe, _ = _is_safe_url(href)
            if is_safe:
                links.append(href)

    return BrowserNavigateResponse(
        url=request.url,
        title=title[:500] if title else None,
        html_content=html_content[:50000]
        if html_content
        else None,  # truncate large pages
        screenshot_base64=None,  # screenshot not yet implemented
        extracted_links=links[:100],  # limit links
        execution_time_ms=elapsed_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Document Fetch
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/document-fetch", response_model=DocumentFetchResponse)
async def execute_document_fetch(
    request: DocumentFetchRequest,
    db: Database = Depends(get_library_database),
) -> DocumentFetchResponse:
    """Fetch a document URL and optionally save as Layer 1 Source (sandboxed)."""
    if _is_sandbox_violation(request.url):
        raise HTTPException(
            status_code=400,
            detail="URL scheme not allowed in sandboxed fetch",
        )
    
    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = _is_safe_url(request.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {error_msg}")

    from fichero.models import Document, DocType

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                ),
            }
            resp = await _safe_http_get(client, request.url, headers=headers)
            content = resp.text if isinstance(resp.text, str) else str(resp.text)
            content_type = str(resp.headers.get("content-type", "text/plain"))
            # Extract title from HTML or use URL
            if "text/html" in content_type:
                import re

                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
                )
                title = title_match.group(1).strip() if title_match else request.url
                title = re.sub(r"<[^>]+>", "", title).strip()
            else:
                title = request.url.split("/")[-1]

    except HTTPException:
        raise
    except httpx.TimeoutException:
        return DocumentFetchResponse(
            url=request.url,
            title=None,
            content=None,
            content_type=None,
            source_id=None,
            success=False,
            error="Fetch timed out",
        )
    except Exception as e:
        return DocumentFetchResponse(
            url=request.url,
            title=None,
            content=None,
            content_type=None,
            source_id=None,
            success=False,
            error=f"Fetch failed: {str(e)}",
        )

    # Optionally create a Layer 1 Source document
    source_id = None
    if request.create_as_source:
        try:
            doc = Document(
                name=title[:255] if title else request.url,
                doc_type=DocType.web_capture,
                path=request.url,
                page_content=content[:50000],  # store truncated content
                metadata={
                    "source_url": request.url,
                    "content_type": content_type,
                    "research_project_id": request.project_id,
                    "fetched_at": datetime.now().isoformat(),
                    **request.metadata,
                },
            )
            db.save(doc)
            source_id = doc.id
        except Exception:
            # Don't fail the fetch if save fails
            pass

    return DocumentFetchResponse(
        url=request.url,
        title=title[:500] if title else None,
        content=content[:50000] if content else None,
        content_type=content_type,
        source_id=source_id,
        success=True,
        error=None,
    )
