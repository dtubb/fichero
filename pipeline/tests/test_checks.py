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


def test_a_coder_sitecustomize_cannot_green_the_guards(scratch):
    """Re-review MED A: a coder-added sitecustomize.py on the guards' path exited every check_* green. It is now a
    pinned-path refusal; and the guards run with `python -I`, so even an unrefused one would not be imported."""
    bypass = "import os, sys\nif 'check_' in ' '.join(sys.argv) or True:\n    os._exit(0)\n"
    wt = lane(scratch, "site", {**REAL_FIX, "src/bad.py": "# forbidden\n", "scripts/sitecustomize.py": bypass})
    results = checks.run_all(wt, scratch["cfg"])
    assert results[0]["name"] == "pinned-checks" and not results[0]["ok"] and "sitecustomize.py" in results[0]["text"]
    # and the isolated runner itself: a sitecustomize in the scripts dir is not imported even when present
    env = checks.test_env(wt, scratch["cfg"])
    r = checks.sh(checks.isolated(str(wt / "scripts" / "check_no_bad.py"), env), cwd=wt, env=env)
    assert r.returncode == 1 and "forbidden" in r.stdout, "the guard ran and saw bad.py; sitecustomize did not exit it"


def test_a_stdlib_named_module_at_a_python_path_root_is_red_and_cannot_shadow(scratch):
    """Round-3 R1: a coder-added pathlib.py at the python_path root (`.` here) gave every guard green."""
    planted = "import os\nos._exit(0)\n"
    wt = lane(scratch, "shadow", {**REAL_FIX, "src/bad.py": "# forbidden\n", "pathlib.py": planted})
    r = checks.run_all(wt, scratch["cfg"])[0]
    assert r["name"] == "pinned-checks" and not r["ok"] and "pathlib.py" in r["text"]
    # and even if it slipped through, the isolated runner puts the tree AFTER the stdlib: the guard still runs
    env = checks.test_env(wt, scratch["cfg"])
    res = checks.sh(checks.isolated(str(wt / "scripts" / "check_no_bad.py"), env), cwd=wt, env=env)
    assert res.returncode == 1 and "forbidden" in res.stdout


def test_failing_rung_text_is_capped_by_chars_and_lines(scratch):
    long = "\n".join("x" * 1000 for _ in range(100))
    out = checks.tail(long)
    assert len(out.splitlines()) <= 40 and len(out) <= 4000 and max(len(ln) for ln in out.splitlines()) <= 300


def test_a_change_under_the_worktrees_claude_dir_is_red_committed_or_untracked(scratch):
    """Round-2 MED: a hook planted in .claude/ would run outside the sandbox at the next session start."""
    wt = lane(scratch, "hook", {**REAL_FIX, ".claude/settings.local.json": '{"hooks": {}}\n'})
    r = checks.run_all(wt, scratch["cfg"])[0]
    assert r["name"] == "pinned-checks" and not r["ok"] and ".claude/settings.local.json" in r["text"]
    wt2 = lane(scratch, "untracked", REAL_FIX)
    (wt2 / ".claude").mkdir()
    (wt2 / ".claude" / "settings.local.json").write_text("{}")  # not committed, not even staged
    r = checks.run_all(wt2, scratch["cfg"])[0]
    assert not r["ok"] and "untracked" not in r["text"] and ".claude/settings.local.json" in r["text"]


def test_scratch_trees_and_base_dirs_live_under_the_state_dir(scratch, monkeypatch):
    """Round-2 MED: the coder can write its TMPDIR, so the checks' scratch trees must not be there."""
    monkeypatch.setattr(checks, "STATE", scratch["state"])
    made = []
    real = checks.tempfile.mkdtemp
    monkeypatch.setattr(checks.tempfile, "mkdtemp", lambda prefix, dir=None: made.append(dir) or real(prefix=prefix, dir=dir))
    wt = lane(scratch, "where", REAL_FIX)
    assert all(r["ok"] for r in checks.run_all(wt, scratch["cfg"]))
    assert made and all(Path(d) == scratch["state"] / "tmp" for d in made), made


def test_pth_conftest_and_stdlib_shadow_files_need_maintainer(scratch):
    for name, path in (("pth", "scripts/evil.pth"), ("conftest", "src/conftest.py"), ("shadow", "scripts/json.py")):
        wt = lane(scratch, name, {**REAL_FIX, path: "# planted\n"})
        r = checks.run_all(wt, scratch["cfg"])[0]
        assert r["name"] == "pinned-checks" and not r["ok"] and path in r["text"], path
    wt = lane(scratch, "okconftest", {**REAL_FIX, "tests/conftest.py": "# fixtures\n"})
    assert checks.run_all(wt, scratch["cfg"])[0]["ok"], "a conftest in the coder's own test dir is fine"


