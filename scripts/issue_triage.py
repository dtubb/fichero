#!/usr/bin/env python3
"""Sort every open issue by what the specs say about it, so the backlog matches the work.

Deterministic (maintainer, 2026-10-04: "there are like 5000, which seems a bit silly"). The specs
are the source of truth; GitHub follows them.

    scripts/issue_triage.py                  # dry run: counts per bucket, writes a TSV
    scripts/issue_triage.py --apply done     # close the DONE bucket
    scripts/issue_triage.py --apply stale    # close the STALE bucket
    scripts/issue_triage.py --check          # guard: exit 1 while any issue is STALE

Buckets, first match wins:
  WAITING  labelled needs-your-decision / needs-your-test / residue        -> keep
  TRACKED  a spec behaviour tagged GAP/PARTIAL/BROKEN/MISSING cites it      -> keep
  DONE     cited by spec behaviours, and every one of them is tagged [OK]    -> close as completed
  RECENT   created in the last --recent-days                                 -> keep (give it a spec home)
  STALE    no spec behaviour cites it, older than that                       -> close as not planned
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

SPECS = Path(__file__).resolve().parents[1] / "docs" / "contributor_manual" / "specs"
TAG = re.compile(r"\[(OK|GAP|PARTIAL|BROKEN|MISSING)\]")
ISSUE = re.compile(r"#(\d{2,5})\b")
WAITING_LABELS = {"needs-your-decision", "needs-your-test", "residue"}


def spec_citations(specs_dir: Path = SPECS) -> dict[int, set[str]]:
    """Issue number -> the set of tags of the behaviour bullets that cite it.

    A behaviour is a bullet carrying a state tag; its issue numbers may sit on the tagged line or on
    its indented continuation lines (many specs write `ISSUE: #N` there). Any line that is not an
    indented continuation ends the behaviour."""
    cited: dict[int, set[str]] = {}
    for path in specs_dir.rglob("*.md"):
        if path.name.startswith("_"):
            continue
        current: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.lstrip()
            continues = line[:1] in (" ", "\t") and not stripped.startswith(("- ", "* "))
            starts_item = not continues
            if starts_item:
                tag = TAG.search(line)
                current = tag.group(1) if (tag and stripped.startswith(("- ", "* "))) else None
            if current:
                for number in ISSUE.findall(line):
                    cited.setdefault(int(number), set()).add(current)
    return cited


def bucket(issue: dict, cited: dict[int, set[str]], today: dt.date, recent_days: int) -> str:
    labels = {entry["name"] for entry in issue["labels"]}
    if labels & WAITING_LABELS:
        return "WAITING"
    tags = cited.get(issue["number"], set())
    if tags - {"OK"}:
        return "TRACKED"
    if tags == {"OK"}:
        return "DONE"
    created = dt.date.fromisoformat(issue["createdAt"][:10])
    return "RECENT" if (today - created).days <= recent_days else "STALE"


def _open_issues() -> list[dict]:
    out = subprocess.run(["gh", "issue", "list", "--state", "open", "--limit", "5000", "--json",
                          "number,title,labels,createdAt,updatedAt,milestone"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recent-days", type=int, default=14)
    parser.add_argument("--apply", choices=["done", "stale"])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any open issue is STALE (the backlog rule, as a guard)")
    parser.add_argument("--tsv", default="/tmp/issue_triage.tsv")
    args = parser.parse_args()

    cited, today = spec_citations(), dt.date.today()
    rows = [(bucket(i, cited, today, args.recent_days), i) for i in _open_issues()]
    with open(args.tsv, "w", encoding="utf-8") as fh:
        for name, issue in sorted(rows, key=lambda r: (r[0], r[1]["number"])):
            milestone = (issue.get("milestone") or {}).get("title", "-")
            fh.write(f"{name}\t{issue['number']}\t{issue['createdAt'][:10]}\t{milestone}\t{issue['title']}\n")
    for name in ("WAITING", "TRACKED", "DONE", "RECENT", "STALE"):
        print(f"{name:8} {sum(1 for b, _ in rows if b == name)}")
    print(f"TSV: {args.tsv}")
    if args.check:
        stale = [i["number"] for b, i in rows if b == "STALE"]
        if stale:
            print(f"FAIL: {len(stale)} open issue(s) older than {args.recent_days} days that no spec "
                  "behaviour cites. Give each a spec behaviour, or close it (see the TSV).")
            return 1
        print("OK: every open issue is tracked by a spec, recent, or waiting on the maintainer.")

    if args.apply:
        target = args.apply.upper()
        reason, note = (("completed", "the specs mark every behaviour that cites it as built ([OK])")
                        if target == "DONE" else
                        ("not planned", "no spec behaviour tracks it and it is older than "
                         f"{args.recent_days} days"))
        for name, issue in rows:
            if name != target:
                continue
            subprocess.run(["gh", "issue", "close", str(issue["number"]), "--reason", reason, "--comment",
                            f"Closed in backlog triage (scripts/issue_triage.py, 2026-10-04): {note}. "
                            "If the need is still real, reopen it or refile it with the Bug or Spec-task "
                            "template against a spec behaviour."], check=False, capture_output=True)
        print(f"closed the {target} bucket")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
