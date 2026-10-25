"""pipeline.jailed-agent, tools-in-the-right-places, workers-in-tmux, cost-cap, messages (idle)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline import ROOT, coder

FIXTURES = Path(__file__).parent / "fixtures"


def test_env_allow_list_drops_everything_else(scratch, monkeypatch):
    monkeypatch.setenv("PLANTED_SECRET", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "leak")
    monkeypatch.setenv("PYTHONPATH", "leak")
    monkeypatch.setenv("PIPELINE_STATE", "leak")
    env = coder.allowed_env(scratch["cfg"], "t", "coder")
    for k in ("PLANTED_SECRET", "OPENROUTER_API_KEY", "PYTHONPATH", "PIPELINE_STATE", "PIPELINE_ROOT", "PIPELINE_PYTHON"):
        assert k not in env, k
    assert set(env) <= {"PATH", "HOME", "TERM", "LANG", "PI_CODING_AGENT_DIR", "PIPELINE_WORKER"}
    assert env["PI_CODING_AGENT_DIR"].endswith("pipeline/pi-agent") and env["PIPELINE_WORKER"] == "coder"


def test_worker_env_carries_no_runner_path_only_a_generated_wrapper_on_path(scratch):
    """Review MED 5: the state dir and the runner's python reach the MCP server through a wrapper under the state
    dir, on PATH, never through the worker's environment."""
    env = coder.allowed_env(scratch["cfg"], "t9", "coder")
    bin_dir = Path(env["PATH"].split(":")[0])
    assert bin_dir == scratch["state"] / "bin" / "t9" and (bin_dir / "pipeline-mcp").exists()
    text = (bin_dir / "pipeline-mcp").read_text()
    assert f"PIPELINE_STATE={scratch['state']}" in text and "--role coder" in text and "PIPELINE_WORKER=coder" in text
    assert str(scratch["state"]) not in " ".join(f"{k}={v}" for k, v in env.items() if k != "PATH")


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
    assert all(v.get("lifecycle") == "eager" for v in mcp.values()), "tools are visible from the first turn"


def test_reviewer_prompt_carries_the_ponytail_lens(scratch, tmp_path):
    cmd = coder.pi_command(scratch["cfg"], {"provider": "anthropic", "model": "m"}, tmp_path / "s", role="reviewer")
    lens = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--append-system-prompt" and cmd[i + 1].endswith("ponytail-reviewer.md")]
    assert lens and "named check" in Path(lens[0]).read_text()


def test_worker_window_command_names_session_dir(scratch, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(coder, "sh", lambda args, **kw: calls.append(args) or subprocess.CompletedProcess(args, 1 if args[1] == "has-session" else 0, "", ""))
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    coder.start_window(scratch["cfg"], "coder-demo", tmp_path, ["pi", "--session-dir", str(tmp_path / "s")], {"PATH": "/bin"})
    assert calls[1][:4] == ["tmux", "new-session", "-d", "-s"] and calls[1][4] == "pipeline-test"
    new = calls[-1]
    assert new[:2] == ["tmux", "new-window"] and "coder-demo" in new and str(tmp_path) in new
    assert "env" in new and "-i" in new and "PATH=/bin" in new and f"--session-dir {tmp_path / 's'}" in " ".join(new)


def test_stop_window_interrupts_then_kills(scratch, monkeypatch):
    calls = []
    monkeypatch.setattr(coder, "sh", lambda args, **kw: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    coder.stop_window(scratch["cfg"], "coder-x")
    assert calls[0][1:] == ["send-keys", "-t", "pipeline-test:coder-x", "Escape"]
    assert calls[1][1:] == ["kill-window", "-t", "pipeline-test:coder-x"]


def test_cost_parser_on_redacted_real_sample():
    s = coder.parse_session(FIXTURES / "pi-session-redacted.jsonl")
    assert round(s["cost_usd"], 4) == 0.2028 and s["tokens"] > 100000 and s["turns"] == 8
    assert s["model"] == "qwen/qwen3.8-27b" and sum(s["tool_calls"].values()) == 11
    assert s["idle"] is False, "the trial reaped this session mid-tool: its last line is a tool result, so not idle"


def _write(p, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


USER = {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "do it"}]}}
TOOL = {"type": "message", "message": {"role": "assistant", "stopReason": "toolUse", "usage": {"cost": {"total": 0.01}},
                                       "content": [{"type": "toolCall", "name": "jcodemunch_plan_turn", "arguments": {}}]}}
END = {"type": "message", "message": {"role": "assistant", "stopReason": "stop", "usage": {"cost": {"total": 0.02}},
                                      "content": [{"type": "text", "text": "done"}]}}


