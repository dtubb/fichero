"""dev-workflows.run.presubmit (speed batch 2, manager 2026-11-03/04): `builder done` runs the ready check with its guards over the lane's
sha first, with the PINNED script and guards laid over a scratch tree of that sha, so a guard's red stops in the lane and a lane that edits
its own ready script cannot pass its own presubmit."""
from __future__ import annotations

import os
import subprocess

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue

PINNED_READY = "#!/bin/bash\n[ -e RED ] && { echo 'FAIL: scripts/check_spec_build_order_shape.py'; exit 1; }\necho READY\n"
RULES = '[check]\nready = ["scripts/lane_ready_check.sh", "--no-guards", "HEAD"]\ncheck_paths = ["scripts/"]\n'


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    pinned, wt = tmp_path / "pinned", tmp_path / "wt"
    for d, script in ((pinned, PINNED_READY), (wt, PINNED_READY)):
        (d / "scripts").mkdir(parents=True)
        (d / "scripts" / "lane_ready_check.sh").write_text(script)
        (d / "harness.toml").write_text(RULES)
        _git(d, "init", "-q", "-b", "main")
        _git(d, "add", "."), _git(d, "commit", "-qm", "base")
    monkeypatch.setattr(queue, "PRESUBMIT_ROOT", [str(pinned)])
    queue.add("ext", str(wt), "1.1", str(tmp_path / "b"), [7], kind="external")
    return wt


def test_a_red_presubmit_refuses_the_done_and_a_green_one_lets_it_through(lane, capsys):
    (lane / "RED").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "red")
    assert cli.main(["done", "ext", _git(lane, "rev-parse", "HEAD"), "--state", str(journal.STATE)]) == 1
    out = capsys.readouterr().out
    assert "REFUSED: the presubmit" in out and "check_spec_build_order_shape" in out
    assert queue.load()[0]["steps"][0]["state"] == "queued", "nothing went to the ladder"
    _git(lane, "rm", "-q", "RED"), _git(lane, "commit", "-qm", "fixed")
    assert cli.main(["done", "ext", _git(lane, "rev-parse", "HEAD"), "--state", str(journal.STATE)]) == 0
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"] == ["red", "green"]


def test_a_lane_that_edits_its_own_ready_script_is_judged_by_the_pinned_one_and_no_presubmit_skips_on_purpose(lane, capsys):
    (lane / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\necho READY\n")  # the lane's own copy always passes
    (lane / "RED").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "a red the lane's script hides")
    red = _git(lane, "rev-parse", "HEAD")
    ok, said = queue.presubmit("ext", red)
    assert not ok and "check_spec_build_order_shape" in said, "the pinned script judged the lane's tree"
    assert len(_git(lane, "worktree", "list").splitlines()) == 1, "the scratch tree is removed from the lane's repo"
    assert cli.main(["done", "ext", red, "--no-presubmit", "--state", str(journal.STATE)]) == 0, "the manager's skip"



def test_a_scratch_tree_refusal_refuses_the_done_and_leaves_no_worktree(lane, tmp_path):
    """Review -89: a lane tree the overlay refuses (a check dir that is a symlink out) refuses, as the ladder would; nothing is left."""
    import os
    (lane / "scripts" / "lane_ready_check.sh").unlink()
    os.rmdir(lane / "scripts") if not any((lane / "scripts").iterdir()) else None
    (tmp_path / "elsewhere").mkdir()
    os.symlink(tmp_path / "elsewhere", lane / "scripts")
    _git(lane, "add", "-A"), _git(lane, "commit", "-qm", "scripts is a link out")
    ok, said = queue.presubmit("ext", _git(lane, "rev-parse", "HEAD"))
    assert not ok and said.startswith("presubmit refused") and "outside the scratch tree" in said
    assert len(_git(lane, "worktree", "list").splitlines()) == 1, "the half-made scratch tree is removed"


def test_the_pinned_copy_is_the_live_loops_checkout_never_the_code_done_runs_from(lane, tmp_path, monkeypatch):
    """Review -89: with no override, presubmit reads <state>/live-root (written by the running loop); none = nothing to judge with."""
    monkeypatch.setattr(queue, "PRESUBMIT_ROOT", [None])
    sha = _git(lane, "rev-parse", "HEAD")
    assert queue.presubmit("ext", sha)[1].startswith("presubmit skipped"), "no live root recorded: skipped and said"
    journal.STATE.mkdir(parents=True, exist_ok=True)
    (journal.STATE / "live-root").write_text(str(tmp_path / "pinned") + "\n")
    (lane / "RED").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "red")
    ok, said = queue.presubmit("ext", _git(lane, "rev-parse", "HEAD"))
    assert not ok and "check_spec_build_order_shape" in said, "the live root's pinned script judged it"



