#!/usr/bin/env python3
"""One standard engine perf run on the runner, and its verdict (#6600, Step 2.30, `dev-workflows.quality.perf-rung-engine`).

    python scripts/perf_engine_run.py --baseline scripts/perf_baseline.json [--tests fichero-server/tests/perf] [--dir PATH ...]

Runs pytest-benchmark's suite under pyinstrument (time profile) and `/usr/bin/time -l` (peak RSS), takes `du -sk` of the scratch
library, cache, log and models dirs before and after, then hands the three tools' OUTPUT to `fichero_builder.perf_rung` and prints one
`PERF-RESULT {json}` line (last). Exit 0 whatever the verdict: the rung decides what a red means (report-only until measured). No
timer is written here; the tools measure. Never run on the manager's Mac: the rung ships it to `[check].build_remote`."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fichero-builder"))
from fichero_builder import perf_rung  # noqa: E402


def sh(argv, **kw) -> str:
    return subprocess.run(argv, capture_output=True, text=True, **kw).stdout


def thermal() -> str | None:
    """`pmset -g therm` on the runner: 'nominal' when it reports no CPU limit, else 'fair' or worse by its speed-limit figure."""
    out = sh(["pmset", "-g", "therm"])
    if not out:
        return None
    if "CPU_Speed_Limit" not in out and "No thermal warning level" in out or "No CPU power status" in out:
        return "nominal"
    for line in out.splitlines():
        if "CPU_Speed_Limit" in line:
            limit = int(line.split("=")[-1])
            return "nominal" if limit >= 100 else "fair" if limit >= 80 else "serious"
    return "nominal"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=perf_rung.BASELINE)
    ap.add_argument("--tests", default="fichero-server/tests/perf")
    ap.add_argument("--dir", action="append", default=[], help="a directory whose `du -sk` is held before and after (scratch library, cache, logs, models)")
    ap.add_argument("--declared", default="{}", help='JSON {dir: KiB} the run declares it writes (the fixture library\'s own growth)')
    a = ap.parse_args()
    baseline = json.loads((ROOT / a.baseline).read_text())
    out = Path(tempfile.mkdtemp(prefix="perf-"))
    dirs = [d for d in a.dir if os.path.isdir(d)]
    du = lambda: perf_rung.read_du(sh(["du", "-sk", *dirs])) if dirs else {}  # noqa: E731
    before = du()
    pytest = [sys.executable, "-m", "pytest", a.tests, "-p", "pytest_benchmark", f"--benchmark-json={out / 'bench.json'}", "--benchmark-warmup=on",
              "--benchmark-min-rounds=3", "-q"]
    argv = ["/usr/bin/time", "-l", sys.executable, "-m", "pyinstrument", "-r", "json", "-o", str(out / "profile.json"), "-m", "pytest", *pytest[3:]]
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "fichero-server/src"})
    after = du()
    figs: dict = {"benchmarks": {}, "peak_rss_mb": None, "disk_kib": {}, "top": []}
    notes = []
    try:
        figs["benchmarks"] = perf_rung.read_benchmarks((out / "bench.json").read_text())
    except OSError:
        notes.append("REFUSED: no pytest-benchmark JSON was written (pytest-benchmark missing or the run died)")
    try:
        figs["peak_rss_mb"] = perf_rung.read_peak_rss_mb(r.stderr)
    except ValueError as e:
        notes.append(f"REFUSED: {e}")
    try:
        figs["top"] = perf_rung.top_self_frames((out / "profile.json").read_text())
    except (OSError, ValueError, KeyError):
        notes.append("REFUSED: no pyinstrument profile (pyinstrument missing)")
    figs["disk_kib"] = perf_rung.disk_delta(before, after, json.loads(a.declared)) if dirs else {}
    figs["written_kib"] = float(sum(max(0, after[d] - before[d]) for d in before)) if dirs else None  # net growth of the watched dirs: what the workload added, declared output included
    model = sh(["sysctl", "-n", "hw.model"]).strip()
    verdict = perf_rung.judge(figs, baseline, model, thermal(), idle=os.getloadavg()[0] < 2.0, root=ROOT)
    if notes:
        verdict = {**verdict, "ok": False, "reds": [*notes, *verdict["reds"]]}
    if verdict.get("recorded") and not notes:
        # a baseline with no figure for these keys: WRITE them (report-only; a first measurement is recorded, never a fail)
        baseline["figures"] = {**(baseline.get("figures") or {}), **verdict["recorded"]}
        (ROOT / a.baseline).write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"pytest exit {r.returncode}", file=sys.stderr)
    print(perf_rung.result_line(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
