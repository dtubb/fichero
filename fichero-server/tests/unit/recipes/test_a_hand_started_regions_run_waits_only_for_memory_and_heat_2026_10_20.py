"""Fable runner review #4 (manager ruling 2026-10-19): a run a person started by hand waits ONLY for memory and heat,
never for battery or for the person being at the Mac; a background run is held by all of them. A Set Up try on a
scratch copy has no row of the run in that copy, so its caller says a person watches
(`activity.throttle.hand-started-waits-for-memory-and-heat`)."""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.execution import jobs, throttle
from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import regions


@pytest.fixture
def pages(db, tmp_path, monkeypatch):
    docs = []
    for i in range(2):
        path = tmp_path / f"p{i}.png"
        Image.new("RGB", (40, 60), (250, 250, 250)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
        db.save(doc)
        docs.append(doc.id)
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {"width": 40, "height": 60, "regions": [], "lines": []})
    # The model lane is not under test (a unit test has no scheduler running it): the segmenter's call runs inline.
    monkeypatch.setattr(jobs, "run_on_lane_blocking", lambda library, kind, subject, *, fn, **kw: fn())
    monkeypatch.setattr(regions, "WAIT_POLL_SECONDS", 0)
    monkeypatch.setattr(regions, "SLOWER_YIELD_SECONDS", 0)
    monkeypatch.setattr(throttle, "_enabled", lambda: True)
    monkeypatch.setattr(throttle, "_started", lambda: False)
    return docs


def _probes(monkeypatch, *, memory_tight_for: int = 0):
    """Battery and in-use always say wait for background work; memory says wait `memory_tight_for` times for everyone."""
    tight = iter([True] * memory_tight_for)
    monkeypatch.setattr(throttle, "PROBES", [
        (lambda: "Waiting: memory is tight" if next(tight, False) else None, True),
        (lambda: "Waiting: the Mac is on battery", False),
        (lambda: "Waiting: you're using the Mac", False)])
    monkeypatch.setattr(throttle, "on_battery", lambda: None)  # the slowing branch is not under test here
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: None)
    monkeypatch.setattr(throttle, "mac_is_in_use", lambda: None)


def test_a_try_is_never_held_by_battery_or_use_and_is_held_by_memory(db, pages, monkeypatch):
    _probes(monkeypatch, memory_tight_for=1)
    said: list[str] = []
    # the run's id is on no row in this db (a try's scratch copy): the caller says a person watches
    account = regions.find_regions(db, pages, "no-such-run", "blla", provider="kraken", say=said.append, person=True)
    assert account["pages"] == 2
    assert said[0] == "Waiting: memory is tight"
    assert not any("battery" in s or "using the Mac" in s for s in said), said


def test_a_run_started_by_hand_reads_its_starter_from_its_own_row(db, pages, monkeypatch):
    _probes(monkeypatch)
    jobs._ensure(db)
    run = jobs._insert(db, "recipe-run", "r", None, "owner")
    said: list[str] = []
    regions.find_regions(db, pages, run, "blla", provider="kraken", say=said.append)
    assert not any("battery" in s or "using the Mac" in s for s in said), said


def test_background_work_is_held_by_battery(db, pages, monkeypatch):
    _probes(monkeypatch)
    waits = iter(range(1))
    real = throttle.PROBES[1]
    monkeypatch.setattr(throttle, "PROBES", [throttle.PROBES[0], (lambda: "Waiting: the Mac is on battery" if next(waits, None) is not None else None, real[1])])
    jobs._ensure(db)
    run = jobs._insert(db, "recipe-run", "r", None, "automatic")
    said: list[str] = []
    regions.find_regions(db, pages, run, "blla", provider="kraken", say=said.append)
    assert said[0] == "Waiting: the Mac is on battery", said
