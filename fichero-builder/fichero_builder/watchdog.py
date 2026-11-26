"""The slow-work watchdog (local.watchdog.slow-work, #6589): each tick the loop looks for work taking too long and acts, once per cause.

Three causes, each keyed by what it is about, so a cause is acted on once and a new step or rung is a new cause:
- a step past twice its lane's median land time (`nightly.median_land_s`), counted from its LATEST `sent` row (a retry restarts it);
- a working session (a step `sent`) whose pane has shown no output for SILENT_S;
- a rung of the lane's CURRENT check (its key ends in the cursor step's head, started since this loop started) running past its
  timeout (never under RUNG_S: a rung's wall time includes its wait for the guards or build lock).
Only a lane the loop runs is judged: in [loop].only, not paused, its cursor step in RUNNING. A rung-start whose check died with an
earlier loop never gets a rung row; it is older than the loop and never a timeout. A nudge that reaches no session is the
`local.run.sent-needs-a-live-session` case: the alert says so and nothing escalates.
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
RUNNING = ("sent", "said-done", "done", "checking", "reviewing", "fixing")  # a cursor step in any other state is not watched
RUNG_S = 60 * 60             # a rung's timeout when its figure is unknown, and the least any rung is given
NUDGE = ("The loop's watchdog: {why}. If you are stuck, say what blocks you on its own line as WAITING: <question>; "
         "otherwise carry on and end with the DONE line.")


def _ts(s: str) -> float:
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except ValueError:
        return 0.0


def sent_at(rows: list[dict], lane: str, step: str) -> float:
    """Epoch seconds of the step's latest `sent` row (a retry or restart starts the clock again); 0 when it has none."""
    return next((_ts(r["ts"]) for r in reversed(rows) if r.get("event") == "queue" and r.get("lane") == lane and r.get("step") == step
                 and r.get("state") == "sent"), 0.0)


def watched(lane: dict, only=()) -> dict | None:
    """The lane's cursor step when the loop is running it (in `only` when set, not paused, the step in RUNNING); else None."""
    steps = lane.get("steps") or []
    if (only and lane["id"] not in only) or lane.get("paused") or lane.get("cursor", 0) >= len(steps):
        return None
    s = steps[lane["cursor"]]
    return s if s.get("state") in RUNNING else None


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
           rung_timeout: Callable[[str], float], median: Callable[[list, str], float | None] = nightly.median_land_s,
           only=(), loop_start: float = 0.0) -> list[dict]:
    """Every slow thing now: [{key, lane, step, kind, why, period}]; `period` is how long one more strike waits."""
    out = []
    running = {}
    for lane in lanes:
        if (s := watched(lane, only)) is None:
            continue
        running[lane["id"]] = s
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
        s = running.get(r["lane"])
        head = str((s or {}).get("head") or "")[:9]
        if not s or not head or not r["key"].endswith(".." + head) or r["started"] < loop_start:
            continue  # not this lane's current check, or a check that died with an earlier loop
        limit = max(rung_timeout(r["rung"]) or 0, RUNG_S)
        if now - r["started"] > limit:
            lane_id, step = r["lane"], s["step"]
            out.append({"key": f"rung:{r['key']}:{r['rung']}", "lane": lane_id, "step": step, "kind": "rung-timeout", "period": limit,
                        "head": r["key"].split("..")[-1], "why": f"the {r['rung']} rung of {r['key']} started {(now - r['started']) / 60:.0f} min "
                                                                   f"ago, past its {limit / 60:.0f} min timeout"})
    return out


def check(lanes: list[dict], rows: list[dict], now: float, *, last_output, rung_timeout, nudge: Callable[[dict, str], str],
          stop_retry: Callable[[str, str, str], str], cancel: Callable[[str], None], alert: Callable[[str, str, str], str],
          state: Path | None = None, median=nightly.median_land_s, only=(), loop_start: float = 0.0) -> list[str]:
    """One watchdog pass; returns what it did, one line each. `state` keeps the strikes (default <state dir>/watchdog.json)."""
    f = state or journal.STATE / "watchdog.json"
    try:
        strikes = json.loads(f.read_text())
    except (OSError, ValueError):
        strikes = {}
    now_causes = causes(lanes, rows, now, last_output, rung_timeout, median, only, loop_start)
    did = []
    by_id = {x["id"]: x for x in lanes}
    for c in now_causes:
        seen = strikes.get(c["key"])
        if seen is None:  # the first strike: one alert with the evidence and the action
            if c["kind"] == "rung-timeout":
                action = "nothing yet; one more timeout and the ladder is cancelled and the step retried once"
            else:
                said = nudge(by_id.get(c["lane"], {"id": c["lane"]}), NUDGE.format(why=c["why"]))
                action = ("nudged the session" if not said else
                          f"none: no live session to nudge ({said}); the step is sent with no session, a person's call")
            aid = alert(c["lane"], c["step"], f"watchdog {c['kind']}: {c['why']}; action: {action}")
            # with no session there is nothing to stop: the strike never escalates (local.run.sent-needs-a-live-session)
            strikes[c["key"]] = {"strike": 2 if c["kind"] != "rung-timeout" and said else 1, "at": now, "alert": aid}
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
