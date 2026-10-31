#!/usr/bin/env python3
"""Print a worker's brief for an issue: body + trusted comments + where the code is (#6116).

Usage: scripts/harness_brief.py <issue-number> [--repo-dir DIR]   (reads the issue with `gh`)"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-server" / "src"))
from fichero_server.workflows import brief_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("number", type=int)
ap.add_argument("--repo-dir", default=".")
a = ap.parse_args()
print(brief_tool.build(brief_tool.fetch_issue(a.number), repo=a.repo_dir))
