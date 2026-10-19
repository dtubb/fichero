"""`mcp.client.available-to-chat-is-off-by-default`, `mcp.client.tools-reach-the-agent` and
`mcp.client.chat-calls-are-audited` (#5761, ruled 2026-10-18).

A REAL stdio MCP server (`_echo_mcp_server.py`: `echo` marked read-only, `shout` not) is saved through
`/api/mcp-servers`. The chat loop's model is scripted; what it is offered and what a call leaves behind is read back."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.models import ActionAudit

ECHO = Path(__file__).with_name("_echo_mcp_server.py")


def _resp(content: str = "", tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


class _ScriptedToolLLM:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.seen = list(messages)
        step = self._scripted.pop(0)
        return step(self) if callable(step) else step


class _Retriever:
    def retrieve(self, **_kwargs):
        return SimpleNamespace(context_docs=[], sources=[], kg_claims_used=0, kg_entities_used=0)


@pytest.fixture(autouse=True)
def _clean_manager():
    from fichero_server.mcp.manager import get_mcp_manager
    from fichero_server.workflows.registry import TOOL_DEFS, TOOLS

    yield
    for name in [n for n, d in TOOL_DEFS.items() if d.category.startswith("mcp")]:
        TOOL_DEFS.pop(name, None)
        TOOLS.pop(name, None)
    manager = get_mcp_manager()
    for server in list(manager.list_servers()):
        manager.remove_server(server.name)
    manager.clear_cache()


@pytest.fixture
def server(client, monkeypatch):
    monkeypatch.setenv("FICHERO_MCP_STDIO_ALLOWLIST", Path(sys.executable).name)
    made = client.post("/api/mcp-servers", json={"name": "echoer", "transport": "stdio", "command": sys.executable,
                                                  "args": [str(ECHO)], "enabled": True})
    assert made.status_code == 200, made.text
    return made.json()


def _chat(client, monkeypatch, scripted):
    llm = _ScriptedToolLLM(scripted)
    monkeypatch.delenv("FICHERO_CHAT_TOOLS", raising=False)
    monkeypatch.setattr("fichero_server.api.routes.system.chat._get_langchain_llm", lambda *_a, **_k: llm)
    monkeypatch.setattr("fichero_server.api.routes.system.chat.GraphAwareRetriever", lambda *_a, **_k: _Retriever())
    response = client.post("/api/chat", json={"message": "use the tools"})
    assert response.status_code == 200, response.text
    return llm, response.json()


def _call(suffix: str, **args):
    """A scripted step: call the bound tool whose name ends with `suffix` (or a made-up name when none is bound)."""
    def step(llm):
        name = next((n for n in _names(llm) if n.endswith(suffix)), f"mcp_echoer_{suffix}")
        return _resp(tool_calls=[{"name": name, "args": args, "id": "c1"}])
    return step


def _names(llm) -> list[str]:
    return [t.get("function", t).get("name", "") for t in (llm.bound_tools or [])]


def test_a_new_server_is_not_available_to_chat_and_its_tools_are_absent(client, monkeypatch, server):
    assert server["available_to_chat"] is False
    llm, _ = _chat(client, monkeypatch, [_resp(content="ok")])
    assert not [n for n in _names(llm) if "echo" in n or "shout" in n], _names(llm)


def test_switched_on_its_read_only_tools_are_bound_and_a_call_is_audited(client, db, monkeypatch, server):
    put = client.put(f"/api/mcp-servers/{server['id']}", json={"available_to_chat": True})
    assert put.status_code == 200 and put.json()["available_to_chat"] is True, put.text

    llm, data = _chat(client, monkeypatch, [_call("echo", text="hi"), _resp(content="done")])
    names = _names(llm)
    assert any(n.endswith("echo") for n in names), names
    assert not any(n.endswith("shout") for n in names), "a tool the server does not mark read-only is not offered"

    (call,) = data["tool_calls"]
    assert call["status"] == "ok" and call["audit_id"], call
    audit = db.get(ActionAudit, call["audit_id"])
    assert audit.action_name == "mcp.call_tool"
    assert audit.params["server"] == "echoer" and audit.params["tool"].endswith("echo")


def test_a_call_to_a_tool_that_is_not_read_only_is_refused_and_leaves_no_audit(client, db, monkeypatch, server):
    client.put(f"/api/mcp-servers/{server['id']}", json={"available_to_chat": True})
    _, data = _chat(client, monkeypatch, [_call("shout", text="hi"), _resp(content="done")])
    (call,) = data["tool_calls"]
    assert call["status"] == "error" and not call["audit_id"], call


def test_switched_off_again_its_tools_leave_chat(client, monkeypatch, server):
    client.put(f"/api/mcp-servers/{server['id']}", json={"available_to_chat": True})
    client.put(f"/api/mcp-servers/{server['id']}", json={"available_to_chat": False})
    llm, _ = _chat(client, monkeypatch, [_resp(content="ok")])
    assert not [n for n in _names(llm) if "echo" in n], _names(llm)


def test_the_switch_itself_is_audited(client, monkeypatch, server):
    from fichero_server.db.app import get_app_db

    client.put(f"/api/mcp-servers/{server['id']}", json={"available_to_chat": True})
    rows = [a for a in get_app_db().list_action_audits() if a.action_name == "mcp_server.set_available_to_chat"]
    assert rows and rows[-1].target_ids == [server["id"]] and rows[-1].params["available_to_chat"] is True


def test_a_server_that_will_not_start_is_named_to_the_chat_with_its_error_type(client, monkeypatch):
    made = client.post("/api/mcp-servers", json={"name": "broken", "transport": "stdio", "command": "/no/such/mcp-server",
                                                  "args": [], "enabled": True, "available_to_chat": True})
    assert made.status_code == 200, made.text
    llm, _ = _chat(client, monkeypatch, [_resp(content="ok")])
    notes = [str(m.content) for m in llm.seen if "could not start" in str(getattr(m, "content", ""))]
    assert notes and "broken (" in notes[0], notes
