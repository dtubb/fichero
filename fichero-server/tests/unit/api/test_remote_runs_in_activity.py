"""A remote run in Activity (`activity.remote-under-its-step`, #5740): the row says where, how far and what it offers;
the Inspector reads the run's status; Catch up is an action."""
from __future__ import annotations

import json

from fichero_server.execution import jobs


def _run(db, *, parent=None, shards=None, state="running"):
    detail = {"request": {"target": "rorqual"}, "landing": {"landed": 4},
              "shards": shards or {"0": {"state": "landed", "seconds": 12.0}, "1": {"state": "submitted", "far_id": "9_1"}},
              "estimate": {"pages": 100, "shards": 2, "gpu_hours": 0.5}}
    job_id = jobs.enqueue_remote(db, "read-at-scale", f"read:{id(detail)}", target="rorqual", detail=json.dumps(detail),
                                 reason="Reading on the cluster", started_by="owner")
    db.execute("UPDATE jobs SET state = ? WHERE id = ?", [state, job_id])
    if parent:
        jobs.set_parent(db, job_id, parent)
    return job_id


def test_the_activity_row_carries_the_remote_summary_under_its_step(client, db):
    step = jobs.enqueue_remote(db, "recipe", "step-1", target="this-mac", detail="{}", reason="r", started_by="owner")
    job_id = _run(db, parent=step)
    rows = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}
    row = rows[job_id]
    assert row["parent_id"] == step
    assert row["remote"] == {"target": "rorqual", "far_state": "running", "shards": "1 of 2 shards", "pages_landed": 4,
                             "offers": ["Cancel", "Catch up"]}


def test_the_inspector_status_has_shards_and_estimate_and_catch_up_is_an_action(client, db):
    job_id = _run(db)
    body = client.get(f"/api/reading-at-scale/jobs/{job_id}").json()
    assert body["far_state"] == "running" and [s["state"] for s in body["shards"]] == ["landed", "submitted"]
    assert body["estimate"]["gpu_hours"] == 0.5 and body["actual"]["seconds_per_shard"] == 12.0
    r = client.post(f"/api/reading-at-scale/jobs/{job_id}/catch-up")
    assert r.status_code == 200 and r.json()["state"] == "running"
    assert json.loads(db.execute_fetchone("SELECT detail FROM jobs WHERE id = ?", [job_id])[0])["catch_up"] is True
    assert client.post("/api/reading-at-scale/jobs/nope/catch-up").status_code == 404


def test_catching_up_a_finished_run_is_refused_with_409(client, db):
    job_id = _run(db, state="completed")
    assert client.post(f"/api/reading-at-scale/jobs/{job_id}/catch-up").status_code == 409
