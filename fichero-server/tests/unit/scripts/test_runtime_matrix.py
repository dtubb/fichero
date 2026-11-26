"""`scripts/runtime_matrix.py` (`runner.measured.runtime-matrix`): its table and JSON with every runtime stubbed
(one ok, one failing, one that loads its model on every page, one not on this Mac). No model, no network."""
from __future__ import annotations

import importlib.util
import json
import os
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
                                   "words": "not on this Mac", "peak_rss_mb": None, "footprint_mb": None}
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


def test_the_sample_has_a_real_size_page(tmp_path):
    """The fixtures are 100 to 900 px wide and Kraken scales every page to 1800 rows, so they measured upscaled thumbnails
    (9.5 GB for a fixture, 3.8 GB for a real page, 2026-11-19): the sample carries an A4 page at 300 dpi too."""
    from PIL import Image

    pages = rm.sample_pages(tmp_path)
    assert [p.name for p in pages[:5]] == list(rm.SAMPLE) and pages[-1].name == rm.REAL_PAGE
    with Image.open(pages[-1]) as image:
        assert image.size == (2480, 3508)
    assert rm.sample_pages(tmp_path) == pages  # a second call (the worker's) reuses the file


def test_the_embedder_row_never_downloads(monkeypatch, tmp_path):
    """fastembed downloads a missing model, and the matrix timed a 116 s download as an 87 to 118 s load (2026-11-19)."""
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    rm.scratch_environment(tmp_path)
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_each_row_carries_the_footprint_beside_the_peak_rss(tmp_path):
    report = rm.build_report(_stubs(), [tmp_path / "p.png"], isolate=False)
    ok = next(r for r in report["runtimes"] if r["runtime"] == "stub-ok")
    assert "footprint_mb" in ok
    assert "footprint MB" in rm.table(report)


def test_python_runs_every_worker_with_that_interpreter(monkeypatch, tmp_path):
    """The gate venvs lack mlx_vlm, mlx_whisper and ultralytics; `--python` measures with the shipped engine's Python."""
    commands = []

    class Done:
        stdout = json.dumps({"runtime": "stub-ok", "status": "ok"}) + "\n"

    monkeypatch.setattr(rm.subprocess, "run", lambda command, **kw: commands.append(command) or Done())
    monkeypatch.setattr(rm, "WORKER_PYTHON", "/engine/python")
    rm.run_matrix(_stubs()[:1], [tmp_path / "p.png"], isolate=True)
    assert commands[0][0] == "/engine/python" and "--worker" in commands[0]
    monkeypatch.setattr(rm, "WORKER_PYTHON", None)
    rm.run_matrix(_stubs()[:1], [tmp_path / "p.png"], isolate=True)
    assert commands[1][0] == sys.executable


def test_python_must_exist(capsys):
    import pytest

    with pytest.raises(SystemExit):
        rm.main(["--python", "/no/such/python"])


def _fake_app(tmp_path):
    app = tmp_path / "Fichero Server.app" / "Contents"
    python = app / "Frameworks" / "Python.framework" / "Versions" / "3.13" / "bin" / "python3.13"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    (app / "Resources" / "app_packages").mkdir(parents=True)
    return tmp_path / "Fichero Server.app", python, app / "Resources" / "app_packages"


def test_the_engine_apps_python_and_packages_are_found_from_the_app(tmp_path):
    """YOLO, MLX VLM and Whisper ship only inside the app (`app_packages/ultralytics`, `mlx_vlm`, `mlx_whisper`)."""
    app, python, packages = _fake_app(tmp_path)
    assert rm.engine_app_python(app) == (python, packages)


def test_an_app_with_no_bundled_python_or_packages_is_refused(tmp_path):
    import pytest

    with pytest.raises(SystemExit):
        rm.engine_app_python(tmp_path / "Nope.app")
    app, python, packages = _fake_app(tmp_path)
    python.unlink()
    with pytest.raises(SystemExit):
        rm.engine_app_python(app)


def test_engine_app_runs_the_workers_under_the_apps_python_with_its_packages(tmp_path, monkeypatch):
    app, python, packages = _fake_app(tmp_path)
    monkeypatch.setattr(rm, "real_runtimes", lambda: [])
    monkeypatch.setattr(rm, "install_load_counters", lambda: None)
    monkeypatch.setattr(rm, "scratch_environment", lambda root: None)
    monkeypatch.setattr(rm, "build_report", lambda *a, **k: {"machine": {"chip": "x", "ram_gb": 1, "macos": "x", "free_memory_mb": 1}, "runtimes": []})
    monkeypatch.setattr(rm, "WORKER_PYTHON", None)
    monkeypatch.setenv("PYTHONPATH", "")  # restored after the test
    assert rm.main(["--engine-app", str(app), "--out", str(tmp_path / "m.json")]) == 0
    assert rm.WORKER_PYTHON == str(python)
    assert str(packages) in os.environ["PYTHONPATH"].split(":")


def test_the_machine_reads_ram_through_the_full_sysctl_path_so_a_bare_path_still_reports_it(monkeypatch):
    """#6860: `sysctl` is not on a worker's PATH (only /usr/sbin/sysctl works); the matrix reported ram_gb None."""
    import subprocess

    def fake_run(argv, **_kw):
        out = "17179869184\n" if argv[:3] == ["/usr/sbin/sysctl", "-n", "hw.memsize"] else ""
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    monkeypatch.setattr(rm.subprocess, "run", fake_run)
    assert rm.machine()["ram_gb"] == 16
