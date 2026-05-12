"""Interpretation + InterpretiveFramework CRUD (#905).

The hermeneutics layer lives in fichero/hermeneutics_models.py
but wasn't wired into the API surface. These endpoints expose
the existing models so the Swift inspector can render and edit
interpretations attached to claims.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.hermeneutics_models import (
    FrameworkType,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kg/interpretations", tags=["knowledge-graph"])


# =============================================================================
# Frameworks — the lenses
# =============================================================================


class FrameworkRequest(BaseModel):
    name: str
    framework_type: FrameworkType
    description: str
    core_questions: list[str] = []
    key_concepts: list[str] = []
    typical_applications: list[str] = []
    origin: str | None = None
    creator: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = {}


@router.post(
    "/frameworks",
    response_model=InterpretiveFramework,
    summary="Create an interpretive framework (e.g. 'Marxist historical materialism')",
)
async def create_framework(
    request: FrameworkRequest,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    fw = InterpretiveFramework(**request.model_dump())
    db.save(fw)
    return fw


@router.get(
    "/frameworks",
    response_model=list[InterpretiveFramework],
)
async def list_frameworks(
    db: Database = Depends(get_library_database),
) -> list[InterpretiveFramework]:
    return db.query(InterpretiveFramework)


@router.get(
    "/frameworks/{framework_id}",
    response_model=InterpretiveFramework,
)
async def get_framework(
    framework_id: str,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    fw = db.get(InterpretiveFramework, framework_id)
    if fw is None:
        raise HTTPException(404, f"Framework not found: {framework_id}")
    return fw


class FrameworkPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    core_questions: list[str] | None = None
    key_concepts: list[str] | None = None
    typical_applications: list[str] | None = None
    origin: str | None = None
    creator: str | None = None
    is_active: bool | None = None


@router.patch(
    "/frameworks/{framework_id}",
    response_model=InterpretiveFramework,
)
async def patch_framework(
    framework_id: str,
    request: FrameworkPatchRequest,
    db: Database = Depends(get_library_database),
) -> InterpretiveFramework:
    fw = db.get(InterpretiveFramework, framework_id)
    if fw is None:
        raise HTTPException(404, f"Framework not found: {framework_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(fw, field, value)
    fw.updated_at = datetime.now()
    db.save(fw)
    return fw


@router.delete("/frameworks/{framework_id}", status_code=204)
async def delete_framework(
    framework_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    fw = db.get(InterpretiveFramework, framework_id)
    if fw is None:
        raise HTTPException(404, f"Framework not found: {framework_id}")
    db.delete(fw)


# =============================================================================
# Interpretations — the readings
# =============================================================================


class InterpretationRequest(BaseModel):
    framework_id: str
    interpretation_text: str
    act: InterpretiveActType
    claim_id: str | None = None
    document_id: str | None = None
    passage_text: str | None = None
    confidence: float = 0.5
    key_insights: list[str] = []
    tensions: list[str] = []
    connections: list[str] = []
    metadata: dict[str, Any] = {}


@router.post(
    "",
    response_model=Interpretation,
    summary="Create an interpretation — the result of applying a framework to evidence",
)
async def create_interpretation(
    request: InterpretationRequest,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    # Verify the framework exists.
    if db.get(InterpretiveFramework, request.framework_id) is None:
        raise HTTPException(400, f"Framework not found: {request.framework_id}")
    interp = Interpretation(**request.model_dump())
    db.save(interp)
    return interp


@router.get("", response_model=list[Interpretation])
async def list_interpretations(
    framework_id: str | None = Query(default=None),
    claim_id: str | None = Query(default=None),
    document_id: str | None = Query(default=None),
    db: Database = Depends(get_library_database),
) -> list[Interpretation]:
    rows = db.query(Interpretation)
    if framework_id is not None:
        rows = [r for r in rows if r.framework_id == framework_id]
    if claim_id is not None:
        rows = [r for r in rows if r.claim_id == claim_id]
    if document_id is not None:
        rows = [r for r in rows if r.document_id == document_id]
    return rows


@router.get("/{interpretation_id}", response_model=Interpretation)
async def get_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    interp = db.get(Interpretation, interpretation_id)
    if interp is None:
        raise HTTPException(404, f"Interpretation not found: {interpretation_id}")
    return interp


class InterpretationPatchRequest(BaseModel):
    interpretation_text: str | None = None
    act: InterpretiveActType | None = None
    confidence: float | None = None
    key_insights: list[str] | None = None
    tensions: list[str] | None = None
    connections: list[str] | None = None


@router.patch("/{interpretation_id}", response_model=Interpretation)
async def patch_interpretation(
    interpretation_id: str,
    request: InterpretationPatchRequest,
    db: Database = Depends(get_library_database),
) -> Interpretation:
    interp = db.get(Interpretation, interpretation_id)
    if interp is None:
        raise HTTPException(404, f"Interpretation not found: {interpretation_id}")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(interp, field, value)
    interp.updated_at = datetime.now()
    db.save(interp)
    return interp


@router.delete("/{interpretation_id}", status_code=204)
async def delete_interpretation(
    interpretation_id: str,
    db: Database = Depends(get_library_database),
) -> None:
    interp = db.get(Interpretation, interpretation_id)
    if interp is None:
        raise HTTPException(404, f"Interpretation not found: {interpretation_id}")
    db.delete(interp)
