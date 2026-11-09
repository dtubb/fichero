"""Polled queries are kept until the library changes (#6446).

`/api/stats` and the Start plan are polled every second or two by every client, a paired Mac included, and cost
2-5 s each on a large library. A poll with nothing changed is a read of a kept result, or a 304.
"""
import asyncio
import logging

from fichero_server.api.change_stream import emit_change, library_generation
from fichero_server.core import change_cache, single_flight
from fichero_server.models import Document, DocType, FileType, Status


def _doc(name: str) -> Document:
    return Document(id=name, name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/x/{name}", status=Status.completed)


def test_an_announced_change_ticks_the_library_generation(db):
    library = str(db.path.parent)
    before = library_generation(library)
    emit_change(library, type="document.updated")
    assert library_generation(library) == before + 1
    assert library_generation(str(db.path.parent) + "-other") == 0


def test_stats_with_nothing_changed_is_answered_from_the_kept_result(client, db):
    db.save(_doc("a"))
    first = client.get("/api/stats")
    assert first.status_code == 200 and first.json()["documents"] == 1
    db.save(_doc("b"))  # a write that announced nothing: the kept result stands until a change or MAX_AGE_S
    assert client.get("/api/stats").json()["documents"] == 1
    emit_change(str(db.path.parent), type="document.created")
    assert client.get("/api/stats").json()["documents"] == 2


def test_stats_answers_304_to_the_current_etag_and_200_after_a_change(client, db):
    first = client.get("/api/stats")
    tag = first.headers["etag"]
    again = client.get("/api/stats", headers={"If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    emit_change(str(db.path.parent), type="document.created")
    after = client.get("/api/stats", headers={"If-None-Match": tag})
    assert after.status_code == 200 and after.headers["etag"] != tag


def test_a_kept_result_is_not_served_past_its_age(db, monkeypatch):
    library = str(db.path.parent)
    change_cache.put(library, "k", library_generation(library), "value")
    assert change_cache.get(library, "k") == "value"
    monkeypatch.setattr(change_cache, "MAX_AGE_S", 0.0)
    assert change_cache.get(library, "k") is None


def test_a_result_computed_across_a_change_is_not_current(db):
    library = str(db.path.parent)
    generation = library_generation(library)
    emit_change(library, type="document.updated")  # lands while the compute runs
    change_cache.put(library, "k2", generation, "stale")
    assert change_cache.get(library, "k2") is None


def test_a_poll_over_a_second_warns_with_the_library(monkeypatch, caplog, db):
    monkeypatch.setattr(single_flight, "WARN_MS", -1)

    @single_flight.single_flight
    async def slow_poll(*, db):
        return []

    with caplog.at_level(logging.WARNING, logger=single_flight.logger.name):
        asyncio.run(slow_poll(db=db))
    assert any("slow poll" in r.message and str(db.path) in r.message for r in caplog.records)


def test_the_start_plan_answers_304_to_its_current_etag_until_the_library_changes(client, db):
    first = client.get("/api/recipes/project/start")
    assert first.status_code == 200, first.text
    tag = first.headers["etag"]
    assert client.get("/api/recipes/project/start", headers={"If-None-Match": tag}).status_code == 304
    assert client.get("/api/recipes/project/start").json() == first.json()  # the kept plan, same answer
    emit_change(str(db.path.parent), type="document.created")
    assert client.get("/api/recipes/project/start", headers={"If-None-Match": tag}).status_code == 200
