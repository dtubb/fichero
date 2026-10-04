#!/usr/bin/env python3
"""Apply a reviewed triage TSV (from a triage batch) to the specs and to GitHub.

Each TSV line: number <TAB> decision <TAB> target <TAB> reason-or-behaviour-line

    scripts/apply_triage.py batch.tsv            # dry run
    scripts/apply_triage.py batch.tsv --apply

  SPEC       a line starting "- `" is added to the target spec under "## Triaged from the backlog";
             the issue stays open, now tracked (scheduled by that spec's milestone)
  IDEA       the reason is added to the target spec's "## Future (ideas, not scheduled)"; issue closed
  DONE       closed as completed, citing the evidence; if the reason says it awaits the maintainer,
             labelled needs-your-test instead
  OBSOLETE / DUPLICATE   closed as not planned, citing what replaced it
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "docs" / "contributor_manual" / "specs"
TRIAGED = "## Triaged from the backlog (2026-10-04)"
FUTURE = "## Future (ideas, not scheduled)"
AWAITS = re.compile(r"needs-your-test|awaiting daniel|pending daniel|daniel's click", re.IGNORECASE)


def spec_path(target: str) -> Path | None:
    match = re.search(r"([\w/-]+\.md)", target)
    if not match:
        return None
    name = match.group(1).removeprefix("docs/contributor_manual/specs/")
    path = SPECS / name
    return path if path.exists() else None


def add_under(path: Path, heading: str, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if line in text:
        return
    if heading not in text:
        text = text.rstrip("\n") + f"\n\n{heading}\n"
    head = text.index(heading) + len(heading) + 1
    nxt = text.find("\n## ", head)
    end = len(text) if nxt == -1 else nxt
    section = text[head:end].rstrip("\n")
    text = text[:head] + (section + "\n" if section else "") + line + "\n" + text[end:]
    path.write_text(text, encoding="utf-8")


def gh(*args: str) -> None:
    subprocess.run(["gh", *args], check=False, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tsv")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    for raw in Path(args.tsv).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        number, decision, target, note = (raw.split("\t") + ["", "", ""])[:4]
        decision, path = decision.strip().upper(), spec_path(target)
        action = "?"
        if decision == "SPEC":
            if note.startswith("- `") and path:
                action = f"spec line -> {path.relative_to(ROOT)}"
                if args.apply:
                    add_under(path, TRIAGED, note)
            else:
                action = "SKIP (no behaviour line or spec path; tracked already, or fix by hand)"
        elif decision == "IDEA":
            action = f"idea -> {path.relative_to(ROOT) if path else '?'} Future; close"
            if args.apply and path:
                add_under(path, FUTURE, f"- (#{number}) {note}")
                gh("issue", "close", number, "--reason", "not planned", "--comment",
                   f"Kept as an idea in {path.relative_to(ROOT)} (Future), not scheduled work. Closed in "
                   "backlog triage 2026-10-04; it becomes work again when a spec behaviour picks it up.")
        elif decision == "DONE":
            if AWAITS.search(note) or AWAITS.search(target):
                action = "label needs-your-test"
                if args.apply:
                    gh("issue", "edit", number, "--add-label", "needs-your-test")
            else:
                action = "close completed"
                if args.apply:
                    gh("issue", "close", number, "--reason", "completed", "--comment",
                       f"Closed in backlog triage 2026-10-04: done. Evidence: {target}. {note}")
        elif decision in ("OBSOLETE", "DUPLICATE"):
            action = "close not planned"
            if args.apply:
                gh("issue", "close", number, "--reason", "not planned", "--comment",
                   f"Closed in backlog triage 2026-10-04 ({decision.lower()}): {target}. {note}")
        print(f"#{number}\t{decision}\t{action}")
    if not args.apply:
        print("Dry run; pass --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
