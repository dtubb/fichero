"""A step's per-page time that climbs over a run logs one line (owner's north star: slow-path logging, #6236)."""
from __future__ import annotations

import logging

from fichero_server.execution import runner


def _pages(key, times):
    return [runner.note_page_time(key, ms, "Extract Entities") for ms in times]


def test_a_climb_logs_once(caplog):
    runner._PAGE_TIMES.clear()
    with caplog.at_level(logging.WARNING, logger=runner.__name__):
        _pages("node-a", [1000] * 10 + [1100] * 10 + [4000] * 10 + [5000] * 10)
    lines = [r.getMessage() for r in caplog.records if "per-page time climbing" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "Extract Entities" in lines[0] and "1.0 s" in lines[0]


def test_steady_or_one_slow_page_says_nothing(caplog):
    runner._PAGE_TIMES.clear()
    with caplog.at_level(logging.WARNING, logger=runner.__name__):
        _pages("node-b", [1000] * 30 + [60_000] + [1000] * 30)  # one big page is not a climb
        _pages("node-c", [50] * 10 + [400] * 20)  # 8x, but under a second more: noise on a fast step
    assert not [r for r in caplog.records if "per-page time climbing" in r.getMessage()]


def test_the_history_kept_is_bounded():
    runner._PAGE_TIMES.clear()
    _pages("node-d", [1000] * 100_000)
    first, recent = runner._PAGE_TIMES["node-d"]
    assert len(first) == runner.CLIMB_PAGES and len(recent) == runner.CLIMB_PAGES
