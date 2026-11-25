"""The launch alert lists an import's held page jobs as one item and Continue lets them all go in one statement (#6830).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.resume.launch-alert-is-one-row-per-queue`.
Driven through `GET /api/activity/stopped-at-quit` and `POST /api/activity/stopped-at-quit/continue` on the real jobs
table, with the page kinds of the "derivatives" queue (thumbnail and embed).
"""
from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs
from fichero_server.importers import derivatives

PAGES = 5000  # a thumbnail row and an embed row each: 10,000 held rows


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    jobs.load_kinds()
    jobs.set_paused(True)  # nothing runs: the rows stay where the test puts them
    pages = [f"page-{i}" for i in range(PAGES)]
    jobs.enqueue_many(db, derivatives.THUMBNAIL_KIND, pages)
    jobs.enqueue_many(db, derivatives.EMBED_KIND, pages)
    jobs.resume(db)  # the open: what the quit left is held
    yield db
    jobs.set_paused(False)


def test_the_alert_lists_the_held_pages_as_one_item(held, client):
    items = client.get("/api/activity/stopped-at-quit").json()["items"]
    assert [i["id"] for i in items] == ["derivatives"]
    assert items[0]["name"] == f"Processing imported pages, {PAGES:,} pages"


def test_continue_lets_every_held_row_go_with_few_statements_and_quickly(held, client, monkeypatch):
    db = held
    statements: list[str] = []
    real = type(db).execute

    def counting(self, sql, *a, **k):
        statements.append(sql)
        return real(self, sql, *a, **k)

    monkeypatch.setattr(type(db), "execute", counting)
    started = time.monotonic()
    r = client.post("/api/activity/stopped-at-quit/continue", json={"ids": ["derivatives"]})
    elapsed = time.monotonic() - started

    assert r.json()["continued_ids"] == ["derivatives"]
    assert elapsed < 1.0, elapsed
    assert len([s for s in statements if s.lstrip().upper().startswith("UPDATE")]) <= 3, statements
    states = {row[0] for row in db.execute_fetchall("SELECT DISTINCT state FROM jobs WHERE kind IN ('thumbnail', 'embed')")}
    assert states == {"waiting"}
    assert client.get("/api/activity/stopped-at-quit").json()["items"] == []


def test_a_page_job_the_person_paused_is_not_let_go_by_continue(held, client):
    db = held
    db.execute("UPDATE jobs SET reason = 'Paused by you' WHERE kind = 'embed' AND subject = 'page-0'")
    client.post("/api/activity/stopped-at-quit/continue", json={"all": True})
    row = db.execute_fetchone("SELECT state FROM jobs WHERE kind = 'embed' AND subject = 'page-0'")
    assert row[0] == "paused"
