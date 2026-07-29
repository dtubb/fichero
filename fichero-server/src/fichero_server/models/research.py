"""Research agent models for 0.0.2 Layer 0 — Agent Research Infrastructure."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


def _new_id() -> str:
    return uuid4().hex


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class PlanStatus(str, Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"
    cancelled = "cancelled"


class StepStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class StepTool(str, Enum):
    web_search = "web_search"
    browser_navigate = "browser_navigate"
    document_fetch = "document_fetch"
    local_search = "local_search"


class SearchSourceType(str, Enum):
    url = "url"
    folder = "folder"
    database = "database"
    api = "api"


class ResearchNoteType(str, Enum):
    observation = "observation"
    finding = "finding"
    question = "question"
    hypothesis = "hypothesis"
    synthesis = "synthesis"


class ResearchProject(BaseModel):
    """Top-level research initiative."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.active
    created_by: str = "human"
    library_destination_folder_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchPlan(BaseModel):
    """Phased approach to project goals."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    name: str
    description: str = ""
    status: PlanStatus = PlanStatus.draft
    order_index: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchTask(BaseModel):
    """Concrete unit of work within a plan."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    plan_id: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.pending
    priority: int = 0  # lower = higher priority
    assigned_to: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class StepConfig(BaseModel):
    """Configuration for a research step."""

    query: str | None = None  # web search query
    url: str | None = None  # browser navigate URL
    max_results: int = 10  # web search results limit
    timeout_seconds: int = 30
    headers: dict = Field(default_factory=dict)  # custom HTTP headers
    wait_for_selectors: list[str] = Field(default_factory=list)  # browser selectors


class ResearchStep(BaseModel):
    """Executable search action within a task."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    task_id: str
    tool: StepTool
    label: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.pending
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    order_index: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class SearchSource(BaseModel):
    """Curated search target for a project."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    source_type: SearchSourceType
    label: str
    url: str | None = None  # for URL type
    path: str | None = None  # for folder type
    description: str = ""
    # Curation metadata
    access_status: str = "public"  # public, restricted, private
    reliability: float = 0.5  # 0-1 reliability rating
    scraped_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ResearchNote(BaseModel):
    """Observation or finding recorded during research."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    note_type: ResearchNoteType = ResearchNoteType.observation
    content: str
    tags: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)  # SearchSource IDs
    linked_claim_ids: list[str] = Field(default_factory=list)  # KnowledgeClaim IDs
    created_by: str = "human"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ChecklistItem(BaseModel):
    """Single verification item within a checklist."""

    id: str = Field(default_factory=_new_id)
    label: str
    checked: bool = False
    checked_at: datetime | None = None
    checked_by: str | None = None
    notes: str = ""


class ResearchChecklist(BaseModel):
    """Verification checklist linked to a task or step."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    title: str
    items: list[ChecklistItem] = Field(default_factory=list)
    created_by: str = "human"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed tool request/response models
# ─────────────────────────────────────────────────────────────────────────────


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=10, ge=1, le=50)
    source_ids: list[str] = Field(
        default_factory=list
    )  # optional SearchSource filtering
    language: str | None = None
    timeout_seconds: int = Field(default=30, ge=5, le=120)


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source_name: str | None = None
    published_date: str | None = None
    relevance_score: float = 0.0


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult]
    total_results: int
    execution_time_ms: int


class BrowserNavigateRequest(BaseModel):
    url: str
    wait_for_selectors: list[str] = Field(default_factory=list)
    screenshot: bool = False
    timeout_seconds: int = Field(default=30, ge=5, le=120)


class BrowserNavigateResponse(BaseModel):
    url: str
    title: str | None = None
    html_content: str | None = None  # extracted page content
    screenshot_base64: str | None = None
    extracted_links: list[str] = Field(default_factory=list)
    execution_time_ms: int


class DocumentFetchRequest(BaseModel):
    url: str
    project_id: str
    create_as_source: bool = True  # if True, creates Layer 1 Source
    metadata: dict = Field(default_factory=dict)


class DocumentFetchResponse(BaseModel):
    url: str
    title: str | None = None
    content: str | None = None
    content_type: str | None = None
    source_id: str | None = None  # Layer 1 Source ID if created
    success: bool
    error: str | None = None


class BrowserSaveRequest(BaseModel):
    url: str
    project_id: str
    suggested_name: str | None = None  # override filename; derived from URL if absent
    parent_folder_id: str | None = None  # library folder to save into
    metadata: dict = Field(default_factory=dict)


class BrowserSaveResponse(BaseModel):
    url: str
    document_id: str | None = None
    document_name: str | None = None
    file_path: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    success: bool
    error: str | None = None
