"""dev-workflows.run.loop (Steps 2.9-2.11): `builder loop` keeps every lane going with no person: DONE -> fetch -> check ->
review -> landed --push -> the next step; a red goes back to the worker; every tick a heartbeat row. Processes are fakes."""
from __future__ import annotations

import os

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue, watch
from test_queue_verb import Fake, lane, steps


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/e"\n[land]\nbranch = "integration"\n[loop]\nlanes = 1\nrounds = 1\n')
    return tmp_path


def test_a_restart_mid_chain_resumes_the_step_and_never_lands_it_twice(state):
    """run.loop: killed between check and land, a fresh loop (new handles) picks the step up where the journal left it."""
    lane(state)
    fake = Fake()
    crashed = []

    def chain(lane_, step, stage):
        if not crashed:
            stage("checking")
            crashed.append(1)
            raise KeyboardInterrupt  # the process dies mid-chain
        return Fake.chain(fake, lane_, step, stage)
    fake.procs.chain = chain
    with pytest.raises(KeyboardInterrupt):
        queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert steps()["1.1"]["state"] == "checking"
    assert queue.run(fake.procs, workers_n=1, push=True, heartbeat=True, out=lambda s: None) == 0
    assert fake.landed_calls == [("h1.1", True), ("h1.2", True)], "each step landed once"
    assert [r for r in journal.read() if r["event"] == "loop" and r.get("state") == "tick"], "a heartbeat row a tick"
    assert (journal.STATE / "loop.pid").read_text().strip() == str(os.getpid()), "the loop names itself for the watchdog"


def test_a_red_with_no_live_session_starts_a_new_one_on_a_fix_brief_with_the_findings(state):
    """run.loop-fix-rounds / run.loop-tell: the findings went into the feed of a session that was gone; now a new session
    starts on the step's brief plus the findings."""
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "red", "why": "ladder red", "findings": "test_x failed"}]})
    started, base_chain, base_start = [], fake.procs.chain, fake.procs.start

    def chain(lane_, step, stage):
        if step["step"] == "1.1" and fake.chains.get("1.1"):
            fake.alive_now = False  # the session is gone by the time its first check is red
        return base_chain(lane_, step, stage)

    def start(lane_, step):
        started.append(step.get("resume_brief") or step["brief"])
        return base_start(lane_, step)
    fake.procs.chain, fake.procs.start = chain, start
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert len(started) >= 2 and started[0] == str(state / "b1.1"), started
    fix = open(started[1]).read()
    assert "test_x failed" in fix and "brief 1.1" in fix, "the new session gets the brief and the findings"
    assert fake.sent == ["brief 1.2"], "nothing was written into the dead session's feed"


def test_rounds_come_from_the_loop_table(state, monkeypatch):
    calls = {}
    monkeypatch.setattr(queue, "ROUNDS", queue.ROUNDS)  # restored after: the verb sets the module's round count
    monkeypatch.setattr(queue, "real_procs", lambda root: Fake().procs)
    monkeypatch.setattr(queue, "run", lambda procs, **k: calls.update(k) or 0)
    assert cli.main(["loop", "--root", str(state), "--state", str(state / "s")]) == 0
    assert calls["push"] is True and calls["forever"] is True and calls["heartbeat"] is True and calls["lanes_n"] == 1
    assert queue.ROUNDS == 1, "[loop].rounds"


def test_tell_puts_a_finding_into_the_live_session_and_refuses_with_a_row_when_there_is_none(state, capsys):
    lane(state)
    feed = state / "feed"
    feed.mkdir()
    lanes = queue.load()
    lanes[0].update(feed=str(feed), seq=3)
    queue.save(lanes)
    assert cli.main(["queue", "tell", "--lane", "m1", "--text", "capability reference stale: run the generator", "--state", str(state / "s")]) == 0
    assert (feed / "msg-4.txt").read_text().startswith("capability reference stale") and queue.load()[0]["seq"] == 4
    lanes = queue.load()
    lanes[0]["feed"] = ""
    queue.save(lanes)
    assert cli.main(["queue", "tell", "--lane", "m1", "--text", "x", "--state", str(state / "s")]) == 1
    assert "no live session" in capsys.readouterr().out
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r.get("state") in ("told", "tell-refused")] == ["told", "tell-refused"]


def _alerts():
    return [r for r in journal.read() if r["event"] == "alert"]


def test_every_stop_is_an_alert_with_evidence_and_actions_and_retry_lands_it(state, tmp_path):
    """run.loop-alerts: the manager reads one row (what, evidence, actions) and answers with one verb."""
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "error", "why": "the ladder could not start", "evidence": "/s/ladder-m1.json"}]})
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["lane"] == "m1" and a["step"] == "1.1" and "could not start" in a["what"] and a["evidence"] == "/s/ladder-m1.json"
    assert a["actions"] == ["retry", "park", "ask-owner"]
    assert cli.main(["alert", a["id"], "launch", "--state", str(state / "s")]) == 1, "an action the alert does not offer is refused"
    assert cli.main(["alert", a["id"], "retry", "--state", str(state / "s")]) == 0
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert steps()["1.1"]["state"] == "landed" and steps()["1.2"]["state"] == "landed"
    assert [(r["action"], r["ok"]) for r in journal.read() if r["event"] == "alert-answer"] == [("launch", False), ("retry", True)]


def test_needs_maintainer_is_an_alert_with_the_pinned_diff_and_approve_reruns_as_maintainer(state):
    """run.loop-needs-maintainer: a pinned file changed on purpose is the manager's call, not the worker's."""
    lane(state)
    seen = []
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "needs-maintainer", "why": "pinned-checks: scripts/verify_workflows.py changed",
                                 "evidence": "/s/pinned-m1.diff"}]})
    base_chain = fake.procs.chain
    fake.procs.chain = lambda lane_, step, stage: seen.append(bool(step.get("maintainer"))) or base_chain(lane_, step, stage)
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["actions"] == ["approve", "send-back"] and a["evidence"] == "/s/pinned-m1.diff"
    assert steps()["1.1"]["rounds"] == 0, "never sent back to the worker on its own"
    assert cli.main(["alert", a["id"], "approve", "--state", str(state / "s")]) == 0
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert seen[:2] == [False, True] and steps()["1.1"]["state"] == "landed"


