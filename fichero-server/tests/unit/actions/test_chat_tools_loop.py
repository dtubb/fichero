"""Route tests for the read-only chat-tools agent loop (#1847 / #3).

Covers the ``POST /api/chat`` wiring of ``fichero_server.actions.chat_tools`` behind the
default-off ``FICHERO_CHAT_TOOLS`` flag:

  * flag OFF -> single-shot RAG, response carries ``tool_calls: []`` (unchanged).
  * flag ON + a read tool -> the read action is dispatched through the audited
    choke point and surfaces as a ``tool_calls[]`` entry (status ok, is_mutation
    False, audit_id set).
  * flag ON + a mutating tool -> the call is DENIED (recorded status error,
    is_mutation True, no audit_id) and the action is NEVER invoked (no audit
    write), enforcing reads-only for this slice.

The LLM is stubbed with a scripted fake that supports ``bind_tools`` + async
``ainvoke``; two throwaway actions (one read-only, one mutating) are registered
on the global registry the loop reads from, and removed afterwards.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry as global_registry,
)
from fichero_server.models import ActionAudit


class _EchoParams(BaseModel):
    value: str = "x"


def _resp(content: str = "", tool_calls=None):
    """A stand-in for a LangChain AIMessage (only .content / .tool_calls used)."""
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


class _ScriptedToolLLM:
    """Fake chat model that replays a fixed list of responses, one per ainvoke."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        return self._scripted.pop(0)


class _FakeRetrievalPayload:
    def __init__(self):
        self.context_docs = []
        self.sources = []
        self.kg_claims_used = 0
        self.kg_entities_used = 0


class _FakeRetriever:
    def retrieve(self, **_kwargs):
        return _FakeRetrievalPayload()


@pytest.fixture
def demo_actions():
    """Register a read-only and a mutating throwaway action; clean up after."""
    write_calls: list = []

    def _read_exec(db, params: _EchoParams, ctx: ActionContext):
        return (
            {"echo": params.value},
            ChangeSpec(domains=["demo"], target_ids=["demo-1"]),
        )

    def _write_exec(db, params: _EchoParams, ctx: ActionContext):
        write_calls.append(params.value)  # must NEVER run in the reads-only slice
        return ({"wrote": params.value}, ChangeSpec(domains=["demo"], target_ids=["demo-1"]))

    global_registry.register(
        ActionRegistration(
            name="demo.read",
            params_model=_EchoParams,
            execute=_read_exec,
            domains=["demo"],
            read_only=True,
        )
    )
    global_registry.register(
        ActionRegistration(
            name="demo.write",
            params_model=_EchoParams,
            execute=_write_exec,
            domains=["demo"],
            read_only=False,
        )
    )
    try:
        yield write_calls
    finally:
        global_registry._actions.pop("demo.read", None)
        global_registry._actions.pop("demo.write", None)


def _stub_llm(monkeypatch, llm):
    monkeypatch.setattr(
        "fichero_server.api.routes.chat._get_langchain_llm",
        lambda *_a, **_k: llm,
    )
    monkeypatch.setattr(
        "fichero_server.api.routes.chat.GraphAwareRetriever",
        lambda *_a, **_k: _FakeRetriever(),
    )


# ---------------------------------------------------------------------------
# Kill switch OFF — single-shot RAG unchanged
# ---------------------------------------------------------------------------


def test_kill_switch_forces_single_shot_with_no_tool_calls(client, monkeypatch):
    """FICHERO_CHAT_TOOLS=0 restores the single-shot RAG path (#2067)."""
    monkeypatch.setenv("FICHERO_CHAT_TOOLS", "0")
    llm = _ScriptedToolLLM([_resp(content="plain answer")])
    _stub_llm(monkeypatch, llm)

    r = client.post("/api/chat", json={"message": "hello"})

    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "plain answer"
    assert data["tool_calls"] == []
    # Single-shot means the tools were never even bound.
    assert llm.bound_tools is None


# ---------------------------------------------------------------------------
# Default (no env var) — the agent loop IS the chat path (#2067)
# ---------------------------------------------------------------------------


def test_default_runs_agent_loop_and_dispatches_read_tool(
    client, db, monkeypatch, demo_actions
):
    """With no flag set, the audited read-only agent loop is the default."""
    monkeypatch.delenv("FICHERO_CHAT_TOOLS", raising=False)
    llm = _ScriptedToolLLM(
        [
            _resp(tool_calls=[{"name": "demo_read", "args": {"value": "hi"}, "id": "c1"}]),
            _resp(content="grounded by a tool"),
        ]
    )
    _stub_llm(monkeypatch, llm)

    r = client.post("/api/chat", json={"message": "look something up"})

    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "grounded by a tool"
    assert len(data["tool_calls"]) == 1
    call = data["tool_calls"][0]
    assert call["action_name"] == "demo.read"
    assert call["status"] == "ok"
    assert call["audit_id"]
    assert db.get(ActionAudit, call["audit_id"]) is not None


