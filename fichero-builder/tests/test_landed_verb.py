"""dev-workflows.tool.landed: after a READY verdict and a green check row, `builder landed <sha>` does the fifteen hand
steps as one command (push only with --push), each a journal row, and stops red with its reason. A scratch origin, an
engine repo cloned --no-checkout as in production, and a jail root under a fake sudo boundary."""
from __future__ import annotations

import json
import os
import subprocess
import types

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, land_tool, landed


def _g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    for k, v in {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    seed = tmp_path / "seed"
    seed.mkdir()
    _g(seed, "init", "-q", "-b", "integration")
    (seed / "f").write_text("0")
    _g(seed, "add", "f"), _g(seed, "commit", "-qm", "base")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)
    engine = tmp_path / "engine"
    subprocess.run(["git", "clone", "-q", "--no-checkout", str(origin), str(engine)], check=True)
    wr = tmp_path / "wr"
    (wr / "state").mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(wr / "root")], check=True)
    # the candidate: one commit over integration, in the engine repo as a work ref (what `builder work` leaves)
    _g(seed, "checkout", "-qb", "lane")
    (seed / "g").write_text("1")
    _g(seed, "add", "g"), _g(seed, "commit", "-qm", "feat: g\n\nFixes #7\nPart of #6116")
    sha = _g(seed, "rev-parse", "HEAD")
    _g(engine, "fetch", "-q", str(seed), "+refs/heads/lane:refs/heads/work-n1")
    pinned_dir = tmp_path / "pinned"
    (tmp_path / "harness.toml").write_text(
        f'[check]\nengine_repo = "{engine}"\npython = "/py"\nready = ["r"]\nguard_glob = "g"\nmin_guards = 1\ncontract_guards = ["c"]\n'
        f'check_paths = ["p"]\ncontract_paths = ["c"]\npytest_config = "pyproject.toml"\n'
        f'[land]\nbranch = "integration"\nboundary = ["forbidden-token"]\npinned_dir = "{pinned_dir}"\n'
        f'[jail]\nuser = "wuser"\nworkroot = "{wr}"\ndeny_read = ["~/.ssh"]\n')
    store = tmp_path / "verdicts.json"
    ran = []

    def local(a_or_j, script):
        ran.append(script)
        return subprocess.run(["sh", "-c", f"cd {wr} && {script}"], capture_output=True, text=True)
    monkeypatch.setattr(landed, "as_worker", local)
    gh_log = tmp_path / "gh.log"
    gh = tmp_path / "gh"
    gh.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {gh_log}\n")
    gh.chmod(0o755)

    def ready():
        land_tool.write_verdict(store, engine, "integration", sha)

    def green():
        journal.append("check", repo=str(engine), since=_g(engine, "rev-parse", "integration"), head=sha, ok=True, failed="")

    def go(*extra):
        return cli.main(["landed", sha, "--root", str(tmp_path), "--verdicts", str(store), "--gh", str(gh), "--state", str(tmp_path / "s"), *extra])
    return types.SimpleNamespace(tmp=tmp_path, origin=origin, engine=engine, wr=wr, sha=sha, store=store, ran=ran, ready=ready, green=green,
                                 go=go, pinned_dir=pinned_dir, gh_log=gh_log, seed=seed)


def rows():
    return [r for r in journal.read() if r["event"] == "landed"]


def test_refuses_without_a_ready_verdict(world, capsys):
    world.green()
    assert world.go() == 1
    assert "READY" in capsys.readouterr().err
    assert rows()[-1]["step"] == "verdict" and rows()[-1]["ok"] is False
    assert _g(world.origin, "rev-parse", "integration") != world.sha


def test_refuses_without_a_green_check_row(world, capsys):
    world.ready()
    journal.append("check", head=world.sha, ok=False)
    assert world.go() == 1
    assert "check" in capsys.readouterr().err and rows()[-1]["step"] == "check-row" and rows()[-1]["ok"] is False


def test_refuses_a_sha_that_is_not_a_fast_forward_of_origin(world, capsys):
    world.ready(), world.green()
    (world.seed / "h").write_text("2")
    _g(world.seed, "checkout", "-q", "integration"), _g(world.seed, "add", "h"), _g(world.seed, "commit", "-qm", "other lane")
    _g(world.seed, "push", "-q", str(world.origin), "integration")
    _g(world.engine, "fetch", "-q", "origin")
    assert world.go() == 1
    assert "fast-forward" in capsys.readouterr().err and rows()[-1]["step"] == "fast-forward" and rows()[-1]["ok"] is False


