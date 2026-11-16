"""The performance sweep's rows and ranked hotspot table (#6600 Step 2, spec harness/performance-sweep.md).

`perf-sweep.output.row`: every source gives rows of one shape. `perf-sweep.output.table`: a run writes hotspots.json (all rows) under
`perf/<run>` in the builder's state dir and `perf/latest.json` (a pointer and the ranked top 50); `builder perf show|diff|read` print and
fill them. This step reads logs a run already wrote (see perf_log_readers); no new tool, no new workload."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fichero_builder import journal, perf_log_readers, review_lenses

BAND_PCT = 6.0  # the noise band until `ratchet.noise-band` measures one (Step 7)
PER_KIND = 10
TOP = 50
KINDS = ("time", "cpu", "ram", "disk", "energy", "hang", "leak", "body", "efficiency")
SIDES = ("engine", "app", "field")


def make_row(*, run, machine_model, workload, side, where, kind, value, unit, source, count=1, share=None, trend_pct=None, runs_seen=1,
             profile="", detail=None, area=None) -> dict:
    """One row. A row without `where`, `value` or `source` is refused: a hotspot nobody can find or trace is not a finding."""
    for name, v in (("where", where), ("value", value), ("source", source)):
        if v is None or v == "":
            raise ValueError(f"a perf row needs {name}")
    if kind not in KINDS or side not in SIDES:
        raise ValueError(f"a perf row's kind is one of {KINDS} and its side one of {SIDES}, not {kind!r}/{side!r}")
    return {"run": run, "machine_model": machine_model, "workload": workload, "side": side, "area": area or review_lenses.area_of(where),
            "kind": kind, "where": where, "value": value, "unit": unit, "count": count, "share": share, "source": source,
            "trend_pct": trend_pct, "runs_seen": runs_seen, "profile": profile, "detail": detail or {}}


def _shares(values: list[float]) -> list:
    total = sum(values)
    return [round(v / total, 4) if total > 0 else None for v in values]


def rows_from_logs(app: dict | None, engine: dict | None, *, run, machine_model, workload, profile="") -> list[dict]:
    base = dict(run=run, machine_model=machine_model, workload=workload, profile=profile)
    rows: list[dict] = []
    for group in ("launch", "interaction"):
        ph = [p for p in (app or {}).get("phases", []) if p["kind"] == group]
        top = {p["phase"]: round(p["count"] * p["p50"], 3) for p in ph if ": " not in p["phase"]}
        total = sum(top.values())
        for p in ph:
            v = round(p["count"] * p["p50"], 3)
            parent = top.get(p["phase"].split(": ", 1)[0], total) if ": " in p["phase"] else total
            rows.append(make_row(**base, side="app", where=p["phase"], kind="time", value=v, unit="ms", count=p["count"],
                                 share=round(v / parent, 4) if parent > 0 else None, source="app-log",
                                 detail={"phase": group, "p50": p["p50"], "p95": p["p95"], "max": p["max"]}))
    spans = (engine or {}).get("spans", [])
    for s, sh in zip(spans, _shares([s["total"] for s in spans])):
        where = s["name"] + "".join(f"[{k}={v}]" for k, v in s["group"].items())
        rows.append(make_row(**base, side="engine", where=where, kind="time", value=s["total"], unit="ms", count=s["count"], share=sh,
                             source="perf-line", detail={"p50": s["p50"], "p95": s["p95"], "max": s["max"]}))
    models = (engine or {}).get("models", [])
    for m, sh in zip(models, _shares([m["total_s"] for m in models])):
        rows.append(make_row(**base, side="engine", where=f"model load {m['model']}", kind="time", value=round(m["total_s"] * 1000, 3),
                             unit="ms", count=m["loads"], share=sh, source="model-lane", detail={"reload": m["reload"]}))
    return rows


def _rank_key(r: dict) -> tuple:
    return (r["share"] is None, -(r["share"] or 0), -r["value"], -r["count"])


def rank(rows: list[dict]) -> list[dict]:
    """Within a kind by share where it exists, else by value, ties by count; across kinds the top 10 of each, best of each kind first,
    so a disk hog is never buried under time rows."""
    picked = []
    for kind in KINDS:
        of = sorted((r for r in rows if r["kind"] == kind), key=_rank_key)[:PER_KIND]
        picked += [(i, KINDS.index(kind), r) for i, r in enumerate(of)]
    return [r for _, _, r in sorted(picked, key=lambda t: t[:2])]


def trend_text(trend_pct, band: float = BAND_PCT) -> str:
    """`~` inside the noise band, `+N%` for a worsening beyond it, `−N%` for an improvement, `new` on a first run."""
    if trend_pct is None:
        return "new"
    if abs(trend_pct) <= band:
        return "~"
    return f"+{round(trend_pct)}%" if trend_pct > 0 else f"−{round(-trend_pct)}%"


def _key(r: dict) -> tuple:
    return (r["machine_model"], r["workload"], r["side"], r["kind"], r["where"])


def _read(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _previous(perf: Path) -> dict:
    latest = _read(perf / "latest.json")
    prev = _read(Path(latest["hotspots"])) if latest and latest.get("hotspots") else None
    return {_key(r): r for r in (prev or {}).get("rows", [])}


def sweep(*, run, machine_model, state, workload, app_log=None, engine_log=None, group_by=(), profile="") -> dict:
    """Read the logs, rank, write hotspots.json and latest.json. A log that gave nothing is a note (`no-app-log`, `no-engine-log`),
    never a silent green."""
    perf = Path(state) / "perf"
    app = perf_log_readers.read_app_log(app_log) if app_log is not None else None
    eng = perf_log_readers.read_engine_log(engine_log, group_by) if engine_log is not None else None
    notes = [x["status"] for x in (app, eng) if x and x["status"] != "ok"]
    rows = rows_from_logs(app, eng, run=run, machine_model=machine_model, workload=workload, profile=profile)
    before = _previous(perf)
    for r in rows:
        p = before.get(_key(r))
        if p:
            r["runs_seen"] = p["runs_seen"] + 1
            r["trend_pct"] = round((r["value"] - p["value"]) / p["value"] * 100, 1) if p["value"] else None
    out = perf / run
    out.mkdir(parents=True, exist_ok=True)
    hot = out / "hotspots.json"
    hot.write_text(json.dumps({"run": run, "machine_model": machine_model, "notes": notes, "rows": rows}, indent=1))
    top = rank(rows)[:TOP]
    (perf / "latest.json").write_text(json.dumps({"run": run, "hotspots": str(hot), "notes": notes, "top": top}, indent=1))
    return {"run": run, "rows": rows, "top": top, "notes": notes}


_COLS = ("kind", "area", "where", "value", "share", "count", "trend", "workload", "side", "profile")


def _table(rows: list[dict]) -> str:
    def cells(r):
        sh = "" if r["share"] is None else f"{r['share'] * 100:.1f}%"
        return [r["kind"], r["area"], r["where"], f"{r['value']:g}{r['unit']}", sh, str(r["count"]), trend_text(r["trend_pct"]),
                r["workload"], r["side"], r["profile"] or "-"]
    grid = [list(_COLS)] + [cells(r) for r in rows]
    widths = [max(len(g[i]) for g in grid) for i in range(len(_COLS))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(g, widths)).rstrip() for g in grid)


def _load(state, run) -> dict | None:
    perf = Path(state) / "perf"
    if not run:
        latest = _read(perf / "latest.json")
        run = latest and latest.get("run")
    if not run or not re.fullmatch(r"[\w.-]+", run):
        return None
    return _read(perf / run / "hotspots.json")


def show(state, run: str | None = None) -> int:
    data = _load(state, run)
    if not data:
        print(f"no hotspot table for run {run or '(latest)'} in {Path(state) / 'perf'}")
        return 2
    print(_table(rank(data["rows"])[:TOP]))
    for n in data.get("notes", []):
        print(f"note: {n} (the log gave no rows; this is not a green)")
    return 0


def diff(state, a: str, b: str) -> int:
    da, db = _load(state, a), _load(state, b)
    if not da or not db:
        print(f"no hotspot table for run {a if not da else b}")
        return 2
    before = {_key(r): r for r in da["rows"]}
    crossed = []
    for r in db["rows"]:
        p = before.get(_key(r))
        if p and p["value"]:
            pct = (r["value"] - p["value"]) / p["value"] * 100
            if abs(pct) > BAND_PCT:
                crossed.append({**r, "trend_pct": round(pct, 1)})
    print(_table(sorted(crossed, key=lambda r: -abs(r["trend_pct"]))) if crossed else f"no row moved beyond the {BAND_PCT:g}% band between {a} and {b}")
    return 0


def _model() -> str:
    try:
        return subprocess.run(["sysctl", "-n", "hw.model"], capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _lines(p):
    return Path(p).read_text(errors="replace").splitlines() if p else None


def main(a) -> int:
    state = Path(a.state) if a.state else journal.STATE
    if a.action == "show":
        return show(state, a.args[0] if a.args else None)
    if a.action == "diff":
        if len(a.args) != 2:
            print("usage: builder perf diff <run-a> <run-b>")
            return 2
        return diff(state, *a.args)
    run = a.run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # read: logs in, a hotspot table out
    if not re.fullmatch(r"[\w.-]+", run):
        print("a run id is letters, digits, dots, dashes and underscores")
        return 2
    out = sweep(run=run, machine_model=a.machine_model or _model(), state=state, workload=a.workload, app_log=_lines(a.app_log),
                engine_log=_lines(a.engine_log), group_by=tuple(a.group_by.split(",")) if a.group_by else ())
    print(f"run {run}: {len(out['rows'])} rows")
    return show(state, run)
