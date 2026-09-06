"""Background-jobs Activity surface ([[user-machine-always-useful]] FIX 2).

The user must be able to SEE what is consuming compute and how far along it is.
These pin the live snapshot (from the derivative/embed progress map) and the
GET /api/activity/jobs endpoint that exposes it plus rough process CPU%.
"""

from __future__ import annotations

from fichero_server.importers import derivatives


class TestBackgroundJobsSnapshot:
    def test_snapshot_reflects_active_progress(self, monkeypatch):
        monkeypatch.setattr(
            derivatives, "_progress", {"/lib/A.fichero": {"done": 3, "total": 10}}
        )
        jobs = derivatives.background_jobs_snapshot()
        assert len(jobs) == 1
        job = jobs[0]
        assert job["task_type"] == "derivatives"
        assert job["current"] == 3
        assert job["total"] == 10
        assert job["percent"] == 30.0
        assert job["state"] == "running"
        assert job["library"] == "/lib/A.fichero"

    def test_empty_when_nothing_is_running(self, monkeypatch):
        # An entry is deleted the moment its queue finishes, so an empty map is
        # the honest "nothing running" (not a stale completed job).
        monkeypatch.setattr(derivatives, "_progress", {})
        assert derivatives.background_jobs_snapshot() == []

    def test_zero_total_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr(
            derivatives, "_progress", {"/lib/B.fichero": {"done": 0, "total": 0}}
        )
        assert derivatives.background_jobs_snapshot()[0]["percent"] == 0.0


class TestJobsEndpoint:
    def _library_key(self, db) -> str:
        from pathlib import Path

        return str(Path(db.path).parent)

    def test_endpoint_returns_jobs_and_cpu_fields(self, client, db, monkeypatch):
        # Key the queue by THIS library, matching the endpoint's per-library filter.
        monkeypatch.setattr(
            derivatives, "_progress", {self._library_key(db): {"done": 1, "total": 4}}
        )
        response = client.get("/api/activity/jobs")
        assert response.status_code == 200
        body = response.json()
        derivative_jobs = [j for j in body["jobs"] if j["task_type"] == "derivatives"]
        assert len(derivative_jobs) == 1
        assert derivative_jobs[0]["percent"] == 25.0
        assert derivative_jobs[0]["name"] == "Processing imported pages"
        # CPU fields present; percent may be None on the first sample.
        assert "process_cpu_percent" in body
        assert body["cpu_count"] >= 1

    def test_a_queue_in_another_library_is_not_shown(self, client, monkeypatch):
        # Per-library: a queue keyed to a different library must not leak here.
        monkeypatch.setattr(
            derivatives, "_progress", {"/some/other.fichero": {"done": 1, "total": 4}}
        )
        body = client.get("/api/activity/jobs").json()
        assert [j for j in body["jobs"] if j["task_type"] == "derivatives"] == []

    def test_endpoint_is_empty_when_idle(self, client, monkeypatch):
        monkeypatch.setattr(derivatives, "_progress", {})
        body = client.get("/api/activity/jobs").json()
        assert [j for j in body["jobs"] if j["task_type"] == "derivatives"] == []

    def test_a_failed_workflow_run_shows_with_its_reason(self, client, monkeypatch):
        # FIX 3: a Kraken run that died on "Kraken not installed" must appear as a
        # clear FAILED entry with the reason — Daniel ran it 3× not knowing it failed.
        from types import SimpleNamespace

        monkeypatch.setattr(derivatives, "_progress", {})

        class _FakeStore:
            async def list_workflow_runs(self, limit=50):
                return [
                    SimpleNamespace(
                        thread_id="t-kraken",
                        workflow_id="w1",
                        workflow_name="Detect Regions (Kraken)",
                        status="failed",
                        error="Kraken is not installed. Install it from Settings → AI.",
                        progress_timeline=[],
                    ),
                    SimpleNamespace(  # a completed run must NOT show as a job
                        thread_id="t-done",
                        workflow_id="w2",
                        workflow_name="Transcribe",
                        status="completed",
                        error=None,
                        progress_timeline=[],
                    ),
                ]

        monkeypatch.setattr(
            "fichero_server.api.routes.system.activity.get_activity_tracker",
            lambda db_path: SimpleNamespace(store=_FakeStore()),
        )

        body = client.get("/api/activity/jobs").json()
        workflow_jobs = [j for j in body["jobs"] if j["task_type"] == "workflow"]
        assert len(workflow_jobs) == 1  # the completed one is excluded
        job = workflow_jobs[0]
        assert job["name"] == "Detect Regions (Kraken)"
        assert job["state"] == "failed"
        assert "Kraken is not installed" in job["reason"]
