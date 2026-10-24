"""What a started recipe's step has already done (`source.recipe.done-is-not-redone`, #5390).

The pages a card runs on are worked out when it starts: the project's material (every page, and every file
that has no pages), or the pages an import brought and the pages since cut from them; for a split, the
photographs. Of those, the ones that already have the card's output are left alone unless the person asked to
redo the step:

* splitting: a photograph already cut into pages;
* finding regions: a page with regions the step's own model found; for Kraken's segmenter, which keeps the
  page's lines with its regions (#5689), a page that has lines too;
* finding lines: a page with a live pass that has lines;
* reading lines (with or without finding lines first): a page with a live pass, read by the step's own model,
  that has lines;
* reading a page: a page with a transcription saved by the step's own model;
* preparing the image: a page with a prepared rendition, or one a finished run's step looked at and found
  clear (#5706);
* correcting: a page with a reviewed transcription (the paleographer's review) saved by the step's own model;
* finding names: a page some entity names as a page it was found on (#5584), or one a finished run's names
  step ran on (#5706): a page whose text names no one is done once looked at.

Every other card cannot tell, and runs on every page.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Jobs whose output a page can be seen to have.
KNOWS_DONE = frozenset({"split-pages", "find-regions", "find-lines", "read-a-line", "read-a-page", "prepare-the-image",
                        "correct", "find-names-tag-words", "split-into-entries"})
#: What the correcting step's workflow (the paleographer's review, `transcribe_review`) saves on a page.
REVIEWED = "transcription_review"


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


def material(db: Any, within: set[str] | None = None) -> dict[str, Any]:
    """The project's pages, as the plan counts them, and what they are in words (#5498): the pages a started
    recipe runs over (`pages_for`), one figure for the estimate and the run. The sentence says what is counted
    ("4 photographs + 1 PDF page = 5 pages"), what the project holds that is not (the PDF a page came from, a
    photograph since cut into pages, folders), and photographs that share a file name, so a count that grows
    with copies taken in twice says so rather than jumping without a word. `within`: only these documents (a
    folder's, `runner.folder_scope`; `source.recipe.folder-scoped-start`)."""
    from collections import Counter

    from fichero_server.models import Document

    ids = [i for i in pages_for(db, {}, None) if within is None or i in within]
    docs = {d.id: d for d in db.query(Document)
            if not d.deleted_at and getattr(d, "node_kind", None) not in ("workflow", "entry")
            and (within is None or d.id in within)}
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
    return {"pages": len(ids), "ids": ids, "counted": {k: counted[k] for k in _COUNTED if counted[k]},
            "sentence": sentence}


def kraken_lines_known(db: Any, page_ids: list[str]) -> dict[str, Any]:
    """What the project already holds of Kraken's lines on these pages, for the price of variant A before it runs
    (`source.recipe.kraken-then-cloud-unsure-lines`): the pages with lines found, those lines, and every line's stated
    certainty in `sures` (None where it states none), so each run counts the lines under ITS OWN bar. Two queries for
    all the pages, not two a page; the caller runs this off the event loop."""
    from fichero_server.api.routes.document.segment_readings import counting_readings
    from fichero_server.models.segments import Segment

    rows = [x for x in db.query_in(Segment, "document_id", page_ids) if x.kind == "line" and x.deleted_at is None]
    read = counting_readings(db, rows)
    return {"pages": len(page_ids), "segmented": len({x.document_id for x in rows}), "lines": len(rows),
            "sures": [read[x.id].machine_confidence if x.id in read else None for x in rows]}


def _has_lines(db: Any, doc_id: str, model: str | None) -> bool:
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass

    for p in db.query(SegmentPass, document_id=doc_id):
        if p.deleted_at or (model is not None and p.model != model):
            continue
        if any(s.kind == "line" and not s.deleted_at for s in db.query(Segment, pass_id=p.id)):
            return True
    return False


def _has_regions(db: Any, doc_id: str, model: str | None, *, with_lines: bool) -> bool:
    """Regions the step's model found on the page (#5689: a re-Start found them again on all 92 pages, 25 minutes).
    `with_lines`: Kraken's regions come with the page's lines; regions found before they did leave the page
    to be segmented once more, so Read reads lines rather than segmenting the page itself."""
    from fichero_server.models import Artifact

    found = any(a.artifact_type == "regions" and (model is None or a.model == model)
                for a in db.query(Artifact, document_id=doc_id))
    return found and (not with_lines or _has_lines(db, doc_id, None))


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


def pages_with_readings(db: Any, pages: list[str]) -> set[str]:
    """The pages (that have no live lines) with a reading of any model: a saved transcription, or a reading written onto a
    line from one of the page's artifacts (`_has_page_reading` and `_has_line_readings` for model None, in two reads for all
    the pages, not three or four queries each; a page without live lines has no pass with lines, so `_has_lines` is no)."""
    from fichero_server.models import Artifact, ContentRepresentation

    have: set[str] = set()
    artifacts: dict[str, set[str]] = {}
    for a in db.query_in(Artifact, "document_id", pages):
        if a.artifact_type == "transcription":
            have.add(a.document_id)
        artifacts.setdefault(a.document_id, set()).add(a.id)
    for r in db.query_in(ContentRepresentation, "document_id", list(artifacts)):
        if r.segment_id and r.derived_from_artifact_id in artifacts.get(r.document_id, ()):
            have.add(r.document_id)
    return have


def lines_state(db: Any, doc_id: str, model: str | None = None) -> tuple[int, int, int]:
    """(lines found, lines with no reading and not looked at, lines looked at with no writing) on the page, from
    one scan of its segments and readings (#5758); `model`: only that reader's 'no writing' counts. A ruled or blank line the reader looked at is read: it has
    no reading to show, and reading it again would only cost the same answer."""
    from fichero_server.llm.working_lines import NO_WRITING_MARK
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment

    lines = [x for x in db.query(Segment, document_id=doc_id) if x.kind == "line" and x.deleted_at is None]
    if not lines:
        return 0, 0, 0
    read = {r.segment_id for r in db.query(ContentRepresentation, document_id=doc_id) if r.segment_id}
    blank = [x for x in lines if x.id not in read and isinstance((x.metadata or {}).get(NO_WRITING_MARK), dict)
             and (model is None or x.metadata[NO_WRITING_MARK].get("model") in (model, ""))]
    return len(lines), sum(1 for x in lines if x.id not in read) - len(blank), len(blank)


@dataclass
class PageLines:
    """One page's lines as a reader left them (what `lines_state` and `unread_reasons` give, for the Activity summary)."""

    found: int = 0
    unread: int = 0  # found lines with no reading that were not looked at
    blank: int = 0  # looked at, no writing (not counting `vision`)
    vision: int = 0  # Apple Vision returned nothing for the line twice: final, with its own reason (`source.read.vision-empty-line-says-so`)
    why: dict[str, int] = field(default_factory=dict)  # each unread line's reason, counted


def lines_by_page(db: Any, pages: list[str]) -> dict[str, PageLines]:
    """`lines_state` and `unread_reasons` for all these pages from TWO reads of the database (their lines, then the readings of the
    pages that have lines), not two per page: a run of 200 pages took the connection's transaction gate 2000 times a poll
    (`activity.summary.counts-in-two-queries`, #6001). Same numbers as the per-page helpers."""
    from fichero_server.llm.working_lines import NO_WRITING_MARK, VISION_NOTHING_TWICE
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment

    lines: dict[str, list[Any]] = {}
    for x in db.query_in(Segment, "document_id", pages):
        if x.kind == "line" and x.deleted_at is None:
            lines.setdefault(x.document_id, []).append(x)
    read: dict[str, set[str]] = {}
    for r in db.query_in(ContentRepresentation, "document_id", list(lines)):
        if r.segment_id:
            read.setdefault(r.document_id, set()).add(r.segment_id)
    out: dict[str, PageLines] = {}
    for page in pages:
        info = PageLines(found=len(lines.get(page, [])))
        done = read.get(page, set())
        for x in lines.get(page, []):
            if x.id in done:
                continue
            if isinstance((x.metadata or {}).get(NO_WRITING_MARK), dict):
                if (x.metadata or {}).get("unread_reason") == VISION_NOTHING_TWICE:
                    info.vision += 1  # only while the line has no reading: an explicit read-again that reads it wins
                else:
                    info.blank += 1
                continue
            info.unread += 1
            why = (x.metadata or {}).get("unread_reason") or NOT_ANSWERED
            info.why[why] = info.why.get(why, 0) + 1
        out[page] = info
    return out


def vision_gave_up(db: Any, doc_id: str) -> int:
    """The page's lines Apple Vision returned nothing for twice (`source.read.vision-empty-line-says-so`): final, counted
    read (looked at) but kept apart from the lines a reader found no writing on, as they carry a reason of their own. One
    page of `lines_by_page`; the run summary takes all its pages in the same two reads."""
    return lines_by_page(db, [doc_id])[doc_id].vision


def unread_on(db: Any, doc_id: str) -> int:
    """The page's found lines that have no reading and were not looked at (#5758)."""
    return lines_state(db, doc_id)[1]


NOTHING_FOR_PAGE = "every line came back empty: the reader may not suit this hand"
#: The reason a Kraken page with MOST lines empty gives its unread lines (`models.segments.segment_from_box`).
MOSTLY_NOTHING_FOR_PAGE = "most lines came back empty: the reader may not suit this hand"
#: The reasons that make a page a FAILED read: the reader gave no text for every line, or for most of them.
FAILED_READ_REASONS = frozenset({NOTHING_FOR_PAGE, MOSTLY_NOTHING_FOR_PAGE})
NOT_ANSWERED = "no reader has answered for the line: the read step did not reach it, or ended before it did"


def failed_reads(db: Any, pages: list[str]) -> list[tuple[str, str]]:
    """(page id, why) for each of these pages the reader failed: every unread line of it carries a failed-read reason
    (the reader gave no text for all of its lines, or for most). Such a page is a lost page of its step, not a read one."""
    out = []
    for page in pages:
        reasons = set(unread_reasons(db, page).values())
        if reasons and reasons <= FAILED_READ_REASONS:
            out.append((page, MOSTLY_NOTHING_FOR_PAGE if MOSTLY_NOTHING_FOR_PAGE in reasons else NOTHING_FOR_PAGE))
    return out


def unread_reasons(db: Any, doc_id: str) -> dict[str, str]:
    """Each found line with no reading and no 'looked, no writing' mark, with why it has none (#5758): the line
    record carries every reason a reader gave; a line no reader answered for says so."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment

    read = {r.segment_id for r in db.query(ContentRepresentation, document_id=doc_id) if r.segment_id}
    return {x.id: (x.metadata or {}).get("unread_reason") or NOT_ANSWERED for x in db.query(Segment, document_id=doc_id)
            if x.kind == "line" and x.deleted_at is None and x.id not in read
            and not isinstance((x.metadata or {}).get("read_no_writing"), dict)}


def _has_page_reading(db: Any, doc_id: str, model: str | None) -> bool:
    """A transcription the model saved (a read that came back empty saves none)."""
    from fichero_server.models import Artifact

    return any(a.artifact_type == "transcription" and (model is None or a.model == model)
               for a in db.query(Artifact, document_id=doc_id))


def _has_review(db: Any, doc_id: str, model: str | None, workflow_id: str | None = None) -> bool:
    """A reviewed transcription the step saved (the correcting step's output): by the step's model when it is
    known; else by the step's own workflow, never any model's review from any earlier run (#5616: the plan said
    "already done on 184 of 203" for a Review step whose runs had done none, counting reviews from runs outside the
    recipe)."""
    from fichero_server.models import Artifact

    return any(a.artifact_type == REVIEWED and _by_the_step(a, model, workflow_id)
               for a in db.query(Artifact, document_id=doc_id))


def _by_the_step(artifact: Any, model: str | None, workflow_id: str | None) -> bool:
    if model is not None:
        return artifact.model == model
    return workflow_id is None or artifact.workflow_id == workflow_id


def effective_model(db: Any, card: dict[str, Any]) -> str | None:
    """The model a step's run reads with (#5616): its own choice (`model_override`, a recipe step's model), else its
    workflow's model; None when the workflow names none (its nodes then take the engine's default)."""
    if card.get("model_override"):
        return str(card["model_override"])
    if not card.get("workflow_id"):
        return None
    from fichero_server.models import Workflow

    workflow = db.get(Workflow, card["workflow_id"])
    return (workflow.model or None) if workflow is not None else None


def pages_a_run_did(db: Any, job: str) -> set[str]:
    """The pages a finished recipe run's step of this job ran on and ended well (`runner.RAN_ON_JOBS`, #5706)."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.recipes.runner import KIND

    out: set[str] = set()
    for row in jobs.find_jobs(db, kinds=[KIND], states=["done", "failed", "cancelled"]):
        found = jobs.read_job(db, row["id"]) or {}
        detail = json.loads(found.get("detail") or "{}")
        for card, step in zip(detail.get("runs") or [], detail.get("steps") or []):
            if card.get("job") == job:
                out.update(step.get("ran_on") or [])
    return out


