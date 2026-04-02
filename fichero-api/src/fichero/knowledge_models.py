"""Knowledge graph models for 0.0.2 Search + Semantic backend slices."""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


def _new_id() -> str:
    return uuid4().hex


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
    # --- multi-source ---
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)  # additional source doc IDs
    source_page_labels: list[str] = Field(default_factory=list)  # pages per source
    source_languages: list[str] = Field(default_factory=list)  # languages per source
    # --- claim classification ---
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None
    # --- provenance & confidence ---
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # --- prediction (PyKEEN) ---
    predicted_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    predicted_by: list[str] = Field(default_factory=list)
    prediction: PredictionMetadata | None = None
    # --- metadata ---
    language: str | None = None
    metadata: dict = Field(default_factory=dict)
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
