"""The two log readers of the performance sweep (#6600, Step 2): `perf-sweep.source.app-log-phases` and
`perf-sweep.source.engine-perf-lines`, over fixture logs (no Mac, no app, no model)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FIX = REPO_ROOT / "fichero-builder" / "tests" / "fixtures" / "perf"
_spec = importlib.util.spec_from_file_location("perf_log_readers", REPO_ROOT / "fichero-builder" / "fichero_builder" / "perf_log_readers.py")
readers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(readers)


def _by(rows, key):
    return {r[key]: r for r in rows}


def test_launch_and_interaction_lines_become_phase_rows_with_p50_p95_count():
    out = readers.read_app_log((FIX / "app-log.jsonl").read_text().splitlines())
    rows = _by(out["phases"], "phase")
    expand = rows["sidebar expand"]
    assert (expand["kind"], expand["count"]) == ("interaction", 40)
    assert (expand["p50"], expand["p95"], expand["max"]) == (200.0, 380.0, 400.0)  # nearest rank over 10..400 ms
    assert rows["sidebar expand: fetch"]["count"] == 40  # laps keep their names
    assert "preview swipe → image" not in rows  # a superseded interval is not a measurement
    # launch milestones become ordered gaps whose sum is the last milestone's elapsed
    launch = [r for r in out["phases"] if r["kind"] == "launch"]
    assert [r["phase"] for r in launch] == ["process start", "engine ready", "first window"]
    assert [r["p50"] for r in launch] == [0.0, 412.5, 487.5]
    assert sum(r["p50"] for r in launch) == 900.0
    assert out["status"] == "ok"


def test_the_stderr_timeline_alone_still_yields_the_launch_rows_and_an_empty_log_is_not_green():
    out = readers.read_app_log((FIX / "app-stderr.txt").read_text().splitlines())
    launch = [r for r in out["phases"] if r["kind"] == "launch"]
    assert [r["phase"] for r in launch] == ["process start", "engine ready", "first window"]  # the "(uds)" detail is not a new phase
    assert sum(r["p50"] for r in launch) == 750.0
    empty = readers.read_app_log([])
    assert empty["phases"] == [] and empty["status"] == "no-app-log"


def test_perf_spans_group_by_name_with_count_total_and_model_reloads():
    out = readers.read_engine_log((FIX / "engine.log").read_text().splitlines())
    spans = _by(out["spans"], "name")
    imp = spans["import.page"]
    assert (imp["count"], imp["p50"], imp["p95"], imp["max"], imp["total"]) == (3, 200.0, 300.0, 300.0, 600.0)
    assert spans["search.query"]["total"] == 16.0  # count x p50: how often, not only how slow
    assert "doc_id" not in imp.get("context", {}) and "pages" not in imp.get("context", {})
    models = _by(out["models"], "model")
    assert (models["kraken"]["loads"], models["kraken"]["total_s"], models["kraken"]["reload"]) == (2, 23.0, True)
    assert models["spacy"]["reload"] is False
    assert out["status"] == "ok"  # the uvicorn line was ignored


def test_a_group_by_key_splits_the_span_row_and_an_empty_engine_log_is_marked():
    out = readers.read_engine_log((FIX / "engine.log").read_text().splitlines(), group_by=("provider",))
    kg = [r for r in out["spans"] if r["name"] == "kg.entity_list"]
    assert sorted(r["group"]["provider"] for r in kg) == ["cloud", "local"]
    none = readers.read_engine_log(["INFO uvicorn: up"])
    assert none["spans"] == [] and none["models"] == [] and none["status"] == "no-engine-log"
