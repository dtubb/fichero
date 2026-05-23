"""
Fichero Data Models

Pydantic models for the Fichero data layer.

Core entities:
- Document: Source material (files, pages, chunks) - LangChain compatible
- Artifact: Output from any processing step - ML pipeline convention
- Workflow: A processing pipeline definition
- Run: An execution of a workflow
- Trace: LangChain/LangGraph debug data
- Note: User annotations
- Event: Audit trail and undo support

Usage:
    from fichero.models import Document, Workflow
    from fichero.db import db

    # Query
    folders = db.query(Document, doc_type=DocType.folder)
    doc = db.get(Document, "abc123")

    # Create and save
    doc = Document(name="letter.jpg", path="/path/letter.jpg")
    db.save(doc)

    # Delete
    db.delete(doc)
"""

from pydantic import BaseModel, Field, ConfigDict, computed_field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4
import base64

# Import ProviderType from providers module (single source of truth)
from fichero.providers import ProviderType

# Direct imports — knowledge_models has no dependency on this file.
from fichero.knowledge_models import (
    DocumentCitation,
    KnowledgeClaim,
    KnowledgeEntity,
)

# Forward refs — routes import from this file, so we can't import back. The
# route modules call model_rebuild() on their owning envelope at module end.
if TYPE_CHECKING:
    from fichero.api.routes.activity import ActivityResponse
    from fichero.api.routes.batch import BatchResponse
    from fichero.api.routes.kg_entity_curation import EntityAuditResponse


def _new_id() -> str:
    """Generate a new unique ID (32-char hex string from UUID v4)."""
    return uuid4().hex


# =============================================================================
# Enums
# =============================================================================


class DocType(str, Enum):
    """Type of document node in the hierarchy."""

    folder = "folder"  # Organizational grouping (can be nested at any level)
    group = "group"  # Logical document (letter = multiple pages)
    file = "file"  # Actual file (image, PDF, audio)
    page = "page"  # Page within a multi-page document
    chunk = "chunk"  # Region/segment within a page


class FileType(str, Enum):
    """Type of source file."""

    image = "image"  # jpg, png, tiff, webp
    pdf = "pdf"  # PDF documents
    audio = "audio"  # mp3, wav, m4a
    video = "video"  # mp4, mov
    text = "text"  # txt, md
    word = "word"  # doc
    docx = "docx"  # docx
    epub = "epub"  # ebooks
    spreadsheet = "spreadsheet"  # csv, xlsx, xls, ods
    presentation = "presentation"  # pptx, ppt
    other = "other"


class SourceAuthority(str, Enum):
    """How authoritative this source is for KG triangulation (#903).

    Weighted contribution to ``triangulation.support_count``:
    - primary:   1.0  — original archive document, primary research output
    - secondary: 0.6  — academic / journalistic citation of primary sources
    - tertiary:  0.3  — encyclopaedic / aggregate / textbook
    - unknown:   1.0  — default for un-tagged documents (treated as primary
                       to avoid silently down-weighting existing libraries
                       before the user has tagged anything)
    """

    primary = "primary"
    secondary = "secondary"
    tertiary = "tertiary"
    unknown = "unknown"


# Weight by SourceAuthority (#903). Module-level so triangulation,
# splink, and any future scorer share the same scale.
AUTHORITY_WEIGHTS: dict[str, float] = {
    "primary": 1.0,
    "secondary": 0.6,
    "tertiary": 0.3,
    "unknown": 1.0,
}


class Status(str, Enum):
    """Processing status."""

    pending = "pending"
    processing = "processing"
    active = "active"
    completed = "completed"
    failed = "failed"


