"""Adjusting a Find the Documents proposal before accepting it (`finddocs.adjust`, #5550).

A person can split a proposed document at a page (`finddocs.split`), join a document to the next
(`finddocs.join`), or move a document's first page to the document before it, or its last page to the one
after it (`finddocs.move_page`). Each changes the stored proposal only, never a node: the documents are
renumbered in order, each touched document says the person set it (`adjusted_by`, confidence 1.0, no
machine score), proposed groups keep their documents, and the adjustment appends its labelled examples
(boundary / no boundary between two pages, with what the run said of that join) to the proposal's
`examples`, the corrections the project learns from (`finddocs.corrections-teach`).

Each is one audited action; its undo (`finddocs.unadjust`) puts the documents, groups and examples back as
they were, and redo replays it. A superseded proposal, a document already accepted or rejected, or one whose
pages are no longer the folder's loose pages is refused (`store.ProposalOutOfDate`, 409); an index or page
out of range is refused in words (`AdjustmentNotPossible`, 422).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.finddocs import store
from fichero_server.finddocs.accept import _decision, _refuse_out_of_date
from fichero_server.models.found_documents import (
    BoundaryExample,
    DocumentsProposal,
    FindDocumentsJoinRequest,
    FindDocumentsMovePageRequest,
    FindDocumentsSplitRequest,
    ProposedDocument,
)


class AdjustmentNotPossible(ValueError):
    """An adjustment that names a document or page the proposal does not have, or that cannot be made (a split
    at a document's first page, a move that would empty a document). The routes answer 422."""


class FindDocumentsSplitParams(FindDocumentsSplitRequest):
    proposal_id: str


class FindDocumentsJoinParams(FindDocumentsJoinRequest):
    proposal_id: str


class FindDocumentsMovePageParams(FindDocumentsMovePageRequest):
    proposal_id: str


class FindDocumentsUnadjustParams(BaseModel):
    """The proposal's documents, groups and examples as they were before an adjustment: the undo's payload."""

    proposal_id: str
    before: dict[str, Any]
    #: The proposal as the adjustment left it (#5698): the undo is refused when it is not so any more.
    left: dict[str, Any] | None = None


_RESTORED = ("documents", "groups", "examples")


def _document(proposal: DocumentsProposal, index: int) -> ProposedDocument:
    if not 0 <= index < len(proposal.documents):
        raise AdjustmentNotPossible(
            f"the proposal has no document {index + 1}: it has {len(proposal.documents)} "
            f"(document_index runs from 0 to {len(proposal.documents) - 1})")
    return proposal.documents[index]


def _refuse(db: Any, proposal: DocumentsProposal, documents: list[ProposedDocument]) -> None:
    """Refuse, changing nothing, a superseded proposal, a document already decided, or one whose pages have
    been grouped, moved or deleted since (the accept's own check)."""
    _refuse_out_of_date(db, proposal, [])
    for document in documents:
        if document.state != "proposed":
            raise store.ProposalOutOfDate(
                f"document {document.index + 1} ('{document.name}') is already {document.state}; "
                "undo that first to adjust it")
    _refuse_out_of_date(db, proposal, documents)


def _example(proposal: DocumentsProposal, left: str, right: str, boundary: bool, adjustment: str,
             decision: Any, at: str) -> BoundaryExample:
    join = next((j for j in proposal.joins if j.page_id == right), None)
    reasons = [f"{s.cue} ({s.role}, {s.weight:+.2f})" + (f": {s.line}" if s.line else "")
               for s in (join.signals if join else [])]
    return BoundaryExample(left_page_id=left, right_page_id=right, boundary=boundary, adjustment=adjustment,
                           decided_by=decision, at=at, proposal_id=proposal.id,
                           run_probability=join.probability if join else None, run_reasons=reasons)


def _set_by_person(proposal: DocumentsProposal, document: ProposedDocument, decision: Any, said: str) -> None:
    positions = {page_id: i for i, page_id in enumerate(proposal.page_ids)}
    at = [positions[p] for p in document.page_ids if p in positions]
    if at:
        document.first_position, document.last_position = min(at), max(at)
    document.confidence = 1.0
    document.adjusted_by = decision
    document.reasons = [*document.reasons, said]


def _renumber(proposal: DocumentsProposal, documents: list[ProposedDocument], old_to_new: dict[int, list[int]]) -> None:
    """Set the documents in order and each proposed group's document indexes to the new numbering."""
    for i, document in enumerate(documents):
        document.index = i
    proposal.documents = documents
    for group in proposal.groups:
        group.document_indexes = list(dict.fromkeys(n for i in group.document_indexes for n in old_to_new.get(i, [])))


def _commit(db: Any, proposal: DocumentsProposal, before: dict[str, Any],
            examples: list[BoundaryExample]) -> tuple[dict, ChangeSpec]:
    proposal.examples = [*proposal.examples, *examples]
    store.write(db, proposal)
    result = {"proposal_id": proposal.id, "examples": [e.model_dump(mode="json") for e in examples]}
    return result, ChangeSpec(domains=["document"], target_ids=[proposal.id],
                              after={"proposal_id": proposal.id, "before": before, "left": _snapshot(proposal)})


def _snapshot(proposal: DocumentsProposal) -> dict[str, Any]:
    dumped = proposal.model_dump(mode="json")
    return {key: dumped[key] for key in _RESTORED}


def _now() -> str:
    from fichero_server.core.timeutil import utc_now

    return utc_now().isoformat()


def _invert(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    return ("finddocs.unadjust", {"proposal_id": after["proposal_id"], "before": after["before"],
                                  "left": after.get("left")}) if after else None


@action("finddocs.split", FindDocumentsSplitParams, domains=["document"], undoable=True, invert=_invert)
def _action_split(db: Any, params: FindDocumentsSplitParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    document = _document(proposal, params.document_index)
    if params.page_id not in document.page_ids:
        raise AdjustmentNotPossible(f"page {params.page_id} is not one of document {document.index + 1}'s pages")
    cut = document.page_ids.index(params.page_id)
    if cut == 0:
        raise AdjustmentNotPossible(f"page {params.page_id} is document {document.index + 1}'s first page: "
                                    "a split starts the second document at a later page")
    _refuse(db, proposal, [document])
    before, decision, at = _snapshot(proposal), _decision(proposal, ctx), _now()
    left, right = document.page_ids[cut - 1], document.page_ids[cut]
    second = ProposedDocument(index=0, name="", page_ids=document.page_ids[cut:], first_position=0,
                              last_position=0, parties=list(document.parties), confidence=1.0,
                              reasons=list(document.reasons))
    document.page_ids = document.page_ids[:cut]
    said = f"split by a person: a document starts at page {proposal.page_ids.index(right) + 1}" \
        if right in proposal.page_ids else "split by a person"
    _set_by_person(proposal, document, decision, said)
    _set_by_person(proposal, second, decision, said)
    second.name = f"Document from page {second.first_position + 1}"
    i = document.index
    documents = [*proposal.documents[:i + 1], second, *proposal.documents[i + 1:]]
    old_to_new = {k: ([k, k + 1] if k == i else [k + (1 if k > i else 0)]) for k in range(len(proposal.documents))}
    _renumber(proposal, documents, old_to_new)
    return _commit(db, proposal, before, [_example(proposal, left, right, True, "split", decision, at)])


@action("finddocs.join", FindDocumentsJoinParams, domains=["document"], undoable=True, invert=_invert)
def _action_join(db: Any, params: FindDocumentsJoinParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    first = _document(proposal, params.document_index)
    if params.document_index + 1 >= len(proposal.documents):
        raise AdjustmentNotPossible(f"document {first.index + 1} is the last: there is no document after it to join")
    second = proposal.documents[params.document_index + 1]
    _refuse(db, proposal, [first, second])
    before, decision, at = _snapshot(proposal), _decision(proposal, ctx), _now()
    left, right = first.page_ids[-1], second.page_ids[0]
    first.page_ids = [*first.page_ids, *second.page_ids]
    first.kind = first.kind or second.kind
    first.prototype_key = first.prototype_key or second.prototype_key
    first.date = first.date or second.date
    first.parties = list(dict.fromkeys([*first.parties, *second.parties]))
    _set_by_person(proposal, first, decision, f"joined by a person with '{second.name}'")
    i = first.index
    documents = [d for d in proposal.documents if d is not second]
    old_to_new = {k: [k if k <= i else k - 1] for k in range(len(proposal.documents))}
    _renumber(proposal, documents, old_to_new)
    return _commit(db, proposal, before, [_example(proposal, left, right, False, "join", decision, at)])


@action("finddocs.move_page", FindDocumentsMovePageParams, domains=["document"], undoable=True, invert=_invert)
def _action_move_page(db: Any, params: FindDocumentsMovePageParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    source = _document(proposal, params.document_index)
    other = params.document_index + (-1 if params.to == "previous" else 1)
    if not 0 <= other < len(proposal.documents):
        raise AdjustmentNotPossible(f"document {source.index + 1} has no document {params.to} to it to move a page to")
    if len(source.page_ids) < 2:
        raise AdjustmentNotPossible(f"document {source.index + 1} has one page: moving it would leave no document; "
                                    "join it instead")
    target = proposal.documents[other]
    _refuse(db, proposal, [source, target])
    before, decision, at = _snapshot(proposal), _decision(proposal, ctx), _now()
    if params.to == "previous":
        page, left_behind = source.page_ids[0], source.page_ids[1]
        neighbour = target.page_ids[-1]
        source.page_ids, target.page_ids = source.page_ids[1:], [*target.page_ids, page]
        examples = [_example(proposal, neighbour, page, False, "move-page", decision, at),
                    _example(proposal, page, left_behind, True, "move-page", decision, at)]
    else:
        page, left_behind = source.page_ids[-1], source.page_ids[-2]
        neighbour = target.page_ids[0]
        source.page_ids, target.page_ids = source.page_ids[:-1], [page, *target.page_ids]
        examples = [_example(proposal, page, neighbour, False, "move-page", decision, at),
                    _example(proposal, left_behind, page, True, "move-page", decision, at)]
    said = f"a page moved by a person from '{source.name}' to '{target.name}'"
    _set_by_person(proposal, source, decision, said)
    _set_by_person(proposal, target, decision, said)
    return _commit(db, proposal, before, examples)


@action("finddocs.unadjust", FindDocumentsUnadjustParams, domains=["document"], undoable=False)
def _action_unadjust(db: Any, params: FindDocumentsUnadjustParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    # An adjustment renumbers the documents: it is undone whole, so only while the proposal is as it left it, and
    # a later answer (an accept names pages, not the proposal, so the general rule misses it) is never wiped (#5698).
    if params.left is None or _snapshot(proposal) != params.left:
        from fichero_server.actions.undo import UndoRefused

        raise UndoRefused(409, "changed", "A later answer on this proposal changed it since this adjustment; undo "
                                          "that later answer first, so it is not lost.")
    restored = DocumentsProposal.model_validate({**proposal.model_dump(mode="json"),
                                                 **{k: params.before[k] for k in _RESTORED if k in params.before}})
    store.write(db, restored)
    return {"proposal_id": proposal.id}, ChangeSpec(domains=["document"], target_ids=[proposal.id])
