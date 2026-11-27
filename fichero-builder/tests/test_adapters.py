"""agent-profiles.adapter.interface and .adapter.claude-code (#6623): six answers, Unsupported said out loud, the Claude Code argv."""
from __future__ import annotations

import json
import subprocess
import types

import pytest

from _fake_index import write_rules
from fichero_builder import adapters, start_tool

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
    write_rules(tmp_path, '[policy]\nrules = [{ re = "x", reason = "NO X" }]\n[models.display]\nsonnet = "Claude Sonnet 5.5"\n')
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    scratch = tmp_path / "scratch"
    argv = start_tool.prepare(tmp_path, wt, "do it", scratch)
    assert argv[:3] == ["sh", "-c", start_tool._READ_PROMPT] and argv[4] == str(scratch / "prompt.md") and argv[5] == "do it"
    text = (scratch / "prompt.md").read_text()
    assert "NO X" in text and "Written-By: Claude Sonnet 5.5 using Claude Code using Fichero Builder" in text and text not in " ".join(argv)  # a file, not the text
    assert argv[argv.index("--settings") + 1] == str(scratch / "settings.json")
    assert argv[argv.index("--setting-sources") + 1] == ""  # no user, project or local settings: only the generated file
    assert "--strict-mcp-config" in argv
    assert list(json.loads((scratch / "mcp.json").read_text())["mcpServers"]) == ["jcodemunch", "jdocmunch"]


def test_a_hostile_brief_reaches_the_shell_as_one_argument(tmp_path, monkeypatch):
    """harness_start shell-quotes every word; the wrapper takes the brief as $2, so command text in it is never run."""
    import shlex
    write_rules(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    mark = tmp_path / "ran"
    argv = start_tool.prepare(tmp_path, wt, f"x; touch {mark}; $(touch {mark})", tmp_path / "s", claude_bin="echo")
    out = subprocess.run(["sh", "-c", " ".join(shlex.quote(x) for x in argv)], capture_output=True, text=True)
    assert out.returncode == 0 and not mark.exists() and "touch" in out.stdout


def test_the_claude_code_adapter_answers_all_six_and_can_take_a_lane():
    cc = adapters.get("claude-code")
    assert not any(isinstance(cc.answer(q), adapters.Unsupported) for q in QUESTIONS)
    adapters.require_lane_capable(cc)


def test_the_workers_tmpdir_and_pytest_basetemp_reach_the_session_command_not_the_tmux_servers_environment(tmp_path, monkeypatch):
    """#6869: a window opened in a tmux server that is already running gets the server's environment, so the two variables go on the command."""
    write_rules(tmp_path, '[policy]\nrules = []\n')
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    monkeypatch.setenv("TMPDIR", "/w/work-a/tmp")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--basetemp=/w/work-a/tmp/pytest")
    argv = start_tool.prepare(tmp_path, wt, "do it", tmp_path / "scratch", claude_bin="claude")
    assert argv[6:10] == ["env", "TMPDIR=/w/work-a/tmp", "PYTEST_ADDOPTS=--basetemp=/w/work-a/tmp/pytest", "claude"]


def _prepare(tmp_path, scratch, **kw):
    argv = start_tool.prepare(tmp_path, tmp_path / "wt", "do it", tmp_path / scratch, **kw)
    return argv, json.loads((tmp_path / scratch / "settings.json").read_text())


def test_an_effort_goes_in_the_settings_file_and_no_row_leaves_the_command_unchanged(tmp_path, monkeypatch):
    write_rules(tmp_path, '[models.display]\nsonnet = "Claude Sonnet 5.5"\n')
    (tmp_path / "wt").mkdir()
    subprocess.run(["git", "-C", str(tmp_path / "wt"), "init", "-q"], check=True)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    plain, settings = _prepare(tmp_path, "s1")
    assert "effortLevel" not in settings
    argv, settings = _prepare(tmp_path, "s2", effort="low")
    assert settings["effortLevel"] == "low"
    assert [x.replace("s2", "s1") for x in argv] == plain and "--effort" not in argv  # the flag and the variable win over the file, so the builder sets neither


def test_harness_start_effort_flag_writes_the_settings_level(tmp_path, monkeypatch):
    """`harness_start.py --print --effort low` (the path `run._start` takes) writes effortLevel; no flag writes none."""
    import sys
    from fichero_builder import jail

    write_rules(tmp_path, '[models.display]\nsonnet = "Claude Sonnet 5.5"\n')
    (tmp_path / "wt").mkdir()
    subprocess.run(["git", "-C", str(tmp_path / "wt"), "init", "-q"], check=True)
    (tmp_path / "b.txt").write_text("brief")
    script = start_tool.Path(start_tool.__file__).parent / "scripts" / "harness_start.py"
    monkeypatch.setattr(start_tool, "refusals", lambda *a: [])
    monkeypatch.setattr(jail, "note_unjailed", lambda *a, **k: None)
    monkeypatch.setattr(start_tool, "find_claude", lambda *a: "claude")
    monkeypatch.setattr(sys, "argv", ["harness_start.py"])
    import runpy
    for effort in ("low", None):
        monkeypatch.setattr(sys, "argv", ["harness_start.py", "--root", str(tmp_path), "--worktree", str(tmp_path / "wt"), "--brief", str(tmp_path / "b.txt"),
                                          "--name", f"n-{effort}", "--print", *(["--effort", effort] if effort else [])])
        monkeypatch.setattr(jail, "load", lambda root: types.SimpleNamespace(workroot=str(tmp_path / "work"), user="x"))
        with pytest.raises(SystemExit) as e:
            runpy.run_path(str(script), run_name="__main__")
        assert e.value.code == 0
        s = json.loads((tmp_path / "work" / f"n-{effort}" / "settings.json").read_text())
        assert s.get("effortLevel") == effort


def test_harness_start_refuses_a_jail_with_no_workroot(tmp_path, monkeypatch, capsys):
    """With no workroot the script wrote settings.json (the policy hook) into a folder named by `--name` under the shared temp
    directory, a name any user can make first. It refuses instead, and writes nothing."""
    import runpy
    import sys
    from fichero_builder import jail

    write_rules(tmp_path, '[models.display]\nsonnet = "Claude Sonnet 5.5"\n')
    (tmp_path / "wt").mkdir()
    (tmp_path / "b.txt").write_text("brief")
    script = start_tool.Path(start_tool.__file__).parent / "scripts" / "harness_start.py"
    wrote = []
    monkeypatch.setattr(start_tool, "refusals", lambda *a: [])
    monkeypatch.setattr(jail, "note_unjailed", lambda *a, **k: None)
    monkeypatch.setattr(start_tool, "find_claude", lambda *a: "claude")
    monkeypatch.setattr(start_tool, "prepare", lambda *a, **k: wrote.append(a) or [])
    monkeypatch.setattr(jail, "load", lambda root: types.SimpleNamespace(workroot="", user="x"))
    monkeypatch.setattr(sys, "argv", ["harness_start.py", "--root", str(tmp_path), "--worktree", str(tmp_path / "wt"), "--brief", str(tmp_path / "b.txt"), "--print"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(script), run_name="__main__")
    assert e.value.code == 1 and not wrote
    assert "workroot" in capsys.readouterr().err
