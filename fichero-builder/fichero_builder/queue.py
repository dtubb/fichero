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
import tomllib
from concurrent.futures import ThreadPoolExecutor
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import check_tool, codemap, jail, journal, land_tool, models, work

ROUNDS, RESTARTS = 2, 2
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


def store(lane: dict) -> None:
    """This lane's row back in the file; a step added or a pause set while the chain ran is kept."""
    with journal.Lock("queue"):
        lanes = load()
        fresh = next((x for x in lanes if x["id"] == lane["id"]), None)
        if fresh:
            lane["paused"] = fresh["paused"]
            for k in ("pane", "hold", "maintainer"):  # set from outside while the tick held its copy (manager 2026-11-02: %537 was lost)
                if k in fresh:
                    lane[k] = fresh[k]
            have = {s["step"] for s in lane["steps"]}
            lane["steps"] += [s for s in fresh["steps"] if s["step"] not in have]
        save([lane if x["id"] == lane["id"] else x for x in lanes])


def stored_head(lane_id: str, step: str) -> str:
    """The head the queue file holds for a step now (what `builder done` wrote), not the tick's snapshot of it."""
    return next((st.get("head", "") for x in load() if x["id"] == lane_id for st in x["steps"] if st["step"] == step), "")


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
    tell: Callable[[dict, str], str] = lambda lane, text: ""  # (lane, text) -> '' or why: into an external lane's registered pane
    after_land: Callable[[dict, dict, str], None] = lambda lane, step, head: None  # an external lane's batch landed: sweep its land tree
    intake: Callable[[dict], str] = lambda lane: ""  # an external lane -> the sha to take now by itself (thresholds), or ''
    trees: Callable[[list], dict] = lambda paths: {}  # paths -> {path: "HEAD status-hash"}: what a step must leave unmoved (run.loop-machine-checked)
    jail_root: str = ""


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
    def move(s, state, detail=""):
        s["state"], s["why"] = state, detail[-500:]
        journal.append("queue", lane=lane["id"], step=s["step"], state=state, detail=detail[-300:])
        out(f"{lane['id']} {s['step']}: {state}" + (f" ({detail.strip().splitlines()[-1][:120]})" if detail.strip() else ""))
        store(lane)

    def block(s, why, actions=ACTIONS, evidence=""):
        q = journal.STATE / f"question-{lane['id']}-{s['step']}.txt"
        q.write_text(f"QUESTION: {why}\n")
        move(s, "blocked", why)
        alert(lane["id"], s["step"], why, evidence or str(q), list(actions))
        if lane.get("kind") == "external" and s.get("land_tree"):  # the lane fixes it on its branch: tell it where the findings are
            n = sum(1 for p in journal.STATE.glob(f"findings-{lane['id']}-*.txt")) + 1
            f = journal.STATE / f"findings-{lane['id']}-{n}.txt"
            f.write_text(f"{lane['id']} batch {s['step']} at {s.get('head', '')[:9]}: {why}\n\nEvidence: {evidence or q}\n")
            err = procs.tell(lane, f"FINDINGS for {lane['id']} at {s.get('head', '')[:9]}: {why.splitlines()[0][:300]} (full: {f}). "
                                   f"Fix on your branch (a conflict: rebase onto origin/integration), then run: {done_cmd(lane['id'])}")
            journal.append("queue", lane=lane["id"], step=s["step"], state="told" if not err else "tell-refused", detail=err or str(f))
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
        if stored_head(lane["id"], s["step"]) == h0:  # a `builder done` at a newer head took the step: this old chain must not write its stale copy back over it
            move(s, stage, "")

    def chain() -> dict:
        try:
            return procs.chain(lane, s, stage_cb)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            return {"ok": False, "kind": "error", "why": str(e)}
    if chains is None:
        r = chain()
        if stored_head(lane["id"], s["step"]) != h0:
            journal.append("queue", lane=lane["id"], step=s["step"], state="stale-result", detail=f"the check of {h0[:9]} ended after a newer head superseded it: dropped")
            return True
    elif fut is None:
        if DRAIN[0]:  # new code waits: no new chain starts, so the loop can re-exec between chains
            return True
        chains[lane["id"]] = chains["pool"].submit(chain)
        chains[lane["id"]].head = s.get("head", "")
        return True
    else:
        f = chains.pop(lane["id"])
        r = f.result()
        if getattr(f, "head", s.get("head", "")) != stored_head(lane["id"], s["step"]):  # `builder done` at a newer head ended this batch: its result is dropped, the new head is checked next tick
            journal.append("queue", lane=lane["id"], step=s["step"], state="stale-result", detail=f"the check of {f.head[:9]} ended after {s.get('head', '')[:9]} superseded it: dropped")
            return True
    if r["ok"]:
        s["head"] = r["head"]
        rc, output = procs.landed(lane, r["head"], push)
        if rc:
            return block(s, output)
        if lane.get("kind") == "external" and s.get("land_tree"):
            err = procs.tell(lane, f"LANDED {r['head'][:9]}: rebase onto origin/integration at your next step boundary.")
            journal.append("queue", lane=lane["id"], step=s["step"], state="told" if not err else "tell-refused", detail=err or "LANDED")
            procs.after_land(lane, s, r["head"])
        left = procs.still_open(lane, s)  # a row, not a close: only `builder landed` closes, on a Fixes line (owner ruling)
        close_alerts(lane["id"], s["step"], f"the step landed at {r['head'][:9]}")
        move(s, "landed", f"landed {r['head'][:9]}" + (" (pushed)" if push else " (not pushed)") + (f"; still open: {', '.join(left)}" if left else ""))
        if left:
            journal.append("queue", lane=lane["id"], step=s["step"], state="issue-open", detail=", ".join(left))
        lane["cursor"] += 1
        store(lane)
        return True
    if r.get("kind") in ("needs-maintainer", "weakened-tests", "red-on-base", "pinned-new"):  # a pinned check or a test changed on purpose: the manager's call
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
    return block(s, f"{r['why']}\n{r.get('findings', '')}".strip(), acts, evidence=r.get("evidence", ""))


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


