"""Unit tests for chat tools generated from the action registry (#2016 / #1847).

Covers:
  * ``action_tools()`` returns exactly one OpenAI/LiteLLM tool def per registered
    action, each with a valid tool name, a non-empty description, and a valid
    JSON-schema ``parameters`` block.
  * a known action (``claim.create``) maps to the right sanitised tool name and
    carries the right required fields in its parameter schema.
  * name sanitisation + reverse resolution round-trip (incl. ``:`` and ``.``).
  * dispatching a tool call runs the action through the audited ``registry.invoke``
    choke point — returns the result, threads ``actor='chat'`` + ``origin_window``,
    and writes an ``ActionAudit`` row.
  * argument coercion (JSON-string and ``None``) and unknown-tool errors.

Uses the shared conftest ``db`` fixture (a real Database on a temp .fichero pkg).
"""

from __future__ import annotations

import re

import pytest
from pydantic import BaseModel

# Importing route modules registers their actions via the @action decorator at
# import time — this is what populates the global registry for the chat agent.
import fichero.api.routes.claim.claims  # noqa: F401  (registers claim.* actions)
import fichero.api.routes.actions  # noqa: F401  (registers actionlib.* actions)
from fichero.actions.chat_tools import (
    action_tool,
    action_tools,
    available_tool_names,
    dispatch_tool_call,
    is_read_only_action,
    resolve_action_name,
    tool_name_for,
)
from fichero.actions.registry import (
    ActionContext,
    ActionNotFoundError,
    ActionRegistration,
    ActionRegistry,
    ChangeSpec,
    registry as global_registry,
)
from fichero.models import ActionAudit

_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


# ---------------------------------------------------------------------------
# Helpers — an isolated registry with a throwaway action
# ---------------------------------------------------------------------------


class _DummyParams(BaseModel):
    """Echo a value back (dummy chat-tool params)."""

    value: str


def _make_registry() -> tuple[ActionRegistry, str]:
    """A fresh registry holding one dummy action — never touches the global one."""
    reg = ActionRegistry()
    name = "demo.echo"

    def _execute(db, params: _DummyParams, ctx: ActionContext):
        return (
            {"echo": params.value, "actor": ctx.actor},
            ChangeSpec(
                domains=["demo"],
                target_ids=["demo-1"],
                before={"v": "old"},
                after={"v": params.value},
                emit_type="demo.changed",
                entity_ids=["demo-1"],
            ),
        )

    reg.register(
        ActionRegistration(
            name=name,
            params_model=_DummyParams,
            execute=_execute,
            domains=["demo"],
            undoable=False,
        )
    )
    return reg, name


# ---------------------------------------------------------------------------
# action_tools() shape
# ---------------------------------------------------------------------------


class TestActionTools:
    def test_one_tool_per_registered_action_with_valid_shape(self):
        tools = action_tools()
        actions = global_registry.all()

        assert len(tools) == len(actions)
        assert len(tools) > 0  # route imports registered real actions

        seen_names = set()
        for tool in tools:
            assert tool["type"] == "function"
            fn = tool["function"]
            # Valid OpenAI tool name.
            assert _TOOL_NAME_RE.match(fn["name"]), fn["name"]
            # Names are unique across the tool list.
            assert fn["name"] not in seen_names, f"duplicate tool name {fn['name']}"
            seen_names.add(fn["name"])
            # Non-empty description (OpenAI rejects blanks).
            assert fn["description"].strip()
            # parameters is a JSON-schema object.
            params = fn["parameters"]
            assert isinstance(params, dict)
            assert params.get("type") == "object"
            assert "properties" in params

    def test_tools_match_an_explicit_registry(self):
        reg, name = _make_registry()
        tools = action_tools(reg)
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "demo_echo"
        assert tools[0]["function"]["parameters"]["required"] == ["value"]

    def test_action_tool_uses_params_model_docstring_as_description(self):
        reg, _ = _make_registry()
        tool = action_tool(reg.all()[0])
        # _DummyParams docstring -> first paragraph.
        assert tool["function"]["description"] == "Echo a value back (dummy chat-tool params)."

    def test_description_falls_back_when_no_docstring(self):
        reg = ActionRegistry()

        class _Bare(BaseModel):
            x: int

        def _exec(db, params, ctx):
            return None, ChangeSpec(domains=["bare"])

        reg.register(
            ActionRegistration(
                name="bare.op", params_model=_Bare, execute=_exec, domains=["bare"]
            )
        )
        tool = action_tool(reg.all()[0])
        assert tool["function"]["description"] == "Invoke the 'bare.op' action."


# ---------------------------------------------------------------------------
# Known action — claim.create
# ---------------------------------------------------------------------------


class TestKnownAction:
    def test_claim_create_tool_name_and_required_fields(self):
        tools = action_tools()
        by_name = {t["function"]["name"]: t for t in tools}

        assert "claim_create" in by_name, sorted(by_name)
        fn = by_name["claim_create"]["function"]

        # The dotted action name sanitised to a legal tool name.
        assert tool_name_for("claim.create") == "claim_create"
        # ClaimCreateRequest: only `text` has no default -> the sole required field.
        assert fn["parameters"]["required"] == ["text"]
        assert "text" in fn["parameters"]["properties"]
        # Description comes from ClaimCreateRequest's docstring.
        assert "claim" in fn["description"].lower()


# ---------------------------------------------------------------------------
# Name mapping
# ---------------------------------------------------------------------------


