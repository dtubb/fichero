"""Prove `check_closed_issues_landed` can FAIL — a guardrail with no such proof
is decoration (#4425).

The check exists to catch an issue closed against a commit that is real in the
lane's local tree but has never been pushed. Its two halves are deliberately
asymmetric — corpus is `git log --all`, test is against the remote — and the
easy way to break it is to "optimise" the corpus onto the remote, which makes
every commit reachable by construction and the check silently unfailable.

These tests pin the decision itself, so that regression fails here rather than
being discovered by another lost fix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_closed_issues_landed.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("cci_landed", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    assert _SCRIPT.exists(), f"{_SCRIPT} is missing — the check was deleted, not moved"
    return _load()


def test_the_guardrail_fires_on_an_unpushed_commit(mod):
    """THE test that matters: every citing commit local-only => flagged.

    This is the real 2026-07-30 case — #4392/#4404/#4423 closed minutes after a
    local merge, before the push.
    """
    assert mod.classify(["deadbeef1"], reachable=set()) == "unlanded"


def test_one_reachable_commit_is_enough(mod):
    """#2508's shape: some citing commits unreachable, others pushed.

    The phased work landed; only a later completion did not. This check must
    NOT flag that — it is a different defect, findable only from the branch
    side, and flagging it here would produce noise that gets the check turned
    off.
    """
    assert mod.classify(["local1", "pushed1"], reachable={"pushed1"}) == "ok"


def test_no_citing_commit_is_skipped_not_failed(mod):
    """Duplicates, audits, already-implemented triage closures, and work that
    lands as data (e.g. a default_workflows/*.json preset, #3904) legitimately
    cite no commit. Failing those is noise, and a noisy check gets disabled.
    """
    assert mod.classify([], reachable=set()) == "skip"


def test_all_commits_reachable_passes(mod):
    assert mod.classify(["a", "b"], reachable={"a", "b"}) == "ok"


def test_docstring_keeps_the_corpus_warning(mod):
    """The corpus/test asymmetry is load-bearing and easy to 'optimise' away.

    If someone narrows the corpus to the remote, `is_ancestor` is always true,
    nothing is ever flagged, and this becomes a guardrail that cannot fail —
    the #4382 mode, inside the tool built to prevent it. Keep the warning where
    an editor cannot miss it.
    """
    doc = mod.__doc__ or ""
    assert "git log --all" in doc
    assert "cannot fail" in doc.lower() or "CANNOT FAIL" in doc


def test_a_failed_gh_is_blind_not_zero_closed_issues(monkeypatch):
    """An unreachable GitHub must NOT read as "nothing was closed".

    `sh` runs with check=False, so a failed `gh` returned "" and
    `json.loads(raw or "[]")` turned that into an empty dict — which this script
    reported as "OK: no issues closed in the last 24h" and exited 0. The check
    was at its most confident exactly when it could see nothing.
    """
    import subprocess

    mod = _load()

    def fails(*a, **k):
        return subprocess.CompletedProcess(a, 1, stdout="", stderr="gh: not authenticated")

    monkeypatch.setattr(mod.subprocess, "run", fails)
    with pytest.raises(mod.Blind):
        mod.closed_since(24)


def test_a_missing_gh_binary_is_also_blind(monkeypatch):
    """`gh` absent raises OSError rather than returning non-zero — a separate
    path from an unreachable GitHub, and just as blind."""
    mod = _load()

    def missing(*a, **k):
        raise FileNotFoundError(2, "No such file or directory: 'gh'")

    monkeypatch.setattr(mod.subprocess, "run", missing)
    with pytest.raises(mod.Blind):
        mod.closed_since(24)


# ── The whole script on a fake git repo: a stand-in `gh`, a local bare "origin", no network ──────────────────


def _bin(tmp_path: Path, gh_answer: str | None) -> Path:
    """A PATH holding git and, unless None, a `gh` that prints this closed-issue listing."""
    import os
    import shutil

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    os.symlink(shutil.which("git"), bin_dir / "git")
    if gh_answer is not None:
        (tmp_path / "gh.json").write_text(gh_answer)
        gh = bin_dir / "gh"
        gh.write_text(f"#!/bin/sh\n/bin/cat '{tmp_path / 'gh.json'}'\n")
        gh.chmod(0o755)
    return bin_dir


def _git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(repo),
                        "PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _repo(tmp_path: Path, *, with_origin: bool) -> Path:
    """A repo whose pushed commit cites #100 and whose unpushed commit cites #200."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "integration")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "fix: pushed (#100)")
    if with_origin:
        _git(tmp_path, "init", "-q", "--bare", "origin.git")
        _git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
        _git(repo, "push", "-q", "origin", "integration")
        _git(repo, "fetch", "-q", "origin")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "fix: not pushed (#200)")
    return repo


def _closed(*numbers: int) -> str:
    import json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return json.dumps([{"number": n, "closedAt": now, "title": f"issue {n}"} for n in numbers])


def _run(repo: Path, bin_dir: Path, *args: str):
    import subprocess
    import sys

    return subprocess.run([sys.executable, str(_SCRIPT), *args], cwd=repo, capture_output=True, text=True,
                          env={"PATH": str(bin_dir), "HOME": str(repo), "GIT_CONFIG_GLOBAL": "/dev/null",
                               "GIT_CONFIG_NOSYSTEM": "1"}, timeout=60)


def test_it_still_fails_on_a_closed_issue_whose_only_commit_is_unpushed(tmp_path):
    repo = _repo(tmp_path, with_origin=True)
    bad = _run(repo, _bin(tmp_path, _closed(100, 200)))
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "#200" in bad.stdout and "#100" not in bad.stdout.split("FAIL", 1)[1]


def test_it_passes_when_every_closed_issue_is_pushed(tmp_path):
    repo = _repo(tmp_path, with_origin=True)
    ok = _run(repo, _bin(tmp_path, _closed(100)))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "OK: every closed issue" in ok.stdout


def test_a_checkout_with_no_origin_says_it_cannot_check_and_does_not_fail(tmp_path):
    """The M4's check tree: a fetch with no `origin` remote. A skip, named as one, never an OK."""
    repo = _repo(tmp_path, with_origin=False)
    skipped = _run(repo, _bin(tmp_path, _closed(200)))
    assert skipped.returncode == 0, skipped.stdout + skipped.stderr
    assert "SKIP: cannot check here" in skipped.stdout and "no `origin` remote" in skipped.stdout
    assert "OK" not in skipped.stdout
    assert _run(repo, tmp_path / "bin", "--strict").returncode == 2


def test_no_gh_says_it_cannot_check_and_does_not_fail(tmp_path):
    repo = _repo(tmp_path, with_origin=True)
    skipped = _run(repo, _bin(tmp_path, None))
    assert skipped.returncode == 0, skipped.stdout + skipped.stderr
    assert "SKIP: cannot check here: no working gh" in skipped.stdout
    assert "OK" not in skipped.stdout
    assert _run(repo, tmp_path / "bin", "--strict").returncode == 2


def test_outside_any_git_repository_it_still_fails(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = _run(empty, _bin(tmp_path, _closed(200)))
    assert out.returncode == 1 and "not a git repository" in out.stderr
