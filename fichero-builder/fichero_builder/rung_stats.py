"""`builder rung-stats`: per-rung duration (mean / p90 / max, seconds) from the journal's `activity` rung rows, so a landing-speed
report is exact (landing-speed brief, #6444 item 1: the rows exist since 2026-11-02; what was missing was this read)."""
from __future__ import annotations

import statistics

from fichero_builder import journal


def stats(rows: list[dict], since: str = "") -> dict[str, dict]:
    by: dict[str, list[float]] = {}
    for r in rows:
        if r.get("event") == "activity" and r.get("state") == "rung" and str(r.get("ts", "")) >= since:
            sec = r.get("seconds") if r.get("seconds") is not None else r.get("wall_s")  # a cached/summed rung has no `seconds`, its wall clock is there
            if sec is not None:
                by.setdefault(r["rung"], []).append(float(sec))
    return {k: {"n": len(v), "mean": round(statistics.fmean(v), 1), "p90": round(sorted(v)[min(len(v) - 1, int(len(v) * 0.9))], 1), "max": round(max(v), 1),
                "total_min": round(sum(v) / 60, 1)} for k, v in by.items()}


FLOW = {  # local.flow.report: the check flow's targets ([flow] in harness.toml overrides each), owner 2026-11-26
    "ladder_median_min": 4.0, "ladder_p90_min": 10.0, "shared_file_wait_s": 0.0, "done_per_landed": 2.5, "last_done_median_min": 25.0,
    "last_done_p90_min": 45.0, "first_done_median_min": 90.0, "first_done_p90_min": 240.0, "train_p90_min": 30.0, "ready_reds": 0.0,
}


def _ts(s: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(s).timestamp()


def _p90(v: list[float]) -> float:
    return sorted(v)[min(len(v) - 1, int(len(v) * 0.9))]


def flow(rows: list[dict], since: str = "", targets: dict | None = None) -> list[tuple[str, float | None, float, bool]]:
    """[(target, measured or None for no data, limit, ok)] from the journal alone: each line of local.flow.report's table."""
    t = {**FLOW, **(targets or {})}
    rows = [r for r in rows if str(r.get("ts", "")) >= since]
    starts, walls = {}, []
    for r in rows:  # a ladder run: its check activity's start to its end
        if r.get("event") == "activity" and r.get("kind") == "check" and r.get("state") in ("start", "end"):
            if r["state"] == "start":
                starts[r["key"]] = _ts(r["ts"])
            elif r["key"] in starts:
                walls.append((_ts(r["ts"]) - starts.pop(r["key"])) / 60)
    cause, clash_s = {}, 0.0
    for r in rows:  # a slot wait whose cause was a shared file (the clash row comes before its acquired row)
        if r.get("event") == "lock" and r.get("name") == "ladder":
            if r.get("state") == "clash" or (r.get("state") == "waiting" and "shares" in r.get("detail", "")):
                cause[r.get("what")] = True
            elif r.get("state") == "acquired" and cause.pop(r.get("what"), False):
                clash_s += float(r.get("seconds") or 0)
    dones: dict = {}
    landed: dict = {}
    for r in rows:
        if r.get("event") == "queue" and r.get("state") in ("done", "landed"):
            k = (r.get("lane"), r.get("step"))
            if r["state"] == "done":
                dones.setdefault(k, []).append(_ts(r["ts"]))
            elif k not in landed:
                landed[k] = _ts(r["ts"])
    per, last, first = [], [], []
    for k, at in landed.items():
        before = [d for d in dones.get(k, []) if d <= at]
        if before:
            per.append(len(before))
            last.append((at - max(before)) / 60)
            first.append((at - min(before)) / 60)
    trains = [float(r["seconds"]) / 60 for r in rows if r.get("event") == "train" and r.get("seconds") is not None]
    ready = sum(1 for r in rows if r.get("event") == "activity" and r.get("state") == "rung" and r.get("rung") == "ready" and r.get("ok") is False)

    def line(name: str, v: list[float] | float | None, how, key: str):
        val = (how(v) if v else None) if isinstance(v, list) else v
        return name, None if val is None else round(val, 1), t[key], val is None or val <= t[key]
    return [line("ladder run wall time, median (min)", walls, statistics.median, "ladder_median_min"),
            line("ladder run wall time, 90th percentile (min)", walls, _p90, "ladder_p90_min"),
            line("slot wait for a shared file (s)", clash_s, None, "shared_file_wait_s"),
            line("DONE rows per landed step, mean", [float(x) for x in per], statistics.fmean, "done_per_landed"),
            line("last DONE to landed, median (min)", last, statistics.median, "last_done_median_min"),
            line("last DONE to landed, 90th percentile (min)", last, _p90, "last_done_p90_min"),
            line("first DONE to landed, median (min)", first, statistics.median, "first_done_median_min"),
            line("first DONE to landed, 90th percentile (min)", first, _p90, "first_done_p90_min"),
            line("train wall time, 90th percentile (min)", trains, _p90, "train_p90_min"),
            line("ready reds inside a ladder", float(ready), None, "ready_reds")]


def main_flow(a) -> int:
    import tomllib
    from pathlib import Path
    f = Path(getattr(a, "root", "") or ".") / "harness.toml"
    try:
        targets = tomllib.loads(f.read_text()).get("flow", {}) if f.is_file() else {}
    except (OSError, ValueError):
        targets = {}
    if unknown := sorted(set(targets) - set(FLOW)):
        print(f"harness.toml [flow]: unknown keys {unknown}")
        return 2
    over = False
    for name, val, limit, ok in flow(journal.read(), a.since, targets):
        over = over or not ok
        print(f"{name:46} {'no data' if val is None else val:>8} (target {limit:g})  {'ok' if ok else 'over'}")
    return 1 if over else 0


def main(a) -> int:
    if getattr(a, "flow", False):
        return main_flow(a)
    out = stats(journal.read(), a.since)
    for k, v in sorted(out.items(), key=lambda kv: -kv[1]["total_min"]):
        print(f"{k:20} n={v['n']:4} mean={v['mean']:7} p90={v['p90']:7} max={v['max']:7} total={v['total_min']} min")
    return 0