def test_the_happy_path_without_push_pins_and_refreshes_but_leaves_origin_alone(world):
    world.ready(), world.green()
    _g(world.seed, "push", "-q", str(world.origin), "lane:integration")  # the maintainer pushed by hand
    assert world.go() == 0
    assert _g(world.engine, "rev-parse", "integration") == world.sha, "the engine repo's local branch follows origin"
    assert _g(world.engine, "rev-parse", f"pinned-{world.sha[:7]}") == world.sha
    pinned = world.pinned_dir / f"pinned-{world.sha[:7]}"
    assert pinned.is_dir() and _g(pinned, "rev-parse", "HEAD") == world.sha and (pinned / "g").exists()
    assert _g(world.wr / "root", "rev-parse", "HEAD") == world.sha, "the jail root was fast-forwarded as the worker"
    assert any("git -C root fetch" in s and "--ff-only" in s for s in world.ran)
    steps = [(r["step"], r["ok"]) for r in rows()]
    assert steps[:3] == [("verdict", True), ("check-row", True), ("fast-forward", True)]
    assert ("push", True) in steps and "no --push" in next(r["detail"] for r in rows() if r["step"] == "push")
    last = rows()[-1]
    assert last["step"] == "done" and last["sha"] == world.sha and last["branch"] == "integration" and last["pushed"] is False


def test_push_pushes_the_sha_by_fast_forward_and_the_row_says_so(world):
    world.ready(), world.green()
    assert world.go("--push") == 0
    assert _g(world.origin, "rev-parse", "integration") == world.sha
    assert rows()[-1]["pushed"] is True


def test_a_second_landing_replaces_the_previous_pinned_branch_and_worktree(world):
    world.ready(), world.green()
    assert world.go("--push") == 0
    first = world.sha
    (world.seed / "i").write_text("3")
    _g(world.seed, "add", "i"), _g(world.seed, "commit", "-qm", "feat: i\n\nPart of #6116")
    second = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n2")
    land_tool.write_verdict(world.store, world.engine, "integration", second)
    journal.append("check", head=second, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    assert cli.main(["landed", second, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),
                     "--state", str(world.tmp / "s"), "--push"]) == 0
    branches = _g(world.engine, "branch", "--list", "pinned-*", "--format=%(refname:short)").split()
    assert branches == [f"pinned-{second[:7]}"]
    assert not (world.pinned_dir / f"pinned-{first[:7]}").exists() and (world.pinned_dir / f"pinned-{second[:7]}").is_dir()


def test_scratch_worktrees_of_the_work_rows_for_that_sha_are_removed_as_the_worker(world):
    """#6204: the landing keeps a fresh worktree (a late review or revert can still use it); past the grace period the sweep
    removes it as the worker with `git worktree remove`, a patch of its uncommitted files first, the branch kept."""
    world.ready(), world.green()
    wt = world.wr / "wt-n1"
    _g(world.wr / "root", "worktree", "add", "-q", "-b", "n1", str(wt), "HEAD")
    (wt / "x").write_text("x")
    journal.append("work", name="n1", issues=[7], step="fetch", ok=True, detail=world.sha, worktree=str(wt))
    assert world.go("--push") == 0
    assert wt.is_dir(), "inside the grace period it stays"
    assert any(r["step"] == "scratch" and "grace" in r["detail"] for r in rows())
    sh = lambda script: subprocess.run(["sh", "-c", f"cd {world.wr} && {script}"], capture_output=True, text=True)  # noqa: E731
    done = landed.sweep(sh, "root", "origin/integration", 36, str(world.wr / ".removed"), set(), now=__import__("time").time() + 37 * 3600)
    assert not wt.exists() and len(done) == 1 and "removed" in done[0]
    (patch,) = (world.wr / ".removed").iterdir()
    assert "+x" in patch.read_text(), "the untracked file is in the patch"
    assert _g(world.wr / "root", "branch", "--list", "n1"), "the branch survives"


