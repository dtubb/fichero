"""`scripts/perf_engine_run.py` (#6600, `perf-sweep.rung.not-run-is-visible`): a run that ran its tests measured something, from pytest's own junit
report when pytest-benchmark's JSON holds nothing; it is "measured nothing" only when pytest could not run. Pytest itself is faked."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from fichero_builder import check_tool, journal, perf_rung

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "perf_engine_run.py"
RSS = "        1.00 real\n  1100000000  maximum resident set size\n"
BASE = {"tolerances": {"wall_ms": 0.05, "peak_rss_mb": 0.03, "disk_kib": 0}, "figures": {}, "top": []}


def junit(*cases):
    """cases: (name, seconds, 'ok' | 'failure' | 'error' | 'skipped')"""
    body = "".join(f'<testcase classname="perf.test_x" name="{n}" time="{t}">' + ("" if k == "ok" else f'<{k} message="m"/>') + "</testcase>" for n, t, k in cases)
    return f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{body}</testsuite></testsuites>'


@pytest.fixture
def run(tmp_path, monkeypatch):
    """main() over a fake pytest: `script(xml, exit_code, bench=None)` then call it; returns (PERF-RESULT dict, argv the fake saw)."""
    spec = importlib.util.spec_from_file_location("perf_engine_run_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(BASE))
    monkeypatch.setattr(mod, "thermal", lambda: "nominal")
    monkeypatch.setattr(mod, "sh", lambda argv, **k: "Mac16,10\n")
    monkeypatch.setattr(mod.os, "getloadavg", lambda: (0.5, 0.5, 0.5))
    monkeypatch.setattr(mod, "have", lambda m: True)
    monkeypatch.setattr(mod.sys, "argv", ["perf_engine_run.py", "--baseline", str(baseline)])
    saw = {}

    def go(xml, code=0, bench=None, profile=True, benchmark_module=True, load=0.5):
        monkeypatch.setattr(mod, "have", lambda m: profile if m == "pyinstrument" else benchmark_module)
        monkeypatch.setattr(mod.os, "getloadavg", lambda: (load, 0, 0))

        def fake_run(argv, **k):
            saw["argv"] = argv
            j = next(a.split("=", 1)[1] for a in argv if a.startswith("--junitxml="))
            if xml is not None:
                Path(j).write_text(xml)
            if bench is not None:
                (Path(j).parent / "bench.json").write_text(bench)
            return subprocess.CompletedProcess(argv, code, "", RSS)
        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        printed = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(a[0]) if not k.get("file") else None)
        assert mod.main() == 0
        line = next(p for p in printed if p.startswith("PERF-RESULT "))
        return json.loads(line.removeprefix("PERF-RESULT ")), saw["argv"]
    return go


def test_a_run_whose_tests_ran_measures_their_durations_with_no_benchmark_json(run):
    res, argv = run(junit(("test_list", 0.0123, "ok"), ("test_get", 0.002, "ok"), ("test_slow", 9, "skipped")))
    assert res["ok"] and not res["reds"] and not res["void"]
    assert res["figures"]["benchmarks"] == {"perf.test_x::test_list": pytest.approx(12.3), "perf.test_x::test_get": pytest.approx(2.0)}
    assert any("note: no pytest-benchmark figures" in n for n in res["notes"])
    assert "--junitxml" in " ".join(argv) and "pyinstrument" in argv


def test_benchmark_json_is_used_when_it_holds_figures(run):
    res, _ = run(junit(("test_list", 0.5, "ok")), bench=json.dumps({"benchmarks": [{"fullname": "t::b", "stats": {"median": 0.004}}]}))
    assert res["figures"]["benchmarks"] == {"t::b": pytest.approx(4.0)}


@pytest.mark.parametrize("xml,code", [(None, 4), (junit(), 5), (junit(("a", 1, "error")), 2), (None, 0), ("not xml", 1), (junit(("a", 1, "skipped")), 0)])
def test_a_run_where_pytest_could_not_run_is_refused(run, xml, code):
    """An import error / collection error / usage error / no tests (exit 2-5), no report, an unreadable one or only skips: measured nothing."""
    res, _ = run(xml, code)
    assert not res["ok"] and res["reds"][0].startswith("REFUSED: ") and not res["figures"]["benchmarks"]


def test_a_ratchet_that_failed_on_an_idle_machine_is_a_red_naming_the_test_and_has_no_figure(run):
    res, _ = run(junit(("test_list", 0.3, "failure"), ("test_get", 0.002, "ok")), code=1)
    assert not res["ok"] and "1 perf test(s) failed" in res["reds"][0] and "test_list" in res["reds"][0] and not res["reds"][0].startswith("REFUSED")
    assert list(res["figures"]["benchmarks"]) == ["perf.test_x::test_get"]


def test_failing_ratchets_on_a_busy_machine_are_void_not_red(run):
    res, _ = run(junit(("test_list", 0.315, "failure")), code=1, load=7.0)
    assert res["ok"] and not res["reds"] and res["void"].startswith("VOID") and "not idle" in res["void"]


def test_no_pyinstrument_or_benchmark_plugin_is_a_note_not_a_refusal(run):
    res, argv = run(junit(("test_list", 0.01, "ok")), profile=False, benchmark_module=False)
    assert res["ok"] and not res["reds"] and any("pyinstrument is not installed" in n for n in res["notes"])
    assert "pyinstrument" not in argv and "pytest_benchmark" not in argv
    res, _ = run(junit(("test_list", 0.01, "ok")), profile=True)  # a profile that was not written: also a note
    assert res["ok"] and any("no pyinstrument profile was written" in n for n in res["notes"])


def test_a_void_run_is_an_alert_row_and_the_rung_stays_ok_and_notes_are_said(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    res = {"ok": True, "reds": [], "findings": [], "falls": [], "changes": [], "recorded": {}, "void": "VOID: the machine was not idle: neither pass nor fail",
           "notes": ["note: no pyinstrument profile"]}
    row = {"name": "perf", "ok": True, "exit_code": 0, "stdout_tail": "PERF-RESULT " + json.dumps(res), "stderr_tail": "", "timed_out": False}
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": True, "skipped": False, "results": [row]})
    cfg = check_tool.Config(perf={"enforce": True}, build_remote="m4:/g")
    r = check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], cfg)
    assert r["ok"] and not r.get("not_run") and "VOID" in r["stdout_tail"] and "note: no pyinstrument profile" in r["stdout_tail"]
    assert [x for x in journal.read() if x["event"] == "alert" and x.get("step") == "rung-perf" and "VOID" in x["what"]]


def test_judge_reds_failed_tests_only_after_the_void_check():
    figs = {"benchmarks": {}, "failed": ["t::a"], "peak_rss_mb": None, "disk_kib": {}, "top": []}
    assert perf_rung.judge(figs, BASE, "M", "nominal", idle=False)["ok"]
    assert not perf_rung.judge(figs, BASE, "M", "nominal", idle=True)["ok"]
