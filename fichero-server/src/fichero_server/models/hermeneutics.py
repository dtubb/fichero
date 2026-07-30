"""Hermeneutics models for 0.0.2 Layer 5 — interpretation, patterns, meaning."""

from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


def _new_id() -> str:
    return uuid4().hex


class FrameworkType(str, Enum):
    """Interpretive lens categories."""

    historical = "historical"  # Diachronic analysis, change over time
    disciplinary = "disciplinary"  # Field-specific methodology
    thematic = "thematic"  # Recurring motifs and ideas
    methodological = "methodological"  # Approach to inquiry
    theoretical = "theoretical"  # Abstract frameworks
    narrative = "narrative"  # Story structure and plot


class InterpretiveActType(str, Enum):
    """Types of interpretive operations."""

    reading = "reading"  # Surface-level comprehension
    translating = "translating"  # Converting between contexts
    contextualizing = "contextualizing"  # Placing in broader context
    synthesizing = "synthesizing"  # Drawing together threads
    critiquing = "critiquing"  # Evaluating strengths/weaknesses
    applying = "applying"  # Using framework to interpret


class PatternStatus(str, Enum):
    """Lifecycle state of a recognized pattern."""

    tentative = "tentative"
    confirmed = "confirmed"
    superseded = "superseded"


class CircleNavigationDirection(str, Enum):
    """Movement through the hermeneutic circle."""

    part_to_whole = "part_to_whole"
    whole_to_part = "whole_to_part"


class InterpretiveFramework(BaseModel):
    """An interpretive lens applied to claims and evidence.

    Frameworks are reusable lenses that shape how evidence is interpreted.
    Example: "Marxist historical materialism" as a framework for analyzing
    labor relations in historical documents.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    framework_type: FrameworkType
    description: str
    core_questions: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    typical_applications: list[str] = Field(default_factory=list)
    origin: str | None = None  # Where the framework comes from
    creator: str | None = None  # Who articulated it
    language: str | None = None
    metadata: dict = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Interpretation(BaseModel):
    """An interpretation — the result of applying a framework to evidence.

    An interpretation is always about something (the claim or passage)
    and from the perspective of a specific framework.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    framework_id: str
    claim_id: str | None = None  # The claim being interpreted
    document_id: str | None = None  # Or a document/passage
    passage_text: str | None = None  # The specific text if not a stored claim
    interpretation_text: str  # What this means under the framework
    act: InterpretiveActType
    predicate: str = ""  # Raw/human-typed interpretive predicate (centers, contests_reading, etc)
    predicate_canonical: str | None = None  # Normalized form from HERMENEUTIC_PREDICATES
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    key_insights: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(
        default_factory=list
    )  # Places where framework struggles
    connections: list[str] = Field(
        default_factory=list
    )  # Links to other interpretations
    metadata: dict = Field(default_factory=dict)
    created_by: str = "human"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PatternInstance(BaseModel):
    """A recognized pattern occurring across multiple claims or documents.

    Patterns are recurring structures, motifs, or relationships observed
    in the evidence. Example: "cyclical theory of history" appearing
    across multiple historiographical claims.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    name: str
    description: str
    pattern_type: str  # e.g., "temporal", "causal", "structural", "thematic"
    claim_ids: list[str] = Field(default_factory=list)  # Claims exhibiting this pattern
    entity_ids: list[str] = Field(default_factory=list)  # Entities involved
    frequency: int = 0  # Number of occurrences
    significance: float = Field(default=0.5, ge=0.0, le=1.0)  # How important
    status: PatternStatus = PatternStatus.tentative
    framework_id: str | None = None  # If recognized via a specific framework
    supporting_passages: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HermeneuticCircleState(BaseModel):
    """Tracks navigation between parts and wholes in interpretive analysis.

    The hermeneutic circle describes the iterative process of understanding:
    understanding parts through wholes, and wholes through parts.
    This model tracks where the analyst is in that navigation.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: str = Field(default_factory=_new_id)
    claim_id: str  # The focal claim in this navigation
    current_focus: str  # "part" or "whole"
    focus_id: str  # ID of the currently focused element
    focus_label: str  # Human-readable description
    direction: CircleNavigationDirection
    circle_level: int = 0  # Depth in the navigation
    prior_state_id: str | None = None  # For backtracking
    navigation_log: list[str] = Field(default_factory=list)  # History of moves
    interpretation_id: str | None = None  # Resulting interpretation
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class HermesSuggestionRequest(BaseModel):
    """Request for AI interpretation suggestions."""

    claim_ids: list[str]
    framework_ids: list[str] = Field(default_factory=list)
    context_claim_ids: list[str] = Field(default_factory=list)  # Surrounding claims
    num_suggestions: int = Field(default=3, ge=1, le=10)


class HermesSuggestion(BaseModel):
    """A single AI-generated interpretation suggestion."""

    framework_id: str
    framework_name: str
    interpretation_text: str
    confidence: float
    reasoning: str
    act: InterpretiveActType
    key_insights: list[str] = Field(default_factory=list)


__all__ = [name for name in globals() if not name.startswith("__")]
