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
    source_document_id: str
    source_segment_id: str | None = None
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_ref: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed
    confidence: float = 0.5
    predicted_confidence: float | None = None
    predicted_by: list[str] = Field(default_factory=list)
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
