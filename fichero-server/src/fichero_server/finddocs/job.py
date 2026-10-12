"""Find the Documents as one background job (`finddocs.job.any-box`, #5550).

On any folder or selection of pages: each folder's loose pages (a photograph, or the pages cut from one) in
the folder's order are read as they stand (the page's text, else its best reading; the thumbnail's ink and
look; the names the knowledge graph found on it), proposed (`propose.propose`), and the proposal stored as a
hypothesis: a `grouping` artifact on the folder, the artifact kind that holds which pages belong together
until a person approves. Nothing in the source changes. A run started with `accept_above` (a recipe step's
setting, `recipes/assemble.py`) then accepts the documents at least that confident, through the one audited
action (`finddocs.accept`), as the job's own run.

One row in Activity (kind `find-documents-in-a-folder`, the recipe job's own name), on the images lane: it
reads thumbnails and text, never a model.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs
from fichero_server.finddocs.propose import PageInput, propose
from fichero_server.finddocs.store import store
from fichero_server.models.found_documents import DocumentsProposal, FindDocumentsRequest

KIND = "find-documents-in-a-folder"
#: The side of the thumbnail the ink and the look are measured on: large enough that a pen stroke is a pixel or
#: two, not blurred into the paper (#5676: at 96 px a faint written page measured below a blank one).
THUMB = 384
#: Ink is a pixel this much darker than the paper around it (faded ink, 55 below its paper, is still ink;
#: bleed-through, 30 or so, is not) ...
INK_BELOW_PAPER = 40
#: ... where the paper around it is the page with every dark mark thinner than this (in pixels) closed over: a
#: stroke is filled with the paper it sits on, while a broad ground around the sheet (black or grey) and its edge stay.
INK_STROKE_WIDTH = 9


def _kind(doc: Any) -> str:
    return str(getattr(doc.doc_type, "value", doc.doc_type))


def _file_type(doc: Any) -> str:
    return str(getattr(doc.file_type, "value", doc.file_type) or "")


def _ordered(docs: list[Any]) -> list[Any]:
    return sorted(docs, key=lambda d: (d.sort_order is None, d.sort_order or 0, d.name or "", d.id))


def _children(db: Any, parent_id: str | None) -> list[Any]:
    from fichero_server.models import Document

    return _ordered([d for d in db.query(Document, parent_id=parent_id) if not d.deleted_at])


def loose_pages(db: Any, folder_id: str | None) -> list[Any]:
    """The folder's loose pages, in its order: each photograph, or the pages cut from it. A group (a document
    already made) and a sub-folder are not loose pages; neither is a PDF's page (it has its document)."""
    out = []
    for child in _children(db, folder_id):
        if _kind(child) != "file" or _file_type(child) not in ("image", ""):
            continue
        cut = [c for c in _children(db, child.id) if _kind(c) == "chunk"]
        out += cut or [child]
    return out


def scopes(db: Any, scope_ids: list[str]) -> dict[str | None, list[Any]]:
    """{folder id: its pages in order} for a mix of folders and selected pages."""
    from fichero_server.models import Document

    found: dict[str | None, list[Any]] = {}
    chosen: dict[str | None, set[str]] = {}
    for doc_id in scope_ids:
        doc = db.get(Document, doc_id)
        if doc is None or doc.deleted_at:
            raise LookupError(f"no document {doc_id}")
        if _kind(doc) == "folder":
            found[doc.id] = loose_pages(db, doc.id)
            continue
        parent = db.get(Document, doc.parent_id) if doc.parent_id else None
        if parent is not None and _kind(parent) == "file":  # a page cut from a photograph: its folder is above
            parent = db.get(Document, parent.parent_id) if parent.parent_id else None
        folder_id = parent.id if parent is not None else None
        chosen.setdefault(folder_id, set()).add(doc.id)
    for folder_id, ids in chosen.items():
        if folder_id in found:
            continue
        found[folder_id] = [p for p in loose_pages(db, folder_id) if p.id in ids]
    return found


