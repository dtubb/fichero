"""builder-console.work.counts-are-live (#6645): per milestone, how many steps are in each state, the oldest age in that state, the
lanes holding them and the last failure, read from the lanes' steps through `queue.state_view`. A lane's `milestone` key names its
milestone; a lane without one is `unfiled`. GitHub counts are not read here, and no page calls this yet. `on_origin(lane, step)` says whether a landed step's head is on origin; without it every landed step counts as landed."""
from __future__ import annotations

from typing import Callable

from fichero_builder import queue

GROUP = {"queued": "queued", "sent": "running", "fixing": "running", "said-done": "waiting", "checking": "waiting", "reviewing": "waiting",
         "blocked": "blocked", "red": "red", "done-not-landed": "done-not-landed", "landed": "landed", "parked": "parked"}
FINAL = ("landed", "parked")


def counts(lanes: list[dict], now: float | None = None, on_origin: Callable[[dict, dict], bool] | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    newest_fail: dict[str, float] = {}
    for lane in lanes:
        m = out.setdefault(lane.get("milestone") or "unfiled", {"states": {}, "last_failure": "", "running_lane": "", "last_lane": "", "paused": []})
        if lane.get("paused"):
            m["paused"].append(lane["id"])
        views = [queue.state_view(lane, s, now=now, on_origin=on_origin(lane, s) if on_origin else True) for s in lane["steps"]]
        for v in views:
            g = m["states"].setdefault(GROUP[v["state"]], {"n": 0, "oldest_age_s": 0.0, "lanes": []})
            g["n"] += 1
            g["oldest_age_s"] = max(g["oldest_age_s"], v["age_s"])
            if lane["id"] not in g["lanes"]:
                g["lanes"].append(lane["id"])
            if v["state"] in ("red", "blocked") and v["why"] and (v["since"] >= newest_fail.get(id(m), float("-inf"))):
                newest_fail[id(m)] = v["since"]
                m["last_failure"] = v["why"].strip().splitlines()[0]
        if any(v["state"] not in FINAL for v in views):
            m["running_lane"] = m["running_lane"] or lane["id"]
        elif views:
            m["last_lane"] = lane["id"]
    return out
