"""`builder queue [add|run|pause|resume]`: one long-running worker per lane (a milestone), fed step by step, with no manager in
the loop (dev-workflows.tool.queue, Step 2.6; owner ruling 2026-11-01).

`<state>/queue.json` holds the lanes: id, worktree, cursor, seq, feed, paused, and the steps in build order (step, brief,
issues, waits, state, head, why, rounds, restarts). A step goes queued -> sent -> done -> checking -> reviewing -> landed, or
blocked with its question in `<state>/question-<lane>-<step>.txt`. The worker stays open after `DONE <sha>` (`builder run
--feed`, as the jail user, so it keeps what it has read); this owner-side loop sees its `step` row, runs rebase, patches,
fetch, check, review and the land gate (`work.after_run`), then `builder landed` (push only with --push), then sends the next
brief into the same session. Findings go back as a fix brief, two rounds, then blocked. A new session only when the worker
is gone or at its own 85 % handoff. Pause = idle with nothing sent; resume = send the next brief.
`run` feeds itself from the build order: while fewer than `lanes_n` lanes have steps left, it takes the next build-order
milestone no lane holds (`Procs.next_milestone`), so one command runs a spec to the end and then the next, until the order
is done or a lane blocks on a QUESTION or a cap. With one lane the chain runs inside the tick; with more, each lane's chain
runs in its own thread, so a lane waits only for the ladder lock (`work.after_run`), never for another lane's review."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tomllib
from concurrent.futures import ThreadPoolExecutor
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import check_tool, codemap, jail, journal, land_tool, models, work

ROUNDS, RESTARTS = 2, 2
AUTO_SEND_BACKS = 3  # an external lane's red check is sent back by the loop this many times a batch, then it is an alert
FIX = ("Step {step}: the {kind} did not pass. Fix it on this branch with new commit(s), under the same rules.\n\n{findings}\n\n"
       "When it is committed, end your turn with the exact line DONE <short sha of the branch head>.\n")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", name.lower()).strip("-")


def path() -> Path:
    return journal.STATE / "queue.json"


def load() -> list[dict]:
    return json.loads(path().read_text())["lanes"] if path().is_file() else []


def save(lanes: list[dict]) -> None:
    path().parent.mkdir(parents=True, exist_ok=True)
    tmp = path().with_suffix(".tmp")
    tmp.write_text(json.dumps({"lanes": lanes}, indent=1))
    tmp.replace(path())


def store(lane: dict, expect: tuple | None = None) -> bool:
    """This lane's row back in the file; a step added or a pause set while the chain ran is kept. `expect` = (step, head): the
    write happens only if the file's step still holds that head, checked UNDER the queue lock (a `builder done` at a newer head
    holds that lock through its git work and saves last: a check made before taking the lock would pass and then overwrite it)."""
    with journal.Lock("queue"):
        lanes = load()
        fresh = next((x for x in lanes if x["id"] == lane["id"]), None)
        if expect and fresh and next((st.get("head", "") for st in fresh["steps"] if st["step"] == expect[0]), "") != expect[1]:
            return False
        if fresh:
            lane["paused"] = fresh["paused"]
            for k in ("pane", "hold", "maintainer"):  # set from outside while the tick held its copy (manager 2026-11-02: %537 was lost)
                if k in fresh:
                    lane[k] = fresh[k]
            have = {s["step"] for s in lane["steps"]}
            lane["steps"] += [s for s in fresh["steps"] if s["step"] not in have]
        save([lane if x["id"] == lane["id"] else x for x in lanes])
        return True


def workers(root) -> int:
    f = Path(root) / "harness.toml"
    return int(tomllib.loads(f.read_text()).get("queue", {}).get("workers", 1)) if f.is_file() else 1


def add(lane_id: str, worktree: str, step: str, brief: str, issues: list[int], waits: list[str] | None = None, kind: str = "worker",
        hold: bool | None = None, pane: str = "", maintainer: bool | None = None) -> None:
    """A step at the end of its lane (made when new); a step the lane has already keeps its state."""
    with journal.Lock("queue"):
        lanes = load()
        lane = next((x for x in lanes if x["id"] == lane_id), None)
        if lane is None:
            lane = {"id": lane_id, "worktree": os.path.abspath(worktree), "cursor": 0, "seq": 0, "feed": "", "paused": False, "steps": [], "kind": kind}
            lanes.append(lane)
        elif lane["cursor"] >= len(lane["steps"]) and not any(s["step"] == step for s in lane["steps"]):
            lane.update(kind=kind, worktree=os.path.abspath(worktree))  # a finished lane handed new work takes its kind and tree
        if hold is not None:
            lane["hold"] = hold  # a milestone a person holds: never taken by the intake
        if pane:
            lane["pane"] = pane  # where findings and LANDED are told (an external lane's session)
        if maintainer is not None:
            lane["maintainer"] = maintainer  # the harness builder's lane: its batches change pinned files on purpose (--maintainer)
        if any(s["step"] == step for s in lane["steps"]):
            save(lanes)
            return
        lane["steps"].append({"step": step, "brief": str(brief), "issues": list(issues), "waits": list(waits or []), "state": "queued",
                              "head": "", "why": "", "rounds": 0, "restarts": 0})
        save(lanes)
    journal.append("queue", lane=lane_id, step=step, state="queued", detail=f"after {', '.join(waits or []) or 'nothing'}")


@dataclass
class Procs:
    """What the loop does to the world; the tests replace each one."""
    start: Callable[[dict, dict], object]           # (lane, step) -> a handle: a new session on this step's brief
    alive: Callable[[object], bool]
    send: Callable[[dict, str], None]               # (lane, text): into the running session, as message number lane["seq"]
    rebase: Callable[[dict], str]                   # lane -> '' or why not, before a new step goes in
    row: Callable[[dict], dict | None]              # lane -> the worker's `step` row for lane["seq"], None while it works
    chain: Callable[[dict, dict, Callable], dict]   # (lane, step, stage) -> {ok, kind, why, findings, head}
    landed: Callable[[dict, str, bool], tuple]      # (lane, head, push) -> (rc, output)
    end_of: Callable[[dict], str]                   # lane -> how its worker process ended
    stop: Callable[[dict], None]                    # end the lane's session
    sleep: Callable[[float], None] = time.sleep
    still_open: Callable[[dict, dict], list] = lambda lane, step: []  # (lane, step) -> issues of a landed step not closed, as "#N"
    # taken lane ids -> (lane id, worktree, [{step, brief, issues, waits}]) of the next build-order milestone, or None
    next_milestone: Callable[[set], tuple | None] = lambda taken: None
    build: Callable[[dict], tuple] = lambda lane: (0, "")  # lane -> (rc, output) of the dev build after its milestone landed
    daily_builds: Callable[[], tuple] | None = None  # () -> (rc, output) of `builder daily-builds`; None = no [check.daily_builds]
    verify_all: Callable[[], tuple] = lambda: (0, "")  # () -> (rc, output) of `builder verify-all` over the loop's checkout
    touches_product: Callable[[dict, str], bool] = lambda lane, head: True  # (lane, head) -> does the batch about to land change app/engine product paths
    tell: Callable[[dict, str], str] = lambda lane, text: ""  # (lane, text) -> '' or why: into an external lane's registered pane
    after_land: Callable[[dict, dict, str], None] = lambda lane, step, head: None  # an external lane's batch landed: sweep its land tree
    intake: Callable[[dict], str] = lambda lane: ""  # an external lane -> the sha to take now by itself (thresholds), or ''
    trees: Callable[[list], dict] = lambda paths: {}  # paths -> {path: "HEAD status-hash"}: what a step must leave unmoved (run.loop-machine-checked)
    jail_root: str = ""
    root: str = ""  # the loop's checkout (its harness.toml): the rules warnings at start and the scratch sweep read it


QUIET = ("queued", "blocked", "landed")  # a step state in which the lane's own worker is not moving its tree


def _others(lane: dict, handles: dict, procs: Procs) -> list[str]:
    """The jail root and every other lane's worktree that no worker of its own may be moving now. ponytail: a lane with a live
    session (even a blocked one) or an external lane in flight is skipped, so a stray write there is not seen until it is quiet."""
    out = [procs.jail_root] if procs.jail_root else []
    for x in load():
        if x["id"] == lane["id"] or x["id"] in handles or x["worktree"] == lane["worktree"]:
            continue
        st = x["steps"][x["cursor"]]["state"] if x["cursor"] < len(x["steps"]) else "landed"
        if st in QUIET and not (x.get("kind") == "external" and st == "queued"):
            out.append(x["worktree"])
    return out


def tree_check(lane: dict, s: dict, handles: dict, procs: Procs) -> list[str]:
    """After a step's DONE: each tree snapped when it started that is still quiet must be unmoved (HEAD and `git status`).
    The jail root is skipped when a landing refreshed it meanwhile."""
    snap, since = s.pop("trees", None) or {}, s.pop("trees_at", "")
    if procs.jail_root in snap and any(r.get("event") == "landed" and r.get("step") == "jail-root" and r.get("ts", "") >= since for r in journal.read()):
        snap.pop(procs.jail_root)
    now = procs.trees([p for p in _others(lane, handles, procs) if p in snap])
    return [f"{p}: {snap[p]} -> {now[p]}" for p in now if now[p] != snap[p]]


def _gh_quiet(gh: str, args: list[str], cwd=None) -> str:
    """'' or why the call failed; never raises."""
    try:
        r = subprocess.run([gh, *args], capture_output=True, text=True, timeout=60, cwd=cwd)
    except (subprocess.TimeoutExpired, OSError) as e:
        return str(e)
    return r.stderr.strip()[-200:] if r.returncode else ""


def ask(issues: list[int], where: str, why: str, gh: str = "gh", cwd=None) -> None:
    """A blocked step's QUESTION where the owner sees it (issues-and-labels: a question labels needs-your-decision and
    comments, #6343); a gh that fails is an `ask-failed` row, never a traceback."""
    for n in issues:
        for args in (["issue", "edit", str(n), "--add-label", "needs-your-decision"],
                     ["issue", "comment", str(n), "--body", f"QUESTION (queue {where}): {why.strip()[:1500]}"]):
            if err := _gh_quiet(gh, args, cwd):
                journal.append("queue", lane=where, step="-", state="ask-failed", detail=f"#{n} {args[1]}: {err}"[-300:])


def open_of(issues: list[int], gh: str = "gh", cwd=None) -> list[str]:
    """The issues GitHub does not say are closed; one it cannot read counts, and says so. Never raises: the step has landed by now."""
    out = []
    for n in issues:
        try:
            r = subprocess.run([gh, "issue", "view", str(n), "--json", "state", "--jq", ".state"], capture_output=True, text=True, timeout=60, cwd=cwd)
        except (subprocess.TimeoutExpired, OSError):
            out.append(f"#{n} (could not read)")
            continue
        if r.returncode:
            out.append(f"#{n} (could not read)")
        elif r.stdout.strip().upper() != "CLOSED":
            out.append(f"#{n}")
    return out


