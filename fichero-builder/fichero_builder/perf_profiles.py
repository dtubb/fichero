"""Engine profiles, nightly (#6614, `perf-sweep.source.engine-profiles`; spec harness/performance-sweep.md).

Platform tools measure, we only read: pyinstrument (or py-spy), memray, `du` and `/usr/bin/time -l` write their outputs and the
readers below turn those into perf rows. The nightly driver runs one workload at a time behind the heavy lock, W2 last with its own
budget, under the gate dir on the Dev Disk (never the M4's nearly full internal disk), and refuses before running when free space is
short. Nothing here is run by a test: the tests hand the driver a fake runner and fixture outputs (#5188)."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from fichero_builder import journal, perf_rung, perf_sweep, perf_workloads

OWN = ("fichero_server/", "fichero_cli/", "fichero_mcp/")
TOP_FRAMES = 15
TOP_ALLOCS = 10
DIRS = ("library", "cache", "log", "models")  # the `du` pairs of perf-rung-engine
MIN_FREE_GB = 5
KEEP_RUNS = 7  # run folders kept under the gate dir
ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV")  # all a profiled driver inherits


def _own(path: str) -> bool:
    return any(o in (path or "") for o in OWN)


# --- readers over tool outputs ---------------------------------------------------------------------------------------------------------

def read_pyinstrument(text: str, n: int = TOP_FRAMES) -> list[dict]:
    """Our frames only (fichero_server, fichero_cli, fichero_mcp), ranked by self time; share is against the root's time."""
    root = json.loads(text)["root_frame"]
    total = float(root.get("time", 0.0))
    acc: dict[str, dict] = {}

    def walk(f: dict) -> None:
        kids = f.get("children") or []
        path = f.get("file_path_short") or f.get("file_path") or ""
        if _own(path):
            key = f"{f.get('function')} ({path}:{f.get('line_no')})"
            e = acc.setdefault(key, {"where": key, "self_ms": 0.0, "total_ms": 0.0})
            e["self_ms"] += max(0.0, float(f.get("time", 0.0)) - sum(float(k.get("time", 0.0)) for k in kids)) * 1000
            e["total_ms"] += float(f.get("time", 0.0)) * 1000
        for k in kids:
            walk(k)

    walk(root)
    out = sorted(acc.values(), key=lambda e: -e["self_ms"])[:n]
    for e in out:
        e["self_ms"], e["total_ms"] = round(e["self_ms"], 3), round(e["total_ms"], 3)
        e["share"] = round(e["self_ms"] / (total * 1000), 4) if total > 0 else None
    return out


def read_speedscope(text: str, n: int = TOP_FRAMES) -> list[dict]:
    """The same rows from py-spy's speedscope file (sampled profiles: the leaf of each sample is self time)."""
    doc = json.loads(text)
    frames = doc["shared"]["frames"]
    self_t: dict[int, float] = {}
    tot_t: dict[int, float] = {}
    total = 0.0
    for prof in doc["profiles"]:
        if prof.get("type") != "sampled":
            continue
        mult = 1000.0 if prof.get("unit") == "seconds" else 1.0
        for stack, w in zip(prof["samples"], prof["weights"]):
            w *= mult
            total += w
            if stack:
                self_t[stack[-1]] = self_t.get(stack[-1], 0.0) + w
            for i in set(stack):
                tot_t[i] = tot_t.get(i, 0.0) + w
    out = []
    for i, t in self_t.items():
        f = frames[i]
        if _own(f.get("file", "")):
            out.append({"where": f"{f.get('name')} ({f.get('file')}:{f.get('line')})", "self_ms": round(t, 3),
                        "total_ms": round(tot_t[i], 3), "share": round(t / total, 4) if total > 0 else None})
    return sorted(out, key=lambda e: -e["self_ms"])[:n]


def read_memray_stats(text: str, n: int = TOP_ALLOCS) -> list[dict]:
    """Our allocation sites from `memray stats --json`, by bytes (largest first)."""
    rows = []
    for a in json.loads(text).get("top_allocations_by_size", []):
        loc = a.get("location")
        func, file, line = loc if isinstance(loc, (list, tuple)) else (str(loc), "", 0)
        if _own(file):
            rows.append({"where": f"{func} ({file}:{line})", "bytes": int(a.get("size", 0))})
    return sorted(rows, key=lambda r: -r["bytes"])[:n]


_TIME = re.compile(r"^\s*([\d.]+)\s+real\s+([\d.]+)\s+user\s+([\d.]+)\s+sys", re.M)


