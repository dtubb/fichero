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
    monkeypatch.setattr(queue, "RECENT", [])
    monkeypatch.setattr(queue, "MEMORY_READ", [False])
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


def _two_trains(world, monkeypatch, first_back=False, greens=4):
    """Two lanes waiting for a train; the first train blocks until released; then two more lanes wait (the second train)."""
    import threading
    tmp, _clock = world
    for k in ("FIRST_TID", "TRAIN_THREAD"):
        monkeypatch.setattr(queue, k, [""] if k == "FIRST_TID" else [None])
    monkeypatch.setattr(queue, "SECOND", {})
    monkeypatch.setattr(queue, "TRAIN_DONE", {})
    monkeypatch.setattr(queue, "RECENT", ["green"] * greens)
    monkeypatch.setattr(train, "CAND", {})
    queue.TRAIN[0] = train.Cfg(overlap=2, min_steps=2)

    def wait(names):
        for n in names:
            (tmp / f"b{n}").write_text("b")
            queue.add(f"l{n}", f"/w/l{n}", n, str(tmp / f"b{n}"), [int(n)])
        lanes = queue.load()
        for x in lanes:
            if x["id"] in {f"l{n}" for n in names}:
                x["steps"][0].update(state="train", head="h" + x["steps"][0]["step"], train_since=1.0)
        queue.save(lanes)
    release, calls = threading.Event(), []

    def train_run(spec, tid, base=""):
        calls.append((tid, base, [x["key"] for x in spec]))
        keys = [x["key"] for x in spec]
        if not base:
            train.CAND[tid] = "cand1"
            release.wait(10)
            if first_back:
                return train.Result(id=tid, steps=keys, landed=keys[:1], back={keys[1]: {"kind": "red", "why": "x", "findings": "x"}}, result="red")
        return train.Result(id=tid, steps=keys, landed=keys, result="green")
    fake = Fake()
    fake.procs.train_run = train_run
    wait(["1", "2"])
    queue.train_when_due(fake.procs, {})
    wait(["3", "4"])
    queue.train_when_due(fake.procs, {})
    release.set()
    queue.TRAIN_THREAD[0].join(10)
    if queue.SECOND.get("thread"):
        queue.SECOND["thread"].join(10)
    return calls


def test_a_second_train_runs_on_the_firsts_candidate_and_lands_after_it(world, monkeypatch):
    """local.train.second-train-on-the-first: [train].overlap = 2, 4 of the last 5 green: a second train starts on the first's
    candidate while it runs; its steps are cleared and land only after the first train's."""
    calls = _two_trains(world, monkeypatch)
    assert [(c[1], c[2]) for c in calls] == [("", ["l1/1", "l2/2"]), ("cand1", ["l3/3", "l4/4"])]
    st = {x["id"]: x["steps"][0] for x in queue.load()}
    assert st["l3"]["state"] == "done" and st["l3"]["train_base"] == calls[0][0]
    assert queue.train_waits(next(x for x in queue.load() if x["id"] == "l3"), st["l3"]), "it waits for the first train's steps to land"


def test_when_the_first_train_sends_a_step_back_the_second_is_cancelled_and_its_steps_wait_again(world, monkeypatch):
    calls = _two_trains(world, monkeypatch, first_back=True)
    assert len(calls) == 2
    rows = [r for r in journal.read() if r["event"] == "train" and r.get("result") == "cancelled"]
    assert len(rows) == 1 and rows[0]["detail"].startswith("cancelled: its base did not land")
    st = {x["id"]: x["steps"][0] for x in queue.load()}
    assert st["l3"]["state"] == "train" and not st["l3"].get("train_id") and "train_back" not in st["l3"], "waits again, sent back to no worker"


def test_no_second_train_starts_unless_four_of_the_last_five_were_green(world, monkeypatch):
    calls = _two_trains(world, monkeypatch, greens=3)
    assert len(calls) == 1
    queue.TRAIN[0] = train.Cfg()
    with pytest.raises(ValueError):
        train.load({"train": {"overlap": 3}})


def test_a_stacked_step_never_enters_a_train_ahead_of_the_step_under_it(world):
    """local.step.stacks-on-a-waiting-step: N+1 rides only behind N in the same train; a cut of the train's size never takes N+1 alone."""
    tmp, _clock = world
    for lid, n in (("la", "1"), ("la", "2"), ("lb", "3")):
        (tmp / f"b{n}").write_text(n)
        queue.add(lid, f"/w/{lid}", n, str(tmp / f"b{n}"), [int(n)])
    lanes = queue.load()
    a, b = lanes
    a["cursor"] = 1
    a["steps"][0].update(state="train", head="h1", train_since=5.0, train_back={"ok": False, "kind": "red", "why": "r"})  # sent back, not told yet
    a["steps"][1].update(state="train", head="h2", train_since=2.0, stacked_on="1", stack_base="h1")
    b["steps"][0].update(state="train", head="h3", train_since=1.0)
    queue.save(lanes)
    taken = []
    fake = Fake()
    fake.procs.train_run = lambda spec, tid, **k: taken.append([x["key"] for x in spec]) or train.Result(id=tid, steps=[x["key"] for x in spec], again=[x["key"] for x in spec])
    queue.TRAIN[0] = train.Cfg(min_steps=1)
    queue.train_when_due(fake.procs, None)
    assert taken == [["lb/3"]], "the step under it is not waiting: it waits too"
    lanes = queue.load()
    lanes[0]["steps"][0].pop("train_back")
    queue.save(lanes)
    queue.TRAIN_SIZE[0] = 2
    queue.train_when_due(fake.procs, None)
    assert taken[-1] == ["lb/3", "la/1"], "a size cut between the two takes the step under it, never the one on top"
    queue.TRAIN_SIZE[0] = 3
    queue.train_when_due(fake.procs, None)
    assert taken[-1] == ["lb/3", "la/1", "la/2"], "behind the step under it, whatever its own wait"


