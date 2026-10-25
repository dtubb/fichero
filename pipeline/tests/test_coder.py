"""pipeline.jailed-agent, key-per-lane, tools-in-the-right-places, workers-in-tmux, cost-cap, cost-recorded, messages (idle)."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline import ROOT, coder

FIXTURES = Path(__file__).parent / "fixtures"


def test_env_allow_list_drops_everything_else(scratch, monkeypatch):
    monkeypatch.setenv("PLANTED_SECRET", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "leak")
    monkeypatch.setenv("PYTHONPATH", "leak")
    env = coder.allowed_env(scratch["cfg"])
    assert "PLANTED_SECRET" not in env and "OPENROUTER_API_KEY" not in env and "PYTHONPATH" not in env
    assert set(env) <= {"PATH", "HOME", "TERM", "LANG", "PI_CODING_AGENT_DIR"}
    assert env["PI_CODING_AGENT_DIR"].endswith("pipeline/pi-agent")


def test_runner_never_reads_the_key_and_prefers_the_lane_key(scratch, tmp_path):
    cfg = scratch["cfg"]
    main, lane = tmp_path / "key", tmp_path / "key-lane"
    main.write_text("MAIN-SECRET")
    cfg["keys"]["openrouter"]["files"] = [str(lane), str(main)]
    var, path = coder.key_source(cfg, {"provider": "openrouter", "model": "m"})
    assert (var, path) == ("OPENROUTER_API_KEY", str(main)), "the main key only while no lane key exists"
    lane.write_text("LANE-SECRET")
    assert coder.key_source(cfg, {"provider": "openrouter", "model": "m"})[1] == str(lane)
    cmd = coder.pi_command(cfg, {"provider": "openrouter", "model": "m"}, tmp_path / "s")
    assert "LANE-SECRET" not in " ".join(cmd) and "MAIN-SECRET" not in " ".join(cmd)
    assert cmd[0].endswith("run-worker.sh") and cmd[1:3] == ["OPENROUTER_API_KEY", str(lane)]


def test_pi_command_loads_only_the_pipeline_agent_dir(scratch, tmp_path):
    cmd = coder.pi_command(scratch["cfg"], {"provider": "anthropic", "model": "claude-sonnet-4-5"}, tmp_path / "s", role="coder")
    s = " ".join(cmd)
    assert "--no-extensions" in cmd and "-e /nowhere/adapter.ts" in s, "only the MCP adapter, by explicit path"
    assert "--no-skills" in cmd and "--no-prompt-templates" in cmd and "--no-themes" in cmd
    assert "--model anthropic/claude-sonnet-4-5" in s and f"--session-dir {tmp_path / 's'}" in s
    appended = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--append-system-prompt"]
    assert any(p.endswith("rules/ponytail-coder.md") for p in appended)
    assert any(p.endswith("skills/_shared/python-principles.md") for p in appended)
    assert all(Path(p).exists() for p in appended)
    mcp = json.loads((ROOT / "pipeline" / "pi-agent" / "mcp.json").read_text())["mcpServers"]
    assert set(mcp) == {"jcodemunch", "jdocmunch", "pipeline"}


def test_reviewer_prompt_carries_the_ponytail_lens(scratch, tmp_path):
    cmd = coder.pi_command(scratch["cfg"], {"provider": "anthropic", "model": "m"}, tmp_path / "s", role="reviewer")
    lens = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--append-system-prompt" and cmd[i + 1].endswith("ponytail-reviewer.md")]
    assert lens and "named check" in Path(lens[0]).read_text()


def test_worker_window_command_names_session_dir(scratch, monkeypatch, tmp_path):
    calls = []
    import subprocess
    monkeypatch.setattr(coder, "sh", lambda args, **kw: calls.append(args) or subprocess.CompletedProcess(args, 1 if args[1] == "has-session" else 0, "", ""))
    coder.start_window(scratch["cfg"], "coder-demo", tmp_path, ["pi", "--session-dir", str(tmp_path / "s")], {"PATH": "/bin"})
    assert calls[1][:4] == ["tmux", "new-session", "-d", "-s"] and calls[1][4] == "pipeline-test"
    new = calls[-1]
    assert new[:2] == ["tmux", "new-window"] and "coder-demo" in new and str(tmp_path) in new
    assert "env" in new and "-i" in new and "PATH=/bin" in new and f"--session-dir {tmp_path / 's'}" in " ".join(new)


def test_cost_parser_on_redacted_real_sample():
    s = coder.parse_session(FIXTURES / "pi-session-redacted.jsonl")
    assert round(s["cost_usd"], 4) == 0.2028 and s["tokens"] > 100000
    assert s["model"] == "qwen/qwen3.8-27b" and sum(s["tool_calls"].values()) == 11
    assert s["idle"] is False, "the trial reaped this session mid-tool: its last line is a tool result, so not idle"


def test_idle_is_read_from_the_session_jsonl(tmp_path):
    p = tmp_path / "s.jsonl"
    lines = [{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "do it"}]}},
             {"type": "message", "message": {"role": "assistant", "stopReason": "toolUse", "usage": {"cost": {"total": 0.01}},
                                             "content": [{"type": "toolCall", "name": "jcodemunch_plan_turn", "arguments": {}}]}}]
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert coder.parse_session(p)["idle"] is False, "a tool call is pending"
    lines.append({"type": "message", "message": {"role": "assistant", "stopReason": "stop", "usage": {"cost": {"total": 0.02}},
                                                 "content": [{"type": "text", "text": "done"}]}})
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    s = coder.parse_session(p)
    assert s["idle"] is True and s["last_text"] == "done" and round(s["cost_usd"], 2) == 0.03
    lines.append({"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "next"}]}})
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert coder.parse_session(p)["idle"] is False, "a new prompt is in, no answer yet"


def test_session_fixture_shows_jcodemunch_and_jdocmunch_calls():
    s = coder.parse_session(FIXTURES / "pi-session-mcp-tools.jsonl")
    used = coder.uses_tools(s, "jcodemunch", "jdocmunch")
    assert used["jcodemunch"] >= 1 and used["jdocmunch"] >= 1


def test_idle_state_from_fixture_jsonl_of_each_kind(tmp_path):
    claude = [{"type": "user", "message": {"role": "user", "content": "go"}},
              {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn", "model": "claude-x",
                                                "usage": {"input_tokens": 10, "output_tokens": 5},
                                                "content": [{"type": "text", "text": "You've hit your usage limit"}]}}]
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in claude) + "\n")
    s = coder.parse_session(p)
    assert s["idle"] and s["rate_limited"] and s["tokens"] == 15 and s["cost_usd"] == 0.0


def test_cost_cap_stops_the_task(tmp_path, monkeypatch):
    sd = tmp_path / "s"
    sd.mkdir()
    (sd / "a.jsonl").write_text(json.dumps({"type": "message", "message": {"role": "assistant", "stopReason": "toolUse",
                                                                             "usage": {"cost": {"total": 5.0}}, "content": []}}) + "\n")
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    s = coder.wait_idle(sd, cap_usd=1.0, timeout_s=1)
    assert "cost cap" in s["stopped"]


def test_cost_is_recorded_per_issue_and_model(scratch, issues, fake_coder):
    from pipeline import core, journal
    fake_coder()
    core.start([1001, 1002])
    costs = [e for e in journal.read() if e["event"] == "cost"]
    assert [(e["issue"], e["model"]) for e in costs] == [(1001, "qwen/x"), (1002, "qwen/x")]
    assert costs[0]["tools"] == {"jcodemunch_plan_turn": 1}
