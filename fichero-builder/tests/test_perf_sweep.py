"""The performance sweep's row shape, area map and ranked hotspot table (#6600, Step 2):
`perf-sweep.output.row` and `perf-sweep.output.table`."""
import json
import os
import re
import shlex
import time
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


def test_show_prints_every_column_and_diff_lists_only_band_crossing_rows(tmp_path, capsys, monkeypatch):
    _logs_run(tmp_path, run="r1")
    _logs_run(tmp_path, run="r2", scale=1.03)
    _logs_run(tmp_path, run="r3", scale=1.5)
    monkeypatch.setattr(journal, "STATE", tmp_path)
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


# --- Step 3 (#6613): the workloads and the machine tags ---------------------------------------------------------------------------

import tomllib  # noqa: E402

from fichero_builder import perf_workloads  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _rules():
    return tomllib.loads((REPO / "harness.toml").read_text())


def _manifest():
    return json.loads((REPO / "scripts" / "perf_corpus.json").read_text())


def test_the_workload_table_loads_and_refuses_an_undeclared_corpus_or_budget():
    """perf-sweep.workload.set"""
    rules, manifest = _rules(), _manifest()
    table = perf_workloads.load(rules, manifest)
    assert [w["name"] for w in table] == [f"w{i}" for i in range(1, 11)]
    assert [w["side"] for w in table] == ["engine"] * 5 + ["app"] * 5
    for w in table:
        assert w["corpus"] and w["budget_s"] > 0 and w["outputs"]
    # an engine workload is a pytest driver or a script that exists; an app workload is a FICHERO_PERF_WORKLOAD scenario
    for w in table[:5]:
        files = [t.split("::")[0] for d in w["drivers"] for t in d.split() if t.endswith(".py") or ".py::" in t]
        assert files and all((REPO / f).is_file() for f in files), w["name"]
    assert [w["drivers"] for w in table[5:]] == [[f"FICHERO_PERF_WORKLOAD=w{i}"] for i in range(6, 11)]
    # the seven perf tests are regrouped, none dropped, none run twice
    drivers = " ".join(d for w in table[:5] for d in w["drivers"])
    for f in sorted((REPO / "fichero-server" / "tests" / "perf").glob("test_*.py")):
        assert drivers.count(f.name) == 1, f.name

    def broken(name, **drop):
        r = json.loads(json.dumps(rules))
        for k, v in drop.items():
            if v is None:
                del r["perf"]["workloads"][name][k]
            else:
                r["perf"]["workloads"][name][k] = v
        return r

    with pytest.raises(ValueError, match=r"w3.*corpus"):
        perf_workloads.load(broken("w3", corpus=None), manifest)
    with pytest.raises(ValueError, match=r"w7.*budget_s"):
        perf_workloads.load(broken("w7", budget_s=None), manifest)
    with pytest.raises(ValueError, match=r"w2.*not-in-the-manifest"):
        perf_workloads.load(broken("w2", corpus="not-in-the-manifest"), manifest)
    r = json.loads(json.dumps(rules))
    del r["perf"]["workloads"]["w10"]
    with pytest.raises(ValueError, match="w10"):
        perf_workloads.load(r, manifest)


def test_profiles_place_only_on_declared_machines_and_say_not_run_otherwise():
    """perf-sweep.source.machines"""
    rules = _rules()
    m4 = perf_workloads.machine_tags(rules)["m4air"]
    assert {"profile", "gui"} <= set(m4["tags"]) and m4["sudo"] == ["py-spy"]
    # only the M4 is declared to profile; nothing is placed on the manager's Mac or on a machine that does not say so
    assert [n for n, m in perf_workloads.machine_tags(rules).items() if "profile" in m["tags"]] == ["m4air"]
    assert perf_workloads.place(rules, "engine") == ("m4air", None)
    assert perf_workloads.place(rules, "app") == ("m4air", None)
    assert perf_workloads.py_spy_allowed(rules, "m4air") and not perf_workloads.py_spy_allowed(rules, "imac")

    def only(tags):
        r = json.loads(json.dumps(rules))
        r["perf"]["machines"] = {"m4air": {"tags": tags}}
        return r

    # a profile machine without gui: engine profiles run, app profiles are not-run
    assert perf_workloads.place(only(["pytest", "profile"]), "engine") == ("m4air", None)
    assert perf_workloads.place(only(["pytest", "profile"]), "app") == (None, "not-run: no GUI machine")
    with pytest.raises(ValueError, match="profile"):
        perf_workloads.place(only(["pytest", "gui"]), "engine")


