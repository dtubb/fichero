"""dev-workflows.tool.queue: one long-running worker per lane (a milestone), fed step by step: after DONE the queue checks,
reviews and lands that step, then sends the next brief into the SAME session; findings go back as a fix brief; a new session
only when the worker is gone. The processes are fakes; the transitions and rows are real."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue


class Fake:
    """Each step's row appears once its brief is out; chain results are scripted per step, in order."""

    def __init__(self, chains=None, landed_rc=0, rebase="", moved=True):
        self.chains, self.landed_rc, self.rebase_why, self.moved = chains or {}, landed_rc, rebase, moved
        self.starts, self.sent, self.landed_calls, self.stops, self.seqs = [], [], [], [], set()
        self.alive_now, self.end = True, "gone"
        self.procs = queue.Procs(start=self.start, alive=lambda h: self.alive_now, send=self.send, rebase=lambda lane: self.rebase_why,
                                 row=self.row, chain=self.chain, landed=self.landed, end_of=lambda lane: self.end, stop=self.stop, sleep=lambda s: None)

    def start(self, lane, step):
        self.starts.append((lane["id"], step["step"], lane["seq"]))
        self.seqs.add(lane["seq"])
        self.alive_now = True
        return f"proc-{len(self.starts)}"

    def send(self, lane, text):
        self.sent.append(text)
        self.seqs.add(lane["seq"])

    def row(self, lane):
        return {"moved": self.moved} if lane["seq"] in self.seqs else None

    def chain(self, lane, step, stage):
        stage("checking"), stage("reviewing")
        script = self.chains.get(step["step"], [])
        r = script.pop(0) if script else {"ok": True}
        return {"ok": True, "head": "h" + step["step"], "why": "", "findings": "", **r}

    def landed(self, lane, head, push):
        self.landed_calls.append((head, push))
        return self.landed_rc, "landed" if self.landed_rc == 0 else "REFUSED (verdict): no READY"

    def stop(self, lane):
        self.stops.append(lane["id"])


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[queue]\nworkers = 2\n')
    return tmp_path


def lane(state):
    queue.add("m1", "/w/m1", "1.1", str(state / "b1.1"), [7])
    queue.add("m1", "/w/m1", "1.2", str(state / "b1.2"), [8], waits=["1.1"])


def steps():
    return {s["step"]: s for s in queue.load()[0]["steps"]}


def run(fake, **k):
    return queue.run(fake.procs, workers_n=1, push=k.pop("push", False), out=lambda s: None, **k)


def test_a_two_step_lane_lands_the_first_then_sends_the_second_into_the_same_session_and_stops_at_the_end(state):
    lane(state)
    fake = Fake()
    assert run(fake) == 0
    assert fake.starts == [("m1", "1.1", 1)], "one start: the second brief is not a second session"
    assert fake.sent == ["brief 1.2"]
    assert fake.landed_calls == [("h1.1", False), ("h1.2", False)]
    assert steps()["1.1"]["state"] == "landed" and steps()["1.2"]["state"] == "landed" and queue.load()[0]["cursor"] == 2
    assert fake.stops == ["m1"], "the lane is finished: the session ends"
    rows = [(r["step"], r["state"]) for r in journal.read() if r["event"] == "queue"]
    assert rows == [("1.1", "queued"), ("1.2", "queued"),
                    ("1.1", "sent"), ("1.1", "done"), ("1.1", "checking"), ("1.1", "reviewing"), ("1.1", "landed"),
                    ("1.2", "sent"), ("1.2", "done"), ("1.2", "checking"), ("1.2", "reviewing"), ("1.2", "landed")]


def test_a_red_check_goes_back_as_a_fix_brief_into_the_same_session_before_the_cursor_moves(state):
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "red", "why": "the check is red", "findings": "pytest: test_x failed"}]})
    assert run(fake) == 0
    assert len(fake.starts) == 1 and "pytest: test_x failed" in fake.sent[0] and "DONE <short sha" in fake.sent[0]
    assert fake.sent[1] == "brief 1.2", "the fix first, then the next step"
    assert fake.landed_calls[0] == ("h1.1", False) and steps()["1.1"]["rounds"] == 1


@pytest.mark.parametrize("kind", ["red", "not-ready", "refused"])
def test_two_fix_rounds_then_blocked_with_the_row_file_and_the_cursor_stays(state, kind):
    lane(state)
    bad = {"ok": False, "kind": kind, "why": "still wrong", "findings": "f"}
    fake = Fake(chains={"1.1": [dict(bad), dict(bad), dict(bad)]})
    assert run(fake) == 0
    assert len(fake.sent) == 2 and steps()["1.1"]["state"] == "blocked" and queue.load()[0]["cursor"] == 0 and not fake.landed_calls
    assert "still wrong" in (state / "s" / "question-m1-1.1.txt").read_text()
    assert steps()["1.2"]["state"] == "queued" and not fake.stops, "the worker waits idle for a person"


