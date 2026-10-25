"""pipeline.test-red-on-base, pinned-checks, gate-runs-in-the-worktree, quick-checks-per-item."""
from __future__ import annotations

import subprocess

from pipeline import checks
from pipeline.tests.conftest import git


def lane(scratch, name, files, author="noreply@anthropic.com", msg="work (Fixes #1001)"):
    wt = scratch["tmp"] / name
    subprocess.run(["git", "worktree", "add", "-q", "-b", name, wt, "origin/integration"], cwd=scratch["repo"], check=True)
    for path, text in files.items():
        (wt / path).parent.mkdir(parents=True, exist_ok=True)
        (wt / path).write_text(text)
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", f"user.email={author}", "commit", "-qm", msg)
    return wt


def test_red_on_base_fails_a_test_that_passes_on_base(scratch):
    wt = lane(scratch, "trivial", {"tests/test_t.py": "def test_t():\n    assert True\n"})
    results = checks.run_all(wt, scratch["cfg"])
    red = {r["name"]: r for r in results}
    assert red["ready"]["ok"]
    assert not red["red-on-base"]["ok"] and "NOT RED ON BASE" in red["red-on-base"]["text"]
    assert list(red) == ["ready", "red-on-base"], "stops at the first red rung"


def test_red_on_base_passes_a_real_fix(scratch):
    wt = lane(scratch, "real", {"src/mod.py": "def base():\n    return 0\n\n\ndef f1():\n    return 1\n",
                                "tests/test_1.py": "from src.mod import f1\n\ndef test_f1():\n    assert f1() == 1\n"})
    results = checks.run_all(wt, scratch["cfg"])
    assert [(r["name"], r["ok"]) for r in results] == [("ready", True), ("red-on-base", True), ("fast-guards", True)]
    assert all(r["seconds"] >= 0 for r in results)
    assert not git(wt, "worktree", "list").count("pipeline-red-"), "the scratch base worktree is removed"


def test_red_on_the_branch_is_red(scratch):
    wt = lane(scratch, "broken", {"src/mod.py": "def base():\n    return 0\n\n\ndef f1():\n    return 2\n",
                                  "tests/test_1.py": "from src.mod import f1\n\ndef test_f1():\n    assert f1() == 1\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert not r["red-on-base"]["ok"] and "RED ON THE BRANCH" in r["red-on-base"]["text"]


def test_diff_touching_check_paths_needs_maintainer(scratch):
    wt = lane(scratch, "sneaky", {"scripts/lane_ready_check.sh": "#!/bin/bash\nexit 0\n"})
    results = checks.run_all(wt, scratch["cfg"])
    assert len(results) == 1 and results[0]["name"] == "pinned-checks" and not results[0]["ok"]
    assert "needs-maintainer" in results[0]["text"]


def test_checks_run_from_the_pinned_checkout(scratch):
    """The ready check is the PINNED copy, so a worktree whose copy is broken is still judged by the real one."""
    wt = lane(scratch, "pinned", {"tests/test_t.py": "def test_t():\n    assert True\n"})
    (wt / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\necho hacked; exit 0\n")  # uncommitted edit
    results = checks.run_all(wt, scratch["cfg"])
    assert results[0]["name"] == "ready" and results[0]["ok"] and "hacked" not in results[0]["text"]


def test_checks_cwd_is_the_worktree(scratch):
    wt = lane(scratch, "cwd", {"tests/test_t.py": "def test_t():\n    assert True\n"})
    rung = {"name": "pwd", "cmd": "pwd"}
    ok, text = checks.run_rung(rung, wt, scratch["cfg"], [], scratch["repo"])
    assert ok and text.strip().endswith("cwd")


def test_ready_check_fails_a_wrong_author_and_no_issue(scratch):
    wt = lane(scratch, "author", {"tests/test_t.py": "def test_t():\n    assert True\n"}, author="someone@example.com", msg="no issue")
    r = checks.run_all(wt, scratch["cfg"])[0]
    assert r["name"] == "ready" and not r["ok"] and "not the agent" in r["text"] and "cites no issue" in r["text"]
