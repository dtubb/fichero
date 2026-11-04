"""Manager 2026-11-04 (alerts 315, 316): the LaunchAgent loop took an old build-order milestone the hand loop had long skipped and started
a worker in a fresh worktree on steps another lane had landed. The loop ticks only the lanes [loop].only names, takes milestones only when
[loop].feed_milestones is on, and a jail-user command never runs from the caller's working directory."""
from __future__ import annotations

import plistlib
import subprocess
import types

import pytest

from fichero_builder import journal, queue, work
from test_queue_verb import Fake


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "ONLY", [()])
    (tmp_path / "b").write_text("brief")
    return tmp_path


def test_the_loop_ticks_only_the_lanes_it_names(state):
    queue.add("mine", "/w/mine", "1.1", str(state / "b"), [7])
    queue.add("old-milestone", "/w/old", "0.3", str(state / "b"), [8])
    queue.ONLY[0] = ("mine",)
    fake = Fake()
    queue.tick(fake.procs, {}, workers_n=2, push=False, out=lambda s: None)
    assert [s[0] for s in fake.starts] == ["mine"], "a lane the loop does not name is never started"


def test_milestones_are_taken_only_when_feed_milestones_is_on(state):
    fake, asked = Fake(), []
    fake.procs.next_milestone = lambda taken: asked.append(taken)
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=lambda s: None, feed_milestones=False)
    assert asked == [], "off: no milestone is taken"
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=lambda s: None, feed_milestones=True)
    assert asked, "on: the build order is asked"


def test_a_jail_command_runs_from_the_workroot_never_the_callers_cwd_and_the_plist_works_from_the_state_dir(state, monkeypatch):
    seen = {}
    monkeypatch.setattr(work, "owner_tree", lambda a: False)
    monkeypatch.setattr(work, "_jail", lambda a: types.SimpleNamespace(sudo="/usr/bin/sudo", user="wuser", workroot=str(state / "wr")))
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: (seen.update(k), subprocess.CompletedProcess(argv, 0, "", ""))[1])
    work.as_worker(types.SimpleNamespace(), "true")
    assert seen["cwd"] == str(state / "wr")
    monkeypatch.undo()
    monkeypatch.setattr(journal, "STATE", state / "s")
    loop = plistlib.loads(queue.launch_agents(state, state / "la", state=state / "s")[0].read_bytes())
    assert loop["WorkingDirectory"] == str(state / "s"), "the owner's state dir, never a checkout the jail user cannot read"
