"""The one job model, first slice (#5353): durable rows, one scheduler, one pause.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md -- `activity.one-job-model`,
`activity.durable.*`, `activity.pause.global*`, `activity.lane.group-by-model`,
`activity.lane.co-run-only-if-it-fits`, `activity.correction-reembed-visible`.

Each test drives the real scheduler thread against a real library opened through the database
manager, because that is how the engine finds a library's jobs; a test that called the job
function directly would pass while nothing ever ran it.
"""
from __future__ import annotations

import threading
import time


from fichero_server.db import EmbedOutcome
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


def _kind(monkeypatch, name, model, ran, *, seconds=0.0, during=None):
    def run(db, subject):
        if during:
            during(+1)
        try:
            time.sleep(seconds)
            ran.append(subject)
        finally:
            if during:
                during(-1)

    monkeypatch.setitem(jobs.KINDS, name, jobs.Kind(run=run, model=model))


def _states(db):
    return {row[0]: (row[1], row[2]) for row in db.execute_fetchall("SELECT subject, state, reason FROM jobs")}


def _wait_for(predicate, seconds=60.0):  # returns when true; the lane may be busy with another job
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TestDurability:
    def test_a_waiting_job_survives_a_restart_and_then_runs(self, test_package, monkeypatch):
        """WHY: the queue's whole promise is that quitting loses nothing. The re-embed it replaced
        was a daemon thread: quit mid-queue and the page was never re-embedded, with no trace."""
        ran: list[str] = []
        _kind(monkeypatch, "t-durable", None, ran)
        db = db_manager.get_database(test_package)
        jobs.set_paused(True)
        with db.transaction():
            jobs.enqueue(db, "t-durable", "page-1")

        db_manager.close_database(test_package)  # quit
        monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process
        db = db_manager.get_database(test_package)  # relaunch: the open resumes its jobs
        assert _states(db) == {"page-1": ("waiting", None)}
        assert ran == []

        jobs.set_paused(False)
        assert _wait_for(lambda: ran == ["page-1"])
        assert _wait_for(lambda: _states(db)["page-1"][0] == "done")

    def test_an_interrupted_job_carries_on_and_a_thrice_interrupted_one_is_set_aside(self, test_package, monkeypatch):
        """WHY: a crash mid-job leaves the row `running`. Failing it (what the workflow runs do
        today) throws the work away; retrying forever lets one poison page wedge the queue."""
        ran: list[str] = []
        _kind(monkeypatch, "t-crash", None, ran)
        db = db_manager.get_database(test_package)
        jobs.set_paused(True)
        jobs.enqueue(db, "t-crash", "once")
        jobs.enqueue(db, "t-crash", "poison")
        db.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE subject = 'once'")
        db.execute("UPDATE jobs SET state = 'running', attempts = 3 WHERE subject = 'poison'")

        db_manager.close_database(test_package)  # the crash
        monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
        db = db_manager.get_database(test_package)

        states = _states(db)
        assert states["once"] == ("waiting", "Interrupted; carries on")
        assert states["poison"][0] == "failed" and "Interrupted 3 times" in states["poison"][1]
        jobs.set_paused(False)
        assert _wait_for(lambda: ran == ["once"])

    def test_many_changes_to_one_page_make_one_waiting_job(self, db, monkeypatch):
        """WHY: a scholar correcting line after line must not queue one embed per line; the job
        reads the page when it runs, so one waiting job covers every change before it."""
        _kind(monkeypatch, "t-coalesce", None, [])
        jobs.set_paused(True)
        first = jobs.enqueue(db, "t-coalesce", "page")
        assert jobs.enqueue(db, "t-coalesce", "page") == first
        assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 't-coalesce'")[0] == 1