def test_live_rules_newer_than_this_code_are_a_skip_said_never_a_traceback(lane, tmp_path, capsys):
    """Review -92: a landing adds a [check] key; a lane whose code predates it runs `builder done`: skipped and said, no ValueError."""
    (tmp_path / "pinned" / "harness.toml").write_text(RULES + 'a_key_from_the_future = 1\n')
    sha = _git(lane, "rev-parse", "HEAD")
    ok, said = queue.presubmit("ext", sha)
    assert ok and said.startswith("presubmit skipped") and "a_key_from_the_future" in said
    assert cli.main(["done", "ext", sha, "--state", str(journal.STATE)]) == 0, "the done goes through; the ladder judges it with the current code"


GUARD = "#!/bin/bash\ngrep -q '\"/new\"' scripts/known_gaps.json || { [ -e NEWROUTE ] && { echo 'FAIL: check_route_gaps: /new not listed'; exit 1; }; }\necho READY\n"


def test_a_batch_whose_red_is_only_its_own_guard_data_passes_with_the_line_and_any_other_red_still_refuses(lane, tmp_path, capsys):
    """Manager 2026-11-04: a new route with its known-gaps entry is red under the PINNED data by design; presubmit runs again with
    head's copy of exactly the data files the batch changed, passes and says the guard-data approve is needed. Another red refuses."""
    pinned = tmp_path / "pinned"
    for d in (pinned, lane):
        (d / "scripts" / "lane_ready_check.sh").write_text(GUARD)
        (d / "scripts" / "known_gaps.json").write_text('["/old"]\n')
        _git(d, "add", "."), _git(d, "commit", "-qm", "guard + data")
    _git(lane, "update-ref", "refs/remotes/origin/integration", "HEAD")
    (lane / "NEWROUTE").write_text("x")
    (lane / "scripts" / "known_gaps.json").write_text('["/old", "/new"]\n')
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "a route and its gap entry")
    assert cli.main(["done", "ext", _git(lane, "rev-parse", "HEAD"), "--state", str(journal.STATE)]) == 0
    assert "would need the guard-data approve for scripts/known_gaps.json" in capsys.readouterr().out
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"] == ["guard-data"]
    (lane / "RED").write_text("x")
    (lane / "scripts" / "lane_ready_check.sh").write_text(GUARD.replace("echo READY", "[ -e RED ] && { echo 'FAIL: other'; exit 1; }\necho READY"))
    (pinned / "scripts" / "lane_ready_check.sh").write_text(GUARD.replace("echo READY", "[ -e RED ] && { echo 'FAIL: other'; exit 1; }\necho READY"))
    _git(pinned, "add", "."), _git(pinned, "commit", "-qm", "pinned guard also checks RED")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "and another red")
    ok, said = queue.presubmit("ext", _git(lane, "rev-parse", "HEAD"))
    assert not ok and "would need the guard-data approve" not in said, "a red the data does not explain is still a refusal"
    assert journal.read()[-1]["event"] == "presubmit" and journal.read()[-1]["state"] == "red"


def test_the_ready_checks_fast_guards_run_a_timed_out_guard_once_more_and_only_a_second_timeout_is_red(tmp_path):
    """2026-11-07: at load 95 a 10 s guard timed out in `builder done` and refused a green batch; the ladder retries a timeout once."""
    import subprocess
    import sys
    from pathlib import Path

    script = next(p for p in Path(__file__).resolve().parents if (p / "scripts" / "lane_ready_check.sh").exists()) / "scripts" / "lane_ready_check.sh"
    (tmp_path / "pipeline" / "projects").mkdir(parents=True)
    (tmp_path / "pipeline" / "projects" / "fichero.toml").write_text(
        '[repo]\npython_path = "."\n[[ladder]]\nname = "fast-guards"\nskip = []\ntimeout_s = 1\n')
    s = tmp_path / "scripts"
    s.mkdir()
    for i in range(20):
        (s / f"check_g{i:02}.py").write_text("pass\n")
    mark = tmp_path / "slow-once"
    (s / "check_g00.py").write_text(f"import os, time\nif not os.path.exists({str(mark)!r}):\n    open({str(mark)!r}, 'w').close(); time.sleep(3)\n")
    fn = subprocess.run(["sed", "-n", "/^run_fast_guards()/,/^}/p", str(script)], capture_output=True, text=True, check=True).stdout

    def run():
        return subprocess.run(["bash", "-c", fn + "\nrun_fast_guards"], cwd=tmp_path, capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "FICHERO_PYTHON_BIN": sys.executable}, timeout=60)
    r = run()
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr
    (s / "check_g00.py").write_text("import time\ntime.sleep(3)\n")
    r = run()
    assert r.returncode == 1 and "check_g00.py: timeout (twice)" in r.stdout, "a guard that times out twice is red"


