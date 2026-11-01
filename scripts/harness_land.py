#!/usr/bin/env python3
"""land gate, no push (#6116 Step 0.1): refuse unless the range <land branch>..<head> has a READY verdict for its exact
commits (ordered diff bytes + messages, with the base sha), then run the ladder from the pinned copy. The Lead pushes; this prints the push.

Usage: scripts/harness_land.py <repo> <head> --pinned DIR --verdicts FILE --log FILE
  repo = the engine-owned repository; the base is [land].branch of the pinned harness.toml, resolved in repo (never named
  by the caller) and must be an ancestor of head. --verdicts and --log are owner-owned files outside the workroot, opened
  without following symlinks. Fetching worker commits into repo is done beforehand from the worker's bundle with `git fetch --no-tags` (a tag named like the branch would ride along: review 5 N1)."""
import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-builder"))
from fichero_builder import check_tool, land_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("repo"), ap.add_argument("head")
ap.add_argument("--pinned", required=True), ap.add_argument("--verdicts", required=True), ap.add_argument("--log", required=True)
a = ap.parse_args()


def row(**kw):
    land_tool.safe_append(a.log, json.dumps({"at": time.time(), "land": a.head, **kw}) + "\n")


if problems := check_tool.rules_problems(a.pinned):
    row(refused="rules", detail=problems)
    sys.exit("REFUSED (rules file):\n  " + "\n  ".join(problems))
land_cfg = tomllib.loads((Path(a.pinned) / "harness.toml").read_text())["land"]
branch = land_cfg["branch"]
try:  # review 5 N1 + push line: both ends become shas once, here; a moved ref or a same-named tag changes nothing after
    base = land_tool.resolve_branch(a.repo, branch)
    a.head = land_tool._git(a.repo, "rev-parse", "--verify", f"{a.head}^{{commit}}").strip()
except RuntimeError as e:
    sys.exit(f"REFUSED: {e}")
if stop := land_tool.unreviewed(a.repo, branch, a.head, a.verdicts):
    row(refused="verdict", detail=stop)
    sys.exit("REFUSED:\n  " + "\n  ".join(stop))
if hits := land_tool.boundary(a.repo, base, a.head, land_cfg["boundary"]):
    row(refused="boundary", detail=hits)
    sys.exit("REFUSED (boundary):\n  " + "\n  ".join(hits))
r = check_tool.run_ladder(a.repo, base, a.head, a.pinned)
print(json.dumps({k: r[k] for k in ("ok", "failed") if k in r}))
row(ladder_ok=r.get("ok"), failed=r.get("failed", ""))
if not r["ok"]:
    sys.exit(1)
print(f"READY TO LAND: git push origin {a.head}:refs/heads/{branch}   (the Lead runs this)")