def test_send_back_and_ask_owner(state, tmp_path):
    calls = tmp_path / "calls"
    gh = tmp_path / "gh"
    gh.write_text(f'#!/bin/sh\necho "$*" >> {calls}\n')
    gh.chmod(0o755)
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "error", "why": "boom"}, {"ok": False, "kind": "error", "why": "boom again"}]})
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    first = _alerts()[-1]
    assert cli.main(["alert", first["id"], "ask-owner", "--state", str(state / "s"), "--gh", str(gh)]) == 0
    assert "issue edit 7 --add-label needs-your-decision" in calls.read_text()
    assert cli.main(["alert", first["id"], "send-back", "--state", str(state / "s")]) == 1, "not offered for an error"
    assert cli.main(["alert", first["id"], "park", "--state", str(state / "s")]) == 0
    assert steps()["1.1"]["state"] == "blocked"


def test_a_stale_heartbeat_is_one_alert_per_silence_and_a_fresh_one_is_none(state, capsys):
    """run.loop-alerts: the watchdog reads only the journal; no tick for more than three ticks is an alert, said once."""
    assert queue.heartbeat_check(30, 3) is not None, "no tick ever is stale"
    journal.append("loop", state="tick", lanes=[], busy=False)
    t = journal.read()[-1]["ts"]
    import time
    at = time.mktime(time.strptime(t, "%Y-%m-%dT%H:%M:%S"))
    assert queue.heartbeat_check(30, 3, now=at + 90) is None
    aid = queue.heartbeat_check(30, 3, now=at + 91)
    a = [r for r in journal.read() if r["event"] == "alert" and r["id"] == aid]
    assert a and a[0]["step"] == "heartbeat" and "91 s" in a[0]["what"] and a[0]["evidence"] == str(journal.path())
    assert queue.heartbeat_check(30, 3, now=at + 500) is None, "said once per silence"
    journal.append("loop", state="tick", lanes=[], busy=False)
    assert queue.heartbeat_check(30, 3) is None
    assert cli.main(["heartbeat", "--state", str(journal.STATE)]) == 0


def test_the_launch_agents_keep_the_loop_alive_and_run_the_watchdog_every_three_ticks(state):
    import plistlib
    paths = queue.launch_agents(state, state / "la", state=state / "s", tick_s=30)
    loop, hb = (plistlib.loads(p.read_bytes()) for p in paths)
    assert loop["KeepAlive"] is True
    assert loop["ProgramArguments"][1:4] == ["-m", "fichero_builder", "loop"] and "--state" in loop["ProgramArguments"]
    assert hb["StartInterval"] == 90 and hb["ProgramArguments"][1:4] == ["-m", "fichero_builder", "heartbeat"] and "KeepAlive" not in hb


def test_a_one_lane_chain_runs_beside_the_ticks_so_the_heartbeat_keeps_beating(state):
    """run.loop-alerts: a 15-minute ladder inside the tick would make every check a stale heartbeat."""
    import threading
    lane(state)
    fake = Fake()
    go, sleeps = threading.Event(), []

    def chain(lane_, step, stage):
        assert go.wait(5), "the ticks never went on while the chain ran"
        return Fake.chain(fake, lane_, step, stage)

    def sleep(s):
        sleeps.append(s)
        if len(sleeps) == 3:
            go.set()
    fake.procs.chain, fake.procs.sleep = chain, sleep
    assert queue.run(fake.procs, workers_n=1, push=True, heartbeat=True, out=lambda s: None) == 0
    assert fake.landed_calls == [("h1.1", True), ("h1.2", True)]
    assert sum(1 for r in journal.read() if r["event"] == "loop" and r.get("state") == "tick") >= 3


