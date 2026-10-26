"""The scheduler (pipeline.schedule): `python -m pipeline run` drives the items the journal already holds and starts
new ones, one pass at a time, until the daily cap, a pause or nothing is left. It makes no model call itself: every
call is a `core` function (start, review, resume_asked, retry) that spends under the same caps. Stdlib; restartable,
because every decision reads the journal (state()) and the one thing it records, `schedule` lines, is also read back."""
from __future__ import annotations

import time
from pathlib import Path

from pipeline import checks, core, journal


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
    for key in list(core.state()["items"]):
        try:
            if _step(key, c, did):
                moved = True
        except (BlockingIOError, RuntimeError, OSError) as e:  # one item's failure is journaled and the run carries on
            it = core.state()["items"][key]
            journal.append("note", issue=it["issue"], key=key, text=f"scheduler: {type(e).__name__}: {e}"[:500])
            did.append(f"{key}: {type(e).__name__}: {e}"[:200])
    _adopt_landed(c, did)
    for key, it in core.state()["items"].items():
        if it["state"] == "reviewed":
            _ask_once("ready-to-land", f"{key} is reviewed READY at {it['sha'][:9]}: `python -m pipeline land {key}`")
    did += _start_new(c)
    return did, moved or any(d.startswith("start") for d in did)


def _adopt_landed(c: dict, did: list[str]) -> None:
    """A reviewed item whose checked sha is already on the base branch was landed by hand (a merge by the Lead, a cherry
    pick): it is pushed, not still waiting to land. Journals the move so the closer sees it and no ready-to-land is asked."""
    for key, it in list(core.state()["items"].items()):
        if it["state"] in ("reviewed", "candidate", "gated") and it["sha"] and not checks.sh(
                ["git", "merge-base", "--is-ancestor", it["sha"], c["repo"]["base"]], cwd=c["repo"]["path"]).returncode:
            for to in ("candidate", "gated", "pushed"):
                if (core.state()["items"][key]["state"], to) in core.ALLOWED:
                    core._move(key, to, f"{it['sha'][:9]} is on {c['repo']['base']} (landed by hand)")
            did.append(f"{key}: already on {c['repo']['base']}, marked pushed")


def _step(key: str, c: dict, did: list[str]) -> bool:
    """What the journal says this one item needs next; → whether it moved."""
    moved = False
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
            return moved
        if _scheduled(key, "review", it["sha"]):  # asked once per sha: a reviewer that left no verdict is the maintainer's call
            if not any(v["sha"] == it["sha"] for v in it["verdicts"]):
                _ask_once("blocked", f"{key}: the review of {it['sha'][:9]} left no verdict; `review {key}` to run it again")
            return moved
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
    return moved


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


def land(issue) -> dict:
    """reviewed READY → pushed (pipeline.nightly-gate, the manual `land` step). Refuses unless the item is reviewed READY
    by the reviewer at its live head; runs EVERY scripts/check_*.py (no skip list) in a scratch tree of that head; pushes
    that sha fast-forward to the profile's integration branch and nowhere else (never main, never a tag, never forced).
    A dry run unless `--apply` (core.DRY_RUN): it then runs the guards and says what it would push."""
    with journal.Lock("dispatch", wait=False):
        core._require_running()
        key, it, s = core._item(issue)
        c, sha = core.cfg(), it["sha"]
        wt = Path(s["tasks"][it["task"]]["worktree"])
        remote, _, branch = c["repo"]["base"].partition("/")
        if it["state"] not in ("reviewed", "gated"):
            raise RuntimeError(f"{key} is {it['state']}: only a reviewed READY item lands")
        v = core.verdict_now(it)  # the last verdict at the checked sha counts: a later NOT_READY there beats an earlier READY
        if not v or (v["verdict"], v["by"]) != ("READY", "reviewer"):
            raise RuntimeError(f"{key}: no reviewer READY for {sha[:9]} (the last verdict there counts)")
        if core._head(wt) != sha:
            raise RuntimeError(f"{key}: the worktree head moved past the reviewed {sha[:9]}; check and review again")
        if not branch or branch in (c["repo"]["main"], "main", "master") or branch.startswith("v"):
            raise RuntimeError(f"the profile's base {c['repo']['base']} is not an integration branch: land refuses")
        checks.git(wt, "fetch", "-q", remote)
        if checks.sh(["git", "merge-base", "--is-ancestor", c["repo"]["base"], sha], cwd=wt).returncode:
            raise RuntimeError(f"{key}: {c['repo']['base']} has moved on; rebase the branch, check and review again")
        tree = checks.scratch_tree(wt, sha)  # the sha's own tree: check() already ran the pinned overlay over it, so the guards here are the ones that will land
        try:  # every guard, the slow and network ones too: this is the last look before integration
            ok, text = checks.run_rung({"glob": "{pinned}/scripts/check_*.py", "timeout_s": c.get("run", {}).get("land_guard_s", 900)}, wt, tree, c, [], None, sha)
        finally:
            checks.drop_tree(wt, tree)
        journal.append("land", issue=it["issue"], key=key, sha=sha, ok=ok, apply=not core.DRY_RUN, text=text[:2000])
        if not ok:
            return {"issue": key, "landed": False, "text": text}
        refspec = f"{sha}:refs/heads/{branch}"
        if core.DRY_RUN:
            return {"issue": key, "landed": False, "would_push": f"git push {remote} {refspec}", "text": text}
        if it["state"] == "reviewed":
            core._move(key, "candidate", f"all guards green at {sha[:9]}")
            core._move(key, "gated", "guards run on the candidate head")
        r = checks.sh(["git", "push", remote, refspec], cwd=wt)
        if r.returncode:
            raise RuntimeError(f"{key}: push refused ({r.stderr.strip()[-300:]}); it stays gated, `land` again after fixing")
        core._move(key, "pushed", f"{sha[:9]} to {remote}/{branch}")
        return {"issue": key, "landed": True, "pushed": f"{remote}/{branch}", "sha": sha}


def send_back(issue) -> dict:
    """Re-dispatch a NOT_READY item to its coder with the reviewer's findings as the retry text. A binding NOT_READY has
    already moved the item to coding (this is then `retry`); a NOT_READY recorded without moving it (the manager's, or
    one for a head that has since passed a check) is turned into the same retry here. A stale verdict (not for the
    item's current head) is refused: check and review the new head instead."""
    key, it, _ = core._item(issue)
    last = it["verdicts"][-1] if it["verdicts"] else None
    if it["state"] == "coding" and it["retry_text"].startswith("Review NOT_READY"):
        return core.retry(key)
    if it["state"] not in ("checked", "reviewed") or not last or last["verdict"] != "NOT_READY" or last["sha"] != it["sha"]:
        raise RuntimeError(f"{key} is {it['state']} with no NOT_READY verdict for its head {it['sha'][:9]}: nothing to send back")
    journal.append("retry", issue=it["issue"], key=key, text=f"Review NOT_READY at {last['sha'][:9]} by {last['by']}:\n{last['findings']}")
    core._move(key, "coding", f"NOT_READY by {last['by']} at {last['sha'][:9]}: sent back")
    return core.retry(key)


core.API.update(run=run, land=land, send_back=send_back)
core.WORKER_FORBIDDEN += ("run", "land", "send_back")