def pages_with_names(db: Any) -> set[str]:
    """Every page some entity was found on (`KnowledgeEntity.source_document_ids`): the pages the names
    step has been over."""
    from fichero_server.models import KnowledgeEntity

    return {doc_id for e in db.query(KnowledgeEntity) for doc_id in (e.source_document_ids or [])}


def is_done(db: Any, card: dict[str, Any], doc_id: str) -> bool | None:
    """True when the page already has this card's output; None when the card cannot tell."""
    job = card.get("job")
    if job == "split-pages":
        return bool(_children(db, doc_id))
    if job == "find-regions":
        return _has_regions(db, doc_id, card.get("model"), with_lines=card.get("provider") == "kraken")
    if job == "find-lines":
        return _has_lines(db, doc_id, None)
    if job == "read-a-line":
        # Lines found are not lines read (#5758): a page with any line left without a reading is read again.
        model = card.get("model_override")
        found, unread, blank = lines_state(db, doc_id, model)
        return found > 0 and not unread and (blank == found or _has_line_readings(db, doc_id, model))
    if job == "read-a-page":
        return _has_page_reading(db, doc_id, card.get("model_override"))
    if job == "prepare-the-image":
        from fichero_server.recipes.prepare import prepared

        return prepared(db, doc_id) is not None or doc_id in pages_a_run_did(db, job)
    if job == "correct":
        return _has_review(db, doc_id, effective_model(db, card), card.get("workflow_id"))
    if job == "find-names-tag-words":
        return doc_id in pages_with_names(db) or doc_id in pages_a_run_did(db, job)
    if job == "split-into-entries":  # a page a stopped or earlier run split keeps its entries; the model is not asked again
        return any(c.node_kind == "entry" for c in _children(db, doc_id))
    return None


