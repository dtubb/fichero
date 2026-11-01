"""The engine starts a worker process, watches it, records it as a job row, and stops it (#6116).

The worker's loop lives in the agent harness. `claude` is an interactive session in a tmux window (as
builder_hook.py runs it: long-running, tellable, hook-driven; NOT `claude -p`), started with an empty
`--strict-mcp-config` so the owner's fichero MCP (the real library) never reaches it. `fake` replays a scenario
with no model.
The engine only holds the record: a `worker` job row (running -> done / failed / cancelled) that
Activity shows, with the worker's last line as the row's words and its tail, exit code and cwd as
detail. Stopping kills the worker's whole process group.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs

KIND = "worker"
_TAIL = 20

# Replays a scenario: print its lines, optionally start a child, hang, exit with its code.
_FAKE = (
    "import json,subprocess,sys,time\n"
    "s=json.loads(sys.argv[1])\n"
    "[print(l,flush=True) for l in s.get('lines',[])]\n"
    "s.get('child') and subprocess.Popen(['sleep','300'])\n"
    "s.get('hang') and time.sleep(300)\n"
    "sys.exit(s.get('exit',0))\n"
)


class _Worker:
    def __init__(self, pgid: int, proc: subprocess.Popen[str] | None = None) -> None:
        self.proc = proc  # None for a tmux pane: watched by its log file and its process group
        self.pgid = pgid
        self.pane = ""
        self.log = Path()
        self.status = Path()
        self.tail: deque[str] = deque(maxlen=_TAIL)
        self.ended_by: str | None = None  # "stop" | "timeout"
        self.finished = threading.Event()
        self.state = "running"
        self.jail: Any = None  # the second macOS user it runs as (workflows/jail.py); None for the fake kind


_WORKERS: dict[str, _Worker] = {}


def _tmux(jail: Any, *args: str) -> subprocess.CompletedProcess[str]:
    """tmux as the jailed user (its own per-user socket), or as us when there is no jail."""
    argv = ["tmux", *args]
    if jail is not None:
        argv = jail.argv(argv, env={"PATH": os.environ.get("PATH", "")})
    return subprocess.run(argv, capture_output=True, text=True)


def _kill(w: _Worker) -> None:
    if w.jail is not None:  # another uid: signals go through the jail
        subprocess.run(w.jail.argv(["/bin/kill", "-KILL", "--", f"-{w.pgid}"], env={}), capture_output=True)
    else:
        try:
            os.killpg(w.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if w.pane:
        _tmux(w.jail, "kill-pane", "-t", w.pane)


def _alive(w: _Worker) -> bool:
    if w.jail is not None:
        return subprocess.run(w.jail.argv(["/bin/kill", "-0", "--", f"-{w.pgid}"], env={}), capture_output=True).returncode == 0
    return any_alive([w.pgid])


def _watch(db: Any, job_id: str, w: _Worker, kind: str, cwd: str, timeout_s: float) -> None:
    timer = threading.Timer(timeout_s, lambda: (setattr(w, "ended_by", w.ended_by or "timeout"), _kill(w)))
    timer.start()
    try:
        for line in w.proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if line:
                jobs.say(db, job_id, line)  # the row first, so a reader of the tail finds it already said
                w.tail.append(line)
        code = w.proc.wait()
    finally:
        timer.cancel()
    _settle(db, job_id, w, kind, cwd, timeout_s, code)


_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")


def _watch_pane(db: Any, job_id: str, w: _Worker, kind: str, cwd: str, timeout_s: float) -> None:
    """A tmux pane has no pipe to read: follow its pipe-pane log for the row's words, and its process group for the end."""
    deadline = time.monotonic() + timeout_s
    pos = 0
    while True:
        alive = _alive(w)
        if w.log.exists():
            data = w.log.read_bytes()
            chunk, pos = data[pos:].decode("utf-8", "replace"), len(data)
            for line in _ANSI.sub("", chunk).splitlines():
                if line.strip():
                    jobs.say(db, job_id, line.strip())
                    w.tail.append(line.strip())
        if not alive:
            break
        if time.monotonic() > deadline:
            w.ended_by = w.ended_by or "timeout"
            _kill(w)
        time.sleep(0.2)
    try:
        code = int(w.status.read_text().strip())
    except (OSError, ValueError):
        code = -9 if w.ended_by else None
    _settle(db, job_id, w, kind, cwd, timeout_s, code)


