#!/usr/bin/env python3
"""land gate, no push (#6116 Step 0.1): refuse unless every commit of base..head has a READY verdict for its exact
patch-id and message, then run the ladder from the pinned copy. The Lead pushes; this prints the fast-forward.

Usage: scripts/harness_land.py <repo> <base> <head> --pinned DIR --verdicts FILE [--fetch SRC]
  repo = the engine-owned repository; --fetch SRC first fetches <head> (a sha) from the worker's clone SRC into it.
Order: fetch, verdict per commit (patch-id + message), boundary grep ([land].boundary), the ladder from the pinned copy."""
import argparse
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-server" / "src"))
from fichero_server.workflows import check_tool, land_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("repo"), ap.add_argument("base"), ap.add_argument("head")
ap.add_argument("--pinned", required=True), ap.add_argument("--verdicts", required=True)
ap.add_argument("--fetch")
a = ap.parse_args()


def row(**kw):
    if os.environ.get("FICHERO_HARNESS_LOG"):
        with open(os.environ["FICHERO_HARNESS_LOG"], "a") as f:
            f.write(json.dumps({"at": time.time(), "land": a.head, **kw}) + "\n")


if a.fetch:  # a plain fetch of one sha: no hooks, no filters, into a repo the worker cannot write
    f = subprocess.run([land_tool.GIT, "-C", a.repo, "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags", a.fetch, a.head],
                       capture_output=True, text=True)
    if f.returncode:
        row(refused="fetch")
        sys.exit("REFUSED: fetch failed: " + f.stderr.strip()[:300])
if stop := land_tool.unreviewed(a.repo, a.base, a.head, a.verdicts):
    row(refused="verdict", detail=stop)
    sys.exit("REFUSED:\n  " + "\n  ".join(stop))
patterns = tomllib.loads((Path(a.pinned) / "harness.toml").read_text()).get("land", {}).get("boundary", [])
if hits := land_tool.boundary(a.repo, a.base, a.head, patterns):
    row(refused="boundary", detail=hits)
    sys.exit("REFUSED (boundary):\n  " + "\n  ".join(hits))
r = check_tool.run_ladder(a.repo, a.base, a.head, a.pinned)
print(json.dumps({k: r[k] for k in ("ok", "failed") if k in r}))
row(ladder_ok=r.get("ok"), failed=r.get("failed", ""))
if not r["ok"]:
    sys.exit(1)
print(f"READY TO LAND: git push origin {a.head}:refs/heads/integration   (the Lead runs this)")