def test_install_corpus_is_a_builder_verb_that_refuses_a_mismatch(tmp_path, capsys):
    """perf-sweep.workload.corpus: the verb is wired and its refusal is a nonzero exit naming the corpus."""
    from fichero_builder import __main__ as cli

    manifest = tmp_path / "perf_corpus.json"
    src = tmp_path / "src.txt"
    src.write_text("one page\n")
    good = {"name": "tiny", "kind": "repo", "licence": "AGPL-3.0-only", "source": "src.txt", "file": "src.txt", "pages": 1,
            "sha256": __import__("hashlib").sha256(b"one page\n").hexdigest()}
    manifest.write_text(json.dumps({"corpora": [good]}))
    held = tmp_path / "held"
    argv = ["install", "--corpus", "--manifest", str(manifest), "--root", str(tmp_path), "--dest", str(held)]
    assert cli.main(argv) == 0
    assert (held / f"tiny-{good['sha256'][:12]}" / "src.txt").read_text() == "one page\n"
    src.write_text("another page\n")
    manifest.write_text(json.dumps({"corpora": [good]}))
    rc = cli.main(argv)
    assert rc != 0 and "tiny" in capsys.readouterr().out


# --- Step 4 (#6614): engine profiles nightly ----------------------------------------------------------------------------------------

from fichero_builder import perf_profiles  # noqa: E402

PYI = json.dumps({"root_frame": {"function": "<module>", "file_path_short": "driver.py", "line_no": 1, "time": 10.0, "children": [
    {"function": "import_page", "file_path_short": "fichero_server/import/page.py", "line_no": 40, "time": 7.0, "children": [
        {"function": "execute", "file_path_short": "duckdb/__init__.py", "line_no": 9, "time": 3.0, "children": []},
        {"function": "decode", "file_path_short": "fichero_server/core/codec.py", "line_no": 12, "time": 1.0, "children": []}]},
    {"function": "main", "file_path_short": "fichero_cli/main.py", "line_no": 5, "time": 2.0, "children": []}]}})
MEMRAY = json.dumps({"top_allocations_by_size": [
    {"location": ["load", "fichero_server/models/load.py", 7], "size": 900},
    {"location": ["np_alloc", "numpy/core.py", 3], "size": 5000},
    {"location": ["parse", "fichero_server/core/parse.py", 21], "size": 300}], "top_allocations_by_count": []})
TIME_L = "        12.50 real         9.00 user         2.25 sys\n  734003200  maximum resident set size\n"


