"""Tests for orchestration policy engine (Issue #426)."""

from fichero_server.llm.orchestration_policy import (
    PolicyAction,
    EntityTypeScope,
    PolicyRule,
    AgentWriteRequest,
    AgentWriteRecord,
    ApprovalState,
    get_policy_engine,
)


class TestPolicyAction:
    """Test policy action enum."""

    def test_enum_values(self):
        """Test policy action enum values."""
        assert PolicyAction.auto_approve.value == "auto_approve"
        assert PolicyAction.require_approval.value == "require_approval"
        assert PolicyAction.deny.value == "deny"


class TestEntityTypeScope:
    """Test entity type scope enum."""

    def test_scope_values(self):
        """Test scope enum values."""
        assert EntityTypeScope.all.value == "all"
        assert EntityTypeScope.claims.value == "claims"
        assert EntityTypeScope.entities.value == "entities"
        assert EntityTypeScope.interpretations.value == "interpretations"


class TestApprovalState:
    """Test approval state enum."""

    def test_state_values(self):
        """Test approval state enum values."""
        assert ApprovalState.pending.value == "pending"
        assert ApprovalState.approved.value == "approved"
        assert ApprovalState.rejected.value == "rejected"
        assert ApprovalState.auto_approved.value == "auto_approved"
        assert ApprovalState.auto_rejected.value == "auto_rejected"


class TestPolicyRule:
    """Test PolicyRule model."""

    def test_rule_creation(self):
        """Test creating a policy rule."""
        rule = PolicyRule(
            name="Test Rule",
            description="A test rule",
            entity_type=EntityTypeScope.all,
            action=PolicyAction.require_approval,
        )
        assert rule.name == "Test Rule"
        assert rule.is_active is True
        assert rule.priority == 100  # Default

    def test_rule_matches_all_entity_types(self):
        """Test rule matches all entity types when scope is all."""
        rule = PolicyRule(
            name="All Entities",
            entity_type=EntityTypeScope.all,
            action=PolicyAction.auto_approve,
        )
        assert rule.matches("claims", 0.9, True, 1) is True
        assert rule.matches("entities", 0.5, False, 0) is True

    def test_rule_respects_entity_type_filter(self):
        """Test rule only matches specific entity type."""
        rule = PolicyRule(
            name="Claims Only",
            entity_type=EntityTypeScope.claims,
            action=PolicyAction.auto_approve,
        )
        assert rule.matches("claims", 0.9, True, 1) is True
        assert rule.matches("entities", 0.9, True, 1) is False

    def test_rule_confidence_threshold(self):
        """Test rule respects confidence threshold."""
        rule = PolicyRule(
            name="High Confidence",
            entity_type=EntityTypeScope.all,
            confidence_threshold=0.9,
            action=PolicyAction.auto_approve,
        )
        assert rule.matches("claims", 0.95, True, 1) is True
        assert rule.matches("claims", 0.85, True, 1) is False
        assert rule.matches("claims", None, True, 1) is False

    def test_rule_requires_source(self):
        """Test rule requires source flag."""
        rule = PolicyRule(
            name="Requires Source",
            entity_type=EntityTypeScope.all,
            requires_source=True,
            action=PolicyAction.auto_approve,
        )
        assert rule.matches("claims", 0.9, True, 1) is True
        assert rule.matches("claims", 0.9, False, 1) is False

    def test_rule_min_evidence_count(self):
        """Test rule minimum evidence count."""
        rule = PolicyRule(
            name="Requires Evidence",
            entity_type=EntityTypeScope.all,
            min_evidence_count=2,
            action=PolicyAction.auto_approve,
        )
        assert rule.matches("claims", 0.9, True, 2) is True
        assert rule.matches("claims", 0.9, True, 1) is False

    def test_rule_inactive(self):
        """Test inactive rule does not match."""
        rule = PolicyRule(
            name="Inactive",
            action=PolicyAction.auto_approve,
            is_active=False,
        )
        assert rule.matches("claims", 0.9, True, 1) is False


class TestAgentWriteRequest:
    """Test AgentWriteRequest model."""

    def test_request_creation(self):
        """Test creating a write request."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test Agent",
            operation="create",
            entity_type="claim",
            confidence=0.9,
            sources=["source-1"],
            evidence=[{"type": "text"}],
        )
        assert request.agent_id == "agent-1"
        assert request.confidence == 0.9
        assert len(request.sources) == 1
        assert len(request.evidence) == 1


class TestAgentWriteRecord:
    """Test AgentWriteRecord model."""

    def test_record_creation(self):
        """Test creating a write record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = AgentWriteRecord(request=request)
        assert record.state == ApprovalState.pending
        assert record.request.agent_id == "agent-1"

    def test_record_approve(self):
        """Test approving a write record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = AgentWriteRecord(request=request)
        record.approve("user-1", "Approved by admin")
        assert record.state == ApprovalState.approved
        assert record.approval is not None
        assert record.approval.approved is True
        assert record.approval.approved_by == "user-1"

    def test_record_reject(self):
        """Test rejecting a write record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = AgentWriteRecord(request=request)
        record.reject("user-1", "Insufficient evidence")
        assert record.state == ApprovalState.rejected
        assert record.approval is not None
        assert record.approval.approved is False

    def test_record_auto_approve(self):
        """Test auto-approving a write record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = AgentWriteRecord(request=request)
        record.auto_approve("rule-1")
        assert record.state == ApprovalState.auto_approved
        assert record.policy_rule_id == "rule-1"
        assert record.policy_action == PolicyAction.auto_approve

    def test_record_auto_reject(self):
        """Test auto-rejecting a write record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = AgentWriteRecord(request=request)
        record.auto_reject("rule-1", "Policy denied")
        assert record.state == ApprovalState.auto_rejected
        assert record.policy_rule_id == "rule-1"
        assert record.approval is not None
        assert record.approval.approved is False