def test_an_error_in_the_chain_or_a_refused_landing_or_a_commitless_done_blocks_at_once(state):
    lane(state)
    assert run(Fake(chains={"1.1": [{"ok": False, "kind": "error", "why": "rules file broken"}]})) == 0
    assert steps()["1.1"]["state"] == "blocked" and "rules file broken" in steps()["1.1"]["why"]
    queue.save([])
    lane(state)
    fake = Fake(landed_rc=1)
    assert run(fake, push=True) == 0
    assert steps()["1.1"]["state"] == "blocked" and "no READY" in steps()["1.1"]["why"] and fake.landed_calls == [("h1.1", True)]
    queue.save([])
    lane(state)
    assert run(Fake(moved=False)) == 0
    assert steps()["1.1"]["state"] == "blocked" and "no commit" in steps()["1.1"]["why"]


def test_an_issue_of_a_landed_step_that_stayed_open_is_a_row_and_on_the_step_never_a_close(state):
    """Owner ruling: a step's issues close through `builder landed` on a Fixes line; what did not is reported, and the lane goes on."""
    lane(state)
    fake = Fake()
    fake.procs.still_open = lambda the_lane, step: ["#8"] if step["step"] == "1.2" else []
    assert run(fake) == 0
    assert steps()["1.1"]["state"] == "landed" and "open" not in steps()["1.1"]["why"]
    assert steps()["1.2"]["state"] == "landed" and "still open: #8" in steps()["1.2"]["why"]
    assert [(r["step"], r["detail"]) for r in journal.read() if r["event"] == "queue" and r["state"] == "issue-open"] == [("1.2", "#8")]
    assert queue.load()[0]["cursor"] == 2


def test_the_open_check_reads_each_issue_from_gh_and_says_when_it_cannot(tmp_path):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\ncase "$3" in 1) echo OPEN ;; 2) echo CLOSED ;; *) echo boom >&2; exit 1 ;; esac\n')
    gh.chmod(0o755)
    assert queue.open_of([1, 2, 3], str(gh)) == ["#1", "#3 (could not read)"]


def test_a_rebase_conflict_before_the_next_step_blocks_that_step(state):
    lane(state)
    assert run(Fake(rebase="rebase could not finish")) == 0
    assert steps()["1.1"]["state"] == "landed" and steps()["1.2"]["state"] == "blocked" and "could not finish" in steps()["1.2"]["why"]


def test_a_gone_worker_gets_a_new_session_on_the_same_step_and_a_parked_one_blocks(state):
    lane(state)
    fake = Fake()
    handles = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert steps()["1.1"]["state"] == "sent"
    fake.alive_now, fake.seqs = False, set()
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert [s[1:] for s in fake.starts] == [("1.1", 1), ("1.1", 2)], "a fresh sequence number: the old session's row cannot answer"
    fake.alive_now, fake.end = False, "parked"
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert steps()["1.1"]["state"] == "blocked" and "parked" in steps()["1.1"]["why"]


def test_an_owner_restart_stops_the_old_session_before_starting_a_new_one(state):
    """No handle for a sent step: the old session may still be up, and two workers must never share a worktree."""
    lane(state)
    fake = Fake()
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    fake.seqs = set()
    handles = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.stops == ["m1"] and len(fake.starts) == 1 and steps()["1.1"]["state"] == "queued"
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert len(fake.starts) == 2


def test_pause_leaves_the_worker_idle_with_nothing_sent_and_resume_sends_the_next_brief(state):
    lane(state)
    fake = Fake()
    handles = {}
    for _ in range(2):
        queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert steps()["1.1"]["state"] == "landed"
    assert cli.main(["queue", "pause", "--lane", "m1", "--state", str(state / "s")]) == 0
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.sent == [] and not fake.stops
    assert cli.main(["queue", "resume", "--lane", "m1", "--state", str(state / "s")]) == 0
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    assert fake.sent == ["brief 1.2"]


def test_the_worker_cap_holds_a_second_lane_back_until_the_first_is_finished(state):
    lane(state)
    queue.add("m2", "/w/m2", "1.1", str(state / "b1.1"), [9])
    fake = Fake()
    assert run(fake) == 0
    assert [s[0] for s in fake.starts] == ["m1", "m2"] and fake.stops == ["m1", "m2"]


