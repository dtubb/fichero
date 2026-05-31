"""Hermeneutics API routes (dev tier, backend-first 0.0.2 slice)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.hermeneutics_models import (
    CircleNavigationDirection,
    FrameworkType,
    HermeneuticCircleState,
    HermesSuggestion,
    HermesSuggestionRequest,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)
from fichero.kg._common import canonical_hermeneutic_predicate
from fichero.models import HermeneuticsListResponse, HermesSuggestionListResponse


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────


class FrameworkDeactivatedResponse(BaseModel):
    status: str


class FrameworkCreateRequest(BaseModel):
    name: str
    framework_type: FrameworkType
    description: str
    core_questions: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    typical_applications: list[str] = Field(default_factory=list)
    origin: str | None = None
    creator: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameworkUpdateRequest(BaseModel):
    name: str | None = None
    framework_type: FrameworkType | None = None
    description: str | None = None
    core_questions: list[str] | None = None
    key_concepts: list[str] | None = None
    typical_applications: list[str] | None = None
    origin: str | None = None
    creator: str | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class InterpretationCreateRequest(BaseModel):
    framework_id: str
    claim_id: str | None = None
    document_id: str | None = None
    passage_text: str | None = None
    interpretation_text: str
    act: InterpretiveActType
    predicate: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    key_insights: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(default_factory=list)
    connections: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "human"


class InterpretationUpdateRequest(BaseModel):
    interpretation_text: str | None = None
    act: InterpretiveActType | None = None
    predicate: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    key_insights: list[str] | None = None
    tensions: list[str] | None = None
    connections: list[str] | None = None
    metadata: dict[str, Any] | None = None


class PatternCreateRequest(BaseModel):
    name: str
    description: str
    pattern_type: str
    claim_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    frequency: int = 0
    significance: float = Field(default=0.5, ge=0.0, le=1.0)
    status: PatternStatus = PatternStatus.tentative
    framework_id: str | None = None
    supporting_passages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatternUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    pattern_type: str | None = None
    claim_ids: list[str] | None = None
    entity_ids: list[str] | None = None
    frequency: int | None = None
    significance: float | None = Field(default=None, ge=0.0, le=1.0)
    status: PatternStatus | None = None
    framework_id: str | None = None
    supporting_passages: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TaxonomyItem(BaseModel):
    value: str
    label: str


class MethodTaxonomyResponse(BaseModel):
    """Picker values for the interpretation editor (acts + framework types)."""

    acts: list[TaxonomyItem]
    frameworks: list[TaxonomyItem]


class CircleStateCreateRequest(BaseModel):
    claim_id: str
    current_focus: str  # "part" or "whole"
    focus_id: str
    focus_label: str
    direction: CircleNavigationDirection
    metadata: dict[str, Any] = Field(default_factory=dict)


class CircleStateNavigateRequest(BaseModel):
    direction: CircleNavigationDirection
    focus_id: str
    focus_label: str


# ─────────────────────────────────────────────────────────────────────────────
# Framework CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/frameworks", response_model=InterpretiveFramework)
async def create_framework(
    request: FrameworkCreateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    now = datetime.now()
    framework = InterpretiveFramework(
        name=request.name.strip(),
        framework_type=request.framework_type,
        description=request.description.strip(),
        core_questions=list(request.core_questions),
        key_concepts=list(request.key_concepts),
        typical_applications=list(request.typical_applications),
        origin=request.origin,
        creator=request.creator,
        language=request.language,
        metadata=dict(request.metadata),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.save(framework)
    return framework


@router.get("/frameworks", response_model=HermeneuticsListResponse)
async def list_frameworks(
    framework_type: FrameworkType | None = None,
    is_active: bool | None = None,
    db: Database = Depends(get_library_database),
) -> list[InterpretiveFramework]:
    rows = db.all(InterpretiveFramework)
    if framework_type is not None:
        rows = [r for r in rows if r.framework_type == framework_type]
    if is_active is not None:
        rows = [r for r in rows if r.is_active == is_active]
    return HermeneuticsListResponse(items=rows, count=len(rows))


@router.get("/frameworks/{framework_id}", response_model=InterpretiveFramework)
async def get_framework(
    framework_id: str,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    framework = db.get(InterpretiveFramework, framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {framework_id}"
        )
    return framework


@router.patch("/frameworks/{framework_id}", response_model=InterpretiveFramework)
async def update_framework(
    framework_id: str,
    request: FrameworkUpdateRequest,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    framework = db.get(InterpretiveFramework, framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {framework_id}"
        )

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(framework, key, value)
    framework.updated_at = datetime.now()
    db.save(framework)
    return framework


@router.delete("/frameworks/{framework_id}")
async def delete_framework(
    framework_id: str,
    db: Database = Depends(get_library_database),
) -> FrameworkDeactivatedResponse:
    framework = db.get(InterpretiveFramework, framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {framework_id}"
        )
    # Soft-delete: deactivate
    framework.is_active = False
    framework.updated_at = datetime.now()
    db.save(framework)
    return FrameworkDeactivatedResponse(status="deactivated")


# ─────────────────────────────────────────────────────────────────────────────
# Interpretation CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/interpretations", response_model=Interpretation)
async def create_interpretation(
    request: InterpretationCreateRequest,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    framework = db.get(InterpretiveFramework, request.framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {request.framework_id}"
        )
    if not framework.is_active:
        raise HTTPException(status_code=400, detail="Framework is not active")

    if not request.claim_id:
        raise HTTPException(
            status_code=400,
            detail="claim_id is required",
        )

    now = datetime.now()
    interpretation = Interpretation(
        framework_id=request.framework_id,
        claim_id=request.claim_id,
        document_id=request.document_id,
        passage_text=request.passage_text,
        interpretation_text=request.interpretation_text.strip(),
        act=request.act,
        predicate=(request.predicate or "").strip(),
        predicate_canonical=canonical_hermeneutic_predicate(request.predicate),
        confidence=request.confidence,
        key_insights=list(request.key_insights),
        tensions=list(request.tensions),
        connections=list(request.connections),
        metadata=dict(request.metadata),
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
    )
    db.save(interpretation)
    return interpretation


@router.get("/interpretations", response_model=HermeneuticsListResponse)
async def list_interpretations(
    framework_id: str | None = None,
    claim_id: str | None = None,
    document_id: str | None = None,
    act: InterpretiveActType | None = None,
    db: Database = Depends(get_library_database),
) -> list[Interpretation]:
    rows = db.all(Interpretation)
    if framework_id is not None:
        rows = [r for r in rows if r.framework_id == framework_id]
    if claim_id is not None:
        rows = [r for r in rows if r.claim_id == claim_id]
    if document_id is not None:
        rows = [r for r in rows if r.document_id == document_id]
    if act is not None:
        rows = [r for r in rows if r.act == act]
    return HermeneuticsListResponse(items=rows, count=len(rows))


@router.get("/interpretations/{interpretation_id}", response_model=Interpretation)
async def get_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )
    return interpretation


@router.patch("/interpretations/{interpretation_id}", response_model=Interpretation)
async def update_interpretation(
    interpretation_id: str,
    request: InterpretationUpdateRequest,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    interpretation = db.get(Interpretation, interpretation_id)
    if not interpretation:
        raise HTTPException(
            status_code=404, detail=f"Interpretation not found: {interpretation_id}"
        )

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    if "predicate" in updates:
        updates["predicate"] = str(updates["predicate"] or "").strip()
        updates["predicate_canonical"] = canonical_hermeneutic_predicate(
            updates["predicate"]
        )
    for key, value in updates.items():
        setattr(interpretation, key, value)
    interpretation.updated_at = datetime.now()
    db.save(interpretation)
    return interpretation


# ─────────────────────────────────────────────────────────────────────────────
# Pattern CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/patterns", response_model=PatternInstance)
async def create_pattern(
    request: PatternCreateRequest,
    db: Database = Depends(get_library_database),
) -> PatternInstance:
    now = datetime.now()
    pattern = PatternInstance(
        name=request.name.strip(),
        description=request.description.strip(),
        pattern_type=request.pattern_type.strip(),
        claim_ids=list(request.claim_ids),
        entity_ids=list(request.entity_ids),
        frequency=request.frequency,
        significance=request.significance,
        status=request.status,
        framework_id=request.framework_id,
        supporting_passages=list(request.supporting_passages),
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(pattern)
    return pattern


@router.get("/patterns", response_model=HermeneuticsListResponse)
async def list_patterns(
    pattern_type: str | None = None,
    status: PatternStatus | None = None,
    framework_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[PatternInstance]:
    rows = db.all(PatternInstance)
    if pattern_type is not None:
        rows = [r for r in rows if r.pattern_type == pattern_type]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    if framework_id is not None:
        rows = [r for r in rows if r.framework_id == framework_id]
    return HermeneuticsListResponse(items=rows, count=len(rows))


@router.get("/patterns/{pattern_id}", response_model=PatternInstance)
async def get_pattern(
    pattern_id: str,
    db: Database = Depends(get_library_database),
) -> PatternInstance:
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")
    return pattern


@router.patch("/patterns/{pattern_id}", response_model=PatternInstance)
async def update_pattern(
    pattern_id: str,
    request: PatternUpdateRequest,
    db: Database = Depends(get_library_database),
) -> PatternInstance:
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(pattern, key, value)
    pattern.updated_at = datetime.now()
    db.save(pattern)
    return pattern


@router.post("/patterns/{pattern_id}/claims/{claim_id}", response_model=PatternInstance)
async def add_claim_to_pattern(
    pattern_id: str,
    claim_id: str,
    db: Database = Depends(get_library_database),
) -> PatternInstance:
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")
    if claim_id not in pattern.claim_ids:
        pattern.claim_ids = pattern.claim_ids + [claim_id]
        pattern.frequency = len(pattern.claim_ids)
        pattern.updated_at = datetime.now()
        db.save(pattern)
    return pattern


# ─────────────────────────────────────────────────────────────────────────────
# Hermeneutic Circle State
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/circle-state", response_model=HermeneuticCircleState)
async def create_circle_state(
    request: CircleStateCreateRequest,
    db: Database = Depends(get_library_database),
) -> HermeneuticCircleState:
    now = datetime.now()
    state = HermeneuticCircleState(
        claim_id=request.claim_id,
        current_focus=request.current_focus,
        focus_id=request.focus_id,
        focus_label=request.focus_label,
        direction=request.direction,
        circle_level=0,
        navigation_log=[f"Started at {request.current_focus}: {request.focus_label}"],
        metadata=dict(request.metadata),
        created_at=now,
        updated_at=now,
    )
    db.save(state)
    return state


@router.get("/circle-state", response_model=HermeneuticsListResponse)
async def list_circle_states(
    claim_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> list[HermeneuticCircleState]:
    rows = db.all(HermeneuticCircleState)
    if claim_id is not None:
        rows = [r for r in rows if r.claim_id == claim_id]
    return HermeneuticsListResponse(items=rows, count=len(rows))


@router.get("/circle-state/{state_id}", response_model=HermeneuticCircleState)
async def get_circle_state(
    state_id: str,
    db: Database = Depends(get_library_database),
) -> HermeneuticCircleState:
    state = db.get(HermeneuticCircleState, state_id)
    if not state:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {state_id}"
        )
    return state


@router.post("/circle-state/{state_id}/navigate", response_model=HermeneuticCircleState)
async def navigate_circle(
    state_id: str,
    request: CircleStateNavigateRequest,
    db: Database = Depends(get_library_database),
) -> HermeneuticCircleState:
    state = db.get(HermeneuticCircleState, state_id)
    if not state:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {state_id}"
        )

    # Record prior state for backtracking
    prior_focus = state.focus_label
    state.prior_state_id = state_id
    # Navigate TO whole or part — direction tells us the destination
    state.current_focus = (
        "part"
        if request.direction == CircleNavigationDirection.whole_to_part
        else "whole"
    )
    state.focus_id = request.focus_id
    state.focus_label = request.focus_label
    state.direction = request.direction
    state.circle_level += 1
    state.navigation_log = state.navigation_log + [
        f"Move {state.circle_level}: {prior_focus} → {request.focus_label} ({request.direction.value})"
    ]
    state.updated_at = datetime.now()
    db.save(state)
    return state


@router.post(
    "/circle-state/{state_id}/backtrack", response_model=HermeneuticCircleState
)
async def backtrack_circle(
    state_id: str,
    db: Database = Depends(get_library_database),
) -> HermeneuticCircleState:
    state = db.get(HermeneuticCircleState, state_id)
    if not state:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {state_id}"
        )
    if not state.prior_state_id:
        raise HTTPException(status_code=400, detail="No prior state to backtrack to")

    prior = db.get(HermeneuticCircleState, state.prior_state_id)
    if prior:
        state.circle_level -= 1
        state.navigation_log = state.navigation_log + [
            f"Backtrack to level {state.circle_level}"
        ]
        state.updated_at = datetime.now()
        db.save(state)
    return state


# ─────────────────────────────────────────────────────────────────────────────
# AI Interpretation Suggestions (placeholder — requires LiteLLM integration)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/suggestions", response_model=HermesSuggestionListResponse)
async def suggest_interpretations(
    request: HermesSuggestionRequest,
    db: Database = Depends(get_library_database),
) -> HermesSuggestionListResponse:
    """Generate AI interpretation suggestions for claims.

    Uses available LiteLLM providers to suggest how frameworks might
    be applied to the given claims. Returns ranked suggestions.
    """
    if request.num_suggestions < 1 or request.num_suggestions > 10:
        raise HTTPException(
            status_code=400, detail="num_suggestions must be between 1 and 10"
        )

    # Load requested frameworks (or all active if none specified)
    if request.framework_ids:
        frameworks = [
            db.get(InterpretiveFramework, fid) for fid in request.framework_ids
        ]
        frameworks = [f for f in frameworks if f and f.is_active]
    else:
        frameworks = [f for f in db.all(InterpretiveFramework) if f.is_active]

    if not frameworks:
        raise HTTPException(status_code=400, detail="No active frameworks available")

    suggestions: list[HermesSuggestion] = []

    for framework in frameworks[: request.num_suggestions]:
        suggestion = HermesSuggestion(
            framework_id=framework.id,
            framework_name=framework.name,
            interpretation_text=(
                f"Apply {framework.name} ({framework.framework_type.value}) framework: "
                f"{framework.description[:200]}..."
            ),
            confidence=0.5,
            reasoning=(
                f"Framework '{framework.name}' is relevant based on its "
                f"core questions: {'; '.join(framework.core_questions[:2])}"
            ),
            act=InterpretiveActType.contextualizing,
            key_insights=framework.key_concepts[:3],
        )
        suggestions.append(suggestion)

    return HermesSuggestionListResponse(items=suggestions, count=len(suggestions))


# ─────────────────────────────────────────────────────────────────────────────
# Taxonomy picker (merged from kg_interpretations.py #1126)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/taxonomy/methods",
    response_model=MethodTaxonomyResponse,
    summary="Picker values for interpretation editor (acts + framework types)",
)
async def get_taxonomy() -> MethodTaxonomyResponse:
    acts = [
        TaxonomyItem(value=act.value, label=act.name.replace("_", " ").title())
        for act in InterpretiveActType
    ]
    frameworks = [
        TaxonomyItem(value=ft.value, label=ft.name.replace("_", " ").title())
        for ft in FrameworkType
    ]
    return MethodTaxonomyResponse(acts=acts, frameworks=frameworks)
