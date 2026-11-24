"""dev-workflows.queue.batch.* and queue.session.*: one-issue briefs join the lane's next unstarted step as parts; parts a worker
left are re-queued alone; the lane's live session carries over to the next step unless a stated reason ends it. Fakes, as in
test_queue_verb."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import console, journal, queue
from test_queue_verb import Fake


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "CFG", dict(queue.CFG))
    for n in ("a", "b", "c", "d", "e"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n')
    return tmp_path


def add(state, step, n, issue, **k):
    queue.add("m1", "/w/m1", step, str(state / f"b{n}"), [issue], batch=True, **k)


def steps():
    return queue.load()[0]["steps"]


def test_a_one_issue_brief_joins_the_next_unstarted_step_as_a_part(state):
    add(state, "s1", "a", 7)
    add(state, "s2", "b", 9)
    (s,) = steps()
    assert s["step"] == "s1" and s["issues"] == [7, 9]
    text = Path(s["brief"]).read_text()
    assert text.index("## PART 1 (#7)") < text.index("brief a") < text.index("## PART 2 (#9)") < text.index("brief b")


def test_alone_and_a_full_batch_and_a_started_step_each_make_a_new_step(state):
    queue.CFG["batch_max"] = 2
    add(state, "s1", "a", 7)
    add(state, "s2", "b", 9)
    add(state, "s3", "c", 10)  # the batch has 2 of 2
    queue.add("m1", "/w/m1", "s4", str(state / "bd"), [11], batch=True, alone=True)
    assert [(s["step"], s["issues"]) for s in steps()] == [("s1", [7, 9]), ("s3", [10]), ("s4", [11])]
    lanes = queue.load()
    lanes[0]["steps"][0]["state"], lanes[0]["cursor"], lanes[0]["steps"][1]["state"] = "landed", 1, "sent"
    queue.save(lanes)
    add(state, "s5", "e", 12)
    assert [(s["step"], s["issues"]) for s in steps()][1:] == [("s3", [10]), ("s4", [11, 12])], "a sent step is never changed: the next unstarted one takes it"


def test_without_batch_the_old_one_step_per_add_stands_and_a_repeated_issue_is_not_a_part(state):
    queue.add("m1", "/w/m1", "s1", str(state / "ba"), [7])
    queue.add("m1", "/w/m1", "s2", str(state / "bb"), [9])
    assert len(steps()) == 2
    add(state, "s3", "c", 7)
    assert len(steps()) == 3, "issue 7 is already in s1: it is not appended to it again"


def test_queue_add_batches_by_default_and_alone_keeps_one_step(state, monkeypatch, capsys):
    from fichero_builder import work_store, work_tree
    monkeypatch.setattr(work_store, "open_store", lambda kind: None)
    monkeypatch.setattr(work_tree, "milestone_of", lambda store, issues: "")
    base = ["queue", "add", "--lane", "m1", "--worktree", "/w/m1", "--state", str(state / "s"), "--root", str(state)]
    assert cli.main(base + ["--step", "s1", "--brief", str(state / "ba"), "--issues", "7"]) == 0
    assert cli.main(base + ["--step", "s2", "--brief", str(state / "bb"), "--issues", "9"]) == 0
    assert "joined m1 s1 as part 2" in capsys.readouterr().out
    assert cli.main(base + ["--step", "s3", "--brief", str(state / "bc"), "--issues", "10", "--alone"]) == 0
    assert [(s["step"], s["issues"]) for s in steps()] == [("s1", [7, 9]), ("s3", [10])]


def test_batch_max_and_session_come_from_the_queue_table(state):
    (state / "harness.toml").write_text('[queue]\nbatch_max = 2\nsession = "step"\nsession_max_context = 0.5\nsession_max_steps = 3\n')
    queue.load_cfg(state)
    assert queue.CFG == {"batch_max": 2, "session": "step", "session_max_context": 0.5, "session_max_steps": 3}
    (state / "harness.toml").write_text('[queue]\nsession_max_step = 3\n')
    with pytest.raises(ValueError, match="session_max_step"):
        queue.load_cfg(state)
    (state / "harness.toml").write_text('[queue]\nsession = "everywhere"\n')
    with pytest.raises(ValueError, match="session"):
        queue.load_cfg(state)


def test_parts_the_worker_left_are_requeued_alone_as_the_lanes_next_step(state):
    add(state, "s1", "a", 7)
    add(state, "s2", "b", 9)
    add(state, "s3", "c", 10)
    queue.add("m1", "/w/m1", "s9", str(state / "bd"), [11], batch=True, alone=True)
    fake = Fake()
    row = fake.row
    fake.row = lambda lane: ({**r, "left": [{"part": 2, "why": "needs a design call"}]} if (r := row(lane)) and lane["cursor"] == 0 else r)
    fake.procs.row = fake.row
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    by = {s["step"]: s for s in steps()}
    assert by["s1"]["state"] == "landed" and by["s1"]["issues"] == [7, 10], "the landed step names only the parts that were done"
    left = by["s1-left"]
    assert left["issues"] == [9] and left["state"] in ("landed", "queued")
    text = Path(left["brief"]).read_text()
    assert "brief b" in text and "brief a" not in text and "brief c" not in text
    assert [s["step"] for s in steps()][:2] == ["s1", "s1-left"]


def two_steps(state):
    queue.add("m1", "/w/m1", "s1", str(state / "ba"), [7])
    queue.add("m1", "/w/m1", "s2", str(state / "bb"), [8])


def run_two(state, row_extra=None, model=""):
    two_steps(state)
    fake = Fake()
    fake.procs.model_of = lambda lane: model
    if row_extra is not None:
        fake.row = lambda lane: {"moved": True, **row_extra} if lane["seq"] in fake.seqs else None
        fake.procs.row = fake.row
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    return fake


def session_rows():
    return [(r["step"], r["state"], r["detail"]) for r in journal.read() if r.get("event") == "queue" and r.get("state", "").startswith("session-")]


def test_the_next_brief_goes_into_the_same_session_and_one_row_says_why(state):
    fake = run_two(state)
    assert len(fake.starts) == 1 and fake.sent == ["brief b"]
    assert session_rows() == [("s1", "session-kept", "step 1 of at most 5 in this session; context unknown")]
    assert steps()[1]["session"] == "kept" and steps()[0]["session"] == "fresh"


@pytest.mark.parametrize("cfg,extra,why", [
    ({"session": "step"}, None, "session = step"),
    ({}, {"context": 150000, "window": 200000}, "context 75% is over 70%"),
    ({"session_max_steps": 1}, None, "5 steps"),
    ({}, {"model": "opus", "context": 10, "window": 200000}, "model changed"),
])
def test_a_fresh_session_starts_when_the_reason_holds(state, cfg, extra, why, monkeypatch):
    queue.CFG.update(cfg)
    if "session_max_steps" in cfg:
        why = "1 steps"
    fake = run_two(state, extra, model="sonnet" if extra and "model" in extra else "")
    assert len(fake.starts) == 2 and fake.sent == []
    ((step, kind, detail),) = session_rows()
    assert (step, kind) == ("s1", "session-fresh") and why in detail
    assert steps()[1]["session"] == "fresh"


def test_a_gone_session_is_a_fresh_one_with_its_own_row(state):
    two_steps(state)
    fake = Fake()
    fake.alive_now = True
    orig = fake.chain

    def chain(lane, step, stage):
        r = orig(lane, step, stage)
        fake.alive_now = False
        return r
    fake.procs.chain = chain
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    assert any(k == "session-fresh" and "gone" in d for _, k, d in session_rows())


def test_the_lanes_steps_on_the_console_carry_their_parts_and_session(state):
    add(state, "s1", "a", 7)
    add(state, "s2", "b", 9)
    lanes = queue.load()
    lanes[0]["steps"][0]["session"] = "kept"
    got = console.steps_on_origin(lanes[0], "f" * 40)
    assert got[0]["parts"] == [7, 9] and got[0]["session"] == "kept"


def test_a_part_number_the_brief_lacks_blocks_the_step_before_anything_is_checked_or_landed(state):
    add(state, "s1", "a", 7)
    fake = Fake()
    row = fake.row
    fake.row = lambda lane: ({**r, "left": [{"part": 1, "why": "x"}]} if (r := row(lane)) else r)
    fake.procs.row = fake.row
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    assert steps()[0]["state"] == "blocked" and "does not have" in steps()[0]["why"]
    assert fake.landed_calls == [], "nothing was landed or pushed"


def test_a_managed_lanes_worker_is_stopped_when_its_last_step_lands(state):
    add(state, "s1", "a", 7)
    lanes = queue.load()
    lanes[0]["fresh"] = True
    queue.save(lanes)
    fake = Fake()
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    assert steps()[0]["state"] == "landed"
    handles = {"m1": "h"}
    lane = queue.load()[0]
    lane["cursor"] = len(lane["steps"])
    queue.end_session(lane, lane["steps"][0], handles, fake.procs)
    assert handles == {} and fake.stops.count("m1") >= 1 and lane["feed"] == ""


def test_a_part_joined_while_the_tick_holds_its_copy_of_the_lane_survives_the_ticks_store(state):
    add(state, "s1", "a", 7)
    add(state, "s2", "b", 9)  # the lane's cursor step s1 is the one joined; make a second step to join to
    queue.add("m1", "/w/m1", "s3", str(state / "bc"), [10], batch=True, alone=True)
    lanes = queue.load()
    lanes[0]["cursor"], lanes[0]["steps"][0]["state"] = 1, "landed"
    queue.save(lanes)
    held = queue.load()[0]  # the tick's copy, taken before the add
    queue.add("m1", "/w/m1", "s4", str(state / "bd"), [11], batch=True)
    assert queue.store(held)
    assert next(s for s in steps() if s["step"] == "s3")["issues"] == [10, 11]
