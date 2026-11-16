"""Work that needs a missing model is blocked under its blocker, never picked and re-deferred (#6593).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.pane.blocked-under-its-blocker` (and decision 15,
`activity.run.failed-is-never-requeued-by-itself`). With the search model missing the embeds are blocked on ONE download
row; the lane picks none of them; a failed download leaves them blocked and queues no new one by itself; a finished
download unblocks them and they run.
"""
from __future__ import annotations

import time

import pytest

from fichero_server.db import embed_process
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.llm import local_models
from fichero_server.models import Document
from tests.unit.jobs.test_runs_are_jobs import _wait_for


@pytest.fixture
def world(db, monkeypatch):
    """Three pages to embed, a model that is not there, a download that fails until `state['download']` is "ok"."""
    state = {"model_calls": 0, "model_there": False, "download": "fails"}

    def tree(doc, _db, library=None):
        state["model_calls"] += 1
        if not state["model_there"]:
            raise embed_process.EmbedderUnavailable("Search can't index yet: its model isn't downloaded.")
        return None

    def download(subject, db=None):
        if state["download"] == "ok":
            state["model_there"] = True
            return
        raise RuntimeError("offline")

    monkeypatch.setattr(derivatives, "_embed_document_tree", tree)
    monkeypatch.setattr(local_models, "_run_download", download)
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    jobs.load_kinds()
    docs = [Document(name=f"p{i}", page_content=f"words {i}") for i in range(3)]
    for d in docs:
        db.save(d)
    return db, docs, state


def _downloads(db):
    return db.execute_fetchall("SELECT id, state FROM jobs WHERE kind = ?", [local_models.DOWNLOAD_KIND])


def _embed_rows(db):
    return db.execute_fetchall(
        "SELECT id, state, blocked_by, reason FROM jobs WHERE kind = ? ORDER BY created_at", [derivatives.EMBED_KIND])


def test_a_missing_model_blocks_the_embeds_on_one_download_and_the_lane_picks_none(world):
    db, docs, state = world
    for d in docs:
        jobs.enqueue(db, derivatives.EMBED_KIND, d.id)
    assert _wait_for(lambda: len(_embed_rows(db)) == 3 and all(r[2] for r in _embed_rows(db)), 60), _embed_rows(db)
    assert _wait_for(lambda: [s for _, s in _downloads(db)] == ["failed"], 60), _downloads(db)
    (download_id, _), = _downloads(db)
    assert {r[2] for r in _embed_rows(db)} == {download_id}  # all three under the one download
    assert {r[3] for r in _embed_rows(db)} == {"Waiting for the search model"}  # the blocker's words, once, short
    calls = state["model_calls"]
    jobs._scheduler.wake(jobs._key(db))
    time.sleep(1.0)
    assert state["model_calls"] == calls  # the lane never picked a blocked row
    assert all(r[1] == "waiting" for r in _embed_rows(db))
    assert len(_downloads(db)) == 1  # a failed download is not queued again by itself (decision 15)


def test_a_failed_download_keeps_them_blocked_and_a_finished_one_lets_them_run(world):
    db, docs, state = world
    ids = [jobs.enqueue(db, derivatives.EMBED_KIND, d.id) for d in docs]
    assert _wait_for(lambda: all(r[2] for r in _embed_rows(db)) and _downloads(db)
                     and _downloads(db)[0][1] == "failed", 60), (_embed_rows(db), _downloads(db))
    (download_id, _), = _downloads(db)
    state["download"] = "ok"  # the person's Retry on the blocker
    jobs.retry_job(db, download_id)
    assert _wait_for(lambda: all(jobs.read_job(db, i)["state"] == "done" for i in ids), 60), _embed_rows(db)
    assert all(r[2] is None for r in _embed_rows(db))


def test_the_listed_rows_carry_their_blocker_and_say_the_blockers_words_once(world, client):
    db, docs, state = world
    for d in docs:
        jobs.enqueue(db, derivatives.EMBED_KIND, d.id)
    assert _wait_for(lambda: len(_embed_rows(db)) == 3 and all(r[2] for r in _embed_rows(db)), 60), _embed_rows(db)
    (download_id, _), = _downloads(db)
    listed = client.get("/api/activity/jobs").json()["jobs"]
    blocked = [j for j in listed if j["task_type"] == derivatives.EMBED_KIND]
    assert blocked and all(j["blocked_by"] == download_id for j in blocked)
    assert {j["reason"] for j in blocked} == {"Waiting for the search model"}
    assert all(j["blocked_by"] is None for j in listed if j["task_type"] != derivatives.EMBED_KIND)
