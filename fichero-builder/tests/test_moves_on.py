"""builder-console.step.moves-on (#6646): a final step moves the lane on and the row names the step left and the step taken."""
from __future__ import annotations

import test_queue_verb as tq
from fichero_builder import journal, queue

Fake, _feeding, lane, run, steps = tq.Fake, tq._feeding, tq.lane, tq.run, tq.steps
state = tq.state  # the fixture


def _rows():
    return [(r["lane"], r["left"], r["taken"]) for r in journal.read() if r["event"] == "moves-on"]


def test_landing_step_one_of_two_sends_step_two_and_says_so(state):
    lane(state)
    fake = Fake()
    assert run(fake) == 0
    assert fake.sent == ["brief 1.2"] and _rows() == [("m1", "1.1", "1.2"), ("m1", "1.2", "-")]


def test_a_closed_out_step_does_not_hold_the_lane(state, monkeypatch):
    """Step 1.1 blocked for 60 h, asked once already: the stale watch files the residue, closes it out, and step 1.2 is sent."""
    lane(state)
    ln = queue.load()
    s = ln[0]["steps"][0]
    s.update(state="blocked", why="needs a decision", entered_at=1000.0, blocked_at=1000.0, stale_n=1)
    queue.save(ln)
    monkeypatch.setattr(queue, "_now", lambda: 1000.0 + 60 * 3600)
    monkeypatch.setattr(queue, "BLOCKED_H", [10_000.0])
    monkeypatch.setattr(queue, "_gh_quiet", lambda gh, args, cwd=None: "")
    fake = Fake()
    assert run(fake) == 0
    assert steps()["1.1"]["state"] == "closed-out" and ("m1", "1.1", "1.2") in _rows()
    assert fake.sent == [] and fake.starts[0][1] == "1.2"


def test_the_last_step_landed_starts_the_next_milestones_first_step(state):
    fake = Fake()
    _feeding(fake, state, ["ma", "mb"])
    assert queue.run(fake.procs, workers_n=1, push=True, lanes_n=1, out=lambda s: None) == 0
    assert ("mb", "ma ma.1", "mb.1") in _rows()
