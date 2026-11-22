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
    return None if original_is_there(package, doc) else path


def original_is_there(package: Path, doc: Any) -> bool:
    """The one test of "is the original there" (#6733), the thumbnail's own answer (`resolve_source`: bookmark,
    recorded path, source keys), so the sheet and the thumbnail cannot disagree. The recorded path is tried first, as
    one stat plus the confinement `resolve_source` applies to it; the bookmark is resolved only when that fails."""
    from fichero_server.db.storage import _exists, resolve_source, settings
    from fichero_server.security.path_security import resolve_document_source_path

    recorded = Path(doc.path) if getattr(doc, "path", None) else None
    if (recorded is not None and recorded.is_absolute() and _exists(recorded)
            and resolve_document_source_path(recorded, package, storage_base=settings.base_path) is not None):
        return True
    return resolve_source(doc, library_root=package) is not None


def follow_bookmark(db: Any, doc: Any) -> Path | None:
    """The file a page's bookmark finds when it is not at its recorded path (#6733): the page's path and the source
    paths its metadata recorded move to it, and a FRESH bookmark is saved at once, so the next move is followed
    too. It writes directly, not through `document.relink_originals` (it is called from nowhere yet; wiring it
    means making it a plan entry of that action). None when there is no bookmark, it finds nothing, or the page is
    already where the bookmark says."""
    import base64

    from fichero_server import bookmarks

    raw = (doc.metadata or {}).get("bookmark")
    if not raw or not bookmarks.is_available():
        return None
    from fichero_server.db.storage import settings
    from fichero_server.security.path_security import resolve_document_source_path

    with bookmarks.BookmarkAccess(base64.b64decode(raw)) as resolved:
        # the same confinement `resolve_source` gives a bookmark's answer; a path outside it is not followed
        found = resolve_document_source_path(resolved, Path(db.path).parent, storage_base=settings.base_path) \
            if resolved is not None and Path(resolved).exists() else None
        fresh = bookmarks.refresh_bookmark(Path(found)) if found is not None and str(found) != doc.path else None
    if found is None or str(found) == doc.path:
        return None
    metadata = dict(doc.metadata)
    for key in PATH_KEYS:
        if metadata.get(key) == doc.path:
            metadata[key] = str(found)
    if fresh is None:
        raise RuntimeError(f"found {found} by its bookmark but could not make a fresh bookmark for it")
    metadata["bookmark"] = base64.b64encode(fresh).decode()
    db.save(doc.model_copy(update={"path": str(found), "metadata": metadata}))
    return Path(found)


def _present_by_listing(db: Any, package: Path, within: set[str] | None) -> tuple[list[tuple[str, str]], int]:
    """The linked pages' (id, path) that are NOT answered present by a listing, and how many were: one `scandir` a
    folder (a file that is listed, not a link, in a folder `resolve_document_source_path` admits, is there), and one
    `stat` a volume under /Volumes (a volume that is not mounted makes all its pages missing, their bookmarks not
    tried). Only id and path are read."""
    import os

    from fichero_server.db.storage import settings
    from fichero_server.security import path_security

    candidates: dict[str, list[tuple[str, str]]] = {}
    for doc_id, raw in db.page_paths():
        if (within is not None and doc_id not in within) or not Path(raw).is_absolute():
            continue  # not in scope, or the project's own copy
        candidates.setdefault(str(Path(raw).parent), []).append((doc_id, raw))
    unsure: list[tuple[str, str]] = []
    gone: list[tuple[str, str]] = []
    mounted: dict[str, bool] = {}
    inside: set[Path] | None = None  # the package, as given and resolved: made when a folder under it may exist
    prepared: path_security.PreparedRoots | None = None
    for folder, pages in candidates.items():
        parts = Path(folder).parts
        if len(parts) > 2 and parts[1] == "Volumes":
            volume = os.path.join(*parts[:3])
            if volume not in mounted:
                mounted[volume] = Path(volume).exists()
            if not mounted[volume]:
                gone.extend(pages)
                continue
        if inside is None:
            inside = {package, package.resolve()}
        if any(Path(folder).is_relative_to(root) for root in inside):
            continue  # the project's own copy
        if prepared is None:
            prepared = path_security.prepare_roots(package, storage_base=settings.base_path)
        if path_security.resolve_document_source_path(
            folder, package, storage_base=settings.base_path, prepared=prepared
        ) is None:
            unsure.extend(pages)
            continue
        try:
            with os.scandir(folder) as entries:
                listed = {e.name: e.is_symlink() for e in entries}
        except FileNotFoundError:
            unsure.extend(pages)  # the folder moved: a page's bookmark may still find its file
            continue
        except OSError:
            gone.extend(pages)  # a folder this process may not list holds no original it can open
            continue
        for doc_id, raw in pages:
            if listed.get(Path(raw).name) is False:
                continue
            unsure.append((doc_id, raw))
    return unsure + gone, len(gone)


def missing_originals(db: Any, within: set[str] | None = None) -> dict[str, Any] | None:
    """How many linked pages' originals are not where the project says, in one place (#5672); None when none.
    A page a folder listing shows is there costs no call of its own (#6828); one the listing does not show is asked
    with `original_is_there`, which also follows its bookmark and recorded source paths (#6733)."""
    from fichero_server.models import Document

    package = Path(db.path).parent
    not_listed, gone = _present_by_listing(db, package, within)
    missing: list[tuple[str, str]] = not_listed[: len(not_listed) - gone] if gone else not_listed
    still = [(i, p) for i, p in missing if (d := db.get(Document, i)) is not None and not original_is_there(package, d)]
    still += not_listed[len(not_listed) - gone :] if gone else []
    if not still:
        return None
    ids = [i for i, _ in still]
    roots = sorted({str(Path(p).parent) for _, p in still})
    n = len(ids)
    return {"pages": n, "folders": roots[:20], "ids": ids,
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
