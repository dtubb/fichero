"""dev-workflows.rollout.dry-run: the loop runs against fakes; a cap parks and stops the worker, a gone worker ends with a cost row."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_builder import journal, run

TOML = '[spend]\nsession_usd = 1\nday_usd = 5\nwindow = 1000\nprices = { sonnet = [3, 15] }\n'
HEALTHY = {"started": True, "idle": False, "context": 100, "tokens": 1000, "cost_usd": 0.0, "turns": 1, "rate_limited": False, "error": "", "transient": False}


class Fake:
    def __init__(self, states, heads=("aaaa111", "bbbb222")):
        self.states, self.alive_now, self.stopped, self.t = list(states), True, [], 0.0
        self.heads = list(heads)  # the first is the base; the branch moves once a state has moved=True
        self.procs = run.Procs(start=self.start, alive=lambda p: self.alive_now, stop=self.stop, read=self.read,
                               sleep=lambda s: None, now=lambda: self.t, head=lambda: self.heads[0])

    def start(self, root, worktree, brief, name, model, tmux_session):
        self.started = (str(worktree), str(brief), name, model)
        self.alive_now = True  # a successor is alive again
        return "%9"

    def read(self):
        self.t += 30
        if not self.states:
            self.alive_now = False
            return None
        s = self.states.pop(0)
        if s != "gone" and s.get("moved") and len(self.heads) > 1:
            self.heads.pop(0)
        return None if s == "gone" else s

    def stop(self, pane):
        self.stopped.append(pane)
        self.alive_now = False


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text(TOML)
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setenv("FICHERO_HARNESS_REG", str(tmp_path / "reg"))
    return tmp_path


def test_run_registers_the_worker_for_the_in_session_hook_with_the_successor_left_to_the_watcher(root):
    import json

    fake = Fake([HEALTHY])
    run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None)
    reg = json.loads((root / "reg" / "w.json").read_text())
    assert reg == {"worktree": str(root / "wt"), "handoff": str(root / "wt" / "HANDOFF.md"), "model": "sonnet", "window": 1000,
                   "session": "harness", "successor": "watcher"}


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
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "moved": True, "last_text": "All three landed.\nDONE bbbb222"}, HEALTHY])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    assert fake.stopped == ["%9"] and journal.read()[-1]["end"] == "done"


def test_a_done_line_with_no_commit_or_another_sha_is_a_false_done_not_an_end(root):
    said = []
    # the first live run: the worker wrote "No `DONE` line, since nothing was committed" and the old word match ended the run
    fake = Fake([{**HEALTHY, "idle": True, "last_text": "No `DONE` line, since nothing was committed."},
                 {**HEALTHY, "idle": True, "last_text": "DONE aaaa111"},            # the base sha: the branch never moved
                 {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE 0000fff"}])  # moved, but names another sha
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=said.append) == "gone"
    assert fake.stopped == []
    assert [e["what"][:10] for e in journal.read() if e["event"] == "watch"] == ["false done"]


def test_an_idle_worker_without_the_done_line_is_left_alone(root):
    fake = Fake([{**HEALTHY, "idle": True, "last_text": "hello"}, {**HEALTHY, "idle": True, "last_text": "hello"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert fake.stopped == []


def test_handoff_ready_ends_the_worker_and_starts_a_successor_with_the_handoff_brief(root):
    (root / "wt").mkdir()
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "context": 900, "tokens": 900, "fresh": 900, "last_text": "Committed.\nHANDOFF READY"},
                 HEALTHY, {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE bbbb222"}])
    starts = []
    real_start = fake.start
    fake.procs.start = lambda *a: starts.append(a) or real_start(*a)
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    assert fake.stopped == ["%9", "%9"] and len(starts) == 2
    brief = (root / "wt" / ".builder-brief-w-2.txt").read_text()
    assert "generation 2" in brief and str(root / "wt" / "HANDOFF.md") in brief and "HANDOFF READY" in brief
    rows = journal.read()
    assert [(e["event"], e.get("generation"), e.get("end")) for e in rows if e["event"] in ("worker", "cost")] == [
        ("worker", 1, None), ("cost", 1, "handoff"), ("worker", 2, None), ("cost", 2, "done")]


def test_the_generation_cap_parks_instead_of_starting_another(root):
    (root / "wt").mkdir()
    ready = {**HEALTHY, "idle": True, "last_text": "HANDOFF READY"}
    fake = Fake([ready, ready, ready])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, max_generations=2) == "parked"
    assert [e["what"] for e in journal.read() if e["event"] == "watch"][-1] == "park: 2 generations, the cap"


def test_the_cli_refuses_without_a_cap_and_points_the_journal_at_the_state_dir(tmp_path, monkeypatch, capsys):
    """`python -m fichero_builder run --state DIR` writes nothing to the default state dir; a missing cap refuses before any start."""
    from fichero_builder import __main__ as cli

    (tmp_path / "harness.toml").write_text("[check]\n")
    monkeypatch.setattr(run, "real_procs", lambda home, wt: run.Procs(start=lambda *a: "%1", alive=lambda p: True, stop=lambda p: None, read=lambda: None))
    rc = cli.main(["run", "--worktree", str(tmp_path / "wt"), "--brief", str(tmp_path / "b.txt"), "--root", str(tmp_path),
                   "--state", str(tmp_path / "state")])
    assert rc == 1 and "no cap, no start" in capsys.readouterr().out
    assert journal.STATE == tmp_path / "state"


def test_the_check_verb_runs_the_ladder_and_exits_on_its_verdict(monkeypatch, capsys, tmp_path):
    from fichero_builder import __main__ as cli, check_tool

    calls = []
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: rev)  # no git here: the head is taken as given
    monkeypatch.setattr(check_tool, "run_ladder", lambda *a, **k: calls.append(a) or {"ok": False, "rungs": []})
    assert cli.main(["check", "--repo", "/r", "abc", "def", "--pinned", "/p", "--id", "x.y", "--state", str(tmp_path / "state")]) == 1
    assert calls == [("/r", "abc", "def", "/p", ["x.y"])] and '"ok": false' in capsys.readouterr().out
    monkeypatch.setattr(check_tool, "run_ladder", lambda *a, **k: {"ok": True})
    assert cli.main(["check", "--repo", "/r", "abc", "def", "--pinned", "/p", "--state", str(tmp_path / "state")]) == 0


def test_the_land_verb_runs_the_gate_and_a_bad_rules_file_refuses_before_anything(tmp_path, capsys):
    from fichero_builder import __main__ as cli

    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / "harness.toml").write_text("[breif]\nrules = 1\n")  # a misspelt table: rules_problems refuses
    rc = cli.main(["land", "--repo", str(tmp_path), "HEAD", "--pinned", str(pinned), "--verdicts", str(tmp_path / "v"), "--log", str(tmp_path / "log")])
    err = capsys.readouterr().err
    assert rc == 1 and "REFUSED (rules file)" in err and "breif" in err
    assert "rules" in (tmp_path / "log").read_text()


def test_the_check_row_records_whether_it_was_a_maintainer_batch_and_checked_is_unchanged(monkeypatch, tmp_path):
    from fichero_builder import __main__ as cli, check_tool, journal, land_tool

    monkeypatch.setattr(cli, "resolve", lambda repo, rev: rev)
    monkeypatch.setattr(check_tool, "run_ladder", lambda *a, **k: {"ok": True})
    argv = ["check", "--repo", "/r", "abc", "def", "--pinned", "/p", "--state", str(tmp_path / "state")]
    assert cli.main(argv) == 0 and cli.main([*argv, "--maintainer"]) == 0
    rows = [r for r in journal.read() if r["event"] == "check"]
    assert [r["maintainer"] for r in rows] == [False, True]
    assert land_tool.green_row(rows, "def", "abc")["maintainer"] is True


def test_an_idle_worker_whose_branch_moved_but_said_no_done_is_nudged_once_then_ended_done_unsaid(root):
    """Defect 2 (2026-11-01: two workers idled 30+ min with commits and no DONE line): idle with HEAD moved and no DONE
    line for two ticks -> one nudge naming the exact line; still idle two ticks later -> end `done-unsaid` (a cost row,
    exit 0 at the verb). A worker whose branch never moved is still left alone."""
    told = []
    idle_moved = {**HEALTHY, "idle": True, "moved": True, "last_text": "Committed, all green."}
    fake = Fake([HEALTHY, idle_moved, idle_moved, idle_moved, idle_moved, HEALTHY])
    fake.procs.tell = lambda pane, words: told.append((pane, words))
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done-unsaid"
    assert told == [("%9", "Your branch has commits and your turn ended without the DONE line: end your turn with the exact line DONE bbbb222")]
    assert fake.stopped == ["%9"]
    rows = journal.read()
    assert [r["what"].split(":")[0] for r in rows if r["event"] == "watch"] == ["nudge", "done-unsaid"] and rows[-1]["end"] == "done-unsaid"


def test_a_hand_brief_without_the_done_instruction_gets_it_added_in_the_copy_the_worker_is_started_on(root):
    (root / "wt").mkdir()
    (root / "b.txt").write_text("Fix #1 in this worktree.\n")
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE bbbb222"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    started = Path(fake.started[1])
    assert started == root / "wt" / ".builder-brief-w-1.txt" and started.read_text().startswith("Fix #1 in this worktree.\n")
    assert "end your turn with the exact line DONE <short sha of the branch head>" in started.read_text()
    (root / "b.txt").write_text("Fix #1. When done print on its own line: DONE <short sha of the branch head>.\n")
    fake = Fake([HEALTHY, {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE bbbb222"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    assert Path(fake.started[1]) == root / "b.txt", "a brief that carries the instruction is started as it is"


def test_the_real_procs_tell_types_the_words_then_enter_as_two_tmux_calls(tmp_path, monkeypatch):
    """Defect in the first nudge: the Claude kind's Procs had no tell, so the nudge reached nobody. A bare send-keys with the
    Enter in one call loses the Enter, so the words go literally (-l) and the Enter is its own call."""
    calls = []
    monkeypatch.setattr(run.subprocess, "run", lambda argv, **k: calls.append(argv))
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    run.real_procs(tmp_path, tmp_path / "wt").tell("%3", "end with DONE abc")
    assert calls == [["tmux", "send-keys", "-t", "%3", "-l", "end with DONE abc"], ["tmux", "send-keys", "-t", "%3", "Enter"]]


def test_a_done_line_naming_the_wrong_sha_on_a_moved_branch_is_nudged_and_ended_too(root):
    """The same idle-forever defect: the branch moved, the DONE line names another sha, nothing else would end the run."""
    told = []
    wrong = {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE 0000fff"}
    fake = Fake([HEALTHY, wrong, wrong, wrong, wrong, HEALTHY])
    fake.procs.tell = lambda pane, words: told.append(words)
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done-unsaid"
    assert len(told) == 1 and told[0].endswith("DONE bbbb222")