def test_the_sweep_keeps_unlanded_live_and_recently_used_worktrees_and_a_longer_grace_keeps_them_all(world):
    import time

    root = world.wr / "root"
    sh = lambda script: subprocess.run(["sh", "-c", f"cd {world.wr} && {script}"], capture_output=True, text=True)  # noqa: E731
    made = {}
    for n in ("landed", "live", "busy", "unlanded"):
        made[n] = world.wr / f"wt-{n}"
        _g(root, "worktree", "add", "-q", "-b", n, str(made[n]), "HEAD")
    (made["unlanded"] / "y").write_text("y")
    _g(made["unlanded"], "add", "y"), _g(made["unlanded"], "commit", "-qm", "not on integration")
    later = time.time() + 37 * 3600
    idx = _g(made["busy"], "rev-parse", "--path-format=absolute", "--git-path", "index")
    os.utime(idx, (later, later))  # used just now, as far as the sweep's clock is concerned
    done = landed.sweep(sh, "root", "origin/integration", 36, str(world.wr / ".removed"), {os.path.realpath(made["live"])}, now=later)
    assert [d.split(":")[0] for d in done] == [str(made["landed"])], done
    assert all(made[n].is_dir() for n in ("live", "busy", "unlanded"))
    assert landed.sweep(sh, "root", "origin/integration", 100, str(world.wr / ".removed"), set(), now=later) == [], "a longer grace keeps them"


def test_a_relative_pinned_dir_is_refused_before_anything_moves(world, capsys):
    world.ready(), world.green()
    f = world.tmp / "harness.toml"
    f.write_text(f.read_text().replace(f'pinned_dir = "{world.pinned_dir}"', 'pinned_dir = "pinned"'))
    assert world.go("--push") == 1
    assert "absolute" in capsys.readouterr().err
    assert _g(world.origin, "rev-parse", "integration") != world.sha


def test_a_red_step_stops_the_rest(world, monkeypatch, capsys):
    world.ready(), world.green()
    monkeypatch.setattr(landed, "as_worker", lambda j, s: subprocess.CompletedProcess(s, 1, "", "sudo: a password is required"))
    assert world.go("--push") == 1
    assert "password" in capsys.readouterr().err
    assert rows()[-1]["step"] == "jail-root" and rows()[-1]["ok"] is False and "done" not in [r["step"] for r in rows()]


def test_the_verdict_store_must_be_owned_and_private(world, capsys):
    world.ready(), world.green()
    os.chmod(world.store, 0o666)
    assert world.go() == 1
    assert rows()[-1]["step"] == "verdict" and rows()[-1]["ok"] is False
    assert json.loads(world.store.read_text()), "the store itself was left alone"


def test_the_cited_issues_are_closed_or_commented_through_gh(world):
    """issues.harness-closes-after-integration: one comment per cited issue naming each landed commit (sha, subject, its
    tests); Fixes/Closes closes; Already built comments the proving test and labels needs-your-test."""
    world.ready(), world.green()
    (world.seed / "tests").mkdir()
    (world.seed / "tests" / "test_j.py").write_text("def test_j(): pass\n")
    _g(world.seed, "add", "tests"), _g(world.seed, "commit", "-qm", "docs: j\n\nAlready built: #9 tests/test_j.py::test_j\nPart of #6116")
    second = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", second)
    journal.append("check", head=second, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    go = lambda *x: cli.main(["landed", second, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),  # noqa: E731
                              "--state", str(world.tmp / "s"), "--push", *x])
    assert go() == 0
    calls = world.gh_log.read_text().splitlines()
    first = world.sha[:7]
    assert calls[0] == f"issue close 7 --comment landed on integration at {second[:7]}: {first} feat: g (no test file)"
    both = [c for c in calls if c.startswith("issue comment 6116 --body ")]
    assert len(both) == 1, "one comment per issue per landing, every citing commit in it"
    assert f"{first} feat: g (no test file)" in both[0] and f"{second[:7]} docs: j (tests/test_j.py)" in both[0]
    assert any(c.startswith("issue comment 9 --body already built; the test that proves it: tests/test_j.py::test_j") for c in calls)
    assert "issue edit 9 --add-label needs-your-test" in calls
    assert rows()[-1]["issues"] == [7, 9, 6116]


def test_issues_are_untouched_until_the_sha_is_on_origin(world):
    """Never before the commit is on origin/<branch>: without --push and without a hand push the landing stops at on-origin."""
    world.ready(), world.green()
    assert world.go() == 1
    assert not world.gh_log.exists()
    assert rows()[-1]["step"] == "on-origin" and "not on origin/integration" in rows()[-1]["detail"]


