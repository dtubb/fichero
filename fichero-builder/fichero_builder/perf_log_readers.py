"""The performance sweep's two log readers (#6600 Step 2): the app's launch and interaction timelines, and the engine's `PERF` lines.

Both only READ text a run already wrote (a `log stream` capture, the app's stderr timeline, an engine log); neither measures, runs the
app or loads a model. Percentiles are nearest-rank: p(q) of n sorted values is the value at rank ceil(q*n)."""
from __future__ import annotations

import json
import math
import re

_LAUNCH = re.compile(r"⏱ (.+?) @ (\d+(?:\.\d+)?)ms\s*$")
_TOOK = re.compile(r"⏱ (.+?) took (\d+(?:\.\d+)?)ms(?:: (.*))?$")
_LAP = re.compile(r"(.+?) (\d+(?:\.\d+)?)ms$")
_DETAIL = re.compile(r"\s*\([^()]*\)$")  # a trailing "(detail)" is the call's context, not part of the phase's name
_PERF = re.compile(r"\bPERF (\S+)((?: \S+=\S*)*)\s*$")
_LOADED = re.compile(r"model-lane: loaded (\S+) in (\d+(?:\.\d+)?) s \(load (\d+)")
_AGAIN = re.compile(r"model loaded again: ([^,\s]+),")


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def _stats(values: list[float]) -> dict:
    return {"count": len(values), "p50": pct(values, 0.5), "p95": pct(values, 0.95), "max": max(values)}


def _message(line: str) -> str:
    line = line.strip()
    if line.startswith("{"):  # `log stream --style json`
        try:
            return str(json.loads(line).get("eventMessage", ""))
        except ValueError:
            return ""
    return line


def read_app_log(lines) -> dict:
    """Phase rows from `app-log.jsonl` or the stderr timeline: launch milestones become the gap to the previous milestone, interval
    ends and their laps keep their names; a superseded interval never reached its end and is no measurement."""
    gaps: dict[str, list[float]] = {}
    order: list[str] = []
    took: dict[str, list[float]] = {}
    last = None
    for line in lines:
        msg = _message(line)
        m = _LAUNCH.search(msg)
        if m:
            name, elapsed = _DETAIL.sub("", m.group(1)), float(m.group(2))
            if last is None or elapsed < last:  # a second launch in the same log starts again from zero
                last = 0.0
            if name not in gaps:
                order.append(name)
            gaps.setdefault(name, []).append(round(elapsed - last, 3))
            last = elapsed
            continue
        m = _TOOK.search(msg)
        if m:
            name = _DETAIL.sub("", m.group(1))
            took.setdefault(name, []).append(float(m.group(2)))
            for lap in (m.group(3) or "").split(" · "):
                lm = _LAP.match(lap.strip())
                if lm:
                    took.setdefault(f"{name}: {lm.group(1)}", []).append(float(lm.group(2)))
    phases = [{"phase": n, "kind": "launch", **_stats(gaps[n])} for n in order]
    phases += [{"phase": n, "kind": "interaction", **_stats(v)} for n, v in took.items()]
    return {"phases": phases, "status": "ok" if phases else "no-app-log"}


#: The app's launch milestones the budgets are read from, by the name `LaunchProfile.milestone` logs (#7105).
LAUNCH_MILESTONES = {
    "will_finish": "applicationWillFinishLaunching — engine connect starts",
    "connect": "connect() entry — main actor reached",
    "first_on_appear": "LibraryWindow first onAppear",
}
#: ms. The first window within 3 s of process start; `connect()` on the main actor within 1 s of willFinishLaunching.
LAUNCH_BUDGETS_MS = {"first_on_appear_ms": 3000, "connect_after_will_finish_ms": 1000}


def launch_budgets(lines) -> dict:
    """The first launch in `lines` (the app's `⏱ name @ N ms` lines) against LAUNCH_BUDGETS_MS. `ok` only when every milestone was
    logged and every figure is inside its budget: a launch that logged no milestone was not measured, and that is a red."""
    at: dict[str, float] = {}
    last = None
    for line in lines:
        m = _LAUNCH.search(_message(line))
        if not m:
            continue
        name, elapsed = _DETAIL.sub("", m.group(1)), float(m.group(2))
        if last is not None and elapsed < last:
            break  # a second launch starts again from zero
        last = elapsed
        at.setdefault(name, elapsed)
    missing = [name for name in LAUNCH_MILESTONES.values() if name not in at]
    figures = {}
    if not missing:
        figures = {"first_on_appear_ms": at[LAUNCH_MILESTONES["first_on_appear"]],
                   "connect_after_will_finish_ms": round(at[LAUNCH_MILESTONES["connect"]] - at[LAUNCH_MILESTONES["will_finish"]], 3)}
    over = [f"{name} {value} > {LAUNCH_BUDGETS_MS[name]}" for name, value in figures.items() if value > LAUNCH_BUDGETS_MS[name]]
    return {"ok": not missing and not over, "figures": figures, "over": over, "missing": missing}


def _kv(rest: str) -> dict:
    return dict(tok.split("=", 1) for tok in rest.split())


def read_engine_log(lines, group_by=()) -> dict:
    """Span rows (count, p50, p95, max, total = count x p50) per `PERF <name>` and per `group_by` key, and per model its load count,
    total load seconds and whether the engine said `model loaded again`. Other lines are ignored."""
    spans: dict[tuple, dict] = {}
    models: dict[str, dict] = {}
    for line in lines:
        m = _PERF.search(line)
        if m:
            kv = _kv(m.group(2))
            try:
                ms = float(kv.pop("duration_ms"))
            except (KeyError, ValueError):
                continue
            group = {k: kv[k] for k in group_by if k in kv}
            e = spans.setdefault((m.group(1), tuple(sorted(group.items()))), {"name": m.group(1), "group": group, "values": []})
            e["values"].append(ms)
            continue
        m = _LOADED.search(line)
        if m:
            e = models.setdefault(m.group(1), {"model": m.group(1), "loads": 0, "total_s": 0.0, "reload": False})
            e["loads"] += 1
            e["total_s"] = round(e["total_s"] + float(m.group(2)), 3)
            continue
        m = _AGAIN.search(line)
        if m:
            models.setdefault(m.group(1), {"model": m.group(1), "loads": 0, "total_s": 0.0, "reload": False})["reload"] = True
    span_rows = []
    for e in spans.values():
        st = _stats(e["values"])
        span_rows.append({"name": e["name"], "group": e["group"], **st, "total": round(st["count"] * st["p50"], 3)})
    return {"spans": span_rows, "models": list(models.values()), "status": "ok" if span_rows or models else "no-engine-log"}
