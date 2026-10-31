#!/usr/bin/env python3
"""land gate, no push (#6116 Step 0.1): refuse unless every commit of base..head has a READY verdict for its exact
patch-id and message, then run the ladder from the pinned copy. The Lead pushes; this prints the fast-forward.

Usage: scripts/harness_land.py <repo> <base> <head> --pinned DIR --verdicts FILE   (repo = the engine-owned fetch)"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-server" / "src"))
from fichero_server.workflows import check_tool, land_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("repo"), ap.add_argument("base"), ap.add_argument("head")
ap.add_argument("--pinned", required=True), ap.add_argument("--verdicts", required=True)
a = ap.parse_args()
if stop := land_tool.unreviewed(a.repo, a.base, a.head, a.verdicts):
    sys.exit("REFUSED:\n  " + "\n  ".join(stop))
r = check_tool.run_ladder(a.repo, a.base, a.head, a.pinned)
print(json.dumps({k: r[k] for k in ("ok", "failed") if k in r}))
if not r["ok"]:
    sys.exit(1)
print(f"READY TO LAND: git push origin {a.head}:refs/heads/integration   (the Lead runs this)")
