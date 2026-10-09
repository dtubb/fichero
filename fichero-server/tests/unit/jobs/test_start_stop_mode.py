"""Start / Stop, held work that starts by itself, pause and stop on a counted row, and the import row's
details (#5621, #5623).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.mode.start-stop`,
`activity.throttle.recheck-when-it-clears`, `activity.pause.per-queue`,
`activity.details.what-it-works-on-now`. The maintainer, testing the Dev Embedded build: work held for
battery stayed held after plugging in, nothing could say "run it now", and the import's "Processing
imported pages" row showed a bar and "Nothing written for this row yet".

Through the routes and the real scheduler; the Mac's signals are faked at the throttle's probes (the
suite turns the throttle off by default, the test machine is often in use), and the import's stages are
faked so no model loads.
"""
from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.importers import derivatives

IN_USE = "Waiting: you're using the Mac"
BATTERY = "Waiting: the Mac is on battery"
MEMORY = "Waiting: memory is tight"


@pytest.fixture
def mac(monkeypatch):
    """Switchable signals in the throttle's own order and exemptions; memory pressure normal."""
    state = {"memory": False, "battery": False, "in_use": False}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(throttle, "PROBES", [
        (lambda: MEMORY if state["memory"] else None, True),
        (lambda: BATTERY if state["battery"] else None, False),
        (lambda: IN_USE if state["in_use"] else None, False),
    ])
    return state


@pytest.fixture
def heavy(monkeypatch):
    ran: list[str] = []
    monkeypatch.setitem(jobs.KINDS, "t-heavy", jobs.Kind(run=lambda db, s: ran.append(s), model="embedder"))
    return ran


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _row(client, kind):
    body = client.get("/api/activity/jobs").json()
    return next((j for j in body["jobs"] if j["task_type"] == kind), None), body


def test_work_held_for_battery_starts_when_power_returns(db, mac, heavy):
    """`activity.throttle.recheck-when-it-clears` -- WHY (#5621): plugging in did not start work held for
    battery. Nothing is pressed and nothing new is queued: the lane looks again by itself."""
    mac["battery"] = True
    jobs.enqueue(db, "t-heavy", "page-1")
    assert _wait_for(lambda: db.execute_fetchone(
        "SELECT reason FROM jobs WHERE subject = 'page-1'")[0] == BATTERY)
    time.sleep(0.2)
    assert heavy == []
    mac["battery"] = False  # plugged in
    assert _wait_for(lambda: heavy == ["page-1"])


def test_the_battery_reading_is_trusted_for_seconds_not_half_a_minute():
    """WHY (#5621): the reading was cached 30 s, so work waited half a minute after plugging in."""
    assert throttle.BATTERY_READING_SECONDS <= 10.0


def test_start_lets_held_work_go_and_automatic_holds_it_again(db, client, mac, heavy):
    """`activity.mode.start-stop` -- WHY (ruled 2026-10-09): Start means go ahead although I am using the
    Mac, until pressed again. Through `PUT /api/activity/jobs/mode`, the action behind both buttons."""
    mac["in_use"] = True
    jobs.enqueue(db, "t-heavy", "page-1")
    row, body = _row(client, "t-heavy")
    assert (body["mode"], row["reason"], body["machine"]["why_wait"]) == ("automatic", IN_USE, IN_USE)
    time.sleep(0.2)
    assert heavy == []

    assert client.put("/api/activity/jobs/mode", json={"mode": "started"}).json() == {"mode": "started"}
    assert _wait_for(lambda: heavy == ["page-1"])
    _row_now, body = _row(client, "t-heavy")
    assert body["mode"] == "started" and body["paused"] is False
    assert body["machine"]["why_wait"] is None and body["machine"]["in_use"] is True

    assert client.put("/api/activity/jobs/mode", json={"mode": "automatic"}).json() == {"mode": "automatic"}
    jobs.enqueue(db, "t-heavy", "page-2")
    row, body = _row(client, "t-heavy")
    assert (body["mode"], row["reason"]) == ("automatic", IN_USE)
    time.sleep(0.2)
    assert heavy == ["page-1"]


def test_start_never_lifts_the_memory_hold(db, client, mac, heavy):
    """WHY (ruled 2026-10-09): memory safety still applies to forced work."""
    mac["memory"] = True
    client.put("/api/activity/jobs/mode", json={"mode": "started"})
    jobs.enqueue(db, "t-heavy", "page-1")
    row, body = _row(client, "t-heavy")
    assert row["reason"] == MEMORY and body["machine"]["why_wait"] == MEMORY
    time.sleep(0.2)
    assert heavy == []
    mac["memory"] = False
    assert _wait_for(lambda: heavy == ["page-1"])


def test_stop_pauses_all_work_and_the_mode_survives_as_a_setting(db, client, mac, heavy):
    """Stop is Pause Background Work: nothing that runs by itself starts, rows say "Paused by you", and
    `paused` and `mode` agree. Start from paused lifts the pause too (one mode, never a mix)."""
    assert client.put("/api/activity/jobs/mode", json={"mode": "paused"}).status_code == 200
    jobs.enqueue(db, "t-heavy", "page-1")
    row, body = _row(client, "t-heavy")
    assert (body["mode"], body["paused"], row["reason"]) == ("paused", True, "Paused by you")
    assert jobs.is_paused() and not jobs.is_started()
    time.sleep(0.2)
    assert heavy == []
    client.put("/api/activity/jobs/mode", json={"mode": "started"})
    assert not jobs.is_paused() and jobs.is_started()
    assert _wait_for(lambda: heavy == ["page-1"])