class TestNameMapping:
    def test_tool_name_for_sanitises_dot_and_colon(self):
        assert tool_name_for("claim.create") == "claim_create"
        assert tool_name_for("classification:rename") == "classification_rename"
        assert tool_name_for("already_legal-name") == "already_legal-name"

    def test_resolve_accepts_exact_and_sanitised(self):
        reg, name = _make_registry()  # name == "demo.echo"
        assert resolve_action_name("demo.echo", reg) == name
        assert resolve_action_name("demo_echo", reg) == name

    def test_resolve_unknown_raises(self):
        reg, _ = _make_registry()
        with pytest.raises(ActionNotFoundError):
            resolve_action_name("nope_missing", reg)

    def test_available_tool_names(self):
        reg, _ = _make_registry()
        assert available_tool_names(reg) == ["demo_echo"]


# ---------------------------------------------------------------------------
# Dispatch through the audited choke point
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_invokes_action_returns_result_and_writes_audit(
        self, db, monkeypatch
    ):
        reg, _ = _make_registry()
        # Spy on emit_change to confirm origin_window threads through.
        calls = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        result = dispatch_tool_call(
            db,
            "demo_echo",
            {"value": "hi"},
            actor="chat",
            origin_window="win-1",
            library_path="/lib/test.fichero",
            reg=reg,
        )

        # (a) ActionResult: the action ran and echoed actor='chat'.
        assert result.ok is True
        assert result.result == {"echo": "hi", "actor": "chat"}
        assert result.changed_domains == ["demo"]
        assert result.audit_id

        # (b) ActionAudit row persisted with actor='chat'.
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "demo.echo"
        assert audit.actor == "chat"
        assert audit.params == {"value": "hi"}
        assert audit.before == {"v": "old"}
        assert audit.after == {"v": "hi"}

        # (c) emit_change fired with origin_window threaded through.
        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["type"] == "demo.changed"
        assert kwargs["origin_window"] == "win-1"
        assert kwargs["actor"] == "chat"

    def test_dispatch_accepts_exact_action_name(self, db):
        reg, _ = _make_registry()
        result = dispatch_tool_call(
            db, "demo.echo", {"value": "x"}, library_path=None, reg=reg
        )
        assert result.result["echo"] == "x"

    def test_dispatch_parses_json_string_arguments(self, db):
        reg, _ = _make_registry()
        result = dispatch_tool_call(
            db, "demo_echo", '{"value": "from-json"}', library_path=None, reg=reg
        )
        assert result.result["echo"] == "from-json"

    def test_dispatch_none_arguments_become_empty_dict(self, db):
        reg = ActionRegistry()

        class _NoArgs(BaseModel):
            pass

        def _exec(db_, params, ctx):
            return {"ran": True}, ChangeSpec(domains=["noargs"])

        reg.register(
            ActionRegistration(
                name="noargs.run", params_model=_NoArgs, execute=_exec, domains=["noargs"]
            )
        )
        result = dispatch_tool_call(db, "noargs_run", None, library_path=None, reg=reg)
        assert result.result == {"ran": True}

    def test_dispatch_unknown_tool_raises(self, db):
        reg, _ = _make_registry()
        with pytest.raises(ActionNotFoundError):
            dispatch_tool_call(db, "ghost_tool", {}, library_path=None, reg=reg)

    def test_dispatch_defaults_actor_to_chat(self, db):
        reg, _ = _make_registry()
        result = dispatch_tool_call(
            db, "demo_echo", {"value": "y"}, library_path=None, reg=reg
        )
        # Default actor flows into ctx -> execute saw "chat".
        assert result.result["actor"] == "chat"
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.actor == "chat"


# ---------------------------------------------------------------------------
# Read-only gating (#1847 / #3) — the safe subset the chat loop may call
# ---------------------------------------------------------------------------


def _make_read_write_registry() -> ActionRegistry:
    """A registry with one read-only action and one mutating action."""
    reg = ActionRegistry()

    def _execute(db, params: _DummyParams, ctx: ActionContext):
        return (
            {"echo": params.value},
            ChangeSpec(domains=["demo"], target_ids=["demo-1"], emit_type="demo.changed"),
        )

    reg.register(
        ActionRegistration(
            name="demo.read",
            params_model=_DummyParams,
            execute=_execute,
            domains=["demo"],
            read_only=True,
        )
    )
    reg.register(
        ActionRegistration(
            name="demo.write",
            params_model=_DummyParams,
            execute=_execute,
            domains=["demo"],
            read_only=False,
        )
    )
    return reg


class TestReadOnlyGate:
    def test_registered_actions_default_to_mutating(self):
        # Every real action registered by the route modules is a write path —
        # none opts into read_only, so the safe subset is empty by default.
        assert action_tools(read_only=True) == []

    def test_action_tools_read_only_filters_to_flagged_actions(self):
        reg = _make_read_write_registry()
        all_tools = {t["function"]["name"] for t in action_tools(reg)}
        read_tools = {t["function"]["name"] for t in action_tools(reg, read_only=True)}
        assert all_tools == {"demo_read", "demo_write"}
        assert read_tools == {"demo_read"}

    def test_is_read_only_action_by_tool_and_action_name(self):
        reg = _make_read_write_registry()
        assert is_read_only_action("demo_read", reg) is True
        assert is_read_only_action("demo.read", reg) is True
        assert is_read_only_action("demo_write", reg) is False
        assert is_read_only_action("demo.write", reg) is False

    def test_is_read_only_action_unknown_raises(self):
        reg = _make_read_write_registry()
        with pytest.raises(ActionNotFoundError):
            is_read_only_action("ghost_tool", reg)

    def test_read_only_action_still_dispatches_through_audit(self, db):
        reg = _make_read_write_registry()
        result = dispatch_tool_call(
            db, "demo_read", {"value": "hi"}, library_path=None, reg=reg
        )
        assert result.ok is True
        assert result.result == {"echo": "hi"}
