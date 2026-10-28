"""After a kill, every thumbnail claim a dead process left goes back to waiting, and Retry on the kind row reaches them
(`recipes-run.restart.requeues-unfinished`, `recipes-run.restart.retry-reaches-a-kind-row`; #6203)."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

THUMB = "thumbnail"


@pytest.fixture
def thumbs(monkeypatch):
    made: set[str] = set()
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: made.add(subject), model=None, lane="images",
                                                     name="Make thumbnails", first=True))
    monkeypatch.setattr("fichero_server.db.storage.has_thumbnail", lambda doc_id, package_path=None: doc_id in made)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # the rows are the account; no lane thread here
    return made


def _states(db, ids) -> list[str]:
    return [db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [i])[0] for i in ids]


def _five_pages_killed_after_three(db, made) -> list[str]:
    """Five thumbnails queued; three made, then the engine killed with the other two claimed (rows left running)."""
    ids = [jobs._insert(db, THUMB, f"page-{n}", None, "automatic") for n in range(5)]
    for n, job_id in enumerate(ids[:3]):
        made.add(f"page-{n}")
        db.execute("UPDATE jobs SET state = 'done', finished_at = now() WHERE id = ?", [job_id])
    for job_id in ids[3:]:
        db.execute("UPDATE jobs SET state = 'running', attempts = 1, started_at = now() - INTERVAL 600 SECOND "
                   "WHERE id = ?", [job_id])
    return ids


def test_after_a_kill_the_unfinished_thumbnails_wait_to_run_and_the_made_stay_done(db, thumbs):
    jobs._ensure(db)
    ids = _five_pages_killed_after_three(db, thumbs)

    jobs.resume(db)  # the reopen after the restart

    assert _states(db, ids) == ["done"] * 3 + ["waiting"] * 2


def test_retry_on_the_kind_row_requeues_its_set_aside_and_dead_claims(db, thumbs):
    jobs._ensure(db)
    ids = _five_pages_killed_after_three(db, thumbs)
    set_aside = jobs._insert(db, THUMB, "page-5", None, "automatic")
    db.execute("UPDATE jobs SET state = 'failed', attempts = 3, reason = 'Interrupted 3 times' WHERE id = ?", [set_aside])

    assert jobs.retry_job(db, f"waiting:{THUMB}") == "waiting"

    assert _states(db, [*ids, set_aside]) == ["done"] * 3 + ["waiting"] * 3


def test_retry_on_the_kind_row_leaves_a_claim_a_live_thread_runs(db, thumbs, monkeypatch):
    jobs._ensure(db)
    ids = _five_pages_killed_after_three(db, thumbs)
    monkeypatch.setattr(jobs._scheduler, "running_ids", lambda: [ids[3]])

    jobs.retry_job(db, f"waiting:{THUMB}")

    assert _states(db, ids[3:]) == ["running", "waiting"]


def test_retry_on_a_kind_row_through_activity_is_not_a_404(client, db, thumbs):
    jobs._ensure(db)
    ids = _five_pages_killed_after_three(db, thumbs)

    r = client.post(f"/api/activity/jobs/waiting:{THUMB}/retry")

    assert r.status_code == 200, r.text
    assert r.json()["state"] == "waiting"
    assert _states(db, ids[3:]) == ["waiting", "waiting"]
