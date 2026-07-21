"""Orchestration Policy API Routes.

Endpoints for managing agent write policies and approvals.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from fichero.orchestration_policy import (
    AgentWriteRecord,
    AgentWriteRequest,
    ApprovalState,
    EntityTypeScope,
    PolicyAction,
    PolicyRule,
    get_policy_engine,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class PolicyRuleCreateRequest(BaseModel):
    """Request to create a policy rule."""

    name: str
    description: str = ""
    entity_type: EntityTypeScope = EntityTypeScope.all
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_source: bool = False
    min_evidence_count: int = Field(default=0, ge=0)
    action: PolicyAction = PolicyAction.require_approval
    priority: int = Field(default=100, ge=1, le=1000)


class PolicyRuleResponse(BaseModel):
    """Response for a policy rule."""

    id: str
    name: str
    description: str
    entity_type: str
    confidence_threshold: float | None
    requires_source: bool
    min_evidence_count: int
    action: str
    priority: int
    is_active: bool
    created_at: str
    created_by: str


class PolicyRulesListResponse(BaseModel):
    """Response for listing policy rules."""

    rules: list[PolicyRuleResponse]
    total: int


class AgentWriteRequestInput(BaseModel):
    """Input for submitting an agent write request."""

    agent_id: str
    agent_name: str
    operation: str
    entity_type: str
    entity_id: str | None = None
    document_id: str | None = None
    artifact_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    justification: str = ""


class AgentWriteResponse(BaseModel):
    """Response for agent write submission."""

    record_id: str
    request_id: str
    state: str
    policy_action: str | None
    policy_rule_id: str | None
    message: str


class ApprovalRequest(BaseModel):
    """Request to approve or reject a write request."""

    approved: bool
    reason: str = ""
    approved_by: str


class ApprovalResponse(BaseModel):
    """Response for approval action."""

    record_id: str
    state: str
    approved: bool
    approved_by: str | None
    reason: str


class AgentWriteRecordResponse(BaseModel):
    """Response for a write record."""

    id: str
    request_id: str
    agent_id: str
    agent_name: str
    operation: str
    entity_type: str
    entity_id: str | None
    document_id: str | None
    artifact_id: str | None
    state: str
    policy_action: str | None
    policy_rule_id: str | None
    confidence: float | None
    justification: str
    sources: list[str]
    evidence_count: int
    approved_by: str | None
    approval_reason: str | None
    created_at: str
    updated_at: str
    executed_at: str | None
    error_message: str | None


class AgentWriteRecordsListResponse(BaseModel):
    """Response for listing write records."""

    records: list[AgentWriteRecordResponse]
    total: int
    pending_count: int
    approved_count: int
    rejected_count: int


class PolicyEvaluationRequest(BaseModel):
    """Request to evaluate a hypothetical write against policies."""

    entity_type: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    has_source: bool = False
    evidence_count: int = Field(default=0, ge=0)


class PolicyEvaluationResponse(BaseModel):
    """Response for policy evaluation."""

    action: str
    rule_id: str | None
    rule_name: str | None
    explanation: str


# =============================================================================
# Helper Functions
# =============================================================================


def _rule_to_response(rule: PolicyRule) -> PolicyRuleResponse:
    """Convert PolicyRule to response model."""
    return PolicyRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        entity_type=rule.entity_type.value,
        confidence_threshold=rule.confidence_threshold,
        requires_source=rule.requires_source,
        min_evidence_count=rule.min_evidence_count,
        action=rule.action.value,
        priority=rule.priority,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat(),
        created_by=rule.created_by,
    )


def _record_to_response(record: AgentWriteRecord) -> AgentWriteRecordResponse:
    """Convert AgentWriteRecord to response model."""
    return AgentWriteRecordResponse(
        id=record.id,
        request_id=record.request.id,
        agent_id=record.request.agent_id,
        agent_name=record.request.agent_name,
        operation=record.request.operation,
        entity_type=record.request.entity_type,
        entity_id=record.request.entity_id,
        document_id=record.request.document_id,
        artifact_id=record.request.artifact_id,
        state=record.state.value,
        policy_action=record.policy_action.value if record.policy_action else None,
        policy_rule_id=record.policy_rule_id,
        confidence=record.request.confidence,
        justification=record.request.justification,
        sources=record.request.sources,
        evidence_count=len(record.request.evidence),
        approved_by=record.approval.approved_by if record.approval else None,
        approval_reason=record.approval.reason if record.approval else None,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        executed_at=record.executed_at.isoformat() if record.executed_at else None,
        error_message=record.error_message,
    )


# =============================================================================
# Policy Rules Endpoints
# =============================================================================


@router.get(
    "/api/policies/orchestration",
    response_model=PolicyRulesListResponse,
    summary="List orchestration policy rules",
    tags=["orchestration"],
)
async def list_policy_rules(
    active_only: bool = Query(True, description="Only return active rules"),
) -> PolicyRulesListResponse:
    """Get all orchestration policy rules."""
    engine = get_policy_engine()
    rules = engine.get_rules(active_only=active_only)

    return PolicyRulesListResponse(
        rules=[_rule_to_response(r) for r in rules],
        total=len(rules),
    )


@router.post(
    "/api/policies/orchestration",
    response_model=PolicyRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new policy rule",
    tags=["orchestration"],
)
async def create_policy_rule(
    request: PolicyRuleCreateRequest,
) -> PolicyRuleResponse:
    """Create a new orchestration policy rule."""
    engine = get_policy_engine()

    rule = PolicyRule(
        name=request.name,
        description=request.description,
        entity_type=request.entity_type,
        confidence_threshold=request.confidence_threshold,
        requires_source=request.requires_source,
        min_evidence_count=request.min_evidence_count,
        action=request.action,
        priority=request.priority,
    )

    engine.add_rule(rule)
    return _rule_to_response(rule)


@router.get(
    "/api/policies/orchestration/{rule_id}",
    response_model=PolicyRuleResponse,
    summary="Get a specific policy rule",
    tags=["orchestration"],
)
async def get_policy_rule(
    rule_id: str,
) -> PolicyRuleResponse:
    """Get a specific policy rule by ID."""
    engine = get_policy_engine()
    rule = engine.get_rule(rule_id)

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy rule not found: {rule_id}",
        )

    return _rule_to_response(rule)


@router.patch(
    "/api/policies/orchestration/{rule_id}",
    response_model=PolicyRuleResponse,
    summary="Update a policy rule",
    tags=["orchestration"],
)
async def update_policy_rule(
    rule_id: str,
    updates: dict[str, Any],
) -> PolicyRuleResponse:
    """Update an existing policy rule."""
    engine = get_policy_engine()

    rule = engine.update_rule(rule_id, updates)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy rule not found: {rule_id}",
        )

    return _rule_to_response(rule)


@router.delete(
    "/api/policies/orchestration/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a policy rule",
    tags=["orchestration"],
)
async def delete_policy_rule(
    rule_id: str,
) -> None:
    """Delete a policy rule."""
    engine = get_policy_engine()

    if not engine.delete_rule(rule_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy rule not found: {rule_id}",
        )


# =============================================================================
# Policy Evaluation Endpoint
# =============================================================================


@router.post(
    "/api/policies/orchestration/evaluate",
    response_model=PolicyEvaluationResponse,
    summary="Evaluate a hypothetical write against policies",
    tags=["orchestration"],
)
async def evaluate_policy(
    request: PolicyEvaluationRequest,
) -> PolicyEvaluationResponse:
    """Evaluate what policy would apply to a hypothetical write operation."""
    engine = get_policy_engine()

    # Create a dummy request for evaluation
    dummy_request = AgentWriteRequest(
        agent_id="eval",
        agent_name="evaluator",
        operation="create",
        entity_type=request.entity_type,
        confidence=request.confidence,
        sources=["dummy"] if request.has_source else [],
        evidence=[{}] * request.evidence_count,
    )

    action, rule = engine.evaluate(dummy_request)

    explanation = f"Policy action: {action.value}"
    if rule:
        explanation = f"Matched rule '{rule.name}': {action.value}"

    return PolicyEvaluationResponse(
        action=action.value,
        rule_id=rule.id if rule else None,
        rule_name=rule.name if rule else None,
        explanation=explanation,
    )


# =============================================================================
# Agent Write Endpoints
# =============================================================================


@router.post(
    "/api/agents/write",
    response_model=AgentWriteResponse,
    summary="Submit an agent write request",
    tags=["orchestration"],
)
async def submit_agent_write(
    request: AgentWriteRequestInput,
) -> AgentWriteResponse:
    """Submit an AI agent write request for policy evaluation."""
    engine = get_policy_engine()

    write_request = AgentWriteRequest(
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        operation=request.operation,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        document_id=request.document_id,
        artifact_id=request.artifact_id,
        payload=request.payload,
        confidence=request.confidence,
        sources=request.sources,
        evidence=request.evidence,
        justification=request.justification,
    )

    record = engine.submit_request(write_request)

    message = f"Write request submitted. Status: {record.state.value}"
    if record.policy_action:
        message += f" (action: {record.policy_action.value})"

    return AgentWriteResponse(
        record_id=record.id,
        request_id=record.request.id,
        state=record.state.value,
        policy_action=record.policy_action.value if record.policy_action else None,
        policy_rule_id=record.policy_rule_id,
        message=message,
    )


@router.post(
    "/api/agents/write/approve",
    response_model=ApprovalResponse,
    summary="Approve or reject a pending write request",
    tags=["orchestration"],
)
async def approve_agent_write(
    record_id: str,
    request: ApprovalRequest,
) -> ApprovalResponse:
    """Approve or reject a pending agent write request."""
    engine = get_policy_engine()

    if request.approved:
        record = engine.approve_request(record_id, request.approved_by, request.reason)
    else:
        record = engine.reject_request(record_id, request.approved_by, request.reason)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Write record not found or not in pending state: {record_id}",
        )

    return ApprovalResponse(
        record_id=record.id,
        state=record.state.value,
        approved=record.approval.approved if record.approval else False,
        approved_by=record.approval.approved_by if record.approval else None,
        reason=record.approval.reason if record.approval else "",
    )


@router.get(
    "/api/agents/write/audit",
    response_model=AgentWriteRecordsListResponse,
    summary="Get agent write audit history",
    tags=["orchestration"],
)
async def get_agent_write_audit(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    state: ApprovalState | None = Query(None, description="Filter by approval state"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    document_id: str | None = Query(None, description="Filter by document ID"),
    artifact_id: str | None = Query(None, description="Filter by artifact ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> AgentWriteRecordsListResponse:
    """Get audit history of agent write requests with filtering."""
    engine = get_policy_engine()
    records = engine.get_records(
        agent_id=agent_id,
        state=state,
        entity_type=entity_type,
        document_id=document_id,
        artifact_id=artifact_id,
        limit=limit,
        offset=offset,
    )

    # Count by state
    all_records = list(engine._records.values())
    pending_count = len([r for r in all_records if r.state == ApprovalState.pending])
    approved_count = len([r for r in all_records if r.state == ApprovalState.approved])
    rejected_count = len([r for r in all_records if r.state == ApprovalState.rejected])

    return AgentWriteRecordsListResponse(
        records=[_record_to_response(r) for r in records],
        total=len(all_records),
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
    )


@router.get(
    "/api/agents/write/audit/{record_id}",
    response_model=AgentWriteRecordResponse,
    summary="Get a specific write record",
    tags=["orchestration"],
)
async def get_agent_write_record(
    record_id: str,
) -> AgentWriteRecordResponse:
    """Get details of a specific agent write record."""
    engine = get_policy_engine()
    record = engine.get_record(record_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Write record not found: {record_id}",
        )

    return _record_to_response(record)
