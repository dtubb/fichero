"""Agent Research models for 0.0.2 Layer 0 — systematic discovery and exploration."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


def _new_id() -> str:
    return uuid4().hex


class ResearchStatus(str, Enum):
    """Lifecycle state of research items."""

    draft = "draft"
    active = "active"
    in_progress = "in_progress"
    paused = "paused"
    complete = "complete"
    archived = "archived"


class ResearchResult(str, Enum):
    """Outcome of research execution."""

    pending = "pending"
    success = "success"
    partial = "partial"
    failed = "failed"
    blocked = "blocked"


class StepType(str, Enum):
    """Types of research actions."""

    web_search = "web_search"
    browser_navigate = "browser_navigate"
    document_fetch = "document_fetch"
    note_create = "note_create"
    claim_extract = "claim_extract"
    verify_source = "verify_source"


class SourceType(str, Enum):
    """Categories of searchable sources."""

    url = "url"
    folder = "folder"
    database = "database"
    api = "api"
    library = "library"


class NoteType(str, Enum):
    """Types of research observations."""

    observation = "observation"
    hypothesis = "hypothesis"
    question = "question"
    finding = "finding"
    contradiction = "contradiction"


class CheckItemStatus(str, Enum):
    """Status of checklist items."""

    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"
    blocked = "blocked"
    waived = "waived"


class ResearchProject(BaseModel):
    """Top-level research initiative.

    A project represents a complete research endeavor with goals,
    scope, and deliverables. It contains plans, tasks, and findings.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    research_question: str = ""
    goals: list[str] = Field(default_factory=list)
    scope_notes: str = ""
    status: ResearchStatus = ResearchStatus.draft
    owner_id: str = "user"  # agent_id or "user"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchPlan(BaseModel):
    """Phased approach to research goals.

    A plan breaks down a project into strategic phases with
    objectives and success criteria for each phase.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    name: str
    description: str = ""
    phase_number: int = 1
    objectives: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # plan_ids
    status: ResearchStatus = ResearchStatus.draft
    due_date: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchTask(BaseModel):
    """Concrete unit of research work.

    A task represents a specific deliverable or investigation
    within a plan. It contains steps to execute.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    plan_id: str
    project_id: str
    name: str
    description: str = ""
    task_number: int = 1
    priority: int = Field(default=1, ge=1, le=5)  # 1 = highest
    estimated_hours: float | None = None
    assigned_to: str = "user"  # agent_id or "user"
    status: ResearchStatus = ResearchStatus.draft
    dependencies: list[str] = Field(default_factory=list)  # task_ids
    result: ResearchResult = ResearchResult.pending
    result_notes: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchStep(BaseModel):
    """Executable search or analysis action.

    A step is the smallest unit of work in the research system.
    It represents a single action like a web search or document fetch.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    task_id: str
    plan_id: str
    project_id: str
    step_number: int = 1
    step_type: StepType
    name: str = ""
    description: str = ""
    # Configuration based on step_type
    query: str | None = None  # for web_search
    url: str | None = None  # for browser_navigate, document_fetch
    target_source_id: str | None = None  # for claim_extract
    notes: str = ""
    status: ResearchStatus = ResearchStatus.draft
    result: ResearchResult = ResearchResult.pending
    result_data: dict = Field(default_factory=dict)  # execution output
    error_message: str | None = None
    execution_time_ms: int | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchSource(BaseModel):
    """Curated source for research.

    A source represents a searchable location or collection,
    such as a URL, folder, database, or API endpoint.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    name: str
    description: str = ""
    source_type: SourceType
    location: str  # URL path, folder path, API endpoint
    credentials: dict = Field(default_factory=dict)  # encrypted or token ref
    search_scope: str = ""  # e.g., "full", "title-only", "metadata"
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    last_searched: datetime | None = None
    findings_count: int = 0
    status: ResearchStatus = ResearchStatus.active
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchNote(BaseModel):
    """Observation or finding from research.

    Notes capture insights, observations, hypotheses, and findings
    discovered during research execution.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    plan_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    note_type: NoteType
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)  # linked sources
    claim_ids: list[str] = Field(default_factory=list)  # linked claims
    author_id: str = "user"  # agent_id or "user"
    is_key_finding: bool = False
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ResearchChecklistItem(BaseModel):
    """Verification item for research quality.

    Checklist items ensure research coverage and rigor
    by tracking required verifications and reviews.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    task_id: str | None = None
    step_id: str | None = None
    description: str
    category: str = ""  # e.g., "source_verification", "claim_validation"
    status: CheckItemStatus = CheckItemStatus.pending
    verified_by: str | None = None
    verified_at: datetime | None = None
    verification_notes: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WebSearchResult(BaseModel):
    """Result from web search execution."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    url: str
    title: str
    snippet: str
    source: str  # search engine or database
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    fetched: bool = False
    document_id: str | None = None  # if fetched as Source


class BrowserAction(BaseModel):
    """Browser automation action record."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    step_id: str
    action_type: str  # navigate, click, scroll, extract
    url: str | None = None
    selector: str | None = None
    extracted_text: str | None = None
    success: bool = True
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)
