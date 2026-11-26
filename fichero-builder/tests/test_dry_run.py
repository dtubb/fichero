"""dev-workflows.rollout.dry-run: the loop runs against fakes; a cap parks and stops the worker, a gone worker ends with a cost row."""
from __future__ import annotations

import types

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
    assert reg == {"worktree": str(root / "wt"), "handoff": str(root / "wt" / "HANDOFF.md"), "model": "sonnet", "window": 1000, "handoff_tokens": 850,
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


def test_session_spend_alone_neither_hands_off_nor_stops_the_worker(root):
    """Owner ruling B2 (2026-11-21): the dollar session cap is gone; only the day cap and the context limit end a session."""
    fake = Fake([HEALTHY, {**HEALTHY, "cost_usd": 1.0}, HEALTHY])
    told = []
    fake.procs.tell = lambda pane, words: told.append(words)
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert fake.stopped == [] and told == []
    assert [e["what"] for e in journal.read() if e["event"] == "watch"] == []


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
                   "--state", str(tmp_path / "state"), "--model", "sonnet"])  # no [models] here: the model is named
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
    sends = [c for c in calls if c[1] == "send-keys"]
    assert sends == [["tmux", "send-keys", "-t", "%3", "-l", "end with DONE abc"], ["tmux", "send-keys", "-t", "%3", "Enter"]]


def test_tell_presses_enter_again_while_the_words_still_sit_unsent_in_the_input_line(tmp_path, monkeypatch):
    """#6589 2026-11-19: a long message is taken as a paste and the first Enter is swallowed; briefs sat unsent for hours.
    While the words are still in the ❯ line the Enter is sent again; once the line is clear it stops."""
    calls, boxes = [], iter(["  ❯ Read /x/msg-9.txt and do what it says", "  ❯ "])

    def fake(argv, **k):
        calls.append(argv)
        return types.SimpleNamespace(stdout=next(boxes) if argv[1] == "capture-pane" else "")
    monkeypatch.setattr(run.subprocess, "run", fake)
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    run.real_procs(tmp_path, tmp_path / "wt").tell("%3", "Read /x/msg-9.txt and do what it says")
    assert [c[-1] for c in calls if c[1] == "send-keys"][1:] == ["Enter", "Enter"], "one Enter, then one more while unsent"


def test_a_done_line_naming_the_wrong_sha_on_a_moved_branch_is_nudged_and_ended_too(root):
    """The same idle-forever defect: the branch moved, the DONE line names another sha, nothing else would end the run."""
    told = []
    wrong = {**HEALTHY, "idle": True, "moved": True, "last_text": "DONE 0000fff"}
    fake = Fake([HEALTHY, wrong, wrong, wrong, wrong, HEALTHY])
    fake.procs.tell = lambda pane, words: told.append(words)
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done-unsaid"
    assert len(told) == 1 and told[0].endswith("DONE bbbb222")


def test_feed_mode_keeps_the_session_and_types_the_next_brief_into_the_same_pane(root):
    """Owner ruling (the queue): after DONE the worker stays open; a `step` row says so; msg-<seq+1>.txt in the feed folder
    goes into the SAME pane, one start only; the old idle DONE text is not read as the next step's end; `stop` ends it."""
    feed = root / "inbox"
    feed.mkdir()
    done1 = {**HEALTHY, "idle": True, "moved": True, "turns": 2, "last_text": "DONE bbbb222"}
    stale = {**done1, "moved": False}
    done2 = {**HEALTHY, "idle": True, "moved": True, "turns": 3, "last_text": "DONE cccc333"}
    fake = Fake([HEALTHY, done1, stale, stale, done2, stale], heads=("aaaa111", "bbbb222", "cccc333"))
    told, starts, reads = [], [], []
    real_read, real_start = fake.read, fake.start
    fake.procs.tell = lambda pane, words: told.append((pane, words))
    fake.procs.start = lambda *a: starts.append(a) or real_start(*a)

    def read():
        reads.append(1)
        if len(reads) == 3:  # the owner has checked and landed the first step
            (feed / "msg-1.txt").write_text("the next step")
        if len(reads) == 6:
            (feed / "stop").write_text("")
        return real_read()
    fake.procs.read = read
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed) == "lane-done"
    assert len(starts) == 1 and fake.stopped == ["%9"], "one session from first brief to stop"
    assert told == [("%9", f"Read {feed / 'msg-1.txt'} and do what it says; end your turn with the DONE line it names.")]
    rows = [(r["seq"], r["sha"], r["moved"]) for r in journal.read() if r["event"] == "step"]
    assert rows == [(0, "bbbb222", True), (1, "cccc333", True)], "one row per step; the stale DONE gave none"
    assert not [r for r in journal.read() if r["event"] == "watch" and r["what"].startswith("false done")]