def test_the_spec_behaviour_line_a_landed_commit_names_gets_ok_with_the_test(world):
    """A commit whose `Behaviour: <id>` trailer names a behaviour marks that spec line [OK] and names the commit's test file
    when the line names none; a line already [OK] is left alone; one `spec-ok` row per line changed."""
    spec = world.tmp / "docs" / "contributor_manual" / "specs" / "h" / "x.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# X\n- `x.one` [GAP] (#7) — the thing\n  continues here.\n- `x.two` [OK] (#8) — done. Tests: `t.py`\n- `x.three` [GAP] (#9) — another\n")
    subprocess.run(["git", "init", "-q", str(world.tmp)], check=True)  # the checkout it edits: a status it cannot read refuses
    _g(world.tmp, "add", "docs"), _g(world.tmp, "commit", "-qm", "specs")
    world.ready(), world.green()
    (world.seed / "tests").mkdir()
    (world.seed / "tests" / "test_one.py").write_text("def test_one(): pass\n")
    _g(world.seed, "add", "tests"), _g(world.seed, "commit", "-qm", "feat: x.one and x.two built, see `x.three`\n\nBehaviour: x.one\nBehaviour: x.two\nFixes #7")
    second = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", second)
    journal.append("check", head=second, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    assert cli.main(["landed", second, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),
                     "--state", str(world.tmp / "s"), "--push"]) == 0
    text = spec.read_text()
    assert "- `x.one` [OK] (#7) — the thing Tests: `tests/test_one.py`\n  continues here.\n" in text
    assert "- `x.two` [OK] (#8) — done. Tests: `t.py`\n" in text
    ok = [r for r in rows() if r["step"] == "spec-ok"]
    assert [(r["id"], r["tests"]) for r in ok] == [("x.one", ["tests/test_one.py"])]
    assert "- `x.three` [GAP]" in text, "an id a message only mentions in passing is not marked"


def test_no_issues_skips_gh_but_the_done_row_still_names_the_issues(world):
    world.ready(), world.green()
    assert world.go("--push", "--no-issues") == 0
    assert not world.gh_log.exists() and rows()[-1]["issues"] == [7, 6116]
    assert "--no-issues" in next(r["detail"] for r in rows() if r["step"] == "issues")


def test_a_journal_landed_does_not_own_or_others_can_write_refuses_before_anything(world, monkeypatch, capsys):
    """The check row allows a push and its rows name what `scratch` removes as the worker: `builder landed` trusts this file."""
    world.ready(), world.green()
    wt = world.wr / "wt-forged"
    wt.mkdir()
    journal.append("work", name="n", issues=[7], step="fetch", ok=True, detail=world.sha, worktree=str(wt))
    jp = journal.path()
    jp.chmod(0o666)
    assert world.go("--push") == 1
    assert "REFUSED (journal)" in capsys.readouterr().err
    assert _g(world.origin, "rev-parse", "integration") != world.sha and wt.is_dir(), "nothing moved"
    jp.chmod(0o644)
    real = os.getuid()
    monkeypatch.setattr(land_tool.os, "getuid", lambda: real + 1)
    assert world.go("--push") == 1
    assert "REFUSED (journal)" in capsys.readouterr().err and _g(world.origin, "rev-parse", "integration") != world.sha


def test_a_green_row_counts_only_for_the_range_being_landed(world, capsys):
    """The ladder runs once now, so the row must be that ladder: a row over head~1..head leaves the rest of the range unchecked."""
    world.ready()
    journal.append("check", repo=str(world.engine), since=world.sha, head=world.sha, ok=True, failed="")
    assert world.go("--push") == 1
    assert "check" in capsys.readouterr().err and rows()[-1]["step"] == "check-row" and rows()[-1]["ok"] is False
    assert _g(world.origin, "rev-parse", "integration") != world.sha
    world.green()
    assert world.go("--push") == 0
    assert _g(world.origin, "rev-parse", "integration") == world.sha


def test_a_maintainer_row_lands_and_the_landing_says_it_was_one(world):
    """A person typed --maintainer and no worker can: harness batches land this way, in the open."""
    world.ready()
    journal.append("check", since=_g(world.engine, "rev-parse", "integration"), head=world.sha, ok=True, maintainer=True)
    assert world.go("--push") == 0
    assert "maintainer" in next(r["detail"] for r in rows() if r["step"] == "check-row")


