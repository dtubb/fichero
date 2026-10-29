"""Pages whose originals are in iCloud and not on this Mac: warn, and copy them into the project (#5669).

Ruled by the maintainer 2026-10-11: before Start (and after an import), the plan says how many of the project's
pages are linked to originals that are in iCloud and not on this Mac, and offers, as the primary action, to copy
them into the project: each original is brought down (bounded, `dataless.fetch_first`), copied into the package by
the import's own Copy path (`ingest._copy_to_library`: an APFS clone where it can, verified by size), and the page
then points at its own copy, never at iCloud again. There is no silent download in place as the default; the
bounded fetch before a step reads its pages (`workflows/tools/sources._fetches_first`) stays as the last line of
defence. The copy is one audited action, undone by putting the pages back on their originals and removing the
copies it made.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fichero_server.importers import dataless
from fichero_server.importers.dataless import FETCH_FREE_FLOOR_BYTES, _size_words


def _linked_original(package: Path, doc: Any) -> Path | None:
    """A page's original when it is linked (kept at its own path outside the project's package)."""
    raw = getattr(doc, "path", None)
    if not raw or not Path(raw).is_absolute():
        return None  # a package-relative path is the project's own copy
    path = Path(raw)
    try:
        path.resolve().relative_to(package.resolve())
        return None
    except ValueError:
        return path


def pages_in_icloud(db: Any, within: set[str] | None = None) -> list[tuple[Any, Path, int]]:
    """(page, its original, its size) for every live page whose linked original is in iCloud and not on this Mac,
    within the given documents when named. One `stat` a page: never reads a byte."""
    from fichero_server.models import Document

    package = Path(db.path).parent
    out = []
    for doc in (db.query(Document) if within is None else db.query_in(Document, "id", within)):
        if doc.deleted_at is not None:
            continue
        original = _linked_original(package, doc)
        if original is None or not original.exists() or dataless.dataless_reason(original) is None:
            continue
        out.append((doc, original, getattr(original.stat(), "st_size", 0) or 0))
    return out


def summary(db: Any, within: set[str] | None = None, *, of: int | None = None) -> dict[str, Any] | None:
    """The warning and the offer, for Ready and for an import's answer; None when no page is in iCloud.

    `of`: how many pages the plan covers, for "34 of 92 pages". `room` is false (and `refusal` says why, with the
    numbers) when this disk cannot hold them while keeping its floor free: neither a copy nor a read could bring
    them down."""
    found = pages_in_icloud(db, within)
    if not found:
        return None
    size = sum(s for _, _, s in found)
    free = shutil.disk_usage(Path(db.path).parent).free
    room = size + FETCH_FREE_FLOOR_BYTES <= free
    n = len(found)
    pages = f"{n} page{'s' if n != 1 else ''}"
    counted = f"{n} of {of} pages" if of and of >= n else pages
    verb = "is" if n == 1 and not of else "are"
    sentence = f"{counted} {verb} in iCloud and not on this Mac."
    refusal = None
    if not room:
        refusal = (f"{pages} in iCloud need {_size_words(size)} to come to this Mac, and this disk has "
                   f"{_size_words(free)} free (Fichero keeps {_size_words(FETCH_FREE_FLOOR_BYTES)} free). Free some "
                   "space first")
    return {"pages": n, "of": of, "bytes": size, "sentence": sentence, "room": room, "refusal": refusal,
            "offer": f"Copy them into the project ({_size_words(size)}, then they stay here)",
            "action": "document.copy_into_project", "params": {"ids": [doc.id for doc, _, _ in found]}}


def copy_into_project(db: Any, ids: list[str], *, say=lambda words: None, fetch=None,
                      min_timeout: float | None = None) -> dict[str, Any]:
    """Bring each named page's linked original down and copy it into the package; the page then points at its own
    copy. Returns {"copied": {id: {"from", "to"}}, "not_copied": {id: why}}. A page already the project's own, or
    not found, is left alone and said. Every copy is written before any page is changed, and a page is changed
    only once its copy is verified."""
    from fichero_server.importers.ingest import _copy_to_library
    from fichero_server.models import Document

    package = Path(db.path).parent
    pages, not_copied = [], {}
    for doc_id in dict.fromkeys(ids):
        doc = db.get(Document, doc_id)
        original = _linked_original(package, doc) if doc is not None and doc.deleted_at is None else None
        if doc is None or doc.deleted_at is not None:
            not_copied[doc_id] = "no such page in this project"
        elif original is None:
            not_copied[doc_id] = f"{doc.name} is already the project's own copy"
        elif not original.exists():
            not_copied[doc_id] = f"{doc.name}: its original is not at {original}"
        else:
            pages.append((doc, original))
    kwargs = {"say": say, **({"fetch": fetch} if fetch else {}),
              **({"min_timeout": min_timeout} if min_timeout is not None else {})}
    failed = dataless.fetch_first([str(o) for _, o in pages], **kwargs)
    made: list[tuple[Any, Path, Path]] = []
    try:
        for doc, original in pages:
            if str(original) in failed:
                not_copied[doc.id] = failed[str(original)]
                continue
            made.append((doc, original, _copy_to_library(original, package)))
    except Exception:
        for _, _, copy in made:  # nothing half done: the copies made so far go, the pages are untouched
            copy.unlink(missing_ok=True)
        raise
    copied = {}
    with db.transaction():
        for doc, original, copy in made:
            relative = str(copy.relative_to(package))
            metadata = dict(doc.metadata or {})
            metadata["copied_from"] = str(original)
            for key in ("source_path", "full_path", "local_path"):
                if metadata.get(key) == str(original):
                    metadata[key] = relative
            db.save(doc.model_copy(update={"path": relative, "metadata": metadata}))
            copied[doc.id] = {"from": str(original), "to": relative}
    return {"copied": copied, "not_copied": not_copied}


def undo_copy_into_project(db: Any, copied: dict[str, dict[str, str]]) -> list[str]:
    """Put each page back on its original and remove the copy the action made (only that file). Returns the pages
    put back."""
    from fichero_server.models import Document

    package = Path(db.path).parent
    back = []
    with db.transaction():
        for doc_id, moved in copied.items():
            doc = db.get(Document, doc_id)
            if doc is None or doc.path != moved["to"]:
                continue  # changed since: left as it is
            metadata = {k: v for k, v in (doc.metadata or {}).items() if k != "copied_from"}
            for key in ("source_path", "full_path", "local_path"):
                if metadata.get(key) == moved["to"]:
                    metadata[key] = moved["from"]
            db.save(doc.model_copy(update={"path": moved["from"], "metadata": metadata}))
            back.append(doc_id)
    for doc_id in back:
        (package / copied[doc_id]["to"]).unlink(missing_ok=True)
    return back
