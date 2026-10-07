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
from fichero_server.models.found_documents import DocumentsProposal, FindDocumentsRequest

KIND = "find-documents-in-a-folder"
#: The artifact kind a proposal is stored as, and the method that made it.
ARTIFACT_TYPE = "grouping"
PROVIDER = "fichero"
MODEL = "find-documents/rules-1"
#: The side of the thumbnail the ink and the look are measured on.
THUMB = 96


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


def _look(path: str | None) -> tuple[float | None, int | None]:
    """(ink, average hash) of the image's thumbnail; (None, None) when there is no image to look at."""
    if not path or not Path(path).is_file():
        return None, None
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as image:
            image.draft("L", (THUMB * 4, THUMB * 4))
            gray = ImageOps.grayscale(image)
            gray.thumbnail((THUMB, THUMB))
            pixels = list(gray.getdata())
            small = list(gray.resize((8, 8)).getdata())
    except OSError:
        return None, None
    # Ink is what is much darker than the paper (its median): bleed-through on a blank verso is not.
    paper = sorted(pixels)[len(pixels) // 2]
    ink = sum(1 for p in pixels if p < paper - 50) / len(pixels)
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


def page_inputs(db: Any, pages: list[Any]) -> list[PageInput]:
    names = _names(db, [p.id for p in pages])
    out = []
    for page in pages:
        ink, image_hash = _look(page.path)
        out.append(PageInput(id=page.id, text=_text(db, page), ink=ink, image_hash=image_hash,
                             names=names.get(page.id, [])))
    return out


def store(db: Any, proposal: DocumentsProposal, anchor_id: str) -> DocumentsProposal:
    """Keep the proposal as a `grouping` artifact on its folder (or, for pages at the project's root, on its
    first page): a hypothesis beside the source, never a change to it."""
    from fichero_server.core.timeutil import utc_now
    from fichero_server.models import Artifact

    artifact = Artifact(document_id=anchor_id, artifact_type=ARTIFACT_TYPE, provider=PROVIDER, model=MODEL,
                        run_id=proposal.job_id,
                        confidence=min((d.confidence for d in proposal.documents), default=None))
    proposal = proposal.model_copy(update={"id": artifact.id, "created_at": utc_now().isoformat()})
    artifact.data = proposal.model_dump(mode="json")
    db.save(artifact)
    return proposal


def read(db: Any, proposal_id: str) -> DocumentsProposal:
    from fichero_server.models import Artifact

    artifact = db.get(Artifact, proposal_id)
    if artifact is None or artifact.artifact_type != ARTIFACT_TYPE or artifact.model != MODEL:
        raise LookupError(f"no Find the Documents proposal {proposal_id}")
    return DocumentsProposal.model_validate(artifact.data)


def write(db: Any, proposal: DocumentsProposal) -> None:
    from fichero_server.models import Artifact

    artifact = db.get(Artifact, proposal.id)
    if artifact is None:
        raise LookupError(f"no Find the Documents proposal {proposal.id}")
    artifact.data = proposal.model_dump(mode="json")
    db.save(artifact)


def proposals(db: Any, folder_id: str | None = None) -> list[DocumentsProposal]:
    """Every stored proposal (of one folder), newest first."""
    from fichero_server.models import Artifact

    rows = [a for a in db.query(Artifact, artifact_type=ARTIFACT_TYPE) if a.model == MODEL]
    found = [DocumentsProposal.model_validate(a.data) for a in rows]
    if folder_id is not None:
        found = [p for p in found if p.folder_id == folder_id]
    return sorted(found, key=lambda p: (p.created_at or "", p.id), reverse=True)


def find_documents(db: Any, scope_ids: list[str], *, job_id: str | None = None) -> list[DocumentsProposal]:
    """Propose and store, one proposal per folder in scope; a folder with no loose pages proposes nothing."""
    stored = []
    for folder_id, pages in scopes(db, scope_ids).items():
        if not pages:
            continue
        proposal = propose(page_inputs(db, pages), folder_id=folder_id, job_id=job_id)
        stored.append(store(db, proposal, folder_id or pages[0].id))
    return stored


def start(db: Any, request: FindDocumentsRequest, *, started_by: str, watched: bool = True) -> str:
    scopes(db, request.scope_ids)  # an unknown id is refused now, not when the job runs
    return jobs.enqueue(db, KIND, f"{KIND}:{uuid.uuid4()}", started_by=started_by, watched=watched,
                        detail=json.dumps({"request": request.model_dump()}))


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.finddocs import accept  # noqa: F401  (registers finddocs.accept)

    job_id = jobs.job_id_for(db, KIND, subject)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    request = FindDocumentsRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Finding the documents")
    found = find_documents(db, request.scope_ids, job_id=job_id)
    accepted = 0
    if request.accept_above is not None:
        ctx = ActionContext(actor=row["started_by"] or "owner", run_id=job_id, library_path=str(Path(db.path).parent))
        for proposal in found:
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
                           name="Find the documents")
