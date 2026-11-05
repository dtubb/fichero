"""`ai.cloud.one-typed-refusal` (#6349): a run paused at a cap serves the typed refusal beside its words, on the recipe run's
status as `stopped_refusal`, so the app offers the fixes without reading the sentence."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import spend
from fichero_server.recipes import runner

CHECKPOINT = {"steps": [{"card": "x", "state": "done", "ran_on": ["p1"]}], "batches_done": 1, "batch_states": ["done"]}


@pytest.fixture(autouse=True)
def _lane_stays_asleep(monkeypatch):
    monkeypatch.setattr(jobs, "wake_lane", lambda db: None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    spend._STOPPED_AT_CAP.clear()
    yield
    spend._STOPPED_AT_CAP.clear()


def test_the_paused_run_status_carries_the_typed_refusal(db, tmp_path):
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\ncloud_spend_cap_usd: 0\n")
    lib = str(tmp_path / "P.fichero")
    with spend._LOCK:
        over = spend._over_cap(lib, 0.0, 0.1)
    refusal = spend.cap_refusal(lib, 0.1, over)
    runner.register_job_kinds()
    recipe = jobs.enqueue(db, runner.KIND, "cap-event", detail=json.dumps(CHECKPOINT))
    child = jobs.enqueue(db, "workflow", "thread-capped-event")
    jobs.set_parent(db, child, recipe)
    db.execute("UPDATE jobs SET state = 'paused' WHERE id = ?", [child])
    spend._STOPPED_AT_CAP[child] = {**spend._cap_stop(lib, 0.1, over["words"]), "refusal": refusal.model_dump()}
    row = json.loads(jobs.read_job(db, recipe)["detail"])
    row["awaiting"] = {"card": "x", "child": child}
    jobs.save_detail(db, recipe, json.dumps(row), reason="Paused with its run")
    status = runner.status(db, recipe)
    assert status["stopped_at_cap"] is True
    assert status["stopped_refusal"]["kind"] == "cap-monthly"
    assert [f["kind"] for f in status["stopped_refusal"]["fixes"]] == ["raise-to", "over-cap-once", "open-settings"]