def test_add_merges_steps_into_a_lane_and_keeps_their_state_and_the_verb_refuses_without_its_arguments(state, capsys):
    lane(state)
    items = queue.load()
    items[0]["steps"][0]["state"] = "landed"
    queue.save(items)
    lane(state)
    assert [s["state"] for s in queue.load()[0]["steps"]] == ["landed", "queued"] and len(queue.load()) == 1
    assert cli.main(["queue", "add", "--lane", "m1", "--state", str(state / "s")]) == 1
    assert "needs" in capsys.readouterr().out
    assert cli.main(["queue", "add", "--lane", "m9", "--worktree", "/w", "--step", "1.1", "--brief", "/b", "--issues", "3", "--state", str(state / "s")]) == 0
    assert queue.load()[1]["steps"][0]["issues"] == [3]


def test_the_bare_verb_shows_each_step(state, capsys):
    lane(state)
    assert cli.main(["queue", "--state", str(state / "s")]) == 0
    assert capsys.readouterr().out.startswith("m1\t1.1\tqueued\t#7\t")


def test_the_workers_cap_comes_from_the_rules_file_and_defaults_to_one(state, tmp_path):
    assert queue.workers(state) == 2 and queue.workers(tmp_path / "nowhere") == 1


def test_the_real_landing_reads_the_lanes_own_verdict_store(state):
    argv = queue.landed_argv(state, "m1", "abc1234def", True)
    assert argv[3:5] == ["landed", "abc1234def"] and argv[argv.index("--verdicts") + 1] == str(state / "s" / "verdicts-m1.json") and argv[-1] == "--push"
    assert "--keep-worktree" in argv, "the lane's session is still working in that worktree"
    assert argv[argv.index("--lane") + 1] == "m1", "the landing names its lane on its spec-ok-proposed rows (review -82)"


def test_the_real_start_makes_the_worktree_and_runs_the_worker_side_with_its_feed_as_the_jail_user(state, monkeypatch):
    """The owner cannot read the worker's session file, so `builder run --feed` runs as the jail user; the feed folder is the
    owner's (a worker cannot write its own next brief)."""
    (state / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[jail]\nuser = "wu"\nworkroot = "' + str(state / "wr") + '"\n'
                                        '[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n')
    (state / "wr").mkdir()
    scripts, popens = [], []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: (scripts.append(s), type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())[1])
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv) or object())
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)  # the pinned copy the worker imports from (#6466)
    procs = queue.real_procs(state)
    the_lane = {"id": "m1", "worktree": str(state / "wr" / "wt-m1"), "seq": 3}
    procs.start(the_lane, {"step": "1.1", "brief": str(state / "b1.1"), "issues": [7]})
    assert "worktree add" in scripts[0] and "lane-m1" in scripts[0] and "origin/integration" in scripts[0] and str(state / "wr" / "root") in scripts[0]
    feed = Path(the_lane["feed"])
    assert feed.parent == state / "wr" and feed.name.startswith("inbox-m1-3-") and feed.is_dir() and not feed.is_symlink()
    assert popens[0][:5] == ["/usr/bin/sudo", "-n", "-H", "-u", "wu"] or popens[0][1:5] == ["-n", "-H", "-u", "wu"]
    cmd = popens[0][-1]
    assert f"--feed {feed}" in cmd and "--seq 3" in cmd and "--name m1" in cmd
    assert f"--brief {feed}/brief.txt" in cmd and (feed / "brief.txt").read_text() == "brief 1.1" and (feed / "brief.txt").stat().st_mode & 0o777 == 0o644, \
        "#6466: the brief under the owner's state dir is unreadable by the jail user; its copy in the inbox is what the worker reads"
    procs.send({**the_lane, "seq": 4}, "next")
    assert (feed / "msg-4.txt").read_text() == "next"
    procs.stop(the_lane)
    assert (feed / "stop").exists()


def test_a_planted_inbox_cannot_turn_the_owners_chmod_or_writes_on_another_folder(state, monkeypatch):
    """The workroot is world-writable, so a predictable inbox name could be a worker's symlink to the owner's home: mkdir accepted it,
    chmod followed it, and send and stop wrote through it as the owner. The owner's folder is made exclusively under a name it picks."""
    wr, private = state / "wr", state / "private"
    wr.mkdir(), private.mkdir()
    private.chmod(0o700)
    (state / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[jail]\nuser = "wu"\nworkroot = "' + str(wr) + '"\n'
                                        '[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n')
    (wr / "inbox-m1-3").symlink_to(private)
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda root, brief, base: str(state))
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "d" * 40)
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: object())
    the_lane = {"id": "m1", "worktree": str(wr / "wt-m1"), "seq": 3}
    procs = queue.real_procs(state)
    procs.start(the_lane, {"step": "1.1", "brief": str(state / "b1.1"), "issues": [7]})
    procs.send({**the_lane, "seq": 4}, "next")
    procs.stop(the_lane)
    assert private.stat().st_mode & 0o777 == 0o700 and list(private.iterdir()) == [], "nothing reached the folder the link points at"
    assert (Path(the_lane["feed"]) / "msg-4.txt").read_text() == "next"