def test_the_mode_is_one_audited_undoable_action(db, client, mac):
    """`activity.pause.controls-are-actions`: the mode is changed by `background.mode`, audited, and its
    undo puts the mode back as it was."""
    from fichero_server.actions.registry import registry

    action = registry.get("background.mode")
    assert action.undoable
    client.put("/api/activity/jobs/mode", json={"mode": "started"})
    assert action.invert({"mode": "automatic"}, {"mode": "started"}, None) == (
        "background.mode", {"mode": "automatic"})
    assert client.put("/api/activity/jobs/mode", json={"mode": "sideways"}).status_code == 422


def _import_queue(db, n_embeds=3):
    """The import's stages queued: thumbnails done, embeds waiting (as the maintainer's 97 of 146)."""
    derivatives.register_job_kinds()
    thumbs = [jobs.enqueue(db, derivatives.THUMBNAIL_KIND, f"doc-t{i}") for i in range(2)]
    embeds = [jobs.enqueue(db, derivatives.EMBED_KIND, f"doc-e{i}") for i in range(n_embeds)]
    for job in thumbs:  # made since the embeds were queued, as an import's are
        db.execute("UPDATE jobs SET state = 'done', started_at = now(), finished_at = now() WHERE id = ?", [job])
    return embeds


def test_the_import_row_pauses_resumes_and_stops_its_stages(db, client, mac, monkeypatch):
    """`activity.pause.per-queue` -- WHY (#5621): the import's row had no Pause or Stop. Its id reaches the
    stages it stands for; paused pages are counted on one row, not listed one by one."""
    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: None)
    mac["in_use"] = True  # hold the embeds where they are
    _import_queue(db)

    assert client.put("/api/activity/jobs/derivatives/paused", json={"paused": True}).json()["state"] == "paused"
    states = dict(db.execute_fetchall("SELECT state, count(*) FROM jobs WHERE kind = 'embed' GROUP BY state"))
    assert states == {"paused": 3}
    body = client.get("/api/activity/jobs").json()
    paused_rows = [j for j in body["jobs"] if j["task_type"] == "embed"]
    assert [(j["id"], j["state"], j["total"]) for j in paused_rows] == [("paused:embed", "paused", 3)]

    assert client.put("/api/activity/jobs/paused:embed/paused", json={"paused": False}).json()["state"] == "waiting"
    assert client.post("/api/activity/jobs/waiting:embed/cancel").json()["state"] == "cancelled"
    states = dict(db.execute_fetchall("SELECT state, count(*) FROM jobs WHERE kind = 'embed' GROUP BY state"))
    assert states == {"cancelled": 3}


def test_the_import_rows_details_say_what_it_works_on_its_stages_and_its_log(db, client, mac, monkeypatch):
    """`activity.details.what-it-works-on-now` -- WHY (#5623): selecting "Processing imported pages" showed a
    bar and "Log: Nothing written for this row yet". Its tree has its stages with their state and counts,
    the page running now, and a log of its pages, newest last."""
    import threading

    release = threading.Event()
    started: list[str] = []

    def embed(doc_id, library):
        started.append(doc_id)
        release.wait(30)

    monkeypatch.setattr(derivatives, "_embed_stage", embed)
    _import_queue(db)
    try:
        assert _wait_for(lambda: started == ["doc-e0"])
        tree = client.get("/api/activity/jobs/derivatives").json()
        assert (tree["name"], tree["state"]) == ("Processing imported pages", "running")
        stages = {c["name"]: c for c in tree["children"]}
        assert stages["Make thumbnails"]["state"] == "done"
        assert (stages["Make thumbnails"]["done"], stages["Make thumbnails"]["total"]) == (2, 2)
        embeds = stages["Embed for search"]
        assert (embeds["state"], embeds["done"], embeds["total"]) == ("running", 0, 3)
        assert embeds["working_on"] == "doc-e0"
        assert tree["working_on"] == "Embed for search, doc-e0"
        assert (tree["done"], tree["total"]) == (2, 5)

        log = client.get("/api/activity/jobs/derivatives/log").json()["lines"]
        messages = [line["message"] for line in log]
        assert any(m.startswith("Done: ") for m in messages)
        assert any(m.startswith("Started ") and "doc-e0" in m for m in messages)
    finally:
        release.set()
    assert _wait_for(lambda: client.get("/api/activity/jobs/derivatives").status_code == 404)


def test_a_counted_kind_row_reads_as_a_tree_too(db, client, mac, heavy):
    mac["in_use"] = True
    jobs.enqueue(db, "t-heavy", "a")
    jobs.enqueue(db, "t-heavy", "b")
    row, _ = _row(client, "t-heavy")
    assert (row["id"], row["total"]) == ("waiting:t-heavy", 2)
    tree = client.get("/api/activity/jobs/waiting:t-heavy").json()
    assert (tree["state"], tree["reason"], tree["total"]) == ("waiting", IN_USE, 2)


def test_work_a_person_starts_runs_on_battery_and_background_work_waits(db, mac, heavy):
    """Ruled 2026-10-04, found broken 2026-10-09 (a Kraken run clicked on battery was held): a job a
    person started runs on battery or while they use the Mac, whatever its kind; only work the engine,
    a synced folder or a kept export started waits for those. Memory and heat still hold everything."""
    mac["battery"] = True
    jobs.enqueue(db, "t-heavy", "background-page")
    jobs.enqueue(db, "t-heavy", "clicked-page", started_by="owner")
    assert _wait_for(lambda: "clicked-page" in heavy), "the person's job ran on battery"
    time.sleep(0.2)
    assert "background-page" not in heavy, "background work still waits for power"
    mac["battery"] = False
    assert _wait_for(lambda: "background-page" in heavy)
