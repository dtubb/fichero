"""What a started recipe's step has already done (`source.recipe.done-is-not-redone`, #5390).

The pages a card runs on are worked out when it starts: the project's material (every page, and every file
that has no pages), or the pages an import brought and the pages since cut from them; for a split, the
photographs. Of those, the ones that already have the card's output are left alone unless the person asked to
redo the step:

* splitting: a photograph already cut into pages;
* finding lines: a page with a live pass that has lines;
* reading (with or without finding lines first): a page with a live pass, read by the step's own model, that
  has lines.

Every other card cannot tell, and runs on every page.
"""
from __future__ import annotations

from typing import Any

#: Jobs whose output a page can be seen to have.
KNOWS_DONE = frozenset({"split-pages", "find-lines", "read-a-line"})


def _children(db: Any, doc_id: str) -> list[Any]:
    from fichero_server.models import Document

    return [c for c in db.query(Document, parent_id=doc_id) if not c.deleted_at]


def _is_split_page(doc: Any) -> bool:
    meta = doc.metadata if isinstance(doc.metadata, dict) else {}
    return getattr(doc.doc_type, "value", doc.doc_type) == "chunk" and bool(meta.get("split_source_id"))


def pages_for(db: Any, card: dict[str, Any], documents: list[str] | None) -> list[str]:
    """The pages (or, for a split, the photographs) this card runs on now."""
    from fichero_server.models import Document

    if card.get("job") == "split-pages":
        if documents is None:
            docs = [d for d in db.query(Document) if not d.deleted_at
                    and getattr(d.doc_type, "value", d.doc_type) == "file"
                    and getattr(d.file_type, "value", d.file_type) == "image"]
            return sorted(d.id for d in docs)
        return list(documents)
    if documents is None:
        # The project's material, and the pages a split cut from a photograph (stored as its `chunk` children, which
        # the material count does not see as pages).
        material = db.unit_of_work_ids()
        known = set(material)
        split = sorted(d.id for d in db.query(Document) if not d.deleted_at and _is_split_page(d))
        return material + [d for d in split if d not in known]
    out: list[str] = []
    for doc_id in documents:  # an imported photograph cut since: its pages are the material
        out.extend([c.id for c in _children(db, doc_id)] or [doc_id])
    return out


def _has_lines(db: Any, doc_id: str, model: str | None) -> bool:
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass

    for p in db.query(SegmentPass, document_id=doc_id):
        if p.deleted_at or (model is not None and p.model != model):
            continue
        if any(s.kind == "line" and not s.deleted_at for s in db.query(Segment, pass_id=p.id)):
            return True
    return False


def is_done(db: Any, card: dict[str, Any], doc_id: str) -> bool | None:
    """True when the page already has this card's output; None when the card cannot tell."""
    job = card.get("job")
    if job == "split-pages":
        return bool(_children(db, doc_id))
    if job == "find-lines":
        return _has_lines(db, doc_id, None)
    if job == "read-a-line":
        return _has_lines(db, doc_id, card.get("model_override"))
    return None


def split_done(db: Any, card: dict[str, Any], pages: list[str]) -> tuple[list[str], int | None]:
    """(the pages still to do, how many are done; None when the card cannot tell)."""
    if card.get("job") not in KNOWS_DONE:
        return pages, None
    todo = [p for p in pages if not is_done(db, card, p)]
    return todo, len(pages) - len(todo)


def annotate(db: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Each run in the Start plan with `done`, `of` and a `note`, as things stand now."""
    for card in plan.get("runs", []):
        pages = pages_for(db, card, None)
        _todo, done = split_done(db, card, pages)
        card["done"], card["of"] = done, len(pages)
        unit = "photographs" if card.get("job") == "split-pages" else "pages"
        card["note"] = (f"already done on {done} of {len(pages)} {unit}; runs on the rest" if done is not None
                        else f"cannot tell what is done; runs on every page ({len(pages)})")
    return plan
