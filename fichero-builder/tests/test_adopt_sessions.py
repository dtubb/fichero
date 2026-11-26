"""#6589 (throughput review 2026-11-24, item 7): a restarted loop adopts only the session of its step and head, a dirty tree does not
block the rebase, the two mechanical alerts are retried once by the loop, and `queue landed` records a hand landing."""
from __future__ import annotations

import pytest
from test_queue_verb import Fake, lane, steps
from test_work_verb import _commit, _g, scratch  # noqa: F401  (the scratch fixture)

from fichero_builder import journal, queue, work


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(queue, "ONLY", [()])
    monkeypatch.setattr(queue, "DISPATCH", [()])
    for n in ("1.1", "1.2"):
        (tmp_path / f"b{n}").write_text(f"brief {n}")
    return tmp_path


def _restart(state, descends=True, mutate=None):
    lane(state)
    fake = Fake()
    fake.procs.adopt = lambda ln: "adopted-handle"
    fake.procs.head_of = lambda ln: "h-at-send"
    fake.procs.descends = lambda ln, sha: descends and sha == "h-at-send"
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)  # the old loop starts the session
    assert steps()["1.1"]["state"] == "sent"
    if mutate:
        lanes = queue.load()
        mutate(lanes[0])
        queue.save(lanes)
    handles: dict = {}
    queue.tick(fake.procs, handles, workers_n=1, push=False, out=lambda s: None)
    return fake, handles


def test_the_loop_records_the_step_and_head_a_session_was_sent(state):
    _restart(state)
    ln = queue.load()[0]
    assert ln["session_step"] == "1.1" and ln["session_head"] == "h-at-send"


def test_a_restart_adopts_a_session_whose_step_and_head_match(state):
    fake, handles = _restart(state)
    assert handles == {"m1": "adopted-handle"} and fake.stops == []


def test_a_session_of_another_step_is_not_adopted(state):
    fake, handles = _restart(state, mutate=lambda ln: ln.update(session_step="0.9"))
    assert handles == {} and fake.stops == ["m1"]
    assert any(r.get("state") == "adopt-refused" and "step" in r["detail"] for r in journal.read())


def test_a_session_whose_head_is_not_an_ancestor_of_the_tree_is_not_adopted(state):
    fake, handles = _restart(state, descends=False)
    assert handles == {} and fake.stops == ["m1"]
    assert any(r.get("state") == "adopt-refused" and "head" in r["detail"] for r in journal.read())


def test_a_session_with_no_recorded_step_is_not_adopted(state):
    fake, handles = _restart(state, mutate=lambda ln: (ln.pop("session_step"), ln.pop("session_head")))
    assert handles == {} and fake.stops == ["m1"]


def test_a_dirty_tree_is_stashed_by_the_rebase_and_comes_back(scratch):  # noqa: F811
    _commit(scratch.engine, "theirs")
    (scratch.wt / "f").write_text("unstaged edit")
    assert work.do_rebase(scratch.a, "integration") == ""
    assert (scratch.wt / "theirs").is_file() and (scratch.wt / "f").read_text() == "unstaged edit", "rebased, and the edit is back"


def test_a_dirty_tree_whose_edit_conflicts_with_the_rebase_is_said(scratch):  # noqa: F811
    (scratch.engine / "f").write_text("theirs"), _g(scratch.engine, "commit", "-qam", "theirs")
    (scratch.wt / "f").write_text("unstaged edit")
    why = work.do_rebase(scratch.a, "integration")
    assert "stash" in why.lower() and "f" in why


def _block(state, why):
    lane(state)
    fake = Fake()
    queue.tick(fake.procs, {}, workers_n=1, push=False, out=lambda s: None)
    lanes = queue.load()
    s = lanes[0]["steps"][0]
    s.update(state="blocked", why=why, blocked_at=queue._now())
    queue.save(lanes)
    return queue.alert("m1", "1.1", why, "ev", ["retry", "park"])


@pytest.mark.parametrize("why", ["a tmux window named m1 holds a live session (@3, node): `builder queue stop m1` ends it, then retry",
                                 "the worker said DONE with no commit on this step"])
def test_a_mechanical_alert_is_retried_once_by_the_loop(state, why):
    aid = _block(state, why)
    assert queue.auto_retry_mechanical() == [aid]
    assert steps()["1.1"]["state"] == "queued"
    assert any(r.get("event") == "alert-answer" and r["id"] == aid and r["action"] == "retry" for r in journal.read())
    # blocked on the same thing again: a person decides
    lanes = queue.load()
    lanes[0]["steps"][0].update(state="blocked", why=why)
    queue.save(lanes)
    again = queue.alert("m1", "1.1", why, "ev", ["retry", "park"])
    assert queue.auto_retry_mechanical() == [] and steps()["1.1"]["state"] == "blocked" and again


def test_another_alert_is_never_retried_by_the_loop(state):
    _block(state, "the check is red at abc (failed: guards)")
    assert queue.auto_retry_mechanical() == [] and steps()["1.1"]["state"] == "blocked"


def test_queue_landed_records_a_hand_landing_and_moves_the_cursor(state):
    lane(state)
    aid = queue.alert("m1", "1.1", "something", "ev", ["retry"])
    assert queue.landed("m1", "1.1", "a" * 40) == ""
    s = steps()["1.1"]
    assert s["state"] == "landed" and s["head"] == "a" * 40 and queue.load()[0]["cursor"] == 1
    assert any(r.get("event") == "alert-answer" and r["id"] == aid for r in journal.read()), "its alerts are answered"
    assert any(r.get("state") == "landed" and r["step"] == "1.1" for r in journal.read() if r["event"] == "queue")


@pytest.mark.parametrize("lane_id, step, sha", [("nope", "1.1", "a" * 40), ("m1", "1.2", "a" * 40), ("m1", "1.1", "xyz"), ("m1", "1.1", "")])
def test_queue_landed_refuses_an_unknown_lane_a_step_off_the_cursor_and_a_bad_sha(state, lane_id, step, sha):
    lane(state)
    assert queue.landed(lane_id, step, sha) != ""
    assert queue.load()[0]["cursor"] == 0 and steps()["1.1"]["state"] != "landed"


def test_the_real_head_check_passes_safe_directory_and_tells_ancestors_apart(tmp_path):
    import subprocess
    g = ["git", "-c", "user.email=a@b", "-c", "user.name=n", "-C", str(tmp_path)]
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "one"], check=True)
    first = subprocess.run([*g, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "two"], check=True)
    assert queue.tree_descends(tmp_path, first) and not queue.tree_descends(tmp_path, "0" * 40) and not queue.tree_descends(tmp_path, "")
    seen = []
    real = subprocess.run
    queue.subprocess.run = lambda cmd, **kw: (seen.append(cmd), real(cmd, **kw))[1]
    try:
        queue.tree_descends(tmp_path, first)
    finally:
        queue.subprocess.run = real
    assert seen[0][:3] == ["git", "-c", "safe.directory=*"]


def test_an_alert_row_with_no_id_is_skipped_not_a_crash(tmp_path, monkeypatch):
    """2026-11-25 00:55: an old alert row without an `id` stopped the loop at start (KeyError: 'id')."""
    from fichero_builder import journal, queue
    monkeypatch.setattr(journal, "read", lambda: [{"event": "alert", "what": "a live session runs", "actions": ["retry"]}])
    assert queue.auto_retry_mechanical() == []
