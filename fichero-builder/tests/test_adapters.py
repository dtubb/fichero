"""agent-profiles.adapter.interface and .adapter.claude-code (#6623): six answers, Unsupported said out loud, the Claude Code argv."""
from __future__ import annotations

import json
import subprocess

import pytest

from fichero_builder import adapters, codemap, start_tool

QUESTIONS = ("system_prompt", "mcp", "model", "permission", "policy", "session_read")


class Fake(adapters.Adapter):
    name = "fake"

    def __init__(self, **no):
        self.no = no

    def answer(self, question: str):
        return adapters.Unsupported(self.no[question]) if question in self.no else f"{question}-value"


def test_six_answers_and_unsupported_is_said():
    assert adapters.questions() == QUESTIONS
    ok = Fake()
    assert [ok.answer(q) for q in QUESTIONS] == [f"{q}-value" for q in QUESTIONS]
    adapters.require_lane_capable(ok)
    with pytest.raises(adapters.AdapterRefused, match="no cost without a session file"):
        adapters.require_lane_capable(Fake(session_read="no cost without a session file"))
    with pytest.raises(adapters.AdapterRefused, match="no index"):
        adapters.require_lane_capable(Fake(mcp="no index"))
    assert adapters.policy_line(Fake(policy="no hook point")) == "policy: none (OS jail only)"
    assert adapters.policy_line(ok) == "policy: policy-value"
    with pytest.raises(adapters.AdapterRefused, match="unknown harness 'nope'"):
        adapters.get("nope")
    assert adapters.get("claude-code").name == "claude-code"


def test_claude_code_argv(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text('[policy]\nrules = [{ re = "x", reason = "NO X" }]\n')
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    scratch = tmp_path / "scratch"
    argv = start_tool.prepare(tmp_path, wt, "do it", scratch)
    assert argv[:3] == ["sh", "-c", start_tool._READ_PROMPT] and argv[4] == str(scratch / "prompt.md") and argv[5] == "do it"
    text = (scratch / "prompt.md").read_text()
    assert "NO X" in text and "Written-By: sonnet using Claude Code using Fichero Builder" in text and text not in " ".join(argv)  # a file, not the text
    assert argv[argv.index("--settings") + 1] == str(scratch / "settings.json")
    assert argv[argv.index("--setting-sources") + 1] == ""  # no user, project or local settings: only the generated file
    assert "--strict-mcp-config" in argv
    assert json.loads((scratch / "mcp.json").read_text()) == codemap.mcp_config(tmp_path)


def test_a_hostile_brief_reaches_the_shell_as_one_argument(tmp_path, monkeypatch):
    """harness_start shell-quotes every word; the wrapper takes the brief as $2, so command text in it is never run."""
    import shlex
    (tmp_path / "harness.toml").write_text("")
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    mark = tmp_path / "ran"
    argv = start_tool.prepare(tmp_path, wt, f"x; touch {mark}; $(touch {mark})", tmp_path / "s", claude_bin="echo")
    out = subprocess.run(["sh", "-c", " ".join(shlex.quote(x) for x in argv)], capture_output=True, text=True)
    assert out.returncode == 0 and not mark.exists() and "touch" in out.stdout
