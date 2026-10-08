"""What a started recipe's step has already done (`source.recipe.done-is-not-redone`, #5390).

The pages a card runs on are worked out when it starts: the project's material (every page, and every file
that has no pages), or the pages an import brought and the pages since cut from them; for a split, the
photographs. Of those, the ones that already have the card's output are left alone unless the person asked to
redo the step:

* splitting: a photograph already cut into pages;
* finding lines: a page with a live pass that has lines;
* reading lines (with or without finding lines first): a page with a live pass, read by the step's own model,
  that has lines;
* reading a page: a page with a transcription saved by the step's own model.

Every other card cannot tell, and runs on every page.
"""
from __future__ import annotations

from typing import Any

#: Jobs whose output a page can be seen to have.
KNOWS_DONE = frozenset({"split-pages", "find-lines", "read-a-line", "read-a-page"})


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


#: What each unit of work (and each document held that is not one) is, in words: (one, many).
_UNIT_WORDS = {"photograph": ("photograph", "photographs"), "pdf-page": ("PDF page", "PDF pages"),
               "page": ("page of a file", "pages of files"),
               "cut": ("page cut from a photograph", "pages cut from photographs"),
               "file": ("file with no pages", "files with no pages"),
               # Held, not counted: the pages are.
               "pdf": ("PDF its pages came from", "PDFs their pages came from"),
               "split": ("photograph cut into pages", "photographs cut into pages"),
               "source": ("file its pages came from", "files their pages came from"),
               "folder": ("folder", "folders")}
_COUNTED = ("photograph", "pdf-page", "page", "cut", "file")
_HELD_WORDS = ("pdf", "split", "source", "folder")


def _kind(doc: Any) -> str:
    return str(getattr(doc.doc_type, "value", doc.doc_type))


def _file_type(doc: Any) -> str:
    return str(getattr(doc.file_type, "value", doc.file_type) or "")


def _words(n: int, key: str) -> str:
    one, many = _UNIT_WORDS[key]
    return f"{n} {one if n == 1 else many}"


def material(db: Any) -> dict[str, Any]:
    """The project's pages, as the plan counts them, and what they are in words (#5498): the pages a started
    recipe runs over (`pages_for`), one figure for the estimate and the run. The sentence says what is counted
    ("4 photographs + 1 PDF page = 5 pages"), what the project holds that is not (the PDF a page came from, a
    photograph since cut into pages, folders), and photographs that share a file name, so a count that grows
    with copies taken in twice says so rather than jumping without a word."""
    from collections import Counter

    from fichero_server.models import Document

    ids = pages_for(db, {}, None)
    docs = {d.id: d for d in db.query(Document)
            if not d.deleted_at and getattr(d, "node_kind", None) not in ("workflow", "entry")}
    counted: Counter[str] = Counter()
    for doc_id in ids:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        kind = _kind(doc)
        if kind == "page":
            parent = docs.get(doc.parent_id) if doc.parent_id else None
            counted["pdf-page" if parent is not None and _file_type(parent) == "pdf" else "page"] += 1
        elif kind == "chunk":
            counted["cut"] += 1
        else:
            counted["photograph" if _file_type(doc) == "image" else "file"] += 1
    parts = [_words(counted[k], k) for k in _COUNTED if counted[k]]
    sentence = f"{' + '.join(parts) or 'nothing'} = {len(ids)} {'page' if len(ids) == 1 else 'pages'}"
    # What the project holds that is not a page to read, so "N documents" elsewhere is not a second count.
    taken = set(ids)
    rest: Counter[str] = Counter()
    for doc in docs.values():
        kind = _kind(doc)
        if doc.id in taken or kind not in ("file", "folder", "group"):
            continue
        rest["folder" if kind != "file" else "pdf" if _file_type(doc) == "pdf"
             else "split" if _file_type(doc) == "image" else "source"] += 1
    if rest:
        held = ", ".join(_words(rest[k], k) for k in _HELD_WORDS if rest[k])
        sentence += f"; the project holds {len(taken) + sum(rest.values())} documents: these, and {held}"
    names = Counter(docs[i].name for i in ids
                    if i in docs and _kind(docs[i]) == "file" and _file_type(docs[i]) == "image")
    copies = sum(n for n in names.values() if n > 1)
    if copies:
        sentence += f"; {copies} photographs share a file name with another: copies taken in twice?"
    return {"pages": len(ids), "counted": {k: counted[k] for k in _COUNTED if counted[k]}, "sentence": sentence}


