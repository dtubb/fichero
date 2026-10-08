"""A waiting row says what it truly waits for (#5606, `activity.waiting-says-why`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. On the onboarding box,
"Embed for search" (0 of 203) said "Waiting: you're using the Mac" while the same response's
machine state said the Mac was not in use: the reason was left on the row by an earlier throttle
scan, and the real wait was the model lane, held by a recipe's Paleographer Review. "Processing
imported pages" sat at 100 of 406 for hours with no reason at all.

Through `GET /api/activity/jobs` with the real lanes: the model lane is held by a real handed-in
page under a real run row; the Mac's signals are faked at the throttle's readings, so the row's
reason and `machine` read the Mac by the same path. The stages themselves are faked.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status

HELD = "Waiting for the model lane: Paleographer Review is reading"
IN_USE = "Waiting: you're using the Mac"


@pytest.fixture
def mac(monkeypatch):
    """A calm, idle Mac on AC with the throttle on (the suite turns it off by default)."""
    state = {"idle": 600.0}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: 0)
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: False)
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    return state


@pytest.fixture
def stages(monkeypatch):
    ran: list[tuple[str, str]] = []
    monkeypatch.setattr(derivatives, "_thumbnail_stage", lambda doc_id, library: ran.append(("thumbnail", doc_id)))
    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: ran.append(("embed", doc_id)))
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    return ran


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane_held(db):
    """The model lane held by a page of a Paleographer Review run, as a recipe's reading holds it."""
    release = threading.Event()
    jobs.record_child_run(db, "run-review", parent_step=None, name="Paleographer Review")
    jobs.record_step(db.path, "run-review", "read", status="running", name="Read the page")
    page = jobs.submit(db, "read-a-page", "page-1", model="omlx:mlx-community/reader",
                       fn=lambda: release.wait(30))
    jobs.set_parent(db, page.job_id, "run-review:read")
    assert _wait_for(lambda: db.execute_fetchone(
        "SELECT state FROM jobs WHERE id = ?", [page.job_id])[0] == "running")
    yield page
    release.set()
    page.result(timeout=30)


def _docs(db, n):
    docs = [Document(name=f"p{i}.md", doc_type=DocType.file, file_type=FileType.text,
                     status=Status.pending, page_content=f"page {i}") for i in range(n)]
    for doc in docs:
        db.save(doc)
    return docs


def _rows(client):
    body = client.get("/api/activity/jobs").json()
    return {j["task_type"]: j for j in body["jobs"]}, body["machine"]


def test_a_job_behind_the_model_lane_names_what_holds_it_not_the_mac(db, client, mac, stages, lane_held):
    """WHY (#5606): the embed row said "you're using the Mac" (an earlier scan's words, left on the
    row) while `machine.in_use` was false; the true wait was the lane, held by Paleographer Review."""
    derivatives.register_job_kinds()
    jobs.enqueue(db, derivatives.EMBED_KIND, "doc-1")
    db.execute("UPDATE jobs SET reason = ? WHERE kind = ?", [IN_USE, derivatives.EMBED_KIND])  # stale
    rows, machine = _rows(client)
    assert machine["in_use"] is False and machine["why_wait"] is None
    assert (rows["embed"]["state"], rows["embed"]["reason"]) == ("waiting", HELD)


def test_the_mac_in_use_is_the_reason_only_while_the_throttle_says_so(db, client, mac, stages, lane_held):
    """WHY: "you're using the Mac" is true only while the throttle reads the Mac as in use; the
    moment it is idle again the row says the lane, in the same response as `machine`."""
    derivatives.register_job_kinds()
    jobs.enqueue(db, derivatives.EMBED_KIND, "doc-1")
    mac["idle"] = 3.0
    rows, machine = _rows(client)
    assert machine["in_use"] is True and machine["why_wait"] == IN_USE
    assert rows["embed"]["reason"] == IN_USE
    mac["idle"] = 600.0
    rows, machine = _rows(client)
    assert machine["in_use"] is False
    assert rows["embed"]["reason"] == HELD


def test_the_imports_progress_row_says_why_it_waits(db, client, test_package, mac, stages, lane_held):
    """WHY (#5606): "Processing imported pages" sat at 100 of 406 for hours with reason null while
    Paleographer Review held the lane. Thumbnails made, embeds waiting: the row waits, and says for what."""
    docs = _docs(db, 3)
    derivatives.queue_derivatives(docs, library_path=test_package)
    assert _wait_for(lambda: sum(1 for s in stages if s[0] == "thumbnail") == 3)
    assert _wait_for(lambda: db.execute_fetchone(
        "SELECT count(*) FROM jobs WHERE kind = 'thumbnail' AND state = 'done'")[0] == 3)
    rows, _ = _rows(client)
    progress = rows["derivatives"]
    assert progress["current"] < progress["total"]
    assert (progress["state"], progress["reason"]) == ("waiting", HELD)
    assert not [s for s in stages if s[0] == "embed"]


def test_every_waiting_row_has_a_reason(db, client, mac, stages):
    """WHY: a row that waits never has reason null. A job whose lane is free and that nothing holds
    still says it waits for its turn; paused, it says so."""
    jobs.set_paused(True)
    derivatives.register_job_kinds()
    jobs.enqueue(db, derivatives.EMBED_KIND, "doc-1")
    rows, _ = _rows(client)
    assert rows["embed"]["reason"] == "Paused by you"
    assert jobs.waiting_reason(db, "x", derivatives.EMBED_KIND) == "Paused by you"
    jobs.set_paused(False)
    assert jobs.waiting_reason(db, "x", derivatives.EMBED_KIND) == "Waiting for its turn on the model lane"
