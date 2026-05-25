"""Orchestration Policy Engine for Agent Writes.

Defines policy rules for AI agent write operations with human-in-the-loop
approval workflows and audit logging.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyAction(str, Enum):
    """Actions that can be taken on a policy."""

    auto_approve = "auto_approve"  # No human review needed
    require_approval = "require_approval"  # Human approval required
    deny = "deny"  # Operation blocked


class EntityTypeScope(str, Enum):
    """Scope of entity types for policy rules."""

    all = "all"
    claims = "claims"
    entities = "entities"
    interpretations = "interpretations"


class PolicyRule(BaseModel):
    """Individual policy rule for agent writes."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    entity_type: EntityTypeScope = EntityTypeScope.all
    # Conditions
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_source: bool = False
    min_evidence_count: int = Field(default=0, ge=0)
    # Action
    action: PolicyAction = PolicyAction.require_approval
    # Metadata
    priority: int = Field(default=100, ge=1, le=1000)  # Lower = higher priority
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

    def matches(
        self,
        entity_type: str,
        confidence: float | None,
        has_source: bool,
        evidence_count: int,
    ) -> bool:
        """Check if this rule applies to the given operation."""
        if not self.is_active:
            return False

        # Entity type matching
        if self.entity_type != EntityTypeScope.all:
            if entity_type != self.entity_type.value:
                return False

        # Confidence threshold
        if self.confidence_threshold is not None:
            if confidence is None or confidence < self.confidence_threshold:
                return False

        # Source requirement
        if self.requires_source and not has_source:
            return False

        # Evidence count
        if evidence_count < self.min_evidence_count:
            return False

        return True


class AgentWriteRequest(BaseModel):
    """Request for an AI agent to perform a write operation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    agent_name: str
    operation: str  # "create", "update", "delete"
    entity_type: str  # "claim", "entity", "interpretation"
    entity_id: str | None = None  # For updates/deletes
    document_id: str | None = None
    artifact_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    justification: str = ""
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalState(str, Enum):
    """State of an approval request."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    auto_approved = "auto_approved"  # Policy allowed without review
    auto_rejected = "auto_rejected"  # Policy blocked