def _has_lines(db: Any, doc_id: str, model: str | None) -> bool:
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass

    for p in db.query(SegmentPass, document_id=doc_id):
        if p.deleted_at or (model is not None and p.model != model):
            continue
        if any(s.kind == "line" and not s.deleted_at for s in db.query(Segment, pass_id=p.id)):
            return True
    return False


def _has_line_readings(db: Any, doc_id: str, model: str | None) -> bool:
    """The model read the page's lines: a pass of its own with lines (before #5487), or a reading it wrote
    onto the page's lines (one line pass per page, read many times: the reading names the model's page
    artifact it came from)."""
    from fichero_server.models import Artifact, ContentRepresentation

    if _has_lines(db, doc_id, model):
        return True
    by_model = {a.id for a in db.query(Artifact, document_id=doc_id) if model is None or a.model == model}
    return bool(by_model) and any(r.segment_id and r.derived_from_artifact_id in by_model
                                  for r in db.query(ContentRepresentation, document_id=doc_id))


def _has_page_reading(db: Any, doc_id: str, model: str | None) -> bool:
    """A transcription the model saved (a read that came back empty saves none)."""
    from fichero_server.models import Artifact

    return any(a.artifact_type == "transcription" and (model is None or a.model == model)
               for a in db.query(Artifact, document_id=doc_id))


def is_done(db: Any, card: dict[str, Any], doc_id: str) -> bool | None:
    """True when the page already has this card's output; None when the card cannot tell."""
    job = card.get("job")
    if job == "split-pages":
        return bool(_children(db, doc_id))
    if job == "find-lines":
        return _has_lines(db, doc_id, None)
    if job == "read-a-line":
        return _has_line_readings(db, doc_id, card.get("model_override"))
    if job == "read-a-page":
        return _has_page_reading(db, doc_id, card.get("model_override"))
    return None


def split_done(db: Any, card: dict[str, Any], pages: list[str]) -> tuple[list[str], int | None]:
    """(the pages still to do, how many are done; None when the card cannot tell)."""
    if card.get("job") not in KNOWS_DONE:
        return pages, None
    todo = [p for p in pages if not is_done(db, card, p)]
    return todo, len(pages) - len(todo)


def annotate(db: Any, plan: dict[str, Any], unfinished: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Each run in the Start plan with `done`, `of` and a `note`, as things stand now; a run whose steps the last
    run did not finish (`unfinished`, `runner.unfinished_steps`) says so with `last_run` and `last_why`, and
    that Start runs it again (#5498)."""
    for card in plan.get("runs", []):
        pages = pages_for(db, card, None)
        _todo, done = split_done(db, card, pages)
        card["done"], card["of"] = done, len(pages)
        unit = "photographs" if card.get("job") == "split-pages" else "pages"
        card["note"] = (f"already done on {done} of {len(pages)} {unit}; runs on the rest" if done is not None
                        else f"cannot tell what is done; runs on every page ({len(pages)})")
        last = next(((sid, (unfinished or {})[sid]) for sid in card["steps"] if sid in (unfinished or {})), None)
        if last is not None:
            sid, outcome = last
            card["last_run"], card["last_why"] = outcome["state"], outcome["why"]
            card["note"] = f"{outcome['state']} last time (step {sid}: {outcome['why']}); runs again: {card['note']}"
    return plan
