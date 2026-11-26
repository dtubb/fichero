"""local.check.stale-base-guards (#6589): a shrink-only allowlist entry that "no longer occurs" on a lane's OLDER base, though
integration still needs it, is judged on head merged with the current base, not on the stale base."""
import subprocess
from pathlib import Path

import pytest

from fichero_builder import check_tool, journal

STALE = "check_routes: allowlisted route /b no longer occurs — remove it (shrink-only)."


def g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    for k, v in {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    repo = tmp_path / "repo"
    repo.mkdir()
    g(repo, "init", "-q", "-b", "integration")
    (repo / "a.py").write_text("a\n")
    g(repo, "add", "."), g(repo, "commit", "-qm", "base")
    old = g(repo, "rev-parse", "HEAD")
    (repo / "b.py").write_text("b\n")  # integration gains the code its allowlist entry names
    g(repo, "add", "."), g(repo, "commit", "-qm", "integration moves on")
    tip = g(repo, "rev-parse", "HEAD")
    g(repo, "checkout", "-qb", "lane", old)
    (repo / "c.py").write_text("c\n")
    g(repo, "add", "."), g(repo, "commit", "-qm", "the lane's batch, on the old base")
    head = g(repo, "rev-parse", "HEAD")
    pinned = tmp_path / "pinned"
    g(repo, "worktree", "add", "-q", "--detach", str(pinned), tip)
    # the fake guard: integration's allowlist names b.py; a tree without it says the entry no longer occurs
    monkeypatch.setattr(check_tool, "guards", lambda tree, cfg: {"ok": True, "reason": "", "results": [{"name": "check_routes", "ok": True}]}
                        if (Path(tree) / "b.py").exists() else
                        {"ok": False, "reason": "", "results": [{"name": "check_routes", "ok": False, "stdout_tail": STALE}]})
    return repo, old, tip, head, pinned


def _run(world, tree_head=None):
    repo, old, tip, head, pinned = world
    cfg = check_tool.Config()
    tree = check_tool._scratch_tree(repo, tree_head or head, pinned, cfg)
    try:
        return check_tool.guards_on_current_base(repo, old, tree_head or head, pinned, cfg, tree)
    finally:
        check_tool.drop_tree(repo, tree)


def test_a_stale_allowlist_red_on_an_older_base_is_green_on_the_merge_with_the_current_base(world):
    r = _run(world)
    assert r["ok"] and r["stale_base"] and "no longer occur" in r["reason"] and world[2][:9] in r["reason"]
    assert [x["state"] for x in journal.read() if x["event"] == "check"] == ["stale-base-guards"]


def test_a_lane_already_on_the_current_base_keeps_its_red(world, monkeypatch):
    repo, old, tip, head, pinned = world
    g(repo, "checkout", "-q", "lane"), g(repo, "rebase", "-q", tip)
    monkeypatch.setattr(check_tool, "guards", lambda tree, cfg: {"ok": False, "reason": "", "results": [{"name": "check_routes", "ok": False, "stdout_tail": STALE}]})
    assert not _run(world, g(repo, "rev-parse", "HEAD"))["ok"]


def test_a_red_of_another_kind_is_never_re_judged(world, monkeypatch):
    monkeypatch.setattr(check_tool, "guards", lambda tree, cfg: {"ok": False, "reason": "", "results": [{"name": "check_x", "ok": False, "stdout_tail": "a real red"}]})
    r = _run(world)
    assert not r["ok"] and not r.get("stale_base")
