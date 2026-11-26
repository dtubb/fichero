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
