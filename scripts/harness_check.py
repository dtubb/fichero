#!/usr/bin/env python3
"""check: run the project's ladder over since..head from the PINNED copy; print typed JSON, exit 1 if red (#6116 tool.check).

Usage: scripts/harness_check.py <repo> <since> <head> --pinned DIR [--id BEHAVIOUR_ID ...]
A rules file with problems (no [jail], an undeclared rung, empty deny_read) refuses."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-builder"))
from fichero_builder import check_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("repo"), ap.add_argument("since"), ap.add_argument("head")
ap.add_argument("--pinned", required=True)
ap.add_argument("--id", action="append", default=[])
a = ap.parse_args()
r = check_tool.run_ladder(a.repo, a.since, a.head, a.pinned, a.id)
print(json.dumps(r, indent=1))
sys.exit(0 if r.get("ok") else 1)
