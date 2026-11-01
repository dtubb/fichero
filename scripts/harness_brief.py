#!/usr/bin/env python3
"""Print a worker's brief: for each issue its body + trusted comments + where the code is (#6116).

One issue prints build(); several print a cluster brief (preamble + harness.toml [brief].rules + every issue).
Usage: scripts/harness_brief.py N [N ...] [--repo-dir DIR] [--branch B --base SHA]   (reads the issues with `gh`)"""
import argparse
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fichero-server" / "src"))
from fichero_server.workflows import brief_tool  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("numbers", type=int, nargs="+")
ap.add_argument("--repo-dir", default=".")
ap.add_argument("--branch")
ap.add_argument("--base")
a = ap.parse_args()
issues = [brief_tool.fetch_issue(n) for n in a.numbers]
if a.branch or a.base or len(issues) > 1:
    if not (a.branch and a.base):
        sys.exit("a cluster brief needs --branch and --base")
    rules = tomllib.loads((Path(a.repo_dir) / "harness.toml").read_text()).get("brief", {}).get("rules", "")
    print(brief_tool.cluster(issues, repo=a.repo_dir, branch=a.branch, base=a.base, rules=rules))
else:
    print(brief_tool.build(issues[0], repo=a.repo_dir))
