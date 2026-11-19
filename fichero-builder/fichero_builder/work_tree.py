"""builder-console.work.counts-are-live (#6645): per milestone, how many steps are in each state, the oldest age in that state, the
lanes holding them and the last failure, read from the lanes' steps through `queue.state_view`. A lane's `milestone` key names its
milestone; a lane without one is `unfiled`. GitHub counts are not read here, and no page calls this yet. `on_origin(lane, step)` says whether a landed step's head is on origin; without it every landed step counts as landed."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from fichero_builder import journal, queue

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


def order_path() -> Path:
    return journal.STATE / "work.json"


def read_order() -> list[str]:
    """The ordered milestone titles in the state folder's work.json; [] when the record does not exist yet."""
    p = order_path()
    return json.loads(p.read_text())["order"] if p.is_file() else []


def write_order(order: list[str]) -> None:
    """Replace the record. The caller has checked the titles (check_order) and journals the row."""
    p = order_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps({"order": order}, indent=1))
    os.replace(tmp, p)


def check_order(order: list[str], milestones: list[str]) -> None:
    """ValueError naming a title twice in `order` or a title that is not a milestone, with the milestone to make."""
    if len(set(order)) != len(order):
        raise ValueError("a milestone is listed twice in the order")
    if unknown := [m for m in order if m not in milestones]:
        raise ValueError("no GitHub milestone named " + ", ".join(repr(m) for m in unknown) + ": make the milestone, then order it")


def append_order(titles: list[str], milestones: list[str]) -> list[str]:
    """`builder triage --order`: the titles the record lacks go on the end in the given order and the rest never move. Returns the added ones."""
    current = read_order()
    added = [t for t in dict.fromkeys(titles) if t not in current]
    check_order(current + added, milestones)
    if added:
        write_order(current + added)
        journal.append("order", order=current + added, appended=added)
    return added


def milestone_of(store, issues: list[int]) -> str:
    """The one milestone the open issues belong to, or `unfiled` when none is in a milestone. Issues in two milestones are a ValueError."""
    found = {m["title"] for m in store.milestones() for i in store.issues(m["title"]) if i["number"] in issues}
    if len(found) > 1:
        raise ValueError(f"issues {issues} are in more than one milestone: {', '.join(sorted(found))}")
    return found.pop() if found else "unfiled"
