"""agent-profiles.mcp.required (#6624): jcodemunch and jdocmunch for every worker, tool sets per role, stack and project, a failed index
build refuses. Fake installs; the config is the one start_tool.prepare writes for the worker."""
from __future__ import annotations

import json
import os
import subprocess
import types

import pytest

from _fake_index import write_rules
from fichero_builder import adapters, codemap, journal, mcp_servers, start_tool, work

@pytest.fixture
def world(tmp_path, monkeypatch):
    wr = write_rules(tmp_path, '[mcp.xcode]\ncommand = "/x/xcode-mcp"\nargs = ["--serve"]\n[mcp.engine]\ncommand = "/x/engine-mcp"\n')
    agents = tmp_path / "agents"
    for rel, tools in (("roles/testing.md", ""), ("roles/manager.md", "tools: builder-verbs"), ("stacks/swift.md", "tools: xcode, apple-docs"),
                       ("stacks/python.md", "tools: engine"), ("projects/p/project.md", "tools: xcode, engine, builder-verbs")):
        (agents / rel).parent.mkdir(parents=True, exist_ok=True)
        (agents / rel).write_text(f"# {rel}\n{tools}\n")
    (agents / "common").mkdir()
    (agents / "common" / "common.md").write_text("common\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setattr(mcp_servers, "AGENTS", agents)
    monkeypatch.setattr("fichero_builder.profiles.AGENTS", agents)
    return types.SimpleNamespace(root=tmp_path, wr=wr, wt=wt, agents=agents)


def _prepare(w, **kw):
    start_tool.prepare(w.root, w.wt, "b", w.root / "scratch", **kw)
    return json.loads((w.root / "scratch" / "mcp.json").read_text())["mcpServers"], (w.root / "scratch" / "prompt.md").read_text()


def test_the_config_names_both_required_servers_with_commands_the_worker_can_run(world):
    servers, prompt = _prepare(world)
    assert list(servers) == ["jcodemunch", "jdocmunch"]
    for s in servers.values():
        assert os.access(s["command"], os.X_OK) and s["command"].startswith(str(world.wr / "bin"))
    assert prompt.rstrip().endswith("MCP servers you have: jcodemunch, jdocmunch.")


def test_an_adapter_whose_mcp_answer_is_unsupported_refuses():
    class NoMcp(adapters.Adapter):
        name = "nomcp"

        def answer(self, question):
            return adapters.Unsupported("no strict mode") if question == "mcp" else "x"

    with pytest.raises(adapters.AdapterRefused, match="no strict mode"):
        adapters.require_lane_capable(NoMcp())


def test_a_required_server_with_no_wrapper_refuses_the_start(world):
    (world.wr / "bin" / "jdocmunch-mcp").unlink()
    with pytest.raises(adapters.AdapterRefused, match="jdocmunch is required"):
        _prepare(world)


def test_a_failed_index_build_exits_with_the_marker_and_the_run_raises_with_a_journal_row(world, monkeypatch):
    (world.wr / "jdocmunch" / "venv" / "bin" / "jdocmunch-mcp.exit").write_text("3")
    a = types.SimpleNamespace(pinned=str(world.root), worktree=str(world.wt), brief="/b", root=str(world.root), name="n", kind="claude", session="s", tick=30.0)
    prefix = codemap.index_prefix(world.root, world.wt)
    r = subprocess.run(["sh", "-c", prefix + "echo started"], capture_output=True, text=True)
    assert r.returncode == codemap.INDEX_FAILED and "index build failed: jdocmunch" in r.stderr and "started" not in r.stdout
    monkeypatch.setattr(work.jail.Jail, "require", lambda self: None)
    monkeypatch.setattr(work, "as_worker", lambda a, script: subprocess.run(["sh", "-c", script], capture_output=True, text=True))
    with pytest.raises(RuntimeError, match="index build failed: jdocmunch"):
        work.do_run(a, "sonnet")
    assert [x for x in journal.read() if x["event"] == "refused"][0]["task"] == "n"


def test_a_good_index_build_lets_the_session_start(world):
    r = subprocess.run(["sh", "-c", codemap.index_prefix(world.root, world.wt) + "echo started"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "started"


def test_a_testing_swift_worker_has_the_xcode_set_and_no_engine_and_python_is_the_reverse(world):
    swift, prompt = _prepare(world, role="testing", stack="swift", project="p")
    assert list(swift) == ["jcodemunch", "jdocmunch", "xcode"] and "apple-docs" not in swift
    assert swift["xcode"] == {"type": "stdio", "command": "/x/xcode-mcp", "args": ["--serve"], "env": {}}
    assert prompt.rstrip().endswith("MCP servers you have: jcodemunch, jdocmunch, xcode.")
    py, _ = _prepare(world, role="testing", stack="python", project="p")
    assert list(py) == ["jcodemunch", "jdocmunch", "engine"]


def test_the_manager_role_gets_the_builders_verbs_only_when_the_project_provides_and_configures_them(world):
    with pytest.raises(adapters.AdapterRefused, match=r"no \[mcp.builder-verbs\] command"):
        _prepare(world, role="manager", project="p")


def test_a_server_the_project_lacks_is_a_journal_row_not_a_silent_drop(world):
    servers, _ = _prepare(world, role="testing", stack="swift", project="p")
    assert "apple-docs" not in servers
    rows = [x for x in journal.read() if x["event"] == "mcp-missing"]
    assert [(x["server"], x["stack"], x["project"]) for x in rows] == [("apple-docs", "swift", "p")]
