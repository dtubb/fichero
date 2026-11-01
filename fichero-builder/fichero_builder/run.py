"""`builder run`: one process starts a worker through the start path and watches its session file
(dev-workflows.run.worker-start-stop, run.watch-tick). Runs AS the worker user: the session file is in that user's home
and the start path refuses anyone else. Process control is a small `Procs` so a dry run swaps in fakes
(dev-workflows.rollout.dry-run); nothing here types into a pane."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fichero_builder import journal, session, watcher

HERE = Path(__file__).resolve().parent
START = HERE.parents[1] / "scripts" / "harness_start.py"


def slug(worktree) -> str:
    """Claude Code keeps a project's session files under ~/.claude/projects/<cwd with / as ->."""
    return str(Path(worktree).resolve()).replace("/", "-")


def session_dir(home, worktree) -> Path:
    return Path(home) / ".claude" / "projects" / slug(worktree)


def newest_session(home, worktree) -> Path | None:
    files = session.session_files(session_dir(home, worktree))
    return files[-1] if files else None


@dataclass
class Procs:
    """What the loop does to the world; a dry run replaces each one."""
    start: Callable[..., str]                 # (root, worktree, brief, name, model, tmux_session) -> pane id
    alive: Callable[[str], bool]              # pane id -> still there
    stop: Callable[[str], None]               # pane id -> gone
    read: Callable[[], dict | None]           # the newest session file parsed, or None before the first turn
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.time


def _start(root, worktree, brief, name, model, tmux_session) -> str:
    r = subprocess.run([sys.executable, str(START), "--root", str(root), "--worktree", str(worktree), "--brief", str(brief),
                        "--name", name, "--model", model, "--session", tmux_session], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "harness_start failed")
    return r.stdout.strip()


def _alive(pane: str) -> bool:
    out = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_id}"], capture_output=True, text=True).stdout.split()
    return pane in out


def _stop(pane: str, grace_s: float = 10.0) -> None:
    """TERM the pane's process group, wait the grace, then kill the pane (an interactive session never exits on its own)."""
    pid = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{pane_pid}"], capture_output=True, text=True).stdout.strip()
    if pid.isdigit():
        subprocess.run(["kill", "-TERM", "--", f"-{pid}"], capture_output=True)
        for _ in range(int(grace_s * 10)):
            if not _alive(pane):
                return
            time.sleep(0.1)
    subprocess.run(["tmux", "kill-pane", "-t", pane], capture_output=True)


def real_procs(home, worktree) -> Procs:
    def read():
        f = newest_session(home, worktree)
        return session.parse_session(f) if f else None
    return Procs(start=_start, alive=_alive, stop=_stop, read=read)


DONE = re.compile(r"\bDONE\b")
HANDOFF_READY = "HANDOFF READY"


def successor_brief(name: str, gen: int, worktree, handoff) -> str:
    """The successor's whole brief: read the handoff, carry on, same rules, same end line (dev-workflows.worker.handoff)."""
    return (f"You succeed long-running worker {name} (generation {gen}). Work in {worktree}. Read {handoff} first, then continue "
            f"the work it lists, in order, under the rules it gives. When told your context is at 85%, finish the step, commit, "
            f"update {handoff}, and end your turn with the exact line {HANDOFF_READY}. When every item is done, end with the DONE line.")


def run(root, worktree, brief, *, name: str, model: str = "sonnet", kind: str = "claude", tmux_session: str = "harness",
        tick_s: float = 30.0, procs: Procs, out=print, done=DONE, handoff=None, max_generations: int = 20) -> str:
    """Start, then watch until the worker is done (idle with the DONE word in its last text: the brief's own end line),
    parked (a cap or a provider refusal) or gone. Returns the end as a word.
    Handoff: the in-session hook tells the worker at 85 %; when the worker is then idle with HANDOFF READY in its last text,
    the loop ends it (TERM, grace, kill) and starts a successor through the same start path with a brief that names the
    handoff file (`<worktree>/HANDOFF.md` unless given); the successor is the same name, generation plus one."""
    spend = watcher.load(root)
    bad = watcher.refusals(spend, kind, model)
    if bad:
        for b in bad:
            out("builder run refuses: " + b)
        return "refused"
    handoff = Path(handoff) if handoff else Path(worktree) / "HANDOFF.md"
    gen = 1
    pane = procs.start(root, worktree, brief, name, model, tmux_session)
    journal.append("worker", task=name, pane=pane, model=model, kind=kind, worktree=str(worktree), generation=gen)
    started = last_change = procs.now()
    seen = None
    told: set[str] = set()
    state: dict = {}
    while True:
        procs.sleep(tick_s)
        now = procs.now()
        st = procs.read()
        if st is not None:
            key = (st.get("turns"), st.get("tokens"), st.get("idle"))
            if key != seen:
                seen, last_change = key, now
            state = st
        if not procs.alive(pane):
            end = "gone"
            break
        today = time.strftime("%Y-%m-%d")  # the journal stamps rows with the wall clock
        decisions = watcher.assess(state, spend, model, spent_today=watcher.spent_today(journal.read(), today),
                                   silent_for_s=now - last_change)
        for d in decisions:
            kind_of = d.split(":")[0]  # one row per kind of decision, not one per tick
            if kind_of not in told:
                journal.append("watch", task=name, what=d)
                out(f"{name}: {d}")
                told.add(kind_of)
        if any(d.startswith("park") for d in decisions):
            procs.stop(pane)
            end = "parked"
            break
        if state.get("idle") and done.search(state.get("last_text", "")):
            procs.stop(pane)
            end = "done"
            break
        if state.get("idle") and HANDOFF_READY in state.get("last_text", ""):
            if gen >= max_generations:
                procs.stop(pane)
                end = "parked"
                journal.append("watch", task=name, what=f"park: {gen} generations, the cap")
                break
            procs.stop(pane)
            journal.append("cost", task=name, model=model, usd=round(watcher.cost_of(state, spend, model), 4),
                           tokens=state.get("tokens", 0), turns=state.get("turns", 0), seconds=int(now - started), end="handoff",
                           generation=gen)
            gen += 1
            b = Path(worktree) / f".builder-brief-{name}-{gen}.txt"
            b.write_text(successor_brief(name, gen, worktree, handoff))
            pane = procs.start(root, worktree, b, name, model, tmux_session)
            journal.append("worker", task=name, pane=pane, model=model, kind=kind, worktree=str(worktree), generation=gen)
            out(f"{name}: handoff, generation {gen} started")
            started = last_change = procs.now()
            seen, state, told = None, {}, set()
            continue
    journal.append("cost", task=name, model=model, usd=round(watcher.cost_of(state, spend, model), 4),
                   tokens=state.get("tokens", 0), turns=state.get("turns", 0), seconds=int(procs.now() - started), end=end,
                   generation=gen)
    out(f"{name}: {end}")
    return end