def tick_lane(lane: dict, procs: Procs, handles: dict, workers_n: int, push: bool, out, chains: dict | None = None) -> bool:
    """One pass over one lane. False when it can do nothing more without a person: finished, blocked or paused."""
    def move(s, state, detail="", only_head=None):
        s["state"], s["why"] = state, detail[-500:]
        s.pop("settling", None)  # a final write ends the claim
        if only_head is not None and not store(lane, expect=(s["step"], only_head)):
            return  # a newer head took the step while this chain ran: its stale copy is not written, nor said
        journal.append("queue", lane=lane["id"], step=s["step"], state=state, detail=detail[-300:])
        out(f"{lane['id']} {s['step']}: {state}" + (f" ({detail.strip().splitlines()[-1][:120]})" if detail.strip() else ""))
        if only_head is None:
            store(lane)

    def findings_to_lane(s, why, evidence, q, state="told", note=""):
        n = sum(1 for p in journal.STATE.glob(f"findings-{lane['id']}-*.txt")) + 1
        f = journal.STATE / f"findings-{lane['id']}-{n}.txt"
        f.write_text(f"{lane['id']} batch {s['step']} at {s.get('head', '')[:9]}: {why}\n\nEvidence: {evidence or q}\n")
        err = procs.tell(lane, f"FINDINGS for {lane['id']} at {s.get('head', '')[:9]}: {why.splitlines()[0][:300]} (full: {f}). "
                               f"Fix on your branch (a conflict: rebase onto origin/integration), then run: {done_cmd(lane['id'])}")
        journal.append("queue", lane=lane["id"], step=s["step"], state=state if not err else "tell-refused", detail=err or note + str(f))

    def block(s, why, actions=ACTIONS, evidence="", auto_send_back=False):
        q = journal.STATE / f"question-{lane['id']}-{s['step']}.txt"
        q.write_text(f"QUESTION: {why}\n")
        if auto_send_back:
            s["auto_sb"] = s.get("auto_sb", 0) + 1  # before the move, which stores it
        move(s, "blocked", why)
        if auto_send_back:  # a red the manager would only send back: the lane gets the findings, no alert (manager 2026-11-03)
            findings_to_lane(s, why, evidence, q, state="auto-send-back",  # ONE row: the count, the reason and the findings file (review 361)
                             note=f"sent back automatically ({s['auto_sb']} of {AUTO_SEND_BACKS}): {why.splitlines()[0][:200]}; findings in ")
            return False
        alert(lane["id"], s["step"], why, evidence or str(q), list(actions))
        if lane.get("kind") == "external" and s.get("land_tree"):  # the lane fixes it on its branch: tell it where the findings are
            findings_to_lane(s, why, evidence, q)
        return False

    h = handles.get(lane["id"])
    if lane.get("stop_at") and (h is None or not procs.alive(h) or time.time() >= lane["stop_at"]):  # `queue stop`: the grace is over
        if h is not None:
            procs.stop(lane)
            del handles[lane["id"]]
        lane["feed"] = ""
        lane.pop("stop_at")
        if lane["cursor"] < len(lane["steps"]) and (s := lane["steps"][lane["cursor"]])["state"] == "sent":
            cont = journal.STATE / f"stopped-{lane['id']}-{s['step']}.txt"
            cont.write_text(Path(s.get("resume_brief") or s["brief"]).read_text().rstrip("\n") + "\n\n" + STOPPED)
            s["resume_brief"] = str(cont)
            move(s, "queued", "stopped by the owner: resume starts a fresh session from the tree")
        else:
            store(lane)
        journal.append("queue", lane=lane["id"], step="-", state="stopped", detail="the session is closed; the tree is kept")
        return False
    if lane["cursor"] >= len(lane["steps"]):
        if h is not None:
            procs.stop(lane)
            del handles[lane["id"]]
        if push and lane["steps"] and not lane.get("built"):  # dev-workflows.run.loop-rolls-on: one dev build per milestone landed for real
            lane["built"] = True
            store(lane)
            if lane.get("kind") == "external":
                # owner 2026-11-03: a dev build only at a milestone's end or by hand, never per landing (a post-landing build held the heavy
                # lock 54 min while checks waited); an external lane's batches have no milestone end the loop can see
                journal.append("queue", lane=lane["id"], step="-", state="build-skipped",
                               detail="an external lane's batch landed: the dev build waits for the milestone's end or `builder build --dev`")
                return False

            def build_it():
                rc, output = procs.build(lane)
                journal.append("queue", lane=lane["id"], step="-", state="built" if rc == 0 else "build-failed", detail=output[-300:])
                if rc:  # an alert to read, never a stop: the roll-on goes on
                    alert(lane["id"], "build", f"the dev build after {lane['id']} failed: {(output.strip().splitlines() or [''])[-1]}",
                          str(journal.STATE), [])
            if chains is None:
                build_it()
            else:  # the build is a quarter of an hour: inline it stopped every tick for 17 min (2026-11-02, after harness-unblock landed)
                t = threading.Thread(target=build_it, name=f"build-{lane['id']}", daemon=True)
                BUILDS.append(t)
                t.start()
        return False
    s = lane["steps"][lane["cursor"]]
    if s["state"] == "blocked":
        return False
    if lane.get("kind") == "external" and s["state"] in ("queued", "sent"):
        return False  # no worker: the lane's own session says `builder done <lane> <sha>` (dev-workflows.run.loop-external-lane)
    fut = (chains or {}).get(lane["id"])
    if fut is not None and not fut.done():
        return True  # its check or review is running in its own thread
    if h is not None and not procs.alive(h):
        del handles[lane["id"]]
        h, lane["feed"], end = None, "", procs.end_of(lane)
        if end == "parked":
            return block(s, "the worker was parked (a cap or a provider refusal); read the journal, then `builder queue resume`")
        if s["state"] == "sent":
            s["restarts"] += 1
            if s["restarts"] > RESTARTS:
                return block(s, f"the worker ended {end!r} {s['restarts']} times on this step")
            move(s, "queued", f"the worker ended {end!r}: a new session next tick")
            return True
    if h is None and (s["state"] == "sent" or (s["state"] == "queued" and lane["feed"])):  # no handle: this loop restarted; the old session may be up
        procs.stop(lane)  # ponytail: it stops within its own tick and the new one starts one tick later; two workers never share a worktree for long
        lane["feed"] = ""
        move(s, "queued", "stopping the session this loop lost track of")
        return True
    if s["state"] == "queued":
        # the file, not this tick's copy: a pause written after the tick loaded the lanes must stop the start (manager 2026-11-02)
        if lane["paused"] or next((x.get("paused") for x in load() if x["id"] == lane["id"]), False):
            lane["paused"] = True
            return False
        s["trees"], s["trees_at"] = procs.trees(_others(lane, handles, procs)), time.strftime("%Y-%m-%dT%H:%M:%S")  # before the worker can move anything
        try:
            if h is None:
                if len(handles) >= workers_n:
                    return True
                lane["seq"] += 1
                handles[lane["id"]] = procs.start(lane, s)
            else:
                if why := procs.rebase(lane):
                    return block(s, why)
                lane["seq"] += 1
                procs.send(lane, Path(s.get("resume_brief") or s["brief"]).read_text())  # a send-back or a fix round writes it (review 2026-11-02: the finding never reached a live session)
        except (RuntimeError, OSError, ValueError, KeyError) as e:  # a refusal is a row, never a traceback
            return block(s, f"the step could not start: {e}")
        move(s, "sent", f"message {lane['seq']}")
        return True
    if s["state"] == "sent":
        row = procs.row(lane)
        if row is None:
            return True
        if not row.get("moved"):
            return block(s, "the worker said DONE with no commit on this step")
        move(s, "done", "")
        if moved := tree_check(lane, s, handles, procs):  # an alert to read; the step goes on: the stray write was not in its tree
            alert(lane["id"], s["step"], "a tree outside the step's own moved: " + "; ".join(moved), str(journal.STATE / "journal.jsonl"), [])
    if s["state"] == "done" and (lane["paused"] or next((x.get("paused") for x in load() if x["id"] == lane["id"]), False)):
        lane["paused"] = True  # manager 2026-11-02: a paused lane is never checked; its DONE head waits for `queue resume`
        return False

    h0 = s.get("head", "")

    def stage_cb(stage: str) -> None:
        move(s, stage, "", only_head=h0)  # a `builder done` at a newer head took the step: this old chain must not write its stale copy back over it

    def chain() -> dict:
        try:
            return procs.chain(lane, s, stage_cb)
        except Exception as e:  # noqa: BLE001 - one lane's bug is that lane's error, never the loop's death (2026-11-03: an AttributeError killed it on every ladder)
            journal.append("loop", state="lane-error", lane=lane["id"], step=s["step"], detail=traceback.format_exc()[-1500:])
            return {"ok": False, "kind": "error", "why": f"{type(e).__name__}: {e}"}
    if chains is None:
        r = chain()
    elif fut is None:
        if DRAIN[0]:  # new code waits: no new chain starts, so the loop can re-exec between chains
            return True
        if (hold := journal.manual_hold()) and touches_build(lane, s, getattr(procs, "root", None)):
            # owner 2026-11-06: a held Xcode build rung sat on the only chain worker for an hour; a batch that would build waits HERE,
            # holding no worker, one `held` row per head, and starts by itself once the person's hold ends
            if lane.get("held_head") != s.get("head"):
                lane["held_head"] = s.get("head")
                journal.append("queue", lane=lane["id"], step=s["step"], state="held", detail=f"waits for the heavy-lock hold ({hold[:80]}): its batch builds Swift")
                store(lane, expect=(s["step"], s.get("head", "")))  # review 116: a newer `builder done` saved meanwhile wins
            return True
        if running := [k for k, f in chains.items() if k not in ("pool", lane["id"]) and not f.done()]:
            if len(running) >= chains["pool"]._max_workers:  # the pool queues it with no word: say so (2026-11-05: batch-25 waited 40 min unseen)
                journal.append("queue", lane=lane["id"], step=s["step"], state="waiting-for-worker",
                               detail=f"waiting for a chain worker ({len(running)} ahead of it, running or queued: {', '.join(sorted(running))}; [loop].lanes = {chains['pool']._max_workers})")
        chains[lane["id"]] = chains["pool"].submit(chain)
        chains[lane["id"]].head = s.get("head", "")
        return True
    else:
        f = chains.pop(lane["id"])
        r = f.result()
        if (ran := getattr(f, "head", h0)) != h0:  # the chain ran on an OLDER head: a `builder done` at a newer one cancelled it. It ends silently: no alert, no tell, no finding (manager 2026-11-03)
            journal.append("queue", lane=lane["id"], step=s["step"], state="stale-result", detail=f"the check of {ran[:9]} was cancelled by {h0[:9]}: dropped without a word")
            return True
    # the ONE claim of the chain's outcome: a compare-and-set of (step, head) under the queue lock. Every write a chain makes to the step
    # is `store(expect=...)` (the stage callbacks above, this claim); after it the step is `settling`, which `builder done` refuses, so no
    # outcome below (landed, blocked, a fix brief) can overwrite a newer head, and no unlocked read decides anything (review -92/-94/-96).
    if not r["ok"] or not r.get("head"):
        s["settling"] = True
    else:
        s["head"], s["settling"] = r["head"], True
    if not store(lane, expect=(s["step"], h0)):
        journal.append("queue", lane=lane["id"], step=s["step"], state="stale-result", detail=f"the check of {h0[:9]} ended after a newer head took the step: dropped")
        return True
    if r["ok"]:
        s["product"] = bool(procs.touches_product(lane, r["head"]))  # BEFORE landing: origin/integration is still the base; kept by the landing's one store
        rc, output = procs.landed(lane, r["head"], push)
        if rc:
            return block(s, output)
        if lane.get("kind") == "external" and s.get("land_tree"):
            err = procs.tell(lane, f"LANDED {r['head'][:9]}: rebase onto origin/integration at your next step boundary.")
            journal.append("queue", lane=lane["id"], step=s["step"], state="told" if not err else "tell-refused", detail=err or "LANDED")
            procs.after_land(lane, s, r["head"])
        left = procs.still_open(lane, s)  # a row, not a close: only `builder landed` closes, on a Fixes line (owner ruling)
        close_alerts(lane["id"], s["step"], f"the step landed at {r['head'][:9]}")
        lane["cursor"] += 1  # ONE write ends the landing: the step is landed and the cursor is past it in the same store, so no `builder done` can run between the two
        move(s, "landed", f"landed {r['head'][:9]}" + (" (pushed)" if push else " (not pushed)") + (f"; still open: {', '.join(left)}" if left else ""))
        if push and lane.get("kind") != "external" and lane["cursor"] >= len(lane["steps"]) and any(x.get("product") for x in lane["steps"]):
            # dev-workflows.run.verify-all (owner 2026-11-03): a MILESTONE's last step landed (a worker lane has no step left) and some step touched the product: ONE verify-all once every lane is idle
            (journal.STATE / VERIFY_PENDING).write_text(r["head"])
        if left:
            journal.append("queue", lane=lane["id"], step=s["step"], state="issue-open", detail=", ".join(left))
        return True
    if r.get("kind") in ("needs-maintainer", "weakened-tests", "red-on-base", "pinned-new", "guard-data"):  # a pinned check or a test changed on purpose: the manager's call
        s["approve_kind"] = r["kind"]
        s["approvals"] = r.get("approvals") or []  # every reason the refusal listed: one approve sets them all
        return block(s, r["why"], ("approve", "send-back"), r.get("evidence", ""))
    if r.get("kind") in ("red", "not-ready", "refused") and s["rounds"] < ROUNDS and lane.get("kind") != "external":  # external: an alert
        s["rounds"] += 1
        text = FIX.format(step=s["step"], kind=r["kind"], findings=r.get("findings") or r["why"])
        live = handles.get(lane["id"])
        if live is not None and procs.alive(live):  # the findings into the running session (dev-workflows.run.loop-tell)
            lane["seq"] += 1
            procs.send(lane, text)
            move(s, "sent", f"fix brief, round {s['rounds']}: {r['why']}")
            return True
        fix = journal.STATE / f"fix-{lane['id']}-{s['step']}-{s['rounds']}.txt"  # gone: a new session on the brief plus the findings
        fix.write_text(Path(s["brief"]).read_text().rstrip("\n") + "\n\n" + text)
        s["resume_brief"], lane["feed"] = str(fix), ""
        move(s, "queued", f"fix brief, round {s['rounds']}, in a new session: {r['why']}")
        return True
    # an external lane fixes its own reds: send-back (findings to its pane, its next done re-takes); park keeps the lane too
    acts = ("send-back", "retry", "park") if lane.get("kind") == "external" else ACTIONS
    auto = (lane.get("kind") == "external" and bool(s.get("land_tree")) and r.get("kind") in ("red", "not-ready", "refused")
            and s.get("auto_sb", 0) < AUTO_SEND_BACKS)  # the cap spent, the alert comes as before
    return block(s, f"{r['why']}\n{r.get('findings', '')}".strip(), acts, evidence=r.get("evidence", ""), auto_send_back=auto)


