"""`activity.run.stages-before-search-do-not-embed` (#6126): while a recipe run is going and its Search stage is still ahead,
a page its earlier stages save is not queued for its own embed; Search embeds it once. Otherwise the immediate embed stays.
WHY: inside one run a page was embedded after Read, again after Correct, and only the last counted."""
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.importers.derivatives import EMBED_KIND, queue_embedding
from fichero_server.recipes import runner


def _run(db, search_state):
    cards = [{"steps": ["read"], "card": "workflow", "job": "read-a-line"},
             {"steps": ["search"], "card": "embed", "job": "make-a-vector"}]
    job_id = runner.enqueue(db, {"runs": cards, "skipped": []}, documents=None, started_by="owner")
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    detail["steps"] = [{"steps": ["read"], "card": "workflow", "state": "running", "child_id": None},
                       {"steps": ["search"], "card": "embed", "state": search_state, "child_id": None}]
    jobs.save_detail(db, job_id, json.dumps(detail))
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [job_id])
    return job_id


def _embeds(db):
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [EMBED_KIND])[0]


def test_no_embed_is_queued_while_search_is_ahead_in_a_running_run(db):
    _run(db, "waiting")
    queue_embedding("doc-1", library_path=str(db.path), db=db)
    assert runner.search_is_ahead(db) and _embeds(db) == 0


def test_embed_is_queued_with_no_run_or_once_search_is_done(db):
    queue_embedding("doc-1", library_path=str(db.path), db=db)
    assert not runner.search_is_ahead(db) and _embeds(db) == 1
    _run(db, "done")
    queue_embedding("doc-2", library_path=str(db.path), db=db)
    assert not runner.search_is_ahead(db) and _embeds(db) == 2
