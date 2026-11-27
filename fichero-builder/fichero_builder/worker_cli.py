"""The jailed worker's own copy of Claude Code, kept at the manager's version and signed in (local.run.worker-cli-current).

2026-11-27: /Users/Shared/fichero-worker/bin/claude was a copy made on Oct 31 (2.1.316). It refused `claude-fable-5-2[1m]`
(unrecognized_model), and every Fable session died at once: 'gone' three times on perf-optimize. Then the worker's sign-in was
revoked ("Failed to authenticate: OAuth token revoked"), for every model."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from fichero_builder import journal

CACHE = "worker-cli.json"  # {"models": {version: {model: "" | why refused}}, "auth_alerted": bool, "ends_alerted": "<X>"}
HELD = [False]  # the worker's sign-in is revoked: no new worker session starts until a probe passes
AUTH = re.compile(r"Failed to authenticate|OAuth token revoked", re.I)
ENDS = re.compile(r"sign-in ends between (.+?) and (.+?)(?:[.)\n]|$)", re.I)
WARN_DAYS = 2


def version(binary) -> str:
    try:
        r = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (r.stdout.split() or [""])[0] if r.returncode == 0 else ""


def sync(worker: Path, manager: str) -> str:
    """Copy the manager's resolved binary over the worker's when the versions differ (to .new, then mv: never half a file).
    Returns the worker's version afterwards; one `worker-cli` row when it was replaced or could not be."""
    have, want = version(worker), version(manager)
    if not want or have == want:
        return have
    src = os.path.realpath(manager)
    new = worker.with_name(worker.name + ".new")
    try:
        shutil.copy2(src, new)
        new.chmod(0o755)
        os.replace(new, worker)
    except OSError as e:
        journal.append("worker-cli", state="failed", detail=f"{worker} is {have or '?'}, the manager's {want}: copy failed: {e}")
        return have
    journal.append("worker-cli", state="updated", detail=f"{worker}: {have or '?'} -> {want} (from {src})")
    return want


def probe(worker: Path, model: str, as_user=()) -> tuple[str, str]:
    """("ok" | "auth" | "refused" | "unknown", the CLI's text), `claude -p --model <model>` run as the worker (`as_user` is the sudo prefix)."""
    try:
        r = subprocess.run([*as_user, str(worker), "-p", "--model", model, "--max-turns", "1", "Reply ok."], capture_output=True,
                           text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return "unknown", str(e)
    text = (r.stdout + r.stderr).strip()
    if AUTH.search(text):
        return "auth", text
    if r.returncode:
        return ("refused" if "model" in text.lower() else "unknown"), text
    return "ok", text


def ends_at(text: str) -> dt.date | None:
    """X of "this sign-in ends between X and Y", or None."""
    if not (m := ENDS.search(text)):
        return None
    raw = m.group(1).strip().rstrip(",")
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def auth_text(text: str) -> bool:
    return bool(AUTH.search(text or ""))


def check(worker: Path, manager: str, wanted, alert, as_user=(), today: dt.date | None = None, user: str = "fichero-worker") -> None:
    """sync; one uncached probe for the sign-in (HELD while revoked, one alert); each wanted model probed once per (version, model);
    a refusal is one alert naming it; a "sign-in ends between X and Y" warning is one alert WARN_DAYS before X."""
    ver = sync(worker, manager)
    f = journal.STATE / CACHE
    try:
        cache = json.loads(f.read_text())
    except (OSError, ValueError):
        cache = {}
    login = f"sudo -u {user} -H {worker} auth login"
    wanted = sorted(set(wanted))
    if wanted:
        kind, text = probe(worker, wanted[0], as_user)
        if kind == "auth":
            HELD[0] = True
            if not cache.get("auth_alerted"):
                cache["auth_alerted"] = True
                alert("", ver, f"the worker's Claude sign-in is revoked: run `{login}`; no new worker session starts until it passes", text[-300:])
        elif kind == "ok":
            HELD[0], cache["auth_alerted"] = False, False
        if (x := ends_at(text)) and (today or dt.date.today()) >= x - dt.timedelta(days=WARN_DAYS) and cache.get("ends_alerted") != str(x):
            cache["ends_alerted"] = str(x)
            alert("", ver, f"the worker's Claude sign-in ends from {x}: run `{login}` before then", text[-300:])
        if ver and not HELD[0]:
            seen = cache.setdefault("models", {}).setdefault(ver, {})
            if kind in ("ok", "refused"):
                seen[wanted[0]] = text[-300:] if kind == "refused" else ""
            for m in [m for m in wanted if m not in seen]:
                k, t = probe(worker, m, as_user)
                if k in ("ok", "refused"):
                    seen[m] = t[-300:] if k == "refused" else ""
            for m in wanted:
                if seen.get(m) and m not in cache.setdefault("refused_alerted", {}).get(ver, []):
                    cache["refused_alerted"].setdefault(ver, []).append(m)
                    alert(m, ver, f"the worker's Claude Code {ver} refuses model {m!r}: a lane on it would end 'gone' at once", seen[m])
            cache["models"] = {ver: seen}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cache, indent=1))