def _text(db: Any, doc: Any) -> str:
    if (doc.page_content or "").strip():
        return doc.page_content
    from fichero_server.checking.tie_text import page_reading

    reading = page_reading(db, doc.id)
    return reading.content if reading is not None else ""


def _image_of(db: Any, page: Any) -> str:
    """The page's image as every step finds it (`source.pages.image-found-wherever-kept`): a copied page's stored
    path is inside the package."""
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    return _resolve_abs_path(page, str(Path(db.path).parent))


def _look(path: str | None) -> tuple[float | None, int | None]:
    """(ink, average hash) of the image's thumbnail; (None, None) when there is no image to look at."""
    if not path or not Path(path).is_file():
        return None, None
    from PIL import Image, ImageOps

    from PIL import ImageChops, ImageFilter

    try:
        with Image.open(path) as image:
            image.draft("L", (THUMB * 2, THUMB * 2))
            gray = ImageOps.grayscale(image)
            gray.thumbnail((THUMB, THUMB))
            small = list(gray.resize((8, 8)).tobytes())
    except OSError:
        return None, None
    # Ink is what is much darker than the paper around it (#5676): not the paper's median, which a black or grey
    # ground around the sheet becomes (a written page on black read as 0% ink, a blank sheet on grey as 6%).
    # Bleed-through on a blank verso is lighter than INK_BELOW_PAPER, and is not ink.
    paper = gray.filter(ImageFilter.MaxFilter(INK_STROKE_WIDTH)).filter(ImageFilter.MinFilter(INK_STROKE_WIDTH))
    darker = ImageChops.subtract(paper, gray).histogram()
    ink = sum(darker[INK_BELOW_PAPER + 1:]) / (gray.size[0] * gray.size[1])
    mean = sum(small) / len(small)
    image_hash = sum(1 << i for i, p in enumerate(small) if p > mean)
    return ink, image_hash


def _names(db: Any, page_ids: list[str]) -> dict[str, list[str]]:
    """The people and organisations the knowledge graph found on each page."""
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity

    out: dict[str, list[str]] = {}
    wanted = set(page_ids)
    for entity_id in db.knowledge_entity_ids_scoped_to_documents(wanted):
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is None or entity.merged_into_id or entity.entity_type not in (EntityType.person,
                                                                                 EntityType.organization):
            continue
        for doc_id in set(entity.source_document_ids) & wanted:
            out.setdefault(doc_id, []).append(entity.canonical_name)
    return out


#: Before reading, a page this empty of ink is blank and is not read (#5579). Lower than the proposer's blank
#: (`propose.BLANK_INK`): a faint page is read rather than lost unread. Measured on CACIQUES_INDIOS,17,D.5 (#5676):
#: its blank placeholder sheet 0.007, its faintest written page 0.0175.
UNREAD_BELOW_INK = 0.011


def blank_versos(db: Any, page_ids: list[str]) -> set[str]:
    """Of `page_ids`, the pages blank as their images show them before anything is read (#5579): a page with almost
    no ink, wherever it falls in its folder (#5676: its first page, a blank after a blank, the back of a leaf). A
    proposal: sorting marks it `blank`, and a person who gives it another kind has it read."""
    from fichero_server.models import Document

    wanted = set(page_ids)
    folders: set[str | None] = set()
    for page_id in page_ids:
        doc = db.get(Document, page_id)
        if doc is not None and _kind(doc) == "file" and _file_type(doc) == "image":
            folders.add(doc.parent_id)
    out: set[str] = set()
    for folder_id in folders:
        if folder_id is not None and (folder := db.get(Document, folder_id)) is not None and _kind(folder) != "folder":
            continue
        for page in loose_pages(db, folder_id):
            if page.id in wanted and (ink := _look(_image_of(db, page))[0]) is not None and ink < UNREAD_BELOW_INK:
                out.add(page.id)
    return out