class ApprovalDecision(BaseModel):
    """Decision on an agent write request."""

    approved: bool
    approved_by: str | None = None
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentWriteRecord(BaseModel):
    """Record of an agent write operation (pending or completed)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: AgentWriteRequest
    state: ApprovalState = ApprovalState.pending
    # Policy evaluation
    policy_rule_id: str | None = None
    policy_action: PolicyAction | None = None
    # Approval
    approval: ApprovalDecision | None = None
    # Execution
    executed_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    error_message: str | None = None
    # Audit
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def approve(self, approved_by: str, reason: str = "") -> None:
        """Approve this write request."""
        self.state = ApprovalState.approved
        self.approval = ApprovalDecision(
            approved=True,
            approved_by=approved_by,
            reason=reason,
        )
        self.updated_at = datetime.now(timezone.utc)

    def reject(self, rejected_by: str, reason: str = "") -> None:
        """Reject this write request."""
        self.state = ApprovalState.rejected
        self.approval = ApprovalDecision(
            approved=False,
            approved_by=rejected_by,
            reason=reason,
        )
        self.updated_at = datetime.now(timezone.utc)

    def auto_approve(self, policy_rule_id: str) -> None:
        """Auto-approve based on policy."""
        self.state = ApprovalState.auto_approved
        self.policy_rule_id = policy_rule_id
        self.policy_action = PolicyAction.auto_approve
        self.updated_at = datetime.now(timezone.utc)

    def auto_reject(self, policy_rule_id: str, reason: str = "") -> None:
        """Auto-reject based on policy."""
        self.state = ApprovalState.auto_rejected
        self.policy_rule_id = policy_rule_id
        self.policy_action = PolicyAction.deny
        self.approval = ApprovalDecision(
            approved=False,
            approved_by="system",
            reason=reason,
        )
        self.updated_at = datetime.now(timezone.utc)

    def mark_executed(self, result: dict[str, Any] | None = None) -> None:
        """Mark as executed."""
        self.executed_at = datetime.now(timezone.utc)
        self.execution_result = result
        self.updated_at = datetime.now(timezone.utc)

    def mark_error(self, error: str) -> None:
        """Mark as failed with error."""
        self.error_message = error
        self.updated_at = datetime.now(timezone.utc)


class PolicyEngine:
    """Engine for evaluating agent write requests against policies."""

    def __init__(self) -> None:
        self._rules: list[PolicyRule] = []
        self._records: dict[str, AgentWriteRecord] = {}
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default policy rules."""
        # Auto-approve high-confidence claims with sources
        self._rules.append(
            PolicyRule(
                name="High Confidence Auto-Approve",
                description="Auto-approve high-confidence writes with sources",
                entity_type=EntityTypeScope.all,
                confidence_threshold=0.9,
                requires_source=True,
                min_evidence_count=2,
                action=PolicyAction.auto_approve,
                priority=1,
            )
        )

        # Require approval for medium confidence
        self._rules.append(
            PolicyRule(
                name="Medium Confidence Review",
                description="Human review required for medium confidence writes",
                entity_type=EntityTypeScope.all,
                confidence_threshold=0.7,
                requires_source=False,
                min_evidence_count=1,
                action=PolicyAction.require_approval,
                priority=100,
            )
        )

        # Always require approval for entity deletions
        self._rules.append(
            PolicyRule(
                name="Entity Deletion Protection",
                description="Always require approval for entity deletions",
                entity_type=EntityTypeScope.entities,
                action=PolicyAction.require_approval,
                priority=10,
            )
        )

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a new policy rule."""
        self._rules.append(rule)
        # Sort by priority
        self._rules.sort(key=lambda r: r.priority)

    def get_rules(self, active_only: bool = True) -> list[PolicyRule]:
        """Get all policy rules."""
        if active_only:
            return [r for r in self._rules if r.is_active]
        return list(self._rules)

    def get_rule(self, rule_id: str) -> PolicyRule | None:
        """Get a specific rule by ID."""
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        return None

    def update_rule(self, rule_id: str, updates: dict[str, Any]) -> PolicyRule | None:
        """Update a policy rule."""
        rule = self.get_rule(rule_id)
        if rule is None:
            return None

        # Create new rule with updates (rules are immutable)
        rule_dict = rule.model_dump()
        rule_dict.update(updates)
        rule_dict["id"] = rule_id  # Preserve ID
        new_rule = PolicyRule(**rule_dict)

        # Replace in list
        self._rules = [r for r in self._rules if r.id != rule_id]
        self._rules.append(new_rule)
        self._rules.sort(key=lambda r: r.priority)

        return new_rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a policy rule."""
        initial_count = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        return len(self._rules) < initial_count

    def evaluate(self, request: AgentWriteRequest) -> tuple[PolicyAction, PolicyRule | None]:
        """Evaluate a write request against policies."""
        # Sort by priority (lower = higher priority)
        sorted_rules = sorted(self._rules, key=lambda r: r.priority)

        for rule in sorted_rules:
            if not rule.is_active:
                continue

            evidence_count = len(request.evidence)
            has_source = len(request.sources) > 0

            if rule.matches(
                entity_type=request.entity_type,
                confidence=request.confidence,
                has_source=has_source,
                evidence_count=evidence_count,
            ):
                return rule.action, rule

        # Default: require approval
        return PolicyAction.require_approval, None

    def submit_request(self, request: AgentWriteRequest) -> AgentWriteRecord:
        """Submit a write request for evaluation."""
        action, rule = self.evaluate(request)

        record = AgentWriteRecord(request=request)

        if rule:
            record.policy_rule_id = rule.id
            record.policy_action = action

        if action == PolicyAction.auto_approve:
            if rule:
                record.auto_approve(rule.id)
        elif action == PolicyAction.deny:
            if rule:
                record.auto_reject(rule.id, "Policy denied this operation")

        self._records[record.id] = record
        return record

    def get_record(self, record_id: str) -> AgentWriteRecord | None:
        """Get a specific write record."""
        return self._records.get(record_id)
        return self._records.get(record_id)

    def get_records(
        self,
        agent_id: str | None = None,
        state: ApprovalState | None = None,
        entity_type: str | None = None,
        document_id: str | None = None,
        artifact_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentWriteRecord]:
        """Get write records with filtering."""
        records = list(self._records.values())

        if agent_id:
            records = [r for r in records if r.request.agent_id == agent_id]
        if state:
            records = [r for r in records if r.state == state]
        if entity_type:
            records = [r for r in records if r.request.entity_type == entity_type]
        if document_id:
            records = [r for r in records if r.request.document_id == document_id]
        if artifact_id:
            records = [r for r in records if r.request.artifact_id == artifact_id]

        # Sort by created_at descending
        records.sort(key=lambda r: r.created_at, reverse=True)

        return records[offset : offset + limit]

    def approve_request(
        self,
        record_id: str,
        approved_by: str,
        reason: str = "",
    ) -> AgentWriteRecord | None:
        """Approve a pending write request."""
        record = self._records.get(record_id)
        if record is None:
            return None
        if record.state != ApprovalState.pending:
            return None

        record.approve(approved_by, reason)
        return record

    def reject_request(
        self,
        record_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> AgentWriteRecord | None:
        """Reject a pending write request."""
        record = self._records.get(record_id)
        if record is None:
            return None
        if record.state != ApprovalState.pending:
            return None

        record.reject(rejected_by, reason)
        return record


# Global policy engine instance
_policy_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Get or create the global policy engine."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
