"""Knowledge graph models for 0.0.2 Search + Semantic backend slices."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

import re

from pydantic import BaseModel, Field, ConfigDict, field_validator


def _new_id() -> str:
    return uuid4().hex


# =============================================================================
# Source Reference Metadata
# =============================================================================


class ProvenanceInfo(BaseModel):
    """Tracks how source metadata was obtained."""

    source: str = Field(
        description="How this metadata was obtained: 'imported', 'manual', 'agent'"
    )
    agent_id: str | None = Field(default=None, description="Agent ID if source='agent'")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class SourceMetadataProvenance(BaseModel):
    """Per-field provenance tracking for source metadata."""

    imported: ProvenanceInfo | None = None
    manual: ProvenanceInfo | None = None
    agent: ProvenanceInfo | None = None


DOI_PATTERN = re.compile(r"^10\.\d{4,}/[^\s]+$")
ISBN_13_PATTERN = re.compile(r"^\d{13}$")
ISBN_10_PATTERN = re.compile(r"^\d{9}[\dXx]$")
ISSN_PATTERN = re.compile(r"^\d{4}-\d{3}[\dXx]$")


class SourceMetadata(BaseModel):
    """Structured citation and archival metadata for knowledge sources.

    Covers: documents, articles, books, web pages, datasets, archives.
    Supports DOI, ISBN, ISSN, arXiv, URL, and archive identifiers.
    """

    model_config = ConfigDict(extra="allow")

    # --- Core citation ---
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    date: str | None = Field(
        default=None,
        description="Publication date in any common format (ISO 8601 preferred)",
    )
    publisher: str | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None

    # --- Identifiers ---
    doi: str | None = Field(default=None, description="Digital Object Identifier")
    isbn_13: str | None = Field(default=None, description="ISBN-13")
    isbn_10: str | None = Field(default=None, description="ISBN-10")
    issn: str | None = Field(
        default=None, description="International Standard Serial Number"
    )
    arxiv_id: str | None = Field(default=None, description="arXiv identifier")
    url: str | None = None
    url_accessed: str | None = Field(
        default=None, description="Date URL was accessed/archived (ISO 8601)"
    )

    # --- Archive identifiers ---
    archive_name: str | None = Field(
        default=None,
        description="Archive that holds the source (e.g., 'Internet Archive')",
    )
    archive_identifier: str | None = Field(
        default=None, description="Identifier within the archive"
    )
    wwb_legacy_id: str | None = Field(
        default=None, description="Weber Wentzel Bize legacy archive ID"
    )

    # --- Rights & access ---
    rights: str | None = Field(
        default=None, description="License or copyright statement"
    )
    access_restrictions: str | None = Field(
        default=None,
        description="Access restrictions: 'public', 'restricted', 'closed'",
    )

    # --- IIIF ---
    iiif_manifest: str | None = Field(
        default=None, description="IIIF manifest URL for image collections"
    )

    # --- Language ---
    language: str | None = Field(
        default=None,
        description="Primary language code (ISO 639-1, e.g., 'en', 'fr')",
    )

    # --- Metadata provenance ---
    provenance: SourceMetadataProvenance = Field(
        default_factory=SourceMetadataProvenance,
        description="Tracks how metadata fields were obtained",
    )

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not DOI_PATTERN.match(v):
            raise ValueError(f"Invalid DOI format: {v!r}. Expected '10.XXXX/...'")
        return v

    @field_validator("isbn_13")
    @classmethod
    def validate_isbn13(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.replace("-", "").strip()
        if not ISBN_13_PATTERN.match(v):
            raise ValueError(f"Invalid ISBN-13: {v!r}. Expected 13 digits.")
        # Checksum
        digits = [int(c) for c in v]
        checksum = sum((i % 2 * 2 + 1) * d for i, d in enumerate(digits)) % 10
        if checksum != 0:
            raise ValueError(f"Invalid ISBN-13 checksum: {v!r}")
        return v

    @field_validator("isbn_10")
    @classmethod
    def validate_isbn10(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.replace("-", "").strip().upper()
        if not ISBN_10_PATTERN.match(v):
            raise ValueError(f"Invalid ISBN-10: {v!r}. Expected 10 digits or 9+X.")
        # Checksum
        digits = [int(c) if c.isdigit() else 10 for c in v[:-1]]
        checksum = sum((10 - i) * d for i, d in enumerate(digits))
        last = 10 if v[-1] == "X" else int(v[-1])
        checksum += last
        if checksum % 11 != 0:
            raise ValueError(f"Invalid ISBN-10 checksum: {v!r}")
        return v

    @field_validator("issn")
    @classmethod
    def validate_issn(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.replace("-", "").strip().upper()
        if not re.match(r"^\d{7}[\dXx]$", v):
            raise ValueError(
                f"Invalid ISSN: {v!r}. Expected 8 digits with optional trailing X."
            )
        # Checksum: mod 11
        digits = [int(c) for c in v[:7]]
        checksum = sum((8 - i) * d for i, d in enumerate(digits)) % 11
        check = (11 - checksum) % 11
        expected = str(check) if check < 10 else "X"
        if v[-1] != expected:
            raise ValueError(f"Invalid ISSN checksum: {v!r}. Expected '{expected}'.")
        return v

    @field_validator("arxiv_id")
    @classmethod
    def validate_arxiv(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        # arXiv IDs: nnnn.nxxxx or arXiv:nnnn.nxxxx
        if v.startswith("arXiv:"):
            v = v[6:]
        if not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", v):
            raise ValueError(f"Invalid arXiv ID: {v!r}. Expected 'YYYY.XXXXX' format.")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid URL: {v!r}. Must start with http:// or https://."
            )
        return v

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[str]) -> list[str]:
        return [a.strip() for a in v if a.strip()]

    @field_validator("access_restrictions")
    @classmethod
    def validate_access_restrictions(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"public", "restricted", "closed"}
        if v.lower() not in allowed:
            raise ValueError(
                f"Invalid access_restrictions: {v!r}. Expected one of: {allowed}"
            )
        return v.lower()

    def to_citation(self) -> str:
        """Render a plain-text citation from this metadata."""
        parts = []
        if self.authors:
            authors_str = "; ".join(self.authors[:3])
            if len(self.authors) > 3:
                authors_str += " et al."
            parts.append(authors_str)
        if self.date:
            parts.append(f"({self.date})")
        if self.title:
            parts.append(f'"{self.title}"')
        if self.journal:
            parts.append(f"*Journal of {self.journal}*")
        if self.publisher:
            parts.append(self.publisher)
        if self.doi:
            parts.append(f"https://doi.org/{self.doi}")
        return ". ".join(parts) if parts else ""


# =============================================================================
# Entity Type
# =============================================================================


class EntityType(str, Enum):
    person = "person"
    location = "location"
    organization = "organization"
    event = "event"
    concept = "concept"
    other = "other"


class SourceType(str, Enum):
    document = "document"
    claim = "claim"
    multiple = "multiple"
    synthesis = "synthesis"


class ClaimType(str, Enum):
    fact = "fact"
    analysis = "analysis"
    interpretation = "interpretation"
    argument = "argument"
    historiography = "historiography"
    theory = "theory"


class EpistemicStatus(str, Enum):
    tentative = "tentative"
    confirmed = "confirmed"
    rejected = "rejected"


class ClaimCurationState(str, Enum):
    unreviewed = "unreviewed"
    shortlisted = "shortlisted"
    curated = "curated"
    rejected = "rejected"


class ClaimRelationType(str, Enum):
    supports = "supports"
    contradicts = "contradicts"
    refines = "refines"
    duplicate_of = "duplicate_of"


# --- #1123 attribution-taxonomy enums (Phase A) ---
# Three orthogonal axes of "how does this claim's text relate to its source":
# QuotationKind = how literal (warrant strength),
# ProvenanceLayer = where on the page (marginalia ≠ main text),
# SourceGenre = what kind of document genre per passage (a 19c collection
# may reprint an 18c royal decree — the genre is per-passage, not per-doc).


class QuotationKind(str, Enum):
    """How literally a claim reproduces its source text.

    Picks up the warrant strength: a verbatim quotation supports a stronger
    epistemic status than an inferred one. Defaults to ``paraphrase`` —
    that's the realistic default for an LLM extractor that summarised the
    source rather than copying it verbatim.
    """

    verbatim = "verbatim"
    paraphrase = "paraphrase"
    indirect = "indirect"
    inference = "inference"
    free_indirect = "free_indirect"


class ProvenanceLayer(str, Enum):
    """Where on a page the claim's source text lives.

    Marginalia and interlinear annotations were added by later readers and
    carry different evidentiary weight than the main text. ``main_text``
    is the default; PDF-bbox heuristics (top/bottom margin offsets) flip
    to ``marginalia`` or ``footnote``.
    """

    main_text = "main_text"
    marginalia = "marginalia"
    footnote = "footnote"
    annotation_later = "annotation_later"
    scribal_correction = "scribal_correction"
    interlinear = "interlinear"


class SourceGenre(str, Enum):
    """Genre of the source passage that produced this claim.

    Per-passage, not per-document — a 19th-century compiled collection may
    reprint an 18th-century royal decree alongside private letters; each
    excerpt carries its own genre. Classified per-doc at ingest, stamped
    onto every claim from that doc as a default; overridable per-claim.
    """

    petition = "petition"
    testimony = "testimony"
    royal_decree = "royal_decree"
    private_letter = "private_letter"
    receipt = "receipt"
    inventory = "inventory"
    deed = "deed"
    minutes = "minutes"
    report = "report"
    article = "article"
    book = "book"
    note = "note"
    other = "other"


class GeoPoint(BaseModel):
    """Lat/lon for the spatial scope a claim refers to.

    Distinct from entity locations (a claim about Pedro travelling from
    Popayán to Quito has a different geo scope than Pedro's birthplace).
    Optional precision_m lets the renderer draw a confidence radius
    instead of a point pin when locations are imprecise.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    precision_m: float | None = Field(
        default=None,
        description="Radius of locational uncertainty in metres (None = exact).",
    )
    place_name: str | None = None


class ProvenanceStep(BaseModel):
    """One step in a document's chain of custody.

    Example sequence for a colonial bill of sale:
        filed 1699 (Popayán) → copied 1933 (compiled into archive series)
        → scanned 2019 → accessed 2026 (researcher).

    Each step records who did what, when, where. Empty actor/date is fine
    when the step is implicit or unknown.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    action: str = Field(
        description="What happened: 'filed', 'copied', 'scanned', 'accessed', etc.",
    )
    actor: str | None = Field(
        default=None,
        description="Who performed the action (person / institution / agent).",
    )
    date: str | None = Field(
        default=None, description="ISO 8601 — date or partial date.",
    )
    location: str | None = None
    notes: str | None = None


class ImageProvenance(BaseModel):
    """For digitised images: who/when/how the digital surrogate was captured.

    Separate from document-level provenance because the same physical
    document can have multiple captures (initial scan + reshoot for
    damaged page); image_provenance describes THIS particular digital
    artifact, not the document's broader chain of custody.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    photographer: str | None = None
    capture_date: str | None = Field(
        default=None, description="ISO 8601 — when the digital image was captured.",
    )
    equipment: str | None = Field(
        default=None,
        description="Camera / scanner make + model.",
    )
    condition_notes: str | None = Field(
        default=None,
        description="Notable damage, fading, or capture limitations.",
    )


class InclusionScopeType(str, Enum):
    library = "library"
    folder = "folder"
    document = "document"


class PredictionEntity(BaseModel):
    text: str
    type: str  # person, location, organization, date, etc.
    start: int
    end: int


class PredictionUncertaintySpan(BaseModel):
    start: int
    end: int
    reason: str


class PredictionLink(BaseModel):
    target_claim_id: str
    link_type: str  # next_logical, supports, contradicts, refines


class PredictionMetadata(BaseModel):
    confidence: float
    model: str
    entities: list[PredictionEntity] = Field(default_factory=list)
    uncertainty_spans: list[PredictionUncertaintySpan] = Field(default_factory=list)
    predicted_links: list[PredictionLink] | None = None


class KnowledgeEntity(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    canonical_name: str
    entity_type: EntityType = EntityType.other
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    language: str | None = None
    metadata: dict = Field(default_factory=dict)
    merged_into_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class EntityMergeOperationType(str, Enum):
    merge = "merge"
    split = "split"
    undo_merge = "undo_merge"
    undo_split = "undo_split"


class EntityMergeAudit(BaseModel):
    """Immutable audit record for entity merge/split operations."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    operation_type: EntityMergeOperationType
    source_entity_ids: list[str]  # entities absorbed (merge) or split apart (split)
    target_entity_id: str  # canonical entity involved
    alias_changes: dict = Field(
        default_factory=dict,
        description="Keys: 'added', 'removed', 'moved_to', 'restored_from'",
    )
    reversal_id: str | None = None  # set to the audit ID that reverses this operation
    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)


class ClassificationDimension(str, Enum):
    """Which classification axis a registry value belongs to (#915)."""

    epistemic_status = "epistemic_status"
    claim_type = "claim_type"
    entity_type = "entity_type"


class ClassificationValue(BaseModel):
    """User-extensible classification taxonomy entry (#915).

    Replaces the hardcoded EpistemicStatus / ClaimType / EntityType
    enums for runtime registry: users add new buckets via
    /api/classifications without code changes. Built-in values are
    seeded on first run and protected from deletion.

    Example custom values a historiographer might add:
    - dimension=epistemic_status, key="contested", label="Contested"
    - dimension=claim_type, key="ethnographic", label="Ethnographic"
    - dimension=entity_type, key="plant_species", label="Plant species"
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    dimension: ClassificationDimension
    key: str = Field(
        description="Machine-readable identifier; lowercase, used in queries.",
    )
    label: str = Field(description="Human-readable display string.")
    description: str | None = None
    parent_key: str | None = Field(
        default=None,
        description="Optional hierarchy: 'binding' parent of 'constitutional'.",
    )
    color: str | None = Field(
        default=None, description="Hex tint for badge rendering, e.g. '#FF8800'."
    )
    icon: str | None = Field(default=None, description="SF Symbol name for inspector chips.")
    is_builtin: bool = Field(
        default=False,
        description="Built-in values (tentative/confirmed/...) cannot be deleted.",
    )
    sort_order: int = 0
    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class DocumentCitation(BaseModel):
    """One document citing another (#906).

    Captures both the structural fact (A cites B) and the textual
    evidence (where in A the citation appears). Confidence reflects
    how certain the detector is that ``target_document_id`` is the
    right resolution — needed when matching a bibliography string
    to an in-library document by fuzzy title + author.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    source_document_id: str   # the citing document
    target_document_id: str | None = Field(
        default=None,
        description="The cited document if resolved in the library, else None.",
    )
    target_citation_text: str = Field(
        description="The citation as it appears in the source (the raw string).",
    )
    page_label: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    detector: str = Field(
        default="manual",
        description="Which detector emitted this citation: manual / regex / llm / bibtex_import",
    )
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ProjectStatus(str, Enum):
    """Lifecycle of a research workspace (#918)."""

    active = "active"
    archived = "archived"
    shipped = "shipped"


class Project(BaseModel):
    """A research workspace — named container for sources + analysis (#918).

    Groups documents, entities, claims, notes, and interpretations
    under a single project context (a thesis chapter, a JLAR review,
    a conference talk). Inclusion is via ProjectInclusion rows so
    the same KG row can sit in multiple projects.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    description: str | None = None
    color: str | None = None
    icon: str | None = None  # SF Symbol name for the sidebar
    status: ProjectStatus = ProjectStatus.active
    members: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectInclusion(BaseModel):
    """One KG row's membership in a project (#918)."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    project_id: str
    target_id: str
    target_type: str = Field(
        description="'document' | 'entity' | 'claim' | 'note' | 'interpretation' | 'annotation'"
    )
    role: str | None = Field(
        default=None,
        description="Optional role label: 'primary source' | 'argument' | 'draft' | ...",
    )
    notes: str | None = None
    added_by: str = "human"
    added_at: datetime = Field(default_factory=datetime.now)


class NoteKind(str, Enum):
    """Zettelkasten note kinds (#917)."""

    zettel = "zettel"          # atomic idea, one note per concept
    reference = "reference"    # literature note — summary of a source
    hub = "hub"                # structure note — index over related zettels
    inbox = "inbox"            # quick capture, not yet processed
    fleeting = "fleeting"      # transient thought, may or may not become a zettel
    permanent = "permanent"    # the elaborated, well-formed idea


class Note(BaseModel):
    """A Zettelkasten-style atomic user note (#917).

    Notes are user-authored prose units that link to each other,
    to entities, to claims, and to documents — forming a personal
    knowledge graph independent of the source corpus's KG.

    Distinct from Annotation: annotations are anchored to a specific
    document region (a highlight on page 14). Notes are floating —
    they can reference any number of documents/claims/entities but
    don't sit on a document themselves.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    title: str | None = None
    body: str = ""  # rich-text markdown
    kind: NoteKind = NoteKind.zettel
    tags: list[str] = Field(default_factory=list)

    # Cross-links to other KG nodes. Each list holds ids of the
    # appropriate type; bidirectional resolution is via NoteLink for
    # note↔note edges (other targets are unidirectional from the note).
    linked_note_ids: list[str] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_document_ids: list[str] = Field(default_factory=list)

    # Luhmann-style numeric address (optional). "1.4a.2" denotes
    # zettel #2 under branch 1.4a. Free-form so users can adopt other
    # conventions.
    address: str | None = None
    parent_address: str | None = None

    author_type: str = "user"  # "user" | "ai"
    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class NoteLink(BaseModel):
    """Bidirectional link between two Notes — the Zettelkasten edge (#917).

    Stored separately from Note.linked_note_ids so both sides can
    query the relation efficiently and the link itself can carry
    metadata (type, annotation).
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    source_note_id: str
    target_note_id: str
    link_type: str = "free"     # follows | references | contradicts | supports | free
    annotation: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class AnnotationKind(str, Enum):
    """User annotation kinds (#914).

    Each kind has slightly different rendering + payload conventions:
    - highlight: coloured tint over a span; ``color`` + ``rating`` carry weight
    - note: margin/sticky note; ``text`` is the body
    - rating: 1-5 importance flag; ``rating`` carries weight
    - bookmark: navigation marker; ``text`` optional label
    - comment: threaded discussion (future); ``text`` is the body
    """

    highlight = "highlight"
    note = "note"
    rating = "rating"
    bookmark = "bookmark"
    comment = "comment"


class Annotation(BaseModel):
    """User-authored annotation on a document, text span, or image region (#914).

    Anchored to a Document via document_id, optionally further refined
    by char_start/char_end (text spans, reuses #913's offsets) and/or
    bbox (image / PDF rectangles). Workflows can consume annotations
    as AI input (see #914 comment on workflow-input extension) so a
    bbox over 10% of a 100MB image becomes the cropped input that
    Apple Intelligence actually sees.

    Distinct from KnowledgeClaim — annotations are user-authored
    surface marks, claims are knowledge-graph propositions. A
    highlight can be promoted to a claim via
    POST /api/annotations/{id}/promote-to-claim.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    document_id: str
    page_label: str | None = None
    # Sub-page anchors (reuse #913 substrate).
    char_start: int | None = None
    char_end: int | None = None
    # Image / PDF region as [x, y, width, height] in source coordinates.
    bbox: list[float] | None = None

    kind: AnnotationKind
    text: str | None = None  # note body / comment text / bookmark label
    rating: int | None = Field(default=None, ge=1, le=5)
    color: str | None = Field(
        default=None,
        description="Hex colour for highlight tint, e.g. '#FFFF00'",
    )
    tags: list[str] = Field(default_factory=list)

    # Cross-links — promote annotations into the KG.
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    linked_note_ids: list[str] = Field(default_factory=list)  # see Note model

    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PendingMatchState(str, Enum):
    """Lifecycle state of an EntityMatchCandidate."""
    pending = "pending"
    accepted = "accepted"  # human merged
    rejected = "rejected"  # human said "definitely different" — labelled negative


class PendingMatchMethod(str, Enum):
    """Which detector flagged this candidate pair."""
    embedding_cosine = "embedding_cosine"
    splink = "splink"
    manual = "manual"
    graph_context = "graph_context"


class EntityMatchCandidate(BaseModel):
    """A pair of entities the system suspects might be the same, waiting
    on a human review-gate decision (#899 Phase D / #377).

    Created by ``upsert_entity`` when a fuzzy match falls in the
    review band (cosine 0.75-0.92 today). The reviewer accepts
    (merges survivor + candidate) or rejects (labelled negative,
    feeds splink/PyKEEN training).

    Decisions live on this row; the actual merge writes an
    ``EntityMergeAudit`` for the reversible history. Splitting
    review state from merge state lets us re-suggest the same pair
    if a user later edits one of the entities significantly.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    survivor_entity_id: str = Field(
        description="The entity that survives on accept — typically the older / more-claimed one."
    )
    candidate_entity_id: str = Field(
        description="The entity that absorbs into the survivor on accept."
    )
    score: float = Field(
        ge=0.0, le=1.0,
        description="Calibrated probability or cosine similarity in [0, 1].",
    )
    method: PendingMatchMethod = PendingMatchMethod.embedding_cosine
    state: PendingMatchState = PendingMatchState.pending
    reason: str | None = Field(
        default=None,
        description=(
            "Optional human-readable explanation of why the pair was "
            "flagged — useful when reviewing later. Examples: 'name "
            "token-set similarity 0.82', 'embedded description "
            "cosine 0.88'."
        ),
    )
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class MutationOperationType(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    restore = "restore"


class MutationLog(BaseModel):
    """General-purpose mutation log for auditable entity/claim changes.

    Tracks before/after snapshots so any mutation can be reversed.
    Supports both individual undo and grouped AI-run rollback.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    entity_type: str = Field(
        description="Type of entity mutated: 'KnowledgeClaim', 'KnowledgeEntity', etc."
    )
    entity_id: str = Field(description="ID of the mutated entity")
    operation: MutationOperationType
    before_state: dict | None = Field(
        default=None,
        description="Full entity state before mutation (null for creates)",
    )
    after_state: dict | None = Field(
        default=None,
        description="Full entity state after mutation (null for deletes)",
    )
    changed_fields: list[str] | None = Field(
        default=None,
        description="Which fields were modified (for updates)",
    )
    run_id: str | None = Field(
        default=None,
        description="AI run ID if this mutation was part of an agent batch",
    )
    agent_id: str | None = Field(default=None)
    created_by: str = "human"
    reversal_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class KnowledgeClaim(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    text: str
    # --- single-source (backwards-compatible) ---
    source_document_id: str
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    # --- sub-page anchor (#913) — character offset + optional bbox ---
    # Lets the inspector navigate to the exact span instead of just
    # the page. Populated by the catalogue extractor when source_text
    # can be located in page_content; nullable for legacy claims and
    # claims where the substring search fails.
    source_char_start: int | None = None
    source_char_end: int | None = None
    # --- Toulmin argument structure (#907) — populated only for ---
    # --- claim_type in {analysis, argument, interpretation, theory} ---
    # Fact claims stay flat (just text + SVO). Analytic claims gain the
    # six Toulmin slots: grounds (evidence), warrant (rule linking
    # grounds → claim), backing (support for warrant), qualifier
    # (presumably / usually), rebuttal (known counter).
    # All nullable so existing claims and fact claims survive.
    grounds: str | None = Field(
        default=None,
        description="Evidence: 'the heirs filed in 1933'.",
    )
    warrant: str | None = Field(
        default=None,
        description="Rule connecting grounds → claim.",
    )
    backing: str | None = Field(
        default=None,
        description="Support for the warrant — why the rule holds.",
    )
    qualifier: str | None = Field(
        default=None,
        description="'presumably' / 'usually' / 'in most cases'.",
    )
    rebuttal: str | None = Field(
        default=None,
        description="Known exception / counter-evidence.",
    )
    # --- temporal scope (#904) — when did this claim's content happen? ---
    # Distinct from created_at (when the claim was extracted). Lets the
    # inspector / SPARQL surface answer "what happened in 1933?"
    time_start: str | None = Field(
        default=None,
        description=(
            "Start of the time period the claim refers to, ISO 8601 "
            "(year / month / day). 'X became alcalde in 1933' → 1933-01-01."
        ),
    )
    time_end: str | None = Field(
        default=None,
        description=(
            "End of the time period — equal to time_start for "
            "instant events, later for ranges. 'X served from 1933 "
            "to 1937' → time_end=1937-12-31."
        ),
    )
    time_precision: str | None = Field(
        default=None,
        description="'year' | 'month' | 'day' | 'range' | 'unknown'",
    )
    source_bbox: list[float] | None = Field(
        default=None,
        description=(
            "[x, y, width, height] in PDF page coordinates. Populated "
            "via PyMuPDF page.search(excerpt) for PDF-backed claims; "
            "None for text-only or when the search misses."
        ),
    )
    # --- multi-source ---
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)  # additional source doc IDs
    source_page_labels: list[str] = Field(default_factory=list)  # pages per source
    source_languages: list[str] = Field(default_factory=list)  # languages per source
    # --- claim classification ---
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None
    # --- SVO triple (#984) — promoted to top-level fields from
    # metadata so OpenAPI codegen, DuckDB queries, and Pydantic
    # validation all see them as first-class.  The extractor (see
    # extractors.py:1375-1456) populates these alongside the legacy
    # metadata["subject"/"verb"/"object"] keys for one release of
    # backwards compat.  All nullable so legacy claims survive.
    subject_canonical: str | None = Field(
        default=None,
        description=(
            "Canonical name of the subject entity in this claim's S-V-O triple. "
            "For entity-bearing claims this matches the entity's canonical_name "
            "and (when present) subject_entity_id resolves to the entity row. "
            "For date-style claims the subject is the normalised date string."
        ),
    )
    subject_entity_id: str | None = Field(
        default=None,
        description=(
            "Resolved KnowledgeEntity.id when the subject canonical name "
            "matches a known entity. Lets the graph view do an O(1) lookup "
            "instead of name matching at render time."
        ),
    )
    predicate_verb: str | None = Field(
        default=None,
        description=(
            "Verb / verb phrase of the SVO triple. Examples: 'served as', "
            "'wrote', 'is located in'. Composed with object_phrase to form "
            "the human-readable claim text."
        ),
    )
    object_phrase: str | None = Field(
        default=None,
        description=(
            "Object phrase of the SVO triple — the rest of the predicate "
            "after the verb. Example: 'the alcalde of Popayán'."
        ),
    )
    # --- provenance & confidence ---
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # --- prediction (PyKEEN) ---
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] = Field(default_factory=list)
    prediction: PredictionMetadata | None = None
    # --- provenance: which LLM (+ optional post-processor) produced this ---
    # (#1113) — populated by the extractor write path with the LLM
    # provider/model that proposed the item, plus a "+heuristic-svo"
    # suffix on `model` when our local SVO splitter filled in fields
    # the LLM didn't return. Honest about hybrid pipelines so users
    # can audit per-model claim quality at the inspector layer.
    # Both nullable so legacy claims and human-authored claims survive.
    provider: str | None = Field(
        default=None,
        description=(
            "LLM provider that proposed this claim (e.g. 'openai', "
            "'anthropic', 'apple'). None for human-authored claims and "
            "legacy rows written before #1113."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Model that produced this claim, optionally suffixed with "
            "'+heuristic-svo' when local SVO synthesis filled in verb/"
            "object the LLM didn't return. Examples: 'gpt-4o-mini', "
            "'apple-intelligence+heuristic-svo'."
        ),
    )
    # --- metadata ---
    language: str | None = None
    metadata: dict = Field(default_factory=dict)
    source_metadata: SourceMetadata | None = Field(
        default=None,
        description="Structured citation and archival metadata for the primary source",
    )
    # =====================================================================
    # #1123 attribution taxonomy — Phase A (claim-level)
    # =====================================================================
    # All nullable / default-safe so legacy claims survive. Populated by
    # the extractor (Phase D); defaults encode "we don't know" rather than
    # a guess. Honest absence > guessed presence.
    #
    # --- speaker / authorship layer ---
    # Claim provenance ≠ document author. A trial record may quote ten
    # witnesses; each witness's statements need their own speaker. The
    # scribe / editor split surfaces bias that a flat author field hides:
    # Maria petitions, the scribe writes (and may insert language), the
    # 19c editor selects + orders the passage into a collection.
    speaker_name: str | None = Field(
        default=None,
        description=(
            "Free-text speaker label as it appears in the source — "
            "'the witness Pedro', 'the petitioner Maria'. May not match "
            "any known entity (use speaker_entity_id when it does)."
        ),
    )
    speaker_entity_id: str | None = Field(
        default=None,
        description=(
            "Resolved KnowledgeEntity.id when speaker_name matches a "
            "known entity — lets the inspector navigate by speaker."
        ),
    )
    subject_of_inquiry_entity_id: str | None = Field(
        default=None,
        description=(
            "When the claim is testimony ABOUT a third party (Pedro "
            "testified about Maria), this names that third party. "
            "Distinct from subject_entity_id (the SVO subject = Pedro)."
        ),
    )
    scribe_name: str | None = Field(
        default=None,
        description=(
            "Who physically wrote the source text. The scribe is often "
            "different from the speaker (Maria petitions; the scribe "
            "writes); their hand may inflect bias or formula."
        ),
    )
    scribe_entity_id: str | None = Field(default=None)
    editor_name: str | None = Field(
        default=None,
        description=(
            "Editor of the curated collection / edition this claim was "
            "extracted from. For uncurated raw documents this is null."
        ),
    )
    editor_entity_id: str | None = Field(default=None)

    # --- quotation / interpretive layer ---
    quotation_kind: QuotationKind | None = Field(
        default=None,
        description=(
            "How literally the claim reproduces the source — verbatim "
            "vs paraphrase changes the warrant strength."
        ),
    )
    provenance_layer: ProvenanceLayer = Field(
        default=ProvenanceLayer.main_text,
        description=(
            "Where on the page the source text lives. Defaults to "
            "main_text; PDF-bbox margin heuristics promote to marginalia "
            "/ footnote / interlinear."
        ),
    )
    source_language: str | None = Field(
        default=None,
        description=(
            "Original language of THIS claim's source text (ISO 639-1). "
            "May differ from the document's primary language when a doc "
            "contains multilingual passages — a 17c Spanish record may "
            "embed a Latin formula. Mirrors `language` for back-compat; "
            "the extractor writes both."
        ),
    )
    translation_chain: list[str] = Field(
        default_factory=list,
        description=(
            "Translation history as 'lang:source' tags, e.g. "
            "['es:original', 'en:apple-translate', 'en:human-edit']. "
            "Empty list means the text is in its original language."
        ),
    )
    audience: str | None = Field(
        default=None,
        description=(
            "Whom the claim was addressed to — 'the Cabildo of Popayán', "
            "'the Audiencia'. Extracted from 'to the X' / 'addressed to "
            "Y' patterns in the source."
        ),
    )
    source_genre: SourceGenre | None = Field(
        default=None,
        description=(
            "Genre of the source passage. Per-passage (not per-doc) — "
            "a 19c compiled collection may reprint petitions alongside "
            "royal decrees and private letters."
        ),
    )

    # --- temporal / spatial scope (extending existing time_*) ---
    claim_recorded_at: str | None = Field(
        default=None,
        description=(
            "When THIS claim's text was recorded, ISO 8601. Distinct "
            "from time_start (when the events happened) and from the "
            "document's date — a 1933 archive copy may reproduce an "
            "1820 letter, so the letter's claim has time_start=1820 "
            "but claim_recorded_at=1820 (the letter's date), while a "
            "scribal annotation on the same page might have "
            "claim_recorded_at=1965."
        ),
    )
    claim_geo: GeoPoint | None = Field(
        default=None,
        description=(
            "Spatial scope of the claim — distinct from entity "
            "locations. 'Pedro left Popayán for Quito' has claim_geo "
            "pinned to the journey path's midpoint, not Pedro's "
            "birthplace."
        ),
    )

    # --- quality / confidence layer ---
    confidence_source: str | None = Field(
        default=None,
        description=(
            "Where the `confidence` value came from: 'llm_logprob' / "
            "'heuristic' / 'human_review' / 'corroboration' / 'default'. "
            "Lets the inspector explain why a claim is rated 0.7 "
            "instead of treating the number as load-bearing."
        ),
    )

    # --- predicate canonical vocabulary ---
    # `predicate_verb` is free-text (good for display). `predicate_canonical`
    # is a normalised slug from `kg/_common.py::CANONICAL_VERBS` (added in
    # Phase C). Queries / aggregation use canonical; rendering uses verb.
    predicate_canonical: str | None = Field(
        default=None,
        description=(
            "Normalised predicate from kg/_common.py::CANONICAL_VERBS "
            "(~40-50 verbs across ontological / spatial / temporal / "
            "speech / role / kinship / property / causal / quantitative "
            "categories). Used for queries + SPARQL parity; "
            "predicate_verb is kept free-text for display."
        ),
    )

    created_by: str = "human"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class KnowledgeClaimLink(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    claim_id: str
    related_claim_id: str
    relation_type: ClaimRelationType
    link_quality: float = 0.5
    evidence: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class KnowledgeGraphInclusion(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    scope_type: InclusionScopeType
    target_id: str
    included: bool = True
    reason: str | None = None
    updated_by: str = "human"
    updated_at: datetime = Field(default_factory=datetime.now)


class PredictionModelType(str, Enum):
    transe = "transe"
    rotate = "rotate"
    complex = "complex"
    hermite = "hermite"


class KnowledgePredictionRun(BaseModel):
    """Stores a PyKEEN model training run and its output predictions.

    Separate from individual claim predictions (which are stored in claim.prediction).
    This tracks which model was trained, on what data, and the resulting predictions.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    model_type: PredictionModelType
    pykeen_config: dict = Field(default_factory=dict)  # PyKEEN config dict
    trained_at: datetime = Field(default_factory=datetime.now)
    # Training set info
    num_entities: int = 0
    num_claims: int = 0
    num_relation_types: int = 0
    # Evaluation metrics
    mrr: float | None = None
    hits_at_10: float | None = None
    hits_at_5: float | None = None
    hits_at_1: float | None = None
    # Model artifact path (if saved to disk)
    model_path: str | None = None
    # Status
    status: str = "trained"  # trained, failed, archived
    metadata: dict = Field(default_factory=dict)