APPROVALS = ("approve_red", "approve_weakened", "approve_pinned_new", "approve_kind", "approvals", "approved_head", "approved_tests", "maintainer")


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
        elif lane["cursor"] < len(lane["steps"]) and lane["steps"][lane["cursor"]]["state"] in IN_LADDER and not (
                lane["steps"][lane["cursor"]]["state"] in ("checking", "reviewing") and (sha := sha or lane_head(lane["worktree"]))
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
            if s["state"] in ("checking", "reviewing"):  # a newer head of the same work: the old check is cancelled, its approvals and alerts end with it
                from fichero_builder import check_tool
                old_head = s.get("head", "")
                journal.STATE.mkdir(parents=True, exist_ok=True)
                check_tool.cancel_file(old_head).write_text(sha)
                for k in APPROVALS:
                    s.pop(k, None)
                journal.append("queue", lane=lane_id, step=s["step"], state="superseded", detail=f"{old_head[:9]} by {sha[:9]}: its check is cancelled")
            # no tree on this machine (a lane named by hand): the old DONE, taken from the lane's worktree
            path, why = land_tree(lane, sha) if Path(lane["worktree"]).is_dir() else ("", "")
            if not why:
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


def answer(alert_id: str, action: str, gh: str = "gh", cwd=None) -> tuple[int, str]:
    """The manager's one verb: retry or approve re-run the step, send-back gives it to a new session with the finding,
    park leaves it, ask-owner puts it on GitHub for the owner. An action the alert does not offer is refused, with a row."""
    a = next((r for r in reversed(journal.read()) if r.get("event") == "alert" and r.get("id") == alert_id), None)
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
                s["approved_head"] = s.get("head", "")
                s["approved_tests"] = sorted(set(re.findall(r"[\w./-]+\.py", said)))
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


def launch_agents(root, out, *, state=None, tick_s: float = 30.0) -> list[Path]:
    """The owner's two LaunchAgents (dev-workflows.run.loop): `builder loop` kept alive, and `builder heartbeat` every three
    ticks. Both run as the owner from the checkout's package; logs beside the journal."""
    import plistlib

    pkg, out = Path(__file__).resolve().parents[1], Path(out)
    logs = Path(state) if state else journal.STATE
    st = ["--state", str(state)] if state else []
    jobs = {"loop": (["loop", "--root", str(root), "--tick", f"{tick_s:g}", *st], {"KeepAlive": True, "RunAtLoad": True}),
            "heartbeat": (["heartbeat", "--tick", f"{tick_s:g}", *st], {"StartInterval": int(3 * tick_s)})}
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, (args, when) in jobs.items():
        label = f"local.builder.{name}"
        f = out / f"{label}.plist"
        f.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": [sys.executable, "-m", "fichero_builder", *args],
                                      "WorkingDirectory": str(pkg), "EnvironmentVariables": {"PYTHONPATH": str(pkg), "PATH": os.environ.get("PATH", "")},
                                      "StandardOutPath": str(logs / f"{name}.log"), "StandardErrorPath": str(logs / f"{name}.log"), **when}))
        paths.append(f)
    return paths


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


