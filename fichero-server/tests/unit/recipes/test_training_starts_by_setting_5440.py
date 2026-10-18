"""`source.recipe.train-never-automatic` follows the setting (#5440, ruled 2026-10-17): under `here`, training starts by
itself once the corrected lines reach the threshold; under `offered` it is only offered; it starts once, not at every step.

WHY: the setting said "Training runs by itself on this Mac", but nothing started it: `offered_when` was listed, never run.
"""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.recipes import train_offers as offers_mod
from fichero_server.recipes.train_offers import due_starts

READY = {"ready": True, "sentence": None}
PARAMS = {"scope_ids": ["root"], "teacher": "gemini-2.5-pro"}


def _offer(mode: str, *, ready=READY, params=PARAMS, place="this-mac", action="training.start_here"):
    return {"step": "read", "job": "read-a-line", "readiness": ready, "setting": {"mode": mode, "why": ""},
            "ways": [{"method": "kraken", "available": True,
                      "targets": [{"place": place, "starts": action, "params": params}]}]}


def test_under_here_a_ready_offer_is_due_to_start_on_this_mac_5440():
    assert due_starts([_offer("here")]) == [("training.start_here", PARAMS)]


def test_nothing_starts_when_offered_not_ready_or_with_nothing_to_learn_from_5440():
    assert due_starts([_offer("offered")]) == []
    assert due_starts([_offer("here", ready={"ready": False, "sentence": "needs more"})]) == []
    assert due_starts([_offer("here", params=None)]) == []  # no teacher yet
    assert due_starts([_offer("here", place="huggingface-jobs", action="training.start")]) == []  # here means here


def test_it_starts_once_not_at_every_step_5440(db, monkeypatch):
    started = []
    monkeypatch.setattr(offers_mod, "_offers_now", lambda db, **kw: [_offer("here")])
    monkeypatch.setattr(offers_mod, "_corrected_lines", lambda db: 2500)
    monkeypatch.setattr(offers_mod, "_start", lambda db, action, params: started.append(action) or
                        jobs.enqueue(db, "train-on-this-mac", "training:test"))
    assert offers_mod.start_when_ready(db, mac_memory_gb=64) == ["training.start_here"]
    assert offers_mod.start_when_ready(db, mac_memory_gb=64) == []
    assert started == ["training.start_here"]


def test_a_step_that_finishes_asks_whether_training_is_due_5440(db, monkeypatch):
    from fichero_server.recipes import runner

    asked = []
    monkeypatch.setattr(offers_mod, "start_when_ready", lambda db, **kw: asked.append(True) or [])
    step, problems = {"state": "done"}, []
    runner._after_the_step(db, {"card": "check"}, step, {}, [], "done", None, None, {}, problems, "read")
    assert asked == [True] and problems == []


def test_after_a_failure_it_waits_for_more_corrections_and_says_why_5440(db, monkeypatch):
    """A training that failed is not started again at the next step: it waits for more corrected lines than it was
    started on, and says why it is waiting. With more, it starts again.
    WHY: a failure re-queued at every step would fail again on the same lines, all night."""
    import json
    from datetime import datetime

    started, lines = [], {"now": 2500}
    monkeypatch.setattr(offers_mod, "_offers_now", lambda db, **kw: [_offer("here")])
    monkeypatch.setattr(offers_mod, "_corrected_lines", lambda db: lines["now"])

    def start(db, action, params):
        started.append(action)
        # held off far ahead: the scheduler must not run this fake job and fail it with a reason of its own
        return jobs.enqueue(db, "train-on-this-mac", f"training:{len(started)}", run_after=datetime(2099, 1, 1))

    monkeypatch.setattr(offers_mod, "_start", start)
    assert offers_mod.start_when_ready(db, mac_memory_gb=64) == ["training.start_here"]
    (job_id,) = [r[0] for r in db.execute_fetchall("SELECT id FROM jobs WHERE kind = 'train-on-this-mac'")]
    assert json.loads(jobs.read_job(db, job_id)["detail"])["started_at_lines"] == 2500
    db.execute("UPDATE jobs SET state = 'failed', reason = 'the base reader would not load' WHERE id = ?", [job_id])

    assert offers_mod.start_when_ready(db, mac_memory_gb=64) == []
    why = offers_mod.held_after_failure(db)
    assert "would not load" in why and "2500" in why.replace(",", "")
    lines["now"] = 2600
    assert offers_mod.held_after_failure(db) is None
    assert offers_mod.start_when_ready(db, mac_memory_gb=64) == ["training.start_here"]