def test_a_relative_worktree_is_stored_absolute(state, monkeypatch):
    """The worker's side resolves from the workroot and the owner's from its cwd: a relative path would mean two places."""
    monkeypatch.chdir(state)
    queue.add("m3", "rel/wt", "1.1", "/b", [1])
    assert queue.load()[-1]["worktree"] == str(Path.cwd() / "rel" / "wt")


def test_a_gh_that_times_out_or_is_missing_counts_as_unread_and_the_lane_goes_on(state, tmp_path, monkeypatch):
    """Review of range 5: after the push, a traceback here killed the loop before the cursor moved, and a restart then blocked a step that had landed."""
    assert queue.open_of([1], str(tmp_path / "no-such-gh")) == ["#1 (could not read)"]

    def slow(argv, **k):
        raise queue.subprocess.TimeoutExpired(argv, 60)
    monkeypatch.setattr(queue.subprocess, "run", slow)
    assert queue.open_of([2]) == ["#2 (could not read)"]


def test_the_open_check_runs_from_the_repo_so_gh_knows_which_one(state, monkeypatch):
    seen = {}

    def run(argv, **k):
        seen.update(k)
        return type("R", (), {"returncode": 0, "stdout": "CLOSED", "stderr": ""})()
    monkeypatch.setattr(queue.subprocess, "run", run)
    assert queue.open_of([1], cwd="/repo") == [] and seen["cwd"] == "/repo"


def _feeding(fake, state, names):
    """The build order as a fake: each milestone one step `<name>.1`; next_milestone hands out the first one no lane holds."""
    for n in names:
        (state / f"b{n}").write_text(f"brief {n}")
    taken_log = []

    def next_milestone(taken):
        n = next((x for x in names if x not in taken), None)
        if n is None:
            return None
        taken_log.append(n)
        return n, f"/w/{n}", [{"step": f"{n}.1", "brief": str(state / f"b{n}"), "issues": [1], "waits": []}]
    fake.procs.next_milestone = next_milestone
    return taken_log


def test_the_queue_rolls_on_to_the_next_build_order_milestone_when_a_lanes_steps_have_landed(state):
    """Owner 2026-11-02: one command runs a spec to the end, then the next build-order milestone, until the order is done."""
    fake = Fake()
    taken = _feeding(fake, state, ["ma", "mb", "mc"])
    assert queue.run(fake.procs, workers_n=1, push=True, lanes_n=1, out=lambda s: None) == 0
    assert taken == ["ma", "mb", "mc"] and [s[0] for s in fake.starts] == ["ma", "mb", "mc"], "one milestone at a time, in order"
    assert fake.landed_calls == [("hma.1", True), ("hmb.1", True), ("hmc.1", True)]
    assert all(x["cursor"] == len(x["steps"]) for x in queue.load())


def test_a_finished_milestone_gets_one_dev_build_and_a_failed_build_is_an_alert_while_the_roll_on_goes_on(state):
    """run.loop-rolls-on: `builder build --dev` after each milestone; a failure is an alert row, never a stop."""
    fake = Fake()
    taken = _feeding(fake, state, ["ma", "mb", "mc"])
    built = []
    fake.procs.build = lambda lane: (built.append(lane["id"]), (1, "FAILED: exit 65") if lane["id"] == "ma" else (0, "PASSED x.dmg"))[1]
    assert queue.run(fake.procs, workers_n=1, push=True, lanes_n=1, out=lambda s: None) == 0
    assert taken == ["ma", "mb", "mc"] and built == ["ma", "mb", "mc"], "one build per milestone, and the failed one did not stop the order"
    alerts = [r for r in journal.read() if r["event"] == "alert"]
    assert [(a["lane"], a["step"]) for a in alerts] == [("ma", "build")] and "exit 65" in alerts[0]["what"]
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r["state"] in ("built", "build-failed")] == ["build-failed", "built", "built"]


