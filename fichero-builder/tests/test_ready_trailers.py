"""lane_ready_check.sh judges trailers and empty commits itself (deterministic-conductor.md pipeline.ready-trailers), so the LLM review does not."""
import subprocess
from pathlib import Path

SCRIPT = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "lane_ready_check.sh").exists()) / "scripts" / "lane_ready_check.sh"
GOOD = "Written-By: Claude Sonnet 5.5 using Claude Code using Fichero Builder"


def _git(repo, *a, **kw):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True, **kw)


def _ready(tmp_path, message, empty=False):
    repo = tmp_path / "r"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "noreply@anthropic.com")
    _git(repo, "config", "user.name", "Claude")
    (repo / "harness.toml").write_text('[check]\nmax_commits = 100\n[models.display]\nsonnet = "Claude Sonnet 5.5"\nopus = "Claude Opus 5.5"\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "update-ref", "refs/remotes/origin/integration", "HEAD")
    if not empty:
        (repo / "x.txt").write_text("x\n")
        _git(repo, "add", "-A")
    (repo / "msg").write_text(message)
    _git(repo, "commit", "-q", "--allow-empty", "-F", "msg")
    r = subprocess.run(["/bin/bash", str(SCRIPT), "--no-guards", "HEAD"], cwd=repo, capture_output=True, text=True)
    return r.returncode, r.stdout


def test_one_written_by_with_a_display_model_and_an_optional_spec_change_is_ready(tmp_path):
    rc, out = _ready(tmp_path / "a", f"fix: x (#6589)\n\n{GOOD}\n")
    assert rc == 0, out
    rc, out = _ready(tmp_path / "b", f"fix: x (#6589)\n\nSpec-change: manager 2026-11-24 ruling\n{GOOD}\n")
    assert rc == 0, out


def test_a_model_not_in_models_display_is_refused_naming_it(tmp_path):
    rc, out = _ready(tmp_path, "fix: x (#6589)\n\nWritten-By: claude-sonnet-5-5 using Claude Code using Fichero Builder\n")
    assert rc == 1 and "claude-sonnet-5-5" in out and "[models.display]" in out, out


def test_two_written_by_lines_or_two_spec_change_lines_are_refused(tmp_path):
    rc, out = _ready(tmp_path / "a", f"fix: x (#6589)\n\n{GOOD}\n{GOOD}\n")
    assert rc == 1 and "more than one Written-By" in out, out
    rc, out = _ready(tmp_path / "b", f"fix: x (#6589)\n\nSpec-change: manager a\nSpec-change: manager b\n{GOOD}\n")
    assert rc == 1 and "more than one Spec-change" in out, out


def test_a_missing_written_by_is_refused(tmp_path):
    rc, out = _ready(tmp_path, "fix: x (#6589)\n")
    assert rc == 1 and "Written-By" in out, out


def test_an_empty_commit_is_refused(tmp_path):
    rc, out = _ready(tmp_path, f"fix: x (#6589)\n\n{GOOD}\n", empty=True)
    assert rc == 1 and "empty commit" in out, out
