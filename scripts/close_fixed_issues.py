#!/usr/bin/env python3
"""Close the issues that commits on origin/integration say they fix.

GitHub closes `Fixes #N` only when the commit reaches the default branch (main); our work lands
on `integration`, so without this the issue list only grows (maintainer, 2026-10-04). Run it
after each push to integration:

    scripts/close_fixed_issues.py            # dry run: says what it would close
    scripts/close_fixed_issues.py --apply    # closes them, each with a comment naming the commit

An issue labelled `residue` is never closed here: part of it is still owed, and that part gets
its own narrower issue. Only commits already on the remote count, so an issue is never closed
against work that has not been pushed (`check_closed_issues_landed.py` checks the same promise).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

FIXES = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)


def cited(message: str) -> set[int]:
    """The issue numbers a commit message says it fixes."""
    return {int(n) for n in FIXES.findall(message)}


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def fixing_commits(remote: str, since: str) -> dict[int, tuple[str, str]]:
    """Issue number -> (sha, subject) of the newest commit on `remote` that fixes it."""
    out = _run("git", "log", remote, f"--since={since}", "--format=%H%x1f%s%x1f%B%x1e")
    found: dict[int, tuple[str, str]] = {}
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        sha, subject, body = record.strip().split("\x1f", 2)
        for number in cited(body):
            found.setdefault(number, (sha, subject))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remote", default="origin/integration")
    parser.add_argument("--since", default="14 days ago")
    parser.add_argument("--apply", action="store_true", help="close the issues (default: dry run)")
    args = parser.parse_args()

    _run("git", "fetch", "-q", args.remote.split("/", 1)[0])
    closed = 0
    for number, (sha, subject) in sorted(fixing_commits(args.remote, args.since).items()):
        issue = json.loads(_run("gh", "issue", "view", str(number), "--json", "state,labels"))
        labels = {label["name"] for label in issue["labels"]}
        if issue["state"] != "OPEN":
            continue
        if "residue" in labels:
            print(f"#{number}: open, labelled residue -- left open")
            continue
        print(f"#{number}: {'closing' if args.apply else 'would close'} (fixed in {sha[:9]}: {subject})")
        if args.apply:
            _run("gh", "issue", "close", str(number), "--comment",
                 f"Fixed in {sha[:9]} on integration: {subject}")
            closed += 1
    print(f"{closed} closed." if args.apply else "Dry run; pass --apply to close.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