class TestPause:
    def test_pause_holds_every_job_says_why_and_is_kept_in_app_settings(self, db, client, app_db, monkeypatch):
        """WHY: one switch must stop everything that runs by itself, say so in the job's row, and
        still be on after relaunch, which is why it lives in app settings and not in memory."""
        ran: list[str] = []
        _kind(monkeypatch, "t-pause", None, ran)
        r = client.put("/api/activity/jobs/paused", json={"paused": True})
        assert r.status_code == 200 and r.json() == {"paused": True}
        assert app_db.get_setting(jobs.PAUSE_SETTING_KEY) == "1"

        jobs.enqueue(db, "t-pause", "page")
        time.sleep(0.3)
        assert ran == []
        body = client.get("/api/activity/jobs").json()
        assert body["paused"] is True
        [row] = [j for j in body["jobs"] if j["task_type"] == "t-pause"]
        assert (row["state"], row["reason"]) == ("waiting", "Paused by you")

        assert client.put("/api/activity/jobs/paused", json={"paused": False}).json() == {"paused": False}
        assert _wait_for(lambda: ran == ["page"])

    def test_pause_survives_a_relaunch_and_activity_says_so(self, test_package, client, monkeypatch):
        """WHY (#5355, `activity.pause.global-survives-relaunch`): a Mac paused at quit is paused at
        launch. The open's own resume (interrupted jobs back to waiting) must not start them, and
        Activity must say paused, through the same routes the window reads."""
        ran: list[str] = []
        _kind(monkeypatch, "t-relaunch", None, ran)
        db = db_manager.get_database(test_package)
        assert client.put("/api/activity/jobs/paused", json={"paused": True}).json() == {"paused": True}
        jobs.enqueue(db, "t-relaunch", "waiting-page")
        jobs.enqueue(db, "t-relaunch", "interrupted-page")
        db.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE subject = 'interrupted-page'")

        db_manager.close_database(test_package)  # quit
        monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process
        db_manager.get_database(test_package)  # relaunch: the open resumes its jobs

        time.sleep(0.3)
        assert ran == []
        body = client.get("/api/activity/jobs").json()
        assert body["paused"] is True
        rows = [j for j in body["jobs"] if j["task_type"] == "t-relaunch"]
        assert rows and all((j["state"], j["reason"]) == ("waiting", "Paused by you") for j in rows)

        assert client.put("/api/activity/jobs/paused", json={"paused": False}).json() == {"paused": False}
        assert _wait_for(lambda: sorted(ran) == ["interrupted-page", "waiting-page"])

    def test_pausing_is_an_audited_undoable_action(self, db, client):
        """WHY: controls are actions (`activity.pause.controls-are-actions`): the window, MCP and
        the command line reach the same audited path, and Undo puts the switch back."""
        from fichero_server.models import ActionAudit

        client.put("/api/activity/jobs/paused", json={"paused": True})
        audit = [a for a in db.all(ActionAudit) if a.action_name == "background.pause"][-1]
        assert audit.before == {"paused": False} and audit.after == {"paused": True}
        assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
        assert jobs.is_paused() is False