def _settle(db: Any, job_id: str, w: _Worker, kind: str, cwd: str, timeout_s: float, code: int | None) -> None:
    if w.ended_by == "stop":
        state, reason = "cancelled", "Stopped"
    elif w.ended_by == "timeout":
        state, reason = "failed", f"The worker timed out after {timeout_s:g}s"
    elif code == 0:
        state, reason = "done", None
    else:
        state, reason = "failed", f"The worker exited with code {code}"
    detail = json.dumps({"worker": kind, "cwd": cwd, "exit_code": code, "tail": list(w.tail)})
    jobs._record(db, job_id, kind=KIND, subject=job_id, parent_id=None, state=state, reason=reason, name=f"Worker ({kind})")
    jobs.save_detail(db, job_id, detail)
    w.state = state
    w.finished.set()


def stop(db: Any, job_id: str) -> str:
    """Stop a worker: kill its process group; its row settles `cancelled` as the watcher sees it end."""
    w = _WORKERS.get(job_id)
    if w is not None and not w.finished.is_set():
        w.ended_by = w.ended_by or "stop"
        _kill(w)
    return jobs._job_row(db, job_id)[1]


jobs.register_kind(KIND, None, model=None, name="Worker", cancel=stop)


def start(
    db: Any,
    *,
    kind: str,
    brief: str,
    workdir: str | Path,
    timeout_s: float,
    scenario: dict[str, Any] | None = None,
    tmux_session: str = "",
    claude_bin: str = "claude",
    model: str = "sonnet",
    task: str = "",
    jail: Any = None,
) -> str:
    """Start a worker of `kind` ("claude" or "fake") in `workdir`; returns its job id. `claude` needs the tmux
    session to open its window in (`tmux_session`).
    ponytail: --dangerously-skip-permissions as builder_hook.py does, until the per-worker sandbox lands."""
    if os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower() != "dev":
        raise PermissionError("dev workers run only on a dev-tier engine")
    if os.environ.get("FICHERO_DEV_WORKERS") != "1":  # a dev DMG on the real library is dev tier too (review 3 H4)
        raise PermissionError("dev workers start only when the launcher sets FICHERO_DEV_WORKERS=1")
    if kind not in ("claude", "fake"):
        raise ValueError(f"unknown worker kind {kind!r}")
    if kind == "claude":  # owner 2026-10-31: a worker runs as the second macOS user or does not start; no fallback
        if jail is None:
            raise PermissionError("a claude worker runs as the jail user; none is configured (harness.toml [jail])")
        jail.require()
        if wall := jail.probe():
            raise PermissionError("the jail leaks: " + "; ".join(wall))
    if kind == "claude" and not tmux_session:
        raise ValueError("a claude worker needs the tmux_session to open its window in")
    cwd = Path(workdir)
    if not cwd.is_dir():
        raise ValueError(f"workdir {str(cwd)!r} is not a directory")
    if not timeout_s or timeout_s <= 0:
        raise ValueError("a worker needs a positive timeout_s")
    job_id = f"worker-{uuid.uuid4().hex[:12]}"
    if kind == "claude":
        _start_pane(db, job_id, brief, cwd, timeout_s, tmux_session, claude_bin, model, jail)
        _set_address(db, task, job_id, kind, _WORKERS[job_id].pane, _WORKERS[job_id].log.parent)
        return job_id
    argv = [sys.executable, "-c", _FAKE, json.dumps(scenario or {})]
    # As cli_agent (#5186): no stdin; own process group so a stop or timeout kills what it started.
    proc = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", start_new_session=True,
    )
    w = _WORKERS[job_id] = _Worker(proc.pid, proc)
    jobs._record(db, job_id, kind=KIND, subject=job_id, parent_id=None, state="running", reason=None, name=f"Worker ({kind})")
    _set_address(db, task, job_id, kind, "", "")
    threading.Thread(target=_watch, args=(db, job_id, w, kind, str(cwd), timeout_s), daemon=True).start()
    return job_id