def test_the_dev_build_never_holds_a_tick_the_loops_other_lanes_wait_on(state):
    """2026-11-02: harness-unblock landed, its inline `builder build --dev` ran 17 minutes inside the tick, and no lane was checked
    for that long. With the loop's chains the build runs in its own thread and the tick returns at once."""
    import threading
    import time
    fake = Fake()
    queue.add("ma", "/w/ma", "1.1", str(state / "b1.1"), [])
    lanes = queue.load()
    lanes[0]["steps"][0]["state"], lanes[0]["cursor"] = "landed", 1
    queue.save(lanes)
    release, started = threading.Event(), threading.Event()
    fake.procs.build = lambda lane: (started.set(), release.wait(10), (0, "PASSED x.dmg"))[2]
    t0 = time.time()
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None, chains={"pool": None})
    assert time.time() - t0 < 2 and started.wait(5), "the tick returned while the build was still running"
    assert queue.load()[0]["built"] is True
    release.set()
    for t in list(queue.BUILDS):
        t.join(5)
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r["state"] in ("built", "build-failed")] == ["built"]


def test_a_question_stops_the_roll_on_and_the_next_milestone_is_not_taken(state):
    fake = Fake(chains={"mb.1": [{"ok": False, "kind": "error", "why": "the ladder could not start"}]})
    taken = _feeding(fake, state, ["ma", "mb", "mc"])
    assert queue.run(fake.procs, workers_n=1, push=True, lanes_n=1, out=lambda s: None) == 0
    assert taken == ["ma", "mb"], "mb is blocked on a QUESTION: it holds the one lane"
    assert (journal.STATE / "question-mb-mb.1.txt").is_file()


def test_n_lanes_hold_n_milestones_and_their_chains_overlap_but_the_ladder_is_one_at_a_time(state):
    """`--lanes 2`: two milestones at once; a lane's check waits only for the ladder lock, never for the other lane's work."""
    import threading
    import time

    fake = Fake()
    taken = _feeding(fake, state, ["ma", "mb", "mc"])
    started = {n: threading.Event() for n in ("ma", "mb", "mc")}
    held, peak, log = [0], [0], []
    base_chain = fake.chain

    def chain(lane, step, stage):
        started[lane["id"]].set()
        if lane["id"] == "ma" and not started["mb"].wait(10):  # ma's chain is still running when mb's starts
            return {"ok": False, "kind": "error", "why": "mb's chain waited for ma's"}
        with journal.Lock("ladder"):
            held[0] += 1
            peak[0] = max(peak[0], held[0])
            time.sleep(0.05)
            held[0] -= 1
        log.append(lane["id"])
        return base_chain(lane, step, stage)
    fake.procs.chain = chain
    active_peak = [0]
    orig_start = fake.procs.start

    def start(lane, step):
        active_peak[0] = max(active_peak[0], sum(1 for x in queue.load() if x["cursor"] < len(x["steps"])))
        return orig_start(lane, step)
    fake.procs.start = start
    assert queue.run(fake.procs, workers_n=2, push=True, lanes_n=2, out=lambda s: None) == 0
    assert taken == ["ma", "mb", "mc"] and set(log) == {"ma", "mb", "mc"}, "ma landed: mb's chain started while ma's ran"
    assert peak[0] == 1, "one ladder at a time"
    assert active_peak[0] == 2, "never more than two milestones held"
    assert sorted(h for h, _ in fake.landed_calls) == ["hma.1", "hmb.1", "hmc.1"]


def test_a_blocked_step_labels_its_issues_needs_your_decision_and_comments_the_question(state, tmp_path):
    """#6343: a QUESTION was only a file and a row; the owner could not see it from GitHub (issues-and-labels: a question labels
    needs-your-decision and comments). A gh that fails is a row, never a traceback; resume takes the label off."""
    calls = tmp_path / "calls"
    gh = tmp_path / "gh"
    gh.write_text(f'#!/bin/sh\necho "$*" >> {calls}\n')
    gh.chmod(0o755)
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "error", "why": "rules file broken"}]})
    assert run(fake) == 0 and steps()["1.1"]["state"] == "blocked"
    assert not calls.exists(), "since the loop's alerts (2026-11-02) a block goes to the manager first: ask-owner puts it on GitHub"
    (a,) = [r for r in journal.read() if r["event"] == "alert"]
    assert cli.main(["alert", a["id"], "ask-owner", "--state", str(state / "s"), "--gh", str(gh), "--root", str(state)]) == 0
    seen = calls.read_text().splitlines()
    assert "issue edit 7 --add-label needs-your-decision" in seen
    assert any(x.startswith("issue comment 7 --body QUESTION (queue m1 1.1): rules file broken") for x in seen), seen
    queue.ask([7], "m1 1.1", "x", gh=str(tmp_path / "no-such-gh"))  # never raises
    assert [r for r in journal.read() if r["event"] == "queue" and r.get("state") == "ask-failed"]
    assert cli.main(["queue", "resume", "--lane", "m1", "--state", str(state / "s"), "--gh", str(gh)]) == 0
    assert "issue edit 7 --remove-label needs-your-decision" in calls.read_text().splitlines()


