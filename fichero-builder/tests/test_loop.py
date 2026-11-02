"""dev-workflows.run.loop (Steps 2.9-2.11): `builder loop` keeps every lane going with no person: DONE -> fetch -> check ->
review -> landed --push -> the next step; a red goes back to the worker; every tick a heartbeat row. Processes are fakes."""
from __future__ import annotations

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue
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
