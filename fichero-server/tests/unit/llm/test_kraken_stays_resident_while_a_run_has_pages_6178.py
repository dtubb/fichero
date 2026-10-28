"""Kraken is not let go between the pages of a run that is still going (#6178, `activity.lane.load-once`):
Ann's engine reloaded it 23 times in a day because a page that took over the idle spell (120 s) let go of
the reader while the run still had pages waiting."""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime as kr


def _held():
    kr._RESIDENT.clear()
    kr._RESIDENT["read"] = ("reader-a", object())


def test_the_idle_release_keeps_the_reader_while_the_run_has_pages_in_flight(monkeypatch):
    _held()
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: True)
    kr._release_if_idle()
    assert "read" in kr._RESIDENT
    assert kr._idle_timer is not None  # looked at again later, not forgotten
    kr._idle_timer.cancel()


def test_with_no_run_going_the_idle_release_still_lets_go(monkeypatch):
    _held()
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: False)
    kr._release_if_idle()
    assert not kr._RESIDENT
