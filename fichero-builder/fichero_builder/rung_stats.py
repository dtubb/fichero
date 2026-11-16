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


def main(a) -> int:
    out = stats(journal.read(), a.since)
    for k, v in sorted(out.items(), key=lambda kv: -kv[1]["total_min"]):
        print(f"{k:20} n={v['n']:4} mean={v['mean']:7} p90={v['p90']:7} max={v['max']:7} total={v['total_min']} min")
    return 0
