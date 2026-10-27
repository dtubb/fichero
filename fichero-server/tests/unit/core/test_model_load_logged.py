"""A model load says its time, and a model loaded again soon after says so once (owner's north star, #6236)."""
from __future__ import annotations

import logging

from fichero_server.core import perf


def test_a_load_says_its_time_and_a_reload_warns_once(caplog, monkeypatch):
    perf._LOADS.clear()
    clock = iter([0.0, 2.5, 100.0, 101.0, 200.0, 201.0])
    monkeypatch.setattr(perf.time, "monotonic", lambda: next(clock))
    with caplog.at_level(logging.INFO, logger=perf.__name__):
        for _ in range(3):
            with perf.model_load("kraken segment blla"):
                pass
    said = [r for r in caplog.records if "kraken segment blla" in r.getMessage()]
    assert "loaded kraken segment blla in 2.5 s (load 1 in this engine)" in said[0].getMessage()
    warned = [r.getMessage() for r in said if r.levelno == logging.WARNING]
    assert len(warned) == 1 and "loaded again" in warned[0] and "98 s after" in warned[0]


def test_a_reload_after_the_window_is_quiet(caplog, monkeypatch):
    perf._LOADS.clear()
    clock = iter([0.0, 1.0, 5000.0, 5001.0])
    monkeypatch.setattr(perf.time, "monotonic", lambda: next(clock))
    with caplog.at_level(logging.INFO, logger=perf.__name__):
        for _ in range(2):
            with perf.model_load("embedder e5"):
                pass
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
