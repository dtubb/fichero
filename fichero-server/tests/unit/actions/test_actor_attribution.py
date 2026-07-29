from __future__ import annotations

import pytest
from pydantic import BaseModel

from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero_server.api.auth import action_context, actor_from_request
from fichero_server.models import ActionAudit
from fichero_server.workflows.tools import _workflow_change_emit


class _ActorParams(BaseModel):
    value: str


@pytest.fixture
def actor_action():
    name = "test.actor_attr"

    def _execute(db, params: _ActorParams, ctx: ActionContext):
        return (
            {"actor_seen": ctx.actor, "value": params.value},
            ChangeSpec(
                domains=["test"],
                target_ids=["actor-target"],
                before={"value": "before"},
                after={"value": params.value},
                emit_type="test.actor_changed",
                entity_ids=["actor-target"],
            ),
        )

    registry.register(
        ActionRegistration(
            name=name,
            params_model=_ActorParams,
            execute=_execute,
            domains=["test"],
        )
    )
    yield name
    registry._actions.pop(name, None)


def test_actor_from_request_prefers_username_and_falls_back_to_system():
    class _State:
        user = type("User", (), {"username": "alice", "id": "user-id"})()

    request = type("Request", (), {"state": _State()})()
    assert actor_from_request(request) == "alice"

    request.state.user = None
    assert actor_from_request(request) == "system"


def test_registry_invoke_uses_authenticated_request_state_not_forged_actor(
    db,
    actor_action,
    monkeypatch,
):
    class _State:
        user = type("User", (), {"username": "alice", "id": "user-id"})()

    request = type(
        "Request",
        (),
        {
            "state": _State(),
            "headers": {"X-Fichero-Actor": "mallory"},
            "body": {"actor": "mallory"},
        },
    )()
    captured: list[dict] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda _library_path, **kwargs: captured.append(kwargs),
    )

    ctx = action_context(request, "/lib/test.fichero", "win-1")
    result = registry.invoke(
        db,
        actor_action,
        {"value": "after"},
        ctx,
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "alice"
    assert captured[0]["actor"] == "alice"
    assert captured[0]["origin_window"] == "win-1"
    assert captured[0]["origin_user"] == "alice"


def test_multiuser_off_request_state_keeps_system_actor(
    db,
    actor_action,
):
    class _State:
        user = None

    request = type("Request", (), {"state": _State()})()
    result = registry.invoke(
        db,
        actor_action,
        {"value": "after"},
        action_context(request, "/lib/test.fichero", None),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "system"


def test_action_context_marks_bootstrap_requests():
    class _State:
        user = None
        bootstrap_auth = True

    request = type("Request", (), {"state": _State()})()
    ctx = action_context(request, "/lib/test.fichero", None)

    assert ctx.actor == "system"
    assert ctx.is_bootstrap is True


def test_workflow_emit_preserves_workflow_actor(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(
        _workflow_change_emit,
        "emit_change",
        lambda _library_path, **kwargs: captured.append(kwargs),
    )

    _workflow_change_emit.emit_workflow_kg_changes(
        "/lib/test.fichero",
        entity_ids=["e1"],
        claim_ids=["c1"],
        document_ids=["d1"],
    )

    assert [call["actor"] for call in captured] == [
        "workflow",
        "workflow",
        "workflow",
    ]
