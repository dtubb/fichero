"""`recipes-run.memory.recorded-per-step` (#6673): each step records the Mac's RAM, the engine's peak, swap, memory pressure and
model loads and unloads, in the run's record and in the engine log Save Logs for Support carries."""
from __future__ import annotations

import logging

from fichero_server.core import perf
from fichero_server.execution import jobs, throttle
from fichero_server.recipes import runner, step_memory

GIB = 1024**3
REAL = step_memory.StepMemory


def _reading(loads, pressure=2):
    peak = throttle.PeakMemory(engine=lambda: None, servers=lambda: None, rss=lambda: 7 * GIB, swap=lambda: 6 * GIB)
    return REAL(ram=lambda: 16 * GIB, pressure=lambda: pressure, peak=peak, loads=loads)


def test_a_steps_reading_has_ram_peak_swap_pressure_and_the_loads_and_unloads_it_saw():
    totals = iter([(10, 4), (41, 35)])
    memory = _reading(lambda: next(totals))
    memory.start()
    found = memory.finish()
    assert found == {"model_loads": 31, "model_unloads": 31, "ram_bytes": 16 * GIB,
                     "engine_peak_rss_since_start_bytes": 7 * GIB, "swap_used_bytes": 6 * GIB, "swap_growth_bytes": 0,
                     "memory_pressure": "high"}


def test_the_log_line_reads_like_the_support_note():
    line = step_memory.words("lines", {"model_loads": 31, "model_unloads": 31, "swap_used_bytes": 6 * GIB, "memory_pressure": "high"})
    assert line == "run step lines: 31 model loads, 31 unloads; swap 6.0 GB; memory pressure high"


def test_a_step_run_over_two_batches_adds_its_loads_and_keeps_the_worst_pressure():
    step: dict = {}
    step_memory.record(step, "lines", {"model_loads": 2, "model_unloads": 1, "memory_pressure": "critical", "swap_used_bytes": 1})
    step_memory.record(step, "lines", {"model_loads": 3, "model_unloads": 0, "memory_pressure": "normal", "swap_used_bytes": 5})
    assert step["memory"] == {"model_loads": 5, "model_unloads": 1, "memory_pressure": "critical", "swap_used_bytes": 5}


def test_a_model_unload_is_counted_beside_its_loads():
    loads, unloads = perf.model_load_totals()
    perf.model_unloaded("kraken")
    assert perf.model_load_totals() == (loads, unloads + 1)


def test_the_run_batch_puts_the_steps_memory_in_its_record_and_the_log(monkeypatch, caplog):
    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_step_pages", lambda *a, **k: (["p1"], {}, {"p1": "page"}))
    for name in ("_blocked", "_await_downloads", "_after_the_step", "_recount_on_the_folder", "_beside"):
        monkeypatch.setattr(runner, name, lambda *a, **k: None)
    monkeypatch.setattr(runner, "_run_card", lambda *a, **k: ("child", "done", None))
    monkeypatch.setattr(runner, "_stop_asked", lambda *a: False)
    monkeypatch.setattr(runner, "_wait_out_a_pause", lambda *a: None)
    monkeypatch.setattr(runner, "_let_go_after_the_last_served_step", lambda *a: None)
    totals = iter([(0, 0), (2, 1)])
    monkeypatch.setattr(step_memory, "StepMemory", lambda: _reading(lambda: next(totals)))
    detail = {"runs": [{"card": "workflow", "job": "find-lines", "steps": ["lines"]}], "steps": [{"state": "waiting"}],
              "batch_states": [None], "redo": []}
    with caplog.at_level(logging.INFO, logger=step_memory.logger.name):
        runner._run_batch(None, "job", detail, {"units": ["p1"], "folder": "f"}, {}, "test", final=True)
    assert detail["steps"][0]["memory"]["model_loads"] == 2
    assert any("run step lines: 2 model loads, 1 unloads" in r.getMessage() for r in caplog.records)