ACTIONS = ("retry", "park", "ask-owner")
STOP_NOTE = ("STOP (the owner): commit what is green now, leave the rest uncommitted in the worktree, and end your session. "
             "The lane resumes later in a fresh session from this tree.")
STOPPED = ("Continue from the tree: this step was stopped by the owner mid-way. Its commits so far are on the branch and any "
           "uncommitted work is still in the worktree; read them first, then finish the step.")


def intake_sha(lane: dict, branch: str, commits: int, hours: float, now: float | None = None) -> str:
    """The lane's HEAD when it is a finished step (`(Step ` in its subject or a `Behaviour:` trailer) and the lane has `commits`
    commits past origin/<branch>, or its oldest unlanded one is `hours` old; else ''."""
    g = ["git", "-c", "safe.directory=*", "-C", lane["worktree"]]
    if not missing(lane["worktree"], branch):  # every commit is on origin by patch (a pre-rebase copy of a landed batch)
        return ""
    log = subprocess.run(g + ["log", "--format=%H %ct", f"origin/{branch}..HEAD"], capture_output=True, text=True).stdout.split("\n")
    log = [x.split() for x in log if x.strip()]
    if not log:
        return ""
    msg = subprocess.run(g + ["log", "-1", "--format=%B"], capture_output=True, text=True).stdout
    if "(Step " not in msg.split("\n", 1)[0] and not re.search(r"(?m)^Behaviour:", msg):
        return ""
    old = (now or time.time()) - int(log[-1][1])
    return log[0][0] if len(log) >= commits or old >= hours * 3600 else ""


def done_cmd(lane_id: str) -> str:
    """The exact command an external lane runs to queue its next batch (manager 2026-11-02: lanes said DONE to a person)."""
    pkg = Path(__file__).resolve().parents[1]
    return f"cd {shlex.quote(str(pkg))} && PYTHONPATH=. {shlex.quote(sys.executable)} -m fichero_builder done {lane_id} --state {shlex.quote(str(journal.STATE))}"


def external_owner(spec: str, title: str = "") -> str:
    """The external lane with steps left whose brief names this spec (or milestone), or ''. Manager 2026-11-02: the loop
    planned `Sharing & Pairing` while lane-sharing (external) worked that spec."""
    stem = Path(spec).name
    for x in load():
        if x.get("kind") != "external" or x.get("hold") or x["cursor"] >= len(x["steps"]):
            continue
        try:
            text = Path(x["steps"][x["cursor"]]["brief"]).read_text()
        except OSError:
            continue
        if stem in text or (title and f"`{title}`" in text):
            return x["id"]
    return ""


def missing(worktree: str, branch: str = "integration", head: str = "HEAD") -> int:
    """How many commits of head origin/<branch> lacks by patch (`git cherry`: '+'); -1 when git cannot say."""
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", worktree, "cherry", f"origin/{branch}", head], capture_output=True, text=True)
    return sum(1 for ln in r.stdout.splitlines() if ln.startswith("+")) if r.returncode == 0 else -1


def lane_head(worktree: str) -> str:
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def related(worktree: str, old: str, new: str) -> bool:
    """`new` is a descendant of `old`, or a rewrite of it (some commit of old's patch is in new: `git cherry` '-')."""
    g = ["git", "-c", "safe.directory=*", "-C", worktree]
    if subprocess.run(g + ["merge-base", "--is-ancestor", old, new], capture_output=True).returncode == 0:
        return True
    r = subprocess.run(g + ["cherry", old, new], capture_output=True, text=True)
    return r.returncode == 0 and any(ln.startswith("-") for ln in r.stdout.splitlines())


APPROVALS = ("approve_red", "approve_weakened", "approve_pinned_new", "approve_guard_data", "approve_kind", "approvals", "approved_head", "approved_tests", "maintainer")


def land_tree(lane: dict, sha: str) -> tuple[str, str]:
    """(path, '') of `land-<lane>` beside the lane's worktree, made or reset at `sha` as the owner; the lane's own tree and
    branch are never touched (its agent works there). ('', why) when git refuses."""
    path = str(Path(lane["worktree"]).resolve().parent / f"land-{lane['id']}")
    g = ["git", "-c", "safe.directory=*"]
    if Path(path).is_dir():
        r = subprocess.run(g + ["-C", path, "checkout", "-q", "-f", "-B", f"land-{lane['id']}", sha], capture_output=True, text=True)
    else:
        r = subprocess.run(g + ["-C", lane["worktree"], "worktree", "add", "-q", "-f", "-B", f"land-{lane['id']}", path, sha], capture_output=True, text=True)
    return (path, "") if r.returncode == 0 else ("", (r.stderr or r.stdout).strip()[-300:])


IN_LADDER = ("checking", "reviewing", "sent")


def done(lane_id: str, sha: str = "") -> str:
    """`builder done <lane> [sha]`: an external lane's DONE (dev-workflows.run.loop-external-intake). The sha (default: the
    lane's HEAD now) is a snapshot: `land-<lane>` is made there and the chain takes it, so later commits go in the next batch.
    A blocked step is re-taken from the new sha (the lane fixed its findings); a finished lane gets a new batch step; a batch
    already in the ladder refuses (one at a time). '' or why it is refused."""
    with journal.Lock("queue"):
        lanes = load()
        lane = next((x for x in lanes if x["id"] == lane_id), None)
        s = None
        if lane is None or lane.get("kind") != "external":
            why = f"no external lane {lane_id!r}"
        elif lane["cursor"] < len(lane["steps"]) and lane["steps"][lane["cursor"]].get("settling"):  # a chain's outcome is being written, whatever state the chain left the step in (it may return before its first stage)
            why = f"{lane_id} has a batch settling its outcome: one at a time; run done again once it is written"
        elif lane["cursor"] < len(lane["steps"]) and lane["steps"][lane["cursor"]]["state"] in IN_LADDER and not (
                lane["steps"][lane["cursor"]]["state"] in ("checking", "reviewing") and not lane["steps"][lane["cursor"]].get("settling")
                and (sha := sha or lane_head(lane["worktree"]))
                and sha != lane["steps"][lane["cursor"]].get("head") and lane["steps"][lane["cursor"]].get("head")
                and related(lane["worktree"], lane["steps"][lane["cursor"]]["head"], sha)):
            why = f"{lane_id} has a batch in the ladder: one at a time; run done again after it lands (a newer head of the same work supersedes it)"
        elif not (sha := sha or lane_head(lane["worktree"])) and Path(lane["worktree"]).is_dir():
            why = f"cannot read {lane_id}'s HEAD in {lane['worktree']}"
        elif Path(lane["worktree"]).is_dir() and missing(lane["worktree"], "integration", sha) == 0:
            why = f"every commit of {sha[:9]} is already on origin/integration (git cherry): nothing to land"
        else:
            if lane["cursor"] >= len(lane["steps"]):  # finished: the next batch
                n = sum(1 for x in lane["steps"] if x["step"].startswith("batch-")) + 1
                lane["steps"].append({"step": f"batch-{n}", "brief": lane["steps"][-1]["brief"] if lane["steps"] else "", "issues": [], "waits": [],
                                      "state": "queued", "head": "", "why": "", "rounds": 0, "restarts": 0})
            s = lane["steps"][lane["cursor"]]
            # no tree on this machine (a lane named by hand): the old DONE, taken from the lane's worktree
            path, why = land_tree(lane, sha) if Path(lane["worktree"]).is_dir() else ("", "")
            if not why and s["state"] in ("checking", "reviewing"):  # a newer head of the same work: the old check is cancelled, its approvals and alerts end with it (only once the new head is taken: a refused done cancels nothing)
                from fichero_builder import check_tool
                old_head = s.get("head", "")
                journal.STATE.mkdir(parents=True, exist_ok=True)
                check_tool.cancel_file(old_head).write_text(sha)
                for k in APPROVALS:
                    s.pop(k, None)
                journal.append("queue", lane=lane_id, step=s["step"], state="superseded", detail=f"{old_head[:9]} by {sha[:9]}: its check is cancelled")
            if not why:
                s.pop("settling", None)
                s.update(state="done", head=sha, why=f"DONE {sha} (external)", rounds=0, restarts=0, **({"land_tree": path} if path else {}))
                save(lanes)
    journal.append("queue", lane=lane_id, step=s["step"] if not why else "-", state="done" if not why else "done-refused", detail=why or sha)
    if not why:
        close_alerts(lane_id, s["step"], f"superseded by the new head {sha[:9]}")
    return why


