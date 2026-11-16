"""dev-workflows.node.worker: cost, tokens, idle and a quota failure are read from the session file of either kind."""
from __future__ import annotations

import json
from pathlib import Path

from fichero_builder import session

FIXTURES = Path(__file__).parent / "fixtures"
USER = {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "do it"}]}}
TOOL = {"type": "message", "message": {"role": "assistant", "stopReason": "toolUse", "usage": {"cost": {"total": 0.01}},
                                       "content": [{"type": "toolCall", "name": "jcodemunch_plan_turn", "arguments": {}}]}}
END = {"type": "message", "message": {"role": "assistant", "stopReason": "stop", "usage": {"cost": {"total": 0.02}},
                                      "content": [{"type": "text", "text": "done"}]}}


def _write(p, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_cost_parser_on_a_redacted_real_pi_session():
    s = session.parse_session(FIXTURES / "pi-session-redacted.jsonl")
    assert round(s["cost_usd"], 4) == 0.2028 and s["tokens"] > 100000 and s["turns"] == 8
    assert s["model"] == "qwen/qwen3.8-27b" and sum(s["tool_calls"].values()) == 11
    assert s["idle"] is False, "its last line is a tool result, so not idle"


def test_idle_is_read_from_the_session_file(tmp_path):
    p = tmp_path / "s.jsonl"
    _write(p, [USER, TOOL])
    assert session.parse_session(p)["idle"] is False, "a tool call is pending"
    _write(p, [USER, TOOL, END])
    s = session.parse_session(p)
    assert s["idle"] is True and s["last_text"] == "done" and round(s["cost_usd"], 2) == 0.03 and s["turns"] == 2
    _write(p, [USER, TOOL, END, USER])
    assert session.parse_session(p)["idle"] is False, "a new prompt is in, no answer yet"
    (tmp_path / "e.jsonl").write_text('{"type": "session", "version": 3}\n')
    assert session.parse_session(tmp_path / "e.jsonl")["idle"] is False, "no answer yet is not idle"


def test_the_mcp_fixture_shows_jcodemunch_and_jdocmunch_calls():
    used = session.uses_tools(session.parse_session(FIXTURES / "pi-session-mcp-tools.jsonl"), "jcodemunch", "jdocmunch")
    assert used["jcodemunch"] >= 1 and used["jdocmunch"] >= 1


def test_a_claude_code_session_reads_tokens_idle_and_a_limit_with_no_price(tmp_path):
    claude = [{"type": "user", "message": {"role": "user", "content": "go"}},
              {"type": "assistant", "isApiErrorMessage": True,
               "message": {"role": "assistant", "stop_reason": "end_turn", "model": "claude-x",
                           "usage": {"input_tokens": 10, "output_tokens": 5},
                           "content": [{"type": "text", "text": "You've hit your usage limit"}]}}]
    p = tmp_path / "c.jsonl"
    _write(p, claude)
    s = session.parse_session(p)
    assert s["idle"] and s["rate_limited"] and s["tokens"] == 15 and s["cost_usd"] == 0.0 and s["context"] == 10


def test_a_pi_turn_fills_context_from_input_plus_cache(tmp_path):
    pi = {"type": "message", "message": {"role": "assistant", "stopReason": "stop", "model": "qwen/x",
                                         "usage": {"input": 100, "cacheRead": 900, "cacheWrite": 50, "totalTokens": 1100, "cost": {"total": 0.001}},
                                         "content": [{"type": "text", "text": "ok"}]}}
    p = tmp_path / "p.jsonl"
    _write(p, [USER, pi])
    s = session.parse_session(p)
    assert s["context"] == 1050 and s["cache_read"] == 900 and s["cache_hit"] == round(900 / 1050, 3)


def test_rate_limit_is_read_from_error_shapes_never_from_prose(tmp_path):
    prose = {"type": "message", "message": {"role": "assistant", "stopReason": "stop", "usage": {"cost": {"total": 0.01}},
                                            "content": [{"type": "text", "text": "I added backoff for the 429 rate limit and the insufficient-credit case."}]}}
    p = tmp_path / "p.jsonl"
    _write(p, [USER, prose])
    assert session.parse_session(p)["rate_limited"] is False
    err = {"type": "message", "message": {"role": "assistant", "stopReason": "error", "errorMessage": "402 Insufficient credits",
                                          "usage": {}, "content": []}}
    _write(p, [USER, prose, USER, err])
    assert session.parse_session(p)["rate_limited"] is True
    _write(p, [USER, prose, USER, err, USER, END])
    assert session.parse_session(p)["rate_limited"] is False, "only the latest turn counts"