def test_the_scratch_trees_git_trusts_the_lanes_tree_whoever_owns_it(tmp_path):
    """#6507: `builder done lane-ie` refused with 'dubious ownership': the scratch tree's git runs as the owner on the jail user's tree
    with the global config switched off, so no safe.directory applied. The command line carries it, as every other owner-side git call does."""
    from fichero_builder import check_tool
    _git(tmp_path, "init", "-q")
    argv = check_tool._git_argv(tmp_path, ["worktree", "add", "x"])
    assert "safe.directory=*" in argv and argv.index("safe.directory=*") < argv.index("worktree")


def test_the_presubmit_honours_a_guard_data_approval_bound_to_the_files_content(lane, tmp_path, capsys):
    """Alert 541 (2026-11-11): `builder done` refused a head as NOT READY although the guard-data approval for its known-gaps files
    existed (bound to the old head). With the approval bound to the files' blobs, the presubmit lays HEAD's copies under the pinned
    guards from the start and is plainly green; without it the second run still only says what approve would be needed."""
    pinned = tmp_path / "pinned"
    _git(lane, "update-ref", "refs/remotes/origin/integration", "HEAD")  # the base the presubmit diffs the data files against
    for d, text in ((pinned, "old"), (lane, "new")):
        (d / "scripts" / "x_known_gaps.json").write_text(text)
        (d / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\ngrep -q new scripts/x_known_gaps.json && { echo READY; exit 0; }\necho 'FAIL: scripts/check_x.py: 1 new gap'; exit 1\n")
        _git(d, "add", "."), _git(d, "commit", "-qm", "gaps")
    head = _git(lane, "rev-parse", "HEAD")
    assert cli.main(["done", "ext", head, "--state", str(journal.STATE)]) == 0
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"] == ["guard-data"], "no approval: green only under head's data, said so"
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="queued", approved_guard_blobs={"scripts/x_known_gaps.json": _git(lane, "rev-parse", f"{head}:scripts/x_known_gaps.json")})
    queue.save(lanes)
    (lane / "z").write_text("z")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "later")
    assert cli.main(["done", "ext", _git(lane, "rev-parse", "HEAD"), "--state", str(journal.STATE)]) == 0
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"][-1] == "green", "the approval holds at the later head: plainly green"


def test_the_presubmit_makes_its_scratch_tree_as_a_shared_clone_when_the_lanes_git_dir_is_not_writable(lane, tmp_path, capsys):
    """2026-11-11: `builder done` run by the manager could not add a worktree to the worker's clone ('could not create directory of
    .../.git/worktrees/...: Permission denied'). When `git worktree add` is refused, the scratch tree is a shared clone of the lane's repo
    (objects by alternates, every new file the invoking user's) at the same sha, with the remote refs the checks diff against, and it is
    removed after; a presubmit judges the same tree either way."""
    from fichero_builder import check_tool
    (lane / "ok").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "work")
    _git(lane, "update-ref", "refs/remotes/origin/integration", "HEAD~1")
    head = _git(lane, "rev-parse", "HEAD")
    gitdir = lane / ".git"
    worktrees = gitdir / "worktrees"
    worktrees.mkdir(exist_ok=True)
    worktrees.chmod(0o555)
    made = []
    real = check_tool._scratch_tree

    def spy(*a, **k):
        tree = real(*a, **k)
        made.append(tree)
        return tree
    try:
        import fichero_builder.check_tool as ct
        ct._scratch_tree, orig = spy, ct._scratch_tree
        try:
            ok, said = queue.presubmit("ext", head)  # the presubmit alone: the land tree `done` makes after it is the lane's own repo's business
            assert ok, said
        finally:
            ct._scratch_tree = orig
    finally:
        worktrees.chmod(0o755)
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"] == ["green"]
    assert made and not os.path.exists(made[0]), "the scratch clone is removed after the presubmit"
    assert not list(worktrees.iterdir()), "nothing was written into the lane's own git dir"
