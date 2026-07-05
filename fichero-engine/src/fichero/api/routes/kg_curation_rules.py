"""Persistent entity/claim curation rule CRUD routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import action_context
from fichero.api.main import get_library_database, get_library_database_for_write
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


class EntityRuleRestoreRequest(BaseModel):
    rule: EntityRuleReadResponse


def _invert_create_entity_rule(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict]:
    if not after or "id" not in after:
        raise ValueError("Cannot undo kg.entity_rule.create without created rule id")
    return "kg.entity_rule.delete", {"rule_id": after["id"]}


def _invert_delete_entity_rule(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict]:
    if not before or "rule" not in before:
        raise ValueError("Cannot undo kg.entity_rule.delete without deleted rule")
    return "kg.entity_rule.restore", {"rule": before["rule"]}


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


class ClaimRuleRestoreRequest(BaseModel):
    rule: ClaimRuleReadResponse


def _invert_create_claim_rule(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict]:
    if not after or "id" not in after:
        raise ValueError("Cannot undo kg.claim_rule.create without created rule id")
    return "kg.claim_rule.delete", {"rule_id": after["id"]}


def _invert_delete_claim_rule(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict]:
    if not before or "rule" not in before:
        raise ValueError("Cannot undo kg.claim_rule.delete without deleted rule")
    return "kg.claim_rule.restore", {"rule": before["rule"]}


def _entity_rule_response(rule: EntityResolutionRule) -> EntityRuleReadResponse:
    return EntityRuleReadResponse(**rule.model_dump())


def _claim_rule_response(rule: ClaimSuppressionRule) -> ClaimRuleReadResponse:
    return ClaimRuleReadResponse(**rule.model_dump())


def _create_entity_rule_impl(
    db: Database, request: EntityRuleCreateRequest
) -> EntityResolutionRule:
    rule = EntityResolutionRule(**request.model_dump())
    db.save(rule)
    return rule


def _create_entity_rules_batch_impl(
    db: Database, request: EntityRuleBatchCreateRequest
) -> list[EntityResolutionRule]:
    created: list[EntityResolutionRule] = []
    for item in request.items:
        rule = EntityResolutionRule(**item.model_dump())
        db.save(rule)
        created.append(rule)
    return created


def _delete_entity_rule_impl(db: Database, rule_id: str) -> None:
    rule = db.get(EntityResolutionRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity rule not found: {rule_id}",
        )
    db.delete(rule)


def _create_claim_rule_impl(
    db: Database, request: ClaimRuleCreateRequest
) -> ClaimSuppressionRule:
    rule = ClaimSuppressionRule(**request.model_dump())
    db.save(rule)
    return rule


def _create_claim_rules_batch_impl(
    db: Database, request: ClaimRuleBatchCreateRequest
) -> list[ClaimSuppressionRule]:
    created: list[ClaimSuppressionRule] = []
    for item in request.items:
        rule = ClaimSuppressionRule(**item.model_dump())
        db.save(rule)
        created.append(rule)
    return created


def _delete_claim_rule_impl(db: Database, rule_id: str) -> None:
    rule = db.get(ClaimSuppressionRule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Claim rule not found: {rule_id}",
        )
    db.delete(rule)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> EntityRuleReadResponse:
    result = registry.invoke(
        db,
        "kg.entity_rule.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return EntityRuleReadResponse.model_validate(result.result)


@router.post("/entity-rules/batch", response_model=EntityRuleListResponse)
async def create_entity_rules_batch(
    request: EntityRuleBatchCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> EntityRuleListResponse:
    result = registry.invoke(
        db,
        "kg.entity_rule.batch_create",
        request.model_dump(mode="json"),
        ctx,
    )
    return EntityRuleListResponse.model_validate(result.result)


@router.delete("/entity-rules", response_model=EntityRuleDeleteResponse)
async def delete_entity_rule(
    request: EntityRuleDeleteRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> EntityRuleDeleteResponse:
    result = registry.invoke(
        db,
        "kg.entity_rule.delete",
        request.model_dump(mode="json"),
        ctx,
    )
    return EntityRuleDeleteResponse.model_validate(result.result)


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
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimRuleReadResponse:
    result = registry.invoke(
        db,
        "kg.claim_rule.create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClaimRuleReadResponse.model_validate(result.result)


@router.post("/claim-rules/batch", response_model=ClaimRuleListResponse)
async def create_claim_rules_batch(
    request: ClaimRuleBatchCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimRuleListResponse:
    result = registry.invoke(
        db,
        "kg.claim_rule.batch_create",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClaimRuleListResponse.model_validate(result.result)


@router.delete("/claim-rules", response_model=ClaimRuleDeleteResponse)
async def delete_claim_rule(
    request: ClaimRuleDeleteRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ClaimRuleDeleteResponse:
    result = registry.invoke(
        db,
        "kg.claim_rule.delete",
        request.model_dump(mode="json"),
        ctx,
    )
    return ClaimRuleDeleteResponse.model_validate(result.result)


@action(
    "kg.entity_rule.create",
    EntityRuleCreateRequest,
    domains=["entity"],
    undoable=True,
    invert=_invert_create_entity_rule,
)
def _action_create_entity_rule(
    db: Database, params: EntityRuleCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = _create_entity_rule_impl(db, params)
    spec = ChangeSpec(
        domains=["entity"],
        target_ids=[rule.id],
        after=rule.model_dump(mode="json"),
        emit_type="entity.updated",
    )
    return _entity_rule_response(rule).model_dump(mode="json"), spec


@action(
    "kg.entity_rule.batch_create",
    EntityRuleBatchCreateRequest,
    domains=["entity"],
    undoable=False,
)
def _action_create_entity_rules_batch(
    db: Database, params: EntityRuleBatchCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    created = _create_entity_rules_batch_impl(db, params)
    spec = ChangeSpec(
        domains=["entity"],
        target_ids=[rule.id for rule in created],
        after={"rule_ids": [rule.id for rule in created]},
        emit_type="entity.updated" if created else None,
    )
    return EntityRuleListResponse(
        items=[_entity_rule_response(rule) for rule in created],
        count=len(created),
    ).model_dump(mode="json"), spec


@action(
    "kg.entity_rule.delete",
    EntityRuleDeleteRequest,
    domains=["entity"],
    undoable=True,
    invert=_invert_delete_entity_rule,
)
def _action_delete_entity_rule(
    db: Database, params: EntityRuleDeleteRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = db.get(EntityResolutionRule, params.rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity rule not found: {params.rule_id}",
        )
    _delete_entity_rule_impl(db, params.rule_id)
    spec = ChangeSpec(
        domains=["entity"],
        target_ids=[params.rule_id],
        before={"rule": rule.model_dump(mode="json")},
        after={"deleted_rule_id": params.rule_id},
        emit_type="entity.updated",
    )
    return EntityRuleDeleteResponse(deleted_rule_id=params.rule_id).model_dump(
        mode="json"
    ), spec


@action(
    "kg.entity_rule.restore",
    EntityRuleRestoreRequest,
    domains=["entity"],
    undoable=False,
)
def _action_restore_entity_rule(
    db: Database, params: EntityRuleRestoreRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = EntityResolutionRule.model_validate(params.rule.model_dump(mode="json"))
    existing = db.get(EntityResolutionRule, rule.id)
    before = existing.model_dump(mode="json") if existing is not None else None
    db.save(rule)
    spec = ChangeSpec(
        domains=["entity"],
        target_ids=[rule.id],
        before={"rule": before} if before is not None else None,
        after={"rule": rule.model_dump(mode="json")},
        emit_type="entity.updated",
    )
    return _entity_rule_response(rule).model_dump(mode="json"), spec


@action(
    "kg.claim_rule.create",
    ClaimRuleCreateRequest,
    domains=["claim"],
    undoable=True,
    invert=_invert_create_claim_rule,
)
def _action_create_claim_rule(
    db: Database, params: ClaimRuleCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = _create_claim_rule_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[rule.id],
        after=rule.model_dump(mode="json"),
        emit_type="claim.updated",
    )
    return _claim_rule_response(rule).model_dump(mode="json"), spec


@action(
    "kg.claim_rule.batch_create",
    ClaimRuleBatchCreateRequest,
    domains=["claim"],
    undoable=False,
)
def _action_create_claim_rules_batch(
    db: Database, params: ClaimRuleBatchCreateRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    created = _create_claim_rules_batch_impl(db, params)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[rule.id for rule in created],
        after={"rule_ids": [rule.id for rule in created]},
        emit_type="claim.updated" if created else None,
    )
    return ClaimRuleListResponse(
        items=[_claim_rule_response(rule) for rule in created],
        count=len(created),
    ).model_dump(mode="json"), spec


@action(
    "kg.claim_rule.delete",
    ClaimRuleDeleteRequest,
    domains=["claim"],
    undoable=True,
    invert=_invert_delete_claim_rule,
)
def _action_delete_claim_rule(
    db: Database, params: ClaimRuleDeleteRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = db.get(ClaimSuppressionRule, params.rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"Claim rule not found: {params.rule_id}",
        )
    _delete_claim_rule_impl(db, params.rule_id)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[params.rule_id],
        before={"rule": rule.model_dump(mode="json")},
        after={"deleted_rule_id": params.rule_id},
        emit_type="claim.updated",
    )
    return ClaimRuleDeleteResponse(deleted_rule_id=params.rule_id).model_dump(
        mode="json"
    ), spec


@action(
    "kg.claim_rule.restore",
    ClaimRuleRestoreRequest,
    domains=["claim"],
    undoable=False,
)
def _action_restore_claim_rule(
    db: Database, params: ClaimRuleRestoreRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    rule = ClaimSuppressionRule.model_validate(params.rule.model_dump(mode="json"))
    existing = db.get(ClaimSuppressionRule, rule.id)
    before = existing.model_dump(mode="json") if existing is not None else None
    db.save(rule)
    spec = ChangeSpec(
        domains=["claim"],
        target_ids=[rule.id],
        before={"rule": before} if before is not None else None,
        after={"rule": rule.model_dump(mode="json")},
        emit_type="claim.updated",
    )
    return _claim_rule_response(rule).model_dump(mode="json"), spec
