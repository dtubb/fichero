"""local.train.*: the queue holds green steps in state `train`, runs one train over them, lands the cleared ones in order and
sends the culprit or the conflicting step back. Processes are fakes."""
from __future__ import annotations

import pytest

from fichero_builder import journal, queue, train
from test_queue_verb import Fake


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n')
    clock = Clock()
    monkeypatch.setattr(queue, "_now", clock)
    monkeypatch.setattr(queue, "TRAIN", [train.Cfg()])
    monkeypatch.setattr(queue, "TRAIN_SIZE", [0])
    return tmp_path, clock


class Trained:
    """A fake loop with one single-step lane per name; `bad` heads fail swift-tests, `conflict` heads do not merge."""

    def __init__(self, tmp, clock, names, bad=(), conflict=(), cfg=None):
        for n in names:
            (tmp / f"b{n}").write_text(f"brief {n}")
            queue.add(f"l{n}", f"/w/l{n}", n, str(tmp / f"b{n}"), [int(n)])
        queue.TRAIN[0] = cfg or train.Cfg()
        self.fake, self.bad, self.conflict, self.rungs, self.trains = Fake(), set(bad), set(conflict), [], []
        self.fake.procs.train_run = self.run_train
        self.fake.procs.sleep = lambda s: setattr(clock, "t", clock.t + 600)  # ten minutes a tick
        self.fake.chain = self.chain
        self.fake.procs.chain = self.chain

    def chain(self, lane, step, stage):
        stage("checking"), stage("reviewing")
        return {"ok": True, "head": "h" + step["step"], "why": "", "findings": ""}

    def merge(self, heads):
        return "+".join(h for h in heads if h not in self.conflict), {h: f"conflict in {h}" for h in heads if h in self.conflict}

    def rung(self, name, cand):
        self.rungs.append((name, cand))
        fixed = any("merge train" in m for m in self.fake.sent)  # the worker fixed the culprit once it was told
        hit = [h for h in cand.split("+") if h in self.bad and name == "swift-tests" and not fixed]
        return not hit, f"{name} failed: {hit}" if hit else "ok"

    def run_train(self, spec, tid):
        self.trains.append([x["key"] for x in spec])
        return train.run_train(spec, merge=self.merge, rung=self.rung, rungs_for=lambda hs: ["build", "swift-tests", "unit"], tid=tid)

    def go(self, n=4):
        return queue.run(self.fake.procs, workers_n=n, push=True, out=lambda s: None)


def states():
    return {x["id"]: x["steps"][0]["state"] for x in queue.load()}


def landed_rows():
    return [r for r in journal.read() if r["event"] == "queue" and r.get("state") == "landed"]


def test_four_green_steps_land_together_after_one_swift_run(world):
    t = Trained(*world, ["1", "2", "3", "4"])
    assert t.go() == 0
    assert set(states().values()) == {"landed"}
    assert [h for h, _p in t.fake.landed_calls] == ["h1", "h2", "h3", "h4"], "in the order they entered the train"
    assert [n for n, _c in t.rungs] == ["build", "swift-tests", "unit"], "each rung once for the four steps"
    assert len(t.trains) == 1 and t.trains[0] == ["l1/1", "l2/2", "l3/3", "l4/4"]
    (row,) = [r for r in journal.read() if r["event"] == "train"]
    assert row["steps"] == t.trains[0] and row["result"] == "green" and row["candidate"] == "h1+h2+h3+h4" and row["rungs"]
    assert all(row["id"] in r["detail"] for r in landed_rows()) and len(landed_rows()) == 4, "one row per step naming the train"


def test_a_red_train_of_four_lands_three_and_sends_the_culprit_back(world):
    t = Trained(*world, ["1", "2", "3", "4"], bad={"h3"})
    t.go()
    assert [h for h, _p in t.fake.landed_calls[:3]] == ["h1", "h2", "h4"]
    (row,) = [r for r in journal.read() if r["event"] == "train" and r["result"] == "red"]
    assert row["landed"] == ["l1/1", "l2/2", "l4/4"] and list(row["back"]) == ["l3/3"] and row["extra_runs"] <= 3 and row["bisect"]
    told = [m for m in t.fake.sent if "swift-tests failed" in m]
    assert told and "DONE <short sha" in told[0], "the culprit's lane got the failing output as its fix brief"
    assert queue.load()[2]["steps"][0]["rounds"] == 1
    assert t.fake.landed_calls[-1][0] == "h3", "fixed, it waited for the next train (max_wait) and landed"
    assert len([r for r in journal.read() if r["event"] == "train"]) == 2


