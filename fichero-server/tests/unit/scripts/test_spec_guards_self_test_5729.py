"""#5729 (rule 0): a spec guard must know when it is blind. `check_spec_behaviors_are_tagged` has a `--self-test` that plants an
untagged behavior in a scratch spec and fails unless the guard finds exactly that one.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "scripts" / script), *args], cwd=REPO, capture_output=True,
                          text=True, timeout=120)


def test_the_tag_guard_proves_it_can_see_an_untagged_behavior():
    done = _run("check_spec_behaviors_are_tagged.py", "--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_tag_guard_self_test_fails_when_the_guard_is_blind(monkeypatch):
    """The self-test is only worth having if it fails for a guard that sees nothing."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import check_spec_behaviors_are_tagged as guard

        monkeypatch.setattr(guard, "untagged_behaviors", lambda specs_dir: [])
        assert guard._self_test() == 1
    finally:
        sys.path.remove(str(REPO / "scripts"))


def test_the_spec_test_linkage_guard_proves_it_can_fail_and_pass():
    """#5729: `check_specs_have_tests --self-test` runs the guard over scratch trees: an approved spec no test cites and a
    test citing a missing spec both fail, a cited approved spec passes."""
    done = _run("check_specs_have_tests.py", "--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_milestone_guard_proves_it_can_fail_and_pass():
    """#5729: `check_spec_milestones --self-test`: an APPROVED spec with no Milestone header fails, one that declares it passes."""
    done = _run("check_spec_milestones.py", "--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_manual_ref_guard_proves_it_can_fail_and_pass():
    """#5729: `check_spec_manual_refs --self-test`: an APPROVED spec with no Manual line fails, `Manual: TBD` fails, a real path passes."""
    done = _run("check_spec_manual_refs.py", "--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_capability_scrape_guard_proves_it_can_fail_and_pass():
    """#5729: `check_capability_scrapes --self-test`: a new AppSource scrape and a drifted baseline entry are both reported, a clean tree is not."""
    done = _run("check_capability_scrapes.py", "--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr
