"""Start while the models download (#5660 item 6, from the maintainer's Set Up test of 2026.10.10).

The needed models (a Kraken reader, Qwen2.5-VL) begin downloading by themselves, yet the plan still said "not on
this Mac: download it first" and Start stayed refused. A model already downloading no longer refuses Start: the
plan says it is downloading (with its progress), and the run's steps on it wait for it to land. A model that is
neither here nor downloading still refuses.
"""

from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.llm.local_models import DOWNLOAD_KIND
from fichero_server.recipes import runner
from tests.unit.recipes.test_kraken_reader_offered_before_start import LINES, READ, READER
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _save

PROGRESS = "Downloading the Kraken reader kraken-zenodo-21788410: 12 MB of 40 MB"


def _downloading(db) -> str:
    job_id = jobs.enqueue(db, DOWNLOAD_KIND, f"kraken:{READER}", started_by="automatic")
    jobs.save_detail(db, job_id, json.dumps({"progress": PROGRESS}), reason=PROGRESS)
    return job_id


def _end(db, job_id: str, state: str, reason: str | None = None) -> None:
    db.execute("UPDATE jobs SET state = ?, reason = ? WHERE id = ?", [state, reason, job_id])


def _plan(client, tmp_path, monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: False)
    _save(client, _recipe(tmp_path, LINES, READ))
    return client.get("/api/recipes/project/start").json()


def test_a_model_downloading_does_not_refuse_start_and_says_it_is_downloading(
        jobs_run_by_the_test, client, db, tmp_path, monkeypatch):
    download_job = _downloading(db)

    plan = _plan(client, tmp_path, monkeypatch)

    (offer,) = plan["downloads"]
    assert (offer["downloading"], offer["job_id"], offer["progress"]) == (True, download_job, PROGRESS)
    assert not any(READER in r for r in plan["refusals"]), plan["refusals"]
    assert not any("download it first" in w for w in plan["waiting"])
    (said,) = plan["waiting"]
    assert "which is downloading" in said and PROGRESS in said and "they run when it lands" in said, said

    started = client.post("/api/recipes/project/start")
    assert started.status_code == 200, started.text
    run_id = started.json()["started"]["job_id"]
    detail = json.loads(jobs.read_job(db, run_id)["detail"])
    assert detail["awaited"] == [{"steps": offer["steps"], "job_id": download_job, "name": READER}]


def test_a_model_neither_here_nor_downloading_still_refuses_start(
        jobs_run_by_the_test, client, db, tmp_path, monkeypatch):
    finished = _downloading(db)
    _end(db, finished, "failed", "the network went away")  # an ended download is not under way

    plan = _plan(client, tmp_path, monkeypatch)

    assert plan["downloads"][0]["downloading"] is False
    assert any(READER in r and "download it first" in r for r in plan["refusals"]), plan["refusals"]
    assert plan["waiting"] == []
    assert client.post("/api/recipes/project/start").status_code == 422


def test_a_step_waits_for_its_download_then_runs_or_says_why_not(jobs_run_by_the_test, db, monkeypatch):
    monkeypatch.setattr(runner, "_CHECK_POLL_SECONDS", 0.01)
    card = {"steps": ["lines", "read"], "card": "workflow"}
    other = {"steps": ["export"], "card": "export"}

    landed = _downloading(db)
    _end(db, landed, "done")
    detail = {"awaited": [{"steps": ["lines", "read"], "job_id": landed, "name": READER}]}
    assert runner._await_downloads(db, "recipe-run", detail, card) is None
    assert detail["awaited"][0]["landed"] is True
    # A step that needs no awaited download never waits.
    assert runner._await_downloads(db, "recipe-run", {"awaited": [{"steps": ["read"], "job_id": "none",
                                                                   "name": READER}]}, other) is None

    failed = _downloading(db)
    _end(db, failed, "failed", "the network went away")
    detail = {"awaited": [{"steps": ["read"], "job_id": failed, "name": READER}]}
    why = runner._await_downloads(db, "recipe-run", detail, card)
    assert why == f"its model {READER} did not download: the network went away"