class TestTheLocalModelLane:
    def test_work_is_grouped_by_the_model_already_loaded(self, db, monkeypatch):
        """WHY: switching heavy models costs a load each time (Kraken 2-3 GB); alternating page by
        page pays it on every page. The lane runs everything for the loaded model first."""
        ran: list[str] = []
        _kind(monkeypatch, "t-a", "model-a", ran)
        _kind(monkeypatch, "t-b", "model-b", ran)
        jobs.set_paused(True)
        for subject, kind in (("a1", "t-a"), ("b1", "t-b"), ("a2", "t-a"), ("b2", "t-b")):
            jobs.enqueue(db, kind, subject)
        jobs.set_paused(False)
        assert _wait_for(lambda: len(ran) == 4)
        assert ran == ["a1", "a2", "b1", "b2"]

    def test_two_heavy_jobs_never_run_at_once(self, db, monkeypatch):
        """WHY: two heavy models together on a Mac's shared memory swap and each runs slower than
        alone; on an 8 GB Mac they do not fit at all. Jobs queued from many threads still run
        one at a time."""
        ran: list[str] = []
        live = [0]
        peak = [0]
        lock = threading.Lock()

        def during(step):
            with lock:
                live[0] += step
                peak[0] = max(peak[0], live[0])

        _kind(monkeypatch, "t-x", "model-x", ran, seconds=0.05, during=during)
        _kind(monkeypatch, "t-y", "model-y", ran, seconds=0.05, during=during)
        threads = [
            threading.Thread(target=jobs.enqueue, args=(db, "t-x" if i % 2 else "t-y", f"p{i}"))
            for i in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert _wait_for(lambda: len(ran) == 6)
        assert peak[0] == 1

    def test_a_heavy_job_waits_for_a_kraken_page_and_says_so(self, db, monkeypatch):
        """WHY: a workflow's Kraken page holds Kraken's lock outside the queue; starting the
        embedder beside it would put two heavy models in memory. The job waits, and its row says
        what for, instead of looking stuck."""
        from fichero_server.llm import kraken_runtime

        ran: list[str] = []
        _kind(monkeypatch, "t-embed", "embedder", ran)
        with kraken_runtime._INFERENCE_LOCK:
            jobs.enqueue(db, "t-embed", "page")
            assert _wait_for(lambda: _states(db)["page"][1] == "Waiting for Kraken (another page is using it)")
            assert ran == []
        assert _wait_for(lambda: ran == ["page"])

    def test_a_failure_is_kept_with_its_reason(self, db, monkeypatch):
        """WHY: a failed job that vanished, or failed without saying why, is the defect the
        Activity window exists to end."""
        def boom(db, subject):
            raise RuntimeError("the model is not installed")

        monkeypatch.setitem(jobs.KINDS, "t-fail", jobs.Kind(run=boom, model=None))
        jobs.enqueue(db, "t-fail", "page")
        assert _wait_for(lambda: _states(db).get("page", ("",))[0] == "failed")
        assert _states(db)["page"] == ("failed", "the model is not installed")


class TestTheCorrectionReembedRunsThroughTheQueue:
    def test_a_correction_queues_a_visible_reembed_that_runs_when_resumed(self, db, client, monkeypatch):
        """WHY (`activity.correction-reembed-visible`): the re-embed after a correction was a raw
        daemon thread: invisible, unpausable, lost on quit. It is now a job row, written with the
        correction, shown in Activity, held by the pause, and run by the scheduler."""
        from tests.unit.api.seeded_converted_page import seed_page

        from fichero_server.actions import page_text_cache
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
        from fichero_server.models import Artifact

        _, page, art = seed_page(db)
        assert client.put(f"/api/artifacts/{art.id}/regions",
                          json={"op": "move", "indices": [3], "bbox": [0.5, 0.9, 0.1, 0.05]}).status_code == 200
        row = live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]
        embedded: list[str] = []
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: embedded.append(doc.page_content) or EmbedOutcome(embedded=True))

        jobs.set_paused(True)
        ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
        rid = registry.invoke(db, "representation.create", {
            "document_id": page.id, "segment_id": row.id, "kind": "transcription",
            "content": "In the year of Our Lord"}, ctx).result["id"]
        registry.invoke(db, "reading.choose",
                        {"segment_id": row.id, "kind": "transcription", "representation_id": rid}, ctx)

        [queued] = [j for j in client.get("/api/activity/jobs").json()["jobs"]
                    if j["task_type"] == page_text_cache.REEMBED_KIND]
        assert queued["state"] == "waiting" and queued["name"] == "Make vectors for search"
        time.sleep(0.3)
        assert embedded == []

        jobs.set_paused(False)
        assert _wait_for(lambda: embedded and embedded[-1].startswith("In the year of Our Lord"))
        assert _wait_for(lambda: _states(db)[page.id][0] == "done")