def test_engine_profile_readers_rank_own_frames_allocators_disk_and_cpu_efficiency():
    frames = perf_profiles.read_pyinstrument(PYI)
    # ours only (duckdb and the driver are not), ranked by self time; share against the root's 10 s
    assert [f["where"].split(" ")[0] for f in frames] == ["import_page", "main", "decode"]
    assert frames[0]["self_ms"] == 3000.0 and frames[0]["total_ms"] == 7000.0 and frames[0]["share"] == pytest.approx(0.3)
    assert len(perf_profiles.read_pyinstrument(PYI, n=1)) == 1

    allocs = perf_profiles.read_memray_stats(MEMRAY)
    assert [a["where"].split(" ")[0] for a in allocs] == ["load", "parse"] and allocs[0]["bytes"] == 900  # ours, by peak bytes

    t = perf_profiles.read_time_l(TIME_L)
    assert t == {"wall_s": 12.5, "cpu_s": 11.25, "cpu_per_wall": pytest.approx(0.9), "peak_rss_mb": pytest.approx(700.0)}
    with pytest.raises(ValueError):
        perf_profiles.read_time_l("nothing")

    d = perf_profiles.disk_deltas("100\t/g/library\n50\t/g/log\n", "180\t/g/library\n50\t/g/log\n")
    assert d == {"/g/library": 80, "/g/log": 0}
    assert perf_profiles.disk_deltas("100\t/g/library\n", "90\t/g/library\n") == {"/g/library": -10}  # held exactly, not clamped

    rows = perf_profiles.rows_for("w1", PYI, MEMRAY, TIME_L, d, run="r1", machine_model="m", profiler="pyinstrument")
    kinds = {(r["kind"], r["where"].split(" ")[0]) for r in rows}
    assert ("time", "import_page") in kinds and ("ram", "load") in kinds and ("disk", "/g/library") in kinds
    assert ("efficiency", "w1") in kinds and ("cpu", "w1") in kinds and ("ram", "w1") in kinds
    assert all(r["side"] == "engine" and r["workload"] == "w1" for r in rows)


@pytest.fixture(autouse=True)
def _journal_state(monkeypatch, tmp_path):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")


def _fake_rules(sudo=("py-spy",), min_free_gb=5):
    r = _rules()
    r["perf"]["machines"]["m4air"]["sudo"] = list(sudo)
    r["machines"]["m4air"]["min_free_gb"] = min_free_gb
    return r


class _Runner:
    """Records every command line; writes the fixture outputs a real profiler would, so no profiler or engine ever runs."""

    def __init__(self, fail=None, sudo_ok=True):
        self.calls, self.fail, self.sudo_ok = [], fail or {}, sudo_ok
        self.du = 100

    def __call__(self, argv, *, timeout, env=None, cwd=None, attach=None):
        assert isinstance(argv, list) and (attach is None or isinstance(attach, list)), "an argument list, never a shell string"
        cmd = shlex.join(argv) if attach is None else shlex.join(attach) + " -- " + shlex.join(argv)
        self.calls.append({"cmd": cmd, "argv": argv, "timeout": timeout, "env": env, "attach": attach})
        if argv[:2] == ["du", "-sk"]:
            self.du += 10
            return 0, "".join(f"{self.du}\t{p}\n" for p in argv[2:]), ""
        if argv[:4] == ["sudo", "-n", "-l", argv[3]] and len(argv) == 4:
            return (0 if self.sudo_ok else 1), "", ""
        for w, rc in self.fail.items():
            if f"/{w}." in cmd or f"-{w}-" in cmd:
                return rc, "", "boom"
        for out in re.findall(r"-o ('[^']+'|\S+)", cmd):
            p = Path(shlex.split(out)[0])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(PYI if p.suffix == ".json" and "pyinstrument" in p.name else MEMRAY if p.name.endswith("memray.json") else "x")
        return 0, "", TIME_L if "/usr/bin/time" in argv else ""


def _nightly(tmp_path, runner, rules=None, free_gb=500, **kw):
    journal.STATE.mkdir(exist_ok=True)
    gate = tmp_path / "Dev Disk" / "gate"
    return perf_profiles.nightly(rules or _fake_rules(), _manifest(), gate=gate, state=journal.STATE, run="n1", machine="m4air",
                                 runner=runner, free_gb=lambda p: free_gb, machine_model="Mac16,1", **kw)