def test_a_range_over_the_boundary_is_not_pushed(world, capsys):
    """Nothing on this path ran the boundary: a READY verdict and a green row pushed a token to the public repo."""
    (world.seed / "leak").write_text("forbidden-token-here\n")
    _g(world.seed, "add", "leak"), _g(world.seed, "commit", "-qm", "feat: leak\n\nPart of #7")
    head = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", head)
    journal.append("check", head=head, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    assert cli.main(["landed", head, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),
                     "--state", str(world.tmp / "s"), "--push"]) == 1
    assert "leak: pattern 0" in capsys.readouterr().err and rows()[-1]["step"] == "boundary" and rows()[-1]["ok"] is False
    assert _g(world.origin, "rev-parse", "integration") != head


def test_a_rules_file_the_land_gate_would_refuse_refuses_here_too(world, capsys):
    world.ready(), world.green()
    f = world.tmp / "harness.toml"
    f.write_text(f.read_text().replace('min_guards = 1\n', ''))
    assert world.go("--push") == 1
    assert "min_guards" in capsys.readouterr().err and _g(world.origin, "rev-parse", "integration") != world.sha


def test_a_red_step_after_the_refresh_can_be_run_again_and_finishes_the_rest(world, monkeypatch):
    """Once the local branch has moved the range is empty, so a rerun used to die on `nothing to land` and the issues were never told."""
    world.ready(), world.green()
    real = landed.as_worker
    monkeypatch.setattr(landed, "as_worker", lambda j, s: subprocess.CompletedProcess(s, 1, "", "sudo: a password is required"))
    assert world.go("--push") == 1 and rows()[-1]["step"] == "jail-root"
    assert not world.gh_log.exists()
    monkeypatch.setattr(landed, "as_worker", real)
    assert world.go("--push") == 0
    assert rows()[-1]["step"] == "done"
    calls = world.gh_log.read_text().splitlines()
    assert any(c.startswith("issue close 7") for c in calls), "the base the first run saw still names the range"
    assert world.go("--push") == 1, "a finished landing is not run twice"


def test_without_push_an_unpushed_sha_is_refused_before_anything_moves_and_a_push_rerun_finishes(world, capsys):
    """Review of range 1: a run without --push pinned, removed scratch trees and closed issues as "landed" for a sha never pushed."""
    world.ready(), world.green()
    wt = world.wr / "wt-n1"
    wt.mkdir()
    journal.append("work", name="n1", issues=[7], step="fetch", ok=True, detail=world.sha, worktree=str(wt))
    assert world.go() == 1
    assert "not on origin" in capsys.readouterr().err and rows()[-1]["step"] == "on-origin" and rows()[-1]["ok"] is False
    assert not world.pinned_dir.exists() and wt.is_dir() and not world.gh_log.exists(), "nothing moved"
    assert "done" not in [r["step"] for r in rows()]
    assert _g(world.engine, "rev-parse", "integration") != world.sha, "the engine repo's branch stays with origin"
    assert world.go("--push") == 0, "the rerun pushes"
    assert _g(world.origin, "rev-parse", "integration") == world.sha and rows()[-1]["step"] == "done" and rows()[-1]["pushed"] is True
    assert "issue close 7" in world.gh_log.read_text() and wt.is_dir(), "a landed worktree waits out its grace period (#6204)"


def test_a_gh_that_times_out_is_a_red_step_never_a_traceback(world, monkeypatch, capsys):
    world.ready(), world.green()
    real = subprocess.run

    def run(argv, **k):
        if argv[0] == str(world.tmp / "gh"):
            raise subprocess.TimeoutExpired(argv, 120)
        return real(argv, **k)
    monkeypatch.setattr(landed.subprocess, "run", run)
    assert world.go("--push") == 1
    assert "timed out" in capsys.readouterr().err and rows()[-1]["step"] == "issues" and rows()[-1]["ok"] is False


def test_keep_worktree_leaves_a_lanes_worktree_for_its_open_session(world):
    """The queue's worker stays open after a step, in that worktree: its landing must not remove what the fetch row names."""
    world.ready(), world.green()
    wt = world.wr / "wt-lane"
    wt.mkdir()
    journal.append("work", name="lane", issues=[7], step="fetch", ok=True, detail=world.sha, worktree=str(wt))
    assert world.go("--push", "--keep-worktree") == 0
    assert wt.is_dir() and "kept" in next(r["detail"] for r in rows() if r["step"] == "scratch")


