"""POST /api/workers starts a worker through an audited action; the row shows in Activity; stop and tell go
through the same route (dev-workflows.run.worker-start-stop, #6116)."""

from __future__ import annotations

import time

from fichero_server.workflows import worker_process as wp


def _until(pred, secs=20):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_post_workers_starts_a_fake_worker_and_its_row_settles(client, db, tmp_path):
    r = client.post("/api/workers", json={"kind": "fake", "brief": "x", "workdir": str(tmp_path), "timeout_s": 20,
                                         "scenario": {"lines": ["hi"], "exit": 0}})
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    assert wp.wait(job, 20) == "done"
    assert db.execute_fetchone("SELECT kind, state FROM jobs WHERE id = ?", [job]) == ("worker", "done")


def test_post_workers_stop_cancels_a_running_worker(client, db, tmp_path):
    job = client.post("/api/workers", json={"kind": "fake", "brief": "x", "workdir": str(tmp_path), "timeout_s": 60,
                                           "scenario": {"lines": ["up"], "hang": True}}).json()["job_id"]
    assert wp.wait_for_line(job, "up", 20)
    assert client.post(f"/api/workers/{job}/stop").status_code == 200
    assert wp.wait(job, 20) == "cancelled"


def test_a_bad_request_is_a_422(client, tmp_path):
    r = client.post("/api/workers", json={"kind": "gpt", "brief": "x", "workdir": str(tmp_path), "timeout_s": 5})
    assert r.status_code == 422
    assert client.post("/api/workers/tell", json={"task": "none", "generation": 1, "text": "x"}).status_code == 409


def test_a_release_engine_has_no_worker_actions_and_refuses_to_start(tmp_path):
    """/api/actions/invoke runs any registered name, so at release worker.* must not be registered (review 2 B1)."""
    import os
    import subprocess
    import sys

    code = (
        "import fichero_server.api.main\n"
        "from fichero_server.actions.registry import registry\n"
        "print('REG', [n for n in registry.names() if n.startswith('worker.')])\n"
        "from fichero_server.workflows import worker_process as wp\n"
        "try:\n    wp.start(None, kind='fake', brief='x', workdir='.', timeout_s=5)\nexcept PermissionError as e:\n    print('REFUSED', e)\n"
    )
    env = {**os.environ, "FICHERO_FEATURE_TIER": "release", "FICHERO_BASE_PATH": str(tmp_path), "HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300).stdout
    assert "REG []" in out and "REFUSED" in out, out


def test_at_dev_the_worker_actions_are_app_owner_only():
    from fichero_server.actions.registry import registry

    for n in ("worker.start", "worker.stop", "worker.tell"):
        r = registry.get(n)
        assert r.owner_only and r.owner_scope == "app"