def test_builder_done_on_an_external_lane_lands_it_and_no_worker_is_started(state, capsys):
    """run.loop-external-lane: a plain Claude Code lane lands through the loop; a red is an alert, never a fix round."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    queue.add("ext", "/w/ext", "1.2", str(state / "b1.2"), [8], waits=["1.1"])
    fake = Fake(chains={"1.2": [{"ok": False, "kind": "red", "why": "pytest red", "findings": "t1 failed", "evidence": "/l.json"}]})
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert fake.starts == [] and steps()["1.1"]["state"] == "queued", "no worker: it waits for its DONE"
    assert cli.main(["done", "ext", "abc123", "--state", str(journal.STATE)]) == 0
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert fake.starts == [] and fake.landed_calls == [("h1.1", True)] and steps()["1.1"]["state"] == "landed"
    assert cli.main(["done", "ext", "def456", "--state", str(journal.STATE)]) == 0
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert steps()["1.2"]["state"] == "blocked" and fake.sent == [], "a red on an external lane is an alert, not a fix brief"
    assert [(r["lane"], r["evidence"]) for r in journal.read() if r["event"] == "alert"] == [("ext", "/l.json")]
    lane(state)
    assert cli.main(["done", "m1", "abc", "--state", str(journal.STATE)]) == 1 and "no external lane" in capsys.readouterr().out


def test_a_step_that_moves_another_lanes_tree_or_the_jail_root_alerts(state):
    """run.loop-machine-checked: after a step's DONE the jail root and every quiet lane's worktree are unmoved and clean as
    they were when it started; a moved one is an alert naming it, and the step itself still lands."""
    lane(state)
    queue.add("m2", "/w/m2", "2.1", str(state / "b1.1"), [9])
    lanes = queue.load()
    lanes[1]["paused"] = True  # quiet: its own worker never starts
    queue.save(lanes)
    world = {"/jail/root": "r1 clean", "/w/m2": "a1 clean"}
    fake = Fake()
    fake.procs.jail_root, fake.procs.trees = "/jail/root", lambda paths: {p: world[p] for p in paths}
    base_start = fake.procs.start

    def start(lane_, step):  # m1's worker commits in m2's tree on its first step
        if step["step"] == "1.1":
            world["/w/m2"] = "a2 dirty 1234"
        return base_start(lane_, step)
    fake.procs.start = start
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    (a,) = _alerts()
    assert a["lane"] == "m1" and a["step"] == "1.1" and "/w/m2: a1 clean -> a2 dirty 1234" in a["what"] and "/jail/root" not in a["what"]
    assert steps()["1.1"]["state"] == "landed" and steps()["1.2"]["state"] == "landed", "an alert, not a stop"
    assert "trees" not in steps()["1.1"], "the snapshot is spent at the check"


def test_a_landing_meanwhile_excuses_the_jail_root_and_a_busy_lane_is_not_checked(state):
    lane(state)
    queue.add("m2", "/w/m2", "2.1", str(state / "b1.1"), [9])
    world = {"/jail/root": "r1 clean", "/w/m2": "a1 clean"}
    fake = Fake()
    fake.procs.jail_root, fake.procs.trees = "/jail/root", lambda paths: {p: world[p] for p in paths}

    def row(lane_):  # by the DONE, another landing has refreshed the root and m2's own worker has committed
        world["/jail/root"], world["/w/m2"] = "r2 clean", "a2 clean"
        journal.append("landed", sha="x" * 40, step="jail-root", ok=True, detail="root fast-forwarded")
        return {"moved": True} if lane_["seq"] in fake.seqs else None
    fake.procs.row = row
    queue.run(fake.procs, workers_n=2, push=False, out=lambda s: None)
    assert _alerts() == []


def test_stop_tells_the_worker_closes_its_session_after_the_grace_and_resume_starts_a_fresh_one_from_the_tree(state):
    """`queue stop` (manager 2026-11-02): pause = no new step is fed; stop = the worker is told to commit what is green, its
    session is closed after the grace, the tree is kept, and resume starts a fresh session on the same step from the tree."""
    lane(state)
    fake = Fake()
    working = fake.procs.row
    fake.procs.row = lambda lane_: None  # the worker is mid-step
    handles: dict = {}

    def tick():
        queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    tick()
    assert steps()["1.1"]["state"] == "sent" and "m1" in handles
    feed = state / "feed"
    feed.mkdir()
    lanes = queue.load()
    lanes[0]["feed"] = str(feed)
    queue.save(lanes)
    assert cli.main(["queue", "stop", "--lane", "m1", "--grace", "3600", "--state", str(state / "s")]) == 0
    assert max(feed.iterdir()).read_text().startswith("STOP (the owner): commit what is green now")
    tick()
    assert fake.stops == [] and "m1" in handles, "within the grace the session is kept"
    lanes = queue.load()
    lanes[0]["stop_at"] = 1  # the grace is over
    queue.save(lanes)
    tick()
    assert fake.stops == ["m1"] and "m1" not in handles and steps()["1.1"]["state"] == "queued"
    assert queue.load()[0]["paused"] and "stop_at" not in queue.load()[0]
    tick()
    assert len(fake.starts) == 1, "stopped: nothing starts until resume"
    assert cli.main(["queue", "resume", "--lane", "m1", "--state", str(state / "s")]) == 0
    fake.procs.row = working
    tick()
    assert len(fake.starts) == 2 and fake.starts[-1][1] == "1.1", "a fresh session on the same step"
    assert "Continue from the tree" in open(steps()["1.1"]["resume_brief"]).read()
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r.get("state") in ("stop", "stopped")] == ["stop", "stopped"]
    assert cli.main(["queue", "stop", "--lane", "nope", "--state", str(state / "s")]) == 1


def test_weakened_tests_are_an_alert_with_the_test_diff_and_approve_reruns_recording_the_approval(state):
    """Manager 2026-11-02: weakened tests had no approve path. Now: the same alert as needs-maintainer (evidence the test
    files' diff, actions approve|send-back); approve re-runs the step's check with approve_weakened, not --maintainer."""
    lane(state)
    seen = []
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "weakened-tests", "why": "weakened tests at abc: test_old.py",
                                 "evidence": "/s/weakened-m1.diff"}]})
    base_chain = fake.procs.chain
    fake.procs.chain = lambda lane_, step, stage: seen.append((bool(step.get("approve_weakened")), bool(step.get("maintainer")))) or base_chain(lane_, step, stage)
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["actions"] == ["approve", "send-back"] and a["evidence"] == "/s/weakened-m1.diff"
    assert cli.main(["alert", a["id"], "approve", "--state", str(state / "s")]) == 0
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert seen[:2] == [(False, False), (True, False)], "approve re-ran the check recording the approval, never as a maintainer batch"
    assert steps()["1.1"]["state"] == "landed"


def test_external_lanes_hold_their_milestone_but_are_not_the_loops_lanes_and_a_finished_lane_is_briefed_again(state, monkeypatch):
    """Soak 2026-11-02: two external lanes filled `lanes = 1`, so the loop took nothing; a lane that landed a batch kept its
    milestone forever, so its open issues were never briefed; re-briefing only landed steps must not loop."""
    monkeypatch.setattr(queue, "_SKIPPED", set())
    queue.add("lane-sharing", "/w/s", "2.3", str(state / "b1.1"), [], kind="external")
    queue.add("dev-workflows", "/w/h", "held", str(state / "b1.1"), [], kind="external")
    queue.add("image-enhancement", "/w/land-ie", "ie-batch2", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[2]["steps"][0]["state"] = "checking"  # the loop is landing ie-batch2: that uses its one lane
    queue.save(lanes)
    assert queue.feed(Fake().procs, 1, out=lambda s: None) is False
    lanes = queue.load()
    lanes[2]["steps"][0]["state"], lanes[2]["cursor"] = "landed", 1  # ie-batch2 landed through the chain
    queue.save(lanes)
    asked = []

    def nxt(taken):
        asked.append(set(taken))
        if "image-enhancement" not in taken:
            return "image-enhancement", "/jail/wt-image-enhancement", [{"step": "1.1", "brief": str(state / "b1.1"), "issues": [7]}]
        return None
    fake = Fake()
    fake.procs.next_milestone = nxt
    assert queue.feed(fake.procs, 1, out=lambda s: None) is True
    assert {"lane-sharing", "dev-workflows"} <= asked[0] and "image-enhancement" not in asked[0], "external lanes hold; a finished one frees"
    ie = next(x for x in queue.load() if x["id"] == "image-enhancement")
    assert ie["kind"] == "worker" and ie["worktree"] == "/jail/wt-image-enhancement" and [s["step"] for s in ie["steps"]] == ["ie-batch2", "1.1"]
    assert queue.feed(fake.procs, 1, out=lambda s: None) is False, "one worker lane busy: lanes = 1 is full"
    lanes = queue.load()
    lanes[2]["steps"][1]["state"], lanes[2]["cursor"] = "landed", 2
    queue.save(lanes)
    fake.procs.next_milestone = lambda taken: ("image-enhancement", "/jail/wt-image-enhancement", [{"step": "1.1", "brief": str(state / "b1.1"), "issues": [7]}]) if "image-enhancement" not in taken else None
    assert queue.feed(fake.procs, 1, out=lambda s: None) is False, "a finished worker lane keeps its milestone: never a loop"
    assert [s["step"] for s in next(x for x in queue.load() if x["id"] == "image-enhancement")["steps"]] == ["ie-batch2", "1.1"]


def test_a_red_on_base_refusal_is_an_alert_and_approve_reruns_with_approve_red(state):
    lane(state)
    seen = []
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "red-on-base", "why": "red-on-base at abc: NOT RED ON BASE: test_x.py", "evidence": "/s/ladder.json"}]})
    base_chain = fake.procs.chain
    fake.procs.chain = lambda lane_, step, stage: seen.append(bool(step.get("approve_red"))) or base_chain(lane_, step, stage)
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["actions"] == ["approve", "send-back"] and "NOT RED ON BASE" in a["what"]
    assert cli.main(["alert", a["id"], "approve", "--state", str(state / "s")]) == 0
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert seen[:2] == [False, True] and steps()["1.1"]["state"] == "landed"


def test_the_loop_re_execs_itself_between_ticks_when_its_code_changes_and_nothing_is_in_flight(state, monkeypatch):
    """Manager 2026-11-02: restarting the loop by hand to pick up new code is a hand step. Between ticks, with no chain and no
    worker session, a changed source makes it exec itself with the same args, after one row."""
    marks = iter([("a",), ("a",), ("b",), ("b",)])
    monkeypatch.setattr(queue, "code_mark", lambda: next(marks, ("b",)))
    execs = []
    monkeypatch.setattr(queue, "reexec", lambda: execs.append(1))
    fake = Fake()
    n = []
    fake.procs.sleep = lambda s: (n.append(1), len(n) > 3 and (_ for _ in ()).throw(SystemExit))
    with pytest.raises(SystemExit):
        queue.run(fake.procs, workers_n=1, push=False, forever=True, heartbeat=True, out=lambda s: None)
    assert execs == [1], "one re-exec when the mark changed"
    (r,) = [r for r in journal.read() if r["event"] == "loop" and r.get("state") == "restarted"]
    assert r["detail"] == "loop restarted for new code" and r["pid"]


def test_a_new_file_under_a_pinned_path_is_an_alert_and_approve_reruns_with_approve_pinned_new(state):
    """Manager 2026-11-02: on a --maintainer batch a new file under a pinned path was a dead end (no flag, no answer)."""
    lane(state)
    seen = []
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "pinned-new", "why": "a new file under a pinned path at abc: scripts/x.py", "evidence": "/s/new.diff"}]})
    base_chain = fake.procs.chain
    fake.procs.chain = lambda lane_, step, stage: seen.append(bool(step.get("approve_pinned_new"))) or base_chain(lane_, step, stage)
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["actions"] == ["approve", "send-back"] and a["evidence"] == "/s/new.diff"
    assert cli.main(["alert", a["id"], "approve", "--state", str(state / "s")]) == 0
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert seen[:2] == [False, True] and steps()["1.1"]["state"] == "landed"


def _ext_repo(tmp_path, commits=1, subject="feat: x (Step 1.2, a.b)"):
    import subprocess

    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    seed = tmp_path / "seed"
    seed.mkdir()
    g(seed, "init", "-q", "-b", "integration"), (seed / "a").write_text("a"), g(seed, "add", "."), g(seed, "commit", "-qm", "base")
    g(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    wt = tmp_path / "lane-x"
    g(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(wt))
    for i in range(commits):
        (wt / f"f{i}").write_text(str(i))
        g(wt, "add", "."), g(wt, "commit", "-qm", subject if i == commits - 1 else f"wip {i}")
    return wt, g


def test_done_snapshots_the_lanes_head_into_a_land_tree_and_a_red_tells_its_pane_and_a_re_done_re_takes(state, tmp_path):
    """dev-workflows.run.loop-external-intake: the lane's own tree is never touched; findings go to a file and its pane."""
    wt, g = _ext_repo(tmp_path)
    queue.add("lane-x", str(wt), "batch-1", str(state / "b1.1"), [], kind="external", pane="%7")
    head = g(wt, "rev-parse", "HEAD")
    assert queue.done("lane-x") == ""
    s = steps_of("lane-x")[0]
    land = tmp_path / "land-lane-x"
    assert s["state"] == "done" and s["head"] == head and s["land_tree"] == str(land.resolve()) and g(land, "rev-parse", "HEAD") == head
    assert g(wt, "rev-parse", "--abbrev-ref", "HEAD") != "land-lane-x" and g(wt, "status", "--porcelain") == "", "the lane's tree is untouched"
    told, swept = [], []
    fake = Fake(chains={"batch-1": [{"ok": False, "kind": "red", "why": "ruff on the changed Python", "findings": "x.py:1 F401"}]})
    fake.procs.tell, fake.procs.after_land = (lambda lane, text: told.append((lane.get("pane"), text)) or ""), (lambda lane, step, head: swept.append(step["land_tree"]))
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert steps_of("lane-x")[0]["state"] == "blocked" and told and told[0][0] == "%7" and "FINDINGS" in told[0][1]
    (f,) = (state / "s").glob("findings-lane-x-*.txt")
    assert "ruff on the changed Python" in f.read_text()
    (wt / "fix").write_text("fixed")
    g(wt, "add", "."), g(wt, "commit", "-qm", "fix: the finding (Step 1.2)")
    assert queue.done("lane-x") == "", "the lane fixed it and ran done again"
    assert steps_of("lane-x")[0]["head"] == g(wt, "rev-parse", "HEAD")
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    assert steps_of("lane-x")[0]["state"] == "landed" and any("LANDED" in t for _p, t in told) and swept == [str(land.resolve())]
    assert queue.done("lane-x") == "" and [x["step"] for x in steps_of("lane-x")] == ["batch-1", "batch-2"], "a finished lane gets its next batch"


def test_the_intake_takes_a_finished_step_past_its_thresholds_and_never_a_held_lane(state, tmp_path):
    wt, g = _ext_repo(tmp_path, commits=3)
    lane_ = {"id": "lane-x", "worktree": str(wt)}
    assert queue.intake_sha(lane_, "integration", 3, 99) == g(wt, "rev-parse", "HEAD"), "three commits, a finished step"
    assert queue.intake_sha(lane_, "integration", 8, 99) == "", "under the commit threshold and young"
    assert queue.intake_sha(lane_, "integration", 8, 0) != "", "old enough"
    (wt / "z").write_text("z")
    g(wt, "add", "."), g(wt, "commit", "-qm", "wip: half a step")
    assert queue.intake_sha(lane_, "integration", 1, 0) == "", "the HEAD is not a finished step"
    queue.add("held", str(wt), "held", str(state / "b1.1"), [], kind="external", hold=True)
    fake = Fake()
    fake.procs.intake = lambda lane: "f" * 40
    queue.run(fake.procs, workers_n=1, push=False, once=True, out=lambda s: None)
    assert steps_of("held")[0]["state"] == "queued", "a held lane is never taken"


def steps_of(lane_id):
    return next(x for x in queue.load() if x["id"] == lane_id)["steps"]


def test_a_milestone_an_external_lane_owns_is_skipped_unplaced_issues_are_one_alert_and_external_retry_re_takes(state, monkeypatch):
    """Manager 2026-11-02: the loop planned Sharing (lane-sharing's spec) and raised 25 alerts, one per unplaced issue; a retry
    left ie-batch2 waiting for a done no one would run."""
    monkeypatch.setattr(queue, "_SKIPPED", set())
    brief = state / "brief-sharing.md"
    brief.write_text("LANE sharing. Spec: docs/contributor_manual/specs/source/sharing-two-macs.md\n")
    queue.add("lane-sharing", "/w/s", "2.3", str(brief), [], kind="external")
    assert queue.external_owner("source/sharing-two-macs.md") == "lane-sharing"
    assert queue.external_owner("source/image-enhancement.md") == ""
    for i in range(3):
        journal.append("alert", id=f"old-{i}", lane="gone", step="plan", what="#1 names no step", evidence="", actions=[])
    for i in range(3):
        assert cli.main(["alert", f"old-{i}", "park", "--state", str(state / "s")]) == 0, "a no-action alert of a gone lane parks"
    queue.add("ie", "/w/ie", "batch", str(brief), [], kind="external")
    queue.done("ie", "a" * 40)
    fake = Fake(chains={"batch": [{"ok": False, "kind": "not-ready", "why": "stale base"}]})
    queue.run(fake.procs, workers_n=1, push=False, out=lambda s: None)
    a = [x for x in _alerts() if x["lane"] == "ie"][0]
    assert cli.main(["alert", a["id"], "retry", "--state", str(state / "s")]) == 0
    assert steps_of("ie")[0]["state"] == "done", "an external retry re-takes the snapshot, never waits for a done"


def test_a_lane_paused_after_the_tick_loaded_it_never_starts_a_step(state):
    """Manager 2026-11-02: paused (then stopped) between the tick's load and the start, the lane still started step 0.3."""
    lane(state)
    stale = queue.load()[0]  # the tick's copy, taken before the pause
    assert cli.main(["queue", "pause", "--lane", "m1", "--state", str(state / "s")]) == 0
    fake = Fake()
    assert queue.tick_lane(stale, fake.procs, {}, 1, False, lambda s: None) is False
    assert fake.starts == [] and steps()["1.1"]["state"] == "queued"


def test_a_head_whose_every_commit_is_on_origin_by_patch_is_never_taken(state, tmp_path):
    """Manager 2026-11-02: the intake re-took land-ie's pre-rebase ie-batch2 (all 18 commits already landed by patch)."""
    wt, g = _ext_repo(tmp_path, commits=3)
    head = g(wt, "rev-parse", "HEAD")
    seed = tmp_path / "seed"
    (seed / "other").write_text("o")
    g(seed, "add", "."), g(seed, "commit", "-qm", "another landing first")  # so the picks get other shas
    g(seed, "fetch", "-q", str(wt), "HEAD")
    base = g(wt, "rev-parse", "origin/integration")
    g(seed, "cherry-pick", f"{base}..FETCH_HEAD")
    g(seed, "push", "-q", str(tmp_path / "origin.git"), "integration")
    g(wt, "fetch", "-q", "origin")
    assert queue.missing(str(wt)) == 0, "every commit is on origin by patch"
    lane_ = {"id": "lane-x", "worktree": str(wt)}
    assert queue.intake_sha(lane_, "integration", 1, 0) == ""
    queue.add("lane-x", str(wt), "batch-1", str(state / "b1.1"), [], kind="external")
    assert "already on origin" in queue.done("lane-x", head)


def test_a_paused_external_lanes_done_is_recorded_and_waits_for_resume(state, capsys):
    """Manager 2026-11-02: lane-onboard was paused, ran `builder done`, and the loop checked it. A paused lane's DONE records
    the head and says it waits; the loop starts no check until `queue resume`."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    lanes = queue.load()
    lanes[0]["paused"] = True
    queue.save(lanes)
    fake = Fake()
    assert cli.main(["done", "ext", "abc123", "--state", str(journal.STATE)]) == 0
    assert "PAUSED" in capsys.readouterr().out
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert fake.landed_calls == [] and steps()["1.1"]["state"] == "done" and steps()["1.1"]["head"] == "abc123"
    assert cli.main(["queue", "resume", "--lane", "ext", "--state", str(journal.STATE)]) == 0
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert fake.landed_calls and steps()["1.1"]["state"] == "landed"


def test_run_check_fetches_the_lanes_head_and_runs_the_pinned_ladder_over_it_and_lands_nothing(state, tmp_path):
    """Owner 2026-11-02 (console 'Run check'): `builder check-lane <lane>` checks the lane's HEAD now, under its own fetch
    name, in a ladder slot; the result is printed; no review, no landing."""
    import contextlib
    import types
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/engine"\n[land]\nbranch = "integration"\n')
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    seen = []

    @contextlib.contextmanager
    def slot(name, files, n):
        seen.append(("slot", name, files))
        yield "ladder"
    w = types.SimpleNamespace(
        ensure_pinned=lambda root, brief, base: str(tmp_path),
        do_fetch=lambda a, repo, branch: (seen.append(("fetch", a.name)), "f" * 40)[1],
        _git=lambda repo, *args: types.SimpleNamespace(stdout="x.py\n"), r_since=lambda repo, branch: "b" * 40, ladder_slot=slot,
        do_check=lambda a, repo, branch, head, ladder: (seen.append(("check", a.name, head)), {"ok": False, "failed": "pytest"})[1])
    rc, msg = queue.check_head(tmp_path, "ext", w)
    assert rc == 1 and msg == "ext at fffffffff: RED at pytest"
    assert seen == [("fetch", "ext-check"), ("slot", "ext (Run check)", ["x.py"]), ("check", "ext", "f" * 40)]
    assert queue.check_head(tmp_path, "nope", w)[0] == 1
    assert "check-lane" in __import__("fichero_builder.console", fromlist=["VERBS"]).VERBS


def test_an_approve_binds_to_its_alerts_head_and_named_tests_and_a_new_head_clears_it(state):
    """Defect 2026-11-02: alert -36's approve_red (for one import-only test at 8a145781e) was still set when the lane's next
    head e4e23bbfb9 was checked. An approve records its head and the test files its alert named; the chain sees it only for
    that head, and a `builder done` at a new head carries none of it."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    assert queue.done("ext", "a" * 40) == ""
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", approve_kind="red-on-base", why="red-on-base at aaaaaaaaa: NOT RED ON BASE: fichero-builder/tests/test_x.py passes")
    queue.save(lanes)
    aid = queue.alert("ext", "1.1", "red-on-base at aaaaaaaaa: NOT RED ON BASE: fichero-builder/tests/test_x.py passes at b", "/l.json", ["approve", "send-back"])
    assert queue.answer(aid, "approve")[0] == 0
    s = steps()["1.1"]
    assert s["approved_head"] == "a" * 40 and s["approved_tests"] == ["fichero-builder/tests/test_x.py"]
    assert queue._approved(s, "approve_red")
    lanes = queue.load()
    lanes[0]["steps"][0]["state"] = "blocked"
    queue.save(lanes)
    assert queue.done("ext", "c" * 40) == ""
    assert not queue._approved(steps()["1.1"], "approve_red"), "a new head clears the approve"








def test_a_new_head_or_a_landing_answers_the_steps_open_alerts_superseded_and_never_parks(state):
    """Manager defect 2026-11-02: alerts -37, -48, -49 stayed open on the console after the batch moved to a new head."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    queue.add("ext", "/w/ext", "1.2", str(state / "b1.2"), [8], waits=["1.1"])
    old = [queue.alert("ext", "1.1", f"red at {n}", "/l.json", ["retry", "park"]) for n in "ab"]
    other = queue.alert("ext", "1.2", "another step", "/l.json", ["retry"])
    assert queue.done("ext", "c" * 40) == ""
    answers = {r["id"]: r for r in journal.read() if r["event"] == "alert-answer"}
    assert set(answers) == set(old) and all(r["action"] == "superseded" and r["ok"] for r in answers.values())
    assert [a["id"] for a in watch.status(journal.read(), queue.load())["open_alerts"]] == [other], "only this step's alerts closed"
    assert steps()["1.1"]["state"] == "done", "the live step was not parked"
    late = queue.alert("ext", "1.1", "red at the new head", "/l.json", ["retry"])
    assert queue.close_alerts("ext", "1.1", "the step landed") == [late]


def test_an_approve_on_a_worker_lane_whose_step_has_no_head_yet_still_counts(state):
    """Review 2026-11-02: a worker lane's step has head "" until a chain is green, so an approve recorded with head "" never counted.
    It holds while the step has no head and lapses when one is set (a new head clears it)."""
    queue.add("w", "/w/w", "1.1", str(state / "b1.1"), [7])
    step = {"state": "done", "head": "", "approve_red": True, "approved_head": ""}
    assert queue._approved(step, "approve_red")
    assert not queue._approved({**step, "head": "c" * 40}, "approve_red"), "a head set later clears it"
    assert not queue._approved({"state": "done", "head": "", "approve_red": True}, "approve_red"), "no recorded approve head: no approve"
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", approve_kind="red-on-base", why="red-on-base: NOT RED ON BASE: t/test_x.py passes")
    queue.save(lanes)
    aid = queue.alert("w", "1.1", "red-on-base: NOT RED ON BASE: t/test_x.py passes", "/l.json", ["approve", "send-back"])
    assert queue.answer(aid, "approve")[0] == 0
    assert queue._approved(steps()["1.1"], "approve_red"), "an approve through the real answer path on a headless worker step counts"


def test_a_send_back_or_fix_brief_reaches_a_live_session_not_the_original_brief(state):
    """Review 2026-11-02: with a session still alive the queued step re-sent the original brief and ignored `resume_brief`, so the
    manager's finding never reached the worker."""
    fake = Fake()
    queue.add("w", "/w/w", "1.1", str(state / "b1.1"), [7])
    (state / "fix.txt").write_text("FIX: the manager's finding")
    lanes = queue.load()
    lanes[0]["feed"] = str(state / "feed")
    lanes[0]["steps"][0].update(state="queued", resume_brief=str(state / "fix.txt"))
    queue.save(lanes)
    fake.procs.alive = lambda h: True
    queue.tick(fake.procs, {"w": object()}, workers_n=1, push=True, out=lambda s: None)
    assert fake.sent == ["FIX: the manager's finding"], fake.sent


def test_a_newer_head_of_the_same_work_supersedes_a_batch_in_the_ladder_and_an_unrelated_one_is_refused(state, tmp_path):
    """Manager 2026-11-02 (lane-onboard replaced its batch while it was checked: `done` refused): a head that descends from, or
    rewrites, the head in the ladder takes its place: the old check is cancelled (cancel-<head>), its approvals and alerts end,
    the step is `done` at the new head. Anything unrelated still waits its turn."""
    import subprocess as sp

    def g(*a, cwd=None):
        return sp.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", *a], cwd=cwd or repo, capture_output=True, text=True, check=True).stdout.strip()
    repo = tmp_path / "ext"
    repo.mkdir()
    def commit(name, text):
        (repo / name).write_text(text)
        g("add", name), g("commit", "-q", "-m", name)
    g("init", "-q", "-b", "main"), commit("a", "1")
    old = g("rev-parse", "HEAD")
    commit("b", "2")
    child = g("rev-parse", "HEAD")
    g("checkout", "-q", "--orphan", "other"), commit("c", "3")
    stranger = g("rev-parse", "HEAD")
    queue.add("ext", str(repo), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="checking", head=old, approve_red=True, approved_head=old, approved_tests=["t.py"], approvals=["approve_red"])
    queue.save(lanes)
    aid = queue.alert("ext", "batch-1", "red-on-base at old", "/l.json", ["approve"])
    assert "one at a time" in queue.done("ext", stranger) and steps()["batch-1"]["head"] == old, "an unrelated head waits"
    assert queue.done("ext", child) == ""
    s = steps()["batch-1"]
    assert s["state"] == "done" and s["head"] == child and not any(k in s for k in queue.APPROVALS)
    assert (journal.STATE / f"cancel-{old[:9]}").read_text() == child
    assert any(r.get("event") == "alert-answer" and r["id"] == aid and r["action"] == "superseded" for r in journal.read())
    assert any(r.get("state") == "superseded" for r in journal.read() if r["event"] == "queue")


def test_a_guard_data_alert_is_approved_by_file_name_and_binds_to_the_head(state):
    """Manager 2026-11-02 (lane-onboard -79): guards red only because a guard's allowlist .json changed in the batch. The alert offers
    approve|send-back; the approve records `approve_guard_data` and the json file names it quoted, for that head only."""
    lane(state)
    fake = Fake(chains={"1.1": [{"ok": False, "kind": "guard-data", "approvals": ["approve_guard_data"], "evidence": "/s/gd.diff",
                                 "why": "guards red at abc with guard data changed by the batch: scripts/check_x_known_gaps.json; approve lays HEAD's copy"}]})
    queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None)
    (a,) = _alerts()
    assert a["actions"] == ["approve", "send-back"] and a["evidence"] == "/s/gd.diff"
    lanes = queue.load()
    lanes[0]["steps"][0]["head"] = "a" * 40
    queue.save(lanes)
    assert cli.main(["alert", a["id"], "approve", "--state", str(state / "s")]) == 0
    s = steps()["1.1"]
    assert s["approve_guard_data"] is True and s["approved_tests"] == ["scripts/check_x_known_gaps.json"] and s["approved_head"] == "a" * 40
    assert queue._approved(s, "approve_guard_data") and not queue._approved({**s, "head": "b" * 40}, "approve_guard_data")


