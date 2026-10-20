"""#5806: Set Up's stage tries. A try waits behind nothing it does not need, says what it waits for with progress, and a
refusal of one stage's try is about that stage's own steps.

WHY: the owner testing the staged build (2026-10-19): Find Lines "Compare on these pages" sat behind the Read try's
5.7 GB download (both tries ran on the one-wide recipes lane, the Read try holding it while it waited); a waiting try
said nothing; Prepare Images' try was refused 422 with nothing on screen.
"""
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.recipes import samples
from tests.unit.recipes.test_stage_try_words_5687 import _pages, _set_up  # noqa: F401


def test_a_stage_try_has_a_lane_of_its_own_wide_enough_for_two():
    """A try waiting on a download holds its lane; the next stage's try must not queue behind it."""
    samples.register_job_kinds()
    lane = jobs.KINDS[samples.TRY_KIND].lane
    assert lane != "recipes" and jobs.LANES[lane] >= 2


def test_a_try_waiting_on_a_download_says_what_for_with_its_progress(db, monkeypatch):
    try_id = jobs.enqueue(db, samples.TRY_KIND, "read:aaaaaaaa", started_by="test", watched=True,
                          detail=json.dumps({"stage": "read", "pages": []}))
    download = jobs.enqueue(db, "download-model", "omlx:qwen2.5-vl-7b", started_by="test")
    # The try is the job whose body is running (`current_job_id`), so it is marked running: left queued, a lane a
    # earlier test registered the kind on would run its real body here and overwrite the reason with its own error.
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [try_id])
    db.execute("UPDATE jobs SET state = 'running', reason = ? WHERE id = ?",
               ["Downloading Qwen2.5-VL 7B: 1.2 GB of 5.6 GB", download])
    monkeypatch.setattr(jobs, "current_job_id", lambda: try_id)
    seen = []

    def sleep(_):
        seen.append(jobs.read_job(db, try_id)["reason"])
        db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [download])

    monkeypatch.setattr(samples.time, "sleep", sleep)
    plan = {"downloads": [{"name": "Qwen2.5-VL 7B", "model": "qwen2.5-vl-7b", "job_id": download}]}
    assert samples._await_downloads(db, plan) is None
    assert seen and "Waiting for Qwen2.5-VL 7B" in seen[0] and "1.2 GB of 5.6 GB" in seen[0], seen


def test_a_prepare_images_try_is_not_refused_for_another_steps_problem(client, db, tmp_path):
    """The stage's plan checks only its own steps: a Read step with a pin nothing can run (#5800) is the Read try's
    refusal, not Prepare Images'."""
    _pages(db, tmp_path)
    _set_up(client, ["prepare-the-image"])
    saved = client.get("/api/recipes/project").json()
    for step in saved["recipe"]["steps"]:
        if step["job"] == "read-a-line":
            step["model"] = {"hf": "nobody/not-a-model-5800", "revision": "main"}  # a Zenodo DOI is always a reader Fichero can fetch
    assert client.put("/api/recipes/project", json={"answers": saved["answers"], "recipe": saved["recipe"]}
                      ).status_code == 200
    r = client.post("/api/recipes/stages/prepare-images/try", json={})
    assert r.status_code == 200, r.text
