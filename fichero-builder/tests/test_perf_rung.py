"""The engine half of the `perf` rung reads three tools' output and reds only a worse figure (#6600, Step 2.30)."""
import json

from fichero_builder import perf_rung

BASE = {
    "tolerances": {"wall_ms": 0.05, "peak_rss_mb": 0.03, "disk_kib": 0},
    "figures": {
        "wall_ms|tests/perf/test_entity_list_perf.py::test_list|Mac16,10": {"median": 100.0},
        "peak_rss_mb|engine perf run|Mac16,10": {"median": 1000.0},
    },
    "top": ["parse (fichero_server/a.py:1)", "json.dumps (json/__init__.py:2)"],
}
NAME = "tests/perf/test_entity_list_perf.py::test_list"


def _bench(median_ms):
    return json.dumps({"benchmarks": [{"fullname": NAME, "stats": {"median": median_ms / 1000}}]})


def _judge(ms=100.0, rss=1000.0, disk=None, top=None, thermal="nominal", model="Mac16,10"):
    figs = {"benchmarks": perf_rung.read_benchmarks(_bench(ms)), "peak_rss_mb": rss, "disk_kib": disk or {}, "top": top or []}
    return perf_rung.judge(figs, BASE, model, thermal)


def test_the_engine_half_reads_benchmark_rss_disk_and_profile_and_reds_only_a_worse_figure():
    over = _judge(ms=108.0)  # 8% over: red naming the test, both medians and the machine
    assert not over["ok"] and NAME in over["reds"][0] and "108" in over["reds"][0] and "100" in over["reds"][0] and "Mac16,10" in over["reds"][0]
    assert _judge(ms=104.0)["ok"]  # 4% over is green
    time_l = "        1.00 real  1.0 user  0.1 sys\n  1100000000  maximum resident set size\n  7  page reclaims\n"
    rss = perf_rung.read_peak_rss_mb(time_l)  # 1,100,000,000 bytes: 1049 MB, about 4.9% over 1000
    assert 1048 < rss < 1050 and not _judge(rss=rss)["ok"]  # 4.9% over a 3% tolerance is red
    assert not _judge(rss=1050.0)["ok"] and _judge(rss=1020.0)["ok"]
    # a du pair whose delta is 40 KiB with no declared output is red naming the directory; a declared one is subtracted
    delta = perf_rung.disk_delta(perf_rung.read_du("100\t/lib\n5\t/cache\n"), perf_rung.read_du("100\t/lib\n45\t/cache\n"))
    red = _judge(disk=delta)
    assert not red["ok"] and "/cache" in red["reds"][0] and "40" in red["reds"][0]
    assert _judge(disk=perf_rung.disk_delta({"/cache": 5}, {"/cache": 45}, {"/cache": 40}))["ok"]
    # a new own frame in the top ten prints a finding and stays green; a library's frame does not
    prof = {"root_frame": {"function": "main", "file_path_short": "m.py", "line_no": 1, "time": 10.0, "children": [
        {"function": "new_hot", "file_path_short": "fichero_server/b.py", "line_no": 9, "time": 6.0, "children": []},
        {"function": "dumps", "file_path_short": "json/__init__.py", "line_no": 2, "time": 3.0, "children": []}]}}
    top = perf_rung.top_self_frames(json.dumps(prof))
    assert top[0].startswith("new_hot")
    r = _judge(top=top)
    assert r["ok"] and r["findings"] == ["new_hot (fichero_server/b.py:9)"]
    # a raised baseline in the batch's diff is refused; a lower one is not
    assert perf_rung.raised_baselines(BASE, {**BASE, "figures": {k: {"median": v["median"] * 1.1} for k, v in BASE["figures"].items()}})
    assert not perf_rung.raised_baselines(BASE, {**BASE, "figures": {k: {"median": v["median"] * 0.9} for k, v in BASE["figures"].items()}})
    assert perf_rung.raised_baselines(BASE, {**BASE, "tolerances": {**BASE["tolerances"], "wall_ms": 0.2}})


def test_a_machine_that_cannot_be_read_or_is_throttled_is_refused_or_void_never_green():
    assert not _judge(thermal=None)["ok"] and "REFUSED" in _judge(thermal=None)["reds"][0]
    assert not _judge(model="")["ok"]
    void = _judge(ms=500.0, thermal="fair")
    assert void["ok"] and void["void"].startswith("VOID") and not void["reds"]
    assert _judge(ms=500.0, model="Mac14,2")["ok"]  # another machine's figure is never compared with this baseline's