def test_a_step_never_lands_from_a_train_that_did_not_run_its_owed_dirs(world):
    """local.train.whole-tests-against-base: a step whose ladder left whole-tests dirs to the train lands only from one that ran them."""
    t = Trained(*world, ["1", "2"], cfg=train.Cfg(min_steps=2))
    t.chain = lambda lane, step, stage: {"ok": True, "head": "h" + step["step"], "why": "", "findings": "", **({"owed": ["pkg/tests"]} if step["step"] == "1" else {})}
    t.fake.procs.chain = t.chain
    ran = {"dirs": []}

    def run_train(spec, tid):
        t.trains.append([x["key"] for x in spec])
        return train.Result(id=tid, candidate="c", steps=[x["key"] for x in spec], landed=[x["key"] for x in spec], result="green",
                            rungs=[{"name": "whole-tests", "ok": True, "dirs": list(ran["dirs"])}])
    t.fake.procs.train_run = run_train
    queue.TRAIN_SIZE[0] = 0
    hs: dict = {}
    for _ in range(6):
        queue.tick(t.fake.procs, hs, workers_n=2, push=True, out=lambda s: None)
    assert states()["l2"] == "landed" and states()["l1"] == "train", "the step that owes nothing lands; the other waits"
    assert any(r.get("state") == "owed-not-run" and r["step"] == "1" for r in journal.read())
    ran["dirs"] = ["pkg/tests"]
    queue.TRAIN[0] = train.Cfg(min_steps=1)
    for _ in range(4):
        queue.tick(t.fake.procs, hs, workers_n=2, push=True, out=lambda s: None)
    assert states()["l1"] == "landed"


def test_the_train_size_and_the_last_results_survive_a_restart(world):
    t = Trained(*world, ["1", "2"], cfg=train.Cfg(min_steps=1, max_steps=4))
    t.result = "red"
    t.fake.procs.train_run = lambda spec, tid: t.trains.append(spec) or train.Result(id=tid, candidate="c", steps=[x["key"] for x in spec],
                                                                                     again=[x["key"] for x in spec], result="unresolved")
    queue.TRAIN_SIZE[0] = 4
    hs: dict = {}
    for _ in range(4):
        queue.tick(t.fake.procs, hs, workers_n=2, push=True, out=lambda s: None)
    assert t.trains, "a train ran"
    size, recent = queue.TRAIN_SIZE[0], list(queue.RECENT)
    assert size < 4 and recent
    queue.TRAIN_SIZE[0], queue.RECENT[:], queue.MEMORY_READ[0] = 0, [], False  # a restart
    queue._train_memory()
    assert (queue.TRAIN_SIZE[0], queue.RECENT) == (size, recent)


def test_train_cleared_steps_land_the_trains_merge_with_no_new_ladder_or_review_and_one_failure_never_holds_the_others(world):
    """train-20261126-181343 was green over kg-readable-representation/2.1, read-any-hand/0.1, seg-finish/bug-7076. The first went
    back through rebase, fetch, a 31-minute ladder and a whole review (NOT READY on a moved base) and held the other two behind it."""
    t = Trained(*world, ["1", "2", "3"], cfg=train.Cfg(min_steps=3))
    chains, lands = [], []

    def chain(lane, step, stage):
        chains.append(step["step"])
        return t.chain(lane, step, stage)
    t.fake.chain = t.fake.procs.chain = chain

    def land_cleared(lane, head, push, tid, key):
        lands.append((key, tid))
        return (1, "REFUSED (train-merge): TRAIN MERGE CONFLICT\nmerging h1 conflicts in: a.py") if key == "l1/1" else (0, f"landed {head}")
    t.fake.procs.land_cleared = land_cleared
    hs: dict = {}
    for _ in range(8):
        queue.tick(t.fake.procs, hs, workers_n=3, push=True, out=lambda s: None)
    (row,) = [r for r in journal.read() if r["event"] == "train"][:1]
    assert row["result"] == "green" and row["landed"] == ["l1/1", "l2/2", "l3/3"]
    assert chains.count("2") == chains.count("3") == 1, "one ladder each, before the train; none after it cleared them"
    assert chains.count("1") == 2, "the conflicting step's fix round is checked again, as any new head"
    assert [k for k, _t in lands[:3]] == ["l1/1", "l2/2", "l3/3"] and all(tid == row["id"] for _k, tid in lands[:3])
    assert not t.fake.landed_calls, "no `builder landed` for the plain READY path"
    s = states()
    assert s["l2"] == "landed" and s["l3"] == "landed", "the first one's conflict never holds the other two"
    assert s["l1"] != "landed" and any("merging h1 conflicts" in m for m in t.fake.sent), "the conflicting step goes back to its worker"
