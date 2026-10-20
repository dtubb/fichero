#!/usr/bin/env python3
"""Read-only audit (#5906): which pages a `document.copy_into_project` has repointed at an in-package copy.

  python fichero-server/scripts/audit_copied_from.py <library.duckdb | a folder holding exactly one library>...

Run it ONLY on a COPY of a library: it opens each library read-only and writes nothing, and it REFUSES (exit 2, in words)
a path under ~/Fichero, ~/Fichero Projects or ~/Library/Containers/app.fichero.* (symlinks resolved first), a .duckdb with a
.wal beside it (a live or unclean library: opening it would replay the log), and a folder that does not hold exactly one
library file directly in it (nothing is searched recursively). A repointed page
carries `metadata.copied_from` (the original path it pointed at) and its `path` is now package-relative. It prints, per
library, the pages with `copied_from`, and exits 0 (2 if any path was refused). No repair: the owner decides what, if anything, to put back
(`document.uncopy_from_project` undoes one audited copy).
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb


def refusal(arg: str, home: Path | None = None) -> tuple[str, Path | None]:
    """(why this path is refused, else "") and the one library file it names. Pure, so each refusal is testable."""
    home = (home or Path.home()).resolve()
    path = Path(arg).expanduser().resolve()  # symlinks resolved first: a link into a live library is the live library
    containers = home / "Library" / "Containers"
    live = [home / "Fichero", home / "Fichero Projects", *sorted(containers.glob("app.fichero.*"))]
    # APFS is case-insensitive: compare resolved, case-folded paths (a container glob is case-sensitive, so also match by name)
    folded = [str(r.resolve()).casefold() for r in live]
    mine = str(path).casefold()
    in_container = containers.resolve() in path.parents and path.relative_to(containers.resolve()).parts[0].casefold().startswith("app.fichero.")
    if in_container or any(mine == root or mine.startswith(root + "/") for root in folded):
        return f"{path} is under a live Fichero location; copy the library elsewhere and audit the copy.", None
    if path.is_dir():
        found = sorted(path.glob("*.duckdb"))  # directly in the folder only
        if len(found) != 1:
            return f"{path} holds {len(found)} library files; name the one library file instead.", None
        path = found[0]
    if not path.is_file():
        return f"{path} is not a library file.", None
    if Path(f"{path}.wal").exists():
        return f"{path} has a .wal beside it (live or unclean); audit a clean copy, not this.", None
    return "", path


def audit(db_file: Path) -> list[tuple[str, str, str]]:
    con = duckdb.connect(str(db_file), read_only=True)
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if "documents" not in tables:
            return []
        rows = con.execute(
            "SELECT id, name, path, metadata FROM documents WHERE metadata::VARCHAR LIKE '%copied_from%'").fetchall()
    finally:
        con.close()
    return [(r[0], r[1] or "", f"now {r[2]}  was {_copied_from(r[3])}") for r in rows]


def _copied_from(metadata) -> str:
    import json

    try:
        return json.loads(metadata).get("copied_from", "?") if isinstance(metadata, str) else (metadata or {}).get("copied_from", "?")
    except Exception:  # noqa: BLE001 -- an unreadable metadata cell is reported, not fatal
        return "?"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    refused = False
    for arg in argv:
        why, db_file = refusal(arg)
        if why:
            print(f"REFUSED: {why}")
            refused = True
            continue
        try:
            found = audit(db_file)
        except Exception as exc:  # noqa: BLE001
            print(f"{db_file}: could not be read ({type(exc).__name__}: {exc})")
            continue
        print(f"{db_file}: {len(found)} repointed page(s)")
        for doc_id, name, where in found:
            print(f"  {doc_id}  {name}  {where}")
    return 2 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