def test_feed_mode_a_done_with_no_new_commit_is_a_step_row_saying_so(root):
    """A fix brief answered with no commit must not hang the lane: the owner reads moved=False."""
    feed = root / "inbox"
    feed.mkdir()
    fake = Fake([{**HEALTHY, "idle": True, "turns": 2, "last_text": "DONE aaaa111"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed, seq=4) == "gone"
    assert [(r["seq"], r["moved"]) for r in journal.read() if r["event"] == "step"] == [(4, False)]


def test_a_worker_that_answers_the_nudge_without_the_line_still_ends(root):
    """One nudge only: a reply with no DONE line between the idle ticks must not reset it into a nudge loop."""
    told = []
    idle = {**HEALTHY, "idle": True, "moved": True, "last_text": "Committed."}
    busy = {**HEALTHY, "moved": False}
    fake = Fake([idle, idle, busy, idle, idle, HEALTHY])
    fake.procs.tell = lambda pane, words: told.append(words)
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done-unsaid"
    assert len(told) == 1


def test_the_brief_copy_is_ignored_so_a_worker_cannot_commit_it():
    import os

    root = Path(run.__file__).resolve().parents[2]
    assert ".builder-brief-*" in (root / ".gitignore").read_text().splitlines(), os.fspath(root)


def test_a_run_records_what_it_read_before_its_first_commit(root):
    """The reading metric: turns and tokens at the first tick the worktree's HEAD has moved: a `reading` row once, and on the cost row."""
    fake = Fake([{**HEALTHY, "turns": 3, "tokens": 50}, {**HEALTHY, "turns": 9, "tokens": 400, "moved": True}, {**HEALTHY, "turns": 12, "tokens": 900},
                 {**HEALTHY, "turns": 12, "tokens": 900, "idle": True, "last_text": "DONE bbbb222"}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "done"
    rows = journal.read()
    reading = [r for r in rows if r["event"] == "reading"]
    assert [(r["task"], r["turns_before_first_commit"], r["tokens_before_first_commit"]) for r in reading] == [("w", 9, 400)]
    cost = rows[-1]
    assert cost["event"] == "cost" and cost["turns_before_first_commit"] == 9 and cost["tokens_before_first_commit"] == 400


def test_a_run_with_no_commit_has_no_reading_figure(root):
    fake = Fake([{**HEALTHY, "turns": 3, "tokens": 5000}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "gone"
    assert journal.read()[-1]["turns_before_first_commit"] is None and not [r for r in journal.read() if r["event"] == "reading"]


def _feed_run(root, states, heads, at_read, **extra):
    """A feed run where `at_read[n]` is called on the n-th read; returns (told, redelivered, step rows)."""
    feed = root / "inbox"
    feed.mkdir(exist_ok=True)
    fake = Fake(states, heads=heads)
    told, again, reads = [], [], []
    real_read = fake.read
    fake.procs.tell = lambda pane, words: told.append(words)
    fake.procs.redeliver = lambda pane, words: again.append(words)

    def read():
        reads.append(1)
        if (f := at_read.get(len(reads))):
            f(feed)
        return real_read()
    fake.procs.read = read
    run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed, **extra)
    return told, again, [(r["seq"], r["sha"], r["moved"]) for r in journal.read() if r["event"] == "step"]


def test_an_old_done_on_screen_never_marks_a_new_step_done_before_its_message_is_delivered(root):
    """#6589 2026-11-20: a DONE counts only if printed after this step's message was delivered. Step 2's message was sent but no
    prompt arrived (turns moved on by tool turns of the old work); the old `DONE bbbb222` text is still the last text."""
    done1 = {**HEALTHY, "idle": True, "moved": True, "turns": 2, "prompts": 1, "last_text": "DONE bbbb222"}
    other_turn = {**done1, "moved": False, "turns": 3}  # an assistant turn, no new prompt: the message sits in the input box
    states = [HEALTHY, done1, done1, other_turn, other_turn, other_turn, {**HEALTHY, "idle": True, "turns": 3, "prompts": 1, "last_text": "DONE bbbb222"}]
    told, again, rows = _feed_run(root, states, ("aaaa111", "bbbb222"),
                                  {3: lambda feed: (feed / "msg-1.txt").write_text("next"), 7: lambda feed: (feed / "stop").write_text("")})
    assert rows == [(0, "bbbb222", True)], "the old DONE gave no second step row"


def test_a_message_that_started_no_turn_within_sixty_seconds_is_delivered_again(root):
    done1 = {**HEALTHY, "idle": True, "moved": True, "turns": 2, "prompts": 1, "last_text": "DONE bbbb222"}
    quiet = {**done1, "moved": False}
    states = [HEALTHY, done1, quiet, quiet, quiet, quiet, quiet]
    told, again, rows = _feed_run(root, states, ("aaaa111", "bbbb222"),
                                  {3: lambda feed: (feed / "msg-1.txt").write_text("next"), 8: lambda feed: (feed / "stop").write_text("")})
    assert len(told) == 1 and len(again) >= 1 and again[0] == told[0], (told, again)
    assert [r for r in journal.read() if r["event"] == "watch" and r["what"].startswith("redeliver")]


def test_a_delivered_message_is_not_delivered_again(root):
    done1 = {**HEALTHY, "idle": True, "moved": True, "turns": 2, "prompts": 1, "last_text": "DONE bbbb222"}
    working = {**HEALTHY, "idle": False, "turns": 3, "prompts": 2, "last_text": "working"}
    states = [HEALTHY, done1, done1, working, working, working, working, working]
    told, again, rows = _feed_run(root, states, ("aaaa111", "bbbb222"),
                                  {3: lambda feed: (feed / "msg-1.txt").write_text("next"), 9: lambda feed: (feed / "stop").write_text("")})
    assert len(told) == 1 and again == []


def test_the_real_redeliver_presses_enter_when_the_words_sit_in_the_box_and_types_them_again_when_a_turn_never_started(tmp_path, monkeypatch):
    calls = []
    box = iter(["❯ Read /x/msg-9.txt and do what it says", "❯ ", "❯ ", "❯ ", "❯ "])

    def fake(argv, **k):
        calls.append(argv)
        return types.SimpleNamespace(stdout=next(box) if argv[1] == "capture-pane" else "")
    monkeypatch.setattr(run.subprocess, "run", fake)
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    words = "Read /x/msg-9.txt and do what it says"
    p = run.real_procs(tmp_path, tmp_path / "wt")
    p.redeliver("%3", words)
    assert [c[3:] for c in calls if c[1] == "send-keys"][:1] == [["Enter"]] or [c[-1] for c in calls if c[1] == "send-keys"][0] == "Enter"
    calls.clear()
    p.redeliver("%3", words)
    assert [c[-1] for c in calls if c[1] == "send-keys"][0] == words


def _rules(path, day_usd):
    import json
    path.write_text(json.dumps({"spend": {"day_usd": day_usd, "window": 1000, "prices": {"sonnet": [3, 15]}}, "models": {}}))


def test_a_raised_cap_in_the_published_rules_reaches_a_running_session_on_the_next_tick(root):
    """local.perf.caps-reread-each-tick (#6851): the run reads `--rules` every tick; a cap raised after the start counts."""
    rules = root / "rules.json"
    _rules(rules, 2)

    class Raised(Fake):
        def read(self):
            if self.t == 30:
                _rules(rules, 50)  # the owner raises the cap while the worker runs
            return super().read()
    fake = Raised([HEALTHY, {**HEALTHY, "cost_usd": 3.0}, {**HEALTHY, "cost_usd": 4.0}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, rules=rules) == "gone"
    assert fake.stopped == [] and not [e for e in journal.read() if e["event"] == "watch"]


def test_a_lowered_cap_in_the_root_rules_parks_on_the_next_tick(root):
    """Without `--rules` the run reads the root's rules file every tick."""
    class Lowered(Fake):
        def read(self):
            if self.t == 30:
                (root / "harness.toml").write_text(TOML.replace("day_usd = 5", "day_usd = 2"))
            return super().read()
    fake = Lowered([HEALTHY, {**HEALTHY, "cost_usd": 3.0}, HEALTHY])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "parked"
    assert any("reached the cap 2.00" in e.get("what", "") for e in journal.read())


def test_unreadable_rules_mid_run_alert_once_and_keep_the_last_figures(root):
    rules = root / "rules.json"
    _rules(rules, 2)

    class Broken(Fake):
        def read(self):
            if self.t == 30:
                rules.write_text("{not json")
            return super().read()
    fake = Broken([HEALTHY, HEALTHY, {**HEALTHY, "cost_usd": 3.0}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, rules=rules) == "parked"
    watch = [e["what"] for e in journal.read() if e["event"] == "watch"]
    assert len([w for w in watch if w.startswith("alert: rules unreadable")]) == 1
    assert watch[-1] == "park: today's spend 3.00 USD reached the cap 2.00", "the last figures still hold"


def _live(name, usd):
    import json
    import time
    d = journal.STATE / "live"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"usd": usd, "day": time.strftime("%Y-%m-%d")}))


def test_three_live_sessions_near_the_cap_keep_a_fourth_from_starting(root):
    """local.perf.day-cap-counts-live-sessions (#6871): the day cap counts the running cost of the sessions still going."""
    for n in ("a", "b", "c"):
        _live(n, 1.7)
    fake = Fake([HEALTHY])
    assert run.run(root, root / "wt", root / "b.txt", name="d", procs=fake.procs, out=lambda s: None) == "parked"
    assert not hasattr(fake, "started")
    assert [e["what"] for e in journal.read()] == ["park: today's spend 5.10 USD reached the cap 5.00 before the start"]


def test_a_tick_parks_when_the_others_live_cost_and_its_own_reach_the_cap_and_the_own_file_goes_at_the_end(root):
    import json
    _live("a", 3.0)
    seen = []

    class Watch(Fake):
        def read(self):
            f = journal.STATE / "live" / "w.json"
            seen.append(json.loads(f.read_text())["usd"] if f.exists() else None)
            return super().read()
    fake = Watch([HEALTHY, {**HEALTHY, "cost_usd": 1.0}, {**HEALTHY, "cost_usd": 2.5}])
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None) == "parked"
    assert seen[1:3] == [0.015, 1.0], "each tick writes the run's running cost"
    assert any(e.get("what") == "park: today's spend 5.50 USD reached the cap 5.00" for e in journal.read())
    assert not (journal.STATE / "live" / "w.json").exists() and (journal.STATE / "live" / "a.json").exists()


def test_a_stale_live_file_does_not_hold_back_a_start(root):
    import os
    _live("crashed", 9.0)
    os.utime(journal.STATE / "live" / "crashed.json", (1000.0, 1000.0))
    fake = Fake([HEALTHY])
    assert run.run(root, root / "wt", root / "b.txt", name="d", procs=fake.procs, out=lambda s: None) == "gone"
    assert hasattr(fake, "started")


def test_a_waiting_end_message_is_one_step_row_with_the_question_and_the_session_stays(root):
    """#6855: a turn that ends with a `WAITING:` line is not a DONE and not an unsaid commit: the step row carries the question."""
    feed = root / "inbox"
    feed.mkdir()
    ask = {**HEALTHY, "idle": True, "moved": False, "turns": 2, "last_text": "I need a ruling.\nWAITING: which of the two caps does the day cap replace?"}
    fake = Fake([HEALTHY, ask, ask, ask], heads=("aaaa111",))
    reads = []
    real_read = fake.read

    def read():
        reads.append(1)
        if len(reads) == 4:
            (feed / "stop").write_text("")
        return real_read()
    fake.procs.read = read
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed) == "lane-done"
    rows = [r for r in journal.read() if r["event"] == "step"]
    assert len(rows) == 1 and rows[0]["waiting"] == "which of the two caps does the day cap replace?" and rows[0]["moved"] is False


def test_a_done_step_row_carries_the_sessions_context_model_window_and_the_parts_left(root):
    """The queue decides to keep a session from the step row: the latest prompt size, the model and window, and `PART n left: why` lines."""
    feed = root / "inbox"
    feed.mkdir()
    text = "Parts 1 and 3 are in.\nPART 2 left: needs a design call\nDONE aaaa111"
    fake = Fake([{**HEALTHY, "idle": True, "turns": 2, "context": 12345, "last_text": text}], heads=("aaaa111",))
    assert run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed, model="sonnet") == "gone"
    (row,) = [r for r in journal.read() if r["event"] == "step"]
    assert row["context"] == 12345 and row["model"] == "sonnet" and row["window"] > 0
    assert row["left"] == [{"part": 2, "why": "needs a design call"}]


def test_a_metered_role_parks_before_the_start_when_the_weeks_rows_reach_its_cap(root):
    """local.spend.metered-provider-needs-a-cap: the cost rows name their provider, and the week's openrouter rows reach the figure."""
    (root / "harness.toml").write_text(TOML.replace("prices = { sonnet = [3, 15] }", 'prices = { sonnet = [3, 15], qwen = [0.2, 1] }\nmetered = ["openrouter"]')
                                       + '[spend.week_usd]\nopenrouter = 1\n[models]\nproviders = ["openrouter"]\nq = { provider = "openrouter", model = "qwen" }\n')
    assert run.run(root, root / "wt", root / "b.txt", name="w", model="qwen", role="q", procs=Fake([{**HEALTHY, "cost_usd": 0.6}]).procs, out=lambda s: None) == "gone"
    assert journal.read()[-1]["provider"] == "openrouter"
    assert run.run(root, root / "wt", root / "b.txt", name="w2", model="qwen", role="q", procs=Fake([{**HEALTHY, "cost_usd": 0.5}]).procs, out=lambda s: None) == "parked"
    assert any("this week's openrouter spend" in r.get("what", "") for r in journal.read())
    said = []
    assert run.run(root, root / "wt", root / "b.txt", name="w3", model="qwen", role="q", procs=Fake([HEALTHY]).procs, out=said.append) == "parked"
    assert "before the start" in said[0]


def test_an_attached_watcher_starts_nothing_and_reads_a_done_already_on_screen(root):
    """local.run.sessions-survive-watchers: 2026-11-25 13:46, seg-tools (hands-5161) had printed `DONE eab0a2072e` and sat at the
    prompt with no watcher; the loop never read it. `builder run --attach` watches that pane and reads the DONE at the first idle tick."""
    feed = root / "inbox"
    feed.mkdir()
    fake = Fake([{**HEALTHY, "idle": True, "turns": 9, "prompts": 4, "last_text": "work done\nDONE eab0a2072e"}], heads=("eab0a2072e",))
    fake.procs.start = lambda *a: pytest.fail("an attached watcher starts no session")
    end = run.run(root, root / "wt", root / "b.txt", name="seg-tools", procs=fake.procs, out=lambda s: None, feed=feed, seq=7,
                  attach="%4", base_sha="23462609bb")
    assert end == "gone"
    assert [(r["seq"], r["sha"], r["moved"]) for r in journal.read() if r["event"] == "step"] == [(7, "eab0a2072e", True)]
    assert [r.get("attached") for r in journal.read() if r["event"] == "worker"] == [True]


def test_an_attached_watcher_with_no_step_out_waits_for_the_next_message(root):
    feed = root / "inbox"
    feed.mkdir()
    fake = Fake([{**HEALTHY, "idle": True, "turns": 9, "prompts": 4, "last_text": "DONE eab0a2072e"}], heads=("eab0a2072e",))
    run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed, seq=7, attach="%4", outstanding=False)
    assert not [r for r in journal.read() if r["event"] == "step"], "the DONE on screen is the last step's, already recorded"


