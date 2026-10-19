"""`activity.read.page-read-once`: opening a page's text never starts a read, and never holds the event loop."""
from __future__ import annotations

import asyncio
import time

from fichero_server.api.routes.document import segment_readings
from fichero_server.models import DocType, Document


def test_opening_a_pages_text_starts_no_recognise(db, monkeypatch):
    """A run is reading the page (its own recognise is the only one); the text view derives from what exists."""
    from fichero_server.llm import kraken_runtime

    calls = []

    def recognise(*args, **kwargs):
        calls.append(1)
        raise AssertionError("the text view started a read")

    for name in ("recognize_to_geometry", "recognize_lines", "segment_to_geometry", "_kraken_call"):
        monkeypatch.setattr(kraken_runtime, name, recognise, raising=False)
    page = Document(name="p1", doc_type=DocType.image)
    db.save(page)

    derived = segment_readings.document_text(db, page.id)

    assert calls == []
    assert derived.text == ""  # nothing read yet: the page's stored text stands, nothing is started


def test_the_text_route_derives_off_the_event_loop(monkeypatch):
    def slow(*_a, **_k):
        time.sleep(1.5)  # the library lock behind a lane write
        return "derived"

    monkeypatch.setattr(segment_readings, "document_text", slow)

    async def go() -> float:
        work = asyncio.ensure_future(segment_readings.get_document_text(
            "doc", pass_id=None, order=None, kind="transcription", include_furniture=False, db=object()))
        await asyncio.sleep(0.2)
        started = time.monotonic()
        await asyncio.sleep(0)
        took = time.monotonic() - started
        assert await work == "derived"
        return took

    assert asyncio.run(go()) < 1.0
