"""`recipes-run.order.search-entities-once-at-the-end` (#6186, ruling 5): an import into a project whose recipe runs on what
it brings queues NO per-page embed and NO names draft when that run has a Search stage and a names stage; the run does both
once, after reading. Thumbnails still queue. A project whose run lacks Search keeps today's import-time embed, and a page
the run's Search embeds stops being pending (else every open would queue its embed again).
WHY: dogfood B12, "Embed for search 0/95" queued at import beside every step, competing with the readers."""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.importers.derivatives import EMBED_KIND, NLP_KIND, THUMBNAIL_KIND
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.recipes import runner

SEARCH = {"steps": ["search"], "card": "embed", "job": "make-a-vector"}
NAMES = {"steps": ["names"], "card": "workflow", "job": "find-names-tag-words"}
READ = {"steps": ["read"], "card": "workflow", "job": "read-a-line"}


def _count(db, kind):
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [kind])[0]


@pytest.fixture
def pages(db):
    docs = [Document(name=f"p{i}.jpg", doc_type=DocType.file, file_type=FileType.image, status=Status.pending,
                     page_content="text") for i in range(6)]
    for d in docs:
        db.save(d)
    return docs


def _run_queued(monkeypatch, db, cards, state="queued"):
    jobs._ensure(db)
    run_id = jobs._insert(db, runner.KIND, "import-run", None, "import")
    db.execute("UPDATE jobs SET state = ?, detail = ? WHERE id = ?", [state, json.dumps({"runs": cards}), run_id])
    monkeypatch.setattr(runner, "material_arrived", lambda _db, _ids: run_id)
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: True)


def test_a_run_with_search_and_names_takes_the_embed_and_the_names_draft(db, pages, monkeypatch):
    _run_queued(monkeypatch, db, [READ, NAMES, SEARCH])
    derivatives.queue_derivatives(pages, library_path=str(db.path), db=db)
    assert (_count(db, EMBED_KIND), _count(db, NLP_KIND)) == (0, 0)
    assert _count(db, THUMBNAIL_KIND) == 6


def test_a_run_without_search_keeps_the_import_embed(db, pages, monkeypatch):
    _run_queued(monkeypatch, db, [READ, NAMES])
    derivatives.queue_derivatives(pages, library_path=str(db.path), db=db)
    assert (_count(db, EMBED_KIND), _count(db, NLP_KIND)) == (6, 0)


def test_a_refused_run_keeps_todays_import(db, pages, monkeypatch):
    _run_queued(monkeypatch, db, [READ, NAMES, SEARCH], state="failed")
    derivatives.queue_derivatives(pages, library_path=str(db.path), db=db)
    assert (_count(db, EMBED_KIND), _count(db, NLP_KIND)) == (6, 6)


def test_searchs_embed_clears_a_pages_pending(db, pages, monkeypatch):
    from fichero_server.actions import page_text_cache

    monkeypatch.setattr(type(db), "embed_many_unless_current", lambda self, docs: (0, len(docs), len(docs)))
    [batch] = page_text_cache.queue_reembed_batches(db, [d.id for d in pages], started_by="owner")
    page_text_cache._reembed(db, jobs.read_job(db, batch)["subject"])
    assert {db.get(Document, d.id).status for d in pages} == {Status.completed}


def test_what_runs_by_itself_says_search_and_names_run_once_at_the_end(db, monkeypatch):
    monkeypatch.setattr(runner, "_why_no_recipe_on_add", lambda _db: None)
    monkeypatch.setattr(runner, "_plan", lambda _db: {"refusals": [], "runs": [READ, NAMES, SEARCH], "skipped": []})
    monkeypatch.setattr("fichero_server.importers.nlp_draft.auto_nlp_enabled", lambda: True)
    on_add = {e["job"]: e for e in runner.what_runs_by_itself(db)["on_add"] if e["job"]}
    for kind in (EMBED_KIND, NLP_KIND):
        assert on_add[kind]["runs"] is False and "once at the end" in on_add[kind]["why"]
    assert on_add[THUMBNAIL_KIND]["runs"] is True
