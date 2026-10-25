"""Workers: an interactive Pi in a tmux window (pipeline.workers-in-tmux, jailed-agent, key-per-lane,
tools-in-the-right-places), messages to it (`tell`), and what the runner reads back from its session JSONL
(cost, tool calls, idleness; pipeline.cost-cap, messages). The runner never holds a key: the worker wrapper
reads the key file into the one env var Pi expects."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

from pipeline import ROOT, STATE
from pipeline.config import pi_model_id

WRAPPER = ROOT / "pipeline" / "pi-agent" / "run-worker.sh"
ALLOWED_ENV = ("PATH", "HOME", "TERM", "LANG")


def sh(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


def allowed_env(cfg: dict) -> dict:
    """The coder's environment: PATH, HOME, TERM, LANG and Pi's agent dir. The key is added by the wrapper."""
    env = {k: os.environ[k] for k in ALLOWED_ENV if k in os.environ}
    agent = ROOT / cfg["workers"]["agent_dir"]
    env["PI_CODING_AGENT_DIR"] = str(agent)
    # the MCP servers are found by name on PATH (Pi's adapter does not expand ${VAR} in a command)
    env["PATH"] = f"{agent / 'bin'}:{Path.home() / '.local' / 'bin'}:{env.get('PATH', '/usr/bin:/bin')}"
    return env


def key_source(cfg: dict, worker: dict) -> tuple[str, str]:
    """(env var, key file) for the worker's provider; the lane key file wins when it exists; never read here."""
    k = cfg["keys"].get(worker["provider"], {"env": "", "files": []})
    for f in k["files"]:
        if Path(f).expanduser().exists():
            return k["env"], str(Path(f).expanduser())
    return k["env"], ""


def pi_command(cfg: dict, worker: dict, session_dir: Path, role: str = "coder") -> list[str]:
    """Interactive Pi with only the MCP adapter, the project's shared principles and the role's ponytail rules."""
    agent = ROOT / cfg["workers"]["agent_dir"]
    env_var, key_file = key_source(cfg, worker)
    cmd = [str(WRAPPER), env_var or "-", key_file or "-", "pi",
           "--no-extensions", "-e", str(Path(cfg["workers"]["pi_adapter"]).expanduser()),
           "--no-skills", "--no-prompt-templates", "--no-themes",
           "--session-dir", str(session_dir), "--model", pi_model_id(worker)]
    for f in sorted((agent / "skills" / "_shared").glob("*.md")) + [agent / "rules" / f"ponytail-{role}.md"]:
        cmd += ["--append-system-prompt", str(f)]
    return cmd


def window_env_args(env: dict) -> list[str]:
    return [a for k, v in env.items() for a in ("-e", f"{k}={v}")]


def start_window(cfg: dict, name: str, cwd: Path, cmd: list[str], env: dict) -> None:
    """One tmux session for the pipeline; one window per worker, started with ONLY the allow-listed env."""
    session = cfg["workers"]["tmux_session"]
    if sh(["tmux", "has-session", "-t", session]).returncode:
        sh(["tmux", "new-session", "-d", "-s", session, "-n", "jobs", "-c", str(ROOT)])
    sh(["tmux", "kill-window", "-t", f"{session}:{name}"])
    r = sh(["tmux", "new-window", "-d", "-t", session, "-n", name, "-c", str(cwd), *window_env_args(env),
            "env", "-i", *[f"{k}={v}" for k, v in env.items()], *cmd])
    if r.returncode:
        raise RuntimeError(f"tmux new-window: {r.stderr.strip()}")


def tell(cfg: dict, window: str, text: str) -> None:
    """Lifted from agent-work/status/briefs/tell.sh: type the text, pause, Enter. One line; long text is a brief file."""
    target = f"{cfg['workers']['tmux_session']}:{window}"
    with open(STATE / f"window-{window}.lock", "a"):  # ponytail: the lock file exists; serialising typists is Stage 1
        sh(["tmux", "send-keys", "-t", target, "-l", text])
        time.sleep(1)
        sh(["tmux", "send-keys", "-t", target, "Enter"])


def brief_file(task: str, name: str, text: str) -> Path:
    p = STATE / "briefs" / task / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


# --- reading the session log ---------------------------------------------------------------------------------

def session_files(session_dir: Path) -> list[Path]:
    return sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if session_dir.exists() else []


def parse_session(path: Path) -> dict:
    """cost_usd, tokens, tool_calls (Counter by name), idle, last_text, rate_limited, model — from a Pi JSONL,
    or a Claude Code JSONL (no price; usage limit => rate_limited)."""
    out = {"cost_usd": 0.0, "tokens": 0, "tool_calls": Counter(), "idle": True, "last_text": "", "rate_limited": False,
           "model": "", "turns": 0}
    for line in path.read_text().splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message") if isinstance(o.get("message"), dict) else None
        if not m or not isinstance(m.get("content"), (list, str)):
            continue
        role = m.get("role") or o.get("type")
        content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        if role == "assistant":
            out["turns"] += 1
            u = m.get("usage") or {}
            out["cost_usd"] += ((u.get("cost") or {}).get("total") or 0.0)
            out["tokens"] += u.get("totalTokens") or sum(u.get(k, 0) for k in ("input_tokens", "output_tokens"))
            out["model"] = m.get("model") or out["model"]
            stop = m.get("stopReason") or m.get("stop_reason") or ""
            out["idle"] = stop in ("stop", "end_turn", "endTurn", "stop_sequence") and not any(
                c.get("type") in ("toolCall", "tool_use") for c in content)
            for c in content:
                if c.get("type") in ("toolCall", "tool_use"):
                    out["tool_calls"][c.get("name", "?")] += 1
                elif c.get("type") == "text" and c.get("text"):
                    out["last_text"] = c["text"]
                    if re.search(r"usage limit|rate limit|out of credits|insufficient", c["text"], re.I):
                        out["rate_limited"] = True
        elif role == "user":
            out["idle"] = False  # a prompt is in, the answer is not
    return out


def status(session_dir: Path) -> dict:
    files = session_files(session_dir)
    if not files:
        return {"cost_usd": 0.0, "tokens": 0, "tool_calls": Counter(), "idle": False, "last_text": "", "rate_limited": False,
                "model": "", "turns": 0, "started": False}
    s = parse_session(files[-1])
    s["started"] = True
    return s


def wait_idle(session_dir: Path, cap_usd: float, poll: float = 10.0, timeout_s: float = 3600, note=None) -> dict:
    """Block until the worker's last turn ended with no tool pending, the cost cap is hit, or the time is up."""
    t0 = time.time()
    while True:
        s = status(session_dir)
        if s["started"] and s["cost_usd"] > cap_usd:
            s["stopped"] = f"cost cap: ${s['cost_usd']:.2f} > ${cap_usd:.2f}"
            return s
        if s["started"] and s["idle"] or s["rate_limited"]:
            return s
        if time.time() - t0 > timeout_s:
            s["stopped"] = f"no idle turn in {int(timeout_s)} s"
            return s
        if note:
            note(s)
        time.sleep(poll)


def uses_tools(s: dict, *prefixes: str) -> dict:
    return {p: sum(n for name, n in s["tool_calls"].items() if p in name) for p in prefixes}
