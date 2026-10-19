"""Find the Documents, from the API (`finddocs.*`, specs/source/finding-documents.md, #5550).

Start a run on folders or a selection of pages (`finddocs.run`, one background job), follow it, read the
proposals it stored, score them against what a person set (`finddocs.score`), adjust them (`finddocs.split`, `finddocs.join`, `finddocs.move_page`), and accept or reject
them (`finddocs.accept`, `finddocs.reject`): each audited, undone by one undo through
`/api/actions/audit/{id}/undo`. The MCP and the command line get these from the contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry, started_by_for
from fichero_server.api.auth import action_context
from fichero_server.api.main import (
    get_library_database,
    get_library_database_for_write,
    optional_library_path,
    readable_documents,
)
from fichero_server.db import Database
from fichero_server.finddocs import accept as _accept  # noqa: F401  (registers finddocs.accept, .reject)
from fichero_server.finddocs import adjust as finddocs_adjust  # registers finddocs.split, .join, .move_page
from fichero_server.finddocs import score as finddocs_score  # registers finddocs.score
from fichero_server.finddocs import store as finddocs_store
from fichero_server.models.found_documents import (
    DocumentsProposal,
    FindDocumentsAcceptRequest,
    FindDocumentsAcceptResult,
    FindDocumentsRejectResult,
    FindDocumentsAdjustResult,
    FindDocumentsJoinRequest,
    FindDocumentsMovePageRequest,
    FindDocumentsRejectRequest,
    FindDocumentsScore,
    FindDocumentsScoreRequest,
    FindDocumentsScoreResult,
    FindDocumentsScores,
    FindDocumentsSplitRequest,
    FindDocumentsRequest,
    FindDocumentsRun,
)
from fichero_server.api.errors import ErrorDetail as _RefusalBody

router = APIRouter(prefix="/find-documents")

#: An agent's tool reads a proposal lean (`openapi.mcp.answers-fit-an-agent`, `openapi.mcp.onboarding-journey`): its
#: documents with their reasons, without every join's signals, which are most of its weight (an accept on a
#: 4-document box answered 15 KB; a 92-page box's proposal is 39 KB). The app, calling with no parameters, keeps them.
AGENT_SUMMARY = {"x-fichero-agent-defaults": {"summary": True}}
_SUMMARY = Query(False, description="a lean answer for an agent: the proposal's documents (each with its pages "
                                    "and reasons), groups and findings, without each join's signals, the pages "
                                    "looked at or the labelled examples (`joins`, `page_ids`, `examples` empty). "
                                    "The whole proposal is one GET away.")


def _lean(proposal: DocumentsProposal, summary: bool) -> DocumentsProposal:
    return proposal.model_copy(update={"joins": [], "page_ids": [], "examples": []}) if summary else proposal


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
    job_id = _job().start(db, params, started_by=started_by_for(ctx))
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


@router.get("/proposals", response_model=DocumentsProposalList, summary="Stored Find the Documents proposals",
            openapi_extra=AGENT_SUMMARY)
async def list_find_documents_proposals(
    request: Request,
    summary: bool = _SUMMARY,
    folder_id: str | None = Query(None, description="Only this folder's proposals."),
    include_superseded: bool = Query(False, description="Also the proposals a later run on the same pages "
                                                        "replaced (kept for what their answers teach)."),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> DocumentsProposalList:
    """Newest first; a proposal on a folder this caller may not read is left out and counted. A proposal a later
    run replaced (`state` "superseded") is left out unless asked for, so the same pages are never listed twice."""
    found = finddocs_store.proposals(db, folder_id, superseded=include_superseded)
    kept = _readable(request, x_fichero_library_path, found)
    return DocumentsProposalList(items=[_lean(p, summary) for p in kept], count=len(kept),
                                 withheld=len(found) - len(kept))


@router.get("/proposals/{proposal_id}", response_model=DocumentsProposal, summary="One Find the Documents proposal",
            openapi_extra=AGENT_SUMMARY)
async def get_find_documents_proposal(
    proposal_id: str,
    request: Request,
    summary: bool = _SUMMARY,
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> DocumentsProposal:
    try:
        proposal = finddocs_store.read(db, proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not _readable(request, x_fichero_library_path, [proposal]):
        raise HTTPException(status_code=404, detail=f"no Find the Documents proposal {proposal_id}")
    return _lean(proposal, summary)


@router.post("/proposals/{proposal_id}/accept", response_model=FindDocumentsAcceptResult,
             summary="Accept proposed documents: group nodes with their prototypes, the canvas laid out",
             responses={409: {"model": _RefusalBody, "description": "The proposal is out of date: a later run replaced it, or a "
                                             "document's pages were grouped, moved or deleted since."}},
             openapi_extra=AGENT_SUMMARY)
async def accept_find_documents_proposal(
    proposal_id: str,
    body: FindDocumentsAcceptRequest,
    summary: bool = _SUMMARY,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsAcceptResult:
    """Accept all the proposed documents, the ones named, or those at least `min_confidence` sure: each becomes a
    group node of its pages (a one-page document stays its page) with its proposed prototype (made if the project
    has none of that name); a proposed group whose documents are all accepted becomes a group of them; the
    folder's canvas is laid out in their order. One audited action: undoing it (its `audit_id`) restores all.
    Each kind records who chose it: the run, accepted by this caller. A proposal a later run replaced, or a
    document whose pages are no longer the folder's loose pages, is refused (409) and nothing changes."""
    try:
        result = registry.invoke(db, "finddocs.accept", {"proposal_id": proposal_id, **body.model_dump()}, ctx)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except finddocs_store.ProposalOutOfDate as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FindDocumentsAcceptResult(proposal=_lean(finddocs_store.read(db, proposal_id), summary),
                                     audit_id=result.audit_id, **result.result)


