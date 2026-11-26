"""builder-console.stale.acted-on (#6646): the lane's current step, when it has sat in one state longer than `[loop].stale_hours.<state>`,
gets one action per tick and one `stale` journal row (step, age, action, result).

Acted on here: said-done, checking, reviewing, red, fixing, blocked. Not acted on here: done-not-landed, queued, sent, and a paused
or held lane. `q` is the queue module (passed in: queue imports this module)."""
from __future__ import annotations

from pathlib import Path

from fichero_builder import journal

HOURS = {"said-done": 1.0, "checking": 3.0, "reviewing": 3.0, "fixing": 12.0, "red": 12.0, "blocked": 48.0}


def _live(chains: dict | None, lane: dict) -> bool:
    fut = (chains or {}).get(lane["id"])
    return fut is not None and not fut.done()


def act(lane: dict, *, q, chains: dict | None, hours: dict, now: float, gh: str = "gh") -> str | None:
    """The action taken on the lane's current step (a `stale` row, the lane stored), or None: not stale, or nothing to do for its state."""
    if lane.get("paused") or lane["cursor"] >= len(lane["steps"]):
        return None
    s = lane["steps"][lane["cursor"]]
    v = q.state_view(lane, s, now)
    limit = hours.get(v["state"])
    since = max(v["since"], s.get("stale_at", 0.0))
    if limit is None or (now - since) / 3600 < limit:
        return None
    n = s.get("stale_n", 0)
    why = (s.get("why") or "").strip()
    state = v["state"]
    closed = False
    if state == "said-done" and not _live(chains, lane):
        s.pop("settling", None)
        action, result = "run-check", "the claim on the check is cleared; the next tick checks"
    elif state in ("checking", "reviewing") and not _live(chains, lane):
        s["state"], s["why"], s["entered_at"] = "done", "", now
        action, result = "restart", f"the {state} had no live activity; back to said-done, so the check runs again"
    elif state == "red" and n == 0:
        brief = journal.STATE / f"stale-{lane['id']}-{s['step']}.txt"
        brief.parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(Path(q.brief_of(s)).read_text().rstrip("\n") + "\n\n" + q.fix_text(s["step"], "check", why[-1500:]))
        s["resume_brief"], s["rounds"], s["restarts"] = str(brief), 0, 0
        s.pop("red_head", None)
        s["state"], s["why"], s["entered_at"] = "queued", "re-briefed once with the rung's tail", now
        action, result = "re-brief", f"a fresh session with the rung's tail ({brief.name})"
    elif state == "red" or (state == "fixing" and s.get("rounds", 0) > q.ROUNDS):
        s.pop("red_head", None)
        s["state"], s["blocked_at"], s["entered_at"] = "blocked", now, now
        s["why"] = f"{state} past {limit:g} h with no way forward: {why[-300:]}"
        q.alert(lane["id"], s["step"], s["why"], str(journal.STATE / f"question-{lane['id']}-{s['step']}.txt"), ["retry", "park"])
        action, result = "block", "blocked, with an alert"
    elif state == "blocked" and n == 0:
        q.ask(s.get("issues", []), f"{lane['id']} {s['step']}", why or "blocked", gh=gh)
        action, result = "ask", f"asked again on {len(s.get('issues', []))} issue(s)"
    elif state == "blocked":  # asked once already: the residue is filed as an issue and the lane moves on
        title = f"Residue of {lane['id']} {s['step']}: blocked {(now - v['since']) / 3600:.0f} h"
        err = q._gh_quiet(gh, ["issue", "create", "--title", title, "--body", why[:1500] or "(no reason recorded)"])
        s["state"], s["why"], s["entered_at"] = "closed-out", f"residue filed: {err or title}", now
        q.close_alerts(lane["id"], s["step"], "closed out by the stale watch")
        lane["cursor"] += 1
        action, result, closed = "close-out", s["why"], True
    else:
        return None
    s["stale_n"], s["stale_at"] = n + 1, now
    journal.append("stale", lane=lane["id"], step=s["step"], state=state, age_h=round((now - since) / 3600, 1), action=action, result=result)
    if closed:
        q.moved_on(lane, s["step"])
    q.store(lane)
    return action
