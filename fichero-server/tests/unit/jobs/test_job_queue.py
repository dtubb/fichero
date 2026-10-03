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

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def fresh_scheduler(monkeypatch, app_db):
    """A scheduler with nothing loaded and the pause off, per test: the module's scheduler and
    the pause are process-wide, and a model left loaded by another test would change the order."""
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(False)
    yield
    jobs.set_paused(False)


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
        monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: embedded.append(doc.page_content))

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
