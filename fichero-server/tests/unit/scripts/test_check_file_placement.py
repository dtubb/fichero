"""spec: code-organization — `code-org.enforce.per-batch-placement`: `check_file_placement --since <base>` judges each file
a batch adds or renames, and proves it can see a misplaced one."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[4]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "scripts" / "check_file_placement.py"), *args], cwd=REPO,
                          capture_output=True, text=True, timeout=120)


def test_the_guard_proves_it_sees_one_wrong_file_per_rule():
    done = _run("--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_an_unknown_base_is_blind_not_clean():
    done = _run("--since", "no-such-ref-for-the-test")
    assert done.returncode == 2, done.stdout + done.stderr


def _has_base() -> bool:
    return (REPO / ".git").exists() and subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "origin/integration"], cwd=REPO, capture_output=True).returncode == 0


@pytest.mark.skipif(not _has_base(), reason="no repo or no origin/integration to diff against (a gate copy, a bare clone): the guard goes blind there, by design")
def test_this_branch_places_every_file_it_adds():
    done = _run("--since", "origin/integration")
    assert done.returncode == 0, done.stdout + done.stderr
