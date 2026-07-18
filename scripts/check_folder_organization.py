#!/usr/bin/env python3
"""Folder-organization guardrail — flag Swift dumping-ground directories.

Rule (#1940/#1944): directories under `fichero/fichero` should not collect a
large number of unrelated Swift files directly in one folder. Put files in a
feature-specific subfolder when a directory becomes a catch-all.

This detector intentionally uses cheap static signals:
  1. More than MAX_DIRECT_SWIFT_FILES `.swift` files directly in a directory.
  2. Known mixed-concern directories that already need subdivision.

It does not try to prove architecture. `KNOWN_VIOLATIONS` is the current backlog:
the script exits 0 while only these known folders are found, and exits 1 if a new
dumping-ground folder appears. See agents/ROADMAP.md for the guardrail roadmap.

Usage:
    python3 scripts/check_folder_organization.py
    python3 scripts/check_folder_organization.py --list
    python3 scripts/check_folder_organization.py -h
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
RULE_DOC = "agents/ROADMAP.md"
MAX_DIRECT_SWIFT_FILES = 18

MIXED_CONCERN_DIRS: dict[str, str] = {
    "Views/Library": "mixes browser, picker, inspector, viewer, and workspace surfaces",
    "Views/Workflow": "mixes editor, execution, node, import/export, and library surfaces",
    "Views/Sidebar": "mixes sidebar state, rows, drag/drop, modes, and commands",
}

SUGGESTED_SUBFOLDERS: dict[str, str] = {
    "Views/Library": "Artifacts/, PDFReading/, QuickLook/, KnowledgeGraph/, Pickers/, Tools/, Thumbnails/",
}

# Current folder-organization backlog. Drop entries as directories are split.
KNOWN_VIOLATIONS: dict[str, str] = {
    "Models": "#1944 — 53 Swift files directly in Models",
    "Services": "#1944 — 60 Swift files directly in Services",
    "Views/KnowledgeGraph/OntologyBrowser": "#1944 — 31 Swift files directly in OntologyBrowser",
    "Views/Library": "#1944 — 42 Swift files directly; mixed Library concerns",
    "Views/Inspector/Document": "#3439 — 25 Swift files directly in Inspector/Document; split by responsibility (Phase 3 reorg)",
    "Views/Inspector": "#3439 — 25 Swift files directly in Inspector; split by responsibility (Phase 3 reorg)",
    "Views/Settings": "settings panes absorbed AIProviders/MCPServers/About; subfolder by tab (follow-on reorg)",
    "Views/Sidebar": "#1944 — 27 Swift files directly; mixed Sidebar concerns",
    "Views/Workflow": "#1944 — 42 Swift files directly; mixed Workflow concerns",
}


def direct_swift_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".swift")


def scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for directory in sorted(p for p in SWIFT_ROOT.rglob("*") if p.is_dir()):
        rel = directory.relative_to(SWIFT_ROOT).as_posix()
        files = direct_swift_files(directory)
        reasons: list[str] = []
        if len(files) > MAX_DIRECT_SWIFT_FILES:
            reasons.append(
                f"{len(files)} Swift files directly in one directory "
                f"(limit: {MAX_DIRECT_SWIFT_FILES})"
            )
        if rel in MIXED_CONCERN_DIRS:
            reasons.append(MIXED_CONCERN_DIRS[rel])
        if reasons:
            found[rel] = reasons
    return found


def print_list(found: dict[str, list[str]]) -> None:
    print(f"Folder-organization offenders ({len(found)} directories):\n")
    for rel, reasons in sorted(found.items(), key=lambda item: (-len(direct_swift_files(SWIFT_ROOT / item[0])), item[0])):
        tag = "known" if rel in KNOWN_VIOLATIONS else "NEW"
        print(f"  [{tag}] {rel}")
        for reason in reasons:
            print(f"          - {reason}")
        if rel in SUGGESTED_SUBFOLDERS:
            print(f"          - suggested subfolders: {SUGGESTED_SUBFOLDERS[rel]}")
        print(f"          - move new files into a specific subfolder under {rel}")


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print_list(found)
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Folder-organization guardrail: scanned {SWIFT_ROOT.relative_to(ROOT)}")
    print(f"  {len(found)} dumping-ground directorie(s); {len(known)} known backlog entries.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for rel in stale:
            print(f"      {rel}")

    if new:
        print(f"\n  ✗ {len(new)} new dumping-ground directorie(s):")
        for rel in new:
            for reason in found[rel]:
                print(f"      {rel}  ←  {reason}")
        print(
            "\nFix: move the added Swift file(s) into a focused subfolder, or split the "
            f"directory as part of the organization roadmap. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No folder-organization offenders beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
