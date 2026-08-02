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
    from fichero_server.models import Document, Workflow
    from fichero_server.db import db

    # Query
    folders = db.query(Document, doc_type=DocType.folder)
    doc = db.get(Document, "abc123")

    # Create and save
    doc = Document(name="letter.jpg", path="/path/letter.jpg")
    db.save(doc)

    # Delete
    db.delete(doc)
"""

from pydantic import BaseModel, Field, ConfigDict, computed_field, field_validator
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from uuid import uuid4
import base64
import logging

# Typed OCR/transcription geometry saved on artifacts.
from fichero_server.media.ocr_geometry import OCRGeometryResult

# Import ProviderType from providers module (single source of truth)
from fichero_server.llm.providers import ProviderType

# Import from the sibling models/knowledge.py submodule directly (not via
# the fichero_server.models.knowledge top-level shim, which routes back through
# `fichero_server.models.knowledge` — the shim isn't fully initialized yet when
# something imports fichero_server.models.knowledge *before* fichero_server.models, so
# going through it here would reintroduce the exact circular-import
# ordering bug the direct-submodule import avoids) (#2566).
from fichero_server.models.knowledge import Reference, ReferenceProvenance

# Direct imports — knowledge.py has no dependency on this file.
from fichero_server.models.knowledge import (
    DocumentCitation,
    KnowledgeClaim,
    KnowledgeEntity,
    LibraryItemLink,
)

# Forward refs — routes import from this file, so we can't import back. The
# route modules call model_rebuild() on their owning envelope at module end.
if TYPE_CHECKING:
    from fichero_server.api.routes.system.activity import ActivityResponse
    from fichero_server.api.routes.workflow.batch import BatchResponse
    from fichero_server.api.routes.kg_entity_curation import EntityAuditResponse


logger = logging.getLogger(__name__)


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
    node_kind: str | None = "document"
    doc_type: DocType = DocType.file
    file_type: FileType | None = None

    # Identity
    name: str
    path: str | None = None  # File path (local or in library)

    # For pages/chunks
    sequence: int | None = None  # Raw 1-based page/image order
    page_label: str | None = None  # Document's own numbering; distinct from sequence
    bbox: tuple[int, int, int, int] | None = None  # x, y, width, height
    prototype_key: str | None = None  # user-assigned document prototype/class key

    # Alias / reference node (#2591 P2, node-model fold). When set, this node is
    # a *reference* to another node (Tinderbox-style alias): it appears inside a
    # container via ``parent_id`` but never duplicates the target's content. The
    # convention is ``node_kind == "alias"`` together with ``alias_target_id``
    # pointing at the referenced node. Resolution lives in ``node_aliases.py`` and
    # *raises* on a dangling target rather than silently substituting (prefer-raise).
    alias_target_id: str | None = None

    # Content (LangChain compatible)
    page_content: str | None = None

    # Extensible metadata - see properties below for common keys
    metadata: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Prototype-scoped node attributes. Saved-search nodes use this for "
            "their folded query/filter payload (#2591 F1)."
        ),
    )

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

    # Historical document date (#3322, plan #3319). The date the document was
    # WRITTEN, not imported — `created_at` is import time and is meaningless
    # for an 1893 diary page. JDN (Julian Day Number, an int) is the sort/
    # filter key: calendar-independent, timezone-immune, no datetime anywhere
    # in the sort path. Imprecise dates ("March 1791", "An II") are RANGES:
    # jdn = range start, jdn_end = range end; a day-precise date has
    # jdn == jdn_end. All NULL = no date; sort falls back to created_at.
    #
    # date_meta distinguishes three facts a historian needs kept apart
    # (never collapse them): {"status": "dated"} a date was extracted;
    # {"status": "undated_explicit"} the document SAYS it is undated
    # ("n.d.", "s.f."); {"status": "none_found"} extraction ran and found
    # nothing. date_meta is None only when extraction has never run. Also
    # carries calendar_system, precision (day|month|year|circa),
    # converted_gregorian_iso, display, source (extracted|metadata|user),
    # confidence.
    date_original: str | None = Field(
        default=None,
        description="The date string as written on/about the document, verbatim.",
    )
    date_jdn: int | None = Field(
        default=None, description="Julian Day Number of the date (range start)."
    )
    date_jdn_end: int | None = Field(
        default=None, description="Julian Day Number of the range end."
    )
    date_meta: dict[str, Any] | None = Field(
        default=None,
        description="HistoricalDate metadata: status, calendar_system, precision, display, source, confidence.",
    )

    # Workspace folders (#1313). A workspace is a normal folder document with
    # curated items layered on top of its child documents; views consume the
    # same folder hierarchy instead of a separate Mind Palace room tree.
    is_workspace: bool = Field(
        default=False,
        description="True when a folder document is presented as a workspace.",
    )
    curated_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Workspace-curated sources, annotations, and quotes. Stored as "
            "JSON so existing folder documents can opt in without a separate "
            "workspace table."
        ),
    )
    structure: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Programmatic book structure for PDF/file containers: chapters, "
            "sections, and subsections with page_range metadata (#1279)."
        ),
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

    # Workflow provenance (#1382). Stored as JSON so the existing DuckDB
    # table picker can add the new column without a manual migration.
    workflow_runs: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Workflow run provenance entries for this document. Each item "
            "records the workflow/model/result plus start and completion "
            "timestamps."
        ),
    )

    # Processing state
    status: Status = Status.pending
    is_read: bool = False
    is_starred: bool = False
    is_flagged: bool = False
    exclude_from_processing: bool = Field(
        default=False,
        description=(
            "True when import/workflow processing should skip this document. "
            "Used by curation to keep selected rows out of downstream passes."
        ),
    )

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    deleted_at: datetime | None = None
    deleted_by: str | None = None

    # User-defined order within parent folder. Set by /documents/reorder;
    # consumed by `SidebarItemBuilder.childOrder` Swift-side (lower =
    # earlier). Every document defaults to 0; once a folder is reordered,
    # its children get sequential values. Reorder-unaware folders tie at
    # 0 and fall through to name-based sort. Without this field declared
    # on the Pydantic model, the reorder endpoint's `doc.sort_order = i`
    # assignment is dropped silently by `model_dump()` (only declared
    # fields are serialized), so reorder never persists to DB.
    sort_order: int = 0

    # How many children this node has, supplied per-request by the listing
    # routes and NEVER stored (#3355). Listed in TRANSIENT_FIELDS below.
    #
    # The sidebar decides whether to draw a disclosure triangle from
    # `childCount > 0`. The backend did not send this on `/roots` or
    # `/{id}/children`, so every unexpanded folder decoded 0 and rendered
    # childless: you could not tell a folder had sub-folders, or a PDF had
    # pages, without clicking it first. "Not loaded yet" was being rendered as
    # "has nothing" — an absence read as an answer.
    #
    # The Swift client already reads it (`DocumentService` takes `child_count`
    # from `additionalProperties`), so nothing there had to change.
    child_count: int = 0

    # Fields that exist on the wire but never as columns. `Document` is both the
    # API response shape and the persisted row, so a per-request value like
    # `child_count` would otherwise become a real column holding a number that
    # goes stale the moment any child is added, moved or deleted. Honoured by
    # `db.transient_field_names` (CREATE TABLE, ALTER TABLE, and every write).
    TRANSIENT_FIELDS: ClassVar[set[str]] = {"child_count"}

    # Case grouping: optional identifier to group documents into cases within
    # a folder (#1096). Catalogue tool groups documents by case_id and emits
    # one artifact per case instead of per folder.
    case_id: str | None = None

    # Canvas position for a node in the library (#2589). Stored as first-class
    # columns so the position rides on the document and survives list/get
    # responses and updates.
    position_x: float | None = None
    position_y: float | None = None
    position_z: float | None = None
    rotation_z: float | None = None
    scale: float | None = None
    z_index: int = 0

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
    def bibtex(self) -> str | None:
        """Canonical BibTeX record string for bibliographic sources."""
        source_metadata = self.__dict__.get("source_metadata")
        if isinstance(source_metadata, dict):
            value = source_metadata.get("bibtex")
            return value if isinstance(value, str) else None
        return None

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
            except Exception as exc:
                # A stored-but-undecodable bookmark is a real failure (lost
                # security-scoped access), not "no bookmark" — don't swallow it
                # silently (#2507).
                logger.warning(
                    "Could not decode security-scoped bookmark for document %s: %s",
                    self.id,
                    exc,
                )
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
    ocr_geometry: OCRGeometryResult | None = None  # Typed OCR/transcription boxes

    # Provenance
    source_document_id: str | None = None  # Source document this was extracted from (for page docs, parent PDF)
    run_id: str | None = None  # Workflow run thread_id (live path, #4313)
    provider: str | None = None  # "qwen", "openai", "kreuzberg", "human"
    model: str | None = None  # "gpt-4o", "qwen-vl-max"
    step_name: str | None = None  # Producing workflow node id (#4313)
    workflow_id: str | None = None  # Workflow definition that produced this (#4313)
    sequence: int | None = None  # Per-run monotonic save order (#4313)

    # Quality
    confidence: float | None = None
    reviewed: bool = False

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)

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


class ContentRepresentationKind(str, Enum):
    transcription = "transcription"
    normalized_text = "normalized_text"
    translation = "translation"
    transliteration = "transliteration"
    markdown = "markdown"
    html = "html"
    svg = "svg"


class ContentReviewState(str, Enum):
    source = "source"
    draft = "draft"
    reviewed = "reviewed"


class ContentSourceAnchor(BaseModel):
    document_id: str
    page_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: list[float] | None = None


class ContentRepresentation(BaseModel):
    """Immutable source-linked content representation (#3443 slice 1)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    document_id: str
    kind: ContentRepresentationKind
    content: str
    language: str | None = None
    script: str | None = None
    source_anchor: ContentSourceAnchor
    parent_representation_id: str | None = None
    derived_from_representation_id: str | None = None
    producer_run_id: str | None = None
    producer_tool: str | None = None
    producer_model: str | None = None
    review_state: ContentReviewState = ContentReviewState.source
    created_at: datetime = Field(default_factory=utc_now)


class ContentRepresentationRevision(BaseModel):
    """A user-authored revision linked to an immutable representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    representation_id: str
    content: str
    reviewer: str = "human"
    decision: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ContentRepresentationListResponse(BaseModel):
    """Standardized envelope for GET /api/content-representations/document/{document_id}."""

    items: list[ContentRepresentation]
    count: int


class ContentRepresentationRevisionListResponse(BaseModel):
    """Standardized envelope for GET /api/content-representations/{representation_id}/revisions."""

    items: list[ContentRepresentationRevision]
    count: int


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
    # Stored shape is the registry-stripped NodeDef / canonical EdgeDef dict.
    # Node example:
    # {"id": "node1", "tool": "transcribe", "label": "Transcribe", "position_x": 100, "position_y": 200, ...}
    # Edge example (canonical field names):
    # {"source": "node1", "source_port": "output", "target": "node2", "target_port": "input"}
    # Legacy ``source_node_id`` / ``source_port_id`` spellings are accepted on
    # input and normalized to the canonical names by the validators below.

    # Default config for steps/nodes
    config: dict[str, Any] = Field(default_factory=dict)

    # LLM configuration
    provider: str = ""
    model: str = ""

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("nodes", mode="before")
    @classmethod
    def _validate_nodes(cls, v: Any) -> list[dict[str, Any]]:
        """Validate + normalize persisted nodes at the storage boundary (#2537).

        The persisted ``nodes`` column was previously ``list[dict]`` that nothing
        type-checked, so a malformed node (missing ``tool``, wrong field types)
        surfaced as a runtime KeyError/None deep in the graph builder instead of
        a clean validation error at save/load time.

        Each node is round-tripped through the typed ``NodeDef`` so malformed
        nodes raise a Pydantic ``ValidationError`` *here*. The stored shape stays
        a minimal dict via ``model_dump_for_storage()`` — ports are stripped and
        re-hydrated from the tool registry on read (``enrich_node_with_ports``),
        so persisted JSON stays small and the running graph is unaffected.
        """
        from pydantic import ValidationError
        from fichero_server.workflows.types import NodeDef

        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("Workflow.nodes must be a list")

        out: list[dict[str, Any]] = []
        for idx, item in enumerate(v):
            if isinstance(item, NodeDef):
                node = item
            elif isinstance(item, dict):
                try:
                    node = NodeDef.model_validate(item)
                except ValidationError as exc:
                    raise ValueError(
                        f"invalid workflow node at index {idx}: {exc}"
                    ) from exc
            else:
                raise ValueError(
                    f"workflow node at index {idx} must be a dict or NodeDef, "
                    f"got {type(item).__name__}"
                )
            out.append(node.model_dump_for_storage())
        return out

    @field_validator("edges", mode="before")
    @classmethod
    def _validate_edges(cls, v: Any) -> list[dict[str, Any]]:
        """Validate + normalize persisted edges at the storage boundary (#2537).

        Each edge is round-tripped through the typed ``EdgeDef`` so a malformed
        edge raises a Pydantic ``ValidationError`` at save/load time rather than
        a runtime KeyError during graph construction. ``EdgeDef`` also resolves
        the ``source_port`` vs ``source_port_id`` (and ``source`` vs
        ``source_node_id``) drift: legacy spellings on already-stored workflows
        are accepted and normalized onto the canonical field, so existing
        libraries keep loading without a migration.
        """
        from pydantic import ValidationError
        from fichero_server.workflows.types import EdgeDef

        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("Workflow.edges must be a list")

        out: list[dict[str, Any]] = []
        for idx, item in enumerate(v):
            if isinstance(item, EdgeDef):
                edge = item
            elif isinstance(item, dict):
                try:
                    edge = EdgeDef.model_validate(item)
                except ValidationError as exc:
                    raise ValueError(
                        f"invalid workflow edge at index {idx}: {exc}"
                    ) from exc
            else:
                raise ValueError(
                    f"workflow edge at index {idx} must be a dict or EdgeDef, "
                    f"got {type(item).__name__}"
                )
            out.append(edge.model_dump())
        return out


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
    queued_at: datetime = Field(default_factory=utc_now)
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
    started_at: datetime = Field(default_factory=utc_now)
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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentNote(BaseModel):
    """User-authored note content keyed to a document."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    document_id: str
    content: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentNoteSourceAnchor(BaseModel):
    """User-visible provenance anchor for AI working-memory notes (#2152)."""

    model_config = ConfigDict(from_attributes=True)

    document_id: str | None = None
    page_id: str | None = None
    expediente: str | None = None
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None


class AgentNoteActor(BaseModel):
    """Who wrote the agent note — explicit, transparent attribution (#2152)."""

    model_config = ConfigDict(from_attributes=True)

    actor_id: str
    model_name: str | None = None
    run_id: str | None = None


class AgentNote(BaseModel):
    """Per-library AI working-memory note with provenance and attribution."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    body: str
    source_anchor: AgentNoteSourceAnchor
    actor: AgentNoteActor
    kind: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ImageEditChain(BaseModel):
    """Ordered non-destructive edit operations for a document image."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    document_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    timestamp: datetime = Field(default_factory=utc_now)

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
# Account - App-Wide User/Session Storage
# =============================================================================


class AccountUser(BaseModel):
    """App-wide user account stored in the global app database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    username: str
    display_name: str
    password_hash: str
    is_owner: bool = False
    active: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class AccountSession(BaseModel):
    """App-wide session record stored in the global app database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    user_id: str
    token_hash: str
    device_label: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    revoked: bool = False


class AccountInvite(BaseModel):
    """App-wide one-time invite record stored in the global app database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    username: str
    display_name: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    channel: Literal["qr", "messages", "email"] = "qr"
    consumed_at: datetime | None = None
    revoked: bool = False


class EnrollmentSecret(BaseModel):
    """Hashed, revocable grant for enrolling one owner's own devices."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    user_id: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    revoked: bool = False


class Device(BaseModel):
    """App-wide paired device credential stored in the global app database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str
    user_id: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    last_seen: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    revoked: bool = False


class LibraryRole(BaseModel):
    """Per-user role for one library, stored in the global app database."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    user_id: str
    library_path: str
    role: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LibraryAclOverride(BaseModel):
    """Per-user grant/deny override for a library subtree."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    user_id: str
    library_path: str
    target_id: str
    effect: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# Provider - AI Service Provider
# =============================================================================

# Note: ProviderType is imported from fichero_server.llm.providers (single source of truth)


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

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    created_by: str = "system"  # Owning user id when multi-user is enabled

    # Organization
    folder_path: str = "/"  # Unix-style path for organization
    sort_order: int = 0  # User-defined order within folder (position)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    scope_document_id: str | None = None  # Node-backed chat scope reference
    metadata: dict[str, Any] = Field(default_factory=dict)  # Additional metadata

    # Organization
    folder_path: str = "/"  # Unix-style path for organization
    sort_order: int = 0  # User-defined order within folder

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


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
    files_path: str | None = None  # Relative path to copied originals
    includes_files: bool = False  # Whether files/ was captured
    offsite_path: str | None = None  # Absolute path to offsite snapshot copy
    file_count: int = 0  # Number of files in snapshot
    duckdb_size_bytes: int = 0  # Size of DuckDB Parquet export
    lance_size_bytes: int = 0  # Size of LanceDB vector copy
    files_size_bytes: int = 0  # Size of copied originals

    # Retention
    is_pinned: bool = False  # Pinned snapshots are not auto-deleted
    tags: list[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None  # Auto-delete after this time


# =============================================================================
# Library bootstrap (CLI / API)
# =============================================================================


class LibraryCreateRequest(BaseModel):
    """Request body for ``POST /api/library`` — bootstrap a fresh library.

    The path must end in ``.fichero`` and be inside one of the allowlist
    roots enforced by ``fichero_server.api.main._is_allowed_library_path``. The
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


class RemoteBackendHealth(BaseModel):
    """Health diagnostics for the remote-backend client path."""

    enabled: bool
    connection_model: str
    api_url: str | None = None
    library_path_configured: bool
    token_configured: bool
    tailnet_status: str
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response from ``GET /api/health`` endpoint.

    If library path is provided in the request header, returns stats for that
    library. Otherwise, returns general backend health.
    """

    status: str
    library_path: str | None = None
    database: str | None = None
    document_count: int | None = None
    error: str | None = None
    backend_version: str | None = None
    active_libraries: int | None = None
    remote_backend: RemoteBackendHealth | None = None
    server_proof: str | None = None
    # Instance identity (#2862): the host app passes FICHERO_LAUNCH_NONCE at
    # spawn and verifies it is echoed here, proving this responder is the engine
    # it just launched — not a stale process squatting the port. engine_pid lets
    # the app diagnose "port occupied by PID N" precisely.
    engine_pid: int | None = None
    launch_nonce: str | None = None


class EmbeddingStatsResponse(BaseModel):
    """Response from ``GET /api/search/stats`` and embedded library stats."""

    indexed_count: int
    table_exists: bool
    entity_indexed_count: int = 0
    entity_table_exists: bool = False
    claim_indexed_count: int = 0
    claim_table_exists: bool = False


class LibraryStatsResponse(BaseModel):
    """Response from ``GET /api/stats`` for the active library."""

    documents: int
    artifacts: int
    embedding_stats: EmbeddingStatsResponse


class AuthIdentityUser(BaseModel):
    """Authenticated account identity, when the credential resolves to a user."""

    id: str
    username: str
    display_name: str
    is_owner: bool


class AuthIdentityResponse(BaseModel):
    """Response from ``GET /api/auth/identity`` across all auth modes."""

    multiuser_enabled: bool
    auth_kind: str
    user: AuthIdentityUser | None = None
    is_owner_access: bool


class LibraryAccessDeniedResponse(BaseModel):
    """Structured 403 payload for library-scoped read/write denials."""

    detail: str
    code: str
    library_path: str
    auth_kind: str | None = None
    username: str | None = None
    required: str


class LibraryAuthzSnapshot(BaseModel):
    """Response from ``GET /api/authz/library`` for the active library."""

    library_path: str
    multiuser_enabled: bool
    auth_kind: str
    can_manage_roles: bool
    current_user_id: str | None = None
    current_user_role: str | None = None
    target_id: str | None = None
    target_can_read: bool
    target_can_write: bool
    roles: list[LibraryRole] = Field(default_factory=list)


class LibraryMember(BaseModel):
    """One user's access to a library, joined with their account profile.

    The Users & Sharing UI (#2869 A2/A4) needs human-readable names, not the
    bare ``user_id`` the ``library_roles`` table stores. This is that join.
    """

    user_id: str
    username: str
    display_name: str
    is_owner_account: bool
    role: str


class LibraryMembersResponse(BaseModel):
    """Response from ``GET /api/authz/members`` — who can access this library."""

    library_path: str
    members: list[LibraryMember] = Field(default_factory=list)
    count: int


class AccessibleLibrary(BaseModel):
    """One library the current credential may access."""

    library_path: str
    library_name: str
    role: str


class SetLibraryRoleRequest(BaseModel):
    """Typed body for ``PUT /api/authz/members`` — assign/change a library role.

    A typed OpenAPI surface over the ``acl.set`` registry action so the Swift
    client gets a generated method instead of hand-rolling ``/actions/invoke``.
    """

    user: str = Field(description="Target user id or username")
    role: str = Field(description="owner/editor/viewer")


class ShareRequest(BaseModel):
    """Typed body for ``POST /api/authz/share`` — the Share button (#1867).

    Authz-gated model: sharing an object grants the recipient a per-library
    role via the existing ACL (not a tokenless public link). Sharing an
    entity/document grants library access so the recipient can reach it — the
    ACL is per-library and a role-less user can't be granted a subtree-only
    override.
    """

    user: str = Field(description="Recipient user id or username")
    role: str = Field(default="viewer", description="Role to grant: owner/editor/viewer")
    object_type: str = Field(default="library", description="library | entity | document")
    object_id: str | None = Field(
        default=None, description="Entity/document id (required for those types)"
    )


class ShareResponse(BaseModel):
    """Result of a share: the granted access + a link the recipient can open."""

    user: str
    role: str
    object_type: str
    object_id: str | None = None
    library_path: str
    share_url: str


class ReinstallDefaultWorkflowsResponse(BaseModel):
    """Response from ``POST /api/workflows/reinstall-defaults``."""

    seeded: int
    status: str


class AppleIntelligenceProbeResponse(BaseModel):
    """Result of probing whether Apple Intelligence is usable on this Mac."""

    available: bool
    reason: str | None = None


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
    added_at: datetime = Field(default_factory=utc_now)
    last_accessed: datetime = Field(default_factory=utc_now)

    # Backup configuration. Interval <= 0 keeps scheduled snapshots disabled,
    # preserving current behavior until a library explicitly opts in.
    snapshot_interval_seconds: float = 0.0
    snapshot_retention_count: int = 10
    snapshot_offsite_path: str | None = None


class LibraryRegistryResponse(BaseModel):
    """Response from GET /api/registry — list all known libraries."""

    libraries: list[KnownLibrary]
    count: int


class OpenLibraryHandle(BaseModel):
    """A live package connection owned by the backend database manager."""

    # The manager cache key is the only stable identity for a live handle.
    id: str
    path: str
    is_open: bool = True


class OpenLibraryHandlesResponse(BaseModel):
    """Response from GET /api/registry/open — live backend library handles."""

    libraries: list[OpenLibraryHandle]
    count: int


class UnicodeLibraryCollisionIdentity(BaseModel):
    """One side of a Unicode-equivalent library collision."""

    raw_path: str
    raw_path_escaped: str
    name: str
    name_escaped: str
    document_count: int | None
    document_count_error: str | None = None
    duckdb_size_bytes: int
    files_size_bytes: int
    modified_at: datetime | None = None


class UnicodeLibraryCollision(BaseModel):
    """Read-only report of two library identities that NFC-collide."""

    left: UnicodeLibraryCollisionIdentity
    right: UnicodeLibraryCollisionIdentity
    nfc_path: str
    nfc_name: str
    collision_case: str


class UnicodeLibraryCollisionResponse(BaseModel):
    """Response from GET /api/registry/unicode-collisions."""

    collisions: list[UnicodeLibraryCollision]
    count: int


class ActionCategoriesResponse(BaseModel):
    """Response from GET /api/actions/categories."""

    categories: list[str]


class ActionSuccessResponse(BaseModel):
    """Boolean success envelope for action mutations."""

    success: bool


class ActionJsonResponse(BaseModel):
    """Response from GET /api/actions/{action_id}/export."""

    json_data: str


class LocalModelInfoResponse(BaseModel):
    """A locally-managed AI model (Whisper, embeddings)."""

    model_id: str
    model_type: str
    display_name: str
    size_bytes: int
    is_downloaded: bool
    expected_size_mb: int
    path: str | None
    metadata: dict[str, Any]


class LocalModelListResponse(BaseModel):
    """List of local models."""

    models: list[LocalModelInfoResponse]


class DiskUsageResponse(BaseModel):
    """Disk usage broken down by model type."""

    whisper: int
    embeddings: int
    total: int


class DownloadStartedResponse(BaseModel):
    """Confirmation that a model download has been queued."""

    status: str
    model_type: str
    model_id: str


class DeleteModelResponse(BaseModel):
    """Result of a model deletion."""

    status: str
    freed_bytes: int


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


class LibraryItemLinkListResponse(BaseModel):
    """Standardized envelope for generic library-item link list endpoints."""

    items: list[LibraryItemLink]
    count: int


class DocumentListResponse(BaseModel):
    """Standardized envelope for document list endpoints (GET /api/documents,
    /collections, /roots, /{id}/children, /{id}/ancestors)."""

    items: list[Document]
    count: int


class RelatedDocumentsResponse(BaseModel):
    """One row of GET /api/documents/{doc_id}/related — another document
    related via shared knowledge-graph entities and/or semantic
    similarity (#4120). Lives here (not route-local) so the envelope is
    fully typed in the OpenAPI spec and the generated Swift client.
    """

    document_id: str
    name: str | None = None
    doc_type: str | None = None
    file_type: str | None = None
    shared_entities: int
    sample_entity_names: list[str] = []
    # Real cosine similarity in [0, 1] from the embedding index, when the
    # doc surfaced via the semantic leg. None = entity overlap only.
    similarity: float | None = None


class RelatedDocumentListResponse(BaseModel):
    """Standardized envelope for GET /api/documents/{doc_id}/related."""

    items: list[RelatedDocumentsResponse]
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


class LibraryEntityTypeListResponse(BaseModel):
    """Standardized envelope for GET /api/libraries/{lib}/entity-types list endpoints."""

    items: list[Any]  # Typically LibraryEntityType
    count: int


class MCPServerListResponse(BaseModel):
    """Standardized envelope for GET /api/mcp-servers list endpoints."""

    items: list[Any]  # Typically MCPServerResponse
    count: int


class CanvasListResponse(BaseModel):
    """Standardized envelope for canvas spatial list endpoints."""

    items: list[Any]
    count: int


class CanvasDeletedResponse(BaseModel):
    """Standardized success envelope for canvas deletes."""

    status: str


class AgentNoteListResponse(BaseModel):
    """Standardized envelope for agent-memory note endpoints."""

    items: list[Any]  # Typically AgentNote
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


class ReferenceListResponse(BaseModel):
    """Standardized envelope for GET /api/references list endpoints."""

    items: list[Reference]
    count: int


class ReferenceWithProvenanceResponse(BaseModel):
    """Response from GET /api/references/{id}."""

    reference: Reference
    provenance: list[ReferenceProvenance]


class DocumentCitationsResponse(BaseModel):
    """Response from GET /api/documents/{id}/citations."""

    model_config = ConfigDict(populate_by_name=True)

    self_: Reference = Field(alias="self")
    references: list[Reference]
    links: list[ReferenceProvenance]


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


# =============================================================================
# Action layer audit (EPIC #1848 / #2013)
# =============================================================================


class ActionAudit(BaseModel):
    """Immutable audit row for one registered-action invocation.

    Written by ``ActionRegistry.invoke`` (the single mutation choke point) for
    EVERY action that runs through it. Generalizes the entity-specific
    ``EntityMergeAudit``: ``before``/``after`` are JSON-able domain-object
    snapshots and ARE the undo payload — ``invert(before, after)`` derives the
    inverse action from them (see ``fichero_server.actions.registry``).

    0.0.x no-migration: the table (``actionaudits``) is picked up automatically
    by ``Database._ensure_table`` the first time an ``ActionAudit`` is saved on a
    fresh DB; ``_ensure_table``'s ADD COLUMN reconciliation covers existing DBs.

    Reuses the provenance/run-id conventions (#1832): ``run_id`` ties an action
    to the AI run that triggered it; ``created_at`` mirrors the other audit
    models' ``default_factory=utc_now``.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    action_name: str = Field(description="Registered action name, '<domain>.<verb>'")
    actor: str = Field(default="system", description="ui | chat | workflow | import | system | device id")
    client: str | None = Field(
        default=None,
        description=(
            "Client surface that invoked the action (X-Fichero-Client header: "
            "fichero-mcp | fichero-cli | ...). Attribution only, never authz — "
            "so an agent acting on the owner credential is distinguishable "
            "from the owner in the app (#4469). None = header absent (the app, "
            "or pre-#4469 rows)."
        ),
    )
    target_ids: list[str] = Field(
        default_factory=list,
        description="Primary domain-object ids this action touched.",
    )
    params: dict = Field(
        default_factory=dict,
        description="Validated action params (model_dump) as invoked.",
    )
    before: dict | None = Field(
        default=None,
        description="JSON-able snapshot of touched objects before execute (undo payload).",
    )
    after: dict | None = Field(
        default=None,
        description="JSON-able snapshot/result handles after execute (undo payload).",
    )
    run_id: str | None = Field(
        default=None,
        description="AI run id if this action ran as part of an agent batch (#1832).",
    )
    created_at: datetime = Field(default_factory=utc_now)
    chain_seq: int | None = Field(
        default=None,
        description=(
            "Monotonic append order for this database's audit chain. "
            "Assigned under the database lock when the row is written."
        ),
    )
    undone: bool = Field(
        default=False,
        description="True once this action has been reversed via its inverse.",
    )
    inverse_of: str | None = Field(
        default=None,
        description=(
            "If this action was invoked AS the inverse of another action (i.e. by "
            "the undo endpoint), the id of that ORIGINAL audit row. This is what "
            "makes generalized redo possible: undoing an inverse audit replays the "
            "original forward action's name + params (see fichero_server.actions.registry "
            "and POST /api/actions/audit/{id}/undo). None for ordinary forward actions."
        ),
    )
    prev_hash: str | None = Field(
        default=None,
        description="Previous ActionAudit row_hash in this database's append-only chain.",
    )
    row_hash: str = Field(
        default="",
        description=(
            "SHA-256 over immutable creation fields plus prev_hash; empty only on "
            "legacy rows created before the tamper-evident chain existed."
        ),
    )


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
    "EmbeddingStatsResponse",
    "LibraryStatsResponse",
    "LibraryAuthzSnapshot",
    "AccessibleLibrary",
    "ReinstallDefaultWorkflowsResponse",
    "AppleIntelligenceProbeResponse",
    "EntityContextResponse",
    # Known library registry (#1131)
    "KnownLibrary",
    "LibraryRegistryResponse",
    "OpenLibraryHandle",
    "OpenLibraryHandlesResponse",
    "UnicodeLibraryCollisionIdentity",
    "UnicodeLibraryCollision",
    "UnicodeLibraryCollisionResponse",
    "ActionCategoriesResponse",
    "ActionSuccessResponse",
    "ActionJsonResponse",
    "LocalModelInfoResponse",
    "LocalModelListResponse",
    "DiskUsageResponse",
    "DownloadStartedResponse",
    "DeleteModelResponse",
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
    "IntegrationListResponse",
    "KGInclusionListResponse",
    "KGPredictionListResponse",
    "AgentNote",
    "AgentNoteActor",
    "AgentNoteListResponse",
    "AgentNoteSourceAnchor",
    "ContradictionEvidence",
    "ContradictionListResponse",
    "MCPServerListResponse",
    "CanvasDeletedResponse",
    "CanvasListResponse",
    "NoteListResponse",
    "ProjectListResponse",
    "ResearchCrudListResponse",
    "ResearchNotesListResponse",
    "ScheduleListResponse",
    "SourceListResponse",
    "TriggerListResponse",
    "AccountUser",
    "AccountSession",
    "AccountInvite",
    "Device",
    "LibraryRole",
    "LibraryAclOverride",
]