def _start_pane(db: Any, job_id: str, brief: str, cwd: Path, timeout_s: float, session: str, claude_bin: str, model: str, jail: Any) -> str:
    scratch = Path(jail.mkdtemp(f"{job_id}-"))  # under the shared workroot: the jailed user writes the log and exit code
    mcp = scratch / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {}}))  # with --strict-mcp-config: no MCP server at all, not the owner's
    log, status = scratch / "pane.log", scratch / "exit_code"
    cmd = (f"cd {shlex.quote(str(cwd))} && {shlex.quote(claude_bin)} --dangerously-skip-permissions --model {shlex.quote(model)} "
           f"--strict-mcp-config --mcp-config={shlex.quote(str(mcp))} {shlex.quote(brief)}; echo $? > {shlex.quote(str(status))}")
    r = _tmux(jail, "new-window", "-d", "-P", "-F", "#{pane_id} #{pane_pid}", "-t", session, "-n", job_id, cmd)
    if r.returncode:
        raise RuntimeError(f"tmux could not open the worker window: {r.stderr.strip()}")
    pane, pid = r.stdout.split()
    _tmux(jail, "pipe-pane", "-t", pane, f"cat >> {shlex.quote(str(log))}")
    w = _WORKERS[job_id] = _Worker(int(pid))
    w.jail = jail
    w.pane, w.log, w.status = pane, log, status
    jobs._record(db, job_id, kind=KIND, subject=job_id, parent_id=None, state="running", reason=None, name="Worker (claude)")
    threading.Thread(target=_watch_pane, args=(db, job_id, w, "claude", str(cwd), timeout_s), daemon=True).start()
    return job_id


class StaleWorker(Exception):
    """A tell addressed to a worker generation that is not the task's current one (or to a task with none)."""


_ADDR_DDL = ("CREATE TABLE IF NOT EXISTS worker_addresses (task TEXT PRIMARY KEY, generation INTEGER NOT NULL, "
             "job_id TEXT NOT NULL, kind TEXT NOT NULL, pane TEXT NOT NULL, session_dir TEXT NOT NULL)")


def _set_address(db: Any, task: str, job_id: str, kind: str, pane: str, session_dir: Any) -> None:
    """(dev-workflows.run.worker-address) Rewrite the task's address to this generation; no `task` = untracked."""
    if not task:
        return
    db.execute(_ADDR_DDL)
    prev = db.execute_fetchone("SELECT generation FROM worker_addresses WHERE task = ?", [task])
    gen = (prev[0] if prev else 0) + 1
    db.execute("DELETE FROM worker_addresses WHERE task = ?", [task])
    db.execute("INSERT INTO worker_addresses VALUES (?, ?, ?, ?, ?, ?)", [task, gen, job_id, kind, pane, str(session_dir)])


def address(db: Any, task: str) -> dict[str, Any] | None:
    db.execute(_ADDR_DDL)
    r = db.execute_fetchone("SELECT generation, job_id, kind, pane, session_dir FROM worker_addresses WHERE task = ?", [task])
    return dict(zip(("generation", "job_id", "kind", "pane", "session_dir"), r)) if r else None


def tell(db: Any, task: str, generation: int, text: str) -> None:
    """Type `text` into the task's current worker pane. Refused for any other generation."""
    a = address(db, task)
    if a is None or a["generation"] != generation:
        raise StaleWorker(f"task {task!r}: generation {generation} is not the current worker "
                          f"({a['generation'] if a else 'none'})")
    if not a["pane"]:
        raise StaleWorker(f"task {task!r}: its worker has no pane to tell")
    jail = _WORKERS[a["job_id"]].jail if a["job_id"] in _WORKERS else None
    for args in (("send-keys", "-t", a["pane"], "-l", text), ("send-keys", "-t", a["pane"], "Enter")):
        if _tmux(jail, *args).returncode:
            raise RuntimeError("tmux could not send the keys")
        time.sleep(0.2)  # a bare send-keys loses the Enter; send it on its own


def wait(job_id: str, timeout: float) -> str | None:
    """The worker's final state, or None if it is still running after `timeout` seconds."""
    w = _WORKERS[job_id]
    return w.state if w.finished.wait(timeout) else None


def wait_for_line(job_id: str, text: str, timeout: float) -> bool:
    w = _WORKERS[job_id]
    deadline = threading.Event()
    for _ in range(int(timeout * 20)):
        if text in w.tail:
            return True
        deadline.wait(0.05)
    return False


def pids(job_id: str) -> list[int]:
    return [_WORKERS[job_id].pgid]


def any_alive(group_ids: list[int]) -> bool:
    for g in group_ids:
        try:
            os.killpg(g, 0)
            return True
        except ProcessLookupError:
            pass
    return False
