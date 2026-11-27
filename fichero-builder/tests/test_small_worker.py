"""agent-profiles.worker.small (#6625): one step per brief, a brief of at most 120 lines that names a test, a diff bound per role."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_builder import brief_tool, profiles, queue, small_worker, start_tool

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "harness_policy_hook.py"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


def _issue(n, step="1.1", body="", tests=True):
    body = f"Step: {step}\n" + (f"Tests: fichero-builder/tests/test_x{n}.py\n" if tests else "") + body
    return {"number": n, "title": f"t{n}", "body": body, "authorAssociation": "OWNER", "comments": []}


def _cluster(issues, tmp_path, **kw):
    return brief_tool.cluster(issues, repo=str(tmp_path), branch="b", base="x", **kw)


def test_a_two_step_cluster_is_refused(tmp_path):
    assert _cluster([_issue(1), _issue(2)], tmp_path)  # one step in two issues is one brief
    with pytest.raises(brief_tool.Refused, match="2 steps"):
        _cluster([_issue(1, "1.1"), _issue(2, "1.2")], tmp_path)


def test_a_brief_of_121_lines_is_refused_and_120_is_not(tmp_path):
    base = len(_cluster([_issue(1, body="x")], tmp_path).splitlines())

    def fill(total):  # a body that makes the brief `total` lines
        return "x\n" + "\n".join("y" for _ in range(total - base))

    ok = _cluster([_issue(1, body=fill(small_worker.CAP))], tmp_path)
    assert len(ok.splitlines()) == small_worker.CAP
    with pytest.raises(brief_tool.Refused, match="121 lines"):
        _cluster([_issue(1, body=fill(small_worker.CAP + 1))], tmp_path)


def test_a_code_project_brief_with_no_named_test_is_refused(tmp_path):
    assert _cluster([_issue(1, tests=False)], tmp_path)  # not a code project: no test needed
    with pytest.raises(brief_tool.Refused, match="no test file"):
        _cluster([_issue(1, tests=False)], tmp_path, need_tests=True)
    assert _cluster([_issue(1)], tmp_path, need_tests=True)


def test_the_lane_route_says_why_it_refused(tmp_path, monkeypatch):
    """`builder lane --issues`: a refusal is a one-line answer, never a traceback."""
    from fichero_builder import journal, land_tool
    (tmp_path / "harness.toml").write_text(f'[check]\npython = "p"\n[land]\nbranch = "integration"\n[jail]\nworkroot = "{tmp_path / "wr"}"\n')
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setattr(brief_tool, "fetch_issue", lambda n, gh="gh": _issue(n, "1.1" if n == 1 else "1.2"))
    monkeypatch.setattr(land_tool, "resolve_branch", lambda repo, b: "abc")
    rc, out = queue.lane_from_issues(tmp_path, "l", [1, 2])
    assert rc == 1 and "refused" in out and "2 steps" in out


def _agents(tmp_path, role_text):
    agents = tmp_path / "agents"
    for rel, body in (("common/common.md", "COMMON"), ("roles/feature.md", role_text)):
        (agents / rel).parent.mkdir(parents=True, exist_ok=True)
        (agents / rel).write_text(body)
    (tmp_path / "harness.toml").write_text("[policy]\nrules = []\n")
    return agents


def test_a_role_file_with_no_diff_bound_refuses_to_start(tmp_path, monkeypatch):
    run = dict(worktree="/w", scratch="/s", harness="Claude Code", model="m")
    with pytest.raises(profiles.ProfileError, match="roles/feature.md has no `diff_bound"):
        profiles.assemble(tmp_path, role="feature", agents_dir=_agents(tmp_path, "# feature\n"), **run)
    assert "COMMON" in profiles.assemble(tmp_path, role="feature", agents_dir=_agents(tmp_path, "diff_bound: 400\n"), **run)
    wt = tmp_path / "wt"
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "x"], check=True, env=GIT_ENV)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gc"))
    monkeypatch.setattr(profiles, "AGENTS", _agents(tmp_path, "# feature\n"))
    with pytest.raises(profiles.ProfileError, match="diff_bound"):  # the start path refuses before it writes a hook
        start_tool.prepare(tmp_path, wt, "b", tmp_path / "scratch", role="feature")
    assert not (tmp_path / "scratch" / "settings.json").exists()


def _hook(tmp_path, wt, scratch, cmd="git commit -m x", bound=5, base="HEAD"):
    return subprocess.run([sys.executable, str(HOOK), "--root", str(tmp_path), "--worktree", str(wt), "--scratch", str(scratch),
                           "--diff-bound", str(bound), "--diff-base", base],
                          input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}), capture_output=True, text=True)


def test_a_diff_past_the_bound_is_told_once_then_parked(tmp_path):
    """Through the real hook script: generated files are not counted; the first commit past the bound is refused with a tell,
    the second writes the park marker; a diff under the bound is let through."""
    (tmp_path / "harness.toml").write_text('[policy]\nrules = []\n[check]\ngenerated = ["gen/*"]\n')
    wt, scratch = tmp_path / "wt", tmp_path / "scratch"
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "base"], check=True, env=GIT_ENV)
    (wt / "gen").mkdir()
    (wt / "gen" / "big.py").write_text("x\n" * 500)
    (wt / "a.py").write_text("x\n" * 5)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    assert _hook(tmp_path, wt, scratch).returncode == 0, "500 generated lines and 5 others: at the bound, not over it"
    assert not (scratch / "bound-told").exists()
    (wt / "a.py").write_text("x\n" * 6)
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
    first = _hook(tmp_path, wt, scratch)
    assert first.returncode == 2 and "6 changed lines" in first.stderr and "bound for your role is 5" in first.stderr
    assert (scratch / "bound-told").exists() and not (scratch / "bound-park").exists()
    assert _hook(tmp_path, wt, scratch, cmd="git status").returncode == 0, "only a commit is counted"
    second = _hook(tmp_path, wt, scratch)
    assert second.returncode == 2 and "parked" in second.stderr and (scratch / "bound-park").is_file()
    assert _hook(tmp_path, wt, tmp_path / "other", bound=50).returncode == 0