def split_done(db: Any, card: dict[str, Any], pages: list[str]) -> tuple[list[str], int | None]:
    """(the pages still to do, how many are done; None when the card cannot tell)."""
    if card.get("job") not in KNOWS_DONE:
        return pages, None
    if card.get("job") == "find-names-tag-words":  # one read of the entities, not one per page
        named = pages_with_names(db) | pages_a_run_did(db, "find-names-tag-words")
        todo = [p for p in pages if p not in named]
        return todo, len(pages) - len(todo)
    if card.get("job") == "prepare-the-image":  # the runs read once, not once per page
        ran = pages_a_run_did(db, "prepare-the-image")
        from fichero_server.recipes.prepare import prepared

        todo = [p for p in pages if p not in ran and prepared(db, p) is None]
        return todo, len(pages) - len(todo)
    todo = [p for p in pages if not is_done(db, card, p)]
    return todo, len(pages) - len(todo)


def _note(done: int | None, of: int, unit: str) -> str:
    """What Start will do on this run's pages, in words (#5616): never "done on 0 ...; runs on the rest"."""
    if done is None:
        return f"cannot tell what is done; runs on every page ({of})"
    if done == 0:
        return f"runs on all {of} {unit}"
    if done >= of:
        return f"already done on all {of} {unit}; nothing to run"
    return f"already done on {done} of {of} {unit}; runs on the other {of - done}"


