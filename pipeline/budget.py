"""Machine budget, Stage 0 (pipeline.machine-budget): free memory before a job, one test run at a time (the Lock in
journal.py), a spawn cap, backoff with jitter. ponytail: swap, load, RPM caps and the owner's engine come in Stage 1."""
from __future__ import annotations

import os
import random
import re
import subprocess

PAGE = 16384 if os.uname().machine == "arm64" else 4096


def _out(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def machine() -> dict:
    """free_mb from memory_pressure's system-wide free percentage (vm_stat's "free" pages are tiny on macOS, which
    keeps RAM as file cache: 87 MB "free" on a healthy 16 GB machine); vm_stat is the fallback."""
    mp = _out(["memory_pressure"]).lower()
    pct = re.search(r"free percentage:\s*(\d+)%", mp)
    total = int((_out(["sysctl", "-n", "hw.memsize"]) or "0").strip() or 0) // 2**20
    if pct and total:
        free = total * int(pct.group(1)) // 100
    else:
        vm = _out(["vm_stat"])
        free = sum(int(m) for m in re.findall(r"Pages (?:free|speculative|purgeable):\s+(\d+)", vm)) * PAGE // 2**20
    # kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical (memory_pressure's text never says "warn")
    level = (_out(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]) or "").strip()
    pressure = {"1": "normal", "2": "warn", "4": "critical"}.get(level, "?")
    return {"free_mb": free, "pressure": pressure, "load1": round(os.getloadavg()[0], 2)}


def room_for(kind: str, needs_mb: dict, m: dict | None = None) -> tuple[bool, str]:
    """(ok, reason): the job kind's declared need must fit in free RAM and pressure must not be critical."""
    m = m or machine()
    need = needs_mb.get(kind, 0)
    if m["pressure"] == "critical":
        return False, f"memory pressure critical ({m['free_mb']} MB free)"
    if m["free_mb"] < need:
        return False, f"{kind} needs {need} MB, {m['free_mb']} MB free"
    return True, f"{kind}: {m['free_mb']} MB free"


def backoff(attempt: int, base: float = 2.0, cap: float = 120.0, rng=random.random) -> float:
    """Seconds before retry `attempt` (0-based): exponential with full jitter, never a hot loop."""
    return min(cap, base * 2**attempt) * (0.5 + 0.5 * rng())


class Spawns:
    """What the runner has spawned per kind, de-duplicated by key and capped (the lesson of Bernstein's stray tasks)."""

    def __init__(self, caps: dict):
        self.caps, self.live = caps, {}

    def can(self, kind: str, key: str) -> tuple[bool, str]:
        live = self.live.setdefault(kind, set())
        if key in live:
            return False, f"{kind} {key} already running"
        if len(live) >= self.caps.get(kind, 1):
            return False, f"{kind} cap {self.caps.get(kind, 1)} reached"
        return True, "ok"

    def add(self, kind: str, key: str) -> None:
        ok, why = self.can(kind, key)
        if not ok:
            raise RuntimeError(why)
        self.live[kind].add(key)

    def remove(self, kind: str, key: str) -> None:
        self.live.get(kind, set()).discard(key)