def close_alerts(lane_id: str, step: str, why: str) -> list[str]:
    """Manager defect 2026-11-02: an alert about a superseded head stayed open on the console. Every open alert of this lane and
    step is answered `superseded` (never park: that would act on the live step), so a new head or a passed step clears them."""
    rows = journal.read()
    answered = {r.get("id") for r in rows if r.get("event") == "alert-answer" and r.get("ok")}
    ids = [r["id"] for r in rows if r.get("event") == "alert" and r.get("lane") == lane_id and r.get("step") == step and r["id"] not in answered]
    for i in ids:
        journal.append("alert-answer", id=i, action="superseded", ok=True, detail=why)
    return ids


def alert(lane_id: str, step: str, why: str, evidence: str, actions: list[str]) -> str:
    """One `alert` row: what failed in a line, where its evidence is, what the manager may answer (dev-workflows.run.loop-alerts)."""
    n = sum(1 for r in journal.read() if r.get("event") == "alert") + 1
    aid = f"{lane_id}-{step}-{n}"
    journal.append("alert", id=aid, lane=lane_id, step=step, what=(why.strip().splitlines() or [""])[0][:300], evidence=evidence, actions=actions)
    return aid


def _alert_kind(r: dict) -> tuple:
    """What makes two alerts the same alert for Dismiss: lane, step, and the text before its first `;`, its numbers masked."""
    return (r.get("lane"), r.get("step"), re.sub(r"\d+", "N", str(r.get("what", "")).split(";")[0]).strip())


def answer(alert_id: str, action: str, gh: str = "gh", cwd=None) -> tuple[int, str]:
    """The manager's one verb: retry or approve re-run the step, send-back gives it to a new session with the finding,
    park leaves it, ask-owner puts it on GitHub for the owner. An action the alert does not offer is refused, with a row."""
    rows = journal.read()
    if alert_id == "all" and action == "dismiss":  # owner 2026-11-08: Dismiss All answers every open alert at once
        answered = {r.get("id") for r in rows if r.get("event") == "alert-answer" and r.get("ok")}
        ids = list(dict.fromkeys(r["id"] for r in rows if r.get("event") == "alert" and r.get("id") not in answered))
        for i in ids:
            journal.append("alert-answer", id=i, action="dismiss", ok=True, detail="dismissed with all, from the console")
        return 0, f"dismissed {len(ids)} open alert(s)"
    a = next((r for r in reversed(rows) if r.get("event") == "alert" and r.get("id") == alert_id), None)
    if a is not None and action == "dismiss":  # owner 2026-11-04: an alert never hangs around; dismiss answers it and changes nothing else
        # owner 2026-11-05: Dismiss "did nothing": 75 identical runner alerts were open, and each click only showed the next one. It
        # answers every open alert of the same kind (lane, step, and the text before its first `;` with the numbers masked)
        answered = {r.get("id") for r in rows if r.get("event") == "alert-answer" and r.get("ok")}
        same = [r["id"] for r in rows if r.get("event") == "alert" and r.get("id") not in answered and r.get("id") != alert_id
                and _alert_kind(r) == _alert_kind(a)]
        journal.append("alert-answer", id=alert_id, action="dismiss", ok=True, detail="dismissed from the console")
        for other in dict.fromkeys(same):
            journal.append("alert-answer", id=other, action="dismiss", ok=True, detail=f"dismissed with {alert_id}: the same alert")
        return 0, f"{alert_id}: dismissed" + (f", with {len(set(same))} open alert(s) of the same kind" if same else "")
    if a is None or (action not in a.get("actions", []) and not (action == "park" and not a.get("actions"))):  # a no-action alert may be parked
        why = f"no alert {alert_id!r}" if a is None else f"{action!r} is not one of {a['actions']}"
        journal.append("alert-answer", id=alert_id, action=action, ok=False, detail=why)
        return 1, f"REFUSED: {why}"
    with journal.Lock("queue"):
        lanes = load()
        lane = next((x for x in lanes if x["id"] == a["lane"]), None)
        s = next((x for x in (lane or {}).get("steps", []) if x["step"] == a["step"]), None)
        if s is None and action == "park":  # nothing to leave in place: the alert is answered (a plan's questions)
            journal.append("alert-answer", id=alert_id, action=action, ok=True, detail="parked; no lane or step behind it")
            return 0, f"{alert_id}: park"
        if s is None:
            journal.append("alert-answer", id=alert_id, action=action, ok=False, detail="the lane or step is gone")
            return 1, "REFUSED: the lane or step is gone"
        if action in ("retry", "approve", "send-back"):
            # an external lane has no worker to send a step to: retry and approve re-take its snapshot; send-back waits for its done
            again = "done" if action == "approve" or (lane.get("kind") == "external" and action == "retry" and s.get("head")) else "queued"
            said = f"{a.get('what', '')}\n{s.get('why', '')}"
            s.update(state=again, rounds=0, restarts=0, why="")
            if action == "approve":  # manager 2026-11-02: an approve binds to this head and the tests the alert named; a new head clears it
                # one head's approvals ACCUMULATE (manager 2026-11-03: sharing bb3 was asked about the same test three times,
                # each approve replacing the last one's files); a new head starts empty
                had = set(s.get("approved_tests") or ()) if s.get("approved_head") == s.get("head", "") else set()
                s["approved_head"] = s.get("head", "")
                s["approved_tests"] = sorted(had | set(re.findall(r"[\w./-]+\.(?:py|json)", said)))
            if action == "approve" and s.get("approvals"):  # every reason the alert listed (maintainer, weakened, pinned-new, red)
                for k in s["approvals"]:
                    s[k] = True
            elif action == "approve" and s.get("approve_kind") == "pinned-new":
                s["approve_pinned_new"] = True  # the chain re-runs the check recording the new pinned files as approved
            elif action == "approve" and s.get("approve_kind") == "red-on-base":
                s["approve_red"] = True  # the chain re-runs the check recording the approval in the red-on-base row
            elif action == "approve" and s.get("approve_kind") == "weakened-tests":
                s["approve_weakened"] = True  # the chain re-runs the check recording the approval (the check row says so)
            elif action == "approve":
                s["maintainer"] = True  # the chain runs the check with --maintainer
            if action == "send-back":
                fix = journal.STATE / f"sendback-{alert_id}.txt"
                fix.write_text(Path(s["brief"]).read_text().rstrip("\n") + f"\n\nSent back by the manager: {a['what']}\nEvidence: {a['evidence']}\n")
                s["resume_brief"] = str(fix)
            lane["paused"] = False
            save(lanes)
    if action == "ask-owner":
        ask(s["issues"], f"{a['lane']} {a['step']}", f"{a['what']} (evidence: {a['evidence']})", gh=gh, cwd=cwd)
    if action in ("send-back", "park") and lane is not None and lane.get("kind") == "external":  # the lane fixes it: tell it how to come back
        from fichero_builder import tell as tell_mod
        rc, out = tell_mod.send(lane["pane"], f"SENT BACK ({action}) {a['lane']} {a['step']}: {a['what'][:300]} (evidence: {a['evidence']}). "
                                f"Fix on your branch (a conflict: rebase onto origin/integration), then run: {done_cmd(a['lane'])}") if lane.get("pane") else (1, "no registered pane")
        journal.append("queue", lane=a["lane"], step=a["step"], state="told" if rc == 0 else "tell-refused", detail=out[-200:])
    journal.append("alert-answer", id=alert_id, action=action, ok=True, detail="")
    return 0, f"{alert_id}: {action}"


def heartbeat_check(tick_s: float = 30.0, ticks: int = 3, now: float | None = None) -> str | None:
    """The watchdog (dev-workflows.run.loop-alerts): reads only the journal. No `loop` tick row for more than `ticks` ticks
    is an alert, once per silence (a later tick row ends it). Returns the new alert's id, or None."""
    rows = journal.read()
    i = next((k for k in range(len(rows) - 1, -1, -1) if rows[k].get("event") == "loop" and rows[k].get("state") == "tick"), -1)
    last = time.mktime(time.strptime(rows[i]["ts"], "%Y-%m-%dT%H:%M:%S")) if i >= 0 else None
    age = (now or time.time()) - last if last is not None else None
    if age is not None and age <= ticks * tick_s:
        answered = {r.get("id") for r in rows if r.get("event") == "alert-answer" and r.get("ok")}
        for r in rows[:i]:  # the silence ended: its alert is answered, so it never hangs around (owner 2026-11-04)
            if r.get("event") == "alert" and r.get("step") == "heartbeat" and r.get("id") not in answered:
                journal.append("alert-answer", id=r["id"], action="loop-back", ok=True, detail="the loop ticks again")
        return None
    if any(r.get("event") == "alert" and r.get("step") == "heartbeat" for r in rows[i + 1:]):
        return None  # already said for this silence
    what = f"no loop tick for {int(age)} s (> {ticks} ticks of {tick_s:g} s)" if age is not None else "no loop tick in the journal"
    # ponytail: no action to answer: KeepAlive restarts a dead loop; a wedged one needs the owner (launchctl kickstart -k)
    return alert("loop", "heartbeat", what, str(journal.path()), [])


def restart_loop(root, tick_s: float = 30.0) -> int:
    """The watchdog's one restart per silence: the stale loop (loop.pid) and its children are killed, a new `builder loop` starts
    detached from the checkout's package, and loop.pid names it. A wedged tick never recovers by itself (2026-11-02)."""
    journal.STATE.mkdir(parents=True, exist_ok=True)
    pidf = journal.STATE / "loop.pid"
    try:
        old = int(pidf.read_text().strip())
    except (OSError, ValueError):
        old = 0
    if not old:  # no pid to kill: a second loop would tick beside the stuck one (review 2026-11-02), so say so and start nothing
        journal.append("loop", state="restart-refused", detail="no loop.pid: the loop has not written its pid, nothing was started")
        return 0
    if old:
        def kill_tree(pid: int) -> None:  # the whole tree: a build's script and xcodebuild are grandchildren and outlive a parent-only kill (2026-11-02)
            for c in subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split():
                kill_tree(int(c))
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        kill_tree(old)
    pkg = Path(__file__).resolve().parents[1]
    log = open(journal.STATE / "loop.out", "a")
    p = subprocess.Popen([sys.executable, "-m", "fichero_builder", "loop", "--root", str(root), "--tick", f"{tick_s:g}", "--state", str(journal.STATE)],
                         cwd=str(pkg), env={**os.environ, "PYTHONPATH": str(pkg)}, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    pidf.write_text(f"{p.pid}\n")
    journal.append("loop", state="restarted", detail="restarted by the heartbeat watchdog", pid=p.pid, was=old)
    return p.pid


def launch_agents(root, out, *, state=None, tick_s: float = 30.0, port: int = 8766) -> list[Path]:
    """The owner's three LaunchAgents (dev-workflows.run.loop, run.loop-launchd): `builder loop` and the console (`builder status`)
    kept alive and started at login, and `builder heartbeat` every three ticks. All run as the owner from the checkout's package;
    logs beside the journal."""
    import plistlib

    pkg, out = Path(__file__).resolve().parents[1], Path(out)
    logs = Path(state) if state else journal.STATE
    st = ["--state", str(state)] if state else []
    jobs = {"loop": (["loop", "--root", str(root), "--tick", f"{tick_s:g}", *st], {"KeepAlive": True, "RunAtLoad": True}),
            "heartbeat": (["heartbeat", "--tick", f"{tick_s:g}", *st], {"StartInterval": int(3 * tick_s)}),
            "console": (["status", "--port", str(port), "--root", str(root), *st], {"KeepAlive": True, "RunAtLoad": True})}
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, (args, when) in jobs.items():
        label = f"local.builder.{name}"
        f = out / f"{label}.plist"
        f.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": [sys.executable, "-m", "fichero_builder", *args],
                                      "WorkingDirectory": str(logs), "EnvironmentVariables": {"PYTHONPATH": str(pkg), "PATH": os.environ.get("PATH", "")},
                                      "StandardOutPath": str(logs / f"{name}.log"), "StandardErrorPath": str(logs / f"{name}.log"), **when}))
        paths.append(f)
    return paths



