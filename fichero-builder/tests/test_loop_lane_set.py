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
    loop = plistlib.loads(queue.launch_agents(state, state / "la", state=state / "s", branch="main")[0].read_bytes())
    assert loop["WorkingDirectory"] == str(state / "s"), "the owner's state dir, never a checkout the jail user cannot read"


def _waiting_lanes(state, states_, pre="w", queued=True):
    """One lane per state, its cursor step in that state with a live session; plus one queued lane q."""
    handles = {}
    for i, st in enumerate(states_):
        queue.add(f"{pre}{i}", f"/w/{pre}{i}", "1.1", str(state / "b"), [i])
        lanes = queue.load()
        next(x for x in lanes if x["id"] == f"{pre}{i}")["steps"][0].update(state=st, head=f"h{i}")
        queue.save(lanes)
        handles[f"{pre}{i}"] = object()
    if queued:
        queue.add("q", "/w/q", "1.1", str(state / "b"), [99])
    return handles


def test_a_step_waiting_for_its_check_or_the_train_holds_no_writer_so_the_next_queued_step_starts(state, monkeypatch):
    """local.flow.writers-are-not-capped-by-checks: [loop].lanes counts writers (sent, fixing, blocked, red); a step that is done,
    checking, reviewing or waiting for the train holds none."""
    monkeypatch.setattr(queue, "MAX_IN_FLIGHT", [0])
    monkeypatch.setattr(queue, "IN_FLIGHT_SAID", [False])
    handles = _waiting_lanes(state, ["done-not-landed", "said-done"])
    assert queue._working(handles) == 0
    fake = Fake()
    fake.procs.alive = lambda h: True
    queue.tick(fake.procs, handles, workers_n=2, push=False, out=lambda s: None)
    assert [s[0] for s in fake.starts] == ["q"], "two lanes past DONE, lanes = 2: q still starts"
    assert queue._working(_waiting_lanes(state, ["sent", "red", "fixing", "blocked"], pre="x", queued=False)) == 4, "writers keep their slot"


def test_no_step_starts_past_max_in_flight_and_one_row_says_so(state, monkeypatch):
    monkeypatch.setattr(queue, "MAX_IN_FLIGHT", [2])
    monkeypatch.setattr(queue, "IN_FLIGHT_SAID", [False])
    handles = _waiting_lanes(state, ["train", "train"])
    fake = Fake()
    fake.procs.alive = lambda h: True
    for _ in range(2):
        queue.tick(fake.procs, handles, workers_n=5, push=False, out=lambda s: None)
    assert not [s for s in fake.starts if s[0] == "q"]
    assert len([r for r in journal.read() if r.get("state") == "in-flight-cap"]) == 1