class RunStatus(str, Enum):
    """Workflow run status."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# =============================================================================
# Document - Source Material (LangChain compatible)
# =============================================================================


class Document(BaseModel):
    """
    A node in the document hierarchy.

    Represents any organizational unit or file:
    - Collection: top-level archive/project
    - Folder: organizational grouping (box, series)
    - Group: logical document (a letter that spans 3 pages)
    - File: actual file (image, PDF, audio)
    - Page: page within a PDF
    - Chunk: region within a page (signature, stamp, paragraph)

    Hierarchy via parent_id:
        Collection > Folder > Group > File > Page > Chunk

    Compatible with LangChain's Document concept via page_content and metadata.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    parent_id: str | None = None

    # Type
    doc_type: DocType = DocType.file
    file_type: FileType | None = None

    # Identity
    name: str
    path: str | None = None  # File path (local or in library)

    # For pages/chunks
    sequence: int | None = None  # Page number or order
    bbox: tuple[int, int, int, int] | None = None  # x, y, width, height

    # Content (LangChain compatible)
    page_content: str | None = None

    # Extensible metadata - see properties below for common keys
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Source authority for KG weighting (#903). Defaults to ``unknown``
    # so existing libraries don't suddenly down-weight every claim
    # they emit; the user sets per-document via the inspector.
    source_authority: SourceAuthority = SourceAuthority.unknown

    # Bibliographic metadata (#908). Populated by the bibliography
    # extractor workflow tool (PyMuPDF for PDF metadata, LLM for
    # cover-page extraction, optional DOI lookup at #910). Used by
    # the citation renderer (#912) to emit BibTeX / Chicago / APA /
    # MLA. Stored as a dict because Document already lives in DuckDB
    # and adding a nested Pydantic model would require a migration
    # and a serializer — the renderer accepts a SourceMetadata
    # constructed on the fly from this dict at read-time.
    source_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Bibliographic metadata (SourceMetadata shape). See #908.",
    )

    # =========================================================================
    # #1123 attribution taxonomy — document-level provenance (Phase A)
    # =========================================================================
    # Stored as JSON dicts (not nested Pydantic models) for the same reason
    # source_metadata above is dict — Document lives in DuckDB and nested
    # Pydantic would require migration + custom serializer. The KG inspector
    # constructs typed ProvenanceStep / ImageProvenance models on the fly
    # at read time. Both default-empty so existing docs survive.
    provenance_chain: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Chain of custody as a list of ProvenanceStep dicts: "
            "'filed 1933, copied 1965, scanned 2019, accessed 2026'. "
            "Lets the inspector render lineage; queries by step.actor / "
            "step.date answer 'show me everything this scribe touched'."
        ),
    )
    image_provenance: dict[str, Any] | None = Field(
        default=None,
        description=(
            "For digitised images: photographer / capture_date / "
            "equipment / condition_notes. Separate from the broader "
            "provenance_chain because the same physical document can "
            "have multiple captures (initial scan + reshoot)."
        ),
    )

    # Processing state
    status: Status = Status.pending

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # User-defined order within parent folder. Set by /documents/reorder;
    # consumed by `SidebarItemBuilder.childOrder` Swift-side (lower =
    # earlier). Every document defaults to 0; once a folder is reordered,
    # its children get sequential values. Reorder-unaware folders tie at
    # 0 and fall through to name-based sort. Without this field declared
    # on the Pydantic model, the reorder endpoint's `doc.sort_order = i`
    # assignment is dropped silently by `model_dump()` (only declared
    # fields are serialized), so reorder never persists to DB.
    sort_order: int = 0

    # Case grouping: optional identifier to group documents into cases within
    # a folder (#1096). Catalogue tool groups documents by case_id and emits
    # one artifact per case instead of per folder.
    case_id: str | None = None

    # =========================================================================
    # Typed accessors for common metadata
    # =========================================================================

    def _metadata_value(self, key: str, default: Any = None) -> Any:
        """Read metadata values defensively for static analyzers and runtime safety."""
        metadata = self.__dict__.get("metadata")
        if not isinstance(metadata, dict):
            return default
        return metadata.get(key, default)

    @property
    def source_type(self) -> str:
        """Source type: 'local', 'iiif', 'url', 's3'."""
        return self._metadata_value("source_type", "local")

    @property
    def source_url(self) -> str | None:
        """Original URL if imported from remote source."""
        return self._metadata_value("source_url")

    @property
    def derived_from(self) -> str | None:
        """ID of document this was derived from (e.g., PDF → extracted page)."""
        return self._metadata_value("derived_from")

    @property
    def thumbnail_path(self) -> str | None:
        """Path to thumbnail image (package-relative).

        Returns the expected package-relative path.
        Use storage.get_thumbnail(doc, package_path) to check if it exists.
        """
        return self.expected_thumbnail_path

    @property
    def display_path(self) -> str | None:
        """Path to display-size image (package-relative).

        Returns the expected package-relative path.
        Use storage.get_display(doc, package_path) to check if it exists.
        """
        return self.expected_display_path

    @property
    def full_path(self) -> str | None:
        """Path to full-resolution file in library."""
        return self._metadata_value("full_path")

    @property
    def checksum(self) -> str | None:
        """File checksum (sha256)."""
        return self._metadata_value("checksum")

    @property
    def file_size(self) -> int | None:
        """File size in bytes."""
        return self._metadata_value("file_size")

    @property
    def width(self) -> int | None:
        """Image/video width in pixels."""
        return self._metadata_value("width")

    @property
    def height(self) -> int | None:
        """Image/video height in pixels."""
        return self._metadata_value("height")

    @property
    def duration(self) -> float | None:
        """Audio/video duration in seconds."""
        return self._metadata_value("duration")

    @property
    def page_count(self) -> int | None:
        """Number of pages (for PDFs)."""
        return self._metadata_value("page_count")

    @property
    def iiif_manifest(self) -> str | None:
        """IIIF manifest URL."""
        return self._metadata_value("iiif_manifest")

    @property
    def iiif_canvas_id(self) -> str | None:
        """IIIF canvas identifier."""
        return self._metadata_value("iiif_canvas_id")

    # =========================================================================
    # Storage paths (computed from storage module)
    # =========================================================================

    @computed_field
    @property
    def expected_thumbnail_path(self) -> str:
        """Expected thumbnail path relative to package (may not exist yet).

        Returns package-relative path for multi-library support:
        storage/thumbnails/{id[:2]}/{id}.jpg

        For actual file access, use storage.get_thumbnail(doc, package_path).
        """
        prefix = self.id[:2].lower()
        return f"storage/thumbnails/{prefix}/{self.id}.jpg"

    @computed_field
    @property
    def expected_display_path(self) -> str:
        """Expected display-size image path relative to package (may not exist yet).

        Returns package-relative path for multi-library support:
        storage/thumbnails/{id[:2]}/{id}_display.jpg

        For actual file access, use storage.get_display(doc, package_path).
        """
        prefix = self.id[:2].lower()
        return f"storage/thumbnails/{prefix}/{self.id}_display.jpg"

    @property
    def has_thumbnail(self) -> bool:
        """Check if thumbnail exists on disk.

        NOTE: In multi-library mode, this always returns False.
        Use storage.has_thumbnail(doc.id, package_path) instead.
        """
        # Cannot check existence without package_path in multi-library architecture
        return False

    @property
    def has_display(self) -> bool:
        """Check if display image exists on disk.

        NOTE: In multi-library mode, this always returns False.
        Use storage.has_display(doc.id, package_path) instead.
        """
        # Cannot check existence without package_path in multi-library architecture
        return False

    # =========================================================================
    # macOS bookmark support (for external file tracking)
    # =========================================================================

    @property
    def bookmark(self) -> bytes | None:
        """macOS security-scoped bookmark for external files.

        Bookmarks survive file moves/renames and work in sandboxed apps.
        Returns decoded bytes from base64-encoded metadata.
        """
        b64 = self._metadata_value("bookmark")
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception:
                return None
        return None

    def set_bookmark(self, bookmark_data: bytes) -> None:
        """Store bookmark in metadata (base64-encoded).

        Args:
            bookmark_data: Raw bookmark bytes from macOS API
        """
        self.metadata["bookmark"] = base64.b64encode(bookmark_data).decode()

    # =========================================================================
    # LangChain compatibility
    # =========================================================================

    def to_langchain(self):
        """Convert to LangChain Document."""
        from langchain_core.documents import Document as LCDocument

        return LCDocument(
            page_content=self.page_content or "",
            metadata={
                "id": self.id,
                "name": self.name,
                "doc_type": self.doc_type.value,
                "file_type": self.file_type.value if self.file_type else None,
                **self.metadata,
            },
        )