def load_agents(paths, run=subprocess.run) -> list[str]:
    """`builder launchd --load`: each agent booted out (an old copy, ignored when none) and bootstrapped into the owner's GUI
    domain, so a reboot starts the loop and the console by themselves. One line per agent: loaded, or launchctl's own error."""
    dom = f"gui/{os.getuid()}"
    lines = []
    for p in paths:
        run(["launchctl", "bootout", f"{dom}/{Path(p).stem}"], capture_output=True, text=True)
        r = run(["launchctl", "bootstrap", dom, str(p)], capture_output=True, text=True)
        lines.append(f"loaded {Path(p).stem}" if r.returncode == 0 else f"FAILED {Path(p).stem}: {(r.stderr or r.stdout).strip()[-200:]}")
    return lines


def other_loop() -> int:
    """The pid of a live `builder loop` other than this process named in loop.pid, else 0. A launchd loop at login and a hand-started
    one must never tick together; a pid the reboot left behind (dead, or reused by another program) is no loop."""
    try:
        pid = int((journal.STATE / "loop.pid").read_text().strip())
    except (OSError, ValueError):
        return 0
    if pid == os.getpid():
        return 0
    cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return pid if "fichero_builder loop" in cmd else 0


SHELLS = {"zsh", "bash", "sh", "fish", "login"}


def repane(listing: str | None = None) -> list[str]:
    """dev-workflows.run.loop-launchd: pane ids change after a reboot. An external lane whose registered pane is gone is pointed at
    the one live pane running something other than a shell (a Claude session) in its worktree or below it; none or several = left
    as it is. One `queue` row per move. ponytail: two dead lanes on one worktree both take its one session; a pane title match
    if that ever picks wrong."""
    if listing is None:
        try:
            r = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_id}\t#{pane_current_command}\t#{pane_current_path}"], capture_output=True, text=True)
        except OSError:
            return []  # no tmux on this PATH (the jail running the tests, a launchd PATH without it): nothing to re-point
        if r.returncode:
            return []  # no tmux server yet (the loop starts at login, before any session): next tick
        listing = r.stdout
    panes = [ln.split("\t") for ln in listing.splitlines() if ln.count("\t") == 2]
    live = {p[0] for p in panes}
    moved = []
    with journal.Lock("queue"):
        lanes = load()
        for x in lanes:
            if x.get("kind") != "external" or not x.get("pane") or x["pane"] in live:
                continue
            wt = os.path.realpath(x["worktree"])
            fit = [p[0] for p in panes if p[1].lstrip("-") not in SHELLS and (os.path.realpath(p[2]) + "/").startswith(wt + "/")]
            if len(fit) == 1:
                moved.append(f"{x['id']}: pane {x['pane']} -> {fit[0]}")
                journal.append("queue", lane=x["id"], state="repane", detail=moved[-1])
                x["pane"] = fit[0]
        if moved:
            save(lanes)
    return moved

def feed(procs: Procs, lanes_n: int, out=print) -> bool:
    """While fewer than `lanes_n` lanes have steps left, queue the next build-order milestone no lane holds. True if one was taken."""
    took = False
    while True:
        lanes = load()
        busy = [x for x in lanes if x["cursor"] < len(x["steps"])]
        # an external lane (a session of its own, or one holding a milestone) is not one of the loop's lanes, but it holds its milestone;
        # a finished external lane (a batch landed for it) frees its milestone, so the issues left open are briefed (soak 2026-11-02)
        # an external lane whose step the loop is checking, reviewing or landing uses one of the loop's lanes while it does
        if sum(1 for x in busy if x.get("kind") != "external" or x["steps"][x["cursor"]]["state"] != "queued") >= lanes_n:
            return took
        nxt = procs.next_milestone({x["id"] for x in lanes if x in busy or x.get("kind") != "external"} | _SKIPPED)
        if not nxt:
            return took
        lane_id, worktree, steps = nxt
        for st in steps:
            add(lane_id, worktree, st["step"], st["brief"], st["issues"], waits=st.get("waits"))
        if not any(x["id"] == lane_id and x["cursor"] < len(x["steps"]) for x in load()):  # every step it has already ran: never again this run
            _SKIPPED.add(lane_id)
            journal.append("queue", lane=lane_id, step="-", state="question", detail="the milestone's open issues brief only steps this lane already ran")
            continue
        journal.append("queue", lane=lane_id, step="-", state="milestone", detail=f"taken: {len(steps)} steps")
        out(f"{lane_id}: taken from the build order, {len(steps)} steps")
        took = True


VERIFY_PENDING = "verify-pending"  # a product landing's head, waiting for every lane to go idle


def verify_when_idle(procs: Procs, chains: dict | None) -> None:
    """dev-workflows.run.verify-all (owner 2026-11-03): after a worker lane's MILESTONE is complete (its last step landed, some step product), once no lane is busy and no build runs, `builder verify-all`
    runs once over the loop's checkout: one `verify` row and its activity rows, an alert when red; it never pushes and takes the heavy lock."""
    marker = journal.STATE / VERIFY_PENDING
    if not marker.is_file() or any(t.is_alive() for t in BUILDS):
        return
    head = marker.read_text().strip()
    marker.unlink(missing_ok=True)

    def run_it():
        rc, output = procs.verify_all()
        journal.append("queue", lane="-", step="-", state="verified" if rc == 0 else "verify-failed", detail=f"{head[:9]}: {output[-300:]}")
        if rc:
            alert("-", "verify", f"verify-all after the landing of {head[:9]} is red: {(output.strip().splitlines() or [''])[-1]}", str(journal.STATE), [])
    if chains is None:
        run_it()
    else:
        t = threading.Thread(target=run_it, name="verify-all", daemon=True)
        BUILDS.append(t)
        t.start()


DAILY = "daily-builds.last"  # when the daily builds last started (epoch seconds)
DAILY_S = 24 * 3600


def daily_when_due(procs: Procs, chains: dict | None) -> None:
    """#6390 (owner 2026-11-07): the iOS app and the Swift test target, which the build rung never compiles, built once a day
    on the build remote (`builder daily-builds`), busy lanes or not: a `daily-builds` row, and an alert when one is red. It runs
    in a BUILDS thread, so a re-exec waits for it. ponytail: one day from the last START; a down Air waits the day too."""
    if procs.daily_builds is None or any(t.name == "daily-builds" and t.is_alive() for t in BUILDS):
        return
    marker = journal.STATE / DAILY
    try:
        if time.time() - float(marker.read_text()) < DAILY_S:
            return
    except (OSError, ValueError):
        pass
    marker.write_text(f"{time.time()}\n")

    def run_it():
        rc, output = procs.daily_builds()
        journal.append("daily-builds", state={0: "green", 1: "red"}.get(rc, "not-run"), detail=output[-600:])
        if rc == 1:
            red = next((ln for ln in output.splitlines() if ": RED" in ln), output.strip()[-200:])
            alert("-", "daily-builds", f"a daily build is red: {red}", str(journal.STATE / "build-logs"), [])
    if chains is None:
        run_it()
    else:
        t = threading.Thread(target=run_it, name="daily-builds", daemon=True)
        BUILDS.append(t)
        t.start()


ONLY: list = [()]  # [loop].only: the lanes the loop ticks; () = every lane in the queue (tests); the verb sets it (manager 2026-11-04)


def _ours(lane: dict) -> bool:
    return not ONLY[0] or lane["id"] in ONLY[0]


def tick(procs: Procs, handles: dict, *, workers_n: int, push: bool, out=print, chains: dict | None = None) -> bool:
    busy = False
    for lane in filter(_ours, load()):
        try:
            busy = tick_lane(lane, procs, handles, workers_n, push, out, chains) or busy
        except Exception:  # noqa: BLE001 - the same for the tick's own work on a lane: a row, and the other lanes still tick
            journal.append("loop", state="lane-error", lane=lane["id"], detail=traceback.format_exc()[-1500:])
            out(f"{lane['id']}: lane error (journal row lane-error); the loop goes on")
    daily_when_due(procs, chains)
    if not busy:
        verify_when_idle(procs, chains)
        if getattr(procs, "root", ""):  # housekeeping at a quiet tick: the ladders' old scratch dirs (run.scratch-sweep)
            from fichero_builder import scratch
            scratch.when_idle(procs.root)
    return busy


DRAIN: list = [False]
BUILDS: list = []  # the post-landing dev builds' threads: a re-exec waits for them


def code_mark() -> tuple:
    """What the running loop's code is: each fichero_builder source's name, size and mtime."""
    pkg = Path(__file__).resolve().parent
    return tuple(sorted((f.name, f.stat().st_size, f.stat().st_mtime_ns) for f in pkg.glob("*.py")))


def reexec() -> None:  # the tests replace this
    os.execv(sys.executable, [sys.executable, "-m", "fichero_builder", *sys.argv[1:]])


def run(procs: Procs, *, workers_n: int, push: bool, lanes_n: int = 1, tick_s: float = 30.0, once: bool = False, forever: bool = False,
        heartbeat: bool = False, out=print, feed_milestones: bool = True) -> int:
    """Ticks until nothing can move without a person; `forever` (the verb) keeps ticking so a blocked or paused lane keeps its
    session and a resume from another shell is picked up. Each tick first takes build-order milestones up to `lanes_n`."""
    handles: dict = {}
    DRAIN[0] = False  # a fresh process (a re-exec included) runs the code on disk
    mark = code_mark()
    if heartbeat:
        journal.STATE.mkdir(parents=True, exist_ok=True)
        (journal.STATE / "loop.pid").write_text(f"{os.getpid()}\n")  # the watchdog's restart kills this pid; an exec keeps it
        from fichero_builder import check_tool
        for w in check_tool.rules_warnings(getattr(procs, "root", "") or "."):
            journal.append("rules", state="warning", detail=w)
    # the loop always chains in a thread: a one-lane check inside the tick would starve the heartbeat for its whole ladder
    chains: dict | None = {"pool": ThreadPoolExecutor(max_workers=lanes_n)} if lanes_n > 1 or heartbeat else None
    if heartbeat:  # this process is the current code: a step the old code blocked on newer rules goes again
        retry_rules_blocked(out)
        if getattr(procs, "root", ""):  # presubmit judges with the live loop's checkout, whoever runs `builder done`
            (journal.STATE / "live-root").write_text(str(Path(procs.root).resolve()) + "\n")
    while True:
        if heartbeat:  # after a reboot the lanes' sessions come back in new panes (run.loop-launchd)
            for m in repane():
                out(m)
        for x in filter(_ours, load()):  # dev-workflows.run.loop-external-intake: an external lane past its thresholds is taken as if done ran
            cur = x["steps"][x["cursor"]]["state"] if x["cursor"] < len(x["steps"]) else "landed"
            if x.get("kind") == "external" and not x.get("hold") and cur in ("queued", "landed") and (sha := procs.intake(x)):
                why = done(x["id"], sha)
                out(f"{x['id']}: intake at {sha[:9]}" + (f" refused: {why}" if why else ""))
        took = feed(procs, lanes_n, out) if feed_milestones else False  # the verb: only when [loop].feed_milestones (manager 2026-11-04)
        busy = tick(procs, handles, workers_n=workers_n, push=push, out=out, chains=chains) or took
        if heartbeat:  # dev-workflows.run.loop: a watchdog reads the gap between these
            journal.append("loop", state="tick", lanes=[f"{x['id']} {x['cursor']}/{len(x['steps'])}" for x in load()], busy=busy)
        if once or not (busy or forever):
            return 0
        # new code (soak 2026-11-02: a hand restart is a defect): between ticks, nothing in flight, the loop execs itself, same args.
        # ponytail: a live worker session holds the restart off (a restart would lose its handle); it runs at the next quiet tick
        DRAIN[0] = heartbeat and code_mark() != mark  # serial chains never left a gap: stop starting them until it re-execs
        if heartbeat and code_mark() != mark and not handles and not any(not f.done() for k, f in (chains or {}).items() if k != "pool") and not any(t.is_alive() for t in BUILDS):
            journal.append("loop", state="restarted", detail="loop restarted for new code", pid=os.getpid(), argv=sys.argv[1:])
            reexec()
            mark = code_mark()  # a test's reexec returns
        procs.sleep(tick_s)



