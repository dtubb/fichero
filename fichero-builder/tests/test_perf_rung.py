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


def _remote(monkeypatch, tmp_path, name, exit_code, stderr=""):
    """`_remote_build_locked` over a fake ssh and a fake run_command: the remote command exits `exit_code` printing `stderr`."""
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    r = {"ok": exit_code == 0, "exit_code": exit_code, "timed_out": False, "seconds": 1, "stdout_tail": "", "stderr_tail": stderr, "errors": ""}
    monkeypatch.setattr(check_tool, "run_command", lambda n, *a, **k: {"ok": True} if n == "build-sync" else dict(r))
    monkeypatch.setattr(check_tool, "_stable_build_tree", lambda root, cfg: str(root))
    return check_tool._remote_build_locked(tmp_path, _perf_cfg(), "m4", "/gate", ("py", "x"), name, False)


def test_a_rung_that_did_not_measure_is_not_run_never_green_and_names_why(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    eng = ["fichero-server/src/x.py"]
    # _remote_build: a 255 is a runner it could not reach (None); any other env-red keeps its row, for every build name
    assert _remote(monkeypatch, tmp_path, "perf", 255, "ssh: connect refused") is None
    for name in ("perf", "build"):
        row = _remote(monkeypatch, tmp_path, name, 1, "No module named pytest_benchmark")
        assert row is not None and not row["ok"] and row["remote_env_red"] and "pytest_benchmark" in row["results"][0]["stderr_tail"]
    # perf(): None is "runner down"; a refused tool and a missing file are named, each with the remote stderr, never "unreachable"
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: None)
    r = check_tool.perf(tmp_path, "a", eng, _perf_cfg())
    assert not r["ok"] and r["not_run"] and "not-run: runner down" in r["stdout_tail"]
    def env_red(err):
        return {"ok": False, "skipped": False, "remote_env_red": True, "remote": "m4", "results": [{"exit_code": 1, "stderr_tail": err, "stdout_tail": ""}]}

    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: env_red("ModuleNotFoundError: No module named pytest_benchmark"))
    r = check_tool.perf(tmp_path, "a", eng, _perf_cfg())
    assert not r["ok"] and r["not_run"] and "not-run: perf tool refused" in r["stdout_tail"] and "pytest_benchmark" in r["stdout_tail"]
    assert "unreachable" not in r["stdout_tail"]
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: env_red("FileNotFoundError: [Errno 2] No such file or directory: 'scripts/perf_baseline.json'"))
    r = check_tool.perf(tmp_path, "a", eng, _perf_cfg())
    assert not r["ok"] and r["not_run"] and "not-run: scripts/perf_baseline.json missing on the runner" in r["stdout_tail"]
    # every one is a journal row with state not-run and an id
    rows = [x for x in journal.read() if x.get("state") == "not-run" and x.get("rung") == "perf"]
    assert len(rows) == 3 and all(x.get("id") for x in rows) and len({x["id"] for x in rows}) == 3


def test_a_perf_run_that_could_not_measure_is_red_even_report_only_but_a_slow_number_is_not(tmp_path, monkeypatch):
    """#6600: report-only forgives a slow figure, never a missing one (2026-11-23: no PERF-RESULT line, pytest exit 1, and the rung counted ok)."""
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    row = {"name": "perf", "ok": True, "exit_code": 1, "stdout_tail": "no result here", "stderr_tail": "pytest exit 1", "timed_out": False}
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": True, "skipped": False, "results": [row]})
    r = check_tool.perf(tmp_path, "a", ["fichero-server/src/x.py"], _perf_cfg())
    assert not r["ok"] and "REFUSED: the perf run printed no PERF-RESULT line" in r["stdout_tail"]
    slow = check_tool._report_only("perf", {"enforce": False}, False, ["median 130 ms over 100"])
    assert slow["ok"] and not slow.get("not_run")


def test_the_result_carries_bytes_written_and_says_each_figures_change_against_the_base_in_percent():
    """#6600: time, peak RSS and the disk the workload added are each compared with the base and the change is said in %."""
    base = {**BASE, "figures": {**BASE["figures"], "written_kib|engine perf run|Mac16,10": {"median": 2000.0}}}
    figs = {"benchmarks": perf_rung.read_benchmarks(_bench(104.0)), "peak_rss_mb": 1020.0, "disk_kib": {}, "written_kib": 2500.0, "top": []}
    out = perf_rung.judge(figs, base, "Mac16,10", "nominal")
    assert out["ok"], out["reds"]
    text = "\n".join(out["changes"])
    assert "104 vs base 100 (+4.0%)" in text and "1020 vs base 1000 (+2.0%)" in text and "2500 vs base 2000 (+25.0%)" in text
    fresh = perf_rung.judge(figs, BASE, "Mac16,10", "nominal")
    assert "written_kib" in "\n".join(fresh["changes"]) and "no base yet" in "\n".join(fresh["changes"])
    assert fresh["recorded"]["written_kib|engine perf run|Mac16,10"] == {"median": 2500.0} and fresh["ok"], "a first figure is recorded, never a red"


_TIME_L = "Test Suite passed\n       42.50 real        30.00 user         5.00 sys\n  734003200  maximum resident set size\n"
_BUILD = ("xcodebuild", "-scheme", "S", "build")
_SWIFT = ["fichero/fichero/A.swift"]


