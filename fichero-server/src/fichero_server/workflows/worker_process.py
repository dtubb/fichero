"""The engine starts a worker process, watches it, records it as a job row, and stops it (#6116).

The worker's loop lives in the agent harness (Claude Code; `fake` replays a scenario with no model).
The engine only holds the record: a `worker` job row (running -> done / failed / cancelled) that
Activity shows, with the worker's last line as the row's words and its tail, exit code and cwd as
detail. Stopping kills the worker's whole process group.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs
from fichero_server.workflows.tools.cli_agent import _build_command

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
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self.proc = proc
        self.pgid = proc.pid
        self.tail: deque[str] = deque(maxlen=_TAIL)
        self.ended_by: str | None = None  # "stop" | "timeout"
        self.finished = threading.Event()
        self.state = "running"


_WORKERS: dict[str, _Worker] = {}


def _kill(w: _Worker) -> None:
    try:
        os.killpg(w.pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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
) -> str:
    """Start a worker of `kind` ("claude" or "fake") in `workdir`; returns its job id."""
    if kind == "claude":
        argv = _build_command(cli="claude", prompt=brief, use_ollama_launch=False, ollama_model="")
    elif kind == "fake":
        argv = [sys.executable, "-c", _FAKE, json.dumps(scenario or {})]
    else:
        raise ValueError(f"unknown worker kind {kind!r}")
    cwd = Path(workdir)
    if not cwd.is_dir():
        raise ValueError(f"workdir {str(cwd)!r} is not a directory")
    if not timeout_s or timeout_s <= 0:
        raise ValueError("a worker needs a positive timeout_s")
    job_id = f"worker-{uuid.uuid4().hex[:12]}"
    # As cli_agent (#5186): no stdin; own process group so a stop or timeout kills what it started.
    proc = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", start_new_session=True,
    )
    w = _WORKERS[job_id] = _Worker(proc)
    jobs._record(db, job_id, kind=KIND, subject=job_id, parent_id=None, state="running", reason=None, name=f"Worker ({kind})")
    threading.Thread(target=_watch, args=(db, job_id, w, kind, str(cwd), timeout_s), daemon=True).start()
    return job_id


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