def test_a_merge_conflict_drops_one_step_and_the_train_goes_on(world):
    t = Trained(*world, ["1", "2", "3", "4"], conflict={"h2"})
    t.go()
    first = [r for r in journal.read() if r["event"] == "train"][0]
    assert first["landed"] == ["l1/1", "l3/3", "l4/4"] and list(first["back"]) == ["l2/2"] and first["candidate"] == "h1+h3+h4"
    assert [h for h, _p in t.fake.landed_calls[:3]] == ["h1", "h3", "h4"]
    assert any("conflict in h2" in m for m in t.fake.sent), "the lane got the conflict"


def test_max_wait_triggers_a_train_of_two(world):
    t = Trained(*world, ["1", "2"])
    t.go(2)
    assert t.trains == [["l1/1", "l2/2"]] and set(states().values()) == {"landed"}
    assert queue._now() - 1000 >= 45 * 60, "it waited for the oldest step to be 45 minutes old"


def test_a_train_that_is_off_lands_each_step_by_itself(world):
    t = Trained(*world, ["1", "2"], cfg=train.Cfg(enabled=False))
    t.go(2)
    assert not t.trains and [h for h, _p in t.fake.landed_calls] == ["h1", "h2"]


def test_a_loop_without_train_wiring_lands_as_before(world):
    t = Trained(*world, ["1", "2"])
    t.fake.procs.train_run = None
    t.go(2)
    assert not t.trains and len(t.fake.landed_calls) == 2


def test_a_restarted_loop_takes_steps_of_a_dead_train_back_into_the_queue(world):
    t = Trained(*world, ["1", "2"])
    lanes = queue.load()
    for x in lanes:
        x["steps"][0].update(state="train", head="h" + x["steps"][0]["step"], train_since=1.0, train_id="train-dead")
    queue.save(lanes)
    t.go(2)
    assert set(states().values()) == {"landed"} and len(t.trains) == 1


def test_the_console_shows_a_train_as_one_row_with_its_steps_and_the_waiting_ones(world):
    from fichero_builder import console
    t = Trained(*world, ["1", "2", "3", "4"], bad={"h3"})
    t.go()
    lanes = queue.load()
    lanes[0]["cursor"], lanes[0]["steps"][0]["state"] = 0, "train"  # one more waiting for the next train
    st = console.status(journal.read(), lanes)
    first = st["trains"][0]
    assert first["steps"] == ["l1/1", "l2/2", "l3/3", "l4/4"] and first["result"] == "red" and first["landed"] == ["l1/1", "l2/2", "l4/4"] and first["back"] == ["l3/3"]
    assert st["waiting_for_train"] == ["l1/1"]


def test_a_tick_with_no_dead_train_does_not_rewrite_the_lanes_file(world, monkeypatch):
    t = Trained(*world, ["1", "2"])
    saves = []
    real = queue.save
    monkeypatch.setattr(queue, "save", lambda lanes: (saves.append(1), real(lanes))[1])
    queue.train_when_due(t.fake.procs, None)  # two queued steps, nothing waiting, nothing to put back
    assert saves == []


