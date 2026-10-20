"""`activity.read.page-read-once`: opening a page's text never starts a read, and never holds the event loop."""
from __future__ import annotations

import asyncio
import threading
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
    page = Document(name="p1", doc_type=DocType.page)
    db.save(page)

    derived = segment_readings.document_text(db, page.id)

    assert calls == []
    assert derived.text == ""  # nothing read yet: the page's stored text stands, nothing is started


def _ask(**overrides):
    kwargs = dict(pass_id=None, order=None, kind="transcription", include_furniture=False, db=_Db())
    kwargs.update(overrides)
    return segment_readings.get_document_text(**kwargs)


class _Db:
    """Stands in for a library database (the route only passes it on)."""
    path = "/lib/x.duckdb"
    execute = None


def test_the_text_route_derives_off_the_event_loop(monkeypatch):
    """The loop's longest stall while the route runs (a ticker beside it), not a timing taken after the block: the old
    `async def` that derived on the loop stalls it for the whole 1.5 s."""
    monkeypatch.setattr(segment_readings, "document_text", lambda *_a, **_k: (time.sleep(1.5), "derived")[1])
    gaps: list[float] = []

    async def go():
        async def ticker():
            last = time.monotonic()
            while True:
                await asyncio.sleep(0.02)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        tick = asyncio.ensure_future(ticker())
        await asyncio.sleep(0.1)
        result = await _ask(document_id="doc")
        tick.cancel()
        return result

    assert asyncio.run(go()) == "derived"
    assert max(gaps) < 0.5, f"the event loop stalled {max(gaps):.2f} s while the text was derived"


def test_three_gets_for_one_page_derive_it_once(monkeypatch):
    calls = []

    def derive(*_a, **_k):
        calls.append(1)
        time.sleep(0.3)
        return "derived"

    monkeypatch.setattr(segment_readings, "document_text", derive)

    async def go():
        db = _Db()
        return await asyncio.gather(*(_ask(document_id="doc", db=db) for _ in range(3)))

    assert asyncio.run(go()) == ["derived"] * 3
    assert len(calls) == 1


def test_derivations_of_different_pages_never_overlap(monkeypatch):
    running, most = [0], [0]
    guard = threading.Lock()

    def derive(*_a, **_k):
        with guard:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.15)
        with guard:
            running[0] -= 1
        return "derived"

    monkeypatch.setattr(segment_readings, "document_text", derive)

    async def go():
        db = _Db()
        return await asyncio.gather(*(_ask(document_id=f"doc-{n}", db=db) for n in range(3)))

    asyncio.run(go())
    assert most[0] == 1, "two text derivations ran at once beside a read"


def test_gets_waiting_their_turn_leave_the_executor_free_for_auth(monkeypatch):
    """Review 352: the one-at-a-time lock sat INSIDE the worker thread, so every waiting GET held a thread of the default
    executor and auth's device lookup queued behind them. Four GETs on a two-thread executor must leave one free."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(segment_readings, "document_text", lambda *_a, **_k: (time.sleep(0.6), "derived")[1])

    async def go() -> float:
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=2))
        db = _Db()
        gets = [asyncio.ensure_future(_ask(document_id=f"doc-{n}", db=db)) for n in range(4)]
        await asyncio.sleep(0.1)  # all four are in; one derives, three wait their turn
        started = time.monotonic()
        await asyncio.get_running_loop().run_in_executor(None, lambda: None)  # what auth does
        waited = time.monotonic() - started
        await asyncio.gather(*gets)
        return waited

    assert asyncio.run(go()) < 0.3, "a waiting GET held an executor thread"
