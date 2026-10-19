"""The app-DB lock must not hang the request path (`activity.engine.auth-never-hangs`, owner 18:11 respawn).

Lane threads poll `jobs.is_paused` on every claim; auth's device lookup shares the one app-DB lock. The pause flag is
read once and cached; the lookup waits a bounded time and answers 503 in words.
"""
from __future__ import annotations

import json
import threading

import pytest
from starlette.requests import Request

from fichero_server.api import auth
from fichero_server.db.app import AppDatabaseBusy
from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def _fresh_pause_cache():
    jobs._paused_cache.clear()
    yield
    jobs._paused_cache.clear()


def _count_reads(monkeypatch, app_db) -> list[str]:
    reads: list[str] = []
    real = app_db.get_setting
    monkeypatch.setattr(app_db, "get_setting", lambda key, *a, **k: reads.append(key) or real(key, *a, **k))
    return reads


def test_is_paused_reads_the_database_once_and_set_paused_clears_it(app_db, monkeypatch):
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: app_db)
    reads = _count_reads(monkeypatch, app_db)
    assert [jobs.is_paused() for _ in range(5)] == [False] * 5
    assert len(reads) == 1  # five claims, one read
    jobs.set_paused(True)
    assert jobs.is_paused() is True  # the write cleared the cache: the next read sees it
    jobs.set_mode("automatic")
    assert jobs.is_paused() is False
    jobs.set_mode("paused")
    assert jobs.is_paused() is True


def test_a_device_lookup_behind_a_held_lock_gives_up_instead_of_hanging(app_db):
    held, release = threading.Event(), threading.Event()

    def hold():
        with app_db._lock:
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert held.wait(5)
    try:
        with pytest.raises(AppDatabaseBusy):
            app_db.get_device_by_token_hash("x", wait=0.1)
        with pytest.raises(AppDatabaseBusy):
            app_db.get_user("x", wait=0.1)
    finally:
        release.set()
        holder.join(5)
    assert app_db.get_device_by_token_hash("x", wait=0.1) is None  # free again: answers normally


def test_auth_answers_503_in_words_when_the_database_stays_busy(app_db, monkeypatch):
    monkeypatch.setattr(auth, "get_app_db", lambda: app_db)
    monkeypatch.setattr(auth, "AUTH_DB_WAIT_SECONDS", 0.1)
    held, release = threading.Event(), threading.Event()

    def hold():
        with app_db._lock:
            held.set()
            release.wait(10)

    threading.Thread(target=hold, daemon=True).start()
    assert held.wait(5)
    try:
        with pytest.raises(AppDatabaseBusy):
            auth._authenticate_device_token("a-token")
    finally:
        release.set()
    request = Request({"type": "http", "headers": [], "path": "/api/x", "query_string": b""})
    response = auth._busy_response(request, True)
    body = json.loads(response.body)
    assert response.status_code == 503 and body["code"] == "app_db_busy" and "busy" in body["detail"]


def test_a_try_page_in_its_scratch_library_resolves_to_a_person(db):
    """LOW 312: the try's run row is parented on the try's job, which lives in the PROJECT's database, not the scratch
    copy's. The chain ends there; the run's own starter ('workflow', not background) says a person is waiting."""
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, created_at, started_by, parent_id) "
               "VALUES ('thread-try', 'workflow', 'thread-try', 'running', now(), 'workflow', 'try-job-in-the-project-db')")
    db.execute("INSERT INTO jobs (id, kind, subject, state, created_at, started_by, parent_id) "
               "VALUES ('page-1', 'read-a-page', 'p1', 'waiting', now(), 'workflow', 'thread-try')")
    assert jobs.person_waits_on(db, "page-1") is True
    # Control: the same shape under an automatic starter is background.
    db.execute("UPDATE jobs SET started_by = 'automatic' WHERE id = 'thread-try'")
    assert jobs.person_waits_on(db, "page-1") is False
