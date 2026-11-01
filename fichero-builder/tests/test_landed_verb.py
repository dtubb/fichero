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
        f'[check]\nengine_repo = "{engine}"\n[land]\nbranch = "integration"\nboundary = []\npinned_dir = "{pinned_dir}"\n'
        f'[jail]\nuser = "wuser"\nworkroot = "{wr}"\n')
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
    journal.append("check", head=second, ok=True)
    assert cli.main(["landed", second, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),
                     "--state", str(world.tmp / "s"), "--push"]) == 0
    branches = _g(world.engine, "branch", "--list", "pinned-*", "--format=%(refname:short)").split()
    assert branches == [f"pinned-{second[:7]}"]
    assert not (world.pinned_dir / f"pinned-{first[:7]}").exists() and (world.pinned_dir / f"pinned-{second[:7]}").is_dir()


def test_scratch_worktrees_of_the_work_rows_for_that_sha_are_removed_as_the_worker(world):
    world.ready(), world.green()
    wt = world.wr / "wt-n1"
    wt.mkdir()
    (wt / "x").write_text("x")
    journal.append("work", name="n1", issues=[7], step="fetch", ok=True, detail=world.sha, worktree=str(wt))
    assert world.go("--push") == 0
    assert not wt.exists()
    assert any(r["step"] == "scratch" and str(wt) in r["detail"] for r in rows())


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
    world.ready(), world.green()
    (world.seed / "j").write_text("4")
    _g(world.seed, "add", "j"), _g(world.seed, "commit", "-qm", "docs: j\n\nAlready built: #9 tests/test_j.py::test_j\nPart of #6116")
    second = _g(world.seed, "rev-parse", "HEAD")
    _g(world.engine, "fetch", "-q", str(world.seed), "+refs/heads/lane:refs/heads/work-n1")
    land_tool.write_verdict(world.store, world.engine, "integration", second)
    journal.append("check", head=second, ok=True)
    go = lambda *x: cli.main(["landed", second, "--root", str(world.tmp), "--verdicts", str(world.store), "--gh", str(world.tmp / "gh"),  # noqa: E731
                              "--state", str(world.tmp / "s"), "--push", *x])
    assert go() == 0
    calls = world.gh_log.read_text().splitlines()
    assert calls[0] == f"issue close 7 --comment landed on integration at {second[:7]}"
    assert f"issue comment 6116 --body landed on integration at {second[:7]}" in calls and calls.count(f"issue comment 6116 --body landed on integration at {second[:7]}") == 2
    assert any(c.startswith("issue comment 9 --body already built; the test that proves it: tests/test_j.py::test_j") for c in calls)
    assert "issue edit 9 --add-label needs-your-test" in calls
    assert rows()[-1]["issues"] == [7, 9, 6116]


def test_no_issues_skips_gh_but_the_done_row_still_names_the_issues(world):
    world.ready(), world.green()
    assert world.go("--push", "--no-issues") == 0
    assert not world.gh_log.exists() and rows()[-1]["issues"] == [7, 6116]
    assert "--no-issues" in next(r["detail"] for r in rows() if r["step"] == "issues")