class TestPerJobControls:
    """`activity.pause.per-job`, `activity.pause.controls-are-actions`: one job paused, resumed or
    stopped from the window, MCP or the command line, through one audited action each."""

    def test_a_paused_job_waits_stays_paused_after_a_relaunch_and_runs_when_resumed(
            self, test_package, client, monkeypatch):
        """WHY: pausing one job must hold exactly that job while the rest of the queue moves, and
        a quit must not quietly un-pause it (the opposite of what workflow runs do today)."""
        from fichero_server.models import ActionAudit

        ran: list[str] = []
        _kind(monkeypatch, "t-one", None, ran)
        db = db_manager.get_database(test_package)
        jobs.set_paused(True)
        held = jobs.enqueue(db, "t-one", "held")
        r = client.put(f"/api/activity/jobs/{held}/paused", json={"paused": True})
        assert r.status_code == 200 and r.json() == {"id": held, "state": "paused"}
        jobs.enqueue(db, "t-one", "other")
        jobs.set_paused(False)
        assert _wait_for(lambda: ran == ["other"])

        db_manager.close_database(test_package)
        monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
        db = db_manager.get_database(test_package)
        assert _states(db)["held"] == ("paused", "Paused by you")
        [row] = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == held]
        assert (row["state"], row["reason"]) == ("paused", "Paused by you")

        audit = [a for a in db.all(ActionAudit) if a.action_name == "job.pause"][-1]
        assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200  # undo = resume
        assert _wait_for(lambda: ran == ["other", "held"])

    def test_cancel_stops_a_waiting_job_and_lets_a_running_one_finish_its_item(self, db, client, monkeypatch):
        """WHY: a cancelled job must never run; one already running cannot be interrupted midway,
        so the answer must say it is still running rather than claim it stopped."""
        import threading as _threading

        gate, started, ran = _threading.Event(), _threading.Event(), []

        def slow(db, subject):
            started.set()
            gate.wait(30)
            ran.append(subject)

        monkeypatch.setitem(jobs.KINDS, "t-slow", jobs.Kind(run=slow, model=None))
        running = jobs.enqueue(db, "t-slow", "running")
        assert started.wait(30)
        waiting = jobs.enqueue(db, "t-slow", "waiting")
        assert client.post(f"/api/activity/jobs/{waiting}/cancel").json() == {"id": waiting, "state": "cancelled"}
        assert client.post(f"/api/activity/jobs/{running}/cancel").json() == {"id": running, "state": "running"}
        gate.set()
        assert _wait_for(lambda: _states(db)["running"][0] == "done")
        assert ran == ["running"]
        assert _states(db)["waiting"] == ("cancelled", "Stopped by you")

    def test_a_kind_that_runs_elsewhere_is_stopped_by_its_own_cancel(self, db, client, monkeypatch):
        """WHY: a training Job runs on Hugging Face; only its kind knows how to stop it there (and
        stop the bill). The generic control must hand over, not mark the row and walk away."""
        asked = []
        monkeypatch.setitem(jobs.KINDS, "t-far", jobs.Kind(
            run=lambda db, s: None, model=None, cancel=lambda db, job_id: asked.append(job_id) or "running"))
        jobs.set_paused(True)
        job = jobs.enqueue(db, "t-far", "far")
        assert client.post(f"/api/activity/jobs/{job}/cancel").json() == {"id": job, "state": "running"}
        assert asked == [job]

    def test_a_page_a_run_waits_for_is_paused_with_its_run_and_unknown_ids_are_404(self, db, client):
        """WHY: pausing a page a running step is waiting for would leave that step hanging with
        no way to tell why; the run has its own Pause."""
        import threading as _threading

        gate = _threading.Event()
        first = jobs.submit(db, "find-lines", "first", model="kraken:blla", fn=lambda: gate.wait(30))
        page = jobs.submit(db, "find-lines", "page", model="kraken:blla", fn=lambda: None)
        try:
            assert client.put(f"/api/activity/jobs/{page.job_id}/paused", json={"paused": True}).status_code == 409
            assert client.post("/api/activity/jobs/no-such-job/cancel").status_code == 404
            assert client.post(f"/api/activity/jobs/{page.job_id}/cancel").json()["state"] == "cancelled"
        finally:
            gate.set()
        first.result(30)
        assert page.cancelled()