def test_overlay_failure_raises_instead_of_running_the_coders_copies(scratch, monkeypatch):
    wt = lane(scratch, "overlay", REAL_FIX)
    real = checks.sh

    def failing_checkout(args, cwd, **kw):
        if args[:2] == ["git", "checkout"] and "--" in args:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        return real(args, cwd, **kw)

    monkeypatch.setattr(checks, "sh", failing_checkout)
    results = checks.run_all(wt, scratch["cfg"])
    assert len(results) == 1 and not results[0]["ok"] and "could not lay the pinned checks" in results[0]["text"]
    assert "pipeline-tree-" not in git(wt, "worktree", "list"), "the half-made tree is removed"


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
    """The one check that needs a real pytest (the stub only resolves imports)."""
    scratch["cfg"]["ladder"][1]["pytest"] = "{python} -m pytest -q -p no:cacheprovider {files}"
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


def test_a_ruff_failure_names_the_file_line_and_rule(scratch):
    """Two coders fixed the wrong thing on 2026-10-25 because the retry text said only 'ruff failed'."""
    wt = lane(scratch, "lint", {**REAL_FIX, "tests/test_1.py": "import os\nfrom src.mod import f1\n\ndef test_f1():\n    assert f1() == 1\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert not r["ready"]["ok"]
    assert "tests/test_1.py:1:8" in r["ready"]["text"] and "F401" in r["ready"]["text"] and "`os` imported but unused" in r["ready"]["text"]
    assert len(r["ready"]["text"].splitlines()) <= 45


def test_ready_check_fails_a_wrong_author_and_no_issue(scratch):
    wt = lane(scratch, "author", REAL_FIX, author="someone@example.com", msg="no issue")
    r = checks.run_all(wt, scratch["cfg"])[1]
    assert r["name"] == "ready" and not r["ok"] and "not the agent" in r["text"] and "cites no issue" in r["text"]


def test_an_approved_check_change_runs_the_coders_copy_not_the_pinned_one(scratch):
    """approve-checks: the maintainer OKs the change; the coder's guard is what runs, and a red guard still fails."""
    wt = lane(scratch, "guarded", {**REAL_FIX, "scripts/check_no_bad.py": "import sys\nprint('stricter')\nsys.exit(1)\n"})
    assert not checks.run_all(wt, scratch["cfg"])[0]["ok"]
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"], approved={"scripts/check_no_bad.py": checks.blob(wt, "HEAD", "scripts/check_no_bad.py")})}
    assert r["pinned-checks"]["ok"] and not r["fast-guards"]["ok"] and "stricter" in r["fast-guards"]["text"]


def test_a_guard_over_its_budget_is_red_with_the_way_out(scratch):
    (scratch["repo"] / "scripts" / "check_slow.py").write_text("import time\ntime.sleep(5)\n")
    git(scratch["repo"], "add", ".")
    git(scratch["repo"], "-c", "user.name=M", "-c", "user.email=m@example.com", "commit", "-qm", "slow guard")
    wt = lane(scratch, "slow", REAL_FIX)
    scratch["cfg"]["ladder"][2]["budget_s"] = {"check_slow": 1}
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert not r["fast-guards"]["ok"] and "over its 1 s budget" in r["fast-guards"]["text"]


def test_an_approval_is_for_that_content_a_later_edit_is_red_again(scratch):
    """approve-checks pins the blob: the approved guard runs as the coder's copy, an edited one is a pinned-checks red."""
    f = "scripts/check_no_bad.py"
    wt = lane(scratch, "guarded", {**REAL_FIX, f: "import sys\nprint('approved')\nsys.exit(0)\n"})
    pin = {f: checks.blob(wt, "HEAD", f)}
    assert checks.run_all(wt, scratch["cfg"], approved=pin)[0]["ok"]
    (wt / f).write_text("import sys\nprint('edited after approval')\nsys.exit(0)\n")
    git(wt, "add", ".")
    git(wt, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", "edit the guard again")
    r = checks.run_all(wt, scratch["cfg"], approved=pin)[0]
    assert r["name"] == "pinned-checks" and not r["ok"] and f in r["text"]


def test_a_swift_only_change_skips_red_on_base_instead_of_handing_pytest_a_swift_path(scratch):
    """Live, #3961: a .swift test path went to pytest ("not found") and the coder was re-dispatched for nothing."""
    wt = lane(scratch, "swiftonly", {"App/DocumentStoreTests.swift": "// test\n", "App/Store.swift": "// code\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"])}
    assert r["red-on-base"]["ok"] and "no python tests changed" in r["red-on-base"]["text"]
    py = lane(scratch, "pyonly", {"src/mod.py": "def base():\n    return 0\n\n\ndef g():\n    return 2\n"})
    assert not {x["name"]: x for x in checks.run_all(py, scratch["cfg"])}["red-on-base"]["ok"], "a python change with no test is still red"


def test_an_approved_guard_edit_beside_swift_is_not_python_source_needing_a_test(scratch):
    """Live, #3961: a one-line guard allowlist change (approved) plus Swift said "a source change needs a test"."""
    f = "scripts/check_no_bad.py"
    wt = lane(scratch, "guardswift", {f: "import sys\nsys.exit(0)\n", "App/Store.swift": "// code\n"})
    r = {x["name"]: x for x in checks.run_all(wt, scratch["cfg"], approved={f: checks.blob(wt, "HEAD", f)})}
    assert r["red-on-base"]["ok"] and "no python tests changed" in r["red-on-base"]["text"]
