#!/usr/bin/env python3
"""A long-running worker hands off at 85% of its context; its successor starts through scripts/harness_start.py
(worker user, probe, rules file), never by a bare `claude` (dev-workflows run.slice-zero item 3).

Hook for PostToolUse and Stop. Does nothing unless the session's worker is registered:
  $FICHERO_HARNESS_REG (default ~/.claude/builders)/<name>.json =
    {"worktree": ..., "handoff": ..., "model": "sonnet", "window": 200000, "session": "<tmux session>",
     "notify": ["argv", "prefix"],      # notify + message is run to tell the manager; omit = silent
     "successor": "watcher"}            # `builder run` wrote it: the hook tells and nudges, the watcher ends and starts
The name comes from $FICHERO_BUILDER (set by harness_start.py).
PostToolUse at 85%: tells the worker once to finish, commit, write the handoff and end with HANDOFF READY.
Stop: without that line the worker is told to continue (capped) unless its message has a `WAITING: ` line
or the brief's end line `DONE <sha>` (then `builder run` ends the worker);
with it the successor starts, once per session. Never run this from inside your own session (it TERMs the claude above it).
ponytail: context is read from the transcript's last usage; if that format changes the worker is never told. --test self-checks."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DONE = "HANDOFF READY"
WAIT = "WAITING:"
ENDED = re.compile(r"^DONE [0-9a-f]{7,}", re.M)  # the brief's own end line: `builder run` ends the worker on it
NUDGES = 20
AT = 0.85
HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("FICHERO_HARNESS_REG") or os.path.expanduser("~/.claude/builders"))


def claude_process():
    """(pid, argv) of the claude process above this hook; hooks may run under a shell."""
    pid = os.getppid()
    for _ in range(4):
        out = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
        if not out:
            break
        if "claude" in out[1]:
            return pid, out[1:]
        pid = int(out[0])
    return None, []


def context_used(path):
    """Tokens in the last assistant turn's prompt, from the transcript's tail; 0 if unreadable."""
    try:
        with open(path, "rb") as f:
            start = max(0, os.path.getsize(path) - 300_000)
            f.seek(start)
            lines = f.read().split(b"\n")[1 if start else 0:]  # a seek lands mid-line
    except OSError:
        return 0
    for line in reversed(lines):
        try:
            msg = json.loads(line).get("message")
            usage = msg.get("usage") if isinstance(msg, dict) else None
        except (ValueError, AttributeError):
            continue
        if usage:
            return sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return 0


def brief_text(name, reg, gen):
    return (f"You succeed long-running worker {name} (generation {gen}). Work in {reg['worktree']}. "
            f"Read {reg['handoff']} first, then continue the work it lists, in order, under the rules it gives. "
            f"When told your context is at 85%, finish the step, commit, update {reg['handoff']}, "
            f"and end your turn with the exact line {DONE}.")


def start_successor(name, reg, gen, run=subprocess.run):
    """Through harness_start.py only; its refusals come back as a failed result. The name stays the same: FICHERO_BUILDER keys the registry."""
    brief = Path(tempfile.mkdtemp(prefix="handoff-")) / "brief.txt"
    brief.write_text(brief_text(name, reg, gen))
    argv = [sys.executable, str(HERE / "harness_start.py"), "--worktree", reg["worktree"], "--brief", str(brief),
            "--name", name, "--model", reg.get("model", "sonnet")]
    if reg.get("session"):
        argv += ["--session", reg["session"]]
    return run(argv, capture_output=True, text=True)


def tell(reg, message, run=subprocess.run):
    if reg.get("notify"):
        run([*reg["notify"], message])


def on_post_tool(event, name, reg, state):
    sid = event.get("session_id", "")
    if state.get("told") == sid or context_used(event.get("transcript_path", "")) < AT * reg.get("window", 200_000):
        return None, state
    words = (f"Your context is at 85%. Finish this step, commit, update {reg['handoff']} so a successor can continue "
             f"without asking, and end your turn with the exact line {DONE}. A successor starts automatically.")
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": words}}, dict(state, told=sid)


def on_stop(event, name, reg, state, run=subprocess.run):
    sid = event.get("session_id", "")
    last = event.get("last_assistant_message") or ""
    if DONE not in last:
        # ponytail: a cap per session stops a loop; the manager's check catches a worker past it.
        n = state.get("nudges", {}).get(sid, 0)
        if WAIT in last or ENDED.search(last) or n >= NUDGES:
            return None, state
        words = f"Continue with the next item in {reg['handoff']} without waiting. If nothing can be done until someone acts, say why on a line starting {WAIT}"
        return {"decision": "block", "reason": words}, dict(state, nudges={**state.get("nudges", {}), sid: n + 1})
    if sid and sid in state.get("handed_off_sessions", []):  # a late message can wake a session before its TERM
        return None, state
    if reg.get("successor") == "watcher":  # `builder run` watches this session: it ends the worker and starts the successor
        return None, state
    handoff = Path(reg["handoff"])
    if not handoff.is_absolute():
        handoff = Path(reg["worktree"]) / handoff
    if not handoff.exists():
        tell(reg, f"WORKER {name}: said {DONE} but {reg['handoff']} is missing; no successor started.", run)
        return None, state
    gen = state.get("gen", 1) + 1
    r = start_successor(name, reg, gen, run)
    if getattr(r, "returncode", 1):
        tell(reg, f"WORKER {name}: handoff refused by harness_start: {(getattr(r, 'stderr', '') or '')[-300:]}", run)
        return None, state
    tell(reg, f"WORKER {name}: handed off; generation {gen} started.", run)
    return None, {**state, "gen": gen, "handed_off_sessions": state.get("handed_off_sessions", []) + [sid]}


def main():
    event = json.load(sys.stdin)
    name = os.environ.get("FICHERO_BUILDER")
    path = HOME / f"{name}.json"
    if not name or not path.exists():
        return
    reg = json.loads(path.read_text())
    state_path = Path(str(path) + ".state")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    fn = on_stop if event.get("hook_event_name") == "Stop" else on_post_tool
    out, new = fn(event, name, reg, state)
    if new != state:
        state_path.write_text(json.dumps(new))
    if out:
        print(json.dumps(out))
    if fn is on_stop and new.get("gen") != state.get("gen"):
        pid, _ = claude_process()  # the old process would hold its memory; let the hook return first
        if pid:
            subprocess.Popen(["/bin/sh", "-c", f"sleep 60; kill -TERM {pid}"], start_new_session=True)


def test():
    d = Path(tempfile.mkdtemp())
    t = d / "t.jsonl"
    usage = {"input_tokens": 2, "cache_read_input_tokens": 170_000, "cache_creation_input_tokens": 1000}
    t.write_text(json.dumps({"message": {"usage": usage}}) + "\n")
    assert context_used(t) == 171_002 and context_used("/nope") == 0
    (d / "H.md").write_text("x")
    reg = {"worktree": str(d), "handoff": "H.md", "notify": ["tellme"]}
    out, st = on_post_tool({"transcript_path": str(t)}, "b", reg, {})
    assert out and st["told"] == ""
    assert on_post_tool({"transcript_path": str(t)}, "b", reg, st)[0] is None, "told once"
    assert on_post_tool({"transcript_path": str(t), "session_id": "n"}, "b", reg, st)[0], "a successor is told in its own right"
    usage["cache_read_input_tokens"] = 1000
    t.write_text(json.dumps({"message": {"usage": usage}}) + "\n")
    assert on_post_tool({"transcript_path": str(t)}, "b", reg, {})[0] is None, "under 85% is quiet"
    calls = []

    def run(c, **k):
        calls.append(c)
        return subprocess.CompletedProcess(c, 0, "", "")
    out, st = on_stop({"last_assistant_message": "working", "session_id": "k"}, "b", reg, {}, run)
    assert out["decision"] == "block" and st["nudges"]["k"] == 1 and not calls
    assert on_stop({"last_assistant_message": f"{WAIT} owner", "session_id": "k"}, "b", reg, st, run)[0] is None
    assert on_stop({"last_assistant_message": "x", "session_id": "k"}, "b", reg, {"nudges": {"k": NUDGES}}, run)[0] is None
    assert not calls
    assert on_stop({"last_assistant_message": "sweep green\nDONE 0123abcd", "session_id": "k"}, "b", reg, {}, run) == (None, {}), "the brief's DONE line ends the run: no nudge"
    assert on_stop({"last_assistant_message": "DONE soon", "session_id": "k"}, "b", reg, {}, run)[0]["decision"] == "block", "DONE without a sha is not an end"
    _, st = on_stop({"last_assistant_message": DONE, "session_id": "s1"}, "b", reg, {}, run)
    start = calls[0]
    assert st["gen"] == 2 and start[1].endswith("harness_start.py") and start[start.index("--name") + 1] == "b" and calls[1][0] == "tellme", calls
    n = len(calls)
    assert on_stop({"last_assistant_message": DONE, "session_id": "s1"}, "b", reg, st, run)[1] == st and len(calls) == n, "once per session"
    assert on_stop({"last_assistant_message": DONE, "session_id": "s2"}, "b", reg, st, run)[1]["gen"] == 3
    n = len(calls)
    assert on_stop({"last_assistant_message": DONE, "session_id": "w"}, "b", {**reg, "successor": "watcher"}, {}, run) == (None, {}), "the watcher's worker: no successor from the hook"
    assert len(calls) == n

    def bad(c, **k):
        return subprocess.CompletedProcess(c, 1, "", "no probe")
    _, st = on_stop({"last_assistant_message": DONE, "session_id": "s3"}, "b", reg, {}, bad)
    assert "gen" not in st, "a refused start leaves the generation alone"
    _, st = on_stop({"last_assistant_message": DONE}, "b", dict(reg, handoff="missing.md"), {}, run)
    assert "gen" not in st
    print("ok")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
