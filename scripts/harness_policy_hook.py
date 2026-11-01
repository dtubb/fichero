#!/usr/bin/env python3
"""Claude Code PreToolUse hook (and `--commit-msg FILE` git hook) enforcing harness.toml [policy] (#6116).

stdin = the hook's JSON event; exit 2 + the reason on stderr refuses the tool call. Each refusal is appended as a
JSON line to $FICHERO_HARNESS_LOG when set (the row source until the engine takes them)."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fichero-builder"))
from fichero_builder import policy_hook as ph  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--worktree", default=os.getcwd())
ap.add_argument("--scratch", default=os.environ.get("TMPDIR", "/tmp"))
ap.add_argument("--root", default=str(ROOT))
ap.add_argument("--commit-msg")
a = ap.parse_args()
cfg = ph.load(a.root)
if a.commit_msg:
    problems = ph.commit_msg_problems(Path(a.commit_msg).read_text(), cfg)
    reasons = problems
else:
    event = json.load(sys.stdin)
    r = ph.check(event, cfg, worktree=Path(a.worktree), scratch=Path(a.scratch))
    reasons = [r] if r else []
if reasons:
    if os.environ.get("FICHERO_HARNESS_LOG"):
        with open(os.environ["FICHERO_HARNESS_LOG"], "a") as f:
            f.write(json.dumps({"at": time.time(), "refused": reasons}) + "\n")
    print("\n".join(reasons), file=sys.stderr)
    sys.exit(2 if not a.commit_msg else 1)
