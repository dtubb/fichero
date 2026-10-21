#!/usr/bin/env python3
"""Two pydantic models with the same class name under `api/routes` are one name in the OpenAPI schema: the generator
qualifies both (`fichero_server__api__routes__…__InviteResponse`) and every client that used the short name loses its type
(the Swift `Components.Schemas.InviteResponse` of the Users list, found at the cand 14 regen). Fails, naming the files, when a
class name that derives from `BaseModel` is defined in more than one module of `fichero-server/src/fichero_server/api/routes`.
Stdlib only; a static scan (no import), so a model built dynamically is not seen."""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan_files import scan_rglob  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROUTES = Path("fichero-server/src/fichero_server/api/routes")
#: Names already defined twice when this guard was written (2026-10-21): the committed contract carries most of them as qualified
#: schema names already, and their clients were written against that. A NEW clash fails; a name listed here that no longer clashes is
#: reported so the list shrinks. Do not add to it: rename the new model instead (review of cand 14; the list is a ceiling, not a licence).
KNOWN = frozenset({
    "CitationResponse",
    "DeletedResponse",
    "EntityAuditResponse",
    "EntityMergeRequest",
    "EntitySplitRequest",
    "ExportRequest",
    "ImportRequest",
    "ImportResponse",
    "ModelListResponse",
    "NoteCreateRequest",
    "NoteIdParams",
    "NoteRestoreParams",
    "NoteUpdateActionParams",
    "ProjectCreateRequest",
    "ReindexResponse",
    "ReorderResponse",
    "StatusResponse",
    "ToolListResponse",
})



def models(root: Path) -> tuple[dict[str, set[str]], int]:
    """class name -> the files defining it, for classes that (transitively, by name, within the scan) derive from BaseModel."""
    classes: list[tuple[str, str, list[str]]] = []
    scanned = 0
    for path in sorted(scan_rglob(root / ROUTES, "*.py")):
        scanned += 1
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                bases = [b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else "" for b in node.bases]
                classes.append((node.name, str(path.relative_to(root)), bases))
    known = {"BaseModel", "Enum", "IntEnum", "StrEnum"}  # an Enum is an OpenAPI schema too, so its name clashes like a model's
    grew = True
    while grew:
        grew = False
        for name, _file, bases in classes:
            if name not in known and known & set(bases):
                known.add(name)
                grew = True
    found: dict[str, set[str]] = defaultdict(set)
    for name, file, bases in classes:
        if name not in {"BaseModel", "Enum", "IntEnum", "StrEnum"} and known & set(bases):  # this class derives from a model; a plain class of the same name is not one
            found[name].add(file)
    return found, scanned


def main(root: Path = ROOT, known: frozenset[str] | None = None) -> int:
    known = KNOWN if known is None else known
    found, scanned = models(root)
    if scanned == 0:
        print(f"FAIL check_schema_names_are_unique: scanned no file under {ROUTES}")
        return 1
    clashes = {name: sorted(files) for name, files in found.items() if len(files) > 1}
    fresh = {name: files for name, files in clashes.items() if name not in known}
    stale = sorted(known - set(clashes))
    if fresh or stale:
        if fresh:
            print("FAIL check_schema_names_are_unique: a pydantic model name defined in more than one route module becomes a "
                  "qualified schema name and breaks the client types that used it. Rename one:")
            for name, files in sorted(fresh.items()):
                print(f"  {name}: {', '.join(files)}")
        if stale:
            print(f"FAIL check_schema_names_are_unique: no longer defined twice, remove from KNOWN: {', '.join(stale)}")
        return 1
    print(f"OK check_schema_names_are_unique: {len(found)} route models in {scanned} files, {len(clashes)} old clashes, no new one")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT))
