"""The Pi worker kind over RPC (dev-workflows.node.worker, Step 3.1): `pi --mode rpc` on a pipe, `prompt`, `steer`,
`abort`, `get_session_stats`; the policy a `tool_call` extension asks of us (`fichero-builder/pi/policy.ts`), which
blocks on any answer but ALLOW and on its own crash. Pi 0.75.5's rpc.md: JSON lines, LF only, `id` correlates
responses, events carry no id. Imports nothing from the engine.
ponytail: one reader thread and a queue; no reconnect, a dead Pi is a dead worker (the watcher parks it)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from fichero_builder import policy_hook as ph

# Pi's tool names -> the policy's (Claude Code's) event shape. An unknown tool name REFUSES (node.worker).
_READ_ONLY = {"read", "grep", "find", "ls"}


def policy_event(tool: str, inp: dict, worktree: Path) -> dict | None:
    """None when the policy has no name for the tool (refuse); else the event `policy_hook.check` reads."""
    def path():
        p = Path(str(inp.get("path") or ""))
        return str(p if p.is_absolute() else Path(worktree) / p)
    if tool == "bash":
        return {"tool_name": "Bash", "tool_input": {"command": str(inp.get("command") or "")}}
    if tool in ("write", "edit"):
        return {"tool_name": tool.capitalize(), "tool_input": {"file_path": path()}}
    if tool in _READ_ONLY:
        return {"tool_name": "Read", "tool_input": {"file_path": path()}}
    return None


def decide(call: dict, cfg: dict, *, worktree: Path, scratch: Path) -> str | None:
    """None allows; else the reason. `call` is what the extension sends: {toolName, input}."""
    ev = policy_event(str(call.get("toolName") or ""), call.get("input") or {}, worktree)
    if ev is None:
        return f"policy has no rule for Pi tool {call.get('toolName')!r}; unknown tools are refused"
    return ph.check(ev, cfg, worktree=worktree, scratch=scratch)


def policy_argv(root, worktree, scratch) -> list[str]:
    return [sys.executable, "-m", "fichero_builder.pi_rpc", "policy", "--root", str(root), "--worktree", str(worktree), "--scratch", str(scratch)]


EXTENSION = Path(__file__).resolve().parents[1] / "pi" / "policy.ts"


class Pi:
    """One `pi --mode rpc` process. `send` returns the matching response; events queue up in `events`."""

    def __init__(self, cmd: list[str], *, cwd, env: dict, timeout_s: float = 60.0):
        # bytes on purpose: iterating a binary pipe splits on LF only (rpc.md Framing); text mode would also split on \r
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        self.events: queue.Queue = queue.Queue()
        self._responses: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._n = 0
        self.timeout_s = timeout_s
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") == "response" and "id" in o:
                with self._lock:
                    self._responses[o["id"]] = o
            else:
                self.events.put(o)

    def send(self, cmd: dict, timeout_s: float | None = None) -> dict:
        self._n += 1
        rid = f"r{self._n}"
        self.proc.stdin.write((json.dumps({**cmd, "id": rid}) + "\n").encode())
        self.proc.stdin.flush()
        end = time.time() + (timeout_s or self.timeout_s)
        while time.time() < end:
            with self._lock:
                r = self._responses.pop(rid, None)
            if r is not None:
                return r
            if self.proc.poll() is not None:
                err = self.proc.stderr.read().decode("utf-8", "replace")[-500:]
                raise RuntimeError(f"pi exited {self.proc.returncode} before answering {cmd.get('type')}: {err}")
            time.sleep(0.02)
        raise TimeoutError(f"pi did not answer {cmd.get('type')} in {timeout_s or self.timeout_s}s")

    def prompt(self, text: str) -> dict:
        return self.send({"type": "prompt", "message": text})

    def steer(self, text: str) -> dict:
        return self.send({"type": "prompt", "message": text, "streamingBehavior": "steer"})

    def abort(self) -> dict:
        return self.send({"type": "abort"})

    def stats(self) -> dict:
        return self.send({"type": "get_session_stats"}).get("data") or {}

    def state(self) -> dict:
        return self.send({"type": "get_state"}).get("data") or {}

    def wait(self, until: str = "agent_end", timeout_s: float = 120.0) -> list[dict]:
        """Drain events until one of `until` type (or the process ends); returns everything seen."""
        seen, end = [], time.time() + timeout_s
        while time.time() < end:
            try:
                e = self.events.get(timeout=0.2)
            except queue.Empty:
                if self.proc.poll() is not None:
                    break
                continue
            seen.append(e)
            if e.get("type") == until:
                break
        return seen

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self, grace_s: float = 5.0) -> None:
        if not self.alive():
            return
        try:
            self.send({"type": "abort"}, timeout_s=2)
        except (RuntimeError, TimeoutError, OSError):
            pass
        self.proc.terminate()
        try:
            self.proc.wait(grace_s)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def start(worktree, *, root, scratch, model: str, provider: str, session_dir, agent_dir=None, env=None,
          pi_bin: str = "pi", extra: list[str] = ()) -> Pi:
    """Pi in RPC mode in the worktree with the policy extension and nothing else (`--no-extensions` first, then ours)."""
    e = {**(env or os.environ)}
    e["FICHERO_PI_POLICY_ARGV"] = json.dumps(policy_argv(root, worktree, scratch))
    e["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    if agent_dir:
        e["PI_CODING_AGENT_DIR"] = str(agent_dir)
    cmd = [pi_bin, "--mode", "rpc", "--no-extensions", "-e", str(EXTENSION), "--provider", provider, "--model", model,
           "--session-dir", str(session_dir), *extra]
    return Pi(cmd, cwd=worktree, env=e)


def priced(agent_dir, provider: str, model: str) -> bool:
    """Pi prices each turn from its models.json; a model with no `cost` there would run under a cap that reads zero."""
    f = Path(agent_dir) / "models.json"
    if not f.is_file():
        return False
    try:
        rows = (json.loads(f.read_text()).get("providers", {}).get(provider) or {}).get("models") or []
    except ValueError:
        return False
    return any(r.get("id") == model and isinstance(r.get("cost"), dict) for r in rows)


def pi_procs(*, root, scratch, provider: str, session_dir, agent_dir=None, pi_bin: str = "pi"):
    """The Pi kind's Procs for `run`: start = Pi in RPC mode fed the brief; read = the newest session file under
    --session-dir through the same parser as Claude's; tell = `steer`; stop = abort, TERM, kill."""
    from fichero_builder import session
    from fichero_builder.run import Procs, _head

    live: dict[str, Pi] = {}
    wt: list = []

    def _start(root_, worktree, brief, name, model, tmux_session) -> str:
        pi = start(worktree, root=root_, scratch=scratch, model=model, provider=provider, session_dir=session_dir,
                   agent_dir=agent_dir, pi_bin=pi_bin)
        handle = f"pi:{pi.proc.pid}"
        live[handle] = pi
        wt[:] = [worktree]
        pi.prompt(Path(brief).read_text())
        return handle

    def _read():
        files = session.session_files(Path(session_dir))
        return session.parse_session(files[-1]) if files else None

    def _tell(handle, words):
        if (pi := live.get(handle)) and pi.alive():
            pi.steer(words)

    def _stop(handle):
        if pi := live.pop(handle, None):
            pi.stop()

    return Procs(start=_start, alive=lambda h: bool(live.get(h)) and live[h].alive(), stop=_stop, read=_read,
                 head=lambda: _head(wt[0]) if wt else "", tell=_tell)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="fichero_builder.pi_rpc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("policy", help="stdin: {toolName, input}; prints ALLOW, or the reason on stderr with exit 2")
    p.add_argument("--root", required=True), p.add_argument("--worktree", required=True), p.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    call = json.load(sys.stdin)
    reason = decide(call, ph.load(a.root), worktree=Path(a.worktree), scratch=Path(a.scratch))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    print("ALLOW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
