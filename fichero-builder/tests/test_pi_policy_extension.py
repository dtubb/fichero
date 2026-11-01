"""dev-workflows.node.worker: the Pi policy extension blocks on a refusal, on an unknown tool, and on its own crash."""
from __future__ import annotations

import json

from fichero_builder import pi_rpc
from tests.test_pi_live_helpers import live

CFG = {"rules": [{"re": r"\bgit\s+push\b", "reason": "workers never push"}]}


def test_the_mapping_names_the_policys_tools_and_refuses_unknown_ones(tmp_path):
    wt = tmp_path / "wt"
    assert pi_rpc.decide({"toolName": "bash", "input": {"command": "git push"}}, CFG, worktree=wt, scratch=tmp_path) == "workers never push"
    assert pi_rpc.decide({"toolName": "bash", "input": {"command": "ls"}}, CFG, worktree=wt, scratch=tmp_path) is None
    assert pi_rpc.decide({"toolName": "write", "input": {"path": "a.py"}}, CFG, worktree=wt, scratch=tmp_path) is None, "relative = in the worktree"
    assert "outside" in pi_rpc.decide({"toolName": "edit", "input": {"path": "/etc/hosts"}}, CFG, worktree=wt, scratch=tmp_path)
    assert pi_rpc.decide({"toolName": "read", "input": {"path": "/etc/hosts"}}, CFG, worktree=wt, scratch=tmp_path) is None, "reads anywhere"
    assert "unknown tools are refused" in pi_rpc.decide({"toolName": "browser", "input": {}}, CFG, worktree=wt, scratch=tmp_path)
    for crafted in ("~/.ssh/authorized_keys", "@/etc/x", "@../../x"):  # review 1 M3: Pi expands ~ and strips a leading @ itself
        assert "outside" in (pi_rpc.decide({"toolName": "write", "input": {"path": crafted}}, CFG, worktree=wt, scratch=tmp_path) or ""), crafted
    assert pi_rpc.decide({"toolName": "write", "input": {"path": "@src/a.py"}}, CFG, worktree=wt, scratch=tmp_path) is None


def test_the_policy_command_ignores_a_module_planted_in_the_worktree(tmp_path):
    """Review 1 M2: `python -m` puts the cwd first on sys.path; a worker could plant fichero_builder/pi_rpc.py in its worktree."""
    import os
    import subprocess

    planted = tmp_path / "fichero_builder"
    planted.mkdir()
    (planted / "__init__.py").write_text("")
    (planted / "pi_rpc.py").write_text("import sys\nprint('ALLOW')\nsys.exit(0)\n")
    root = pi_rpc.EXTENSION.parents[2]
    argv = pi_rpc.policy_argv(root, tmp_path, tmp_path)
    env = {**os.environ, "PYTHONPATH": str(pi_rpc.EXTENSION.parents[1])}
    r = subprocess.run(argv, cwd=tmp_path, input='{"toolName": "write", "input": {"path": "/etc/x"}}', capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "outside" in r.stderr, (r.returncode, r.stdout, r.stderr[-200:])


def _tool_end(events):
    return [e for e in events if e.get("type") == "tool_execution_end"]


def _tool_results(calls) -> str:
    """What the model was told the tools returned (the fake's last request, tool-role messages only)."""
    return json.dumps([m for m in calls[-1]["messages"] if m.get("role") == "tool"]) if calls else ""


def test_an_allowed_command_runs_and_its_output_reaches_the_model(tmp_path):
    pi, srv, calls = live(tmp_path, "echo MARKER-OK")
    try:
        assert pi.prompt("go")["success"]
        events = pi.wait(timeout_s=90)
        ends = _tool_end(events)
        assert ends and not ends[0].get("isError"), ends
        assert "MARKER-OK" in _tool_results(calls), "the tool result went back to the model"
    finally:
        pi.stop(), srv.shutdown()


def test_a_refused_command_is_blocked_with_the_reason(tmp_path):
    pi, srv, calls = live(tmp_path, "git push origin main")
    try:
        pi.prompt("go")
        ends = _tool_end(pi.wait(timeout_s=90))
        assert ends and ends[0].get("isError"), ends
        assert "never push" in json.dumps(ends[0]) and len(calls) == 2, "blocked, then the model was told"
    finally:
        pi.stop(), srv.shutdown()


def test_a_crashing_extension_blocks_the_tool(tmp_path):
    pi, srv, calls = live(tmp_path, "echo MARKER-CRASH", crash=True)
    try:
        pi.prompt("go")
        events = pi.wait(timeout_s=90)
        ends = _tool_end(events)
        assert ends and ends[0].get("isError"), ends
        assert "crashed on purpose" in _tool_results(calls) and "MARKER-CRASH\\n" not in _tool_results(calls), "the command never ran"
    finally:
        pi.stop(), srv.shutdown()

