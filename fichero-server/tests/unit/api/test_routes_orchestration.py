"""Tests for orchestration policy routes.

Orchestration routes manage agent write policies (auto-approve, require
approval, deny) and audit logs. The policy engine is an in-memory singleton;
tests mock get_policy_engine() to avoid shared-state contamination between
test runs. Routes use full /api/policies/... paths (mounted at root "").
"""

from unittest.mock import MagicMock, patch

from fichero_server.llm.orchestration_policy import (
    PolicyRule,
    EntityTypeScope,
    PolicyAction,
    ApprovalState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(
    rule_id: str = "rule-1",
    name: str = "Require approval for claims",
    action: PolicyAction = PolicyAction.require_approval,
) -> PolicyRule:
    return PolicyRule(
        id=rule_id,
        name=name,
        entity_type=EntityTypeScope.claims,
        action=action,
    )


def _make_engine(rules: list | None = None) -> MagicMock:
    engine = MagicMock()
    engine.get_rules.return_value = rules or []
    engine.get_records.return_value = []
    engine._records = {}
    return engine


# ---------------------------------------------------------------------------
# GET /api/policies/orchestration
# ---------------------------------------------------------------------------


class TestListPolicyRules:
    def test_returns_empty_list(self, client):
        engine = _make_engine()
        with patch("fichero_server.api.routes.workflow.orchestration.get_policy_engine", return_value=engine):
            r = client.get("/api/policies/orchestration")
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
        assert "total" in data
        assert data["total"] == 0

    def test_returns_rules(self, client):
        rule = _make_rule()
        engine = _make_engine([rule])
        with patch("fichero_server.api.routes.workflow.orchestration.get_policy_engine", return_value=engine):
            r = client.get("/api/policies/orchestration")
        assert r.status_code == 200
        assert r.json()["total"] == 1


# ---------------------------------------------------------------------------
# POST /api/policies/orchestration
# ---------------------------------------------------------------------------


class TestCreatePolicyRule:
    def test_create_rule(self, client):
        rule = _make_rule("r-new", "New rule")
        engine = MagicMock()
        engine.add_rule.return_value = rule

        with patch("fichero_server.api.routes.workflow.orchestration.get_policy_engine", return_value=engine):
            r = client.post("/api/policies/orchestration", json={
                "name": "New rule",
                "entity_type": "claims",
                "action": "require_approval",
            })
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/agents/write/audit
# ---------------------------------------------------------------------------


class TestAgentWriteAudit:
    def test_returns_empty_audit(self, client):
        engine = _make_engine()
        with patch("fichero_server.api.routes.workflow.orchestration.get_policy_engine", return_value=engine):
            r = client.get("/api/agents/write/audit")
        assert r.status_code == 200
        data = r.json()
        assert "records" in data
        assert "total" in data
        assert data["pending_count"] == 0

    def test_filters_by_document_id(self, client):
        record = MagicMock()
        record.id = "rec-1"
        record.request.id = "req-1"
        record.request.agent_id = "agent-1"
        record.request.agent_name = "Agent One"
        record.request.operation = "create"
        record.request.entity_type = "document"
        record.request.entity_id = "ent-1"
        record.request.document_id = "doc-1"
        record.request.artifact_id = None
        record.request.confidence = None
        record.request.justification = ""
        record.request.sources = []
        record.request.evidence = []
        record.state = ApprovalState.pending
        record.policy_action = None
        record.policy_rule_id = None
        record.approval = None
        record.created_at.isoformat.return_value = "2026-05-25T16:00:00+00:00"
        record.updated_at.isoformat.return_value = "2026-05-25T16:00:00+00:00"
        record.executed_at = None
        record.error_message = None

        engine = _make_engine([record])
        engine._records = {"rec-1": record}
        engine.get_records.return_value = [record]
        with patch("fichero_server.api.routes.workflow.orchestration.get_policy_engine", return_value=engine):
            r = client.get("/api/agents/write/audit", params={"document_id": "doc-1"})
        assert r.status_code == 200
        assert engine.get_records.call_args.kwargs["document_id"] == "doc-1"
        assert r.json()["total"] == 1
