"""A names page that takes too long is skipped and named, never spun on in silence (#6236).

WHY: on the M4 106-page run, Extract Entities did pages 1-86 in 1-4 s each, then held one core at 100% for 20+ min
on page 87, logging nothing. Each page now has a time limit: past it the page is left out with a worded stall, the
step goes on to the next page, and the page is not noted done, so Run again on what was missed offers it.
"""
# ruff: noqa: F811  (the imported `library` fixture is used by name)
from __future__ import annotations

from types import SimpleNamespace

import asyncio
import time

from tests.unit.workflows.test_entities_read_the_working_pass import (  # noqa: F401
    _page,
    _run,
    extract_all_module,
    library,
    module,
)


def _noted(monkeypatch) -> list[str]:
    noted: list[str] = []
    monkeypatch.setattr("fichero_server.recipes.done.page_finished", lambda db, run, key: noted.append(key))
    return noted


def test_a_model_page_past_the_limit_is_skipped_with_a_worded_stall_6236(library, tmp_path, monkeypatch):
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "0074.jpg", imported=True)
    _page(db, folder, tmp_path, "0075.jpg", imported=True)
    calls = []

    async def model(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            await asyncio.sleep(30)  # the page that never answers
        return extract_all_module._EntitiesOnly(people=[{"name": "Anna Maria"}], places=[], organizations=[],
                                                dates=[], events=[])

    monkeypatch.setattr(module, "chat_structured_with_fallback", model)
    monkeypatch.setattr(module, "NAMES_PAGE_SECONDS", 0.3)
    noted = _noted(monkeypatch)

    started = time.monotonic()
    result = _run(path, folder.id)

    assert time.monotonic() - started < 10
    assert not result.get("error") and result["summary"]["documents_processed"] == 1
    (stalled,) = [e for e in result["summary"]["left_out"] if "took over" in e["why"]]
    assert stalled["why"].startswith(f"names on page {stalled['name']} took over 0.3 s; skipped")
    assert stalled["document_id"] not in noted and len(noted) == 1


def test_a_spacy_page_past_the_limit_is_skipped_and_a_run_of_only_stalls_fails_6236(library, tmp_path, monkeypatch):
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "0074.jpg", imported=True)

    class Spins:
        async def extract(self, text, *, language=None):
            await asyncio.to_thread(time.sleep, 2)  # spaCy holding a worker thread
            return []

    monkeypatch.setattr(module, "_is_local_ner_provider", lambda provider: True)
    monkeypatch.setattr("fichero_server.workflows.ner.providers.get_ner_provider", lambda *a: Spins())
    monkeypatch.setattr(module, "NAMES_PAGE_SECONDS", 0.3)
    noted = _noted(monkeypatch)

    result = _run(path, folder.id)

    assert "took over 0.3 s" in result["error"] and result["summary"]["documents_processed"] == 0
    assert not noted


def test_writing_a_pages_names_past_the_limit_stops_and_the_next_page_goes_on_6236(library, tmp_path, monkeypatch):
    """The M4 spin was the names' writing (upsert_entity against a grown table), after the timed model call. The page's
    time limit covers the writing too, and the writing really stops: no name of the page is written past it, so no core
    or DB writer is held for it, and the next page is read and noted."""
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "0074.jpg", imported=True)
    _page(db, folder, tmp_path, "0075.jpg", imported=True)
    names = [{"name": f"Name {i}"} for i in range(50)]

    async def model(**kwargs):
        return extract_all_module._EntitiesOnly(people=names, places=[], organizations=[], dates=[], events=[])

    written: list[str] = []  # the page each name was written for
    real_upsert = module.upsert_entity
    clock = [0.0]  # the step's clock: only the first page's writing moves it, so a slow machine can't stall page two

    def slow_upsert(db, *, canonical_name, **kwargs):
        written.append(kwargs["source_document_id"])
        if written[0] == written[-1]:
            clock[0] += 1.0  # the first page's names, each a second to write
        return real_upsert(db, canonical_name=canonical_name, **kwargs)

    monkeypatch.setattr(module, "chat_structured_with_fallback", model)
    monkeypatch.setattr(module, "upsert_entity", slow_upsert)
    monkeypatch.setattr("fichero_server.db.Database.schedule_entity_embedding", lambda self, entity: None)  # fast writes
    monkeypatch.setattr(module, "NAMES_PAGE_SECONDS", 30)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    noted = _noted(monkeypatch)

    result = _run(path, folder.id)

    (stalled,) = [e for e in result["summary"]["left_out"] if "took over" in e["why"]]
    assert "writing its names did not finish" in stalled["why"]
    assert written.count(stalled["document_id"]) < 50, "the stalled page's writing went on past its limit"
    assert result["summary"]["documents_processed"] == 1 and len(noted) == 1 and stalled["document_id"] not in noted
