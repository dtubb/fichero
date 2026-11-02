"""dev-workflows.run.loop (Steps 2.9-2.11): `builder loop` keeps every lane going with no person: DONE -> fetch -> check ->
review -> landed --push -> the next step; a red goes back to the worker; every tick a heartbeat row. Processes are fakes."""
from __future__ import annotations

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue
from tests.test_queue_verb import Fake, lane, steps


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