def test_ticked_issues_become_one_lane_with_one_cluster_brief(state, monkeypatch):
    """Owner 2026-11-02: tick issues in the console and Start as one lane: `builder lane <name> --issues N...`."""
    from fichero_builder import brief_tool, land_tool
    (state / "harness.toml").write_text(state.joinpath("harness.toml").read_text() + f'[jail]\nworkroot = "{state / "wr"}"\n')
    monkeypatch.setattr(brief_tool, "fetch_issue", lambda n, gh="gh": {"number": n, "title": f"issue {n}", "body": "b", "labels": []})
    monkeypatch.setattr(brief_tool, "cluster", lambda issues, **k: "BRIEF " + " ".join(f"#{i['number']}" for i in issues))
    monkeypatch.setattr(land_tool, "resolve_branch", lambda repo, b: "abc")
    rc, out = queue.lane_from_issues(state, "ux-fixes", [11, 12])
    assert rc == 0, out
    (ln,) = [x for x in queue.load() if x["id"] == "ux-fixes"]
    assert ln["kind"] == "worker" and ln["worktree"] == str(state / "wr" / "wt-ux-fixes") and ln["steps"][0]["issues"] == [11, 12]
    assert open(ln["steps"][0]["brief"]).read() == "BRIEF #11 #12"
    assert queue.lane_from_issues(state, "ux-fixes", [13])[0] == 1, "a working lane is not given a second cluster"


def test_the_watchdog_restarts_a_silent_loop_once_per_silence_and_names_the_new_pid(state, monkeypatch):
    """2026-11-02: the loop sat 17 min in one tick and nobody restarted it. `builder heartbeat --restart ROOT`: a new stale alert
    kills the loop in loop.pid (and its children), starts a new one, writes its pid; the same silence does nothing twice."""
    import subprocess as sp
    import time
    old = sp.Popen(["bash", "-c", "sleep 60 & sleep 60; wait"])  # a child and its own children, like a build's scripts
    time.sleep(0.3)
    journal.STATE.mkdir(parents=True, exist_ok=True)
    (journal.STATE / "loop.pid").write_text(f"{old.pid}\n")
    spawned = []
    shim = type("S", (), {"run": staticmethod(sp.run), "DEVNULL": sp.DEVNULL,
                          "Popen": staticmethod(lambda argv, **kw: spawned.append(argv) or type("P", (), {"pid": 424242})())})
    monkeypatch.setattr(queue, "subprocess", shim)  # only the new loop's start is faked; pkill runs for real
    journal.append("loop", state="tick", lanes=[], busy=False)
    rows = journal.read()
    far = time.mktime(time.strptime(rows[-1]["ts"], "%Y-%m-%dT%H:%M:%S")) + 400
    aid = queue.heartbeat_check(30.0, 3, now=far)
    assert aid and queue.restart_loop("/root", 30.0) == 424242
    old.wait(5)
    assert old.returncode is not None, "the stale loop was killed"
    assert sp.run(["pgrep", "-P", str(old.pid)], capture_output=True).returncode == 1, "and its children"
    assert (journal.STATE / "loop.pid").read_text().strip() == "424242" and "loop" in spawned[0] and "/root" in spawned[0]
    assert queue.heartbeat_check(30.0, 3, now=far + 60) is None, "once per silence"
    assert any(r.get("event") == "loop" and r.get("state") == "restarted" and r.get("pid") == 424242 for r in journal.read())


def test_the_watchdog_refuses_with_no_loop_pid_and_starts_no_second_loop(state, monkeypatch):
    """Review 2026-11-02: with no loop.pid the restart killed nothing and started a second loop beside the stuck one."""
    spawned = []
    monkeypatch.setattr(queue.subprocess, "Popen", lambda *a, **k: spawned.append(a) or None)
    assert queue.restart_loop("/root", 30.0) == 0 and not spawned
    assert any(r.get("event") == "loop" and r.get("state") == "restart-refused" for r in journal.read())