class TestPolicyEngine:
    """Test PolicyEngine."""

    def setup_method(self):
        """Setup fresh engine for each test."""
        import fichero_server.llm.orchestration_policy as op
        op._policy_engine = None
        self.engine = get_policy_engine()

    def test_default_rules_exist(self):
        """Test default rules are initialized."""
        rules = self.engine.get_rules()
        assert len(rules) >= 3

        rule_names = [r.name for r in rules]
        assert "High Confidence Auto-Approve" in rule_names
        assert "Entity Deletion Protection" in rule_names

    def test_add_rule(self):
        """Test adding a custom rule."""
        initial_count = len(self.engine.get_rules())
        rule = PolicyRule(
            name="Custom Rule",
            action=PolicyAction.require_approval,
            priority=50,
        )
        self.engine.add_rule(rule)
        assert len(self.engine.get_rules()) == initial_count + 1

    def test_evaluate_auto_approve(self):
        """Test evaluation with auto-approve conditions."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
            confidence=0.95,
            sources=["source-1", "source-2"],
            evidence=[{}, {}, {}],
        )
        action, rule = self.engine.evaluate(request)
        assert action == PolicyAction.auto_approve
        assert rule is not None
        assert "High Confidence" in rule.name

    def test_evaluate_require_approval(self):
        """Test evaluation requiring approval."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
            confidence=0.75,
            sources=["source-1"],
            evidence=[{}],
        )
        action, rule = self.engine.evaluate(request)
        assert action == PolicyAction.require_approval

    def test_evaluate_deny(self):
        """Test evaluation denied (fallback to require_approval when no rules match)."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
            confidence=None,
        )
        action, rule = self.engine.evaluate(request)
        # Fallback is require_approval since no deny rule matches
        assert action == PolicyAction.require_approval

    def test_submit_request(self):
        """Test submitting a write request."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
            confidence=0.95,
            sources=["source-1", "source-2"],
            evidence=[{}, {}],
        )
        record = self.engine.submit_request(request)
        assert record.state == ApprovalState.auto_approved

    def test_get_record(self):
        """Test retrieving a record."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        record = self.engine.submit_request(request)
        retrieved = self.engine.get_record(record.id)
        assert retrieved is not None
        assert retrieved.id == record.id

    def test_get_records_filtering(self):
        """Test filtering records."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="create",
            entity_type="claim",
        )
        self.engine.submit_request(request)

        records = self.engine.get_records(agent_id="agent-1")
        assert len(records) >= 1

    def test_approve_request(self):
        """Test approving a pending request."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="update",
            entity_type="entity",
            confidence=0.5,
        )
        record = self.engine.submit_request(request)
        assert record.state == ApprovalState.pending

        approved = self.engine.approve_request(record.id, "admin", "Approved")
        assert approved is not None
        assert approved.state == ApprovalState.approved

    def test_reject_request(self):
        """Test rejecting a pending request."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="update",
            entity_type="entity",
            confidence=0.5,
        )
        record = self.engine.submit_request(request)

        rejected = self.engine.reject_request(record.id, "admin", "Rejected")
        assert rejected is not None
        assert rejected.state == ApprovalState.rejected

    def test_approve_non_pending_fails(self):
        """Test approving already processed request fails."""
        request = AgentWriteRequest(
            agent_id="agent-1",
            agent_name="Test",
            operation="update",
            entity_type="entity",
            confidence=0.95,
            sources=["source-1", "source-2"],
            evidence=[{}, {}],
        )
        record = self.engine.submit_request(request)
        assert record.state == ApprovalState.auto_approved

        result = self.engine.approve_request(record.id, "admin", "Approved")
        assert result is None

    def test_update_rule(self):
        """Test updating a rule."""
        rule = PolicyRule(name="Test Rule", action=PolicyAction.require_approval)
        self.engine.add_rule(rule)

        updated = self.engine.update_rule(rule.id, {"name": "Updated Name", "priority": 10})
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.priority == 10

    def test_delete_rule(self):
        """Test deleting a rule."""
        rule = PolicyRule(name="Delete Me", action=PolicyAction.require_approval)
        self.engine.add_rule(rule)
        rule_id = rule.id

        deleted = self.engine.delete_rule(rule_id)
        assert deleted is True

        not_found = self.engine.get_rule(rule_id)
        assert not_found is None

    def test_delete_nonexistent_rule(self):
        """Test deleting non-existent rule returns False."""
        deleted = self.engine.delete_rule("nonexistent-id")
        assert deleted is False


class TestGetPolicyEngine:
    """Test get_policy_engine singleton."""

    def test_singleton(self):
        """Test engine is a singleton."""
        import fichero_server.llm.orchestration_policy as op
        op._policy_engine = None

        engine1 = get_policy_engine()
        engine2 = get_policy_engine()
        assert engine1 is engine2