def _ended_run(root, states, hook=None):
    """A feed run with step 0 out and the branch never moved; `hook` = the Stop hook's file, written before the first read."""
    feed = root / "inbox"
    feed.mkdir(exist_ok=True)
    if hook is not None:
        import json
        (feed / "turn-ended.json").write_text(json.dumps(hook))
    states = [*states, HEALTHY]  # the last read writes `stop`, after the tick that matters
    fake = Fake(states, heads=("aaaa111",))
    told = []
    fake.procs.tell = lambda pane, words: told.append(words)
    real_read = fake.read
    reads = []

    def read():
        reads.append(1)
        if len(reads) == len(states):
            (feed / "stop").write_text("")
        return real_read()
    fake.procs.read = read
    run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=feed)
    steps = [r for r in journal.read() if r["event"] == "step"]
    return told, steps, [r["what"] for r in journal.read() if r["event"] == "watch" and r["what"].startswith("turn-ended-no-done")]


def test_an_idle_worker_with_an_unmoved_branch_and_a_last_line_ending_in_a_question_is_one_alert_in_one_tick(root):
    ask = {**HEALTHY, "idle": True, "turns": 2, "last_text": "I looked at both.\nShould the cap replace the day figure or sit beside it?"}
    told, steps, watch = _ended_run(root, [HEALTHY, ask])
    assert len(steps) == 1 and steps[0]["waiting"].endswith("sit beside it?") and steps[0]["moved"] is False and told == []
    assert len(watch) == 1 and watch[0].endswith("sit beside it?")


