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
    def test_endpoint_returns_jobs_and_cpu_fields(self, client, monkeypatch):
        monkeypatch.setattr(
            derivatives, "_progress", {"/lib/A.fichero": {"done": 1, "total": 4}}
        )
        response = client.get("/api/activity/jobs")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["jobs"][0]["percent"] == 25.0
        assert body["jobs"][0]["name"] == "Processing imported pages"
        # CPU fields present; percent may be None on the first sample.
        assert "process_cpu_percent" in body
        assert body["cpu_count"] >= 1

    def test_endpoint_is_empty_when_idle(self, client, monkeypatch):
        monkeypatch.setattr(derivatives, "_progress", {})
        body = client.get("/api/activity/jobs").json()
        assert body["count"] == 0
        assert body["jobs"] == []
