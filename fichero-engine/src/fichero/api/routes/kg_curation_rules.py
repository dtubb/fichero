"""Persistent entity/claim curation rule CRUD routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
)

router = APIRouter(prefix="/kg/curation-rules")


class EntityRuleCreateRequest(BaseModel):
    rule_type: EntityResolutionRuleType
    match_canonical_name: str
    match_entity_type: EntityType | None = None
    target_canonical_name: str | None = None
    target_entity_type: EntityType | None = None
    reason: str
    created_by: str = "human"


class EntityRuleReadResponse(BaseModel):
    id: str
    rule_type: EntityResolutionRuleType
    match_canonical_name: str
    match_entity_type: EntityType | None = None
    target_canonical_name: str | None = None
    target_entity_type: EntityType | None = None
    reason: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class EntityRuleListResponse(BaseModel):
    items: list[EntityRuleReadResponse]
    count: int


class EntityRuleBatchCreateRequest(BaseModel):
    items: list[EntityRuleCreateRequest] = Field(default_factory=list)


class EntityRuleDeleteRequest(BaseModel):
    rule_id: str


class EntityRuleDeleteResponse(BaseModel):
    deleted_rule_id: str


class ClaimRuleCreateRequest(BaseModel):
    action: ClaimSuppressionRuleAction
    match_predicate_verb: str | None = None
    match_subject_name: str | None = None
    match_object_phrase: str | None = None
    suppress_is_a_copulas: bool = False
    reason: str
    created_by: str = "human"


class ClaimRuleReadResponse(BaseModel):
    id: str
    action: ClaimSuppressionRuleAction
    match_predicate_verb: str | None = None
    match_subject_name: str | None = None
    match_object_phrase: str | None = None
    suppress_is_a_copulas: bool = False
    reason: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ClaimRuleListResponse(BaseModel):
    items: list[ClaimRuleReadResponse]
    count: int


class ClaimRuleBatchCreateRequest(BaseModel):
    items: list[ClaimRuleCreateRequest] = Field(default_factory=list)


class ClaimRuleDeleteRequest(BaseModel):
    rule_id: str


class ClaimRuleDeleteResponse(BaseModel):
    deleted_rule_id: str


def _entity_rule_response(rule: EntityResolutionRule) -> EntityRuleReadResponse:
    return EntityRuleReadResponse(**rule.model_dump())


def _claim_rule_response(rule: ClaimSuppressionRule) -> ClaimRuleReadResponse:
    return ClaimRuleReadResponse(**rule.model_dump())


@router.get("/entity-rules", response_model=EntityRuleListResponse)
async def list_entity_rules(
    db: Database = Depends(get_library_database),
) -> EntityRuleListResponse:
    items = sorted(
        db.query(EntityResolutionRule),
        key=lambda rule: (rule.updated_at, rule.created_at, rule.id),
        reverse=True,
    )
    return EntityRuleListResponse(
        items=[_entity_rule_response(rule) for rule in items],
        count=len(items),
    )


@router.post("/entity-rules", response_model=EntityRuleReadResponse)
async def create_entity_rule(
    request: EntityRuleCreateRequest,
    db: Database = Depends(get_library_database),
) -> EntityRuleReadResponse:
    rule = EntityResolutionRule(**request.model_dump())
    db.save(rule)
    return _entity_rule_response(rule)


@router.post("/entity-rules/batch", response_model=EntityRuleListResponse)
async def create_entity_rules_batch(
    request: EntityRuleBatchCreateRequest,
    db: Database = Depends(get_library_database),
) -> EntityRuleListResponse:
    created: list[EntityResolutionRule] = []
    for item in request.items:
        rule = EntityResolutionRule(**item.model_dump())
        db.save(rule)
        created.append(rule)
    return EntityRuleListResponse(
        items=[_entity_rule_response(rule) for rule in created],
        count=len(created),
    )


@router.delete("/entity-rules", response_model=EntityRuleDeleteResponse)
async def delete_entity_rule(
    request: EntityRuleDeleteRequest,
    db: Database = Depends(get_library_database),
) -> EntityRuleDeleteResponse:
    rule = db.get(EntityResolutionRule, request.rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity rule not found: {request.rule_id}",
        )
    db.delete(rule)
    return EntityRuleDeleteResponse(deleted_rule_id=request.rule_id)


@router.get("/claim-rules", response_model=ClaimRuleListResponse)
async def list_claim_rules(
    db: Database = Depends(get_library_database),
) -> ClaimRuleListResponse:
    items = sorted(
        db.query(ClaimSuppressionRule),
        key=lambda rule: (rule.updated_at, rule.created_at, rule.id),
        reverse=True,
    )
    return ClaimRuleListResponse(
        items=[_claim_rule_response(rule) for rule in items],
        count=len(items),
    )


@router.post("/claim-rules", response_model=ClaimRuleReadResponse)
async def create_claim_rule(
    request: ClaimRuleCreateRequest,
    db: Database = Depends(get_library_database),
) -> ClaimRuleReadResponse:
    rule = ClaimSuppressionRule(**request.model_dump())
    db.save(rule)
    return _claim_rule_response(rule)


@router.post("/claim-rules/batch", response_model=ClaimRuleListResponse)
async def create_claim_rules_batch(
    request: ClaimRuleBatchCreateRequest,
    db: Database = Depends(get_library_database),
) -> ClaimRuleListResponse:
    created: list[ClaimSuppressionRule] = []
    for item in request.items:
        rule = ClaimSuppressionRule(**item.model_dump())
        db.save(rule)
        created.append(rule)
    return ClaimRuleListResponse(
        items=[_claim_rule_response(rule) for rule in created],
        count=len(created),
    )


@router.delete("/claim-rules", response_model=ClaimRuleDeleteResponse)
async def delete_claim_rule(
    request: ClaimRuleDeleteRequest,
    db: Database = Depends(get_library_database),
) -> ClaimRuleDeleteResponse:
    rule = db.get(ClaimSuppressionRule, request.rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Claim rule not found: {request.rule_id}",
        )
    db.delete(rule)
    return ClaimRuleDeleteResponse(deleted_rule_id=request.rule_id)