def read_time_l(text: str) -> dict:
    """wall, CPU (user + sys), CPU/wall and peak RSS from `/usr/bin/time -l`. Unreadable is ValueError, never a zero."""
    m = _TIME.search(text)
    if not m:
        raise ValueError("no 'real user sys' line in the /usr/bin/time -l output")
    wall, cpu = float(m.group(1)), float(m.group(2)) + float(m.group(3))
    return {"wall_s": wall, "cpu_s": round(cpu, 3), "cpu_per_wall": round(cpu / wall, 4) if wall > 0 else None,
            "peak_rss_mb": perf_rung.read_peak_rss_mb(text)}


def disk_deltas(before: str, after: str) -> dict[str, int]:
    """KiB per directory, after minus before, held exactly (a fall is a negative number, not a zero)."""
    b, a = perf_rung.read_du(before), perf_rung.read_du(after)
    if set(b) != set(a):
        raise ValueError(f"`du` read different directories before and after: {sorted(set(b) ^ set(a))}")
    return {d: a[d] - b[d] for d in b}


def rows_for(w: str, frames_text: str | None, memray_text: str | None, time_text: str | None, deltas: dict[str, int], *, run, machine_model,
             profiler: str, profile: str = "") -> list[dict]:
    """The perf rows of one workload: top own frames, top own allocation sites, one row per directory, and the workload's wall, CPU,
    CPU/wall and peak RSS. Each part is optional, so a tool that gave nothing leaves its rows out and the caller says why."""
    base = dict(run=run, machine_model=machine_model, workload=w, side="engine", profile=profile)
    rows = []
    if frames_text:
        reader = read_speedscope if profiler == "py-spy" else read_pyinstrument
        for f in reader(frames_text):
            rows.append(perf_sweep.make_row(**base, where=f["where"], kind="time", value=f["self_ms"], unit="ms", share=f["share"],
                                            source=profiler, detail={"total_ms": f["total_ms"]}))
    if memray_text:
        allocs = read_memray_stats(memray_text)
        peak = max((a["bytes"] for a in allocs), default=0)
        for a in allocs:
            rows.append(perf_sweep.make_row(**base, where=a["where"], kind="ram", value=a["bytes"], unit="B",
                                            share=round(a["bytes"] / peak, 4) if peak else None, source="memray"))
    for d, kib in deltas.items():
        rows.append(perf_sweep.make_row(**base, where=d, kind="disk", value=kib, unit="KiB", source="du"))
    if time_text:
        t = read_time_l(time_text)
        rows += [perf_sweep.make_row(**base, where=f"{w} wall", kind="time", value=t["wall_s"], unit="s", source="time-l"),
                 perf_sweep.make_row(**base, where=f"{w} cpu", kind="cpu", value=t["cpu_s"], unit="s", source="time-l"),
                 perf_sweep.make_row(**base, where=f"{w} cpu/wall", kind="efficiency", value=t["cpu_per_wall"] or 0.0, unit="ratio",
                                     source="time-l", detail={"profiler": profiler}),
                 perf_sweep.make_row(**base, where=f"{w} peak rss", kind="ram", value=round(t["peak_rss_mb"], 1), unit="MB", source="time-l")]
    return rows


# --- which profiler -------------------------------------------------------------------------------------------------------------------

def choose_profiler(rules: dict, machine: str, sudo_ok) -> tuple[str, str | None]:
    """py-spy only where the machine DECLARES `sudo = ["py-spy"]` (never probed by trying) and its sudoers line is really there;
    declared but missing is said (the reason), and the run falls back to pyinstrument. We never install or change sudoers."""
    if not perf_workloads.py_spy_allowed(rules, machine):
        return "pyinstrument", None
    if not sudo_ok():
        return "pyinstrument", "py-spy: the sudoers line is not on the machine"
    return "py-spy", None


# --- the nightly driver ---------------------------------------------------------------------------------------------------------------

def _child_pid(pid: int) -> int | None:
    """The workload under `/usr/bin/time` (time forks it), so py-spy attaches to python and not to time."""
    for _ in range(40):
        got = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
        if got:
            return int(got[0])
        time.sleep(0.25)
    return None  # never attach root to a pid that is not the workload's (it may have exited and been reused)


