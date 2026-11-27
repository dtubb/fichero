"""builder-console.mcp.same-reads-and-controls: `builder mcp` serves the console's reads and controls as MCP tools over stdio."""
from __future__ import annotations

import io
import json

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import console, journal, mcp_server, review_page


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(console, "ROOT", tmp_path)
    monkeypatch.setattr(console, "_STATUS", {"at": 0.0, "data": None})
    lanes = [{"id": "a", "worktree": "/nonexistent/a", "cursor": 0, "paused": False, "kind": "worker",
              "steps": [{"step": "s1", "state": "queued", "issues": [7], "why": "", "brief": "/nonexistent/brief"}]}]
    monkeypatch.setattr(console.queue, "load", lambda: lanes)
    ran = []
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (0, "ok"))
    monkeypatch.setattr(review_page, "_gh", lambda *a: pytest.fail("the real gh is never called"))
    journal.append("alert", id="a-s1-1", lane="a", step="s1", what="red at pytest", actions=["retry", "park"])
    review_page.add("c", title="the caret")
    return ran


def _talk(*msgs) -> list[dict]:
    out = io.StringIO()
    mcp_server.serve(io.StringIO("".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in msgs)), out)
    return [json.loads(ln) for ln in out.getvalue().splitlines()]


def _call(name, args=None, mid=1):
    (r,) = _talk({"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})
    res = r["result"]
    return res.get("isError", False), res["content"][0]["text"]


def test_the_server_speaks_initialize_and_lists_the_consoles_reads_and_controls_as_tools(state):
    init, listed, pong, bad, parse = _talk(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        "not json")
    assert init["result"]["protocolVersion"] == "2025-06-18" and init["result"]["capabilities"] == {"tools": {}} and init["result"]["serverInfo"]["name"]
    tools = {t["name"]: t for t in listed["result"]["tools"]}
    assert sorted(tools) == sorted(["status", "lanes", "alerts", "now", "review_list", "thread", "lane_pause", "lane_resume", "alert_answer", "review_verdict", "message_manager"])
    assert all(t["description"] and t["inputSchema"]["type"] == "object" for t in tools.values()) and tools["alert_answer"]["inputSchema"]["required"] == ["id", "action"]
    assert pong == {"jsonrpc": "2.0", "id": 3, "result": {}}, "a notification gets no reply; ping gets an empty result"
    assert bad["error"]["code"] == -32601 and parse["error"]["code"] == -32700 and parse["id"] is None


def test_each_read_tool_returns_what_the_consoles_function_returns(state, monkeypatch):
    monkeypatch.setattr(console, "status_cached", lambda: {"lanes": [{"lane": "a"}], "spend_today_usd": 1.5})
    assert json.loads(_call("status")[1]) == {"lanes": [{"lane": "a"}], "spend_today_usd": 1.5}
    assert json.loads(_call("lanes")[1]) == [{"lane": "a"}]
    assert json.loads(_call("alerts")[1]) == json.loads(json.dumps(console.alerts_view(journal.read()))) and json.loads(_call("alerts")[1])["count"] == 1
    assert [x["lane"] for x in json.loads(_call("now")[1])["lanes"]] == ["a"]
    assert [i["id"] for i in json.loads(_call("review_list")[1])["items"]] == ["c"]
    assert json.loads(_call("thread")[1]) == {"messages": []}


def test_a_control_tool_runs_the_pages_verb_and_writes_the_same_console_row_as_who_mcp(state):
    ran = state
    for name, args, want in [("lane_pause", {"lane": "a"}, ["queue", "pause", "--lane", "a"]),
                             ("lane_resume", {"lane": "a"}, ["queue", "resume", "--lane", "a"]),
                             ("alert_answer", {"id": "a-s1-1", "action": "retry"}, ["alert", "a-s1-1", "retry"])]:
        err, text = _call(name, args)
        assert not err and ran[-1][3:3 + len(want)] == want and json.loads(text)["ok"] is True, (name, text)
    rows = [r for r in journal.read() if r["event"] == "console"]
    assert [(r["verb"], r["state"], r["who"]) for r in rows] == [(v, s, "mcp") for v in ("pause", "resume", "alert") for s in ("started", "ended")]
    err, text = _call("review_verdict", {"id": "c", "status": "works", "note": "good"})
    assert not err and json.loads(text)["status"] == "works" and review_page.load()["items"][0]["note"] == "good"
    assert [r["who"] for r in journal.read() if r["event"] == "console" and r.get("verb") == "review c works"] == ["mcp"]
    err, text = _call("message_manager", {"text": "hold lane a"})
    assert not err and json.loads((journal.STATE / "manager" / "inbox.jsonl").read_text())["text"] == "hold lane a"
    assert [r["who"] for r in journal.read() if r["event"] == "owner-message"] == ["mcp"]


def test_an_unknown_tool_a_missing_argument_and_a_refused_control_are_error_results_never_a_crash(state):
    assert _call("rm_rf")[0] is True and "no tool" in _call("rm_rf")[1]
    assert _call("lane_pause")[0] is True and "lane" in _call("lane_pause")[1]
    assert _call("lane_pause", {"lane": "--root"})[0] is True, "a flag as a value is refused by the console's own check"
    assert _call("review_verdict", {"id": "zz", "status": "works"})[0] is True
    assert _call("message_manager", {"text": "  "})[0] is True
    assert state == [], "nothing ran"


def test_the_mcp_verb_serves_stdio_on_the_roots_state(state, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert cli.main(["mcp", "--root", str(tmp_path), "--state", str(tmp_path)]) == 0
    assert json.loads(out.getvalue()) == {"jsonrpc": "2.0", "id": 1, "result": {}}
