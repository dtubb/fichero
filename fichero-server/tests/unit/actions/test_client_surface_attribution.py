"""#4469: audit rows record WHICH client surface used a credential.

An MCP mutation on the owner token used to audit as bare ``actor="owner"`` —
indistinguishable from Daniel clicking in the app. The X-Fichero-Client header
now flows into ``ActionContext.client`` and onto the ``ActionAudit`` row, so
the record says "owner, via fichero-mcp". Attribution only: the header can
refine the surface, never the actor — actor still comes exclusively from
authenticated request state.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero_server.api.auth import action_context
from fichero_server.models import ActionAudit


class _Params(BaseModel):
    value: str


@pytest.fixture
def surface_action():
    name = "test.client_surface"

    def _execute(db, params: _Params, ctx: ActionContext):
        return (
            {"value": params.value},
            ChangeSpec(domains=["test"], target_ids=["t-1"]),
        )

    registry.register(
        ActionRegistration(
            name=name, params_model=_Params, execute=_execute, domains=["test"]
        )
    )
    yield name
    registry._actions.pop(name, None)


def _request_with_owner_state():
    class _State:
        user = type("User", (), {"username": "owner", "id": "owner-id"})()
        bootstrap_auth = True

    return type("Request", (), {"state": _State()})()


def test_action_context_carries_the_client_header():
    ctx = action_context(
        _request_with_owner_state(),
        x_fichero_library_path="/tmp/lib.fichero",
        x_fichero_origin_window=None,
        x_fichero_client="fichero-mcp",
    )
    assert ctx.actor == "owner", "the header must never change the actor"
    assert ctx.client == "fichero-mcp"


def test_absent_header_means_client_none_not_a_guess():
    ctx = action_context(
        _request_with_owner_state(),
        x_fichero_library_path="/tmp/lib.fichero",
        x_fichero_origin_window=None,
        x_fichero_client=None,
    )
    assert ctx.client is None


def test_invoke_persists_client_on_the_audit_row(db, surface_action):
    ctx = ActionContext(
        actor="owner",
        client="fichero-mcp",
        library_path=str(getattr(db, "library_path", "") or "/tmp/lib.fichero"),
        is_bootstrap=True,
    )
    result = registry.invoke(db, surface_action, {"value": "x"}, ctx)
    rows = [a for a in db.all(ActionAudit) if a.id == result.audit_id]
    assert len(rows) == 1
    assert rows[0].actor == "owner"
    assert rows[0].client == "fichero-mcp", (
        "an MCP mutation must be distinguishable from the owner in the app; "
        "a bare actor=owner row is a false audit (#4469)"
    )


def test_rows_without_a_client_stay_none(db, surface_action):
    ctx = ActionContext(
        actor="owner",
        library_path=str(getattr(db, "library_path", "") or "/tmp/lib.fichero"),
        is_bootstrap=True,
    )
    result = registry.invoke(db, surface_action, {"value": "y"}, ctx)
    rows = [a for a in db.all(ActionAudit) if a.id == result.audit_id]
    assert rows[0].client is None
