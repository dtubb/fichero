"""Locate Originals: reconnect pages to files that moved (#5672).

Asked by the maintainer 2026-10-11: he moved EAP 1740's originals off iCloud to another folder, and the project still
pointed at the old paths. A linked page (its original kept at its own path, outside the project's package) whose file
is no longer there is matched to a file under the folder the person picks:

* **By the path below the old root**, the longest matching tail of path parts wins (`Box 3/f012.jpg` beats a bare
  `f012.jpg` elsewhere). A renamed root, a moved folder, a folder put one level deeper: all are a longer tail.
* **Ties broken by size, then checksum**, where the page recorded them at import (`file_size`, `checksum`). Two files
  sharing a name and a tail, with nothing to tell them apart, are **ambiguous** and listed, never chosen by name alone.
  A lone file of the right name but another size is not taken either.
* **A plan first** (matched, not found, ambiguous, and the folders whose root moves with them), then one audited,
  undoable action, `document.relink_originals`, that repoints the matched pages' and folders' paths and the source
  paths their metadata recorded. The pixels are the same file, so readings, thumbnails and renditions stay.
* **Detection**: `missing_originals` says in one place how many linked originals are not where the project says.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

#: Metadata keys that name a page's original or its folder, kept in step with its path.
PATH_KEYS = ("source_path", "full_path", "local_path", "source_folder")


def _linked_missing(package: Path, doc: Any) -> Path | None:
    raw = getattr(doc, "path", None)
    if not raw or not Path(raw).is_absolute():
        return None  # the project's own copy
    path = Path(raw)
    try:
        path.resolve().relative_to(package.resolve())
        return None
    except ValueError:
        pass
    return None if path.exists() else path


def missing_originals(db: Any, within: set[str] | None = None) -> dict[str, Any] | None:
    """How many linked pages' originals are not where the project says, in one place (#5672); None when none."""
    from fichero_server.models import DocType, Document

    package = Path(db.path).parent
    missing = [d for d in db.query(Document) if d.deleted_at is None and (within is None or d.id in within)
               and d.doc_type != DocType.folder and _linked_missing(package, d) is not None]
    if not missing:
        return None
    roots = sorted({str(Path(d.path).parent) for d in missing})
    n = len(missing)
    return {"pages": n, "folders": roots[:20], "ids": [d.id for d in missing],
            "sentence": (f"{n} page{'s' if n != 1 else ''}' original{'s are' if n != 1 else ' is'} not where this "
                         f"project says ({roots[0]}{' and elsewhere' if len(roots) > 1 else ''}): Locate Originals… "
                         "to point the project at where they are now")}