RULES_NEWER = re.compile(r"unknown keys|rules file refused")


def retry_rules_blocked(out=print) -> list[str]:
    """At the loop's start (a re-exec onto new code included): a step that blocked because the rules file was newer than the code
    that read it (`unknown keys`, `rules file refused`) is retried once per head, with a row, so a harness landing that adds a key
    never leaves the lanes blocked (manager 2026-11-04: 35 min, 10:16-10:50)."""
    done_ = []
    with journal.Lock("queue"):
        lanes = load()
        for x in lanes:
            if x["cursor"] >= len(x["steps"]):
                continue
            st = x["steps"][x["cursor"]]
            if st.get("state") == "blocked" and RULES_NEWER.search(st.get("why", "")) and st.get("rules_retry") != st.get("head", ""):
                st.update(state="done" if x.get("kind") == "external" and st.get("head") else "queued", why="", rules_retry=st.get("head", ""))
                journal.append("queue", lane=x["id"], step=st["step"], state="rules-retry", detail="blocked by rules newer than the code that read them: retried once on the current code")
                done_.append(x["id"])
        if done_:
            save(lanes)
    for d in done_:
        out(f"{d}: retried (rules newer than the old code)")
    return done_

def table() -> list[list[str]]:
    return [[x["id"], s["step"], s["state"], ", ".join(f"#{n}" for n in s["issues"]), s["head"][:9] or "-", s["why"].strip().replace("\n", " ")[:200]]
            for x in load() for s in x["steps"]]


def landed_argv(root, lane_id: str, head: str, push: bool) -> list[str]:
    """`builder landed` for a lane: the verdict store `builder work`'s chain wrote under the lane's name."""
    return [sys.executable, "-m", "fichero_builder", "landed", head, "--root", str(root), "--state", str(journal.STATE),
            "--verdicts", str(journal.STATE / f"verdicts-{lane_id}.json"), "--keep-worktree", "--lane", lane_id] + (["--push"] if push else [])


def check_head(root, lane_id: str, w=None) -> tuple[int, str]:
    """`builder check-lane`: the lane's HEAD fetched into the engine repo (as `work-<lane>-check`, never the chain's ref) and
    the pinned ladder run over it, in a ladder slot like any check; a check row, no review, nothing lands."""
    w = w or work
    rules = tomllib.loads((Path(root) / "harness.toml").read_text())
    repo, branch = rules["check"]["engine_repo"], rules["land"]["branch"]
    lane = next((x for x in load() if x["id"] == lane_id), None)
    if lane is None:
        return 1, f"REFUSED: no lane {lane_id!r}"
    a = types.SimpleNamespace(worktree=lane["worktree"], name=f"{lane_id}-check", external=lane.get("kind") == "external", root=str(root),
                              maintainer=bool(lane.get("maintainer")), ids=[], repo=repo)
    a.pinned = w.ensure_pinned(str(root), "", w.r_since(repo, branch))
    head = w.do_fetch(a, repo, branch)
    if not head:
        return 1, f"REFUSED: could not fetch {lane_id}'s HEAD into {repo}"
    files = w._git(repo, "diff", "--name-only", w.r_since(repo, branch), head).stdout.split()
    a.name = lane_id  # its activity rows sit on the lane's console row
    with w.ladder_slot(f"{lane_id} (Run check)", files, check_tool.load(a.pinned).parallel):
        r = w.do_check(a, repo, branch, head, str(journal.STATE / f"ladder-{lane_id}-check.json"))
    return (0, f"{lane_id} at {head[:9]}: GREEN") if r.get("ok") else (1, f"{lane_id} at {head[:9]}: RED at {r.get('failed') or '?'}")




def build_head(root, lane_id: str, w=None) -> tuple[int, str]:
    """`builder build-check` (design batch ii, manager 2026-11-04): the app's build rung over a lane's HEAD before its `done`, so a
    compile error reaches the lane's pane in minutes, not after a queue and a ladder. The HEAD is fetched into the engine repo as
    `check-lane` does, the pinned check files are laid over a scratch tree of it, and `check_tool.build` runs it exactly as the
    ladder's rung: jailed, in the stable build tree, under the build and heavy locks, a green key stored, so the ladder's own build
    rung reuses it for the same `fichero/` tree. Nothing lands; one `build-check` row."""
    w = w or work
    rules = tomllib.loads((Path(root) / "harness.toml").read_text())
    repo, branch = rules["check"]["engine_repo"], rules["land"]["branch"]
    lane = next((x for x in load() if x["id"] == lane_id), None)
    if lane is None:
        return 1, f"REFUSED: no lane {lane_id!r}"
    a = types.SimpleNamespace(worktree=lane["worktree"], name=f"{lane_id}-check", external=lane.get("kind") == "external", root=str(root),
                              maintainer=bool(lane.get("maintainer")), ids=[], repo=repo)
    a.pinned = w.ensure_pinned(str(root), "", w.r_since(repo, branch))
    head = w.do_fetch(a, repo, branch)
    if not head:
        return 1, f"REFUSED: could not fetch {lane_id}'s HEAD into {repo}"
    cfg = check_tool.load(a.pinned)
    if not cfg.build:
        return 0, f"{lane_id} at {head[:9]}: no [check].build configured, nothing to compile"
    j = jail.load(a.pinned)
    if j is not None:
        j.require()
    check_tool._jail_enter(j)
    check_tool._KEY[0] = f"build-check {head[:9]}"
    tree = None
    try:
        tree = check_tool._scratch_tree(repo, head, a.pinned, cfg)
        r = check_tool.build(tree, list(cfg.build_paths), cfg)  # the build paths themselves as the change: it always compiles
    finally:
        check_tool._jail_exit()
        if tree:
            check_tool._git(repo, "worktree", "remove", "--force", tree)
    res = (r.get("results") or [{}])[0]
    journal.append("build-check", lane=lane_id, head=head, ok=bool(r["ok"]), seconds=res.get("seconds"), reused=bool(res.get("reused")),
                   log=res.get("log", ""))
    if r["ok"]:
        how = "reused a green build of the same tree" if res.get("reused") else f"built in {res.get('seconds', '?')} s"
        return 0, f"{lane_id} at {head[:9]}: BUILD GREEN ({how}); the ladder's build rung will reuse it"
    errors = (res.get("errors") or res.get("stderr_tail") or res.get("stdout_tail") or "").strip()
    return 1, f"{lane_id} at {head[:9]}: BUILD RED{' (timed out)' if res.get('timed_out') else ''}\n{errors[-4000:]}\nlog: {res.get('log', '-')}"



def touches_build(lane: dict, step: dict, root) -> bool:
    """The step's batch changes a `[check].build_paths` file (a Swift build would run). The batch is the step's head, or, on a worker
    lane whose step has no head until a chain is green, the lane worktree's HEAD (review 116). Unknown (no root, git fails): False."""
    if not root:
        return False
    try:
        rules = tomllib.loads((Path(root) / "harness.toml").read_text())
    except (OSError, ValueError):
        return False
    if rules.get("check", {}).get("build_remote"):  # t88: the build runs on another Mac, so the owner's hold here holds nothing back
        return False
    paths = tuple(rules.get("check", {}).get("build_paths", ()))
    branch = rules.get("land", {}).get("branch", "integration")
    tree = step.get("land_tree") or lane.get("worktree", "")
    r = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(tree), "diff", "--no-ext-diff", "--name-only", f"origin/{branch}...{step.get('head') or 'HEAD'}"],
                       capture_output=True, text=True)
    return bool(paths) and r.returncode == 0 and any(f.startswith(paths) for f in r.stdout.split())


CARRYABLE = {"approve_red", "approve_weakened", "approve_guard_data"}  # approvals bound to the files they named; never maintainer or pinned-new


def carry_approvals(step: dict, repo: str, base_ref: str, auto) -> bool:
    """`approval-carry-same-file-diffs`: the step's approve, given on an older head, holds at its new head when each file the approve
    named has the same diff from its base at both heads (one patch-id): commits only added elsewhere, or a rebase whose range-diff of
    those files is empty. A named file whose diff changed, an approval kind not bound to files, or no named file: no carry.
    True when it carried (one `auto` row; the step's approved_head moves)."""
    old, new, named = step.get("approved_head", ""), step.get("head", ""), list(step.get("approved_tests") or [])
    flags = {k for k in (*CARRYABLE, "approve_pinned_new", "maintainer") if step.get(k)}
    if not old or not new or old == new or not flags:
        return False  # nothing to carry

    def declined(why: str) -> bool:  # an older approve that does not carry says why (2026-11-04: a miss left no trace)
        journal.append("carry-declined", step=step.get("step", ""), head=new, approved_head=old, detail=why)
        return False
    if "approval-carry-same-file-diffs" not in auto:
        return declined("the rule is not in [check].auto")
    if not named:
        return declined("the approve named no file")
    if flags - CARRYABLE:
        return declined(f"an approval kind that never carries: {sorted(flags - CARRYABLE)}")

    def pid(head: str, f: str) -> str | None:
        g = ["git", "-c", "safe.directory=*", "-C", repo]
        base = subprocess.run(g + ["merge-base", base_ref, head], capture_output=True, text=True).stdout.strip()
        if not base:
            return None
        d = subprocess.run(g + ["diff", "--no-ext-diff", base, head, "--", f], capture_output=True)
        if d.returncode:
            return None
        if not d.stdout:
            return ""
        return subprocess.run(["git", "patch-id", "--stable"], input=d.stdout, capture_output=True).stdout.decode().split(" ")[0]
    for f in named:
        a, b = pid(old, f), pid(new, f)
        if a is None or a != b:
            return declined(f"{f}: " + ("its diff could not be read at one head" if a is None or b is None else "its diff changed"))
    step["approved_head"] = new
    journal.append("auto", rule="approval-carry-same-file-diffs", head=new, file=", ".join(named), detail=f"the approve given at {old[:9]} holds: the same diff of each named file")
    return True

