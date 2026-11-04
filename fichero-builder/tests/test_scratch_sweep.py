"""dev-workflows.run.scratch-sweep (manager 2026-11-03): the ladders' old scratch dirs leave the workroot by a list, then a separate
delete of exactly that list; never a new dir, a held one, or anything but a scratch prefix."""
from __future__ import annotations

import getpass
import os
import subprocess
import time

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, scratch


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    wr, repo = tmp_path / "wr", tmp_path / "engine"
    wr.mkdir(), repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "b"], check=True)
    (tmp_path / "harness.toml").write_text(f'[jail]\nuser = "{getpass.getuser()}"\nworkroot = "{wr}"\n[check]\nengine_repo = "{repo}"\n')
    old = time.time() - 7 * 3600

    def make(name, age=old, tree=False):
        p = wr / name
        if tree:
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", "-q", str(p)], check=True)
        else:
            p.mkdir()
            (p / "f").write_text("x" * 2048)
        os.utime(p, (age, age))
        return p
    return tmp_path, wr, repo, make


def test_the_list_step_names_only_old_unheld_scratch_dirs_and_deletes_nothing(world, monkeypatch):
    root, wr, repo, make = world
    keep = [make("bt-h3"), make("check-base-new", age=time.time()), make("derived"), make("check-home-held")]
    gone = [make("check-base-aaaa1111"), make("check-home-bbbb2222"), make("check-tree-cccc3333", tree=True)]
    monkeypatch.setattr(scratch, "_held", lambda: f"/usr/bin/python -m pytest {wr / 'check-home-held'}/x")
    f, n, kb = scratch.list_step(root)
    assert sorted(f.read_text().split()) == sorted(str(p) for p in gone) and n == 3 and kb > 0
    assert all(p.exists() for p in keep + gone), "listing deletes nothing"


def test_the_delete_step_removes_exactly_the_list_rechecked_and_says_what_it_freed(world, monkeypatch, capsys):
    root, wr, repo, make = world
    a, b, t = make("check-base-aaaa1111"), make("check-home-bbbb2222"), make("check-tree-cccc3333", tree=True)
    other = make("check-base-dddd4444")  # old, but not on the list
    monkeypatch.setattr(scratch, "_held", lambda: "")
    listed = journal.STATE / "l.txt"
    listed.parent.mkdir(parents=True, exist_ok=True)
    listed.write_text(f"{a}\n{b}\n{t}\n{wr.parent / 'outside'}\n")
    os.utime(b, None)  # touched since the list: too new now
    assert cli.main(["sweep-scratch", "--delete", str(listed), "--root", str(root), "--state", str(journal.STATE)]) == 1, "something was left"
    out = capsys.readouterr().out
    assert not a.exists() and not t.exists() and b.exists() and other.exists()
    assert "removed 2 scratch dir(s)" in out and "too new now" in out and "not a scratch dir directly under the workroot" in out
    assert str(t) not in subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout, "the check tree left git too"
    row = [r for r in journal.read() if r["event"] == "sweep-scratch"][-1]
    assert row["state"] == "deleted" and row["removed"] == 2 and row["kib"] > 0


def test_the_loop_runs_list_then_delete_at_most_every_six_hours(world, monkeypatch):
    root, wr, repo, make = world
    make("check-base-aaaa1111")
    monkeypatch.setattr(scratch, "_held", lambda: "")
    scratch.when_idle(root)
    make("check-base-eeee5555")
    scratch.when_idle(root)
    assert [r["state"] for r in journal.read() if r["event"] == "sweep-scratch"] == ["listed", "deleted"], "the second tick is inside the six hours"
    assert not (wr / "check-base-aaaa1111").exists() and (wr / "check-base-eeee5555").exists()
