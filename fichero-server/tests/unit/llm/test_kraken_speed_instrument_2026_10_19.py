"""The speed review (2026-10-19): which priority a page landed on and what each stage took, one log line per page; a
resident page checks its small working need, not the 2.5 GB cold-load figure; the reader batch floors at 8 unless memory
is really short."""
from __future__ import annotations

import logging
import re
import sys
import time
import types

import pytest

from fichero_server.core import background_compute
from fichero_server.llm import kraken_runtime as kr

GIB = 1024**3


@pytest.fixture(autouse=True)
def _resident_state(monkeypatch):
    saved = dict(kr._RESIDENT)
    kr._RESIDENT.clear()
    monkeypatch.setattr(kr, "require_installed", lambda: None)
    monkeypatch.setattr(kr, "assert_memory_available_for_kraken", lambda: None)
    monkeypatch.setattr(kr, "_release_when_idle", lambda: None)
    yield
    kr._RESIDENT.clear()
    kr._RESIDENT.update(saved)


def _hold(segment=True, read="reader-a"):
    """Hold the line finder and/or a reader in memory, as `_resident` would."""
    kr._RESIDENT.clear()
    if segment:
        kr._RESIDENT["segment"] = ("blla", object())
    if read:
        kr._RESIDENT["read"] = (read, object())


def _fake_torch(monkeypatch):
    seen = {}
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(
        set_num_threads=lambda n: seen.__setitem__("threads", n), set_num_interop_threads=lambda n: None))
    return seen


def _decide(monkeypatch):
    """The throttle's answer without the real Mac's battery, build and input state."""
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "decide", lambda person_waiting=False, **_: throttle.Decision(
        "go", None, "fast" if person_waiting else "balanced"))


def _run_as(monkeypatch, person: bool):
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "current_job_is_a_persons", lambda: person)
    monkeypatch.setattr(kr, "pages_at_once", lambda person: 1)  # one page: every core (two pages at once: its own test)
    kr._kraken_call(lambda: None)


def test_a_persons_start_lands_on_fast_with_every_core(monkeypatch, caplog):
    seen = _fake_torch(monkeypatch)
    _decide(monkeypatch)
    with caplog.at_level(logging.INFO, logger=kr.logger.name):
        _run_as(monkeypatch, True)
    assert seen["threads"] == background_compute.cpu_count()
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("kraken page"))
    assert "priority=fast" in line and "qos=user-initiated" in line and "person=yes" in line
    assert f"threads={background_compute.cpu_count()}" in line and "throttle=go" in line


def test_an_automatic_run_lands_on_balanced(monkeypatch, caplog):
    seen = _fake_torch(monkeypatch)
    _decide(monkeypatch)
    with caplog.at_level(logging.INFO, logger=kr.logger.name):
        _run_as(monkeypatch, False)
    assert seen["threads"] == max(1, background_compute.embed_threads())
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("kraken page"))
    assert "priority=balanced" in line and "qos=utility" in line and "person=no" in line


def test_a_page_logs_one_line_with_every_stage_and_a_total_that_adds_up(monkeypatch, caplog):
    _fake_torch(monkeypatch)
    _decide(monkeypatch)

    def op():
        kr._page_is("/library/IMG_017.png")
        for stage, seconds in (("load", 0.1), ("segment", 0.2), ("recognise", 0.3)):
            with kr._stage(stage):
                time.sleep(seconds)

    with caplog.at_level(logging.INFO, logger=kr.logger.name):
        kr._kraken_call(op)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("kraken page")]
    assert len(lines) == 1
    m = re.match(r"kraken page IMG_017\.png: load ([\d.]+)s segment ([\d.]+)s recognise ([\d.]+)s total ([\d.]+)s", lines[0])
    assert m, lines[0]
    load, segment, recognise, total = map(float, m.groups())
    assert (load, segment, recognise) == pytest.approx((0.1, 0.2, 0.3), abs=0.1)
    assert total == pytest.approx(load + segment + recognise, abs=0.2)


def test_a_resident_page_checks_its_small_working_need():
    available, normal = lambda: 3 * GIB, lambda: 1  # noqa: E731
    _hold()
    token = kr._WANTED.set({"segment": "blla", "read": "reader-a"})
    assert kr.kraken_models_resident() and kr.kraken_need_bytes() < GIB
    from fichero_server.execution.throttle import memory_short

    assert memory_short(available_bytes=lambda: 1 * GIB, pressure_level=normal, need_bytes=kr.kraken_need_bytes()) is None
    kr._RESIDENT.clear()
    kr._WANTED.reset(token)
    assert kr.kraken_need_bytes() == kr._kraken_memory_need_bytes()
    assert memory_short(available_bytes=lambda: 1 * GIB, pressure_level=normal,
                        need_bytes=kr.kraken_need_bytes()) is not None


def test_the_guard_lets_a_resident_page_run_on_3_gb_but_refuses_a_cold_one_on_2(monkeypatch):
    monkeypatch.undo()  # the fixture's stub of the guard; this test wants the real one
    _hold()
    kr.assert_memory_available_for_kraken(available_bytes=lambda: 1 * GIB, pressure_level=lambda: 1)  # no raise
    kr._RESIDENT.clear()
    with pytest.raises(kr.KrakenMemoryUnavailableError):
        kr.assert_memory_available_for_kraken(available_bytes=lambda: 2 * GIB, pressure_level=lambda: 1)


def test_the_shared_floor_stays_cold_even_while_kraken_holds_its_models():
    """Review 279 MED 1: the scheduler, training and derivatives ask this; Kraken's resident memory is still in use."""
    from fichero_server.execution.throttle import heavy_work_need_bytes, model_need

    _hold()
    assert heavy_work_need_bytes() == kr._kraken_memory_need_bytes()
    assert "need_bytes" not in model_need("kraken:reader-a")  # not loaded: the cold floor
    assert model_need("kraken:reader-a", loaded=True)["need_bytes"] == kr.kraken_need_bytes() < kr._kraken_memory_need_bytes()


def test_one_kind_or_another_reader_is_still_a_cold_load():
    """Review 279 MED 2: a held line finder with no reader (or another reader) still loads one."""
    cold = kr._kraken_memory_need_bytes()
    _hold(read=None)
    assert kr.kraken_need_bytes() == cold
    _hold(segment=False)
    assert kr.kraken_need_bytes() == cold
    _hold(read="reader-a")
    token = kr._WANTED.set({"segment": "blla", "read": "reader-b"})  # this page asks for another reader
    assert kr.kraken_need_bytes() == cold
    kr._WANTED.reset(token)
    token = kr._WANTED.set({"segment": "blla"})  # a page that only finds lines needs only the finder
    _hold(read=None)
    assert kr.kraken_need_bytes() < cold
    kr._WANTED.reset(token)


def test_a_call_carries_its_models_into_the_inference_thread(monkeypatch):
    _fake_torch(monkeypatch)
    _decide(monkeypatch)
    seen = {}
    token = kr._WANTED.set({"segment": "blla", "read": "reader-b"})
    kr._kraken_call(lambda: seen.update(wanted=kr._WANTED.get()))
    kr._WANTED.reset(token)
    assert seen["wanted"] == {"segment": "blla", "read": "reader-b"}


