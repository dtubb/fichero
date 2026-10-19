"""Embed for search embeds the TEXT, so it runs after reading (`activity.lane.embed-after-reading`, owner screenshot
2026-10-19 16:27): never ahead of a reading page of the library, whatever was queued first, and never on the reading lane."""
from __future__ import annotations

import threading
import time

from fichero_server.execution import jobs

EMBED = "embed-after-reading"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_every_embed_starts_after_the_reading_pages_have_finished(db, monkeypatch):
    events: list[str] = []
    gate = threading.Event()

    def read(_db, subject):
        events.append(f"read-start:{subject}")
        gate.wait(30)
        events.append(f"read-end:{subject}")

    monkeypatch.setitem(jobs.KINDS, "read-a-page", jobs.Kind(run=read, model="kraken:blla", lane="local-ml", name="Read"))
    monkeypatch.setitem(jobs.KINDS, EMBED, jobs.Kind(run=lambda _db, subject: events.append(f"embed:{subject}"),
                                                    model="embedder", lane="embed", name="Embed for search"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": None)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    jobs.enqueue(db, "read-a-page", "p1")  # an import queues the reading page...
    assert _wait_for(lambda: "read-start:p1" in events)
    jobs.enqueue(db, EMBED, "d1")  # ...and the embeds beside it
    jobs.enqueue(db, EMBED, "d2")
    time.sleep(1.5)  # long enough for the embed lane to have looked
    assert not [e for e in events if e.startswith("embed:")]  # nothing embedded while a page is read
    gate.set()
    assert _wait_for(lambda: {"embed:d1", "embed:d2"} <= set(events))
    assert events.index("read-end:p1") < events.index("embed:d1")  # every embed started after the reading finished