def test_default_model_without_bind_tools_falls_back_to_single_shot(
    client, monkeypatch
):
    """A model/provider with no tool support degrades to single-shot, not 500."""
    monkeypatch.delenv("FICHERO_CHAT_TOOLS", raising=False)

    class _NoToolsLLM:
        # No bind_tools attribute at all — binding raises AttributeError.
        async def ainvoke(self, messages):
            return _resp(content="plain single-shot answer")

    _stub_llm(monkeypatch, _NoToolsLLM())

    r = client.post("/api/chat", json={"message": "hello"})

    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "plain single-shot answer"
    assert data["tool_calls"] == []


def test_read_tool_dispatch_failure_surfaces_as_error_tool_call(
    client, db, monkeypatch
):
    """A read tool that RAISES is recorded as a status=error tool_call — the
    failure is visible in the payload, never silently dropped, and the turn
    still completes with the model's final answer."""
    monkeypatch.delenv("FICHERO_CHAT_TOOLS", raising=False)

    def _boom_exec(db, params: _EchoParams, ctx: ActionContext):
        raise RuntimeError("index unavailable")

    global_registry.register(
        ActionRegistration(
            name="demo.boom",
            params_model=_EchoParams,
            execute=_boom_exec,
            domains=["demo"],
            read_only=True,
        )
    )
    try:
        llm = _ScriptedToolLLM(
            [
                _resp(tool_calls=[{"name": "demo_boom", "args": {"value": "x"}, "id": "c1"}]),
                _resp(content="answered despite tool failure"),
            ]
        )
        _stub_llm(monkeypatch, llm)

        r = client.post("/api/chat", json={"message": "try the broken tool"})

        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "answered despite tool failure"
        assert len(data["tool_calls"]) == 1
        call = data["tool_calls"][0]
        assert call["action_name"] == "demo.boom"
        assert call["status"] == "error"
        assert call["audit_id"] is None
    finally:
        global_registry._actions.pop("demo.boom", None)


def test_default_llm_error_still_raises_never_silent(client, monkeypatch):
    """An LLM failure inside the default loop surfaces as an error, not a fake answer."""
    monkeypatch.delenv("FICHERO_CHAT_TOOLS", raising=False)

    class _BrokenLLM:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("provider exploded")

    _stub_llm(monkeypatch, _BrokenLLM())

    with pytest.raises(RuntimeError, match="provider exploded"):
        client.post("/api/chat", json={"message": "hello"})


# ---------------------------------------------------------------------------
# Flag ON — read tool dispatched, mutating tool denied
# ---------------------------------------------------------------------------


def test_flag_on_read_tool_is_dispatched_and_surfaced(
    client, db, monkeypatch, demo_actions
):
    monkeypatch.setenv("FICHERO_CHAT_TOOLS", "1")
    llm = _ScriptedToolLLM(
        [
            _resp(tool_calls=[{"name": "demo_read", "args": {"value": "hi"}, "id": "c1"}]),
            _resp(content="final grounded answer"),
        ]
    )
    _stub_llm(monkeypatch, llm)

    r = client.post("/api/chat", json={"message": "look something up"})

    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "final grounded answer"
    assert len(data["tool_calls"]) == 1
    call = data["tool_calls"][0]
    assert call["action_name"] == "demo.read"
    assert call["status"] == "ok"
    assert call["is_mutation"] is False
    assert call["actor"]
    assert call["audit_id"]
    # The read went through the audited choke point.
    assert db.get(ActionAudit, call["audit_id"]) is not None
    # Only read-only tools were ever offered to the model.
    offered = {t["function"]["name"] for t in llm.bound_tools}
    assert "demo_read" in offered
    assert "demo_write" not in offered


def test_flag_on_mutating_tool_is_denied_and_never_invoked(
    client, db, monkeypatch, demo_actions
):
    monkeypatch.setenv("FICHERO_CHAT_TOOLS", "1")
    write_calls = demo_actions
    llm = _ScriptedToolLLM(
        [
            # Model tries to invoke a mutating action anyway (hallucinated/forced).
            _resp(tool_calls=[{"name": "demo_write", "args": {"value": "boom"}, "id": "c1"}]),
            _resp(content="acknowledged"),
        ]
    )
    _stub_llm(monkeypatch, llm)

    audits_before = len(list(db.all(ActionAudit)))

    r = client.post("/api/chat", json={"message": "please write"})

    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "acknowledged"
    assert len(data["tool_calls"]) == 1
    call = data["tool_calls"][0]
    assert call["action_name"] == "demo.write"
    assert call["status"] == "error"
    assert call["is_mutation"] is True
    assert call["audit_id"] is None
    # The mutating action was NEVER executed and wrote NO audit row.
    assert write_calls == []
    assert len(list(db.all(ActionAudit))) == audits_before
