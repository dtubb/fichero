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

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
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
            lane = {"id": lane_id, "worktree": os.path.abspath(worktree), "cursor": 0, "seq": 0, "feed": "", "paused": False, "steps": []}
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
    still_open: Callable[[dict, dict], list] = lambda lane, step: []  # (lane, step) -> issues of a landed step not closed, as "#N"
    # taken lane ids -> (lane id, worktree, [{step, brief, issues, waits}]) of the next build-order milestone, or None
    next_milestone: Callable[[set], tuple | None] = lambda taken: None


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
    def chain() -> dict:
        try:
            return procs.chain(lane, s, lambda stage: move(s, stage, ""))
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            return {"ok": False, "kind": "error", "why": str(e)}
    if chains is None:
        r = chain()
    elif fut is None:
        chains[lane["id"]] = chains["pool"].submit(chain)
        return True
    else:
        r = chains.pop(lane["id"]).result()
    if r["ok"]:
        s["head"] = r["head"]
        rc, output = procs.landed(lane, r["head"], push)
        if rc:
            return block(s, output)
        left = procs.still_open(lane, s)  # a row, not a close: only `builder landed` closes, on a Fixes line (owner ruling)
        move(s, "landed", f"landed {r['head'][:9]}" + (" (pushed)" if push else " (not pushed)") + (f"; still open: {', '.join(left)}" if left else ""))
        if left:
            journal.append("queue", lane=lane["id"], step=s["step"], state="issue-open", detail=", ".join(left))
        lane["cursor"] += 1
        store(lane)
        return True
    if r.get("kind") == "needs-maintainer":  # a pinned check changed on purpose: the manager's call, never the worker's
        return block(s, r["why"], ("approve", "send-back"), r.get("evidence", ""))
    if r.get("kind") in ("red", "not-ready", "refused") and s["rounds"] < ROUNDS:
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
    return block(s, f"{r['why']}\n{r.get('findings', '')}".strip(), evidence=r.get("evidence", ""))


ACTIONS = ("retry", "park", "ask-owner")


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
    if a is None or action not in a.get("actions", []):
        why = f"no alert {alert_id!r}" if a is None else f"{action!r} is not one of {a['actions']}"
        journal.append("alert-answer", id=alert_id, action=action, ok=False, detail=why)
        return 1, f"REFUSED: {why}"
    with journal.Lock("queue"):
        lanes = load()
        lane = next((x for x in lanes if x["id"] == a["lane"]), None)
        s = next((x for x in (lane or {}).get("steps", []) if x["step"] == a["step"]), None)
        if s is None:
            journal.append("alert-answer", id=alert_id, action=action, ok=False, detail="the lane or step is gone")
            return 1, "REFUSED: the lane or step is gone"
        if action in ("retry", "approve", "send-back"):
            s.update(state="queued" if action != "approve" else "done", rounds=0, restarts=0, why="")
            if action == "approve":
                s["maintainer"] = True  # the chain runs the check with --maintainer
            if action == "send-back":
                fix = journal.STATE / f"sendback-{alert_id}.txt"
                fix.write_text(Path(s["brief"]).read_text().rstrip("\n") + f"\n\nSent back by the manager: {a['what']}\nEvidence: {a['evidence']}\n")
                s["resume_brief"] = str(fix)
            lane["paused"] = False
            save(lanes)
    if action == "ask-owner":
        ask(s["issues"], f"{a['lane']} {a['step']}", f"{a['what']} (evidence: {a['evidence']})", gh=gh, cwd=cwd)
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
        if sum(1 for x in lanes if x["cursor"] < len(x["steps"])) >= lanes_n:
            return took
        nxt = procs.next_milestone({x["id"] for x in lanes})
        if not nxt:
            return took
        lane_id, worktree, steps = nxt
        for st in steps:
            add(lane_id, worktree, st["step"], st["brief"], st["issues"], waits=st.get("waits"))
        journal.append("queue", lane=lane_id, step="-", state="milestone", detail=f"taken: {len(steps)} steps")
        out(f"{lane_id}: taken from the build order, {len(steps)} steps")
        took = True


def tick(procs: Procs, handles: dict, *, workers_n: int, push: bool, out=print, chains: dict | None = None) -> bool:
    busy = False
    for lane in load():
        busy = tick_lane(lane, procs, handles, workers_n, push, out, chains) or busy
    return busy


def run(procs: Procs, *, workers_n: int, push: bool, lanes_n: int = 1, tick_s: float = 30.0, once: bool = False, forever: bool = False,
        heartbeat: bool = False, out=print) -> int:
    """Ticks until nothing can move without a person; `forever` (the verb) keeps ticking so a blocked or paused lane keeps its
    session and a resume from another shell is picked up. Each tick first takes build-order milestones up to `lanes_n`."""
    handles: dict = {}
    # the loop always chains in a thread: a one-lane check inside the tick would starve the heartbeat for its whole ladder
    chains: dict | None = {"pool": ThreadPoolExecutor(max_workers=lanes_n)} if lanes_n > 1 or heartbeat else None
    while True:
        took = feed(procs, lanes_n, out)
        busy = tick(procs, handles, workers_n=workers_n, push=push, out=out, chains=chains) or took
        if heartbeat:  # dev-workflows.run.loop: a watchdog reads the gap between these
            journal.append("loop", state="tick", lanes=[f"{x['id']} {x['cursor']}/{len(x['steps'])}" for x in load()], busy=busy)
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
        brief = (step.get("resume_brief") or step["brief"]) if step else ""  # a fix brief after a gone session (run.loop-fix-rounds)
        return types.SimpleNamespace(worktree=lane["worktree"], name=lane["id"], pinned=str(root), root=str(root), kind="claude", session="harness",
                                     tick=30.0, issues=step["issues"] if step else [], brief=brief, ids=[], repo=repo,
                                     maintainer=bool(step and step.get("maintainer")))

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

    def stop(lane):
        if lane.get("feed"):
            (Path(lane["feed"]) / "stop").write_text("")

    return Procs(start=start, alive=lambda h: h.poll() is None, send=send, rebase=lambda lane: work.do_rebase(ns(lane), branch), row=row, chain=chain,
                 landed=landed, end_of=end_of, stop=stop, still_open=lambda lane, step: open_of(step["issues"], cwd=str(root)),
                 next_milestone=lambda taken: next_in_order(root, taken))


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
        issues = milestone.list_issues(title, gh=gh)
        if not issues:
            continue
        spec_path = root / triage.SPECS / spec
        planned = milestone.plan(issues, milestone.build_order(spec_path), milestone.spec_slug(spec_path))
        for q in planned["questions"]:
            journal.append("queue", lane=lane, step="-", state="question", detail=q[-300:])
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
        add(a.lane, a.worktree, a.step, a.brief, a.issues)
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