# =============================================================================
# Artifact - Processing Output (ML Pipeline convention)
# =============================================================================


class Artifact(BaseModel):
    """
    Output from any processing step - versioned and chainable.

    Artifacts are results from AI/ML processing:
    - Transcription (OCR text)
    - Entities (people, places, dates)
    - Summary
    - Translation
    - Grouping suggestions (which pages belong together)
    - Segmentation suggestions (regions within a page)

    Versioning: Multiple versions can exist for the same document.
    Chaining: One artifact can be derived from another (OCR → cleaned text).

    Structural artifacts (grouping, segmentation) suggest changes that
    become Document structure when user approves.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    document_id: str  # Which document this artifact is about

    # Versioning/chaining
    source_artifact_id: str | None = None  # Derived from this artifact
    version: int = 1

    # Type
    artifact_type: str  # "transcription", "entities", "grouping", "segmentation", etc.

    # Content (one or both)
    content: str | None = None  # Text output
    data: dict[str, Any] | None = None  # Structured output

    # Provenance
    run_id: str | None = None
    provider: str | None = None  # "qwen", "openai", "kreuzberg", "human"
    model: str | None = None  # "gpt-4o", "qwen-vl-max"
    step_name: str | None = None

    # Quality
    confidence: float | None = None
    reviewed: bool = False

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)

    # =========================================================================
    # Typed accessors for structured data
    # =========================================================================

    def get_segments(self) -> list[dict] | None:
        """Get segments from segmentation artifact."""
        if self.artifact_type == "segmentation" and self.data:
            return self.data.get("segments", [])
        return None

    def get_groups(self) -> list[dict] | None:
        """Get groups from grouping artifact."""
        if self.artifact_type == "grouping" and self.data:
            return self.data.get("groups", [])
        return None

    def get_entities(self) -> dict | None:
        """Get entities from entities artifact."""
        if self.artifact_type == "entities" and self.data:
            return self.data
        return None


# =============================================================================
# Workflow - Pipeline Definition
# =============================================================================


class Workflow(BaseModel):
    """
    A processing pipeline/recipe definition.

    Supports both step-based (legacy) and node-based (visual editor) formats.
    Node-based workflows use nodes and edges for visual pipeline creation.
    Step-based workflows maintain backward compatibility.

    Examples:
        - Legacy: [{"name": "transcribe", "tool": "transcribe", "provider": "qwen"}]
        - Visual: Nodes with ports connected by edges
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""

    # Organization
    folder_path: str = "/"  # Unix-style path: "/archive/letters"
    sort_order: int = 0  # User-defined order within folder
    is_template: bool = False
    is_system: bool = False
    tags: list[str] = []

    # Pipeline format choice
    format: str = "steps"  # "steps" (legacy) or "nodes" (visual editor)

    # Legacy pipeline steps (for backward compatibility)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    # Example:
    # [
    #     {"name": "transcribe", "tool": "transcribe", "provider": "qwen"},
    #     {"name": "entities", "tool": "extract_entities", "provider": "openai"},
    # ]

    # Visual workflow nodes and edges
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    # Node example:
    # {"id": "node1", "tool": "transcribe", "label": "Transcribe", "position_x": 100, "position_y": 200, ...}
    # Edge example:
    # {"source_node_id": "node1", "source_port_id": "output", "target_node_id": "node2", "target_port_id": "input"}

    # Default config for steps/nodes
    config: dict[str, Any] = Field(default_factory=dict)

    # LLM configuration
    provider: str = ""
    model: str = ""

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Run - Workflow Execution
# =============================================================================