def test_a_ladder_cancelled_by_a_newer_head_ends_without_an_alert_a_tell_or_a_finding(state):
    """Manager 2026-11-03 (sharing 31c10f84a cancelled by the resubmit still raised alert -118 and a findings tell): resubmit mid-ladder."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    fake = Fake()
    told = []
    fake.procs.tell = lambda lane, text: told.append(text) or ""
    inside, release = threading.Event(), threading.Event()

    def chain(lane, step, stage):
        stage("checking"), inside.set(), release.wait(10)
        return {"ok": False, "kind": "red", "why": "cancelled: superseded by a newer head", "findings": "guards: cancelled", "head": "old000000"}
    fake.procs.chain = chain
    queue.add("ext", "/w/ext", "batch-1", str(state / "b1.1"), [], kind="external", pane="%7")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head="old000000")
    queue.save(lanes)
    with ThreadPoolExecutor(1) as pool:
        chains = {"pool": pool}
        queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None, chains=chains)
        assert inside.wait(5)
        lanes = queue.load()  # `builder done` at the newer head, mid-guards
        lanes[0]["steps"][0].update(state="done", head="new000000")
        queue.save(lanes)
        release.set()
        chains["ext"].result(5)
        queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None, chains=chains)
    assert not [r for r in journal.read() if r["event"] == "alert"], "no alert row for the cancelled ladder"
    assert told == [], "and nothing is told to the lane"
    assert any(r.get("state") == "stale-result" for r in journal.read() if r["event"] == "queue")
    s = queue.load()[0]["steps"][0]
    assert s["head"] == "new000000" and s["state"] == "done", "the newer head is untouched"


def test_a_product_landing_earns_one_verify_all_once_every_lane_is_idle_and_a_harness_only_landing_earns_none(state):
    """dev-workflows.run.verify-all (manager 2026-11-03): one verify-all after a product landing, never pushing, red = an alert."""
    for product, want in ((True, ["run"]), (False, [])):
        fake = Fake()
        ran = []
        fake.procs.touches_product = lambda lane, head, p=product: p
        fake.procs.verify_all = lambda: (ran.append("run"), (1, "NOT VERIFIED abc") if product else (0, ""))[1]
        queue.add(f"l{product}", "/w/x", "1.1", str(state / "b1.1"), [])
        assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
        assert ran == want, f"product={product}"
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r["state"] in ("verified", "verify-failed")] == ["verify-failed"]
    assert [r["step"] for r in journal.read() if r["event"] == "alert"] == ["verify"], "a red verify-all is an alert"
    assert not (journal.STATE / queue.VERIFY_PENDING).exists(), "the marker is consumed: once per landing"


def test_verify_all_runs_when_the_milestone_is_complete_not_after_every_product_landing(state):
    """owner 2026-11-03: a worker lane's first of two steps landing earns nothing; its last earns one. External lanes: the manual verb."""
    fake = Fake()
    ran = []
    fake.procs.touches_product = lambda lane, head: True
    fake.procs.verify_all = lambda: (ran.append(1), (0, "VERIFIED"))[1]
    queue.add("l", "/w/x", "1.1", str(state / "b1.1"), [])
    queue.add("l", "/w/x", "1.2", str(state / "b1.2"), [], waits=["1.1"])
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert ran == [] and [x["state"] for x in queue.load()[0]["steps"]].count("landed") <= 1
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert ran == [1] and [x["state"] for x in queue.load()[0]["steps"]] == ["landed", "landed"]


def test_verify_all_waits_while_a_lane_is_busy_and_never_runs_for_an_unpushed_landing(state):
    fake = Fake()
    ran = []
    fake.procs.verify_all = lambda: (ran.append(1), (0, "VERIFIED"))[1]
    queue.add("l", "/w/x", "1.1", str(state / "b1.1"), [])
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    assert ran == [] and not (journal.STATE / queue.VERIFY_PENDING).exists(), "push=False: nothing landed for real"
    (journal.STATE / queue.VERIFY_PENDING).write_text("abc")
    queue.add("busy", "/w/y", "1.1", str(state / "b1.1"), [])
    assert queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None) is True and ran == [], "a lane with work left: not yet"



def test_the_daily_builds_run_once_a_day_busy_lanes_or_not_and_a_red_one_is_an_alert(state):
    """#6390 (owner 2026-11-07): the iOS app and the Swift test target, built once a day; no [check.daily_builds] = never."""
    fake = Fake()
    queue.add("busy", "/w/y", "1.1", str(state / "b1.1"), [])
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert not (journal.STATE / queue.DAILY).exists(), "no daily builds declared: nothing runs"
    ran = []
    fake.procs.daily_builds = lambda: (ran.append(1), (1, "ios-sim: GREEN\ntests: RED T.swift:26:9: error: cannot find 'X' (log l)"))[1]
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert ran == [1], "once a day, though a lane is busy"
    assert [r["state"] for r in journal.read() if r["event"] == "daily-builds"] == ["red"]
    alerts = [r for r in journal.read() if r["event"] == "alert"]
    assert len(alerts) == 1 and alerts[0]["step"] == "daily-builds" and "tests: RED T.swift:26:9" in alerts[0]["what"]
    (journal.STATE / queue.DAILY).write_text(f"{queue.time.time() - queue.DAILY_S - 1}\n")
    fake.procs.daily_builds = lambda: (ran.append(2), (0, "ios-sim: GREEN\ntests: GREEN"))[1]
    queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None)
    assert ran == [1, 2] and len([r for r in journal.read() if r["event"] == "alert"]) == 1, "a day later: again; green = no alert"

