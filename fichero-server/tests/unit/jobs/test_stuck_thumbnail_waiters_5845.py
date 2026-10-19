"""Pages that wait on a thumbnail job that will never run (#5845, `activity.lane.thumbnails-first`): a thumbnail that
already exists needs no job, and a set-aside job can be stopped from Activity."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.execution import jobs

THUMB = "thumbnail-5845"


@pytest.fixture
def thumbs(monkeypatch):
    """A `first` kind standing for thumbnails; `made` is the set of pages whose thumbnail file exists."""
    made: set[str] = set()
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: None, model=None, lane="images",
                                                     name="Make thumbnails", first=True))
    monkeypatch.setattr("fichero_server.db.storage.has_thumbnail", lambda doc_id, package_path=None: doc_id in made)
    return made


def _state(db, job_id) -> str:
    return db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0]


def test_a_page_whose_thumbnail_exists_has_no_job_left_to_wait_on(db, thumbs):
    jobs._ensure(db)
    queued = jobs._insert(db, THUMB, "page-002", None, "automatic")
    set_aside = jobs._insert(db, THUMB, "page-016", None, "automatic")
    db.execute("UPDATE jobs SET state = 'failed', finished_at = now(), reason = ? WHERE id = ?",
               [jobs.set_aside_reason(3), set_aside])
    missing = jobs._insert(db, THUMB, "page-028", None, "automatic")
    thumbs.update({"page-002", "page-016"})

    assert jobs.settle_made_thumbnails(db) == 2

    assert _state(db, queued) == "done" and _state(db, set_aside) == "done"
    assert _state(db, missing) == "waiting"  # no thumbnail yet: its job stands


def test_opening_the_project_settles_them_so_a_restart_is_all_the_owner_needs(db, thumbs):
    jobs._ensure(db)
    queued = jobs._insert(db, THUMB, "page-002", None, "automatic")
    thumbs.add("page-002")

    jobs.resume(db)

    assert _state(db, queued) == "done"


def test_stopping_a_set_aside_job_works_through_the_route_the_app_calls(client, db):
    jobs._ensure(db)
    job_id = jobs._insert(db, "stuck-5845", "page-016", None, "automatic")
    db.execute("UPDATE jobs SET state = 'failed', finished_at = now(), reason = ? WHERE id = ?",
               [jobs.set_aside_reason(3), job_id])

    response = client.post(f"/api/activity/jobs/{job_id}/cancel")

    assert response.status_code == 200 and response.json()["state"] == "cancelled"
    assert _state(db, job_id) == "cancelled"


def test_stopping_a_waiting_job_works_through_the_route_the_app_calls(client, db):
    jobs._ensure(db)
    job_id = jobs._insert(db, "stuck-5845", "page-028", None, "automatic")

    response = client.post(f"/api/activity/jobs/{job_id}/cancel")

    assert response.status_code == 200 and response.json()["state"] == "cancelled"
