#!/usr/bin/env python3
"""What is waiting on the maintainer, and what changed: the answer to "what's the update?".

Deterministic: everything comes from GitHub labels and dates, nothing from an agent's memory.

    scripts/maintainer_queue.py                    # since yesterday
    scripts/maintainer_queue.py --since 2026-10-01

Sections, in order:
  DECIDE  open, labelled `needs-your-decision` (or titled "BLOCKED on the maintainer"): a ruling,
          a token, credit, an account
  TEST    open, labelled `needs-your-test`: merged and tested, needs his eyes on screen
  OWED    open, labelled `residue`: partly done, the rest still owed
  CLOSED  closed since --since
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess

BLOCKED_TITLE = "BLOCKED on the maintainer"


def _gh(*args: str) -> list[dict]:
    out = subprocess.run(["gh", *args, "--json", "number,title,labels,milestone,closedAt", "--limit", "5000"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def sections(open_issues: list[dict], closed_issues: list[dict]) -> dict[str, list[dict]]:
    """Sort issues into the maintainer's queue. Pure, so the rule is testable."""
    def has(issue: dict, label: str) -> bool:
        return any(entry["name"] == label for entry in issue["labels"])

    decide = [i for i in open_issues if has(i, "needs-your-decision") or BLOCKED_TITLE in i["title"]]
    test = [i for i in open_issues if has(i, "needs-your-test")]
    owed = [i for i in open_issues if has(i, "residue") and i not in test]
    return {"DECIDE": decide, "TEST": test, "OWED": owed, "CLOSED": closed_issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    parser.add_argument("--since", default=yesterday, help="closed on or after this date (YYYY-MM-DD)")
    args = parser.parse_args()

    open_issues = _gh("issue", "list", "--state", "open")
    closed = _gh("issue", "list", "--state", "closed", "--search", f"closed:>={args.since}")
    for name, issues in sections(open_issues, closed).items():
        print(f"\n{name} ({len(issues)})")
        for issue in sorted(issues, key=lambda i: i["number"]):
            milestone = (issue.get("milestone") or {}).get("title", "-")
            print(f"  #{issue['number']}  [{milestone}]  {issue['title'][:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