def test_an_idle_worker_with_no_question_is_nudged_with_the_exact_line_then_alerted_two_ticks_later(root):
    quiet = {**HEALTHY, "idle": True, "turns": 2, "last_text": "I have looked around and found nothing to change."}
    told, steps, watch = _ended_run(root, [HEALTHY, quiet, quiet, quiet, quiet])
    assert told == ["Your turn ended without the DONE line: end your turn with the exact line DONE aaaa111"]
    assert len(steps) == 1 and "no DONE" in steps[0]["waiting"] and len(watch) == 1
    assert len(watch[0]) <= len("turn-ended-no-done: ") + 300


def test_the_stop_hooks_file_is_read_while_the_session_file_still_says_working(root):
    hook = {"at": 10 ** 9, "text": "x" * 400 + "\nWhich branch do you want?"}
    told, steps, watch = _ended_run(root, [HEALTHY, HEALTHY], hook=hook)
    assert len(steps) == 1 and steps[0]["waiting"].endswith("Which branch do you want?") and len(watch[0]) <= len("turn-ended-no-done: ") + 300


def test_a_hook_file_older_than_the_message_and_a_done_line_raise_nothing(root):
    old = {"at": -1, "text": "Which branch do you want?"}
    told, steps, watch = _ended_run(root, [HEALTHY, HEALTHY], hook=old)
    assert steps == [] and watch == [] and told == []


def test_a_feed_run_registers_its_feed_for_the_stop_hook(root):
    import json

    (root / "inbox").mkdir()
    fake = Fake([HEALTHY])
    run.run(root, root / "wt", root / "b.txt", name="w", procs=fake.procs, out=lambda s: None, feed=root / "inbox")
    assert json.loads((root / "reg" / "w.json").read_text())["feed"] == str(root / "inbox")
