"""The slow-work watchdog (local.watchdog.slow-work, #6589): each tick the loop looks for work taking too long and acts, once per cause.

Three causes, each keyed by what it is about, so a cause is acted on once and a new step or rung is a new cause:
- a step past twice its lane's median land time (`nightly.median_land_s`), counted from its first `sent` row;
- a working session (a step `sent`) whose pane has shown no output for SILENT_S;
- a check rung that started longer ago than its timeout and has not ended.
The first strike raises ONE alert with the evidence and the action taken (the session is nudged; a hung rung is only named). A cause
still there one more period later is the second strike: the session is stopped and the step retried once (a hung rung's ladder is
cancelled and its step retried), with one `watchdog` row naming the alert. After that the cause is left to the person.
Pure over its inputs: the loop passes the clock, the rows and the actions; the tests pass fakes."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from fichero_builder import journal, nightly

SILENT_S = 20 * 60           # a working session with no output this long
SLOW_FACTOR = 2.0            # a step past this many times its lane's median land time
DONE = ("queued", "landed", "parked", "blocked")  # a step in one of these is not running: nothing to watch
NUDGE = ("The loop's watchdog: {why}. If you are stuck, say what blocks you on its own line as WAITING: <question>; "
         "otherwise carry on and end with the DONE line.")


def _ts(s: str) -> float:
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except ValueError:
        return 0.0


def sent_at(rows: list[dict], lane: str, step: str) -> float:
    """Epoch seconds of the step's first `sent` row; 0 when it has none."""
    return next((_ts(r["ts"]) for r in rows if r.get("event") == "queue" and r.get("lane") == lane and r.get("step") == step
                 and r.get("state") == "sent"), 0.0)


def open_rungs(rows: list[dict]) -> list[dict]:
    """[{key, rung, lane, started}] of check rungs that started and have not ended (no `rung` row and no `end` row for the key since)."""
    live: dict = {}
    for r in rows:
        if r.get("event") != "activity" or r.get("kind") != "check":
            continue
        key, st = r.get("key", ""), r.get("state")
        if st == "rung-start":
            live[(key, r.get("rung"))] = {"key": key, "rung": r.get("rung", ""), "lane": r.get("lane", "-"), "started": _ts(r["ts"])}
        elif st == "rung":
            live.pop((key, r.get("rung")), None)
        elif st in ("end", "start"):
            for k in [k for k in live if k[0] == key]:
                live.pop(k)
    return list(live.values())


def causes(lanes: list[dict], rows: list[dict], now: float, last_output: Callable[[dict], float | None],
           rung_timeout: Callable[[str], float], median: Callable[[list, str], float | None] = nightly.median_land_s) -> list[dict]:
    """Every slow thing now: [{key, lane, step, kind, why, period}]; `period` is how long one more strike waits."""
    out = []
    for lane in lanes:
        steps = lane.get("steps") or []
        if lane.get("cursor", 0) >= len(steps):
            continue
        s = steps[lane["cursor"]]
        if s.get("state") in DONE:
            continue
        since = sent_at(rows, lane["id"], s["step"])
        med = median(rows, lane["id"])
        if since and med and now - since > SLOW_FACTOR * med:
            out.append({"key": f"slow:{lane['id']}:{s['step']}", "lane": lane["id"], "step": s["step"], "kind": "slow-step", "period": med,
                        "why": f"step {s['step']} has run {(now - since) / 60:.0f} min, past {SLOW_FACTOR:g}x the lane's median land time "
                               f"({med / 60:.0f} min)"})
        if s.get("state") == "sent" and (seen := last_output(lane)) and now - seen >= SILENT_S:
            out.append({"key": f"silent:{lane['id']}:{s['step']}", "lane": lane["id"], "step": s["step"], "kind": "silent-session",
                        "period": SILENT_S, "why": f"the session of step {s['step']} has shown no output for {(now - seen) / 60:.0f} min"})
    for r in open_rungs(rows):
        limit = rung_timeout(r["rung"])
        if limit and now - r["started"] > limit:
            lane_id = r["lane"]
            step = next((x["steps"][x["cursor"]]["step"] for x in lanes if x["id"] == lane_id and x.get("cursor", 0) < len(x.get("steps") or [])), "")
            out.append({"key": f"rung:{r['key']}:{r['rung']}", "lane": lane_id, "step": step, "kind": "rung-timeout", "period": limit,
                        "head": r["key"].split("..")[-1], "why": f"the {r['rung']} rung of {r['key']} started {(now - r['started']) / 60:.0f} min "
                                                                   f"ago, past its {limit / 60:.0f} min timeout"})
    return out


def check(lanes: list[dict], rows: list[dict], now: float, *, last_output, rung_timeout, nudge: Callable[[dict, str], str],
          stop_retry: Callable[[str, str, str], str], cancel: Callable[[str], None], alert: Callable[[str, str, str], str],
          state: Path | None = None, median=nightly.median_land_s) -> list[str]:
    """One watchdog pass; returns what it did, one line each. `state` keeps the strikes (default <state dir>/watchdog.json)."""
    f = state or journal.STATE / "watchdog.json"
    try:
        strikes = json.loads(f.read_text())
    except (OSError, ValueError):
        strikes = {}
    now_causes = causes(lanes, rows, now, last_output, rung_timeout, median)
    did = []
    by_id = {x["id"]: x for x in lanes}
    for c in now_causes:
        seen = strikes.get(c["key"])
        if seen is None:  # the first strike: one alert with the evidence and the action
            if c["kind"] == "rung-timeout":
                action = "nothing yet; one more timeout and the ladder is cancelled and the step retried once"
            else:
                said = nudge(by_id.get(c["lane"], {"id": c["lane"]}), NUDGE.format(why=c["why"]))
                action = "nudged the session" + (f" (not delivered: {said})" if said else "")
            aid = alert(c["lane"], c["step"], f"watchdog {c['kind']}: {c['why']}; action: {action}")
            strikes[c["key"]] = {"strike": 1, "at": now, "alert": aid}
            did.append(f"{c['key']}: alert {aid}, {action}")
        elif seen["strike"] == 1 and now - seen["at"] >= c["period"]:  # the second strike: stop and retry, once
            if c["kind"] == "rung-timeout":
                cancel(c["head"])
            why = stop_retry(c["lane"], c["step"], seen.get("alert", "")) if c["step"] else "no step to retry"
            action = ("cancelled the ladder, " if c["kind"] == "rung-timeout" else "stopped the session, ") + (f"retry: {why}" if why else "retried once")
            journal.append("watchdog", lane=c["lane"], step=c["step"], cause=c["kind"], alert=seen.get("alert", ""), detail=f"{c['why']}; {action}")
            strikes[c["key"]] = {**seen, "strike": 2, "at": now}
            did.append(f"{c['key']}: {action}")
    live = {c["key"] for c in now_causes}
    strikes = {k: v for k, v in strikes.items() if k in live}  # a cause that ended is forgotten; the same step slow again later is new
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(strikes))
    except OSError:
        pass
    return did
