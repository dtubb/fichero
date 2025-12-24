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
    collections = db.query(Document, doc_type=DocType.collection)
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
from pathlib import Path
from typing import Any
from uuid import uuid4
import base64


def _new_id() -> str:
    """Generate a new unique ID (32-char hex string from UUID v4)."""
    return uuid4().hex


# =============================================================================
# Enums
# =============================================================================

class DocType(str, Enum):
    """Type of document node in the hierarchy."""
    collection = "collection"  # Top-level project/archive
    folder = "folder"          # Organizational grouping (box, series)
    group = "group"            # Logical document (letter = multiple pages)
    file = "file"              # Actual file (image, PDF, audio)
    page = "page"              # Page within a multi-page document
    chunk = "chunk"            # Region/segment within a page


class FileType(str, Enum):
    """Type of source file."""
    image = "image"    # jpg, png, tiff, webp
    pdf = "pdf"        # PDF documents
    audio = "audio"    # mp3, wav, m4a
    video = "video"    # mp4, mov
    text = "text"      # txt, md
    word = "word"      # docx
    epub = "epub"      # ebooks
    other = "other"


class Status(str, Enum):
    """Processing status."""
    pending = "pending"
    processing = "processing"
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
    model_config = ConfigDict(from_attributes=True)

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

    # Processing state
    status: Status = Status.pending

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # =========================================================================
    # Typed accessors for common metadata
    # =========================================================================

    @property
    def source_type(self) -> str:
        """Source type: 'local', 'iiif', 'url', 's3'."""
        return self.metadata.get("source_type", "local")

    @property
    def source_url(self) -> str | None:
        """Original URL if imported from remote source."""
        return self.metadata.get("source_url")

    @property
    def derived_from(self) -> str | None:
        """ID of document this was derived from (e.g., PDF → extracted page)."""
        return self.metadata.get("derived_from")

    @property
    def thumbnail_path(self) -> str | None:
        """Path to thumbnail image.

        Returns the computed storage path if it exists,
        otherwise falls back to metadata.
        """
        # Prefer computed path (storage module) if file exists
        if self.expected_thumbnail_path.exists():
            return str(self.expected_thumbnail_path)
        # Fallback to metadata
        return self.metadata.get("thumbnail_path")

    @property
    def display_path(self) -> str | None:
        """Path to display-size image.

        Returns the computed storage path if it exists,
        otherwise falls back to metadata.
        """
        if self.expected_display_path.exists():
            return str(self.expected_display_path)
        return self.metadata.get("display_path")

    @property
    def full_path(self) -> str | None:
        """Path to full-resolution file in library."""
        return self.metadata.get("full_path")

    @property
    def checksum(self) -> str | None:
        """File checksum (sha256)."""
        return self.metadata.get("checksum")

    @property
    def file_size(self) -> int | None:
        """File size in bytes."""
        return self.metadata.get("file_size")

    @property
    def width(self) -> int | None:
        """Image/video width in pixels."""
        return self.metadata.get("width")

    @property
    def height(self) -> int | None:
        """Image/video height in pixels."""
        return self.metadata.get("height")

    @property
    def duration(self) -> float | None:
        """Audio/video duration in seconds."""
        return self.metadata.get("duration")

    @property
    def page_count(self) -> int | None:
        """Number of pages (for PDFs)."""
        return self.metadata.get("page_count")

    @property
    def iiif_manifest(self) -> str | None:
        """IIIF manifest URL."""
        return self.metadata.get("iiif_manifest")

    @property
    def iiif_canvas_id(self) -> str | None:
        """IIIF canvas identifier."""
        return self.metadata.get("iiif_canvas_id")

    # =========================================================================
    # Storage paths (computed from storage module)
    # =========================================================================

    @computed_field
    @property
    def expected_thumbnail_path(self) -> Path:
        """Expected thumbnail path (may not exist yet).

        Uses sharded storage for scale:
        thumbnails/{id[:2]}/{id}.jpg
        """
        from fichero.storage import settings
        prefix = self.id[:2].lower()
        return settings.thumb_dir / prefix / f"{self.id}.jpg"

    @computed_field
    @property
    def expected_display_path(self) -> Path:
        """Expected display-size image path (may not exist yet)."""
        from fichero.storage import settings
        prefix = self.id[:2].lower()
        return settings.thumb_dir / prefix / f"{self.id}_display.jpg"

    @property
    def has_thumbnail(self) -> bool:
        """Check if thumbnail exists on disk."""
        return self.expected_thumbnail_path.exists()

    @property
    def has_display(self) -> bool:
        """Check if display image exists on disk."""
        return self.expected_display_path.exists()

    # =========================================================================
    # macOS bookmark support (for external file tracking)
    # =========================================================================

    @property
    def bookmark(self) -> bytes | None:
        """macOS security-scoped bookmark for external files.

        Bookmarks survive file moves/renames and work in sandboxed apps.
        Returns decoded bytes from base64-encoded metadata.
        """
        b64 = self.metadata.get("bookmark")
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
                **self.metadata
            }
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

    Defines a sequence of steps to run on documents.
    Steps reference tools and providers.

    Examples:
        - "Transcribe OCR" - just OCR
        - "Full Analysis" - OCR → entities → summary
        - "PDF Processing" - extract pages → enhance → OCR
    """
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""

    # Pipeline steps
    steps: list[dict[str, Any]] = Field(default_factory=list)
    # Example:
    # [
    #     {"name": "transcribe", "tool": "transcribe", "provider": "qwen"},
    #     {"name": "entities", "tool": "extract_entities", "provider": "openai"},
    # ]

    # Default config for steps
    config: dict[str, Any] = Field(default_factory=dict)

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

class ProviderType(str, Enum):
    """Type of AI provider."""
    # On-device (Apple)
    apple = "apple"
    # Local servers
    ollama = "ollama"
    lmstudio = "lmstudio"
    # Open source
    huggingface = "huggingface"
    # Cloud providers
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    groq = "groq"
    together = "together"
    deepseek = "deepseek"
    mistral = "mistral"
    cohere = "cohere"
    # Additional LiteLLM providers
    dashscope = "dashscope"
    xai = "xai"
    perplexity = "perplexity"
    fireworks = "fireworks"
    azure = "azure"
    bedrock = "bedrock"


class Provider(BaseModel):
    """
    AI service provider configuration.

    Stores provider metadata and connection info.
    API keys are stored separately in macOS Keychain.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str                          # "OpenAI", "Qwen", "LM Studio"
    provider_type: ProviderType        # How to connect
    api_base: str | None = None        # Custom endpoint (for local/proxy)
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
    provider_id: str                   # FK to Provider
    name: str                          # "GPT-4o", "Qwen VL Max"
    model_id: str                      # Actual API identifier: "gpt-4o"
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
    name: str                          # "Transcribe"
    description: str = ""              # "Extract text from images using OCR"
    icon: str = "wrench"               # SF Symbol name
    module_path: str                   # "fichero.tools.transcribe"
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
    query: str                         # The search query text
    is_smart_search: bool = True       # Whether to use semantic search
    filters: dict[str, Any] | None = None  # Optional filter parameters

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


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
    "Tool",
    "SavedSearch",
]
