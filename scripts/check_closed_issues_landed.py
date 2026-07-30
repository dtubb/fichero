#!/usr/bin/env python3
"""Fail if an issue closed recently cites a commit that is not on origin/integration.

Catches the case the pre-close ancestor check cannot: closing against a commit
that is real and in the lane's local tree, but has not been pushed. That window
opens every time a merge lands and stays open until the push.

Usage:  check_closed_issues_landed.py [--hours 24] [--remote origin/integration]
Exit 0 = every recently-closed issue is backed by a pushed commit.
Exit 1 = at least one is not.

-----------------------------------------------------------------------------
DO NOT "OPTIMISE" THE CORPUS ONTO THE REMOTE. Read this before editing.
-----------------------------------------------------------------------------
The two halves of this check are deliberately asymmetric:

    corpus  = `git log --all`     (EVERY ref: local branches, lanes, tags)
    test    = merge-base against  origin/integration   (the REMOTE only)

That asymmetry IS the check. The defect being hunted is "a commit exists
locally but not on the remote", so the corpus must be able to see commits the
remote does not have.

Narrowing the corpus to `git log origin/integration` looks like a harmless
speedup and silently destroys the check: every commit it can see is an
ancestor of the remote by construction, so `is_ancestor` is always True, no
issue is ever flagged, and the script prints OK forever. It would then be a
guardrail that CANNOT FAIL — the exact #4382 failure mode this tool exists to
prevent, reappearing inside the tool itself.

If you change either half, add a fixture that proves the check still FIRES:
create a local commit citing a closed issue, do not push it, and assert this
script exits 1. A guardrail with no proof it can fail is decoration.

Two related invariants, for the same reason:
  * Unresolvable --remote exits 1 (see main). It must never "pass" by having
    nothing to compare against.
  * An issue with NO citing commit is SKIPPED, not failed. Duplicates, audits,
    already-implemented triage closures, and work that lands as data rather
    than code (e.g. a default_workflows/*.json preset) legitimately cite
    nothing. Failing those produces noise, and a noisy check gets disabled.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from datetime import datetime, timedelta, timezone

ISSUE_REF = re.compile(r"#(\d+)")


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def closed_since(hours: int) -> dict[int, str]:
    """Issue number -> closedAt, for issues closed within the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    raw = sh("gh", "issue", "list", "--state", "closed", "--limit", "400",
             "--json", "number,closedAt,title")
    out = {}
    for row in json.loads(raw or "[]"):
        if not row.get("closedAt"):
            continue
        if datetime.fromisoformat(row["closedAt"].replace("Z", "+00:00")) >= cutoff:
            out[row["number"]] = row["title"]
    return out


def commits_by_issue(since_days: int = 90) -> dict[int, list[str]]:
    """Map issue number -> SHAs of commits mentioning it, across ALL refs.

    --all matters: the whole point is to find commits that exist locally on a
    branch or an unmerged lane but not on the remote.
    """
    log = sh("git", "log", "--all", f"--since={since_days}.days", "--format=%H%x00%s%x00%b%x01")
    index: dict[int, list[str]] = {}
    for entry in log.split("\x01"):
        if not entry.strip():
            continue
        sha, _, rest = entry.strip().partition("\x00")
        for num in {int(n) for n in ISSUE_REF.findall(rest)}:
            index.setdefault(num, []).append(sha)
    return index


def is_ancestor(sha: str, ref: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                          capture_output=True).returncode == 0


def classify(issue_commits: list[str], reachable: set[str]) -> str:
    """Pure decision: "ok" | "skip" | "unlanded" for one issue's commits.

    Split out from main so the check can be proven to FIRE in a unit test
    without standing up a real remote. Per the module docstring, a guardrail
    with no proof it can fail is decoration.
    """
    if not issue_commits:
        return "skip"          # audits, duplicates, data-only landings
    if any(c in reachable for c in issue_commits):
        return "ok"            # at least one citing commit is pushed
    return "unlanded"          # every citing commit is local-only


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--remote", default="origin/integration")
    args = ap.parse_args()

    if not sh("git", "rev-parse", "--verify", args.remote).strip():
        print(f"FAIL: {args.remote} does not resolve. Run `git fetch` first.", file=sys.stderr)
        return 1

    closed = closed_since(args.hours)
    if not closed:
        print(f"OK: no issues closed in the last {args.hours}h.")
        return 0

    index = commits_by_issue()
    offenders = []
    for num, title in sorted(closed.items()):
        shas = index.get(num, [])
        if not shas:
            continue  # no citing commit: docs/audit/dupe closure, not this check's business
        reachable = {s for s in shas if is_ancestor(s, args.remote)}
        if classify(shas, reachable) == "unlanded":
            offenders.append((num, title, shas[:3]))

    print(f"Checked {len(closed)} issue(s) closed in the last {args.hours}h against {args.remote}.")
    if not offenders:
        print("OK: every closed issue with a citing commit is backed by a pushed commit.")
        return 0

    print(f"\nFAIL: {len(offenders)} closed issue(s) cite only UNPUSHED commits.\n")
    for num, title, shas in offenders:
        print(f"  #{num}  {title}")
        for s in shas:
            print(f"      {s[:9]}  not an ancestor of {args.remote}")
    print("\nThe fix is normally a push, not a state change. Verify, then push.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