def test_the_nightly_runs_one_workload_at_a_time_w2_last_with_its_own_budget_and_quotes_every_path(tmp_path):
    runner = _Runner()
    out = _nightly(tmp_path, runner)
    profiled = [c["cmd"] for c in runner.calls if "pyinstrument" in c["cmd"] or "py-spy record" in c["cmd"]]
    assert len(profiled) == 5 and "test_dense_page_whole_read_perf" in profiled[-1]  # w2 last
    table = {w["name"]: w for w in perf_workloads.load(_rules(), _manifest())}
    for c in runner.calls:
        if "test_dense_page_whole_read_perf" in c["cmd"]:
            assert c["timeout"] == table["w2"]["budget_s"]
        if "test_search_workload_perf" in c["cmd"]:
            assert c["timeout"] == table["w3"]["budget_s"]
    for c in runner.calls:  # every tmp path under the gate with a space is quoted; none under a home dir
        assert "/Users/" not in c["cmd"]
        for m in re.finditer(r"\S*Dev Disk\S*", c["cmd"]):
            assert "'" in c["cmd"][max(0, m.start() - 1):m.start() + 1] or c["cmd"][m.start() - 1] == "'"
    assert (tmp_path / "state" / "perf" / "latest.json").is_file()
    assert {r["workload"] for r in out["rows"]} >= {"w1", "w5"}


def test_a_full_disk_refuses_before_running_and_a_failed_workload_is_a_not_run_row_not_a_stop(tmp_path):
    runner = _Runner()
    out = _nightly(tmp_path, runner, free_gb=1)
    assert runner.calls == [] and out["rows"][0]["where"].startswith("not-run") and "free" in out["rows"][0]["detail"]["reason"]
    runner = _Runner(fail={"w3": 1})
    out = _nightly(tmp_path, runner)
    assert any(r["workload"] == "w3" and r["where"].startswith("not-run") for r in out["rows"])
    assert any(r["workload"] == "w4" and r["kind"] == "efficiency" for r in out["rows"])  # the next workload still ran


def test_a_machine_without_sudo_py_spy_never_spawns_it_and_a_missing_sudoers_line_is_said_in_a_row(tmp_path):
    runner = _Runner()
    _nightly(tmp_path, runner, rules=_fake_rules(sudo=()))
    assert not any("py-spy" in c["cmd"] for c in runner.calls)
    assert perf_profiles.choose_profiler(_fake_rules(sudo=()), "m4air", sudo_ok=lambda: True) == ("pyinstrument", None)
    assert perf_profiles.choose_profiler(_fake_rules(), "m4air", sudo_ok=lambda: True) == ("py-spy", None)
    assert perf_profiles.choose_profiler(_fake_rules(), "m4air", sudo_ok=lambda: False) == ("pyinstrument", "py-spy: the sudoers line is not on the machine")

    runner = _Runner(sudo_ok=False)
    out = _nightly(tmp_path, runner)
    assert not any("py-spy record" in c["cmd"] for c in runner.calls)
    assert any("sudoers" in json.dumps(r["detail"]) for r in out["rows"])

    runner = _Runner()
    _nightly(tmp_path, runner)
    spy = [c["cmd"] for c in runner.calls if "py-spy record" in c["cmd"]]
    assert len(spy) == 5 and all(c.startswith("sudo -n ") and "--subprocesses" in c and "--format speedscope" in c for c in spy)


