"""The scheduler (pipeline.schedule): `python -m pipeline run` drives the items the journal already holds and starts
new ones, one pass at a time, until the daily cap, a pause or nothing is left. It makes no model call itself: every
call is a `core` function (start, review, resume_asked, retry) that spends under the same caps. Stdlib; restartable,
because every decision reads the journal (state()) and the one thing it records, `schedule` lines, is also read back."""
from __future__ import annotations

import time
from pathlib import Path

from pipeline import core, journal


class Stop(Exception):
    """A reason the whole run ends (paused, daily cap), not a problem with one item."""


def _ask_once(kind: str, text: str) -> None:
    """A question for the maintainer, queued once ever for this exact text (an answered one is gone from the queue)."""
    if not any(e["event"] == "queue" and e["text"] == text for e in journal.read()):
        core._queue(kind, text)


def _go() -> None:
    try:
        core._require_running()
        core._require_budget()
    except RuntimeError as e:
        raise Stop(str(e)) from e


def _scheduled(key: str, what: str, sha: str) -> bool:
    return any(e["event"] == "schedule" and (e["key"], e["what"], e["sha"]) == (key, what, sha) for e in journal.read())


def tick() -> tuple[list[str], bool]:
    """One pass over the journal → (what it did, whether any of it moved an item). Order: answered questions, the
    checks and the review of what was coded, a reviewed READY item queued as 'ready to land', NOT_READY sent back,
    blocked items asked about, then new issues from the feeder."""
    did, moved, c = [], False, core.cfg()
    _go()
    for key, it in core.state()["items"].items():
        s = core.state()
        it, st = s["items"][key], s["items"][key]["state"]
        if st == "asking" and it.get("answer") and not any(q.get("key") == key for q in s["queue"].values()):
            _go()
            core.resume_asked(key)
            did.append(f"{key}: answered, resumed")
            moved = True
        elif st == "checked":
            wt = Path(s["tasks"][it["task"]]["worktree"])
            if core._head(wt) != it["sha"] or not it["check_ok"]:
                core.check(key)
                did.append(f"{key}: checked")
                moved = True
                it = core.state()["items"][key]
            if it["state"] != "checked" or not it["check_ok"]:
                continue
            if _scheduled(key, "review", it["sha"]):  # asked once per sha: a reviewer that left no verdict is the maintainer's call
                if not any(v["sha"] == it["sha"] for v in it["verdicts"]):
                    _ask_once("blocked", f"{key}: the review of {it['sha'][:9]} left no verdict; `review {key}` to run it again")
                continue
            _go()
            journal.append("schedule", issue=it["issue"], key=key, what="review", sha=it["sha"])
            core.review(key)
            did.append(f"{key}: reviewed")
            moved = True
        elif st == "coding" and it["retry_text"].startswith("Review NOT_READY"):
            if it["attempts"] <= c["workers"]["retries"]:
                _go()
                core.retry(key)
                did.append(f"{key}: sent back with the review findings")
                moved = True
            else:
                _ask_once("blocked", f"{key}: NOT_READY {it['attempts']} times; the reviewer's findings are in its record, it needs you")
        elif st in ("needs-maintainer", "failed", "rate-limited"):
            _ask_once("blocked", f"{key} is {st}: {it['history'][-1].split(': ', 1)[-1][:300] if it['history'] else ''}")
    for key, it in core.state()["items"].items():
        if it["state"] == "reviewed":
            _ask_once("ready-to-land", f"{key} is reviewed READY at {it['sha'][:9]}: `python -m pipeline land {key}`")
    did += _start_new(c)
    return did, moved or any(d.startswith("start") for d in did)


def _start_new(c: dict) -> list[str]:
    s = core.state()
    sc = c.get("run", {})
    live = sum(1 for w in s["workers"].values() if w.get("role") == "coder" and not w.get("parked"))
    if live >= c["workers"]["caps"]["coders"]:
        return []
    got = core.next_issues(sc.get("batch", 3))
    nums = []
    try:
        if got["ready"]:
            nums, writeup = [i["number"] for i in got["ready"]], False
        elif got["write_up"]:
            nums, writeup = got["write_up"][:1], True
        else:
            return []
        _go()
        out = core.start(nums, milestone=got["milestone"], writeup=writeup)
    except (PermissionError, RuntimeError, BlockingIOError, Stop) as e:
        if isinstance(e, Stop):
            raise
        if "daily cap" in str(e) or "paused" in str(e):
            raise Stop(str(e)) from e
        _ask_once("blocked", f"the scheduler could not start {nums}: {e}")
        return [f"blocked: {e}"]
    return [f"start {nums}{' (write-up)' if writeup else ''}: {out.get('items') or out.get('done')}"]


def run(once: bool = False, poll_s: float | None = None) -> dict:
    """Tick until a stop reason. With items still waiting on an answer, sleep the profile's `[run] poll_s`
    (default 60) between passes and carry on when one arrives; otherwise stop when a pass moves nothing."""
    poll = poll_s or core.cfg().get("run", {}).get("poll_s", 60)
    log = []
    while True:
        try:
            did, moved = tick()
        except Stop as e:
            return {"stopped": str(e), "did": log}
        log += did
        if moved and not once:
            continue
        waiting = [k for k, it in core.state()["items"].items() if it["state"] == "asking"]
        if once or not waiting:
            return {"stopped": "once" if once else "nothing is ready", "did": log}
        time.sleep(poll)


core.API.update(run=run)
core.WORKER_FORBIDDEN += ("run",)
