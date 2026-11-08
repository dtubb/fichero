"""dev-workflows.run.loop-survives (manager 2026-11-03): one lane's exception is that lane's error row, never the loop's
death, and the loop's own detached tree follows origin after each landing so its code is never behind the rules it reads."""
from __future__ import annotations

import subprocess

import pytest

from fichero_builder import journal, queue
from test_queue_verb import Fake, lane, run, steps


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    return tmp_path


def _rows(state_):
    return [r for r in journal.read() if r.get("state") == "lane-error"]


def test_a_chain_that_raises_any_exception_is_an_error_alert_and_the_loop_goes_on(state):
    lane(state)
    fake = Fake()

    def chain(lane_, step, stage):
        raise AttributeError("'list' object has no attribute 'partition'")
    fake.procs.chain = chain
    assert run(fake) == 0, "the loop returned; nothing propagated"
    (row,) = _rows(state)
    assert row["lane"] == "m1" and row["step"] == "1.1" and "AttributeError" in row["detail"] and "Traceback" in row["detail"]
    (a,) = [r for r in journal.read() if r["event"] == "alert"]
    assert "AttributeError" in a["what"] and steps()["1.1"]["state"] == "blocked"


def test_a_lane_whose_tick_raises_is_a_row_and_the_other_lanes_still_tick(state, monkeypatch):
    lane(state)
    queue.add("m2", "/w/m2", "2.1", str(state / "b1.1"), [9])
    real, seen = queue.tick_lane, []

    def tick_lane(ln, *a, **k):
        seen.append(ln["id"])
        if ln["id"] == "m1":
            raise TypeError("a bug in this lane's tick")
        return real(ln, *a, **k)
    monkeypatch.setattr(queue, "tick_lane", tick_lane)
    fake, said = Fake(), []
    queue.tick(fake.procs, {}, workers_n=2, push=False, out=said.append)
    assert seen == ["m1", "m2"] and [r["lane"] for r in _rows(state)] == ["m1"] and "TypeError" in _rows(state)[0]["detail"]
    assert any("m1: lane error" in s for s in said) and ("m2", "2.1", 0) in [(x[0], x[1], 0) for x in fake.starts], "m2 started"


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_the_loops_detached_clean_tree_follows_origin_and_a_branch_or_a_dirty_tree_is_left(state):
    origin, seed, live = state / "origin.git", state / "seed", state / "live"
    _git(state, "init", "-q", "--bare", "-b", "integration", str(origin))
    _git(state, "clone", "-q", str(origin), str(seed))
    (seed / "f").write_text("1\n")
    _git(seed, "add", "f"), _git(seed, "commit", "-qm", "one"), _git(seed, "push", "-q", "origin", "HEAD:integration")
    _git(state, "clone", "-q", str(origin), str(live))
    _git(live, "checkout", "-q", "--detach")
    (seed / "f").write_text("2\n")
    _git(seed, "commit", "-qam", "two"), _git(seed, "push", "-q", "origin", "HEAD:integration")
    new = _git(seed, "rev-parse", "HEAD")
    git = ["git", "-C", str(live)]
    assert queue.refresh_live(live, "integration", git=git) == f"moved to {new[:9]}" and _git(live, "rev-parse", "HEAD") == new
    assert queue.DRAIN[0] is True, "no chain starts on the old code before the re-exec (2026-11-04)"
    queue.DRAIN[0] = False
    assert [r["state"] for r in journal.read() if r["event"] == "loop"] == ["live-tree"]
    (seed / "g").write_text("g\n")  # a hot patch of f rides a landing that leaves f alone (manager 2026-11-07 21:37)
    _git(seed, "add", "g"), _git(seed, "commit", "-qm", "three"), _git(seed, "push", "-q", "origin", "HEAD:integration")
    (live / "f").write_text("local\n")
    three = _git(seed, "rev-parse", "HEAD")
    assert queue.refresh_live(live, "integration", git=git) == f"moved to {three[:9]}, carrying the hot patch of f"
    assert (live / "g").read_text() == "g\n" and (live / "f").read_text() == "local\n", "the new data is there, the patch kept"
    queue.DRAIN[0] = False
    (seed / "f").write_text("4\n")  # a landing that changes the patched file: left, said
    _git(seed, "commit", "-qam", "four"), _git(seed, "push", "-q", "origin", "HEAD:integration")
    assert queue.refresh_live(live, "integration", git=git) == "dirty: left" and _git(live, "rev-parse", "HEAD") == three
    assert "changes the hot-patched f" in [r for r in journal.read() if r["event"] == "loop"][-1]["detail"]
    _git(live, "checkout", "-q", "--", "f"), _git(live, "checkout", "-q", "-b", "mine")
    assert queue.refresh_live(live, "integration", git=git) == "on a branch: left"



def test_a_step_blocked_by_rules_newer_than_its_code_is_retried_once_when_the_loop_starts_current(state):
    """Manager 2026-11-04 (10:16-10:50): three chains started on the old code after a landing added harness.toml keys, blocked on
    'unknown keys', and stayed blocked after the re-exec until a person retried them."""
    queue.add("ext", "/w/ext", "b1", str(state / "b1.1"), [7], kind="external")
    queue.add("w1", "/w/w1", "1.1", str(state / "b1.1"), [8])
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", head="a" * 40, why="ValueError: harness.toml [check]: unknown keys ['generated']")
    lanes[1]["steps"][0].update(state="blocked", why="red at pytest")
    queue.save(lanes)
    assert queue.retry_rules_blocked(lambda s: None) == ["ext"]
    rows = [r for r in journal.read() if r["event"] == "queue" and r.get("state") == "rules-retry"]
    assert [r["lane"] for r in rows] == ["ext"], "only the rules-newer block, never a real red"
    assert queue.load()[0]["steps"][0]["state"] == "done" and queue.load()[1]["steps"][0]["state"] == "blocked"
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", why="the check could not run: rules file refused: harness.toml: unknown keys")
    queue.save(lanes)
    assert queue.retry_rules_blocked(lambda s: None) == [], "once per head: a second block on the same head stays"
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", head="b" * 40, why="REFUSED: the rules file cannot run the loop: x")
    queue.save(lanes)
    assert queue.retry_rules_blocked(lambda s: None) == [], "only the two spec'd reasons (review -89)"



def test_the_loop_retries_rules_blocked_steps_when_it_starts(state, monkeypatch):
    called = []
    monkeypatch.setattr(queue, "retry_rules_blocked", lambda out=print: called.append(True) or [])
    (state / "s").mkdir(parents=True, exist_ok=True)
    queue.run(Fake().procs, workers_n=1, push=False, once=True, heartbeat=True, out=lambda s: None)
    assert called == [True], "a heartbeat loop (the verb, a re-exec included) retries them at its start"



def test_the_loop_records_its_own_checkout_as_the_live_root_when_it_starts(state, monkeypatch):
    """Review -92: presubmit's pinned copy is <state>/live-root; the loop writes it at its start."""
    monkeypatch.setattr(queue, "retry_rules_blocked", lambda out=print: [])
    (state / "s").mkdir(parents=True, exist_ok=True)
    procs = Fake().procs
    procs.root = str(state)
    queue.run(procs, workers_n=1, push=False, once=True, heartbeat=True, out=lambda s: None)
    assert (journal.STATE / "live-root").read_text().strip() == str(state.resolve())
