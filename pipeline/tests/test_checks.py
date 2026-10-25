"""pipeline.test-red-on-base, pinned-checks, quick-checks-per-item."""
from __future__ import annotations

import subprocess
from pathlib import Path

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


REAL_FIX = {"src/mod.py": "def base():\n    return 0\n\n\ndef f1():\n    return 1\n",
            "tests/test_1.py": "from src.mod import f1\n\ndef test_f1():\n    assert f1() == 1\n"}


def test_a_coder_change_that_breaks_a_guard_turns_the_check_red(scratch):
    """HIGH 1 (review 2026-10-25): the guards must see the CODER'S tree. check_no_bad.py scans ROOT; run from the
    pinned checkout it never saw src/bad.py and was green. Failed before the scratch-tree fix."""
    wt = lane(scratch, "bad", {**REAL_FIX, "src/bad.py": "# forbidden\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert not r["fast-guards"]["ok"] and "src/bad.py is forbidden" in r["fast-guards"]["text"]


def test_checks_run_from_the_pinned_checkout(scratch):
    """The check files in the scratch tree are the PINNED commit's, so a worktree whose copies are broken (committed
    or not) is still judged by the real ones; and the guard runs against the coder's HEAD."""
    wt = lane(scratch, "pinned", REAL_FIX)
    (wt / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\necho hacked; exit 0\n")  # uncommitted edit
    (wt / "scripts" / "check_no_bad.py").write_text("print('hacked'); raise SystemExit(1)\n")  # uncommitted edit
    results = {r["name"]: r for r in checks.run_all(wt, scratch["cfg"])}
    assert results["pinned-checks"]["ok"] and "2 files" in results["pinned-checks"]["text"]
    assert results["ready"]["ok"] and "hacked" not in results["ready"]["text"]
    assert results["fast-guards"]["ok"], results["fast-guards"]["text"]


def test_red_on_base_fails_a_test_that_passes_on_base(scratch):
    wt = lane(scratch, "trivial", {"tests/test_t.py": "def test_t():\n    assert True\n"})
    results = checks.run_all(wt, scratch["cfg"])
    red = {r["name"]: r for r in results}
    assert red["ready"]["ok"]
    assert not red["red-on-base"]["ok"] and "NOT RED ON BASE" in red["red-on-base"]["text"]
    assert [r["name"] for r in results] == ["pinned-checks", "ready", "red-on-base"], "stops at the first red rung"


def test_red_on_base_passes_a_real_fix(scratch):
    wt = lane(scratch, "real", REAL_FIX)
    results = checks.run_all(wt, scratch["cfg"])
    assert [(r["name"], r["ok"]) for r in results] == [("pinned-checks", True), ("ready", True), ("red-on-base", True), ("fast-guards", True)]
    assert all(r["seconds"] >= 0 for r in results)
    assert "pipeline-" not in git(wt, "worktree", "list"), "every scratch tree is removed"


def test_each_changed_test_file_must_be_red_on_its_own(scratch):
    """One red file must not cover a trivial sibling (review MED 10)."""
    wt = lane(scratch, "pair", {**REAL_FIX, "tests/test_trivial.py": "def test_t():\n    assert True\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert not r["red-on-base"]["ok"] and "test_trivial.py passes" in r["red-on-base"]["text"]


def test_red_on_base_is_measured_at_the_items_start_not_the_branch_base(scratch):
    """Batch item 2 is judged against the tree after item 1 (`since`), so an ImportError on the branch base does
    not count as red (review MED 10)."""
    wt = lane(scratch, "batch", REAL_FIX)
    since = git(wt, "rev-parse", "HEAD")
    (wt / "tests" / "test_2.py").write_text("from src.mod import f1\n\ndef test_again():\n    assert f1() == 1\n")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "two (Fixes #1002)")
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"], since=since)}
    assert not r["red-on-base"]["ok"] and f"passes at {since[:9]}" in r["red-on-base"]["text"]


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


def test_a_new_guard_may_be_added_but_no_check_changed(scratch):
    """A Stage 1 step adds scripts/check_*.py; that is allowed. Changing an existing check is not."""
    wt = lane(scratch, "newguard", {**REAL_FIX, "scripts/check_new_thing.py": "import sys\nsys.exit(0)\n"})
    results = {r["name"]: r for r in checks.run_all(wt, scratch["cfg"])}
    assert results["pinned-checks"]["ok"] and results["fast-guards"]["ok"]
    wt2 = lane(scratch, "editguard", {"scripts/lane_ready_check.sh": "#!/bin/bash\nexit 0\n"})
    assert not checks.run_all(wt2, scratch["cfg"])[0]["ok"]
    # the coder keeps editing ITS OWN new guard over a second commit: not a pinned check, so allowed (retry proof 2026-10-25)
    (wt / "scripts" / "check_new_thing.py").write_text("import sys\nprint('v2')\nsys.exit(0)\n")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "guard v2 (Fixes #1001)")
    assert checks.run_all(wt, scratch["cfg"])[0]["ok"]


def test_checks_cwd_is_the_scratch_tree_of_the_worktree(scratch):
    wt = lane(scratch, "cwd", REAL_FIX)
    rung = {"name": "pwd", "cmd": "pwd"}
    tree = checks.scratch_tree(wt, "HEAD")
    try:
        ok, text = checks.run_rung(rung, wt, tree, scratch["cfg"], [], "origin/integration")
        assert ok and Path(text.strip()).resolve() == Path(tree).resolve()
    finally:
        checks.drop_tree(wt, tree)


def test_ready_check_fails_a_wrong_author_and_no_issue(scratch):
    wt = lane(scratch, "author", REAL_FIX, author="someone@example.com", msg="no issue")
    r = checks.run_all(wt, scratch["cfg"])[1]
    assert r["name"] == "ready" and not r["ok"] and "not the agent" in r["text"] and "cites no issue" in r["text"]