def carry_in_lane(step: dict, lane: dict, branch: str, auto) -> bool:
    """The chain's carry, in the lane's own repo (its land tree, else its worktree) against its origin/<branch>: that repo holds both
    heads; the engine repo gets the new head only when the chain fetches it, after the carry (2026-11-04: carry-declined 'its diff could
    not be read at one head', twice)."""
    return carry_approvals(step, step.get("land_tree") or lane["worktree"], f"origin/{branch}", auto)


def _approved(step: dict | None, key: str) -> bool:
    """An approve counts only for the head it was given on (defect 2026-11-02: alert -36's approve_red excused a later head)."""
    # a worker lane's step has no head until a chain is green: its approve is recorded with head "" and holds while it still has none
    return bool(step and step.get(key) and step.get("approved_head") == step.get("head", ""))


def real_procs(root) -> Procs:
    root = Path(root)
    rules = tomllib.loads((root / "harness.toml").read_text())
    repo, branch = rules["check"]["engine_repo"], rules["land"]["branch"]
    mdl = models.load(root)
    builder, reviewer = models.for_role(mdl, "builder").model, models.for_role(mdl, "reviewer").model
    reviewer_fast = models.for_role(mdl, "reviewer_fast").model if "reviewer_fast" in mdl else reviewer
    opus_paths = tuple(mdl.get("reviewer_paths") or work.OPUS_PATHS)
    opus_lanes = set(mdl.get("opus_lanes") or ())  # owner 2026-11-06: a lane whose rounds cost more than its review minutes gets the full reviewer
    pkg = Path(__file__).resolve().parents[1]

    def ns(lane: dict, step: dict | None = None) -> types.SimpleNamespace:
        brief = (step.get("resume_brief") or step["brief"]) if step else ""  # a fix brief after a gone session (run.loop-fix-rounds)
        tree = (step or {}).get("land_tree") or lane["worktree"]  # an external lane's batch is taken from its land-<lane> snapshot
        return types.SimpleNamespace(worktree=tree, name=lane["id"], pinned=str(root), root=str(root), kind="claude", session="harness",
                                     tick=30.0, issues=step["issues"] if step else [], brief=brief, ids=[], repo=repo,
                                     maintainer=_approved(step, "maintainer") or bool(lane.get("maintainer")), approve_weakened=_approved(step, "approve_weakened"),
                                     external=lane.get("kind") == "external", approve_red=_approved(step, "approve_red") and (tuple(f for f in step.get("approved_tests") or () if f.endswith(".py")) or True),
                                     approve_pinned_new=_approved(step, "approve_pinned_new"),
                                     guard_data=tuple(f for f in (step or {}).get("approved_tests", ()) if f.endswith(".json")) if _approved(step, "approve_guard_data") else (),
                                     reviewer_fast=reviewer if lane["id"] in opus_lanes else reviewer_fast, opus_paths=opus_paths,
                                     last_step=bool(step) and lane.get("kind") != "external" and bool(lane.get("steps")) and step is lane["steps"][-1])

    def start(lane, step):
        a, q = ns(lane, step), shlex.quote
        if why := work.ensure_worktree(a, f"lane-{lane['id']}"):
            raise RuntimeError(why)
        j = work._jail(a)
        # the owner's folder: a worker cannot write its own next brief. The workroot is world-writable, so the name is one no worker can
        # plant a link at: made exclusively, then opened to reading (the sticky bit keeps a worker from replacing it)
        feed = Path(tempfile.mkdtemp(prefix=f"inbox-{lane['id']}-{lane['seq']}-", dir=j.workroot))
        feed.chmod(0o755)
        lane["feed"] = str(feed)
        codemap.provide(root)
        cmd = work.run_cmd(a, builder, "--feed", feed, "--seq", lane["seq"])
        return subprocess.Popen([j.sudo, "-n", "-H", "-u", j.user, "sh", "-c", f"cd {q(j.workroot)} && {cmd}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def send(lane, text):
        p = Path(lane["feed"]) / f"msg-{lane['seq']}.txt"
        p.write_text(text)
        p.chmod(0o644)

    def row(lane):
        return next((r for r in reversed(work._shared_rows(ns(lane))) if r.get("event") == "step" and r.get("task") == lane["id"]
                     and r.get("seq") == lane["seq"]), None)

    def chain(lane, step, stage):
        carry_in_lane(step, lane, branch, tuple(rules.get("check", {}).get("auto", ())))
        a = ns(lane, step)
        a.pinned = work.ensure_pinned(str(root), step["brief"], land_tool.resolve_branch(repo, branch))
        a.repin = lambda: work.ensure_pinned(str(root), step["brief"], land_tool.resolve_branch(repo, branch))
        return work.after_run(a, repo, branch, reviewer, stage=stage)

    def landed(lane, head, push):
        r = subprocess.run(landed_argv(root, lane["id"], head, push), cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def end_of(lane):
        return next((r["end"] for r in reversed(work._shared_rows(ns(lane))) if r.get("event") == "cost" and r.get("task") == lane["id"]
                     and r.get("end") != "handoff"), "gone")

    def build(lane):
        r = subprocess.run([sys.executable, "-m", "fichero_builder", "build", "--dev", "--root", str(root), "--state", str(journal.STATE)],
                           cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def touches_product(lane, head):
        prefixes = tuple(rules.get("check", {}).get("product_paths", ()))
        if not prefixes:
            return True
        r = subprocess.run([land_tool.GIT, "-C", str(repo), "diff", "--name-only", f"{land_tool.resolve_branch(repo, branch)}..{head}"],
                           capture_output=True, text=True)
        return r.returncode != 0 or any(f.startswith(prefixes) for f in r.stdout.split())  # unknown = build

    def verify_all():
        r = subprocess.run([sys.executable, "-m", "fichero_builder", "verify-all", "--root", str(root), "--state", str(journal.STATE)],
                           cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def daily_builds():
        r = subprocess.run([sys.executable, "-m", "fichero_builder", "daily-builds", "--root", str(root), "--state", str(journal.STATE)],
                           cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def stop(lane):
        if lane.get("feed"):
            (Path(lane["feed"]) / "stop").write_text("")

    loop_cfg = rules.get("loop", {})

    def tell(lane, text):
        if not lane.get("pane"):
            return "no registered pane"
        if not loop_cfg.get("tell"):  # the tracked `builder tell`
            from fichero_builder import tell as tell_mod
            rc, out = tell_mod.send(lane["pane"], text)
            return "" if rc == 0 else out
        try:
            r = subprocess.run([os.path.expanduser(loop_cfg["tell"]), lane["pane"], text[:780]], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return str(e)
        return "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-200:]

    def after_land(lane, step, head):
        from fichero_builder import landed
        landed.sweep_one(root, step["land_tree"])
        refresh_live(root, branch)

    def intake(lane):
        return intake_sha(lane, branch, int(loop_cfg.get("intake_commits", 8)), float(loop_cfg.get("intake_hours", 3)))

    return Procs(start=start, alive=lambda h: h.poll() is None, send=send, rebase=lambda lane: work.do_rebase(ns(lane), branch), row=row, chain=chain,
                 landed=landed, end_of=end_of, stop=stop, still_open=lambda lane, step: open_of(step["issues"], cwd=str(root)),
                 next_milestone=lambda taken: next_in_order(root, taken), build=build, verify_all=verify_all, daily_builds=daily_builds if rules.get("check", {}).get("daily_builds") else None, touches_product=touches_product, trees=trees, tell=tell, after_land=after_land, intake=intake,
                 jail_root=str(Path(rules["jail"]["workroot"]) / "root") if rules.get("jail", {}).get("workroot") else "", root=str(root))


PRESUBMIT_TIMEOUT_S = 1200
PRESUBMIT_ROOT: list = [None]  # the pinned checkout presubmit judges with; None = the builder's own (tests set it)


def presubmit(lane_id: str, sha: str, pinned=None) -> tuple[bool, str]:
    """`builder done`'s shift-left gate (speed batch 2, manager 2026-11-03): the ready check WITH its guards (`--no-guards` dropped:
    every fast guard, the spec guards among them, the lint ratchet, the git checks) over the lane's `sha`, so a red a guard would find
    stops here, in minutes, not after a whole ladder. The script and the guards are the PINNED ones (manager 2026-11-04: a lane that
    edits its own ready script must not pass its own presubmit): a scratch tree of `sha` from the lane's repo with the owner's check
    files laid over it (`check_tool._scratch_tree`, as the ladder does), `pinned` = the builder's own checkout. Still unjailed with the
    caller's environment: the lane's code under test runs there. (ok, what it said); one `presubmit` journal row."""
    from fichero_builder import check_tool
    live = journal.STATE / "live-root"  # the running loop's own checkout, written at its start: never the code `done` was run from (review -89)
    pinned = Path(pinned or PRESUBMIT_ROOT[0] or (live.read_text().strip() if live.is_file() else "") or "/nonexistent")
    lane = next((x for x in load() if x["id"] == lane_id), None)
    wt = Path(lane["worktree"]) if lane else None
    f = pinned / "harness.toml"
    ready = [x for x in tomllib.loads(f.read_text()).get("check", {}).get("ready", []) if x != "--no-guards"] if f.is_file() else []
    if not ready or wt is None or not (wt / ".git").exists():
        journal.append("presubmit", lane=lane_id, head=sha, state="skipped", detail="no pinned [check].ready, or no lane worktree")
        return True, "presubmit skipped: no pinned [check].ready, or no lane worktree"
    g = ["git", "-c", "safe.directory=*", "-C", str(wt)]
    want = subprocess.run(g + ["rev-parse", "--verify", "-q", f"{sha or 'HEAD'}^{{commit}}"], capture_output=True, text=True).stdout.strip()
    if not want:
        journal.append("presubmit", lane=lane_id, head=sha, state="skipped", detail=f"{sha[:12]} is not in the lane's repo")
        return True, f"presubmit skipped: {sha[:12]} is not in the lane's repo"
    try:
        cfg = check_tool.load(pinned)
    except (ValueError, OSError) as e:  # the live loop's rules are newer than this code (a new key) or unreadable: said, never a traceback
        journal.append("presubmit", lane=lane_id, head=want, state="skipped", detail=f"the live rules could not be read by this code: {e}"[-300:])
        return True, f"presubmit skipped: the live rules could not be read by this code (update it): {e}"
    def run(data: tuple = ()) -> tuple[bool, str]:
        tree = None
        try:
            tree = check_tool._scratch_tree(wt, want, pinned, cfg, data_from_head=data)
            r = subprocess.run(["bash", *ready], cwd=tree, capture_output=True, text=True,
                               timeout=PRESUBMIT_TIMEOUT_S, env={**os.environ, "FICHERO_PYTHON_BIN": sys.executable})
            return r.returncode == 0, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            return False, f"presubmit timed out after {PRESUBMIT_TIMEOUT_S} s"
        except RuntimeError as e:  # the scratch tree refused the lane's tree (a symlink out, ...): the ladder would too (review -89)
            return False, f"presubmit refused: {e}"
        finally:
            if tree:
                subprocess.run(g + ["worktree", "remove", "--force", tree], capture_output=True)
    ok, said = run()
    if not ok and not said.startswith(("presubmit refused", "presubmit timed out")):
        # a batch that changes guard DATA (a known-gaps entry for a new route) is red under the pinned copy by design: run again with
        # head's copy of exactly those files, as the ladder's guard-data approve does. Green then = the data was the only cause: the done
        # goes through and the ladder raises the approve (manager 2026-11-04); any other red stays a refusal.
        base = subprocess.run(g + ["merge-base", want, "origin/integration"], capture_output=True, text=True).stdout.strip()
        files = subprocess.run(g + ["diff", "--no-ext-diff", "--name-only", base, want], capture_output=True, text=True).stdout.split() if base else []
        data = tuple(f for f in files if f.endswith(".json") and f.startswith(tuple(cfg.check_paths)))
        if data and run(data)[0]:
            ok, said = True, f"presubmit green but would need the guard-data approve for {', '.join(data)} (red under the pinned copy):\n{said}"
    journal.append("presubmit", lane=lane_id, head=want, state=("guard-data" if said.startswith("presubmit green but") else "green") if ok and not said.startswith("presubmit skipped") else "skipped" if ok else "red", detail=said[-1500:])
    return ok, said


def refresh_live(root, branch: str, git=None) -> str:
    """The loop's own tree (`--root`) follows origin/<branch> after each landing, so the code it runs is never behind the rules it
    reads (2026-11-03: a list in harness.toml landed while the loop's tree lacked the code for it, and the loop died on every ladder).
    Only a DETACHED tree moves (a person's branch checkout is never touched); the re-exec for new code follows by itself
    at the next quiet tick. A hot-patched (dirty) tree moves too, its edits carried, when origin did not touch those files: a
    dirty tree left in place froze the rules data, so a landed known-gaps entry stayed a red in every presubmit (manager
    2026-11-07 21:37, lane-sharing). Origin touching a patched file = left, said. One `loop` row; the word back is what happened."""
    git = git or [land_tool.GIT, "-C", str(root)]
    def g(*a):
        return subprocess.run([*git, *a], capture_output=True, text=True)
    if g("symbolic-ref", "-q", "HEAD").returncode == 0:
        return "on a branch: left"
    dirty = g("diff", "--name-only", "HEAD").stdout.split()
    f = g("fetch", "-q", "origin", branch)
    if f.returncode:
        journal.append("loop", state="live-tree-refused", detail=(f.stderr or f.stdout).strip()[-300:])
        return "refused"
    if clash := sorted(set(dirty) & set(g("diff", "--name-only", "HEAD", f"origin/{branch}").stdout.split())):
        journal.append("loop", state="live-tree-dirty", detail=f"{root}: origin/{branch} changes the hot-patched {', '.join(clash)}: not moved")
        return "dirty: left"
    c = g("checkout", "-q", "--detach", f"origin/{branch}")  # git carries edits to files the move does not touch
    if c.returncode:
        journal.append("loop", state="live-tree-refused", detail=(c.stderr or c.stdout).strip()[-300:])
        return "refused"
    head = g("rev-parse", "HEAD").stdout.strip()
    DRAIN[0] = True  # the code on disk is newer than this process: no chain starts on the old code before the re-exec (2026-11-04)
    carried = f", carrying the hot patch of {', '.join(dirty)}" if dirty else ""
    journal.append("loop", state="live-tree", detail=f"{root} at origin/{branch} {head[:9]}{carried}")
    return f"moved to {head[:9]}{carried}"

def trees(paths: list) -> dict:
    """{path: "HEAD sha1-of-status"} read as the owner (the jail's trees are the worker's: safe.directory); unreadable is its own word."""
    out = {}
    for p in paths:
        g = [land_tool.GIT, "-c", "safe.directory=*", "-C", p]
        head = subprocess.run(g + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "unreadable"
        st = subprocess.run(g + ["status", "--porcelain"], capture_output=True, text=True).stdout
        out[p] = f"{head[:12]} {'clean' if not st else 'dirty ' + hashlib.sha1(st.encode()).hexdigest()[:8]}"
    return out


_SKIPPED: set = set()  # milestones this process found with no step to brief: asked once, not re-planned every tick


def next_in_order(root, taken: set, gh: str = "gh") -> tuple | None:
    """The first `## In order` milestone of the build-order file that no lane holds, has open issues and a spec, with one
    brief per step (the `builder milestone --enqueue` plan); a milestone whose issues place no step is a row and is skipped."""
    from fichero_builder import brief_tool, milestone, triage

    root = Path(root)
    rules = tomllib.loads((root / "harness.toml").read_text())
    for title, spec in triage.build_order(root)[0]:
        lane = slug(title)
        if lane in taken or lane in _SKIPPED or not spec:
            continue
        if owner := external_owner(spec, title):  # a session of its own works this spec: a lane here would duplicate it
            journal.append("queue", lane=lane, step="-", state="owned", detail=f"{owner} (external) owns {spec}")
            _SKIPPED.add(lane)
            continue
        issues = milestone.list_issues(title, gh=gh)
        if not issues:
            continue
        spec_path = root / triage.SPECS / spec
        planned = milestone.plan(issues, milestone.build_order(spec_path), milestone.spec_slug(spec_path))
        for q in planned["questions"]:
            journal.append("queue", lane=lane, step="-", state="question", detail=q[-300:])
        if planned["questions"]:  # the owner places them: ONE alert for the milestone listing every question (not 25)
            what = f"{lane}: {len(planned['questions'])} question(s) to place: " + "; ".join(planned["questions"])
            if not any(r.get("event") == "alert" and r.get("lane") == lane and r.get("step") == "plan" and r.get("what") == what[:300] for r in journal.read()):
                alert(lane, "plan", what, str(spec_path), ["park"])
        if not planned["clusters"]:
            _SKIPPED.add(lane)
            continue
        written = milestone.write_briefs(planned, out=journal.STATE / f"briefs-{lane}", repo_dir=str(root), base="", lane=lane,
                                         rules=rules.get("brief", {}).get("rules", ""), fetch=lambda n: brief_tool.fetch_issue(n, gh=gh),
                                         cluster=brief_tool.cluster, spec_path=str(spec_path), binary=codemap.owner_binary(root))
        worktree = str(Path(rules["jail"]["workroot"]) / f"wt-{lane}")
        return lane, worktree, [{"step": c["step"], "brief": str(b), "issues": [i["number"] for i in c["issues"]], "waits": c["waits"]}
                                for c, b in zip(planned["clusters"], written)]
    return None


def main(a) -> int:
    if a.action == "add":
        if not (a.lane and a.worktree and a.step and a.brief):
            print("REFUSED: queue add needs --lane, --worktree, --step and --brief")
            return 1
        add(a.lane, a.worktree, a.step, a.brief, a.issues, kind=getattr(a, "kind", "worker"), hold=True if getattr(a, "hold", False) else None,
            pane=getattr(a, "pane", ""), maintainer=True if getattr(a, "maintainer", False) else None)
        print(f"queued {a.lane} {a.step}")
        return 0
    if a.action == "tell":  # dev-workflows.run.loop-tell: a finding into the lane's live session, as its next message
        text = Path(a.file).read_text() if getattr(a, "file", None) else (a.text or "")
        with journal.Lock("queue"):
            lanes = load()
            lane = next((x for x in lanes if x["id"] == a.lane), None)
            if lane is None or not lane.get("feed") or not text:
                why = f"no lane {a.lane!r}" if lane is None else ("no text" if not text else "no live session: the finding goes in the next fix brief")
                print(f"REFUSED: {why}")
                journal.append("queue", lane=a.lane, step="-", state="tell-refused", detail=why)
                return 1
            lane["seq"] += 1
            p = Path(lane["feed"]) / f"msg-{lane['seq']}.txt"
            p.write_text(text.rstrip("\n") + "\n")
            p.chmod(0o644)
            save(lanes)
        journal.append("queue", lane=a.lane, step="-", state="told", detail=text[:300])
        return 0
    if a.action == "stop":  # pause = no new step is fed; stop = the session ends (the loop closes it after the grace)
        with journal.Lock("queue"):
            lanes = load()
            lane = next((x for x in lanes if x["id"] == a.lane), None)
            if lane is None:
                print(f"REFUSED: no lane {a.lane!r}")
                journal.append("queue", lane=a.lane, step="-", state="stop-refused", detail="no such lane")
                return 1
            lane["paused"], lane["stop_at"] = True, time.time() + a.grace
            told = bool(lane.get("feed"))
            if told:
                lane["seq"] += 1
                m = Path(lane["feed"]) / f"msg-{lane['seq']}.txt"
                m.write_text(STOP_NOTE + "\n")
                m.chmod(0o644)
            save(lanes)
        journal.append("queue", lane=a.lane, step="-", state="stop", detail=f"grace {a.grace:g} s" + ("; the worker was told" if told else "; no live session"))
        print(f"stopping {a.lane}: the session closes within {a.grace:g} s; `builder queue resume --lane {a.lane}` starts a fresh one")
        return 0
    if a.action in ("pause", "resume"):
        with journal.Lock("queue"):
            lanes = load()
            lane = next((x for x in lanes if x["id"] == a.lane), None)
            if lane is None:
                print(f"REFUSED: no lane {a.lane!r}")
                return 1
            lane["paused"] = a.action == "pause"
            unasked = []
            if a.action == "resume":
                for s in lane["steps"]:
                    if s["state"] == "blocked":
                        s.update(state="queued", rounds=0, restarts=0, why="")
                        unasked += s["issues"]
            save(lanes)
        journal.append("queue", lane=a.lane, step="-", state=a.action, detail="")
        for n in unasked:  # answered: the label goes (the comment stays as the record)
            if err := _gh_quiet(a.gh, ["issue", "edit", str(n), "--remove-label", "needs-your-decision"], a.root):
                journal.append("queue", lane=a.lane, step="-", state="ask-failed", detail=f"#{n} unlabel: {err}"[-300:])
        return 0
    if a.action == "run":
        try:
            procs = real_procs(a.root)
        except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError, models.Question, jail.JailMissing) as e:
            print(f"REFUSED: the rules file cannot run the queue: {e}")
            return 1
        lanes_n = max(1, a.lanes)
        return run(procs, workers_n=max(workers(a.root), lanes_n), push=a.push, lanes_n=lanes_n, tick_s=a.tick, once=a.once, forever=not a.once,
                   heartbeat=getattr(a, "heartbeat", False))
    for row in table():
        print("\t".join(row))
    return 0


def lane_from_issues(root, lane_id: str, issues: list[int], gh: str = "gh") -> tuple[int, str]:
    """`builder lane <name> --issues N...` (the console's Start as one lane): one cluster brief from those issues (the brief tool,
    as `builder milestone` writes them), queued as a worker lane in the jail. One `queue` row."""
    from fichero_builder import brief_tool, land_tool

    root = Path(root)
    rules = tomllib.loads((root / "harness.toml").read_text())
    branch, workroot = rules["land"]["branch"], rules["jail"]["workroot"]
    if not issues:
        return 1, "no issues ticked"
    if any(x["id"] == lane_id and x["cursor"] < len(x["steps"]) for x in load()):
        return 1, f"lane {lane_id!r} is already working"
    try:
        got = [brief_tool.fetch_issue(n, gh=gh) for n in issues]
    except (RuntimeError, OSError, ValueError) as e:
        return 1, f"gh could not read the issues: {e}"
    base = land_tool.resolve_branch(str(root), branch) or f"origin/{branch}"
    text = brief_tool.cluster(got, repo=str(root), branch=branch, base=base, rules=rules.get("brief", {}).get("rules", ""))
    out = journal.STATE / f"briefs-{lane_id}"
    out.mkdir(parents=True, exist_ok=True)
    step = "issues-" + "-".join(str(n) for n in issues[:4])
    (out / f"{step}.md").write_text(text)
    add(lane_id, str(Path(workroot) / f"wt-{lane_id}"), step, str(out / f"{step}.md"), list(issues))
    return 0, f"queued {lane_id} {step}: {len(issues)} issue(s) in one cluster brief"