def test_a_dirty_spec_file_it_would_edit_refuses_before_the_push_and_nothing_else_does(world, capsys):
    """Maintainer's answer: landing refuses when the spec file it would edit is dirty, nothing else. An unrelated dirty file
    or a dirty spec it would not touch goes through."""
    specs = world.tmp / "docs" / "contributor_manual" / "specs" / "h"
    specs.mkdir(parents=True)
    spec, other = specs / "x.md", specs / "y.md"
    spec.write_text("- `x.one` [GAP] (#7) — the thing\n")
    other.write_text("- `y.one` [GAP] (#8) — not named\n")
    (world.tmp / "unrelated.txt").write_text("a\n")
    subprocess.run(["git", "init", "-q", str(world.tmp)], check=True)
    _g(world.tmp, "add", "docs", "unrelated.txt"), _g(world.tmp, "commit", "-qm", "specs")
    (world.seed / "k").write_text("5")
    _g(world.seed, "add", "k"), _g(world.seed, "commit", "-qm", "feat: `x.one` built\n\nBehaviour: x.one\nFixes #7")
    head = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", head)
    journal.append("check", head=head, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    go = lambda: cli.main(["landed", head, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),  # noqa: E731
                           "--state", str(world.tmp / "s"), "--push"])
    spec.write_text("- `x.one` [GAP] (#7) — the thing, edited by hand\n")
    assert go() == 1
    assert "x.md" in capsys.readouterr().err and rows()[-1]["step"] == "spec-clean" and rows()[-1]["ok"] is False
    assert _g(world.origin, "rev-parse", "integration") != head, "refused before the push"
    _g(world.tmp, "checkout", "--", "docs/contributor_manual/specs/h/x.md")
    other.write_text("- `y.one` [GAP] (#8) — dirty, and not named\n")
    (world.tmp / "unrelated.txt").write_text("b\n")
    assert go() == 0
    assert "[OK]" in spec.read_text() and "dirty" in other.read_text()


def test_a_fixes_line_naming_several_issues_closes_each_and_the_done_row_names_what_stayed_open(world, capsys):
    """Owner ruling: nothing is silently left. A row, not a close: an issue a landed commit cites with no Fixes line is named."""
    (world.seed / "m").write_text("6")
    _g(world.seed, "add", "m"), _g(world.seed, "commit", "-qm", "feat: m\n\nFixes #20, #21\nCloses #22 (see #30)\nPart of #23, see #31")
    head = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", head)
    journal.append("check", head=head, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    assert cli.main(["landed", head, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),
                     "--state", str(world.tmp / "s"), "--push"]) == 0
    closed = [c.split()[2] for c in world.gh_log.read_text().splitlines() if c.startswith("issue close")]
    assert closed == ["7", "20", "21", "22"]
    assert rows()[-1]["left_open"] == [23, 6116], "#7 has its Fixes line in the first commit; an issue only mentioned in prose is not cited"
    assert "left open: #23, #6116" in capsys.readouterr().out


def test_making_the_new_pinned_copy_waits_for_a_running_ladder(world, monkeypatch):
    """`pin` removes every other pinned worktree, which another lane's check may be reading: it takes the ladder's lock."""
    world.ready(), world.green()
    held = []
    real = landed.pin

    def probe(*a):
        with pytest.raises(BlockingIOError):
            with journal.Lock("ladder", wait=False):
                pass
        held.append(True)
        return real(*a)
    monkeypatch.setattr(landed, "pin", probe)
    assert world.go("--push") == 0 and held