def test_a_batch_that_touches_no_engine_path_is_not_required():
    assert perf_rung.required(["fichero/fichero/A.swift", "docs/a.md"]).startswith("not required")
    assert perf_rung.required(["fichero-server/src/x.py"]) == ""
    assert perf_rung.required(["pipeline/plan.py"]) == ""


def test_the_rung_skips_unconfigured_unrequired_and_runnerless_batches_and_stays_green_while_report_only(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    eng = ["fichero-server/src/x.py"]
    assert check_tool.perf(tmp_path, "a", eng, check_tool.Config())["stdout_tail"] == "skipped: not configured"
    cfg = check_tool.Config(perf={"enforce": False})
    assert "not required" in check_tool.perf(tmp_path, "a", ["docs/a.md"], cfg)["stdout_tail"]
    assert "never runs on the manager's Mac" in check_tool.perf(tmp_path, "a", eng, cfg)["stdout_tail"]  # no build_remote: not run here
    assert check_tool._report_only("perf", {"enforce": False}, False, ["median 130 ms over 100"])["ok"]
    assert [r for r in journal.read() if r["event"] == "alert" and r.get("rung") == "perf"]


def _perf_cfg(**kw):
    from fichero_builder import check_tool
    return check_tool.Config(perf={"enforce": False}, build_remote="m4:~/fichero-gate", **kw)


def test_perf_argv_uses_the_gate_venv_python_when_remote_python_is_empty(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    seen = []
    monkeypatch.setattr(check_tool, "_remote_build", lambda root, cfg, cmd=(), *a, **k: seen.append(cmd))
    check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg())
    assert seen[0][0].endswith("/venv/bin/python") and seen[0][0] != "python3"
    check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg(remote_python="/opt/py"))
    assert seen[1][0] == "/opt/py"


def test_a_remote_crash_is_a_not_run_row_with_its_stderr_never_unreachable(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    row = {"name": "perf", "ok": False, "exit_code": 1, "stdout_tail": "", "stderr_tail": "TypeError: unsupported operand Path | str", "timed_out": False}
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": False, "skipped": False, "crashed": True, "remote": "m4", "results": [row]})
    r = check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg())
    assert "unreachable" not in r["stdout_tail"] and "TypeError" in r["stdout_tail"]
    assert r["not_run"] and check_tool.rung_not_run(r)
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: None)
    assert "unreachable" in check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg())["stdout_tail"]


def test_a_run_with_no_baseline_figures_records_them_and_does_not_fail():
    base = {"tolerances": {"wall_ms": 0.05, "peak_rss_mb": 0.03, "disk_kib": 0}, "figures": {}}
    out = perf_rung.judge({"benchmarks": {"t::a": 12.0}, "peak_rss_mb": 500.0, "disk_kib": {}, "top": []}, base, "Mac16,10", "nominal")
    assert out["ok"] and out["reds"] == []
    assert out["recorded"] == {"wall_ms|t::a|Mac16,10": {"median": 12.0}, "peak_rss_mb|engine perf run|Mac16,10": {"median": 500.0}}


def test_a_refused_or_skipped_rung_is_not_run_never_green(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")  # #6589: without it, every run wrote a security alert to the owner's journal
    assert check_tool.rung_not_run({"ok": True, "skipped": True})
    r = check_tool._report_only("security", {"enforce": False}, False, ["REFUSED: bandit has no pinned version in harness.toml [check.security]"])
    assert r["ok"] and r["not_run"] and check_tool.rung_not_run(r)
    assert not check_tool.rung_not_run(check_tool._report_only("perf", {"enforce": False}, True, ["all within tolerance"]))


def test_a_perf_timeout_is_an_alert_row_never_a_crash_or_a_red(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    r = {"ok": False, "exit_code": -9, "timed_out": True, "seconds": 900, "stdout_tail": "", "stderr_tail": ""}
    monkeypatch.setattr(check_tool, "run_command", lambda n, *a, **k: {"ok": True} if n == "build-sync" else r)
    monkeypatch.setattr(check_tool, "_ssh", lambda *a, **k: type("P", (), {"returncode": 0, "stdout": b"/gate\n", "stderr": b""})())
    monkeypatch.setattr(check_tool, "_stable_build_tree", lambda root, cfg: str(root))
    out = check_tool._remote_build_locked(tmp_path, _perf_cfg(), "m4", "/gate", ("py", "x"), "perf", False)
    assert out is not None and not out.get("crashed") and out["results"][0]["timed_out"]
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: out)
    res = check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg())
    assert res["ok"] and "timed out" in res["stdout_tail"] and not res.get("not_run")
    assert [x for x in journal.read() if x["event"] == "alert" and x.get("rung") == "perf"]
