"""`python -m fichero_builder run --worktree W --brief FILE [--name N] [--model M] [--root R]` (run AS the worker user)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fichero_builder import run as run_mod


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="builder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="start a worker through the start path and watch its session file")
    r.add_argument("--worktree", required=True)
    r.add_argument("--brief", required=True, help="file holding the brief text")
    r.add_argument("--root", default=str(Path.cwd()))
    r.add_argument("--name", default=f"worker-{int(time.time())}")
    r.add_argument("--model", default="sonnet")
    r.add_argument("--kind", default="claude", choices=["claude"])
    r.add_argument("--session", default="harness")
    r.add_argument("--tick", type=float, default=30.0)
    r.add_argument("--handoff", help="the handoff file a successor reads (default <worktree>/HANDOFF.md)")
    a = ap.parse_args(argv)
    procs = run_mod.real_procs(Path.home(), a.worktree)
    end = run_mod.run(a.root, a.worktree, a.brief, name=a.name, model=a.model, kind=a.kind, tmux_session=a.session,
                      tick_s=a.tick, procs=procs, handoff=a.handoff)
    return 0 if end in ("gone", "parked") else 1


if __name__ == "__main__":
    sys.exit(main())
