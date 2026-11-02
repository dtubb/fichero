"""dev-workflows.tool.queue: one long-running worker per lane (a milestone), fed step by step: after DONE the queue checks,
reviews and lands that step, then sends the next brief into the SAME session; findings go back as a fix brief; a new session
only when the worker is gone. The processes are fakes; the transitions and rows are real."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue, watch


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


def test_the_bare_verb_and_the_watch_page_show_each_step(state, capsys):
    lane(state)
    assert cli.main(["queue", "--state", str(state / "s")]) == 0
    assert capsys.readouterr().out.startswith("m1\t1.1\tqueued\t#7\t")
    html = watch.render(journal.read())
    assert "m1" in html and ">queued<" in html and "#8" in html and "1.1" in html


def test_the_workers_cap_comes_from_the_rules_file_and_defaults_to_one(state, tmp_path):
    assert queue.workers(state) == 2 and queue.workers(tmp_path / "nowhere") == 1


def test_the_real_landing_reads_the_lanes_own_verdict_store(state):
    argv = queue.landed_argv(state, "m1", "abc1234def", True)
    assert argv[3:5] == ["landed", "abc1234def"] and argv[argv.index("--verdicts") + 1] == str(state / "s" / "verdicts-m1.json") and argv[-1] == "--push"
    assert "--keep-worktree" in argv, "the lane's session is still working in that worktree"


def test_the_real_start_makes_the_worktree_and_runs_the_worker_side_with_its_feed_as_the_jail_user(state, monkeypatch):
    """The owner cannot read the worker's session file, so `builder run --feed` runs as the jail user; the feed folder is the
    owner's (a worker cannot write its own next brief)."""
    (state / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[jail]\nuser = "wu"\nworkroot = "' + str(state / "wr") + '"\n'
                                        '[models]\nproviders = ["claude-code"]\nbuilder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n')
    (state / "wr").mkdir()
    scripts, popens = [], []
    monkeypatch.setattr(queue.work, "as_worker", lambda a, s: (scripts.append(s), type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())[1])
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: popens.append(argv) or object())
    procs = queue.real_procs(state)
    the_lane = {"id": "m1", "worktree": str(state / "wr" / "wt-m1"), "seq": 3}
    procs.start(the_lane, {"step": "1.1", "brief": str(state / "b1.1"), "issues": [7]})
    assert "worktree add" in scripts[0] and "lane-m1" in scripts[0] and "origin/integration" in scripts[0] and str(state / "wr" / "root") in scripts[0]
    feed = Path(the_lane["feed"])
    assert feed.parent == state / "wr" and feed.name.startswith("inbox-m1-3-") and feed.is_dir() and not feed.is_symlink()
    assert popens[0][:5] == ["/usr/bin/sudo", "-n", "-H", "-u", "wu"] or popens[0][1:5] == ["-n", "-H", "-u", "wu"]
    cmd = popens[0][-1]
    assert f"--feed {feed}" in cmd and "--seq 3" in cmd and "--name m1" in cmd
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
    monkeypatch.setattr(queue.subprocess, "Popen", lambda argv, **k: object())
    the_lane = {"id": "m1", "worktree": str(wr / "wt-m1"), "seq": 3}
    procs = queue.real_procs(state)
    procs.start(the_lane, {"step": "1.1", "brief": "/b", "issues": [7]})
    procs.send({**the_lane, "seq": 4}, "next")
    procs.stop(the_lane)
    assert private.stat().st_mode & 0o777 == 0o700 and list(private.iterdir()) == [], "nothing reached the folder the link points at"
    assert (Path(the_lane["feed"]) / "msg-4.txt").read_text() == "next"


def test_a_relative_worktree_is_stored_absolute(state, monkeypatch):
    """The worker's side resolves from the workroot and the owner's from its cwd: a relative path would mean two places."""
    monkeypatch.chdir(state)
    queue.add("m3", "rel/wt", "1.1", "/b", [1])
    assert queue.load()[-1]["worktree"] == str(Path.cwd() / "rel" / "wt")
