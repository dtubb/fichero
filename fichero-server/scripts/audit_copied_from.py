#!/usr/bin/env python3
"""Read-only audit (#5906): which pages a `document.copy_into_project` has repointed at an in-package copy.

  python fichero-server/scripts/audit_copied_from.py <library.fichero|folder>...

Run it on a COPY of a library, or with the app closed: it opens each library read-only and writes nothing. A repointed page
carries `metadata.copied_from` (the original path it pointed at) and its `path` is now package-relative. It prints, per
library, the pages with `copied_from`, and exits 0 always. No repair: the owner decides what, if anything, to put back
(`document.uncopy_from_project` undoes one audited copy).
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb


def library_files(arg: str) -> list[Path]:
    path = Path(arg)
    return sorted(path.rglob("*.duckdb")) if path.is_dir() else [path]


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
    for arg in argv:
        for db_file in library_files(arg):
            try:
                found = audit(db_file)
            except Exception as exc:  # noqa: BLE001
                print(f"{db_file}: could not be read ({type(exc).__name__}: {exc})")
                continue
            print(f"{db_file}: {len(found)} repointed page(s)")
            for doc_id, name, where in found:
                print(f"  {doc_id}  {name}  {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