def annotate(db: Any, plan: dict[str, Any], unfinished: dict[str, dict[str, str]] | None = None,
             within: set[str] | None = None, redo: set[str] | None = None) -> dict[str, Any]:
    """Each run in the Start plan with `done`, `of` and a `note`, as things stand now; a run whose steps the last
    run did not finish (`unfinished`, `runner.unfinished_steps`) says so with `last_run` and `last_why`, and
    that Start runs it again (#5498). `within`: only these documents (a folder's)."""
    for card in plan.get("runs", []):
        pages = [p for p in pages_for(db, card, None) if within is None or p in within]
        _todo, done = split_done(db, card, pages)
        card["done"], card["of"] = done, len(pages)
        unit = "photographs" if card.get("job") == "split-pages" else "pages"
        card["note"] = _note(done, len(pages), unit)
        if redo and redo.intersection(card["steps"]):  # the run was asked to do it again (#5689)
            card["note"] = f"runs again on all {len(pages)} {unit}, as asked (redo)"
        last = next(((sid, (unfinished or {})[sid]) for sid in card["steps"] if sid in (unfinished or {})), None)
        if last is not None:
            sid, outcome = last
            card["last_run"], card["last_why"] = outcome["state"], outcome["why"]
            card["note"] = f"{outcome['state']} last time (step {sid}: {outcome['why']}); runs again: {card['note']}"
    return plan
