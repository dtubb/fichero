"""`builder queue [add|run|pause|resume]`: one long-running worker per lane (a milestone), fed step by step, with no manager in
the loop (dev-workflows.tool.queue, Step 2.6; owner ruling 2026-11-01).

`<state>/queue.json` holds the lanes: id, worktree, cursor, seq, feed, paused, and the steps in build order (step, brief,
issues, waits, state, head, why, rounds, restarts). A step goes queued -> sent -> done -> checking -> reviewing -> landed, or
blocked with its question in `<state>/question-<lane>-<step>.txt`. The worker stays open after `DONE <sha>` (`builder run
--feed`, as the jail user, so it keeps what it has read); this owner-side loop sees its `step` row, runs rebase, patches,
fetch, check, review and the land gate (`work.after_run`), then `builder landed` (push only with --push), then sends the next
brief into the same session. Findings go back as a fix brief, two rounds, then blocked. A new session only when the worker
is gone or at its own 85 % handoff. Pause = idle with nothing sent; resume = send the next brief.
ponytail: the chain runs inside the tick, so one lane's ladder holds up the others' bookkeeping (never their workers); a thread per lane if that ever costs more than it saves."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import codemap, jail, journal, land_tool, models, work

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
            have = {s["step"] for s in lane["steps"]}
            lane["steps"] += [s for s in fresh["steps"] if s["step"] not in have]
        save([lane if x["id"] == lane["id"] else x for x in lanes])


def workers(root) -> int:
    f = Path(root) / "harness.toml"
    return int(tomllib.loads(f.read_text()).get("queue", {}).get("workers", 1)) if f.is_file() else 1


def add(lane_id: str, worktree: str, step: str, brief: str, issues: list[int], waits: list[str] | None = None) -> None:
    """A step at the end of its lane (made when new); a step the lane has already keeps its state."""
    with journal.Lock("queue"):
        lanes = load()
        lane = next((x for x in lanes if x["id"] == lane_id), None)
        if lane is None:
            lane = {"id": lane_id, "worktree": str(worktree), "cursor": 0, "seq": 0, "feed": "", "paused": False, "steps": []}
            lanes.append(lane)
        if any(s["step"] == step for s in lane["steps"]):
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


def tick_lane(lane: dict, procs: Procs, handles: dict, workers_n: int, push: bool, out) -> bool:
    """One pass over one lane. False when it can do nothing more without a person: finished, blocked or paused."""
    def move(s, state, detail=""):
        s["state"], s["why"] = state, detail[-500:]
        journal.append("queue", lane=lane["id"], step=s["step"], state=state, detail=detail[-300:])
        out(f"{lane['id']} {s['step']}: {state}" + (f" ({detail.strip().splitlines()[-1][:120]})" if detail.strip() else ""))
        store(lane)

    def block(s, why):
        (journal.STATE / f"question-{lane['id']}-{s['step']}.txt").write_text(f"QUESTION: {why}\n")
        move(s, "blocked", why)
        return False

    h = handles.get(lane["id"])
    if lane["cursor"] >= len(lane["steps"]):
        if h is not None:
            procs.stop(lane)
            del handles[lane["id"]]
        return False
    s = lane["steps"][lane["cursor"]]
    if s["state"] == "blocked":
        return False
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
        if lane["paused"]:
            return False
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
                procs.send(lane, Path(s["brief"]).read_text())
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
    try:
        r = procs.chain(lane, s, lambda stage: move(s, stage, ""))
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        r = {"ok": False, "kind": "error", "why": str(e)}
    if r["ok"]:
        s["head"] = r["head"]
        rc, output = procs.landed(lane, r["head"], push)
        if rc:
            return block(s, output)
        move(s, "landed", f"landed {r['head'][:9]}" + (" (pushed)" if push else " (not pushed)"))
        lane["cursor"] += 1
        store(lane)
        return True
    if r.get("kind") in ("red", "not-ready", "refused") and s["rounds"] < ROUNDS:
        s["rounds"] += 1
        lane["seq"] += 1
        procs.send(lane, FIX.format(step=s["step"], kind=r["kind"], findings=r.get("findings") or r["why"]))
        move(s, "sent", f"fix brief, round {s['rounds']}: {r['why']}")
        return True
    return block(s, f"{r['why']}\n{r.get('findings', '')}".strip())


def tick(procs: Procs, handles: dict, *, workers_n: int, push: bool, out=print) -> bool:
    busy = False
    for lane in load():
        busy = tick_lane(lane, procs, handles, workers_n, push, out) or busy
    return busy


def run(procs: Procs, *, workers_n: int, push: bool, tick_s: float = 30.0, once: bool = False, forever: bool = False, out=print) -> int:
    """Ticks until nothing can move without a person; `forever` (the verb) keeps ticking so a blocked or paused lane keeps its
    session and a resume from another shell is picked up."""
    handles: dict = {}
    while True:
        busy = tick(procs, handles, workers_n=workers_n, push=push, out=out)
        if once or not (busy or forever):
            return 0
        procs.sleep(tick_s)


def table() -> list[list[str]]:
    return [[x["id"], s["step"], s["state"], ", ".join(f"#{n}" for n in s["issues"]), s["head"][:9] or "-", s["why"].strip().replace("\n", " ")[:200]]
            for x in load() for s in x["steps"]]


def landed_argv(root, lane_id: str, head: str, push: bool) -> list[str]:
    """`builder landed` for a lane: the verdict store `builder work`'s chain wrote under the lane's name."""
    return [sys.executable, "-m", "fichero_builder", "landed", head, "--root", str(root), "--state", str(journal.STATE),
            "--verdicts", str(journal.STATE / f"verdicts-{lane_id}.json"), "--keep-worktree"] + (["--push"] if push else [])


def real_procs(root) -> Procs:
    root = Path(root)
    rules = tomllib.loads((root / "harness.toml").read_text())
    repo, branch = rules["check"]["engine_repo"], rules["land"]["branch"]
    mdl = models.load(root)
    builder, reviewer = models.for_role(mdl, "builder").model, models.for_role(mdl, "reviewer").model
    pkg = Path(__file__).resolve().parents[1]

    def ns(lane: dict, step: dict | None = None) -> types.SimpleNamespace:
        return types.SimpleNamespace(worktree=lane["worktree"], name=lane["id"], pinned=str(root), root=str(root), kind="claude", session="harness",
                                     tick=30.0, issues=step["issues"] if step else [], brief=step["brief"] if step else "", ids=[], repo=repo)

    def start(lane, step):
        a, q, g = ns(lane, step), shlex.quote, shlex.quote(work.jail_git())
        wt = q(lane["worktree"])
        r = work.as_worker(a, f"test -d {wt} || ({g} -C root fetch -q origin {q(branch)} && "
                              f"{g} -C root worktree add -q -b {q('lane-' + lane['id'])} {wt} origin/{q(branch)})")
        if r.returncode:
            raise RuntimeError(f"the lane's worktree could not be made: {(r.stderr or r.stdout).strip()[-300:]}")
        j = work._jail(a)
        feed = Path(j.workroot) / f"inbox-{lane['id']}-{lane['seq']}"  # the owner's folder: a worker cannot write its own next brief
        feed.mkdir(parents=True, exist_ok=True)
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
        return work.after_run(a, repo, branch, reviewer, stage=stage)

    def landed(lane, head, push):
        r = subprocess.run(landed_argv(root, lane["id"], head, push), cwd=str(pkg), capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(pkg)})
        return r.returncode, (r.stdout + r.stderr)[-2000:]

    def end_of(lane):
        return next((r["end"] for r in reversed(work._shared_rows(ns(lane))) if r.get("event") == "cost" and r.get("task") == lane["id"]
                     and r.get("end") != "handoff"), "gone")

    def stop(lane):
        if lane.get("feed"):
            (Path(lane["feed"]) / "stop").write_text("")

    return Procs(start=start, alive=lambda h: h.poll() is None, send=send, rebase=lambda lane: work.do_rebase(ns(lane), branch), row=row, chain=chain,
                 landed=landed, end_of=end_of, stop=stop)


def main(a) -> int:
    if a.action == "add":
        if not (a.lane and a.worktree and a.step and a.brief):
            print("REFUSED: queue add needs --lane, --worktree, --step and --brief")
            return 1
        add(a.lane, a.worktree, a.step, a.brief, a.issues)
        print(f"queued {a.lane} {a.step}")
        return 0
    if a.action in ("pause", "resume"):
        with journal.Lock("queue"):
            lanes = load()
            lane = next((x for x in lanes if x["id"] == a.lane), None)
            if lane is None:
                print(f"REFUSED: no lane {a.lane!r}")
                return 1
            lane["paused"] = a.action == "pause"
            if a.action == "resume":
                for s in lane["steps"]:
                    if s["state"] == "blocked":
                        s.update(state="queued", rounds=0, restarts=0, why="")
            save(lanes)
        journal.append("queue", lane=a.lane, step="-", state=a.action, detail="")
        return 0
    if a.action == "run":
        try:
            procs = real_procs(a.root)
        except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError, models.Question, jail.JailMissing) as e:
            print(f"REFUSED: the rules file cannot run the queue: {e}")
            return 1
        return run(procs, workers_n=workers(a.root), push=a.push, tick_s=a.tick, once=a.once, forever=not a.once)
    for row in table():
        print("\t".join(row))
    return 0