@router.post("/proposals/{proposal_id}/reject", response_model=FindDocumentsRejectResult,
             summary="Reject proposed documents (kept, for the project's own model to learn from)",
             openapi_extra=AGENT_SUMMARY)
async def reject_find_documents_proposal(
    proposal_id: str,
    body: FindDocumentsRejectRequest,
    summary: bool = _SUMMARY,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsRejectResult:
    """Reject proposed documents: kept, marked rejected, for the project's own model to learn from. One audited
    action: undoing it (its `audit_id`) puts back only the documents it rejected (#5698)."""
    try:
        result = registry.invoke(db, "finddocs.reject", {"proposal_id": proposal_id, **body.model_dump()}, ctx)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FindDocumentsRejectResult(**_lean(finddocs_store.read(db, proposal_id), summary).model_dump(),
                                     audit_id=result.audit_id)


_ADJUST_RESPONSES = {
    409: {"model": _RefusalBody, "description": "The proposal is out of date: a later run replaced it, the document is already accepted "
                         "or rejected, or its pages were grouped, moved or deleted since."},
    422: {"description": "No such document or page in the proposal, or the adjustment cannot be made."},
}


def _adjust(db: Database, name: str, proposal_id: str, body: BaseModel, ctx: ActionContext,
            summary: bool = False) -> FindDocumentsAdjustResult:
    try:
        result = registry.invoke(db, name, {"proposal_id": proposal_id, **body.model_dump()}, ctx)
    except finddocs_adjust.AdjustmentNotPossible as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except finddocs_store.ProposalOutOfDate as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FindDocumentsAdjustResult(proposal=_lean(finddocs_store.read(db, proposal_id), summary),
                                     audit_id=result.audit_id, examples=result.result["examples"])


@router.post("/proposals/{proposal_id}/split", response_model=FindDocumentsAdjustResult,
             summary="Split a proposed document at a page (an adjustment the project learns from)",
             responses=_ADJUST_RESPONSES, openapi_extra=AGENT_SUMMARY)
async def split_find_documents_document(
    proposal_id: str,
    body: FindDocumentsSplitRequest,
    summary: bool = _SUMMARY,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsAdjustResult:
    """The named page starts a new document: the proposal's documents are renumbered, both halves are set by
    this caller, and the proposal keeps the example "a document starts here" between the two pages. Nothing in
    the library changes; one undo of `audit_id` restores the proposal exactly."""
    return _adjust(db, "finddocs.split", proposal_id, body, ctx, summary)


@router.post("/proposals/{proposal_id}/join", response_model=FindDocumentsAdjustResult,
             summary="Join a proposed document to the next (an adjustment the project learns from)",
             responses=_ADJUST_RESPONSES, openapi_extra=AGENT_SUMMARY)
async def join_find_documents_documents(
    proposal_id: str,
    body: FindDocumentsJoinRequest,
    summary: bool = _SUMMARY,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsAdjustResult:
    """The document and the one after it become one, set by this caller, and the proposal keeps the example "one
    document" across the join. Nothing in the library changes; one undo of `audit_id` restores the proposal."""
    return _adjust(db, "finddocs.join", proposal_id, body, ctx, summary)


@router.post("/proposals/{proposal_id}/move-page", response_model=FindDocumentsAdjustResult,
             summary="Move a proposed document's first or last page to its neighbour (an adjustment the project "
                     "learns from)",
             responses=_ADJUST_RESPONSES, openapi_extra=AGENT_SUMMARY)
async def move_find_documents_page(
    proposal_id: str,
    body: FindDocumentsMovePageRequest,
    summary: bool = _SUMMARY,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsAdjustResult:
    """`to: previous` moves the document's first page to the end of the document before it; `to: next` moves its
    last page to the start of the one after it. Both documents are set by this caller; the proposal keeps two
    examples: one document across the page's new join, a new document across the one it left. Nothing in the
    library changes; one undo of `audit_id` restores the proposal."""
    return _adjust(db, "finddocs.move_page", proposal_id, body, ctx, summary)


def _suggestion(db: Database) -> dict:
    levels = finddocs_score.pooled(db)
    return {"levels": levels, "suggested_accept_above": finddocs_score.suggest(levels),
            "min_joins": finddocs_score.MIN_JOINS}


@router.post("/score", response_model=FindDocumentsScoreResult,
             summary="Score a folder's proposal against the documents a person accepted or adjusted, and keep it",
             responses={404: {"model": _RefusalBody, "description": "No such folder or proposal."},
                        422: {"description": "The folder has no proposal, or a person set none of its documents."}})
async def score_find_documents(
    body: FindDocumentsScoreRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> FindDocumentsScoreResult:
    """Score the folder's newest current proposal (or the one named) against a person's breakdown: the documents a
    person accepted or adjusted. Boundary precision and recall over the joins a person judged, exact documents,
    kind accuracy over the kinds confirmed, and, at each confidence level, how many of the run's calls at least that
    sure the person agreed with. The score is kept on the folder (audited; a measurement, not undone). The answer
    carries `suggested_accept_above`: the lowest level at least 99% right over at least `min_joins` joins, pooled
    over every folder's newest score; null until then. It never turns the auto-accept on."""
    try:
        result = registry.invoke(db, "finddocs.score", body.model_dump(), ctx)
    except finddocs_score.ScoreNotPossible as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    score = FindDocumentsScore.model_validate(result.result["score"])
    stored = finddocs_score.scores(db, body.folder_id)
    return FindDocumentsScoreResult(items=stored, count=len(stored), score=score, audit_id=result.audit_id,
                                    **_suggestion(db))


@router.get("/score", response_model=FindDocumentsScores, summary="Stored Find the Documents scores")
async def list_find_documents_scores(
    request: Request,
    folder_id: str | None = Query(None, description="Only this folder's scores."),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> FindDocumentsScores:
    """Newest first (a score on a folder this caller may not read is left out), with the agreement at each level
    pooled over every folder's newest score and `suggested_accept_above` (null until a level is at least 99% right
    over at least `min_joins` joins)."""
    found = finddocs_score.scores(db, folder_id)
    readable = set(readable_documents(request, x_fichero_library_path, [s.folder_id for s in found]))
    kept = [s for s in found if s.folder_id in readable]
    return FindDocumentsScores(items=kept, count=len(kept), **_suggestion(db))
