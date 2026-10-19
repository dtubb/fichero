"""The search embedder is a child process (#5847), so an embed no longer takes the model lane: a step followed by an
embed keeps Kraken resident, and the next step does not reload blla and the reader (speed review, 2026-10-19).

Real lanes and real job rows; the Kraken and embed work are faked. `_RELEASE["kraken"]` is what unloads Kraken's models
when the model lane switches to another heavy model, so recording it shows whether anything unloaded Kraken.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.actions import page_text_cache
from fichero_server.execution import jobs
from fichero_server.importers import derivatives

PAGE, EMBED = "kraken-page-speed", "embed-speed"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lanes(monkeypatch):
    events: list[str] = []
    unloaded: list[str] = []
    gate = threading.Event()

    def page(db, subject):
        events.append(f"page:{subject}")
        if subject == "hold":
            gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, PAGE, jobs.Kind(run=page, model="kraken:blla", lane="local-ml", name="Read a page"))
    def embed(db, subject):
        events.append(f"embed:{subject}")
        if subject == "hold":
            gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, EMBED, jobs.Kind(run=embed, model="embedder", lane="embed", name="Embed for search"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": unloaded.append(reason))
    monkeypatch.setitem(jobs._RELEASE, "embedder", lambda reason="": events.append("embedder-released"))
    yield type("Lanes", (), {"events": events, "unloaded": unloaded, "gate": gate})
    gate.set()


def test_a_step_followed_by_an_embed_keeps_kraken_resident_and_the_embed_still_runs(db, lanes):
    jobs.enqueue(db, PAGE, "p1")
    assert _wait_for(lambda: "page:p1" in lanes.events)
    jobs.enqueue(db, EMBED, "d1")
    assert _wait_for(lambda: "embed:d1" in lanes.events)  # the embed ran
    jobs.enqueue(db, PAGE, "p2")  # the next step's page
    assert _wait_for(lambda: "page:p2" in lanes.events)
    assert lanes.unloaded == []  # nothing unloaded Kraken between them
    assert jobs._scheduler.lanes["local-ml"].loaded_model == "kraken:blla"


def test_an_embed_runs_beside_a_kraken_page_instead_of_waiting_for_the_model_lane(db, lanes):
    jobs.enqueue(db, PAGE, "hold")
    assert _wait_for(lambda: "page:hold" in lanes.events)
    jobs.enqueue(db, EMBED, "d1")
    assert _wait_for(lambda: "embed:d1" in lanes.events)  # while the page still holds the model lane
    assert lanes.unloaded == []


def test_the_real_embed_kinds_are_on_the_embed_lane_and_stay_background():
    derivatives.register_job_kinds()
    page_text_cache._register()
    from fichero_server.core.background_compute import set_background_qos

    for kind in (derivatives.EMBED_KIND, page_text_cache.REEMBED_KIND):
        assert jobs.KINDS[kind].lane == "embed" and jobs.KINDS[kind].model == "embedder"
        assert jobs.KINDS[kind].qos is set_background_qos  # background class
    assert "embed" in jobs.THROTTLED_LANES and "embed" not in jobs.HEAVY_LANES  # held by battery/memory/heat, but never one-heavy-at-a-time


# --- 3c: a page held for memory goes on as soon as the throttle's decision lets it ---------------------------------------


def _memory_short_once(monkeypatch, decisions):
    """A handed-in page that finds memory short the first time; `decisions` are what `decide` answers, in turn."""
    from fichero_server.execution import throttle

    asked = iter(decisions)
    last = [throttle.Decision("go", None, "fast")]

    def decide(*_a, **_k):
        last[0] = next(asked, last[0])
        return last[0]

    monkeypatch.setattr(throttle, "decide", decide)
    attempts = []

    def fn():
        attempts.append(time.monotonic())
        if len(attempts) == 1:
            raise throttle.MemoryShortError("Waiting: memory is tight")
        return "read"

    return fn, attempts


def test_a_resident_models_page_does_not_pay_the_five_second_look_again(db, lanes, monkeypatch):
    from fichero_server.execution import throttle

    assert jobs.THROTTLE_LOOK_AGAIN_SECONDS >= 5.0
    fn, attempts = _memory_short_once(monkeypatch, [throttle.Decision("go", None, "fast")])
    started = time.monotonic()
    assert jobs.submit(db, PAGE, "p", model="kraken:blla", fn=fn).result(timeout=30) == "read"
    assert len(attempts) == 2 and attempts[1] - started < 2.0  # asked again at once: no 5 s


def test_a_page_really_held_for_memory_goes_the_moment_it_fits(db, lanes, monkeypatch):
    from fichero_server.execution import throttle

    hold, go = throttle.Decision("hold", "Waiting: memory is tight", "background"), throttle.Decision("go", None, "fast")
    fn, attempts = _memory_short_once(monkeypatch, [hold, hold, hold, go])
    started = time.monotonic()
    assert jobs.submit(db, PAGE, "p", model="kraken:blla", fn=fn).result(timeout=30) == "read"
    assert 0.4 < attempts[1] - started < 3.0  # it waited while memory was short, then went: not a fixed 5 s


def test_under_warn_pressure_a_kraken_page_runs_while_an_embed_runs(db, lanes, monkeypatch):
    """Review 280: "embed" in HEAVY_LANES made Kraken wait "one heavy at a time: Embed for search is running"."""
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "memory_is_busy", lambda: True)  # memory pressure at warn
    jobs.enqueue(db, EMBED, "hold")
    assert _wait_for(lambda: "embed:hold" in lanes.events)
    jobs.enqueue(db, PAGE, "p1")
    assert _wait_for(lambda: "page:p1" in lanes.events, 10)  # the embed still runs; Kraken does not wait for it
    assert lanes.unloaded == []