def _stop_point(job_id: str | None) -> None:
    """Stop on the run's row (or on the recipe run it is a step of, #5609) takes effect here: before the next folder
    or page. The folders already finished keep their proposals (a hypothesis each; nothing in the source changed)."""
    from fichero_server.execution.cancellation import cancellation_requested

    if cancellation_requested(job_id):
        raise jobs.JobCancelled("Stopped by you")


def page_inputs(db: Any, pages: list[Any], *, job_id: str | None = None) -> list[PageInput]:
    names = _names(db, [p.id for p in pages])
    out = []
    for page in pages:
        _stop_point(job_id)
        ink, image_hash = _look(_image_of(db, page))
        out.append(PageInput(id=page.id, text=_text(db, page), ink=ink, image_hash=image_hash,
                             names=names.get(page.id, [])))
    return out


def find_documents(db: Any, scope_ids: list[str], *, job_id: str | None = None) -> list[DocumentsProposal]:
    """Propose and store, one proposal per folder in scope; a folder with no loose pages proposes nothing."""
    stored = []
    for folder_id, pages in scopes(db, scope_ids).items():
        _stop_point(job_id)
        if not pages:
            continue
        proposal = propose(page_inputs(db, pages, job_id=job_id), folder_id=folder_id, job_id=job_id)
        stored.append(store(db, proposal, folder_id or pages[0].id))
    return stored


def start(db: Any, request: FindDocumentsRequest, *, started_by: str, watched: bool = True) -> str:
    scopes(db, request.scope_ids)  # an unknown id is refused now, not when the job runs
    return jobs.enqueue(db, KIND, f"{KIND}:{uuid.uuid4()}", started_by=started_by, watched=watched,
                        detail=json.dumps({"request": request.model_dump()}))


def request_cancel(db: Any, job_id: str) -> str:
    """Stop on the run's row (#5609): a waiting or paused run ends cancelled now; a running one is asked to stop and
    stops before its next folder or page (`_stop_point`), its row saying it is stopping until then."""
    from fichero_server.execution.cancellation import request_cancellation

    state = jobs._job_row(db, job_id)[1]
    if state in ("waiting", "paused"):
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state != "running":
        return state
    request_cancellation(job_id)
    jobs.say_stopping(db, job_id)
    return "stopping"


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.execution.cancellation import clear_cancellation

    job_id = jobs.job_id_for(db, KIND, subject)
    try:
        return _run(db, job_id)
    finally:
        clear_cancellation(job_id)


def _run(db: Any, job_id: str) -> dict[str, Any]:
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.finddocs import accept  # noqa: F401  (registers finddocs.accept)

    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    request = FindDocumentsRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Finding the documents")
    found = find_documents(db, request.scope_ids, job_id=job_id)
    accepted = 0
    if request.accept_above is not None:
        ctx = ActionContext(actor=row["started_by"] or "owner", run_id=job_id, library_path=str(Path(db.path).parent))
        for proposal in found:
            _stop_point(job_id)
            if any(d.confidence >= request.accept_above for d in proposal.documents):
                result = registry.invoke(db, "finddocs.accept", {"proposal_id": proposal.id,
                                                                 "min_confidence": request.accept_above}, ctx)
                accepted += len(result.result["accepted"])
    documents = sum(len(p.documents) for p in found)
    findings = sum(len(p.findings) for p in found)
    words = (f"{documents} documents proposed in {len(found)} folders, {findings} pages reported"
             + (f"; {accepted} accepted (at least {request.accept_above:.0%} sure)" if request.accept_above is not None
                else "; waiting for you to accept them"))
    detail["result"] = {"proposal_ids": [p.id for p in found], "documents": documents, "accepted": accepted}
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    return detail["result"]


def status(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no Find the Documents run {job_id}")
    detail = json.loads(row["detail"] or "{}")
    return {"job_id": job_id, "state": row["state"], "reason": row["reason"],
            "proposal_ids": (detail.get("result") or {}).get("proposal_ids", [])}


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="images",
                           name="Find the documents", cancel=request_cancel)
