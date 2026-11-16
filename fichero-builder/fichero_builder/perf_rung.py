"""The engine half of the `perf` rung (#6600, Step 2.30, `dev-workflows.quality.perf-rung-engine`).

Pure readers and judges over the OUTPUT of the three tools (pytest-benchmark's JSON, `/usr/bin/time -l`, pyinstrument's JSON) and
`du -sk` pairs. Nothing here measures, and no judge is written: the decision is `scripts/perf_trial.py`'s (`compare`), the tolerances
are the baseline file's. `scripts/perf_engine_run.py` runs the tools on the runner; `check_tool.perf` applies these."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ENGINE_PATHS = ("fichero-server/", "fichero-cli/", "fichero-mcp/", "pipeline/")
APP_PATHS = ("fichero/",)
BASELINE = "scripts/perf_baseline.json"
OWN_FRAME = "fichero_server/"  # a frame under this is ours, not a library's


def trial(root: Path | str | None = None):
    """`scripts/perf_trial.py` loaded by path (it is a script, not a package); from `root`'s copy when given."""
    here = Path(root) / "scripts" / "perf_trial.py" if root else Path(__file__).resolve().parents[2] / "scripts" / "perf_trial.py"
    spec = importlib.util.spec_from_file_location("perf_trial", here)
    assert spec and spec.loader
    mod = sys.modules.get("perf_trial") or importlib.util.module_from_spec(spec)
    if "perf_trial" not in sys.modules:
        sys.modules["perf_trial"] = mod
        spec.loader.exec_module(mod)
    return mod


def required(changed: list[str]) -> str:
    """"" when the engine half is owed, else the reason it is not (a "not required" row, like red-on-base's)."""
    if any(f.startswith(ENGINE_PATHS) for f in changed):
        return ""
    return "not required: no changed path is under fichero-server/, fichero-cli/, fichero-mcp/ or pipeline/"


def read_benchmarks(text: str) -> dict[str, float]:
    """{test fullname: median ms} from pytest-benchmark's `--benchmark-json` (stats are in seconds)."""
    return {b["fullname"]: float(b["stats"]["median"]) * 1000 for b in json.loads(text).get("benchmarks", [])}


_RSS = re.compile(r"^\s*(\d+)\s+maximum resident set size", re.M)


def read_peak_rss_mb(time_l_text: str) -> float:
    """Peak resident set size in MB from `/usr/bin/time -l` (macOS prints bytes). Unreadable = ValueError, never a zero."""
    m = _RSS.search(time_l_text)
    if not m:
        raise ValueError("no 'maximum resident set size' line in the /usr/bin/time -l output")
    return int(m.group(1)) / (1024 * 1024)


def disk_delta(before: dict[str, int], after: dict[str, int], declared: dict[str, int] | None = None) -> dict[str, int]:
    """Per directory, KiB left behind (after - before, `du -sk`) minus what the run DECLARES it writes (the fixture library's own
    growth). Only a positive remainder is a leak; a directory missing from either side is a refusal, not a zero."""
    declared = declared or {}
    out = {}
    for d in before:
        if d not in after:
            raise ValueError(f"no `du` reading after the run for {d}")
        out[d] = max(0, after[d] - before[d] - declared.get(d, 0))
    if missing := sorted(set(after) - set(before)):
        raise ValueError(f"no `du` reading before the run for {missing}")
    return out


def read_du(text: str) -> dict[str, int]:
    """{path: KiB} from `du -sk <paths>` output."""
    return {path: int(kib) for kib, path in (line.split(maxsplit=1) for line in text.strip().splitlines() if line.strip())}


def top_self_frames(profile_json: str, n: int = 10) -> list[str]:
    """The top-n frames by SELF time from pyinstrument's JSON renderer (`root_frame` tree: time minus the children's),
    named `function (file:line)`."""
    root = json.loads(profile_json)["root_frame"]
    own: dict[str, float] = {}

    def walk(f: dict) -> None:
        kids = f.get("children") or []
        key = f"{f.get('function')} ({f.get('file_path_short') or f.get('file_path')}:{f.get('line_no')})"
        own[key] = own.get(key, 0.0) + max(0.0, float(f.get("time", 0.0)) - sum(float(k.get("time", 0.0)) for k in kids))
        for k in kids:
            walk(k)

    walk(root)
    return [k for k, _v in sorted(own.items(), key=lambda kv: -kv[1])[:n]]