class Run(BaseModel):
    """
    An execution of a workflow on documents.

    Tracks queue position, status, progress, retries, and costs.
    Each Run produces Artifacts and Traces.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    workflow_id: str
    document_ids: list[str] = Field(default_factory=list)

    # Queue
    priority: int = 0

    # Status
    status: RunStatus = RunStatus.queued
    current_step: str | None = None
    progress: float = 0.0  # 0.0 to 1.0

    # Retry
    attempt: int = 1
    max_attempts: int = 3
    error: str | None = None

    # Results
    artifact_ids: list[str] = Field(default_factory=list)

    # Cost tracking
    tokens_used: int = 0
    cost_usd: float = 0.0

    # Runtime config (overrides workflow defaults)
    config: dict[str, Any] = Field(default_factory=dict)

    # Timing
    queued_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


# =============================================================================
# Trace - LangChain/LangGraph Debug Data
# =============================================================================


class Trace(BaseModel):
    """
    Debug data from LangChain/LangGraph execution.

    Captures detailed information about each AI call:
    - What was called (model, provider)
    - Inputs and outputs
    - Timing and cost
    - Errors

    Used for debugging, cost tracking, and optimization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    run_id: str

    # Hierarchy (LangGraph has nested calls)
    parent_trace_id: str | None = None
    sequence: int = 0

    # What executed
    name: str  # Step name
    trace_type: str  # "llm", "chain", "tool", "retriever"

    # Status
    status: str = "running"  # "running", "completed", "failed"
    error: str | None = None

    # I/O
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None

    # Timing
    started_at: datetime = Field(default_factory=datetime.now)
    ended_at: datetime | None = None
    latency_ms: int | None = None

    # Cost tracking
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    # Extra
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Note - User Annotations
# =============================================================================


