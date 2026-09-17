#!/usr/bin/env python3
"""Bidirectional coverage audit: milestone <-> spec <-> manual.

The existing guardrails only look OUTWARD from a spec (does it declare a milestone / a manual
section?). They cannot see an ORPHANED MILESTONE — real work, with real issues, that has no
design behind it and nothing telling a user about it. That direction is this script's job
(creative-director, 2026-09-17: "review all the milestones, and make sure they're tied to a
spec and to a reference").

This is an AUDIT, not a gate: it always exits 0 and prints a coverage table, because today most
milestones predate the spec discipline. Use it to decide what to spec next; tighten into a gate
once coverage is close.

Run: python scripts/audit_spec_milestone_manual.py
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

SPECS_DIR = pathlib.Path("docs/contributor_manual/specs")
MILESTONE_RE = re.compile(r"Milestone:\s*(\S+)")
MANUAL_RE = re.compile(r"Manual:\s*(.+)")


def _specs() -> list[pathlib.Path]:
    return [p for p in SPECS_DIR.rglob("*.md") if not p.name.startswith("_")]


def _head(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")[:1200]


def _milestones() -> list[dict] | None:
    if shutil.which("gh") is None:
        return None
    try:
        proc = subprocess.run(
            ["gh", "api", "repos/:owner/:repo/milestones", "--paginate",
             "-q", "[.[] | {title, open: .open_issues, closed: .closed_issues}]"],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    out: list[dict] = []
    for chunk in proc.stdout.strip().splitlines():
        if chunk.strip():
            try:
                out.extend(json.loads(chunk))
            except json.JSONDecodeError:
                pass
    return out


def main() -> int:
    specs = _specs()
    # spec stem + declared milestone/manual
    by_milestone: dict[str, pathlib.Path] = {}
    spec_rows: list[tuple[str, str, str, str]] = []
    for p in specs:
        head = _head(p)
        status = "APPROVED" if re.search(r"Status:\s*APPROVED", head) else "DRAFT"
        ms = MILESTONE_RE.search(head)
        mn = MANUAL_RE.search(head)
        ms_name = ms.group(1) if ms else ""
        mn_ref = mn.group(1).strip() if mn else ""
        if ms_name:
            by_milestone[ms_name] = p
        by_milestone.setdefault(p.stem, p)  # stem == milestone name convention
        spec_rows.append((str(p.relative_to(SPECS_DIR)), status, ms_name or "-", mn_ref or "-"))

    milestones = _milestones()

    print("=" * 96)
    print("MILESTONE -> SPEC -> MANUAL   (orphaned milestones = work with no design behind it)")
    print("=" * 96)
    if milestones is None:
        print("(gh unavailable — skipping the milestone side)")
    else:
        covered = orphaned = 0
        print(f"{'MILESTONE':<46} {'ISSUES':>11}  {'SPEC':<26} MANUAL")
        for m in sorted(milestones, key=lambda x: x["title"].lower()):
            title = m["title"]
            spec = by_milestone.get(title)
            issues = f"{m['open']}o/{m['closed']}c"
            if spec:
                covered += 1
                head = _head(spec)
                mn = MANUAL_RE.search(head)
                manual = "yes" if (mn and not mn.group(1).strip().upper().startswith("TBD")) else "NO"
                print(f"{title:<46} {issues:>11}  {spec.stem:<26} {manual}")
            else:
                orphaned += 1
                print(f"{title:<46} {issues:>11}  {'— NO SPEC —':<26} -")
        print("-" * 96)
        print(f"milestones: {len(milestones)}   with a spec: {covered}   ORPHANED: {orphaned}")

    print()
    print("=" * 96)
    print("SPEC -> MILESTONE / MANUAL")
    print("=" * 96)
    print(f"{'SPEC':<44} {'STATUS':<9} {'MILESTONE':<26} MANUAL")
    for rel, status, ms_name, mn_ref in sorted(spec_rows):
        short = mn_ref if len(mn_ref) < 34 else mn_ref[:31] + "..."
        print(f"{rel:<44} {status:<9} {ms_name:<26} {short}")
    no_ms = sum(1 for _, s, m, _ in spec_rows if m == "-")
    no_mn = sum(1 for _, _, _, r in spec_rows if r == "-")
    print("-" * 96)
    print(f"specs: {len(spec_rows)}   without a milestone: {no_ms}   without a manual ref: {no_mn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
