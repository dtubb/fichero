"""`scripts/runtime_matrix.py` (`runner.measured.runtime-matrix`): its table and JSON with every runtime stubbed
(one ok, one failing, one that loads its model on every page, one not on this Mac). No model, no network."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "runtime_matrix.py"
_SPEC = importlib.util.spec_from_file_location("runtime_matrix", _SCRIPT)
assert _SPEC and _SPEC.loader
rm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rm
_SPEC.loader.exec_module(rm)  # type: ignore[attr-defined]


def _stubs() -> list:
    def loads_once(_page):
        if not rm.LOADS.get("stub-once"):
            rm.LOADS["stub-once"] = 1

    def loads_every_page(_page):
        rm.LOADS["stub-twice"] = rm.LOADS.get("stub-twice", 0) + 1

    def fails(_page):
        raise RuntimeError("the model is out of memory")

    return [
        rm.Runtime("stub-ok", lambda: None, loads_once, "stub-once"),
        rm.Runtime("stub-failing", lambda: None, fails, "stub-fail"),
        rm.Runtime("stub-double", lambda: None, loads_every_page, "stub-twice"),
        rm.Runtime("stub-absent", lambda: "not on this Mac", loads_once),
    ]


def test_the_report_names_each_runtime_and_its_loads(tmp_path):
    pages = [tmp_path / f"p{i}.png" for i in range(5)]
    report = rm.build_report(_stubs(), pages, isolate=False)
    rows = {r["runtime"]: r for r in report["runtimes"]}
    assert rows["stub-ok"]["status"] == "ok" and rows["stub-ok"]["loads"] == 1
    assert rows["stub-ok"]["first_page_s"] is not None and rows["stub-ok"]["pages"] == 5
    assert rows["stub-double"]["loads"] == 10  # 5 pages x 2 passes: it unloads between pages
    assert rows["stub-failing"]["status"] == "failed"
    assert rows["stub-failing"]["kind"] and rows["stub-failing"]["words"]  # the engine's own kind and words
    assert rows["stub-absent"] == {"runtime": "stub-absent", "note": "", "status": "unavailable",
                                   "words": "not on this Mac", "peak_rss_mb": None}
    assert {"chip", "ram_gb", "macos", "free_memory_mb"} <= set(report["machine"])
    json.dumps(report)  # one JSON file


def test_the_table_flags_a_model_loaded_more_than_once(tmp_path):
    report = rm.build_report(_stubs(), [tmp_path / "p.png"], isolate=False)
    text = rm.table(report)
    assert text.startswith("Mac: ")
    assert "| stub-ok | ok |" in text and "| stub-failing | failed |" in text
    assert "unloads between pages" in text.split("| stub-double |")[1].split("\n")[0]
    assert "unloads between pages" not in text.split("| stub-ok |")[1].split("\n")[0]


def test_a_failing_runtime_does_not_stop_the_matrix_or_the_exit_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rm, "real_runtimes", _stubs)
    monkeypatch.setattr(rm, "run_matrix", lambda runtimes, pages, isolate: [rm.measure(r, pages) for r in runtimes])
    monkeypatch.setattr(rm, "install_load_counters", lambda: None)
    monkeypatch.setattr(rm, "scratch_environment", lambda root: None)
    out = tmp_path / "matrix.json"
    assert rm.main(["--out", str(out)]) == 0
    assert len(json.loads(out.read_text())["runtimes"]) == 4
    assert "| stub-failing | failed |" in capsys.readouterr().out