def test_idle_is_read_from_the_session_jsonl(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [USER, TOOL])
    assert coder.parse_session(p)["idle"] is False, "a tool call is pending"
    _write(p, [USER, TOOL, END])
    s = coder.parse_session(p)
    assert s["idle"] is True and s["last_text"] == "done" and round(s["cost_usd"], 2) == 0.03 and s["turns"] == 2
    _write(p, [USER, TOOL, END, USER])
    assert coder.parse_session(p)["idle"] is False, "a new prompt is in, no answer yet"
    (tmp_path / "e.jsonl").write_text('{"type": "session", "version": 3}\n')
    assert coder.parse_session(tmp_path / "e.jsonl")["idle"] is False, "no answer yet is not idle (review MED 7)"


def test_idle_waits_for_the_answer_to_the_new_message(tmp_path, monkeypatch):
    """Review MED 7: right after a tell, the previous turn's `stop` still sits in the log. wait_idle must require
    a NEW turn (turns > after_turns), or the checks would run on nothing and burn a retry."""
    sd = tmp_path / "s"
    sd.mkdir()
    _write(sd / "a.jsonl", [USER, END])  # stale idle: one finished turn, before the tell
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    s = coder.wait_idle(sd, cap_usd=1.0, after_turns=1, timeout_s=0.01)
    assert "no idle turn" in s["stopped"], "the stale idle turn did not count"
    _write(sd / "a.jsonl", [USER, END, USER, TOOL, END])  # the worker answered
    s = coder.wait_idle(sd, cap_usd=1.0, after_turns=1, timeout_s=1)
    assert s["idle"] and s["turns"] == 3 and "stopped" not in s


def test_tell_confirms_delivery_from_the_log_and_resends_c_m(scratch, tmp_path, monkeypatch):
    """2026-10-25: three lanes sat idle for hours with the text left unsubmitted in the input box. A tell is
    confirmed by a new user turn in the session log; otherwise C-m goes again (3 times) and the send is reported."""
    sd = tmp_path / "s"
    sd.mkdir()
    _write(sd / "a.jsonl", [USER, END])  # one old prompt; the new one never arrives
    sent = []
    monkeypatch.setattr(coder, "sh", lambda args, **kw: sent.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    delivered = coder.tell(scratch["cfg"], "coder-x", "hello", sd, wait_s=0.01)
    assert delivered is False
    assert sent[0][-2:] == ["-l", "hello"] and [a[-1] for a in sent[1:]] == ["C-m"] * 4, "one C-m, then three more"
    seen = iter([1, 1, 2])  # before the tell: 1 prompt; first poll: still 1; second poll: the turn arrived
    monkeypatch.setattr(coder, "status", lambda d: dict(coder.EMPTY, prompts=next(seen, 2)))
    sent.clear()
    assert coder.tell(scratch["cfg"], "coder-x", "hello", sd, wait_s=5) is True
    assert [a[-1] for a in sent[1:]] == ["C-m"], "confirmed on the first try: no resend"


def test_undelivered_tell_flags_the_worker(scratch, monkeypatch):
    from pipeline import core, journal
    journal.append("worker", window="coder-w", task="w", role="coder", model="m", session_dir=str(scratch["tmp"] / "none"), cwd="")
    monkeypatch.setattr(core.coder, "tell", lambda cfg, w, t, sd=None, wait_s=30: False)
    monkeypatch.setattr(core.coder, "status", lambda d: dict(coder.EMPTY))
    out = core.tell("coder-w", "read the brief", task="w")
    assert out["delivered"] is False
    assert core.state()["workers"]["coder-w"]["undelivered"] == "read the brief"
    monkeypatch.setattr(core.coder, "tell", lambda cfg, w, t, sd=None, wait_s=30: True)
    core.tell("coder-w", "again", task="w")
    assert "undelivered" not in core.state()["workers"]["coder-w"]


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
    _write(p, claude)
    s = coder.parse_session(p)
    assert s["idle"] and s["rate_limited"] and s["tokens"] == 15 and s["cost_usd"] == 0.0


def test_cost_cap_stops_the_task(tmp_path, monkeypatch):
    sd = tmp_path / "s"
    sd.mkdir()
    _write(sd / "a.jsonl", [{"type": "message", "message": {"role": "assistant", "stopReason": "toolUse",
                                                             "usage": {"cost": {"total": 5.0}}, "content": []}}])
    monkeypatch.setattr(coder.time, "sleep", lambda s: None)
    s = coder.wait_idle(sd, cap_usd=1.0, timeout_s=1)
    assert "cost cap" in s["stopped"]


def test_cost_is_recorded_per_issue_and_model(scratch, issues, fake_coder):
    from pipeline import core, journal
    fake_coder()
    core.start([1001, 1002])
    costs = [e for e in journal.read() if e["event"] == "cost"]
    assert [(e["issue"], e["model"], round(e["usd"], 2)) for e in costs] == [(1001, "qwen/x", 0.01), (1002, "qwen/x", 0.01)]
    assert costs[0]["tools"] == {"jcodemunch_plan_turn": 1}
