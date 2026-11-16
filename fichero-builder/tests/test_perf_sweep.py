"""The performance sweep's row shape, area map and ranked hotspot table (#6600, Step 2):
`perf-sweep.output.row` and `perf-sweep.output.table`."""
import json
import re
from pathlib import Path

import pytest

from fichero_builder import journal, perf_sweep, review_lenses

FIX = Path(__file__).resolve().parent / "fixtures" / "perf"


def _row(**kw):
    base = dict(run="r1", machine_model="Mac16,1", workload="w", side="engine", where="a.b", kind="time", value=10.0, unit="ms",
                count=1, share=0.5, source="perf-line")
    base.update(kw)
    return perf_sweep.make_row(**base)


def test_rows_have_one_shape_and_an_area_from_the_lens_map():
    assert review_lenses.area_of("fichero/fichero/Views/Sidebar/SidebarView.swift") == "sidebar"
    assert review_lenses.area_of("fichero-server/src/fichero_server/recipes/x.py") == "recipes"
    r = _row(where="fichero/fichero/Views/Sidebar/SidebarView.swift")
    assert r["area"] == "sidebar"
    assert set(r) >= {"run", "machine_model", "workload", "side", "area", "kind", "where", "value", "unit", "count", "share",
                      "source", "trend_pct", "runs_seen", "profile"}
    for missing in ("where", "value", "source"):
        with pytest.raises(ValueError, match=missing):
            _row(**{missing: None})


def _scaled(lines, k):
    """Every duration in the fixture lines times k (a slower run of the same workload)."""
    return [re.sub(r"(duration_ms=|@ |took )(\d+(?:\.\d+)?)", lambda m: f"{m.group(1)}{float(m.group(2)) * k:.2f}", ln) for ln in lines]


def _logs_run(state, run="r1", scale=1.0):
    return perf_sweep.sweep(
        run=run, machine_model="Mac16,1", state=state, workload="smoke",
        app_log=_scaled((FIX / "app-log.jsonl").read_text().splitlines(), scale),
        engine_log=_scaled((FIX / "engine.log").read_text().splitlines(), scale))


def test_the_table_ranks_per_kind_greys_moves_inside_the_band_and_the_console_reads_latest(tmp_path):
    out = _logs_run(tmp_path)
    hot = json.loads((tmp_path / "perf" / "r1" / "hotspots.json").read_text())
    assert len(hot["rows"]) == len(out["rows"]) > 5
    latest = json.loads((tmp_path / "perf" / "latest.json").read_text())
    assert latest["run"] == "r1" and latest["hotspots"].endswith("r1/hotspots.json")
    top = latest["top"]
    # ranked within a kind by share: import.page (600 of 616 engine span ms) leads the engine time rows
    eng = [r for r in top if r["side"] == "engine" and r["kind"] == "time" and r["where"] in ("import.page", "search.query")]
    assert [r["where"] for r in eng] == ["import.page", "search.query"]
    assert "sidebar expand" in [r["where"] for r in top]
    assert all(r["trend_pct"] is None and r["runs_seen"] == 1 for r in top)
    # a log with no engine lines is said, never green
    assert perf_sweep.sweep(run="r0", machine_model="m", state=tmp_path / "x", workload="w", app_log=[], engine_log=[])["notes"] == ["no-app-log", "no-engine-log"]

    # the top 50 holds at most 10 rows per kind
    many = [_row(where=f"s{i}", value=float(i), share=i / 1000, kind="time") for i in range(30)] + [_row(where="disk", kind="disk", value=1.0, share=0.001, unit="KiB")]
    t = perf_sweep.rank(many)
    assert sum(r["kind"] == "time" for r in t) == 10 and any(r["kind"] == "disk" for r in t)  # a disk hog is not buried

    # trend: second run 3% slower under a 6% band shows ~, 20% slower shows +20%
    _logs_run(tmp_path, run="r2", scale=1.03)
    r2 = json.loads((tmp_path / "perf" / "latest.json").read_text())["top"]
    imp = next(r for r in r2 if r["where"] == "import.page")
    assert imp["runs_seen"] == 2 and perf_sweep.trend_text(imp["trend_pct"], band=6.0) == "~"
    assert perf_sweep.trend_text(20.0, band=6.0) == "+20%" and perf_sweep.trend_text(-12.0, band=6.0) == "−12%"
    assert perf_sweep.trend_text(None, band=6.0) == "new"


def test_show_prints_every_column_and_diff_lists_only_band_crossing_rows(tmp_path, capsys):
    _logs_run(tmp_path, run="r1")
    _logs_run(tmp_path, run="r2", scale=1.03)
    _logs_run(tmp_path, run="r3", scale=1.5)
    journal.STATE = tmp_path
    perf_sweep.show(tmp_path, "r3")
    text = capsys.readouterr().out
    for col in ("kind", "area", "where", "value", "share", "count", "trend", "workload", "profile"):
        assert col in text.splitlines()[0]
    assert "import.page" in text and "sidebar expand" in text
    perf_sweep.diff(tmp_path, "r1", "r2")
    assert "import.page" not in capsys.readouterr().out  # 3% is inside the band
    perf_sweep.diff(tmp_path, "r2", "r3")
    assert "import.page" in capsys.readouterr().out
    assert perf_sweep.show(tmp_path, "nope") == 2  # an unknown run is said, not an empty table