def test_a_lane_named_in_opus_lanes_gets_the_full_reviewer_and_others_the_fast_one(state, monkeypatch):
    """Owner 2026-11-06 (t28): [models].opus_lanes; a named lane's batches always get the full reviewer, any other the fast one."""
    (state / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n'
                                        '[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "sonnet" }\n'
                                        'reviewer = { provider = "claude-code", model = "opus" }\nreviewer_fast = { provider = "claude-code", model = "sonnet" }\n'
                                        'opus_lanes = ["lane-sharing"]\n')
    seen = {}
    monkeypatch.setattr(queue, "carry_in_lane", lambda *a, **k: False)
    monkeypatch.setattr(queue.work, "ensure_pinned", lambda *a, **k: "/p")
    monkeypatch.setattr(queue.land_tool, "resolve_branch", lambda repo, branch: "b" * 40)
    monkeypatch.setattr(queue.work, "after_run", lambda a, repo, branch, reviewer, stage=None: seen.setdefault(a.name, a.reviewer_fast) and {"ok": True})
    procs = queue.real_procs(state)
    for lane in ("lane-sharing", "lane-ie"):
        procs.chain({"id": lane, "worktree": "/w", "kind": "external"}, {"step": "b1", "brief": "/b", "issues": []}, lambda s: None)
    assert seen == {"lane-sharing": "opus", "lane-ie": "sonnet"}


def test_queue_move_park_and_unpark_reorder_the_steps_behind_the_cursor_under_the_lock_and_refuse_the_rest(state, capsys):
    """#6467 (run.loop-plan): the owner orders a lane's queue from the console; the verbs behind it. `move --to N` puts a queued or
    parked step at position N among the steps from the cursor on; the cursor's own step and a landed one never move; `park` sends a
    queued or blocked step to the end as parked; `unpark` makes a parked step queued. Each is one `queue` row."""
    for n in ("1.1", "1.2", "1.3", "1.4"):
        queue.add("m1", "/w/m1", n, str(state / "b1.1"), [])
    lanes = queue.load()
    lanes[0]["steps"][0]["state"], lanes[0]["cursor"] = "landed", 1
    queue.save(lanes)
    st = ["--state", str(journal.STATE)]
    assert cli.main(["queue", "move", "--lane", "m1", "--step", "1.4", "--to", "1", *st]) == 0
    assert [s["step"] for s in queue.load()[0]["steps"]] == ["1.1", "1.4", "1.2", "1.3"], "1.4 is now the cursor's step"
    assert cli.main(["queue", "move", "--lane", "m1", "--step", "1.1", "--to", "3", *st]) == 1 and "REFUSED" in capsys.readouterr().out, "a landed step"
    assert cli.main(["queue", "park", "--lane", "m1", "--step", "1.4", *st]) == 0
    assert [(s["step"], s["state"]) for s in queue.load()[0]["steps"]][1:] == [("1.2", "queued"), ("1.3", "queued"), ("1.4", "parked")]
    assert cli.main(["queue", "unpark", "--lane", "m1", "--step", "1.4", *st]) == 0
    assert queue.load()[0]["steps"][-1]["state"] == "queued"
    assert cli.main(["queue", "move", "--lane", "m1", "--step", "1.4", "--to", "9", *st]) == 0, "past the end: the end"
    assert cli.main(["queue", "move", "--lane", "m1", "--step", "1.4", "--to", "0", *st]) == 0 and [s["step"] for s in queue.load()[0]["steps"]] == ["1.1", "1.4", "1.2", "1.3"], "before the cursor: at the cursor"
    assert cli.main(["queue", "park", "--lane", "m1", "--step", "1.1", *st]) == 1, "a landed step is never parked"
    assert cli.main(["queue", "move", "--lane", "zz", "--step", "1.1", "--to", "1", *st]) == 1
    assert [r["state"] for r in journal.read() if r.get("event") == "queue" and r.get("lane") == "m1" and r.get("state") in ("moved", "parked", "unparked")] == ["moved", "parked", "unparked", "moved", "moved"]
