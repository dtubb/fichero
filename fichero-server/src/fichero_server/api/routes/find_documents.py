"""Find the Documents, from the API (`finddocs.*`, specs/source/finding-documents.md, #5550).

Start a run on folders or a selection of pages (`finddocs.run`, one background job), follow it, read the
proposals it stored, and accept or reject them (`finddocs.accept`, `finddocs.reject`: audited, undone by one
undo through `/api/actions/audit/{id}/undo`). The MCP and the command line get these from the contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import (
    get_library_database,
    get_library_database_for_write,
    optional_library_path,
    readable_documents,
)
from fichero_server.db import Database
from fichero_server.finddocs import accept as _accept  # noqa: F401  (registers finddocs.accept, .reject)
from fichero_server.finddocs import store as finddocs_store
from fichero_server.models.found_documents import (
    DocumentsProposal,
    FindDocumentsAcceptRequest,
    FindDocumentsAcceptResult,
    FindDocumentsRejectRequest,
    FindDocumentsRequest,
    FindDocumentsRun,
)

router = APIRouter(prefix="/find-documents")


def _job():
    """The job module, loaded on first use: the proposer and its cue table stay out of engine start."""
    from fichero_server.finddocs import job

    return job


class DocumentsProposalList(BaseModel):
    items: list[DocumentsProposal]
    count: int
    withheld: int = 0


@action("finddocs.run", FindDocumentsRequest, domains=["job"], undoable=False)
def _action_run(db: Database, params: FindDocumentsRequest, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    _job().register_job_kinds()
    if not ctx.is_bootstrap:
        # The action layer checked the ids named; the run reads every page under them (fail closed).
        from fichero_server.security import authz

        pages = [p.id for pages in _job().scopes(db, params.scope_ids).values() for p in pages]
        authz.assert_can_read_every(ctx.actor, ctx.library_path, pages, bootstrap=False)
    job_id = _job().start(db, params, started_by=ctx.actor or "owner")
    return {"job_id": job_id}, ChangeSpec(domains=["job"], target_ids=[job_id],
                                          after={"job_id": job_id, "kind": _job().KIND}, emit_type="job.created")


@router.post("/runs", response_model=FindDocumentsRun, summary="Find the documents in folders or a selection of pages")
async def start_find_documents(
    request: FindDocumentsRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsRun:
    """Queue one background job: each folder's loose pages are paired into leaves, and documents, their kinds
    and their groups are proposed from the text already read, with evidence and a confidence; blank versos and
    second shots are reported, not made documents. The proposals are stored; nothing in the source changes.
    As the run ends, the documents at least `accept_above` sure are accepted (left out: 0.95, the project's
    default); the rest wait for a person. `accept_above: null` leaves them all for a person."""
    try:
        job_id = registry.invoke(db, "finddocs.run", request.model_dump(), ctx).result["job_id"]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FindDocumentsRun(**_job().status(db, job_id))


@router.get("/runs/{job_id}", response_model=FindDocumentsRun, summary="A Find the Documents run and its proposals")
async def find_documents_run(job_id: str, db: Database = Depends(get_library_database)) -> FindDocumentsRun:
    try:
        return FindDocumentsRun(**_job().status(db, job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _readable(request: Request, library: str | None, proposals: list[DocumentsProposal]) -> list[DocumentsProposal]:
    anchors = [p.folder_id or p.page_ids[0] for p in proposals if p.folder_id or p.page_ids]
    readable = set(readable_documents(request, library, anchors))
    return [p for p in proposals if (p.folder_id or (p.page_ids or [None])[0]) in readable]


@router.get("/proposals", response_model=DocumentsProposalList, summary="Stored Find the Documents proposals")
async def list_find_documents_proposals(
    request: Request,
    folder_id: str | None = Query(None, description="Only this folder's proposals."),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> DocumentsProposalList:
    """Newest first; a proposal on a folder this caller may not read is left out and counted."""
    found = finddocs_store.proposals(db, folder_id)
    kept = _readable(request, x_fichero_library_path, found)
    return DocumentsProposalList(items=kept, count=len(kept), withheld=len(found) - len(kept))


@router.get("/proposals/{proposal_id}", response_model=DocumentsProposal, summary="One Find the Documents proposal")
async def get_find_documents_proposal(
    proposal_id: str,
    request: Request,
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> DocumentsProposal:
    try:
        proposal = finddocs_store.read(db, proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not _readable(request, x_fichero_library_path, [proposal]):
        raise HTTPException(status_code=404, detail=f"no Find the Documents proposal {proposal_id}")
    return proposal


@router.post("/proposals/{proposal_id}/accept", response_model=FindDocumentsAcceptResult,
             summary="Accept proposed documents: group nodes with their prototypes, the canvas laid out")
async def accept_find_documents_proposal(
    proposal_id: str,
    body: FindDocumentsAcceptRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsAcceptResult:
    """Accept all the proposed documents, the ones named, or those at least `min_confidence` sure: each becomes a
    group node of its pages (a one-page document stays its page) with its proposed prototype (made if the project
    has none of that name); a proposed group whose documents are all accepted becomes a group of them; the
    folder's canvas is laid out in their order. One audited action: undoing it (its `audit_id`) restores all."""
    try:
        result = registry.invoke(db, "finddocs.accept", {"proposal_id": proposal_id, **body.model_dump()}, ctx)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FindDocumentsAcceptResult(proposal=finddocs_store.read(db, proposal_id), audit_id=result.audit_id,
                                     **result.result)


@router.post("/proposals/{proposal_id}/reject", response_model=DocumentsProposal,
             summary="Reject proposed documents (kept, for the project's own model to learn from)")
async def reject_find_documents_proposal(
    proposal_id: str,
    body: FindDocumentsRejectRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> DocumentsProposal:
    try:
        registry.invoke(db, "finddocs.reject", {"proposal_id": proposal_id, **body.model_dump()}, ctx)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return finddocs_store.read(db, proposal_id)