def test_a_status_that_cannot_be_read_refuses_rather_than_counting_the_spec_clean(world, monkeypatch, capsys):
    """Review of range 5: a failed `git status` left the file looking clean, and the landing then edited it."""
    world.ready(), world.green()
    spec = world.tmp / "docs" / "contributor_manual" / "specs" / "h" / "x.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("- `x.one` [GAP] (#7) — the thing\n")
    (world.seed / "n").write_text("7")
    _g(world.seed, "add", "n"), _g(world.seed, "commit", "-qm", "feat: `x.one` built\n\nBehaviour: x.one\nFixes #7")
    head = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", head)
    journal.append("check", head=head, since=_g(world.engine, "rev-parse", "integration"), ok=True)
    assert cli.main(["landed", head, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"), "--state", str(world.tmp / "s"), "--push"]) == 1
    assert "could not be read" in capsys.readouterr().err and rows()[-1]["step"] == "spec-clean"
    assert _g(world.origin, "rev-parse", "integration") != head


def test_without_verdicts_the_store_under_state_that_holds_the_ready_is_used(world):
    """Real use 2026-11-02: `landed` needed --verdicts though `land` had it; it defaults to the verdict stores under --state."""
    world.ready(), world.green()
    store = world.tmp / "s" / "verdicts-lane.json"
    store.write_text(world.store.read_text())
    assert cli.main(["landed", world.sha, "--root", str(world.tmp), "--gh", str(world.tmp / "gh"), "--state", str(world.tmp / "s"), "--push"]) == 0
    assert any(r["step"] == "verdict" and "verdicts-lane.json" in r["detail"] for r in rows())


def test_the_jail_root_drops_a_local_edit_the_target_already_has_and_refuses_a_real_one(world, capsys):
    """Real use 2026-11-02: the jail root's harness.toml held a hand edit, so the fast-forward aborted. An edit equal to what
    lands is dropped; any other local edit refuses, never discarded."""
    world.ready(), world.green()
    root = world.wr / "root"
    (root / "g").write_text("a different local g")  # the landing brings g = "1"
    (root / "f").write_text("an edit the landing does not touch")
    assert world.go("--push") == 1
    assert next(r for r in rows() if r["step"] == "jail-root")["ok"] is False and "g" in capsys.readouterr().err
    assert (root / "g").read_text() == "a different local g", "a real edit is never discarded"
    (root / "g").write_text("1")  # what the landing brings, already there by hand
    assert world.go("--push") == 0, "with only an edit the target has, the rerun finishes"
    assert (root / "g").read_text() == "1" and (root / "f").read_text() == "an edit the landing does not touch"


def test_the_worker_is_run_from_slash_so_sudo_never_inherits_an_unreadable_cwd(monkeypatch):
    seen = {}

    def run(argv, **k):
        seen.update(k)
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(landed.subprocess, "run", run)
    landed.as_worker(types.SimpleNamespace(sudo="sudo", user="w", workroot="/wr"), "true")
    assert seen.get("cwd") == "/"


def test_a_failed_fetch_in_the_jail_root_refuses_with_a_row_and_never_merges_a_stale_fetch_head(world):
    """Review 2026-11-02: `fetch && ...; merge` merged the FETCH_HEAD an earlier fetch left, exited 0 and said fast-forwarded."""
    world.ready(), world.green()
    root = world.wr / "root"
    _g(root, "fetch", "-q", "origin", "integration")  # a stale FETCH_HEAD: the tip before this landing
    _g(root, "remote", "set-url", "origin", str(world.tmp / "gone.git"))
    before = _g(root, "rev-parse", "HEAD")
    assert world.go("--push") == 1
    r = next(r for r in rows() if r["step"] == "jail-root")
    assert r["ok"] is False and "fast-forwarded" not in r["detail"] and "done" not in [x["step"] for x in rows()]
    assert _g(root, "rev-parse", "HEAD") == before


def test_a_sweep_whose_patch_cannot_be_written_keeps_the_tree_and_alerts(world):
    """Review 2026-11-02 (#6204): `patch; remove --force` destroyed uncommitted work when the patch failed. Now the tree goes
    only after its patch is written; a failed one keeps the tree and is an alert row."""
    import time

    root = world.wr / "root"
    wt = world.wr / "wt-lost"
    _g(root, "worktree", "add", "-q", "-b", "lost", str(wt), "HEAD")
    (wt / "precious").write_text("uncommitted work")
    removed = world.wr / "removed-is-a-file"
    removed.write_text("")  # mkdir -p fails: the patch cannot be written
    sh = lambda script: subprocess.run(["sh", "-c", f"cd {world.wr} && {script}"], capture_output=True, text=True)  # noqa: E731
    done = landed.sweep(sh, "root", "origin/integration", 36, str(removed), set(), now=time.time() + 37 * 3600)
    assert wt.is_dir() and (wt / "precious").read_text() == "uncommitted work", "the tree and its work are kept"
    assert len(done) == 1 and "kept, no patch" in done[0]
    (a,) = [r for r in journal.read() if r["event"] == "alert"]
    assert a["step"] == "sweep" and str(wt) in a["what"]