def _swift_remote(monkeypatch, tmp_path, stderr=_TIME_L, exit_code=0):
    from fichero_builder import check_tool, journal
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    seen = []

    def fake(root, cfg, cmd=(), *a, **k):
        seen.append(cmd)
        timed = cmd and cmd[0] == "/usr/bin/time"
        row = {"name": "perf", "ok": exit_code == 0 or not timed, "exit_code": exit_code if timed else 0, "stdout_tail": "",
               "stderr_tail": stderr if timed else "", "timed_out": False}
        return {"ok": row["ok"], "skipped": False, "results": [row]}
    monkeypatch.setattr(check_tool, "_remote_build", fake)
    return seen


def test_a_swift_only_batch_runs_the_app_perf_test_on_the_remote_and_reports_time_and_memory(tmp_path, monkeypatch):
    """#6600: a changed path under fichero/ runs `[check.perf].swift_test` under /usr/bin/time -l on the build remote."""
    from fichero_builder import check_tool
    seen = _swift_remote(monkeypatch, tmp_path)
    cfg = _perf_cfg(build=_BUILD)
    cfg.perf["swift_test"] = "FicheroUITests/LaunchPerformanceUITests"
    r = check_tool.perf(tmp_path, "a", _SWIFT, cfg)
    assert seen == [("/usr/bin/time", "-l", "xcodebuild", "-scheme", "S", "-only-testing:FicheroUITests/LaunchPerformanceUITests", "test")]
    assert r["ok"] and "not required" not in r["stdout_tail"]
    assert "Swift perf: FicheroUITests/LaunchPerformanceUITests 42.5 s, peak 700 MB" in r["stdout_tail"]
    _swift_remote(monkeypatch, tmp_path, stderr="no figures")
    assert not check_tool.perf(tmp_path, "a", _SWIFT, cfg)["ok"], "no readable figure is a refusal"
    _swift_remote(monkeypatch, tmp_path, exit_code=65)
    assert not check_tool.perf(tmp_path, "a", _SWIFT, cfg)["ok"], "a failing test run measured nothing"


def test_a_swift_batch_with_no_swift_test_says_no_workload_yet_and_alerts_once_a_day(tmp_path, monkeypatch):
    from fichero_builder import check_tool, journal
    seen = _swift_remote(monkeypatch, tmp_path)
    r = check_tool.perf(tmp_path, "a", _SWIFT, _perf_cfg(build=_BUILD))
    check_tool.perf(tmp_path, "a", ["fichero/fichero/B.swift"], _perf_cfg(build=_BUILD))
    assert r["ok"] and r["not_run"] and "Swift perf: no workload yet (#6600)" in r["stdout_tail"] and seen == []
    assert len([x for x in journal.read() if x["event"] == "alert" and x.get("rung") == "perf"]) == 1


def test_an_engine_and_swift_batch_runs_both_halves(tmp_path, monkeypatch):
    from fichero_builder import check_tool
    seen = _swift_remote(monkeypatch, tmp_path)
    cfg = _perf_cfg(build=_BUILD)
    cfg.perf["swift_test"] = "T/U"
    r = check_tool.perf(tmp_path, "a", [*_SWIFT, "fichero-server/src/x.py"], cfg)
    assert len(seen) == 2 and seen[0][0] != "/usr/bin/time" and seen[1][0] == "/usr/bin/time"
    assert "Swift perf: T/U" in r["stdout_tail"]


def test_tail_keeps_a_long_final_perf_result_line_whole_so_the_rung_reads_it():
    """#6600: a first run lists every figure; `tail()` cut the line to 300 characters, so PERF_LINE (needs the closing brace) found nothing."""
    from fichero_builder import check_tool
    names = [f"fichero-server/tests/perf/test_some_long_scenario_name_{i}.py::test_scenario_{i}" for i in range(25)]
    verdict = {"ok": True, "reds": [], "recorded": {f"wall_ms|{n}|Mac16,10": {"median": 123.456} for n in names}}
    line = "PERF-RESULT " + json.dumps(verdict, separators=(",", ":"))
    assert len(line) > 300
    m = check_tool.PERF_LINE.search(check_tool.tail("pytest exit 1\n" + line + "\n"))
    assert m and json.loads(m.group(1)) == verdict


def test_with_the_train_on_perf_runs_once_on_the_candidate_and_sends_no_step_back(tmp_path, monkeypatch):
    import pytest

    from fichero_builder import check_tool, train
    monkeypatch.setattr(check_tool, "SCANS_OWED", check_tool._PerThread(True))
    monkeypatch.setattr(check_tool, "_perf_engine", lambda *a, **k: pytest.fail("no perf run for a step"))
    r = check_tool.perf(tmp_path, "b", ["fichero-server/src/x.py"], check_tool.Config(perf={"enforce": False}))
    assert r["ok"] and r["skipped"] and "owed to the train" in r["stdout_tail"]
    names = train.names_for(["fichero-server/src/x.py"], (), lambda f: False, scans=True)
    assert names[-2:] == ["security", "perf"]
    calls = []
    res = train.run_train([{"key": "l/a", "head": "a"}, {"key": "l/b", "head": "b"}], merge=lambda hs: ("+".join(hs), {}),
                          rung=lambda n, c, only=(): calls.append(n) or (True, "perf (report-only) for train t; steps touching what it measured: a"),
                          rungs_for=lambda hs: names, tid="t")
    assert calls.count("perf") == 1 and not res.back and res.landed == ["l/a", "l/b"]