def real_runner(argv: list[str], *, timeout, env=None, cwd=None, attach: list[str] | None = None) -> tuple[int, str, str]:
    """Run an argument LIST (never a shell string). With `attach` (the `sudo -n py-spy record ...` prefix), the workload starts as this
    user and root is used only to attach to its pid, so the workload never runs as root."""
    if not isinstance(argv, list):
        raise TypeError("a command is an argument list, never a shell string")
    if attach is None:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"timed out after {timeout} s"
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=cwd, start_new_session=True)
    child = _child_pid(proc.pid)
    if child is None:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return 125, "", "py-spy: the workload's process was not found, so nothing was attached"
    spy = subprocess.Popen([*attach, "--pid", str(child)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        spy.kill()
        spy.communicate()
        return 124, "", f"timed out after {timeout} s"
    try:
        _o, spy_err = spy.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        spy.kill()
        _o, spy_err = spy.communicate()
    rc = proc.returncode or (spy.returncode if spy.returncode else 0)
    return rc, out, err + (f"\npy-spy: {spy_err.strip()}" if spy_err.strip() else "")


def real_free_gb(path) -> float:
    return shutil.disk_usage(path).free / 1e9


def _python_argv(driver: str) -> list[str]:
    """`pytest a b` becomes `python -m pytest a b`; `python x.py` stays."""
    t = shlex.split(driver)
    return ["python", "-m", *t] if t and t[0] == "pytest" else t


def _target(drv: list[str]) -> list[str]:
    """The driver as the `-m mod args` or `script args` tail pyinstrument and memray take."""
    return drv[1:]


def _not_run(w, reason, **base) -> dict:
    return perf_sweep.make_row(**base, workload=w, side="engine", where=f"not-run: {w}", kind="time", value=0.0, unit="s",
                               source="engine-profile", detail={"reason": reason})


def nightly(rules: dict, manifest: dict, *, gate, state, run: str, machine: str, machine_model: str, runner=real_runner,
            free_gb=real_free_gb, only=None, cwd=None, sudo_ok=None, py_spy: str = "py-spy", keep: int = KEEP_RUNS) -> dict:
    """Profile the engine workloads one at a time, w2 last, each behind the heavy lock and inside its own `budget_s`. A workload that
    fails or times out is a `not-run` row and the next one still runs; a disk under the machine's `min_free_gb` refuses before any
    run. Commands are argument lists, never shell strings. Profiles and temp live under the gate dir's `perf` folder for this run;
    the memray `.bin` and the temp folder go once their reports are written, and only the newest `keep` run folders stay."""
    gate = Path(gate)
    table = [w for w in perf_workloads.load(rules, manifest) if w["side"] == "engine" and (not only or w["name"] in only)]
    table.sort(key=lambda w: w["name"] == "w2")
    base = dict(run=run, machine_model=machine_model)
    min_free = (rules.get("machines", {}).get(machine) or {}).get("min_free_gb", MIN_FREE_GB)
    rows: list[dict] = []
    notes: list[str] = []
    gate.mkdir(parents=True, exist_ok=True)
    if (free := free_gb(gate)) < min_free:  # before anything runs, the sudoers check included
        reason = f"only {free:.1f} GB free under the gate dir, {min_free} GB needed: refused before running"
        return perf_sweep.write_rows([_not_run("engine", reason, **base)], run=run, machine_model=machine_model, state=state,
                                     notes=[f"not-run: {reason}"])
    sudo_ok = sudo_ok or (lambda: runner(["sudo", "-n", "-l", py_spy], timeout=30)[0] == 0)
    profiler, why = choose_profiler(rules, machine, sudo_ok)
    notes.append(f"profiler: {profiler}")
    if why:
        notes.append(why)
        rows.append(_not_run("engine", why, **base))
    run_dir = gate / "perf" / run
    run_dir.mkdir(parents=True, exist_ok=True)
    models = Path(os.environ.get("FICHERO_MODEL_STORE_ROOT") or gate / "perf-state" / "models")  # the one shared folder
    inherited = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    for w in table:
        n = w["name"]
        free = free_gb(gate)
        if free < min_free:
            reason = f"only {free:.1f} GB free under the gate dir, {min_free} GB needed: refused before running"
            notes.append(f"not-run: {reason}")
            rows.insert(0, _not_run(n, reason, **base))
            break
        (run_dir / "tmp").mkdir(parents=True, exist_ok=True)
        try:
            # library, base and log live in this workload's own folder under the run, so `_prune` bounds them and a `du` delta never
            # holds an older run's data; only the model store is shared
            st = run_dir / "state" / n
            where = {"library": st / "library", "cache": st / "base", "log": st / "log", "models": models}
            env = {**inherited, "TMPDIR": str(run_dir / "tmp")}
            env.update(FICHERO_BASE_PATH=str(where["cache"]), FICHERO_LIBRARY_PATH=str(where["library"]),
                       FICHERO_ENGINE_LOG_PATH=str(where["log"] / "engine.log"), FICHERO_MODEL_STORE_ROOT=str(models))
            for p in where.values():
                p.mkdir(parents=True, exist_ok=True)
            dirs = [str(where[d]) for d in DIRS if d in w["outputs"]]
            du = ["du", "-sk", *dirs] if dirs else None  # no declared folder: no `du` at all (a bare `du -sk` reads the current folder)
            drv = _python_argv(w["drivers"][0])
            out = {k: run_dir / f"{n}.{k}" for k in ("pyinstrument.json", "html", "speedscope", "bin", "memray.json", "memray.html")}
            timed = ["/usr/bin/time", "-l"]
            with journal.heavy(f"perf profile {n}"):
                before = runner(du, timeout=120)[1] if du else ""
                if profiler == "py-spy":
                    # the workload starts as this user; root only attaches to its pid (`--pid` is added by the runner)
                    cmd, attach = [*timed, *drv], ["sudo", "-n", py_spy, "record", "--format", "speedscope", "-o", str(out["speedscope"]),
                                                   "--subprocesses"]
                    rc, _o, err = runner(cmd, timeout=w["budget_s"], env=env, cwd=cwd, attach=attach)
                else:
                    cmd = [*timed, "pyinstrument", "-r", "json", "-o", str(out["pyinstrument.json"]), "-r", "html", "-o", str(out["html"]),
                           *_target(drv)]
                    rc, _o, err = runner(cmd, timeout=w["budget_s"], env=env, cwd=cwd)
                if rc != 0:
                    notes.append(f"{n}: not-run (exit {rc})")
                    rows.append(_not_run(n, f"the profiled run exited {rc}: {err.strip()[-300:]}", **base))
                    continue
                mrc, _o, merr = runner(["memray", "run", "--native", "--follow-fork", "-f", "-o", str(out["bin"]), *_target(drv)],
                                       timeout=w["budget_s"], env=env, cwd=cwd)
                memray_text = None
                if mrc == 0:
                    runner(["memray", "stats", "--json", "-f", "-o", str(out["memray.json"]), str(out["bin"])], timeout=300)
                    runner(["memray", "flamegraph", "-f", "-o", str(out["memray.html"]), str(out["bin"])], timeout=300)
                    memray_text = _read(out["memray.json"])
                else:
                    rows.append(_not_run(n, f"memray run exited {mrc}: {merr.strip()[-300:]}", **base))
                out["bin"].unlink(missing_ok=True)  # hundreds of MB to GB: the stats and the flamegraph are what is kept
                after = runner(du, timeout=120)[1] if du else ""
            frames = _read(out["speedscope"] if profiler == "py-spy" else out["pyinstrument.json"])
            try:
                deltas = disk_deltas(before, after)
            except ValueError as e:
                deltas = {}
                rows.append(_not_run(n, f"disk: {e}", **base))
            prof = str(out["speedscope"] if profiler == "py-spy" else out["html"])
            for part, args in (("time", (frames, None, None, {})), ("ram", (None, memray_text, None, {})), ("disk", (None, None, None, deltas)),
                               ("cpu", (None, None, err, {}))):
                try:
                    rows += rows_for(n, *args, **base, profiler=profiler, profile=prof)
                except (ValueError, KeyError, json.JSONDecodeError) as e:
                    rows.append(_not_run(n, f"the {part} output was unreadable: {e}", **base))
        finally:
            shutil.rmtree(run_dir / "tmp", ignore_errors=True)  # after EVERY workload, a crash included
    _prune(gate / "perf", keep, current=run)
    return perf_sweep.write_rows(rows, run=run, machine_model=machine_model, state=state, notes=notes)


def _prune(perf_dir: Path, keep: int, current: str) -> None:
    """Keep the newest `keep` run folders (the current one always); remove only plain child folders of the gate's perf dir."""
    runs = sorted((d for d in perf_dir.iterdir() if d.is_dir() and not d.is_symlink() and d.name != current), key=lambda d: d.stat().st_mtime,
                  reverse=True)
    for d in runs[max(0, keep - 1):]:
        shutil.rmtree(d, ignore_errors=True)


def _read(p: Path) -> str | None:
    try:
        return Path(p).read_text()
    except OSError:
        return None


def main(a) -> int:
    import tomllib

    root = Path(a.root)
    rules = tomllib.loads((root / "harness.toml").read_text())
    manifest = json.loads((root / "scripts" / "perf_corpus.json").read_text())
    try:
        m, why = perf_workloads.place(rules, "engine")
    except ValueError as e:
        print(e)
        return 2
    machine = a.machine or m
    if "profile" not in perf_workloads.machine_tags(rules).get(machine, {}).get("tags", []):
        print(why or f"{machine} is not declared a `profile` machine")
        return 2
    state = Path(a.state) if a.state else journal.STATE
    run = a.run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    only = a.workload.split(",") if a.workload not in ("", "logs") else None
    out = nightly(rules, manifest, gate=a.gate, state=state, run=run, machine=machine, machine_model=a.machine_model or perf_sweep._model(),
                  only=only, cwd=root, py_spy=shutil.which("py-spy") or "py-spy")  # the sudoers line names the full path
    print(f"run {run}: {len(out['rows'])} rows; " + "; ".join(out["notes"]))
    return 1 if any(r["where"].startswith("not-run") for r in out["rows"]) else 0
