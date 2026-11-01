"""`python -m fichero_builder run --worktree W --brief FILE ...` starts and watches a worker (run AS the worker user);
`python -m fichero_builder check REPO SINCE HEAD --pinned DIR [--id ID ...]` runs the project's ladder and prints typed JSON."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import json

from fichero_builder import check_tool, journal
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
    r.add_argument("--state", help="where the journal lives (default $FICHERO_BUILDER_STATE or the XDG state home); a shared dir lets the owner read it without sudo")
    c = sub.add_parser("check", help="run the ladder over SINCE..HEAD from the pinned copy; exit 1 if red")
    c.add_argument("repo"), c.add_argument("since"), c.add_argument("head")
    c.add_argument("--pinned", required=True)
    c.add_argument("--id", action="append", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "check":
        r = check_tool.run_ladder(a.repo, a.since, a.head, a.pinned, a.id)
        print(json.dumps(r, indent=1))
        return 0 if r.get("ok") else 1
    if a.state:
        journal.STATE = Path(a.state)
    procs = run_mod.real_procs(Path.home(), a.worktree)
    end = run_mod.run(a.root, a.worktree, a.brief, name=a.name, model=a.model, kind=a.kind, tmux_session=a.session,
                      tick_s=a.tick, procs=procs, handoff=a.handoff)
    return 0 if end in ("gone", "parked") else 1


if __name__ == "__main__":
    sys.exit(main())