def _tail(old: Path, candidate_rel: tuple[str, ...]) -> int:
    """How many trailing path parts the old path and the candidate (below the new root) share."""
    n = 0
    for a, b in zip(reversed(old.parts), reversed(candidate_rel)):
        if a != b:
            break
        n += 1
    return n


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relink_plan(db: Any, new_root: str | Path, within: set[str] | None = None) -> dict[str, Any]:
    """What `document.relink_originals` would do, writing nothing: each missing linked page in scope matched,
    not found, or ambiguous, and each folder whose root moves with its pages."""
    from fichero_server.models import DocType, Document

    package = Path(db.path).parent
    root = Path(new_root)
    by_name: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink() and not path.name.startswith("."):
            by_name.setdefault(path.name, []).append(path)
    docs = [d for d in db.query(Document) if d.deleted_at is None and (within is None or d.id in within)]
    matched, not_found, ambiguous, prefixes = [], [], [], {}
    for doc in docs:
        if doc.doc_type == DocType.folder:
            continue
        old = _linked_missing(package, doc)
        if old is None:
            continue
        candidates = by_name.get(old.name, [])
        scored = [(c, _tail(old, c.relative_to(root).parts)) for c in candidates]
        best = max((s for _, s in scored), default=0)
        top = [c for c, s in scored if s == best]
        size = (doc.metadata or {}).get("file_size")
        if size is not None:
            top = [c for c in top if c.stat().st_size == int(size)]
        if len(top) > 1 and (doc.metadata or {}).get("checksum"):
            top = [c for c in top if _sha256(c) == doc.metadata["checksum"]]
        if not top:
            why = ("no file of that name under the folder" if not candidates
                   else "a file of that name, but another size: not taken")
            not_found.append({"id": doc.id, "name": doc.name, "from": str(old), "why": why})
            continue
        if len(top) > 1:
            ambiguous.append({"id": doc.id, "name": doc.name, "from": str(old),
                              "candidates": sorted(str(c) for c in top),
                              "why": "several files match its path and size; none is chosen by name alone"})
            continue
        to = top[0]
        by = "path" if best > 1 else "name and size" if size is not None else "name"
        matched.append({"id": doc.id, "name": doc.name, "from": str(old), "to": str(to), "by": by})
        # The old root and the new one this match implies, for the folders that move with their pages.
        old_root = Path(*old.parts[:len(old.parts) - best]) if best < len(old.parts) else Path(old.anchor)
        new_rel = to.relative_to(root).parts
        new_root_for = root.joinpath(*new_rel[:len(new_rel) - best]) if best < len(new_rel) else root
        prefixes.setdefault(str(old_root), str(new_root_for))
    folders = []
    for doc in docs:
        if doc.doc_type != DocType.folder or not doc.path or not Path(doc.path).is_absolute() or Path(doc.path).exists():
            continue
        for old_root, new_for in sorted(prefixes.items(), key=lambda kv: -len(kv[0])):
            try:
                rest = Path(doc.path).relative_to(old_root)
            except ValueError:
                continue
            target = Path(new_for) / rest
            if target.is_dir():
                folders.append({"id": doc.id, "name": doc.name, "from": doc.path, "to": str(target)})
            break
    sentence = (f"{len(matched)} matched, {len(not_found)} not found, {len(ambiguous)} ambiguous"
                + (f"; {len(folders)} folder{'s move' if len(folders) != 1 else ' moves'} with them" if folders else "")
                + ".")
    return {"new_root": str(root), "matched": matched, "not_found": not_found, "ambiguous": ambiguous,
            "folders": folders, "sentence": sentence}


def apply(db: Any, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Repoint the plan's matched pages and folders, in one transaction; returns what each was, for undo."""
    from fichero_server.models import Document

    moved: dict[str, dict[str, Any]] = {}
    with db.transaction():
        for entry in [*plan["matched"], *plan["folders"]]:
            doc = db.get(Document, entry["id"])
            if doc is None or doc.path != entry["from"]:
                continue  # changed since the plan
            metadata = dict(doc.metadata or {})
            before = {k: metadata.get(k) for k in PATH_KEYS if k in metadata}
            old_parent, new_parent = str(Path(entry["from"]).parent), str(Path(entry["to"]).parent)
            for key in PATH_KEYS:
                value = metadata.get(key)
                if value == entry["from"]:
                    metadata[key] = entry["to"]
                elif value == old_parent:
                    metadata[key] = new_parent
            db.save(doc.model_copy(update={"path": entry["to"], "metadata": metadata}))
            moved[doc.id] = {"from": entry["from"], "to": entry["to"], "metadata": before}
    return moved


def undo(db: Any, moved: dict[str, dict[str, Any]]) -> list[str]:
    """Point each page and folder back where it was, its recorded source paths with it."""
    from fichero_server.models import Document

    back = []
    with db.transaction():
        for doc_id, was in moved.items():
            doc = db.get(Document, doc_id)
            if doc is None or doc.path != was["to"]:
                continue
            metadata = {k: v for k, v in (doc.metadata or {}).items() if k not in PATH_KEYS}
            metadata.update(was.get("metadata") or {})
            db.save(doc.model_copy(update={"path": was["from"], "metadata": metadata}))
            back.append(doc_id)
    return back
