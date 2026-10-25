#!/usr/bin/env python3
"""Close the issues that commits on origin/integration say they fix.

GitHub closes `Fixes #N` only when the commit reaches the default branch (main); our work lands
on `integration`, so without this the issue list only grows (maintainer, 2026-10-04). Run it
after each push to integration:

    scripts/close_fixed_issues.py                       # dry run over the last 14 days: says what it would close
    scripts/close_fixed_issues.py --range A..B --apply  # the pushed range only (the Action passes before..sha)

Only a `Fixes #N` / `Closes #N` / `Resolves #N` that starts a line of the message counts (a subject or a
trailer), never prose such as "revert the fix #5222". An issue labelled `residue` is never closed here: part of
it is still owed, and that part gets its own narrower issue. Nor is one labelled `needs-your-test`: it closes
when the maintainer has checked it on screen. An issue a human REOPENED after the fixing commit stays open: the
fix did not hold. Only commits already on the remote count, so an issue is never closed against work that has
not been pushed (`check_closed_issues_landed.py` checks the same promise).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

# A closing keyword at the start of a line or of a sentence ("Fixes #12. Closes #34, resolves #56."), never inside
# prose ("revert the fix #5222").
FIXES = re.compile(r"(?:^|[.;,]\s+)\s*(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s+#(\d+)", re.IGNORECASE | re.MULTILINE)


def cited(message: str) -> set[int]:
    """The issue numbers a commit message says it fixes: a Fixes/Closes/Resolves clause, not prose."""
    return {int(n) for n in FIXES.findall(message)}


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def fixing_commits(*log_args: str) -> dict[int, tuple[str, str, str]]:
    """Issue number -> (sha, subject, committer date ISO) of the newest commit in `git log <log_args>` that fixes it."""
    out = _run("git", "log", *log_args, "--format=%H%x1f%s%x1f%cI%x1f%B%x1e")
    found: dict[int, tuple[str, str, str]] = {}
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        sha, subject, date, body = record.strip().split("\x1f", 3)
        for number in cited(body):
            found.setdefault(number, (sha, subject, date))
    return found


def reopened_after(number: int, date: str) -> bool:
    """True when a human reopened the issue after the fixing commit: the fix did not hold, leave it open."""
    events = json.loads(_run("gh", "api", f"repos/{{owner}}/{{repo}}/issues/{number}/events?per_page=100"))
    return any(e.get("event") == "reopened" and e.get("created_at", "") > date for e in events)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remote", default="origin/integration")
    parser.add_argument("--since", default="14 days ago")
    parser.add_argument("--range", help="A..B: only these commits (the Action passes the pushed range)")
    parser.add_argument("--apply", action="store_true", help="close the issues (default: dry run)")
    args = parser.parse_args()

    _run("git", "fetch", "-q", args.remote.split("/", 1)[0])
    found = fixing_commits(args.range) if args.range else fixing_commits(args.remote, f"--since={args.since}")
    closed = 0
    for number, (sha, subject, date) in sorted(found.items()):
        issue = json.loads(_run("gh", "issue", "view", str(number), "--json", "state,labels"))
        labels = {label["name"] for label in issue["labels"]}
        if issue["state"] != "OPEN":
            continue
        if "residue" in labels or "needs-your-test" in labels:
            print(f"#{number}: open, labelled {'residue' if 'residue' in labels else 'needs-your-test'} -- left open")
            continue
        if reopened_after(number, date):
            print(f"#{number}: reopened after {sha[:9]} -- left open (the fix did not hold)")
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