def test_an_external_lanes_red_offers_send_back_retry_park_and_a_worker_lanes_keeps_its_own(state):
    """run.loop-external-lane: an external lane fixes its own reds, so it is never offered ask-owner; a worker lane is unchanged."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    red = {"ok": False, "kind": "red", "why": "pytest red", "findings": "t1 failed", "evidence": "/l.json"}
    fake = Fake(chains={"1.1": [red]})
    assert cli.main(["done", "ext", "abc123", "--state", str(journal.STATE)]) == 0
    assert queue.run(fake.procs, workers_n=1, push=True, out=lambda s: None) == 0
    assert [a["actions"] for a in _alerts()] == [["send-back", "retry", "park"]]


def test_send_back_on_an_external_lane_tells_its_pane_the_done_command_and_says_so_when_it_has_none(state, monkeypatch):
    """run.loop-external-lane: send-back and park put the finding and the exact `builder done` command into the lane's pane;
    a lane with no registered pane is a tell-refused row, never a silent send-back."""
    from fichero_builder import tell
    sent = []
    monkeypatch.setattr(tell, "send", lambda pane, msg, **k: sent.append((pane, msg)) or (0, "sent"))
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    journal.append("alert", id="ext-1.1-1", lane="ext", step="1.1", what="pytest red", evidence="/l.json", actions=["send-back", "retry", "park"])
    lanes = queue.load()
    lanes[0]["pane"] = "%77"
    queue.save(lanes)
    assert queue.answer("ext-1.1-1", "send-back")[0] == 0
    assert sent and sent[0][0] == "%77" and "SENT BACK (send-back) ext 1.1" in sent[0][1] and "fichero_builder done ext" in sent[0][1]
    lanes = queue.load()
    lanes[0]["pane"] = ""
    queue.save(lanes)
    assert queue.answer("ext-1.1-1", "park")[0] == 0 and len(sent) == 1
    assert [r["state"] for r in journal.read() if r["event"] == "queue" and r.get("state") in ("told", "tell-refused")] == ["told", "tell-refused"]


def test_a_draining_loop_starts_no_new_chain_so_it_can_re_exec_between_chains(state):
    """Soak 2026-11-02: new code waits; while DRAIN is set no chain starts, and clearing it lets the same step run."""
    queue.add("ext", "/w/ext", "1.1", str(state / "b1.1"), [7], kind="external")
    fake = Fake(chains={})
    assert cli.main(["done", "ext", "abc123", "--state", str(journal.STATE)]) == 0
    chains = {"pool": queue.ThreadPoolExecutor(max_workers=1)}
    queue.DRAIN[0] = True
    try:
        queue.tick(fake.procs, {}, workers_n=1, push=True, out=lambda s: None, chains=chains)
        assert set(chains) == {"pool"} and steps()["1.1"]["state"] != "landed", "no chain was submitted"
    finally:
        queue.DRAIN[0] = False
        chains["pool"].shutdown()


def test_an_old_chains_stage_callback_never_writes_its_stale_step_over_a_newer_done(state, tmp_path):
    """Review 2026-11-02 (-92): `builder done` at a newer head between the old ladder's end and its `reviewing` stage was overwritten by
    the old chain's copy of the step (old head, cleared approvals), so the superseded head could still land."""
    import subprocess as sp

    def g(*a):
        return sp.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", *a], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    repo = tmp_path / "ext"
    repo.mkdir()
    (repo / "a").write_text("1")
    g("init", "-q", "-b", "main"), g("add", "a"), g("commit", "-q", "-m", "a")
    old = g("rev-parse", "HEAD")
    (repo / "b").write_text("2")
    g("add", "b"), g("commit", "-q", "-m", "b")
    child = g("rev-parse", "HEAD")
    queue.add("ext", str(repo), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head=old)
    queue.save(lanes)
    fake = Fake()

    def chain(lane_, step, stage):
        stage("checking")
        assert queue.done("ext", child) == "", "done at the newer head lands between the ladder and the review"
        stage("reviewing")  # the old chain's callback, with its stale copy of the step
        return {"ok": True, "head": old, "why": "", "findings": ""}
    fake.procs.chain = chain
    queue.run(fake.procs, workers_n=1, push=True, once=True, out=lambda s: None)
    assert fake.landed_calls == [], "the superseded head never lands"
    s = steps()["batch-1"]
    assert s["head"] == child and s["state"] == "done", "the newer done stands, untouched by the old chain"
    assert any(r.get("state") == "stale-result" for r in journal.read() if r["event"] == "queue")


