"""Hermeneutics API routes (dev tier, backend-first 0.0.2 slice)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.auth import action_context
from fichero_server.actions.registry import registry
from fichero_server.db import Database
from fichero_server.models.hermeneutics import (
    CircleNavigationDirection,
    FrameworkType,
    HermeneuticCircleState,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)
from fichero_server.kg._common import canonical_hermeneutic_predicate
from fichero_server.models.knowledge import KnowledgeClaim


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


class FrameworkListResponse(BaseModel):
    items: list[InterpretiveFramework]
    count: int


class InterpretationListResponse(BaseModel):
    items: list[Interpretation]
    count: int


class PatternListResponse(BaseModel):
    items: list[PatternInstance]
    count: int


class CircleStateListResponse(BaseModel):
    items: list[HermeneuticCircleState]
    count: int


# ─────────────────────────────────────────────────────────────────────────────
# Framework CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_framework_impl(
    db: Database, request: FrameworkCreateRequest
) -> InterpretiveFramework:
    """Build + persist an interpretive framework (no emit — caller emits).

    Extracted so the typed route and the audited ``framework.create`` action
    run the SAME mutation (EPIC #1848 / #2014). The change event stays in the
    route (UI path); ``registry.invoke`` emits the equivalent event on the
    /api/actions/invoke path.
    """
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


@router.post("/frameworks", response_model=InterpretiveFramework)
async def create_framework(
    request: FrameworkCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> InterpretiveFramework:
    result = registry.invoke(
        db,
        "framework.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return InterpretiveFramework.model_validate(result.result)


@router.get("/frameworks", response_model=FrameworkListResponse)
async def list_frameworks(
    framework_type: FrameworkType | None = None,
    is_active: bool | None = None,
    db: Database = Depends(get_library_database),
) -> FrameworkListResponse:
    rows = db.all(InterpretiveFramework)
    if framework_type is not None:
        rows = [r for r in rows if r.framework_type == framework_type]
    if is_active is not None:
        rows = [r for r in rows if r.is_active == is_active]
    return FrameworkListResponse(items=rows, count=len(rows))


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


def update_framework_impl(
    db: Database, framework_id: str, request: FrameworkUpdateRequest
) -> InterpretiveFramework:
    """Apply a partial framework edit (404 if missing). Shared route/action path."""
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


@router.patch("/frameworks/{framework_id}", response_model=InterpretiveFramework)
async def update_framework(
    framework_id: str,
    request: FrameworkUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> InterpretiveFramework:
    result = registry.invoke(
        db,
        "framework.update",
        {"framework_id": framework_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return InterpretiveFramework.model_validate(result.result)


def delete_framework_impl(db: Database, framework_id: str) -> InterpretiveFramework:
    """Soft-delete (deactivate) a framework; returns it. Shared route/action path.

    The delete is a deactivation (``is_active=False``), so its inverse is simply
    re-activation — ``framework.delete`` is undoable via ``framework.update``.
    """
    framework = db.get(InterpretiveFramework, framework_id)
    if not framework:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {framework_id}"
        )
    # Soft-delete: deactivate
    framework.is_active = False
    framework.updated_at = datetime.now()
    db.save(framework)
    return framework


@router.delete("/frameworks/{framework_id}")
async def delete_framework(
    framework_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> FrameworkDeactivatedResponse:
    registry.invoke(db, "framework.delete", {"framework_id": framework_id}, ctx)
    return FrameworkDeactivatedResponse(status="deactivated")


# ─────────────────────────────────────────────────────────────────────────────
# Interpretation CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_interpretation_impl(
    db: Database, request: InterpretationCreateRequest
) -> Interpretation:
    """Validate + persist an interpretation (no emit — caller emits).

    Preserves the route's guards exactly: framework must exist and be active,
    ``claim_id`` is required and must resolve. Shared route/action path.
    """
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
    claim = db.get(KnowledgeClaim, request.claim_id)
    if claim is None:
        raise HTTPException(
            status_code=404,
            detail=f"Claim not found: {request.claim_id}",
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


@router.post("/interpretations", response_model=Interpretation)
async def create_interpretation(
    request: InterpretationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Interpretation:
    result = registry.invoke(
        db,
        "interpretation.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return Interpretation.model_validate(result.result)


@router.get("/interpretations", response_model=InterpretationListResponse)
async def list_interpretations(
    framework_id: str | None = None,
    claim_id: str | None = None,
    document_id: str | None = None,
    act: InterpretiveActType | None = None,
    db: Database = Depends(get_library_database),
) -> InterpretationListResponse:
    rows = db.all(Interpretation)
    if framework_id is not None:
        rows = [r for r in rows if r.framework_id == framework_id]
    if claim_id is not None:
        rows = [r for r in rows if r.claim_id == claim_id]
    if document_id is not None:
        rows = [r for r in rows if r.document_id == document_id]
    if act is not None:
        rows = [r for r in rows if r.act == act]
    return InterpretationListResponse(items=rows, count=len(rows))


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


def update_interpretation_impl(
    db: Database, interpretation_id: str, request: InterpretationUpdateRequest
) -> Interpretation:
    """Apply a partial interpretation edit (404 if missing). Shared route/action path.

    Keeps the predicate-canonicalization side effect: editing ``predicate`` also
    recomputes ``predicate_canonical``.
    """
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


@router.patch("/interpretations/{interpretation_id}", response_model=Interpretation)
async def update_interpretation(
    interpretation_id: str,
    request: InterpretationUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Interpretation:
    result = registry.invoke(
        db,
        "interpretation.update",
        {
            "interpretation_id": interpretation_id,
            **request.model_dump(mode="json", exclude_unset=True),
        },
        ctx,
    )
    return Interpretation.model_validate(result.result)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_pattern_impl(db: Database, request: PatternCreateRequest) -> PatternInstance:
    """Build + persist a pattern instance (no emit — caller emits). Shared path."""
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


@router.post("/patterns", response_model=PatternInstance)
async def create_pattern(
    request: PatternCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PatternInstance:
    result = registry.invoke(
        db,
        "pattern.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return PatternInstance.model_validate(result.result)


@router.get("/patterns", response_model=PatternListResponse)
async def list_patterns(
    pattern_type: str | None = None,
    status: PatternStatus | None = None,
    framework_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> PatternListResponse:
    rows = db.all(PatternInstance)
    if pattern_type is not None:
        rows = [r for r in rows if r.pattern_type == pattern_type]
    if status is not None:
        rows = [r for r in rows if r.status == status]
    if framework_id is not None:
        rows = [r for r in rows if r.framework_id == framework_id]
    return PatternListResponse(items=rows, count=len(rows))


@router.get("/patterns/{pattern_id}", response_model=PatternInstance)
async def get_pattern(
    pattern_id: str,
    db: Database = Depends(get_library_database),
) -> PatternInstance:
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")
    return pattern


def update_pattern_impl(
    db: Database, pattern_id: str, request: PatternUpdateRequest
) -> PatternInstance:
    """Apply a partial pattern edit (404 if missing). Shared route/action path."""
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")

    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in updates.items():
        setattr(pattern, key, value)
    pattern.updated_at = datetime.now()
    db.save(pattern)
    return pattern


@router.patch("/patterns/{pattern_id}", response_model=PatternInstance)
async def update_pattern(
    pattern_id: str,
    request: PatternUpdateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PatternInstance:
    result = registry.invoke(
        db,
        "pattern.update",
        {"pattern_id": pattern_id, **request.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    return PatternInstance.model_validate(result.result)


def add_claim_to_pattern_impl(
    db: Database, pattern_id: str, claim_id: str
) -> tuple[PatternInstance, bool]:
    """Append a claim to a pattern (idempotent); returns (pattern, changed).

    ``changed`` is False when the claim is already a member, so the caller can
    skip the emit — preserving the route's conditional-broadcast behavior.
    """
    pattern = db.get(PatternInstance, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern not found: {pattern_id}")
    if claim_id in pattern.claim_ids:
        return pattern, False
    pattern.claim_ids = pattern.claim_ids + [claim_id]
    pattern.frequency = len(pattern.claim_ids)
    pattern.updated_at = datetime.now()
    db.save(pattern)
    return pattern, True


@router.post("/patterns/{pattern_id}/claims/{claim_id}", response_model=PatternInstance)
async def add_claim_to_pattern(
    pattern_id: str,
    claim_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PatternInstance:
    result = registry.invoke(
        db,
        "pattern.add_claim",
        {"pattern_id": pattern_id, "claim_id": claim_id},
        ctx,
    )
    return PatternInstance.model_validate(result.result)


# ─────────────────────────────────────────────────────────────────────────────
# Hermeneutic Circle State
# ─────────────────────────────────────────────────────────────────────────────


def create_circle_state_impl(
    db: Database, request: CircleStateCreateRequest
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


@router.post("/circle-state", response_model=HermeneuticCircleState)
async def create_circle_state(
    request: CircleStateCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> HermeneuticCircleState:
    result = registry.invoke(
        db,
        "circle_state.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return HermeneuticCircleState.model_validate(result.result)


@router.get("/circle-state", response_model=CircleStateListResponse)
async def list_circle_states(
    claim_id: str | None = None,
    db: Database = Depends(get_library_database),
) -> CircleStateListResponse:
    rows = db.all(HermeneuticCircleState)
    if claim_id is not None:
        rows = [r for r in rows if r.claim_id == claim_id]
    return CircleStateListResponse(items=rows, count=len(rows))


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


def navigate_circle_impl(
    db: Database, state_id: str, request: CircleStateNavigateRequest
) -> HermeneuticCircleState:
    state = db.get(HermeneuticCircleState, state_id)
    if not state:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {state_id}"
        )

    prior_focus = state.focus_label
    state.prior_state_id = state_id
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


@router.post("/circle-state/{state_id}/navigate", response_model=HermeneuticCircleState)
async def navigate_circle(
    state_id: str,
    request: CircleStateNavigateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> HermeneuticCircleState:
    result = registry.invoke(
        db,
        "circle_state.navigate",
        {"state_id": state_id, **request.model_dump(mode="json")},
        ctx,
    )
    return HermeneuticCircleState.model_validate(result.result)


def backtrack_circle_impl(db: Database, state_id: str) -> HermeneuticCircleState:
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


@router.post(
    "/circle-state/{state_id}/backtrack", response_model=HermeneuticCircleState
)
async def backtrack_circle(
    state_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> HermeneuticCircleState:
    result = registry.invoke(
        db,
        "circle_state.backtrack",
        {"state_id": state_id},
        ctx,
    )
    return HermeneuticCircleState.model_validate(result.result)


# /suggestions (grounded AI interpretation suggestions) was a permanent-501
# stub with no caller — deleted in the endpoint cleanup (2026-07-27); build
# the real thing against the audited action layer when the feature lands.


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


# ─────────────────────────────────────────────────────────────────────────────
# Action layer registration (EPIC #1848 / sweep #2014) — interpretation/ontology
# ─────────────────────────────────────────────────────────────────────────────
#
# Each framework / interpretation / pattern mutation becomes a registered,
# audited action that WRAPS the proven ``*_impl`` above. The typed routes stay
# untouched and keep emitting their existing ``interpretation.*`` change events
# (the UI path, from #2008); the action emits the SAME event type on the
# /api/actions/invoke path via ``registry.invoke`` — so each caller emits exactly
# once, no double-broadcast. Edits and the (soft) framework delete are undoable:
# ``before``/``after`` snapshots ARE the undo payload. Creates are not undoable
# (interpretations/patterns have no delete route; a framework "delete" is a
# deactivation, so create's only honest inverse would be a partial soft-delete).

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


# Patchable field sets used by the invert helpers to restore prior state.
_FRAMEWORK_FIELDS = (
    "name",
    "framework_type",
    "description",
    "core_questions",
    "key_concepts",
    "typical_applications",
    "origin",
    "creator",
    "language",
    "metadata",
    "is_active",
)
_INTERPRETATION_FIELDS = (
    "interpretation_text",
    "act",
    "predicate",
    "confidence",
    "key_insights",
    "tensions",
    "connections",
    "metadata",
)
_PATTERN_FIELDS = (
    "name",
    "description",
    "pattern_type",
    "claim_ids",
    "entity_ids",
    "frequency",
    "significance",
    "status",
    "framework_id",
    "supporting_passages",
    "metadata",
)


def _restore_params(before: dict, fields: tuple[str, ...], id_field: str) -> dict:
    """Build update-action params that restore the pre-edit field values.

    ``update_*_impl`` applies ``exclude_none=True``, so None-valued fields can't
    be reset through this path — an accepted limitation that mirrors the route's
    own PATCH semantics. Non-None prior values are faithfully restored.
    """
    params = {id_field: before["id"]}
    for key in fields:
        val = before.get(key)
        if val is not None:
            params[key] = val
    return params


class FrameworkUpdateParams(FrameworkUpdateRequest):
    framework_id: str


class FrameworkDeleteParams(BaseModel):
    framework_id: str


class InterpretationUpdateParams(InterpretationUpdateRequest):
    interpretation_id: str


class PatternUpdateParams(PatternUpdateRequest):
    pattern_id: str


class PatternAddClaimParams(BaseModel):
    pattern_id: str
    claim_id: str


class CircleStateNavigateParams(CircleStateNavigateRequest):
    state_id: str


class CircleStateBacktrackParams(BaseModel):
    state_id: str


# -- frameworks --------------------------------------------------------------


@action(
    "framework.create",
    FrameworkCreateRequest,
    domains=["interpretation"],
    undoable=False,
)
def _action_create_framework(
    db: Database, params: FrameworkCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    framework = create_framework_impl(db, params)
    after = framework.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[framework.id],
        before=None,
        after=after,
        emit_type="interpretation.created",
        interpretation_ids=[framework.id],
    )
    return after, spec


def _invert_framework_update(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return (
        "framework.update",
        _restore_params(before, _FRAMEWORK_FIELDS, "framework_id"),
    )


@action(
    "framework.update",
    FrameworkUpdateParams,
    domains=["interpretation"],
    undoable=True,
    invert=_invert_framework_update,
)
def _action_update_framework(
    db: Database, params: FrameworkUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(InterpretiveFramework, params.framework_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {params.framework_id}"
        )
    before = existing.model_dump(mode="json")
    request = FrameworkUpdateRequest(
        **params.model_dump(exclude={"framework_id"}, exclude_unset=True)
    )
    framework = update_framework_impl(db, params.framework_id, request)
    after = framework.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[framework.id],
        before=before,
        after=after,
        emit_type="interpretation.updated",
        interpretation_ids=[framework.id],
    )
    return after, spec


def _invert_framework_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a (soft) framework delete by reactivating it."""
    if not before:
        return None
    return ("framework.update", {"framework_id": before["id"], "is_active": True})


@action(
    "framework.delete",
    FrameworkDeleteParams,
    domains=["interpretation"],
    undoable=True,
    invert=_invert_framework_delete,
)
def _action_delete_framework(
    db: Database, params: FrameworkDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(InterpretiveFramework, params.framework_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Framework not found: {params.framework_id}"
        )
    before = existing.model_dump(mode="json")
    framework = delete_framework_impl(db, params.framework_id)
    after = framework.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[framework.id],
        before=before,
        after=after,
        emit_type="interpretation.deleted",
        interpretation_ids=[framework.id],
    )
    return after, spec


# -- interpretations ---------------------------------------------------------


@action(
    "interpretation.create",
    InterpretationCreateRequest,
    domains=["interpretation"],
    undoable=False,
)
def _action_create_interpretation(
    db: Database, params: InterpretationCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    interpretation = create_interpretation_impl(db, params)
    after = interpretation.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[interpretation.id],
        before=None,
        after=after,
        emit_type="interpretation.created",
        interpretation_ids=[interpretation.id],
        document_ids=[interpretation.document_id] if interpretation.document_id else [],
        claim_ids=[interpretation.claim_id] if interpretation.claim_id else [],
    )
    return after, spec


def _invert_interpretation_update(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return (
        "interpretation.update",
        _restore_params(before, _INTERPRETATION_FIELDS, "interpretation_id"),
    )


@action(
    "interpretation.update",
    InterpretationUpdateParams,
    domains=["interpretation"],
    undoable=True,
    invert=_invert_interpretation_update,
)
def _action_update_interpretation(
    db: Database, params: InterpretationUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(Interpretation, params.interpretation_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Interpretation not found: {params.interpretation_id}",
        )
    before = existing.model_dump(mode="json")
    request = InterpretationUpdateRequest(
        **params.model_dump(exclude={"interpretation_id"}, exclude_unset=True)
    )
    interpretation = update_interpretation_impl(db, params.interpretation_id, request)
    after = interpretation.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[interpretation.id],
        before=before,
        after=after,
        emit_type="interpretation.updated",
        interpretation_ids=[interpretation.id],
        document_ids=[interpretation.document_id] if interpretation.document_id else [],
        claim_ids=[interpretation.claim_id] if interpretation.claim_id else [],
    )
    return after, spec


# -- patterns ----------------------------------------------------------------


@action(
    "pattern.create",
    PatternCreateRequest,
    domains=["interpretation"],
    undoable=False,
)
def _action_create_pattern(
    db: Database, params: PatternCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    pattern = create_pattern_impl(db, params)
    after = pattern.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[pattern.id],
        before=None,
        after=after,
        emit_type="interpretation.created",
        interpretation_ids=[pattern.id],
    )
    return after, spec


def _invert_pattern_update(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("pattern.update", _restore_params(before, _PATTERN_FIELDS, "pattern_id"))


@action(
    "pattern.update",
    PatternUpdateParams,
    domains=["interpretation"],
    undoable=True,
    invert=_invert_pattern_update,
)
def _action_update_pattern(
    db: Database, params: PatternUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(PatternInstance, params.pattern_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Pattern not found: {params.pattern_id}"
        )
    before = existing.model_dump(mode="json")
    request = PatternUpdateRequest(
        **params.model_dump(exclude={"pattern_id"}, exclude_unset=True)
    )
    pattern = update_pattern_impl(db, params.pattern_id, request)
    after = pattern.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[pattern.id],
        before=before,
        after=after,
        emit_type="interpretation.updated",
        interpretation_ids=[pattern.id],
    )
    return after, spec


@action(
    "pattern.add_claim",
    PatternAddClaimParams,
    domains=["interpretation"],
    undoable=False,
)
def _action_add_claim_to_pattern(
    db: Database, params: PatternAddClaimParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    pattern, changed = add_claim_to_pattern_impl(db, params.pattern_id, params.claim_id)
    after = pattern.model_dump(mode="json")
    # No-op (claim already a member) emits no change — matches the route.
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[pattern.id],
        before=None,
        after=after,
        emit_type="interpretation.updated" if changed else None,
        interpretation_ids=[pattern.id] if changed else [],
        claim_ids=[params.claim_id] if changed else [],
    )
    return after, spec


# -- hermeneutic circle -----------------------------------------------------


@action(
    "circle_state.create",
    CircleStateCreateRequest,
    domains=["interpretation"],
    undoable=False,
)
def _action_create_circle_state(
    db: Database, params: CircleStateCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    state = create_circle_state_impl(db, params)
    after = state.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[state.id],
        before=None,
        after=after,
        emit_type="interpretation.created",
        interpretation_ids=[state.id],
        claim_ids=[state.claim_id] if state.claim_id else [],
    )
    return after, spec


@action(
    "circle_state.navigate",
    CircleStateNavigateParams,
    domains=["interpretation"],
    undoable=False,
)
def _action_navigate_circle_state(
    db: Database, params: CircleStateNavigateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(HermeneuticCircleState, params.state_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {params.state_id}"
        )
    before = existing.model_dump(mode="json")
    state = navigate_circle_impl(
        db,
        params.state_id,
        CircleStateNavigateRequest(
            **params.model_dump(exclude={"state_id"}, exclude_unset=True)
        ),
    )
    after = state.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[state.id],
        before=before,
        after=after,
        emit_type="interpretation.updated",
        interpretation_ids=[state.id],
        claim_ids=[state.claim_id] if state.claim_id else [],
    )
    return after, spec


@action(
    "circle_state.backtrack",
    CircleStateBacktrackParams,
    domains=["interpretation"],
    undoable=False,
)
def _action_backtrack_circle_state(
    db: Database, params: CircleStateBacktrackParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(HermeneuticCircleState, params.state_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Circle state not found: {params.state_id}"
        )
    before = existing.model_dump(mode="json")
    state = backtrack_circle_impl(db, params.state_id)
    after = state.model_dump(mode="json")
    spec = ChangeSpec(
        domains=["interpretation"],
        target_ids=[state.id],
        before=before,
        after=after,
        emit_type="interpretation.updated",
        interpretation_ids=[state.id],
        claim_ids=[state.claim_id] if state.claim_id else [],
    )
    return after, spec