def test_no_shell_no_root_workload_a_minimal_env_the_engine_pointed_at_the_measured_folders_and_the_run_cleaned_up(tmp_path):
    runner = _Runner()
    gate = tmp_path / "Dev Disk" / "gate"
    for old in ("old1", "old2", "old3"):  # earlier runs: only the newest few stay
        (gate / "perf" / old).mkdir(parents=True)
        (gate / "perf" / old / "x.bin").write_text("x")
        os.utime(gate / "perf" / old, (1, int(old[-1])))
    out = _nightly(tmp_path, runner, keep=2)
    assert sorted(p.name for p in (gate / "perf").iterdir()) == ["n1", "old3"]
    assert not list((gate / "perf" / "n1").glob("*.bin")) and not (gate / "perf" / "n1" / "tmp").exists()
    assert (gate / "perf" / "n1" / "w1.memray.json").is_file()
    spy = [c for c in runner.calls if c["attach"]]
    assert len(spy) == 5 and all(c["argv"][:2] == ["/usr/bin/time", "-l"] and c["attach"][:3] == ["sudo", "-n", "py-spy"] for c in spy)
    assert not any(c["argv"][0] == "sudo" for c in runner.calls if c["attach"])  # the workload itself never runs under sudo
    for c in runner.calls:
        if c["env"]:
            assert set(c["env"]) <= {"PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV", "TMPDIR", "FICHERO_BASE_PATH", "FICHERO_LIBRARY_PATH",
                                     "FICHERO_ENGINE_LOG_PATH", "FICHERO_MODEL_STORE_ROOT"}
            assert c["env"]["FICHERO_LIBRARY_PATH"].startswith(str(gate / "perf" / "n1" / "state"))
    # the folders `du` reads are the ones the engine is pointed at
    du = [c for c in runner.calls if c["argv"][:2] == ["du", "-sk"]][0]["argv"][2:]
    env = next(c["env"] for c in runner.calls if c["env"])
    assert env["FICHERO_LIBRARY_PATH"] in du and env["FICHERO_BASE_PATH"] in du
    assert all(len(c["argv"]) > 2 for c in runner.calls if c["argv"][:2] == ["du", "-sk"])  # never a bare `du -sk`
    assert any(r["kind"] == "disk" for r in out["rows"])


def test_the_real_runner_takes_an_argument_list_and_never_a_shell():
    assert perf_profiles.real_runner(["echo", "a b; echo c"], timeout=10) == (0, "a b; echo c\n", "")
    with pytest.raises(TypeError):
        perf_profiles.real_runner("echo hi", timeout=10)


def test_the_temp_folder_goes_after_every_workload_and_a_missing_child_pid_is_never_attached(tmp_path, monkeypatch):
    seen = []

    class Leaky(_Runner):
        def __call__(self, argv, **kw):
            if kw.get("env"):
                tmp = Path(kw["env"]["TMPDIR"])
                seen.append(sorted(p.name for p in tmp.iterdir()))  # what an earlier workload left behind
                (tmp / f"leak-{len(seen)}").write_text("x")
            return super().__call__(argv, **kw)

    _nightly(tmp_path, Leaky())
    # two env-carrying calls a workload (the profiled run, then memray): the first of each finds the temp folder empty
    assert len(seen) == 10 and all(names == [] for names in seen[0::2])
    assert not (tmp_path / "Dev Disk" / "gate" / "perf" / "n1" / "tmp").exists()

    monkeypatch.setattr(perf_profiles, "_child_pid", lambda pid: None)
    rc, _o, err = perf_profiles.real_runner(["sleep", "5"], timeout=10, attach=["true"])
    assert rc == 125 and "not found" in err


def test_after_nightly_perf_state_holds_nothing_but_the_shared_models(tmp_path, monkeypatch):
    monkeypatch.delenv("FICHERO_MODEL_STORE_ROOT", raising=False)
    runner = _Runner()
    _nightly(tmp_path, runner, keep=1)
    _nightly(tmp_path, runner, keep=1)
    gate = tmp_path / "Dev Disk" / "gate"
    assert [p.name for p in (gate / "perf-state").iterdir() if p.name != "models"] == []
    assert not (gate / "perf-state" / "library").exists()


def test_a_timed_out_workload_takes_its_whole_process_group_with_it(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    rc, _o, err = perf_profiles.real_runner(["sh", "-c", f"sleep 30 & echo $! > '{pidfile}'; wait"], timeout=1)
    assert rc == 124 and "timed out" in err
    pid = int(pidfile.read_text())
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        raise AssertionError("the grandchild of a timed-out workload is still running")