def test_a_stale_chain_store_waits_for_the_queue_lock_and_then_checks_the_head_under_it(state, tmp_path):
    """Review 2026-11-02 (-94): the head check ran before the lock was taken; `builder done` holds the lock through its git work and
    saves last, so a check made first passed and the stale step was written over the new head. The check is inside `store`."""
    import threading
    import time

    queue.add("ext", "/w/ext", "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head="old")
    queue.save(lanes)
    stale = queue.load()[0]
    stale["steps"][0].update(state="reviewing")
    result = []
    with journal.Lock("queue"):  # `done` is mid-way through its git work
        t = threading.Thread(target=lambda: result.append(queue.store(stale, expect=("batch-1", "old"))))
        t.start()
        time.sleep(0.3)
        assert not result, "the stale write is waiting on the lock, its pre-lock check would have passed"
        lanes = queue.load()
        lanes[0]["steps"][0].update(state="done", head="new")  # `done` saves the new head last
        queue.save(lanes)
    t.join(10)
    assert result == [False] and steps()["batch-1"]["head"] == "new" and steps()["batch-1"]["state"] == "done", "the new head stands"
    assert queue.store(queue.load()[0], expect=("batch-1", "new")) is True, "a write at the head it expects still goes through"


def _two_commit_repo(tmp_path):
    import subprocess as sp

    def g(*a):
        return sp.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", *a], cwd=tmp_path / "ext", capture_output=True, text=True, check=True).stdout.strip()
    (tmp_path / "ext").mkdir()
    (tmp_path / "ext" / "a").write_text("1")
    g("init", "-q", "-b", "main"), g("add", "a"), g("commit", "-q", "-m", "a")
    old = g("rev-parse", "HEAD")
    (tmp_path / "ext" / "b").write_text("2")
    g("add", "b"), g("commit", "-q", "-m", "b")
    return old, g("rev-parse", "HEAD")


def test_a_done_while_the_batch_is_landing_is_refused_and_the_landing_keeps_its_step(state, tmp_path):
    """Review 2026-11-02 (-96): a `done` accepted while `procs.landed` ran was overwritten by the landing's own move/store, losing the
    new head. The step is claimed as landing before the landing starts and `done` refuses it until it ends."""
    old, child = _two_commit_repo(tmp_path)
    queue.add("ext", str(tmp_path / "ext"), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head=old)
    queue.save(lanes)
    fake = Fake()
    told = []
    orig = fake.landed

    def landed(lane_, head, push):
        told.append(queue.done("ext", child))  # the lane says DONE at a newer head while the landing runs
        return orig(lane_, head, push)
    fake.procs.landed = landed
    queue.run(fake.procs, workers_n=1, push=True, once=True, out=lambda s: None)
    assert told and "one at a time" in told[0], "done is refused while the batch is landing"
    assert steps()["batch-1"]["state"] == "landed" and "settling" not in steps()["batch-1"]



def test_a_done_the_land_tree_refuses_cancels_nothing_and_leaves_the_running_check(state, tmp_path, monkeypatch):
    """Review 2026-11-02 (-96): done wrote the cancel file and the superseded row before land_tree could refuse, so a refused done
    still killed the running check without taking the new head."""
    old, child = _two_commit_repo(tmp_path)
    queue.add("ext", str(tmp_path / "ext"), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="checking", head=old, approvals=["approve_red"])
    queue.save(lanes)
    monkeypatch.setattr(queue, "land_tree", lambda lane_, sha: ("", "the land tree could not be made"))
    assert "land tree" in queue.done("ext", child)
    assert not (journal.STATE / f"cancel-{old[:9]}").exists() and steps()["batch-1"]["head"] == old and steps()["batch-1"]["state"] == "checking"
    assert not any(r.get("state") == "superseded" for r in journal.read() if r["event"] == "queue")


@pytest.mark.parametrize("result", [{"ok": True}, {"ok": False, "kind": "red", "why": "pytest red", "findings": "t1", "evidence": "/l.json"},
                                    {"ok": False, "kind": "needs-maintainer", "why": "pinned", "evidence": "/l.json"}])
@pytest.mark.parametrize("point", ["checking", "reviewing", "returned"])
def test_a_stale_chain_writes_nothing_at_any_stage_after_a_newer_done(state, tmp_path, point, result):
    """The race class (-92, -94, -96): a chain driven through every write it makes to the step (stage `checking`, stage `reviewing`,
    its result: landed, blocked, a fix brief) against a `builder done` at a newer head that lands at that point. Every write is a
    compare-and-set of (step, head) under the queue lock, so none of them touches the newer head, and nothing lands."""
    old, child = _two_commit_repo(tmp_path)
    queue.add("ext", str(tmp_path / "ext"), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head=old)
    queue.save(lanes)
    fake = Fake()
    fired = []

    def supersede():
        fired.append(queue.done("ext", child))
        assert fired[-1] == "", "the newer done is taken at this point"

    def chain(lane_, step, stage):
        for name in ("checking", "reviewing"):
            stage(name)
            if point == name:
                supersede()
        if point == "returned":
            supersede()
        return {"head": old, "why": "", "findings": "", **result}
    fake.procs.chain = chain
    queue.run(fake.procs, workers_n=1, push=True, once=True, out=lambda s: None)
    s = steps()["batch-1"]
    assert fired == [""] and fake.landed_calls == [], "the superseded head never lands"
    assert s["head"] == child and s["state"] == "done" and "settling" not in s and "why" in s, f"the newer done stands: {s}"
    assert not any(r["event"] == "alert" for r in journal.read()), "and a stale red raises no alert for the old head"


@pytest.mark.parametrize("staged", [True, False])
@pytest.mark.parametrize("result", [{"ok": True}, {"ok": False, "kind": "red", "why": "pytest red", "findings": "t1", "evidence": "/l.json"}])
def test_a_done_right_after_the_outcome_claim_is_refused_whatever_state_the_chain_left_the_step_in(state, tmp_path, monkeypatch, staged, result):
    """Review 2026-11-02 (-99): a chain that returns before its first stage (a rebase error, no patches, a failed fetch, an exception)
    leaves the step `done`; `settling` was refused only for checking/reviewing, so a done right after the claim took the new head and
    the outcome's own write put the old one back. `done` refuses a settling step in any state."""
    old, child = _two_commit_repo(tmp_path)
    queue.add("ext", str(tmp_path / "ext"), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head=old)
    queue.save(lanes)
    fake = Fake()
    def chain(lane_, step, stage):
        if staged:
            stage("checking"), stage("reviewing")
        return {"head": old, "why": "", "findings": "", **result}  # unstaged: returns before its first stage
    fake.procs.chain = chain
    fired = []
    orig_store = queue.store

    def store(lane_, expect=None):
        ok = orig_store(lane_, expect=expect)
        if expect and ok and any(x.get("settling") for x in lane_["steps"]) and not fired:
            fired.append(queue.done("ext", child))  # the lane says DONE right after the claim was won
        return ok
    monkeypatch.setattr(queue, "store", store)
    queue.run(fake.procs, workers_n=1, push=True, once=True, out=lambda s: None)
    assert fired and "one at a time" in fired[0], fired
    s = steps()["batch-1"]
    assert s["head"] != child and "settling" not in s, f"the outcome's own write stands, nothing lost to a refused done: {s}"


def test_the_landing_is_one_write_so_a_done_right_after_it_opens_the_next_batch_and_loses_nothing(state, tmp_path, monkeypatch):
    """Review 2026-11-02 (-101): the landed path wrote the step as landed, then advanced the cursor in a second store; a `builder done`
    between them reused the landed step and the second write put the old head back over it. One store ends the landing."""
    old, child = _two_commit_repo(tmp_path)
    queue.add("ext", str(tmp_path / "ext"), "batch-1", str(state / "b1.1"), [], kind="external")
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="done", head=old)
    queue.save(lanes)
    fake = Fake()
    fired = []
    orig_store = queue.store

    def store(lane_, expect=None):
        ok = orig_store(lane_, expect=expect)
        if not fired and any(x["state"] == "landed" for x in lane_["steps"]):
            fired.append(queue.done("ext", child))  # the lane says DONE the moment the landed write is in
        return ok
    monkeypatch.setattr(queue, "store", store)
    queue.run(fake.procs, workers_n=1, push=True, once=True, out=lambda s: None)
    assert fired == [""], fired
    st = steps()
    assert st["batch-1"]["state"] == "landed" and st["batch-1"]["head"] != child, "the landed step is untouched"
    assert st["batch-2"]["head"] == child and st["batch-2"]["state"] == "done", "the newer head is the next batch, not lost"