def test_a_done_that_conflicts_with_the_land_branch_is_told_before_any_ladder_runs(monkeypatch, tmp_path):
    """local.check.conflict-told-at-done: the chain's rebase onto the land branch comes before any ladder slot; its conflict is the
    worker's conflict fix round at once (run.rebase-conflict-fix-round), and no ladder runs."""
    import types

    from fichero_builder import work
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(work, "do_rebase", lambda a, branch: "conflict in segments.py" + work.REBASE_CONFLICT + "the files: segments.py")
    monkeypatch.setattr(work, "ladder_slot", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a ladder slot was taken")))
    a = types.SimpleNamespace(name="seg-draw", issues=[], worktree=str(tmp_path / "wt"), pinned=str(tmp_path))
    r = work.after_run(a, str(tmp_path), "integration", "opus")
    assert r["kind"] == "conflict" and "segments.py" in r["findings"]


def test_a_done_that_conflicts_with_a_waiting_step_rides_the_train_after_it(world):
    """local.check.conflict-told-at-done: a DONE whose head conflicts with a step waiting for the train is one `conflicts-with` row,
    is checked as usual, and is held out of that step's train, so it merges after it."""
    t = Trained(*world, ["1", "2"])
    asked = []

    def premerge(lane, head):
        asked.append(lane["id"])
        return [("l1/1", ["fichero-server/src/segments.py"])] if lane["id"] == "l2" else []
    t.fake.procs.premerge = premerge
    t.fake.procs.head_of = lambda lane: "tip-" + lane["id"]  # the DONE's tree head (the chain fetches it later)
    t.go(2)
    rows = [r for r in journal.read() if r.get("state") == "conflicts-with"]
    assert [(r["lane"], r["other"]) for r in rows] == [("l2", "l1/1")] and "segments.py" in rows[0]["detail"]
    assert t.trains == [["l1/1"], ["l2/2"]], "l2 rides the train after l1's"
    assert set(states().values()) == {"landed"}
    assert asked.count("l2") == 1, "once per head"


def test_a_worker_lanes_done_is_premerged_by_its_chain_right_after_the_fetch(monkeypatch, tmp_path):
    """local.check.conflict-told-at-done (2026-11-26: seg-batch-6 and seg-select-1 met only in the train's merge): a worker lane's new
    head is not in the engine repo at DONE, so the tick's premerge cannot judge (None: nothing marked); the chain asks once its fetch
    brought the head in, before any ladder slot."""
    import types

    from fichero_builder import work
    monkeypatch.setattr(journal, "STATE", tmp_path)
    lane, s = {"id": "seg-tools", "steps": []}, {"step": "seg-batch-6", "head": ""}
    queue.mark_conflicts(lane, s, "abc", None)
    assert "premerged" not in s
    seen = []
    monkeypatch.setattr(work, "do_rebase", lambda a, branch: "")
    monkeypatch.setattr(work, "do_export", lambda a, branch: 1)
    monkeypatch.setattr(work, "do_fetch", lambda a, repo, branch: "abc123")
    monkeypatch.setattr(work, "r_since", lambda repo, branch: (_ for _ in ()).throw(RuntimeError("stop here")))
    monkeypatch.setattr(work, "ladder_slot", lambda *a, **k: (_ for _ in ()).throw(AssertionError("stop")))
    a = types.SimpleNamespace(name="seg-tools", issues=[], worktree=str(tmp_path / "wt"), pinned=str(tmp_path), after_fetch=seen.append)
    try:
        work.after_run(a, str(tmp_path), "integration", "opus")
    except Exception:  # noqa: BLE001 - the fake ladder stops the chain; only the premerge call is under test
        pass
    assert seen == ["abc123"]


def test_a_train_takes_at_most_size_steps_in_order_and_the_rest_wait(world):
    """local.train.size-follows-the-last-result: at most `size` (from [train].max_steps) waiting steps, in queue order; the rest wait
    for the next train; the row carries size and the number left."""
    t = Trained(*world, ["1", "2", "3", "4", "5"], cfg=train.Cfg(max_steps=3))
    t.go(5)
    assert t.trains[0] == ["l1/1", "l2/2", "l3/3"] and t.trains[1][:2] == ["l4/4", "l5/5"]
    first = [r for r in journal.read() if r["event"] == "train"][0]
    assert (first["size"], first["left"]) == (3, 2)
    assert set(states().values()) == {"landed"}


def test_size_halves_after_a_red_train_and_doubles_after_a_green_one_up_to_max_steps():
    cfg = train.Cfg(max_steps=6)
    assert [train.next_size(6, r, cfg) for r in ("red", "unresolved", "timeout", "error")] == [3, 3, 3, 3]
    assert train.next_size(1, "red", cfg) == 1 and train.next_size(3, "green", cfg) == 6 and train.next_size(6, "green", cfg) == 6
    assert train.next_size(2, "conflict", cfg) == 4, "a green train that dropped a conflicting step is green"
    assert train.load({"train": {"max_steps": 2}}).max_steps == 2 and train.load({}).max_steps == 6
    with pytest.raises(ValueError):
        train.load({"train": {"max_steps": 0}})


def test_a_red_train_halves_the_next_ones_size(world):
    t = Trained(*world, ["1", "2", "3", "4"], bad={"h3"}, cfg=train.Cfg(max_steps=4))
    t.go(4)
    rows = [r for r in journal.read() if r["event"] == "train"]
    assert rows[0]["size"] == 4 and rows[0]["result"] == "red" and rows[1]["size"] == 2
