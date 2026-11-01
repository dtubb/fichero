"""dev-workflows.rollout.dry-run: the loop runs against fakes; a cap parks and stops the worker, a gone worker ends with a cost row."""
from __future__ import annotations

import pytest

from fichero_builder import journal, run

TOML = '[spend]\nsession_usd = 1\nday_usd = 5\nwindow = 1000\nprices = { sonnet = [3, 15] }\n'
HEALTHY = {"started": True, "idle": False, "context": 100, "tokens": 1000, "cost_usd": 0.0, "turns": 1, "rate_limited": False, "error": "", "transient": False}


class Fake:
    def __init__(self, states):
        self.states, self.alive_now, self.stopped, self.t = list(states), True, [], 0.0
        self.procs = run.Procs(start=self.start, alive=lambda p: self.alive_now, stop=self.stop, read=self.read,
                               sleep=lambda s: None, now=lambda: self.t)

    def start(self, root, worktree, brief, name, model, tmux_session):
        self.started = (str(worktree), str(brief), name, model)
        return "%9"

    def read(self):
        self.t += 30
        if not self.states:
            self.alive_now = False
            return None
        s = self.states.pop(0)
        return None if s == "gone" else s

    def stop(self, pane):
        self.stopped.append(pane)
        self.alive_now = False


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text(TOML)
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    return tmp_path


def test_a_missing_price_refuses_before_anything_starts(root):
    fake = Fake([HEALTHY])
    said = []
    assert run.run(root, root / "wt", root / "b.txt", name="w", model="gpt-9", procs=fake.procs, out=said.append) == "refused"
    assert not hasattr(fake, "started") and "unknown price" in said[0] and journal.read() == []


def test_a_healthy_worker_that_ends_leaves_one_worker_row_and_one_cost_row(root):
    fake = Fake([HEALTHY, {**HEALTHY, "turns": 2, "tokens": 2000, "fresh": 2000}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert fake.started == (str(root / "wt"), str(root / "b.txt"), "w", "sonnet") and fake.stopped == []
    events = [e["event"] for e in journal.read()]
    assert events == ["worker", "cost"]
    cost = journal.read()[-1]
    assert cost["usd"] == round(2000 * 3 / 1e6, 4) and cost["turns"] == 2 and cost["end"] == "gone"


def test_the_session_cap_parks_and_stops_the_worker(root):
    fake = Fake([HEALTHY, {**HEALTHY, "cost_usd": 1.0}, HEALTHY])
    said = []
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=said.append) == "parked"
    assert fake.stopped == ["%9"]
    watch = [e["what"] for e in journal.read() if e["event"] == "watch"]
    assert watch == ["park: session spend 1.00 USD reached the cap 1.00"]
    assert journal.read()[-1]["event"] == "cost" and journal.read()[-1]["end"] == "parked"


def test_yesterdays_spend_does_not_count_but_todays_does(root):
    journal.append("cost", task="old", usd=4.5)  # today, by its own ts
    fake = Fake([{**HEALTHY, "cost_usd": 0.6}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "parked"
    assert any("today's spend 5.10" in e.get("what", "") for e in journal.read())


def test_a_silent_worker_alerts_once_and_is_not_stopped(root):
    fake = Fake([HEALTHY] * 100)  # the same state 100 ticks of 30 s: silent for 3000 s
    said = []
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=said.append) == "gone"
    alerts = [e for e in journal.read() if e["event"] == "watch" and e["what"].startswith("alert")]
    assert len(alerts) == 1 and fake.stopped == []


def test_a_handoff_decision_is_recorded_not_acted_on(root):
    fake = Fake([{**HEALTHY, "context": 900}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert [e["what"] for e in journal.read() if e["event"] == "watch"] == ["handoff: context 900 of 1000"]


def test_session_dir_is_the_claude_code_slug(tmp_path):
    assert run.session_dir("/Users/w", "/Users/Shared/x/wt-a").as_posix() == "/Users/w/.claude/projects/-Users-Shared-x-wt-a"


def test_an_idle_worker_whose_last_words_carry_the_done_line_is_ended(root):
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "last_text": "All three landed.\nDONE 4f4e38a9a"}, HEALTHY])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    assert fake.stopped == ["%9"] and journal.read()[-1]["end"] == "done"


def test_an_idle_worker_without_the_done_line_is_left_alone(root):
    fake = Fake([{**HEALTHY, "idle": True, "last_text": "hello"}, {**HEALTHY, "idle": True, "last_text": "hello"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert fake.stopped == []