def new_own_frames(top: list[str], baseline_top: list[str]) -> list[str]:
    """Frames of ours (under fichero_server/) in this top ten and not in the baseline's: a finding to print, never a red."""
    return [f for f in top if OWN_FRAME in f and f not in baseline_top]


def judge(figures: dict, baseline: dict, model: str, thermal: str | None, idle: bool = True, root=None) -> dict:
    """One verdict list over the rung's figures, each already a MEDIAN of the runs the driver took (pytest-benchmark warms up and
    discards its cold rounds). `figures`: {"benchmarks": {name: ms}, "peak_rss_mb": x, "disk_kib": {dir: kib}, "top": [...]}.
    Returns {"ok", "reds", "findings", "falls", "void"}; a thermal state under `fair`, an unreadable one or no machine is VOID or
    REFUSED (a red the caller must show), never a pass."""
    t = trial(root)
    tol = baseline.get("tolerances") or {}
    out = {"ok": True, "reds": [], "findings": [], "falls": [], "void": "", "recorded": {}}
    if not model or thermal not in t.READABLE_THERMAL:
        out["ok"] = False
        out["reds"].append("REFUSED: " + ("no machine model" if not model else "the thermal state could not be read") + ": a gate that cannot read its input fails")
        return out
    if thermal in t.MEASURE_VOID_THERMAL or not idle:
        out["void"] = f"VOID: {'thermal state ' + repr(thermal) if thermal in t.MEASURE_VOID_THERMAL else 'the machine was not idle'}: neither pass nor fail"
        return out
    rows = [("wall_ms", name, v) for name, v in sorted(figures.get("benchmarks", {}).items())]
    if figures.get("peak_rss_mb") is not None:
        rows.append(("peak_rss_mb", "engine perf run", figures["peak_rss_mb"]))
    rows += [("disk_kib", d, v) for d, v in sorted(figures.get("disk_kib", {}).items())]
    for measure, scenario, value in rows:
        if measure not in tol:
            out["ok"] = False
            out["reds"].append(f"REFUSED: no tolerance for {measure} in {BASELINE}")
            continue
        key = f"{measure}|{scenario}|{model}"
        entry = (baseline.get("figures") or {}).get(key)
        if entry is None and measure != "disk_kib":
            out["recorded"][key] = {"median": float(value)}  # no figure yet: written by the run (report-only), never a red
        if measure == "disk_kib" and entry is None:
            entry = {"median": 0}  # nothing may be left behind unless the baseline says so
        status, reason = t.compare(float(value), entry, float(tol[measure]), key)
        if status == "FAIL":
            out["ok"] = False
            out["reds"].append(f"{reason} on {model}" if measure != "disk_kib" else
                               f"{scenario}: {value:g} KiB left behind with no declared output (baseline "
                               f"{(baseline.get('figures') or {}).get(key, {}).get('median', 0):g}) on {model}")
        elif "lower the file" in reason:
            out["falls"].append(reason)
    out["findings"] = new_own_frames(figures.get("top", []), baseline.get("top", []))
    return out


def raised_baselines(old: dict, new: dict) -> list[str]:
    """What a batch's diff of `scripts/perf_baseline.json` raised (`ratchets-held-exactly`): a figure up, a tolerance loosened, a
    figure dropped is not a raise. A figure that is new is not a raise either: it is recorded."""
    out = []
    for k, v in (new.get("figures") or {}).items():
        was = (old.get("figures") or {}).get(k)
        if was is not None and float(v["median"]) > float(was["median"]):
            out.append(f"{k}: {was['median']:g} -> {v['median']:g}")
    for k, v in (new.get("tolerances") or {}).items():
        was = (old.get("tolerances") or {}).get(k)
        if was is not None and float(v) > float(was):
            out.append(f"tolerance {k}: {was:g} -> {v:g}")
    return out