class Note(BaseModel):
    """
    User annotation on any object.

    Can be attached to Documents or Artifacts.
    Can have a position (bbox) for image annotations.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)

    # Target
    target_type: str  # "Document", "Artifact"
    target_id: str

    # Content
    content: str
    note_type: str = "comment"  # "comment", "question", "flag", "correction"

    # Position (for image annotations)
    bbox: tuple[int, int, int, int] | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Event - Audit Trail and Undo
# =============================================================================


class Event(BaseModel):
    """
    Audit log entry for tracking changes.

    Records what changed, before/after state, and context.
    Enables undo/redo and audit trails.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=datetime.now)

    # What changed
    event_type: str  # "document.create", "document.update", "artifact.create", etc.
    target_type: str  # "Document", "Artifact", etc.
    target_id: str

    # For undo
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    # Context
    source: str = "user"  # "user", "system", "workflow"
    run_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Provider - AI Service Provider
# =============================================================================

# Note: ProviderType is imported from fichero.providers (single source of truth)


class Provider(BaseModel):
    """
    AI service provider configuration.

    Stores provider metadata and connection info.
    API keys are stored separately in macOS Keychain.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str  # "OpenAI", "Qwen", "LM Studio"
    provider_type: ProviderType  # How to connect
    api_base: str | None = None  # Custom endpoint (for local/proxy)
    enabled: bool = True
    sort_order: int = 0

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Model - AI Model within a Provider
# =============================================================================


class Model(BaseModel):
    """
    AI model within a provider.

    Tracks capabilities and default status.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    provider_id: str  # FK to Provider
    name: str  # "GPT-4o", "Qwen VL Max"
    model_id: str  # Actual API identifier: "gpt-4o"
    capabilities: list[str] = Field(default_factory=list)  # ["vision", "transcription"]
    is_default: bool = False
    enabled: bool = True
    sort_order: int = 0

    # Cost tracking (per 1M tokens)
    input_cost: float | None = None
    output_cost: float | None = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# ProviderRef - Library's Reference to App-Wide Provider
# =============================================================================


class ProviderRef(BaseModel):
    """
    Library's reference to an app-wide provider.

    Tracks which providers this library uses, without duplicating
    the provider configuration (which is stored app-wide in app.duckdb).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    provider_id: str  # FK to Provider in app.duckdb
    enabled: bool = True  # Whether this provider is enabled for this library
    sort_order: int = 0  # Display order in this library

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Tool - Processing Tool Definition
# =============================================================================


class Tool(BaseModel):
    """
    Processing tool definition.

    Tools are Python modules that process documents.
    This model stores metadata and default configuration.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str  # "Transcribe"
    description: str = ""  # "Extract text from images using OCR"
    icon: str = "wrench"  # SF Symbol name
    module_path: str  # "fichero.tools.transcribe"
    enabled: bool = True
    sort_order: int = 0

    # Default configuration for this tool
    config: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# SavedSearch - User's Saved Search Query
# =============================================================================


class SavedSearch(BaseModel):
    """
    User's saved search query.

    Stores search parameters for quick access.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    query: str  # The search query text
    is_smart_search: bool = True  # Whether to use semantic search
    filters: dict[str, Any] | None = None  # Optional filter parameters
    search_type: str = "hybrid"  # Type of search: semantic, fulltext, hybrid
    sort_by: str = "relevance"  # Sort field
    sort_direction: str = "desc"  # Sort direction: "asc" or "desc"

    # Organization
    folder_path: str = "/"  # Unix-style path for organization
    sort_order: int = 0  # User-defined order within folder (position)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Conversation - Chat Conversation
# =============================================================================


class Conversation(BaseModel):
    """
    Chat conversation with message history.

    Stores chat conversation data for persistence.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    title: str  # Conversation title
    messages: list[dict] = Field(default_factory=list)  # Chat message history
    provider: str | None = None  # LLM provider used
    model: str | None = None  # LLM model used
    document_ids: list[str] = Field(default_factory=list)  # Documents used in RAG
    metadata: dict[str, Any] = Field(default_factory=dict)  # Additional metadata

    # Organization
    folder_path: str = "/"  # Unix-style path for organization
    sort_order: int = 0  # User-defined order within folder

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# MCP Server - Model Context Protocol Integration
# =============================================================================


