"""pipeline.three-faces: the CLI, the MCP server and the page call the same function; per-role MCP tools; no approve
or answer over MCP; a worker's shell cannot run the runner's controls."""
from __future__ import annotations

import json

import pytest

from pipeline import __main__ as cli
from pipeline import core, mcp_server, web


def test_cli_mcp_and_page_call_the_same_function(scratch, monkeypatch, capsys):
    calls = []
    monkeypatch.setitem(core.API, "point", lambda milestone: calls.append(("point", milestone)) or {"point": milestone})
    cli.main(["point", "demo"])  # CLI
    assert json.loads(capsys.readouterr().out)["point"] == "demo"
    assert mcp_server.tools_for("manager")["point"] is core.API["point"]  # MCP: the very same object
    assert "point" in web.COMMANDS  # page: Handler.do_POST dispatches core.API[name]
    assert calls == [("point", "demo")]
    for name in web.COMMANDS:
        assert name in core.API


def test_mcp_has_no_approve_or_answer_tool():
    for role in core.ROLE_TOOLS:
        tools = mcp_server.tools_for(role)
        assert "answer" not in tools and not any(t.startswith("approve") for t in tools), role
    assert set(mcp_server.tools_for("coder")) == {"report", "ask", "done"}
    assert "verdict" in mcp_server.tools_for("reviewer") and "verdict" not in mcp_server.tools_for("coder")


def test_mcp_server_builds_with_the_sdk():
    server = mcp_server.build("coder")
    names = {t.name for t in server._tool_manager.list_tools()}
    assert names == {"report", "ask", "done"}


def test_mcp_start_and_check_take_the_dispatch_lock(scratch, issues, fake_coder):
    """Review MED 6: the lock lives inside core.start/check, so every face holds it."""
    from pipeline import journal
    fake_coder()
    with journal.Lock("dispatch"):
        with pytest.raises(BlockingIOError):
            mcp_server.tools_for("manager")["start"]([1001])
    assert core.start([1001])["items"][1001] == "checked"
    with journal.Lock("dispatch"):
        with pytest.raises(BlockingIOError):
            core.check(1001)


def test_cli_file_bug_is_a_dry_run_by_default(scratch, capsys):
    cli.main(["file-bug", "a title", "seen x, expected y, tests/test_z.py"])
    out = json.loads(capsys.readouterr().out)
    assert out["result"].startswith("DRY RUN: gh issue create") and "type:bug" in out["command"]
    assert core.DRY_RUN is True


def test_cli_verdict_needs_an_explicit_role(scratch, capsys):
    with pytest.raises(SystemExit):
        cli.main(["verdict", "1001", "abc", "READY"])


def test_a_worker_shell_cannot_run_the_runners_controls(scratch, monkeypatch, capsys):
    """Review MED 5: PIPELINE_WORKER marks a worker's shell; the CLI refuses verdict, answer, start, check, tell…"""
    monkeypatch.setenv("PIPELINE_WORKER", "coder")
    for argv in (["verdict", "1001", "abc", "READY", "--by", "reviewer"], ["answer", "q", "yes"], ["start", "1001"],
                 ["retry", "1001"], ["check", "1001"], ["tell", "w", "x"], ["pause"], ["resume"], ["point", "m"], ["reset", "1001"]):
        assert cli.main(argv) == 2, argv
        assert "a worker may not run" in capsys.readouterr().out
    assert cli.main(["queue"]) == 0
