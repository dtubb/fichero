#!/usr/bin/env python3
"""Every read of a Trash-hidden kind goes through the Trash seam (`safety.trash.every-read-leaves-it-out`, #5406, #5243).

A thing in the Trash appears in no list, count, search, graph or export. The engine leaves it out in ONE seam
(`knowledge/trash_visibility.py`, and `trashed_document_ids` / `hide_trashed` for SQL reads). The defect found twice already
(#4960, and documents in exports) is a mark that is written and never read, so this refuses the next one: an API GET handler
that queries a kind the Trash hides (statements, entities, annotations, notes, artifacts) and names neither the seam nor the
Trash.

The handlers that do not yet are seeded in `check_trash_seam_reads_known_gaps.json` (key `<route file>::<function>`), each a
leak to close and then delete from the file. A new one fails. A baseline entry that no longer applies is reported, not failed.

Usage:
    scripts/check_trash_seam_reads.py
    scripts/check_trash_seam_reads.py --list
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from _check_floor import require_scan_floor
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "fichero-server/src/fichero_server/api/routes"
KNOWN_GAPS_PATH = Path(__file__).with_name("check_trash_seam_reads_known_gaps.json")

#: The kinds a Trashed document hides (they rest on it; `trash_visibility`, `trash_storage`).
KINDS = frozenset({"KnowledgeClaim", "KnowledgeEntity", "Annotation", "Note", "Artifact"})
#: A handler naming any of these has gone through the seam, or asked for the Trash by name.
SEAM = (
    "trash_visibility", "visible_claims", "visible_entities", "visible_annotations", "visible_notes",
    "visible_document_ids", "claim_is_hidden", "trashed_document_ids", "trashed_ids", "hide_trashed",
)
#: 443 GET handlers examined when set (2026-11-05); a tripwire at half, not a ratchet (#4487).
SCAN_FLOOR = 220


def _is_get(fn: ast.AST) -> bool:
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get"
        for d in getattr(fn, "decorator_list", [])
    )


def _kind_read(call: ast.Call) -> str | None:
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in ("query", "all") and call.args):
        return None
    arg = call.args[0]
    name = arg.id if isinstance(arg, ast.Name) else arg.attr if isinstance(arg, ast.Attribute) else None
    return name if name in KINDS else None


def scan(routes: Path = ROUTES) -> tuple[int, dict[str, list[str]]]:
    """(GET handlers examined, {route file::function: kinds read without the seam})."""
    examined = 0
    found: dict[str, list[str]] = {}
    for path in sorted(scan_rglob(routes, "*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _is_get(fn):
                continue
            examined += 1
            kinds = sorted({k for n in ast.walk(fn) if isinstance(n, ast.Call) and (k := _kind_read(n))})
            if kinds and not any(token in (ast.get_source_segment(source, fn) or "") for token in SEAM):
                found.setdefault(f"{path.relative_to(routes).as_posix()}::{fn.name}", []).extend(kinds)
    return examined, found


def load_known_gaps(path: Path = KNOWN_GAPS_PATH) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main(argv: list[str]) -> int:
    examined, found = scan()
    require_scan_floor(examined, SCAN_FLOOR, "API GET handlers")
    known = load_known_gaps()
    if "--list" in argv:
        for key, kinds in sorted(found.items()):
            print(f"{key}: {', '.join(sorted(set(kinds)))}{'  [known gap]' if key in known else ''}")
    new = sorted(set(found) - set(known))
    stale = sorted(set(known) - set(found))
    for key in stale:
        print(f"  note: {key} no longer reads without the seam; delete it from {KNOWN_GAPS_PATH.name}")
    if new:
        print(f"check_trash_seam_reads: {len(new)} new read(s) of a Trash-hidden kind without the seam")
        for key in new:
            print(f"  {key}: {', '.join(sorted(set(found[key])))}")
        print(
            "Fix: read through `knowledge/trash_visibility.py` (visible_claims / visible_entities / visible_annotations / "
            "visible_notes) or `trashed_document_ids`, so a thing in the Trash is left out "
            "(`safety.trash.every-read-leaves-it-out`)."
        )
        return 1
    print(f"check_trash_seam_reads: {examined} GET handlers examined; {len(found)} known gaps ({len(known)} seeded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