class MCPServer(BaseModel):
    """MCP (Model Context Protocol) server configuration.

    MCP servers provide tools that can be used in workflows.
    Supports multiple transport types: stdio, HTTP, SSE, WebSocket.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str  # Unique server name (used as identifier)
    description: str = ""

    # Transport configuration
    transport: str  # "stdio", "sse", "http", or "websocket"

    # Transport-specific parameters (JSON-serialized)
    command: str | None = None  # For stdio: command to launch server
    args: list[str] = Field(default_factory=list)  # For stdio: command arguments
    env: dict[str, str] = Field(
        default_factory=dict
    )  # For stdio: environment variables
    url: str | None = None  # For http/sse/websocket: server URL
    headers: dict[str, str] = Field(
        default_factory=dict
    )  # For http/sse/websocket: HTTP headers

    # Tool configuration
    tool_name_prefix: bool = True  # Prefix tool names with server name
    enabled: bool = True  # Server enabled/disabled

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Library Snapshot
# =============================================================================


class SnapshotInitiatorType(str, Enum):
    """Who or what created the snapshot."""

    user = "user"
    ai = "ai"
    system = "system"


class LibrarySnapshot(BaseModel):
    """A point-in-time snapshot of a library database and its vectors.

    Snapshots are stored as Parquet exports of DuckDB tables plus a copy
    of the LanceDB vector directory. They are named with a timestamp and
    an optional reason, and can be restored to recover from bad AI runs
    or schema changes.

    Stored in:
        ~/Library/Application Support/com.fichero.fichero/snapshots/{library_name}/
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    library_path: str  # Path to the .fichero package
    library_name: str  # Display name of the library
    reason: str = ""  # Human-readable reason (e.g. "pre-AI run")
    initiator: SnapshotInitiatorType = SnapshotInitiatorType.user
    initiator_id: str | None = None  # agent_id or user_id if applicable
    run_id: str | None = None  # AI run_id if this was auto-created

    # Storage info
    snapshot_path: str  # Absolute path to snapshot directory
    duckdb_path: str  # Relative path to .duckdb.export Parquet files
    lance_path: str  # Relative path to LanceDB copy
    file_count: int = 0  # Number of files in snapshot
    duckdb_size_bytes: int = 0  # Size of DuckDB Parquet export
    lance_size_bytes: int = 0  # Size of LanceDB vector copy

    # Retention
    is_pinned: bool = False  # Pinned snapshots are not auto-deleted
    tags: list[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None  # Auto-delete after this time


# =============================================================================
# Library bootstrap (CLI / API)
# =============================================================================


class LibraryCreateRequest(BaseModel):
    """Request body for ``POST /api/library`` — bootstrap a fresh library.

    The path must end in ``.fichero`` and be inside one of the allowlist
    roots enforced by ``fichero.api.main._is_allowed_library_path``. The
    server expands ``~`` and validates before touching the filesystem.
    """

    path: str


class LibraryCreateResponse(BaseModel):
    """Response from ``POST /api/library``.

    ``created`` is False when the package already existed (idempotent
    re-creation is a no-op). ``tables_initialized`` is True when the
    DuckDB schema is in place — for both the freshly-created and the
    pre-existing case — so a CLI caller can immediately issue queries.
    ``path`` is the absolute, expanded path that was operated on.
    """

    path: str
    created: bool
    tables_initialized: bool


class HealthResponse(BaseModel):
    """Response from ``GET /api/health`` endpoint.

    If library path is provided in the request header, returns stats for that
    library. Otherwise, returns general backend health.
    """

    status: str
    library_path: str | None = None
    database: str | None = None
    document_count: int | None = None


class EntityContextResponse(BaseModel):
    """Response from CLI ``entity_context()`` aggregation.

    Counts of related entities, documents, and claims in the knowledge graph
    for a specific entity. Used for scoped entity context queries.
    """

    entity_id: str
    page_count: int
    doc_count: int
    folder_count: int
    claim_count: int


# =============================================================================
# Known Library Registry (for CLI library lifecycle #1131)
# =============================================================================


class KnownLibrary(BaseModel):
    """Persistent registry of known libraries.

    Stored in the backend database to support CLI operations like
    listing available libraries and switching between them (#1131).
    When a library is created via POST /api/library, it's auto-registered.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    path: str  # Absolute path to .fichero package (unique constraint)
    name: str | None = None  # Optional display name (defaults to basename)

    # Timestamps for CLI UX (sort by last_accessed for "recent" list)
    added_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)


class LibraryRegistryResponse(BaseModel):
    """Response from GET /api/registry — list all known libraries."""

    libraries: list[KnownLibrary]
    count: int


# =============================================================================
# List Envelope Response Models — standardize all GET list endpoints (#1075)
# =============================================================================


class ActionListResponse(BaseModel):
    """Standardized envelope for GET /api/actions list endpoints."""

    items: list[Any]  # Typically ActionResponse
    count: int


class ActivityListResponse(BaseModel):
    """Standardized envelope for GET /api/activity list endpoints."""

    items: list["ActivityResponse"]
    count: int


class BatchListResponse(BaseModel):
    """Standardized envelope for GET /api/batch list endpoints."""

    items: list["BatchResponse"]
    count: int


class ClaimListResponse(BaseModel):
    """Standardized envelope for GET /api/claims list endpoints."""

    items: list[KnowledgeClaim]
    count: int


class ClaimLinkListResponse(BaseModel):
    """Standardized envelope for claim links list endpoints."""

    items: list[Any]  # Typically KnowledgeClaimLink or KnowledgeClaim
    count: int


class DocumentListResponse(BaseModel):
    """Standardized envelope for document list endpoints (GET /api/documents,
    /collections, /roots, /{id}/children, /{id}/ancestors)."""

    items: list[Document]
    count: int


class RelatedDocumentListResponse(BaseModel):
    """Standardized envelope for GET /api/documents/{doc_id}/related.

    Items are RelatedDocumentsResponse rows (route-local type), so typed as
    Any here to avoid a models <- routes import cycle."""

    items: list[Any]
    count: int


class EntityListResponse(BaseModel):
    """Standardized envelope for GET /api/entities list endpoints."""

    items: list[KnowledgeEntity]
    count: int


class EntityCoOccurrenceListResponse(BaseModel):
    """Standardized envelope for GET /api/entities/{entity_id}/co-occurrence."""

    items: list[Any]  # Typically EntityCoOccurrence
    count: int


class EntityDocumentListResponse(BaseModel):
    """Standardized envelope for GET /api/entities/{entity_id}/documents."""

    items: list[Any]  # Typically EntityDocumentLink
    count: int


class TopEntityListResponse(BaseModel):
    """Standardized envelope for GET /api/entities/top."""

    items: list[Any]  # Typically TopEntityRow
    count: int


class ClaimCountsResponse(BaseModel):
    """Per-entity claim counts for badge display in the entity browser."""

    counts: dict[str, int]


class ArtifactTypeListResponse(BaseModel):
    """Standardized envelope for GET /api/artifacts/types."""

    items: list[str]
    count: int


class EntityAuditListResponse(BaseModel):
    """Standardized envelope for GET /api/kg-entity-curation/audit."""

    items: list["EntityAuditResponse"]
    count: int


class HermeneuticsListResponse(BaseModel):
    """Standardized envelope for hermeneutics list endpoints."""

    items: list[Any]  # Interpretations, Frameworks, Patterns, or HermeneuticCircleState
    count: int


class IntegrationListResponse(BaseModel):
    """Standardized envelope for GET /api/integrations list endpoints."""

    items: list[Any]  # Typically IntegrationInfo or IntegrationItem
    count: int


class KGInclusionListResponse(BaseModel):
    """Standardized envelope for GET /api/kg-inclusion list endpoints."""

    items: list[Any]  # Typically KnowledgeGraphInclusion
    count: int


class KGPredictionListResponse(BaseModel):
    """Standardized envelope for GET /api/kg-predictions list endpoints."""

    items: list[Any]  # Typically KnowledgePredictionRun
    count: int


class ContradictionEvidence(BaseModel):
    """Evidence of a contradiction between two claims.

    Lives here (not in routes/kg_claim_analysis.py) so ContradictionListResponse
    can declare `list[ContradictionEvidence]` instead of `list[Any]`. The
    untyped form caused OpenAPI to drop the schema entirely, breaking the
    Swift API client which references `Components.Schemas.ContradictionEvidence`.
    """

    claim_id: str
    contradicting_claim_id: str
    relation_type: str  # "outgoing" or "incoming"
    evidence: str | None
    link_quality: float
    source_documents: list[dict[str, Any]]
    claim_text: str
    contradicting_text: str


class ContradictionListResponse(BaseModel):
    """Standardized envelope for GET /api/kg-claim-analysis/{claim_id}/contradictions."""

    items: list[ContradictionEvidence]
    count: int


class MCPServerListResponse(BaseModel):
    """Standardized envelope for GET /api/mcp-servers list endpoints."""

    items: list[Any]  # Typically MCPServerResponse
    count: int


class MindPalaceListResponse(BaseModel):
    """Standardized envelope for mind palace spatial list endpoints."""

    items: list[Any]  # Rooms, Nodes, Connections, Stacks, or NativeNote
    count: int


class NoteListResponse(BaseModel):
    """Standardized envelope for GET /api/notes list endpoints."""

    items: list[Any]  # Typically Note
    count: int


class ProjectListResponse(BaseModel):
    """Standardized envelope for GET /api/projects list endpoints."""

    items: list[Any]  # Typically Project
    count: int


class ResearchCrudListResponse(BaseModel):
    """Standardized envelope for research CRUD list endpoints."""

    items: list[Any]  # Projects, Plans, Tasks, Steps
    count: int


class ResearchNotesListResponse(BaseModel):
    """Standardized envelope for research notes/sources/checklists list endpoints."""

    items: list[Any]  # ResearchNote, SearchSource, or ResearchChecklist
    count: int


class ScheduleListResponse(BaseModel):
    """Standardized envelope for GET /api/schedules list endpoints."""

    items: list[Any]  # Typically ScheduleResponse or ScheduleRunResponse
    count: int


class SourceListResponse(BaseModel):
    """Standardized envelope for GET /api/sources list endpoints."""

    items: list[Any]  # Typically SourceUpsertResponse
    count: int


class TriggerListResponse(BaseModel):
    """Standardized envelope for GET /api/triggers list endpoints."""

    items: list[Any]  # Typically TriggerResponse or TriggerExecutionResponse
    count: int


class AnnotationListResponse(BaseModel):
    """Standardized envelope for GET /api/annotations list endpoints."""

    items: list[Any]  # Typically Annotation
    count: int


class CitationListResponse(BaseModel):
    """Standardized envelope for GET /api/citations list endpoints."""

    items: list[DocumentCitation]
    count: int


class ClassificationListResponse(BaseModel):
    """Standardized envelope for GET /api/classifications list endpoints."""

    items: list[Any]  # Typically ClassificationValue
    count: int


class MutationListResponse(BaseModel):
    """Standardized envelope for mutation/triangulation list endpoints."""

    items: list[Any]  # Typically MutationRow or TripleSupportResponse
    count: int


class ReviewListResponse(BaseModel):
    """Standardized envelope for KG review list endpoints."""

    items: list[Any]  # Typically ReviewPairResponse
    count: int


class KGGraphListResponse(BaseModel):
    """Standardized envelope for KG graph analytics endpoints."""

    items: list[Any]  # Various graph analysis rows (CentralityRow, PageRankRow, etc.)
    count: int


class PykeenListResponse(BaseModel):
    """Standardized envelope for PyKEEN prediction endpoints."""

    items: list[Any]  # Typically StoredPrediction or TrainingResult
    count: int


class ProjectInclusionListResponse(BaseModel):
    """Standardized envelope for project inclusion list endpoints."""

    items: list[Any]  # Typically ProjectInclusion
    count: int


class HermesSuggestionListResponse(BaseModel):
    """Standardized envelope for hermeneutics suggestion endpoints."""

    items: list[Any]  # Typically HermesSuggestion
    count: int


# =============================================================================
# Convenience exports
# =============================================================================

__all__ = [
    # Enums
    "DocType",
    "FileType",
    "Status",
    "RunStatus",
    "ProviderType",
    # Models
    "Document",
    "Artifact",
    "Workflow",
    "Run",
    "Trace",
    "Note",
    "Event",
    # New config models
    "Provider",
    "Model",
    "ProviderRef",
    "Tool",
    "SavedSearch",
    "Conversation",
    "MCPServer",
    # Library bootstrap + API responses
    "LibraryCreateRequest",
    "LibraryCreateResponse",
    "HealthResponse",
    "EntityContextResponse",
    # Known library registry (#1131)
    "KnownLibrary",
    "LibraryRegistryResponse",
    # List envelope response models (#1075)
    "ActionListResponse",
    "ActivityListResponse",
    "BatchListResponse",
    "ClaimListResponse",
    "ClaimLinkListResponse",
    "DocumentListResponse",
    "EntityListResponse",
    "EntityCoOccurrenceListResponse",
    "EntityDocumentListResponse",
    "EntityAuditListResponse",
    "ClaimCountsResponse",
    "HermeneuticsListResponse",
    "IntegrationListResponse",
    "KGInclusionListResponse",
    "KGPredictionListResponse",
    "ContradictionEvidence",
    "ContradictionListResponse",
    "MCPServerListResponse",
    "MindPalaceListResponse",
    "NoteListResponse",
    "ProjectListResponse",
    "ResearchCrudListResponse",
    "ResearchNotesListResponse",
    "ScheduleListResponse",
    "SourceListResponse",
    "TriggerListResponse",
]
