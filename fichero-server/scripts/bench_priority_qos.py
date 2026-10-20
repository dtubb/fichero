#!/usr/bin/env python3
"""Kraken s/page at each compute priority: fast, balanced, background (#5358, the owner question on #5819).

  <engine-venv>/bin/python fichero-server/scripts/bench_priority_qos.py --model /path/to/reader.safetensors \
      --images <public dev pages, e.g. reader-seed/src> [--pages 5]

Each priority runs `bench_reading.py` in its OWN process (QoS and thread pools are fixed per process/thread) with
`FICHERO_COMPUTE_PRIORITY` set and a scratch `FICHERO_BASE_PATH`, so nothing of the person's is touched. Prints the
QoS class and threads each used (`core/compute_preferences.apply_to_this_thread` is the mechanism) and s/page each way,
and the slowdown against fast. Without --images it draws pages (a proxy). Run on the M4 on AC, nothing else running;
background is slow by design, so keep --pages small. Exit 0 always: it measures, it does not judge.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).with_name("bench_reading.py")
PER_PAGE = re.compile(r"([\d.]+) s a page \(wall\)")
# bench_reading prints: priority   {'fast/user-initiated/threads=8/person=yes/run': 5}
USED = re.compile(r"\'([\w-]+)/([\w-]+)/threads=(\d+)")  # each key of the priority dict


def measure(priority: str, model: str, pages: int, images: str | None, automatic: bool = False) -> tuple[float | None, str]:
    scratch = tempfile.mkdtemp(prefix="bench-qos-")
    env = {**os.environ, "FICHERO_BASE_PATH": scratch}
    if not automatic:  # the automatic row is the throttle's own choice (Mac in use), not an override
        env["FICHERO_COMPUTE_PRIORITY"] = priority
    cmd = [sys.executable, str(BENCH), "--model", model, "--pages", str(pages)] + (["--images", images] if images else []) + (["--automatic"] if automatic else [])
    try:
        run = subprocess.run(cmd, env=env, capture_output=True, text=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    seconds = PER_PAGE.search(run.stdout)
    line = next((l for l in run.stdout.splitlines() if l.startswith("priority")), "")
    kinds = USED.findall(line)  # every key, not the first: pages of one run may differ
    used = kinds[0] if kinds else None
    if not seconds or not kinds:
        tail = " | ".join((run.stderr or run.stdout).strip().splitlines()[-3:])
        return None, f"FAILED (exit {run.returncode}): {tail or 'no output'}"
    note = f"{used[1]}, {used[2]} threads"
    wrong = sorted({k[0] for k in kinds} - {priority})
    if wrong or len(set(kinds)) > 1:  # the override did not take, or pages ran at mixed classes
        note += f"  !! ASKED {priority} BUT PAGES RAN AT {sorted(set(kinds))}"
    return float(seconds[1]), note


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--images")
    ap.add_argument("--pages", type=int, default=5)
    args = ap.parse_args()
    results = {p: measure(p, args.model, args.pages, args.images) for p in ("fast", "balanced", "background")}
    # An import's own run while the Mac is used: the throttle gives it background; Kraken lifts it to utility (2026-10-20).
    results["automatic"] = measure("background", args.model, args.pages, args.images, automatic=True)
    base = results["fast"][0]
    print(f"{'priority':<12}{'s/page':>8}{'x fast':>8}  qos, threads")
    for priority, (seconds, used) in results.items():
        times = f"{seconds / base:.1f}x" if seconds and base else "?"
        print(f"{priority:<12}{(f'{seconds:.1f}' if seconds else '?'):>8}{times:>8}  {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
