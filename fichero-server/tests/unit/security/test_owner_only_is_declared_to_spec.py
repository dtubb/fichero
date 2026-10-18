"""`sharing.owner-only-asserted-in-the-action` (#5766): an owner-only action is DECLARED on its registration
(`owner_only=True`) and the registry refuses a non-owner before the action runs, so `/api/actions/invoke`, MCP and
chat cannot reach it with library WRITE alone. A guardrail keeps the declaration and the docstrings honest.

WHY: `POST /api/actions/invoke` asserts only library WRITE. Each owner-only action had to remember to assert
ownership itself; one that forgot was an editor-to-owner hole. The flag makes the rule central."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ActionRegistration, registry
from fichero_server.security.authz import AuthorizationError


class _Nothing(BaseModel):
    pass


def _register(name: str, ran: list[str], *, owner_only: bool) -> None:
    def execute(db, params, ctx):
        ran.append(name)
        from fichero_server.actions.registry import ChangeSpec

        return {}, ChangeSpec(domains=["test"], target_ids=[], before=None, after=None, emit_type="test.ran")

    registry.register(ActionRegistration(name=name, params_model=_Nothing, execute=execute, domains=["test"],
                                         owner_only=owner_only))


def test_an_owner_only_action_refuses_a_non_owner_before_it_runs(db, monkeypatch):
    from fichero_server.security import authz

    ran: list[str] = []
    _register("test.owner_only_probe", ran, owner_only=True)
    _register("test.open_probe", ran, owner_only=False)
    monkeypatch.setattr(authz, "assert_can_write", lambda *a, **k: None)  # the caller has library WRITE...

    def not_the_owner(user, library):
        raise AuthorizationError("owner access required", required="owner")

    monkeypatch.setattr(authz, "require_owner", not_the_owner)  # ...but is not an owner
    editor = ActionContext(actor="editor", library_path="/tmp/lib.fichero")

    with pytest.raises(AuthorizationError):
        registry.invoke(db, "test.owner_only_probe", {}, editor)
    assert ran == [], "the action ran before the owner check"
    registry.invoke(db, "test.open_probe", {}, editor)  # an action not declared owner-only is unaffected
    assert ran == ["test.open_probe"]
    # the loopback owner (bootstrap) passes
    registry.invoke(db, "test.owner_only_probe", {}, ActionContext(actor="owner", library_path="/tmp/lib.fichero",
                                                                  is_bootstrap=True))
    assert ran[-1] == "test.owner_only_probe"


def test_every_action_whose_doc_says_owner_only_declares_it():
    """The guardrail: a docstring that says owner-only without the flag is a hole waiting to be found."""
    import fichero_server.api.main  # noqa: F401  (registers every action)

    wrong = [name for name, reg in sorted(registry._actions.items())
             if not reg.owner_only and any(p in (reg.execute.__doc__ or "").lower()
                                           for p in ("owner-only", "owner only", "only the owner"))]
    assert not wrong, f"documented as owner-only but not declared owner_only=True: {wrong}"


def test_the_access_actions_are_declared():
    import fichero_server.api.main  # noqa: F401

    assert registry.get("acl.set").owner_only is True
