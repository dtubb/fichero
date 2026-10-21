"""scripts/check_agent_commits_authored_as_claude.py (#5997): a temp git repo with one good and one bad commit."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_agent_commits_authored_as_claude.py"
CLAUDE = ("Claude", "noreply@anthropic.com")
DANIEL = ("Daniel Tubb", "dtubb@example.com")


def _git(repo: Path, *args: str, who=CLAUDE) -> str:
    env = {"GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1], "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1],
           "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo)}
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout


def _commit(repo: Path, name: str, message: str, who) -> str:
    (repo / name).write_text(name)
    _git(repo, "add", name, who=who)
    _git(repo, "commit", "-q", "-m", message, who=who)
    return _git(repo, "rev-parse", "HEAD", who=who).strip()


def _run(repo: Path, rng: str | None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT)] + ([rng] if rng else [])
    return subprocess.run(args, cwd=repo, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo)})


def _repo(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q", "-b", "main")
    base = _commit(tmp_path, "base", "base", CLAUDE)
    return tmp_path, base


def test_an_agent_commit_authored_as_claude_passes(tmp_path):
    repo, base = _repo(tmp_path)
    _commit(repo, "a", "work\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", CLAUDE)
    done = _run(repo, f"{base}..HEAD")
    assert done.returncode == 0 and "OK" in done.stdout, done.stdout + done.stderr


def test_an_agent_trailer_on_a_commit_authored_as_the_maintainer_fails_and_names_it(tmp_path):
    repo, base = _repo(tmp_path)
    good = _commit(repo, "a", "good\n\nDirected-By: the maintainer", CLAUDE)
    bad = _commit(repo, "b", "bad\n\nDirected-By: the maintainer", DANIEL)
    done = _run(repo, f"{base}..HEAD")
    assert done.returncode == 1
    assert bad[:12] in done.stdout and "Daniel Tubb" in done.stdout and good[:12] not in done.stdout


def test_a_co_authored_by_claude_trailer_counts_too(tmp_path):
    repo, base = _repo(tmp_path)
    bad = _commit(repo, "a", "bad\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>", DANIEL)
    assert bad[:12] in _run(repo, f"{base}..HEAD").stdout


def test_a_maintainer_commit_with_no_agent_trailer_and_a_human_co_author_pass(tmp_path):
    repo, base = _repo(tmp_path)
    _commit(repo, "a", "mine", DANIEL)
    _commit(repo, "b", "paired\n\nCo-Authored-By: Alex Example <alex@example.com>", DANIEL)
    assert _run(repo, f"{base}..HEAD").returncode == 0


def test_history_outside_the_given_range_is_not_judged(tmp_path):
    repo, _ = _repo(tmp_path)
    _commit(repo, "old", "old\n\nDirected-By: the maintainer", DANIEL)
    tip = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "new", "new\n\nDirected-By: the maintainer", CLAUDE)
    assert _run(repo, f"{tip}..HEAD").returncode == 0


def test_a_range_git_cannot_read_fails_rather_than_passing(tmp_path):
    repo, _ = _repo(tmp_path)
    assert _run(repo, "nosuchref..HEAD").returncode == 2
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    assert _run(empty, "HEAD~1..HEAD").returncode == 2  # a range that is given and cannot be read; no range is a skip (review 807)


def test_no_argument_and_no_origin_integration_skips_with_exit_0_but_a_given_range_still_fails(tmp_path):
    """The gate runs every check with no argument; the M4 clones have no origin/integration (review 807)."""
    repo, _ = _repo(tmp_path)
    _commit(repo, "x", "x\n\nDirected-By: the maintainer", DANIEL)
    skipped = _run(repo, None)
    assert skipped.returncode == 0 and "SKIP" in skipped.stdout and "origin/integration" in skipped.stdout
    assert _run(repo, "nosuchref..HEAD").returncode == 2
    assert _run(repo, "HEAD~1..HEAD").returncode == 1  # a range that is given is judged