def tick(procs: Procs, handles: dict, *, workers_n: int, push: bool, out=print, chains: dict | None = None) -> bool:
    busy = False
    for lane in load():
        busy = tick_lane(lane, procs, handles, workers_n, push, out, chains) or busy
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
        heartbeat: bool = False, out=print) -> int:
    """Ticks until nothing can move without a person; `forever` (the verb) keeps ticking so a blocked or paused lane keeps its
    session and a resume from another shell is picked up. Each tick first takes build-order milestones up to `lanes_n`."""
    handles: dict = {}
    mark = code_mark()
    if heartbeat:
        journal.STATE.mkdir(parents=True, exist_ok=True)
        (journal.STATE / "loop.pid").write_text(f"{os.getpid()}\n")  # the watchdog's restart kills this pid; an exec keeps it
        from fichero_builder import check_tool
        for w in check_tool.rules_warnings(getattr(procs, "root", "") or "."):
            journal.append("rules", state="warning", detail=w)
    # the loop always chains in a thread: a one-lane check inside the tick would starve the heartbeat for its whole ladder
    chains: dict | None = {"pool": ThreadPoolExecutor(max_workers=lanes_n)} if lanes_n > 1 or heartbeat else None
    while True:
        for x in load():  # dev-workflows.run.loop-external-intake: an external lane past its thresholds is taken as if done ran
            cur = x["steps"][x["cursor"]]["state"] if x["cursor"] < len(x["steps"]) else "landed"
            if x.get("kind") == "external" and not x.get("hold") and cur in ("queued", "landed") and (sha := procs.intake(x)):
                why = done(x["id"], sha)
                out(f"{x['id']}: intake at {sha[:9]}" + (f" refused: {why}" if why else ""))
        took = feed(procs, lanes_n, out)
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


def table() -> list[list[str]]:
    return [[x["id"], s["step"], s["state"], ", ".join(f"#{n}" for n in s["issues"]), s["head"][:9] or "-", s["why"].strip().replace("\n", " ")[:200]]
            for x in load() for s in x["steps"]]


def landed_argv(root, lane_id: str, head: str, push: bool) -> list[str]:
    """`builder landed` for a lane: the verdict store `builder work`'s chain wrote under the lane's name."""
    return [sys.executable, "-m", "fichero_builder", "landed", head, "--root", str(root), "--state", str(journal.STATE),
            "--verdicts", str(journal.STATE / f"verdicts-{lane_id}.json"), "--keep-worktree"] + (["--push"] if push else [])


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
    pkg = Path(__file__).resolve().parents[1]

    def ns(lane: dict, step: dict | None = None) -> types.SimpleNamespace:
        brief = (step.get("resume_brief") or step["brief"]) if step else ""  # a fix brief after a gone session (run.loop-fix-rounds)
        tree = (step or {}).get("land_tree") or lane["worktree"]  # an external lane's batch is taken from its land-<lane> snapshot
        return types.SimpleNamespace(worktree=tree, name=lane["id"], pinned=str(root), root=str(root), kind="claude", session="harness",
                                     tick=30.0, issues=step["issues"] if step else [], brief=brief, ids=[], repo=repo,
                                     maintainer=_approved(step, "maintainer") or bool(lane.get("maintainer")), approve_weakened=_approved(step, "approve_weakened"),
                                     external=lane.get("kind") == "external", approve_red=_approved(step, "approve_red") and (tuple(step.get("approved_tests") or ()) or True),
                                     approve_pinned_new=_approved(step, "approve_pinned_new"),
                                     reviewer_fast=reviewer_fast, opus_paths=opus_paths,
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

    def intake(lane):
        return intake_sha(lane, branch, int(loop_cfg.get("intake_commits", 8)), float(loop_cfg.get("intake_hours", 3)))

    return Procs(start=start, alive=lambda h: h.poll() is None, send=send, rebase=lambda lane: work.do_rebase(ns(lane), branch), row=row, chain=chain,
                 landed=landed, end_of=end_of, stop=stop, still_open=lambda lane, step: open_of(step["issues"], cwd=str(root)),
                 next_milestone=lambda taken: next_in_order(root, taken), build=build, trees=trees, tell=tell, after_land=after_land, intake=intake,
                 jail_root=str(Path(rules["jail"]["workroot"]) / "root") if rules.get("jail", {}).get("workroot") else "")


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
