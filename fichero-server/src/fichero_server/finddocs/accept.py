"""Accepting a Find the Documents proposal: one audited action, undone as one (`finddocs.accept-makes-groups`, #5550).

`finddocs.accept` takes a stored proposal and accepts its documents (all, the ones named, or those at least
`min_confidence` sure), in order, through the functions the app's own commands use:

* each document of two or more pages becomes a group node of its pages (`group_documents_impl`, the Group
  command's, #5303), named for its kind and date; a document of one page stays that page;
* its proposed prototype is assigned (`assign_document_prototype_impl`), the prototype made first when the
  project has none of that name (`create_value_impl`);
* each proposed group whose documents are all accepted becomes a group of those documents, in its order;
* the folder's canvas is laid out in the documents' order (`arrange_impl`, the Arrange command's).

Each kind it writes records who chose it (`metadata.attribute_sources.prototype`, the one attribute-sources
path, `workflows/attribute_sources.py`): the run that made the proposal when its own auto-accept accepted it
(the action runs as that run: `ctx.run_id` is the proposal's `job_id`), never a person; otherwise the run's
proposal with ``accepted_by`` the person. The run's auto-accept leaves a kind a person chose alone. Each
document and group decided records who decided it (`decided_by`), so a person's answer can be told from the
run's (`finddocs.corrections-teach`).

Accept refuses, changing nothing, a proposal a later run superseded, and a document whose pages are no longer
the folder's loose pages (grouped, moved or deleted since it was proposed): `store.ProposalOutOfDate`.

Its inverse, `finddocs.unaccept`, ungroups what it made (newest first, so every page returns to its slot),
puts back each page's prototype and who chose it, removes the prototypes it made, restores the canvas rows it moved
(`canvas.layout.restore`'s own code) and sets the proposal back to proposed: one undo restores the folder.
`finddocs.reject` marks documents rejected (kept for learning, `finddocs.corrections-teach`), undone the same way.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.finddocs import store
from fichero_server.models.found_documents import (
    Decision,
    FindDocumentsAcceptRequest,
    FindDocumentsRejectRequest,
)


class FindDocumentsAcceptParams(FindDocumentsAcceptRequest):
    proposal_id: str


class FindDocumentsRejectParams(FindDocumentsRejectRequest):
    proposal_id: str


class FindDocumentsUnacceptParams(BaseModel):
    """What one accept did, in the order it did it: the undo's whole payload."""

    proposal_id: str
    made: list[str] = Field(default_factory=list, description="Group nodes made, oldest first.")
    values_made: list[str] = Field(default_factory=list, description="Prototype values made.")
    prototypes_before: dict[str, str | None] = Field(default_factory=dict)
    kind_records_before: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Each page's record of who chose its kind, and any kind proposed on it.")
    folder_id: str | None = None
    canvas_before: list[dict[str, Any]] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    states_before: dict[str, Any] = Field(default_factory=dict)


class FindDocumentsRestateParams(BaseModel):
    proposal_id: str
    states_before: dict[str, Any]


def _state(item: Any) -> list[Any]:
    return [item.state, item.accepted_as, item.decided_by.model_dump(mode="json") if item.decided_by else None]


def _states(proposal: Any) -> dict[str, Any]:
    return {"documents": {str(d.index): _state(d) for d in proposal.documents},
            "groups": {str(g.index): _state(g) for g in proposal.groups}}


def _set_state(item: Any, saved: list[Any] | None) -> None:
    if saved is None:
        return
    # An audit row from before `decided_by` holds [state, accepted_as].
    item.state, item.accepted_as, decided = (list(saved) + [None])[:3]
    item.decided_by = Decision.model_validate(decided) if decided else None


def _restate(proposal: Any, states: dict[str, Any]) -> None:
    for d in proposal.documents:
        _set_state(d, states.get("documents", {}).get(str(d.index)))
    for g in proposal.groups:
        _set_state(g, states.get("groups", {}).get(str(g.index)))


def _decision(proposal: Any, ctx: ActionContext) -> Decision:
    """The run's own auto-accept runs as the run that made the proposal (`job._run`); anything else is a
    person's: the routes never set a run id."""
    if ctx.run_id and ctx.run_id == proposal.job_id:
        return Decision(by="run", run_id=ctx.run_id)
    return Decision(by="person", actor=ctx.actor)


def _kind_source(proposal: Any, document: Any, decision: Decision) -> dict:
    """Who chose a document's kind, in `attribute_sources`' shape: the run that proposed it (its proposal,
    method and reasons), with ``accepted_by`` when a person accepted it."""
    from fichero_server.workflows import attribute_sources

    source = attribute_sources.machine_source(
        tool="find-documents", step="finddocs.accept", run_id=proposal.job_id, artifact_id=proposal.id,
        provider=store.PROVIDER, model=store.MODEL, said="; ".join(document.reasons) or None)
    return {**source, "accepted_by": decision.actor} if decision.by == "person" else source


def _kind_record(page: Any) -> dict[str, Any]:
    """A page's record of who chose its kind and the kind proposed on it, as an accept found them."""
    from fichero_server.workflows import attribute_sources

    return {"source": attribute_sources.sources(page).get(attribute_sources.PROTOTYPE),
            "proposed": attribute_sources.proposals(page).get(attribute_sources.PROTOTYPE)}


def _restore_kind_record(page: Any, record: dict[str, Any]) -> None:
    from fichero_server.workflows import attribute_sources

    meta = dict(page.metadata) if isinstance(page.metadata, dict) else {}
    for field, saved in ((attribute_sources.SOURCES, record.get("source")),
                         (attribute_sources.PROPOSED, record.get("proposed"))):
        entries = dict(meta.get(field)) if isinstance(meta.get(field), dict) else {}
        if saved is None:
            entries.pop(attribute_sources.PROTOTYPE, None)
        else:
            entries[attribute_sources.PROTOTYPE] = saved
        if entries:
            meta[field] = entries
        else:
            meta.pop(field, None)
    page.metadata = meta


def _refuse_out_of_date(db: Any, proposal: Any, chosen: list[Any]) -> None:
    """Refuse, before anything changes, a superseded proposal, and a chosen document any of whose pages is no
    longer one of its folder's loose pages (`job.loose_pages`: a photograph in the folder, or a page cut from
    one, whose parent is its photograph): accepting it would pull pages out of groups made since."""
    from fichero_server.finddocs.job import loose_pages
    from fichero_server.models import Document

    if proposal.state == "superseded":
        raise store.ProposalOutOfDate(
            f"this proposal was replaced by a later run of Find the Documents ({proposal.superseded_by}); "
            "accept from the later one")
    if not chosen:
        return
    loose = {page.id for page in loose_pages(db, proposal.folder_id)}
    for document in chosen:
        for page_id in document.page_ids:
            if page_id in loose:
                continue
            page = db.get(Document, page_id)
            parent = db.get(Document, page.parent_id) if page is not None and page.parent_id else None
            if page is None or page.deleted_at:
                why = "has been deleted"
            elif parent is not None and str(getattr(parent.doc_type, "value", parent.doc_type)) == "group":
                why = f"is already inside the group '{parent.name}'"
            else:
                why = "is no longer a loose page of the folder"
            raise store.ProposalOutOfDate(
                f"document {document.index + 1} ('{document.name}'): page '{page.name if page else page_id}' "
                f"{why} since it was proposed; run Find the Documents again")


def _chosen(proposal: Any, params: FindDocumentsAcceptParams) -> list[Any]:
    waiting = [d for d in proposal.documents if d.state == "proposed"]
    if params.document_indexes is not None:
        unknown = sorted(set(params.document_indexes) - {d.index for d in proposal.documents})
        if unknown:
            raise LookupError(f"the proposal has no documents {unknown}")
        waiting = [d for d in waiting if d.index in set(params.document_indexes)]
    if params.min_confidence is not None:
        waiting = [d for d in waiting if d.confidence >= params.min_confidence]
    return waiting


def _ensure_prototype(db: Any, key: str, label: str, made: list[str]) -> None:
    from fichero_server.api.routes.document.classifications import ClassificationCreateRequest, create_value_impl
    from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue

    if db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key=key):
        return
    value = create_value_impl(db, ClassificationCreateRequest(
        dimension=ClassificationDimension.document_prototype, key=key, label=label,
        description="Proposed by Find the Documents"))
    made.append(value.id)


def _emit(folder_id: str | None, node_ids: list[str]):
    def emit(ctx: ActionContext, spec: ChangeSpec) -> None:
        from fichero_server.api.change_stream import emit_change
        from fichero_server.api.routes.document.documents import _emit_document_change_spec

        _emit_document_change_spec(ctx, spec)
        if ctx.library_path and folder_id and node_ids:
            emit_change(ctx.library_path, type="canvas.arranged", entity_ids=node_ids, document_ids=[folder_id],
                        run_id=ctx.run_id, actor=ctx.actor, origin_window=ctx.origin_window, origin_user=ctx.actor)

    return emit


def _invert_accept(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    return ("finddocs.unaccept", dict(after)) if after else None


@action("finddocs.accept", FindDocumentsAcceptParams, domains=["document", "canvas"], undoable=True,
        invert=_invert_accept)
def _action_accept(db: Any, params: FindDocumentsAcceptParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.api.routes.document.documents import (
        DocumentGroupParams,
        PrototypeAssignRequest,
        assign_document_prototype_impl,
        group_documents_impl,
    )
    from fichero_server.api.routes.interpretation.canvas import _load_canvas_layout, arrange_impl
    from fichero_server.models import Document
    from fichero_server.workflows import attribute_sources

    proposal = store.read(db, params.proposal_id)
    states_before = _states(proposal)
    chosen = _chosen(proposal, params)
    _refuse_out_of_date(db, proposal, chosen)
    decision = _decision(proposal, ctx)
    made: list[str] = []
    values_made: list[str] = []
    prototypes_before: dict[str, str | None] = {}
    kind_records_before: dict[str, dict[str, Any]] = {}
    for document in chosen:
        pages = list(document.page_ids)
        source = _kind_source(proposal, document, decision)
        if len(pages) >= 2:
            group = group_documents_impl(db, DocumentGroupParams(name=document.name, child_ids=pages))
            target = group.id
            made.append(target)
            if document.prototype_key:
                _ensure_prototype(db, document.prototype_key, document.kind or document.prototype_key, values_made)
                # The group is this action's own, not yet committed: the assign route's impl reads committed
                # rows only, so the new node takes its prototype, and who chose it, as it is made.
                group.prototype_key = document.prototype_key
                group.metadata = attribute_sources.with_sources(group.metadata,
                                                                {attribute_sources.PROTOTYPE: source})
                db.save(group)
        else:
            target = pages[0]
            page = db.get(Document, target)
            prototypes_before[target] = page.prototype_key
            kind_records_before[target] = _kind_record(page)
            # The run's own accept never replaces a kind a person chose (`attribute_sources.machine_may_set`).
            if document.prototype_key and (decision.by == "person" or
                                           attribute_sources.machine_may_set(page, attribute_sources.PROTOTYPE)):
                _ensure_prototype(db, document.prototype_key, document.kind or document.prototype_key, values_made)
                assign_document_prototype_impl(db, target, PrototypeAssignRequest(
                    prototype_key=document.prototype_key), source=source)
        document.state, document.accepted_as, document.decided_by = "accepted", target, decision
    # A proposed group whose documents are all accepted becomes a group of them, in its order.
    tops = {d.index: d.accepted_as for d in proposal.documents if d.state == "accepted"}
    if params.groups:
        for group in proposal.groups:
            members = [tops.get(i) for i in group.document_indexes]
            if group.state != "proposed" or None in members or len(members) < 2:
                continue
            made_group = group_documents_impl(db, DocumentGroupParams(name=group.label or "Group",
                                                                      child_ids=members)).id
            made.append(made_group)
            group.state, group.accepted_as, group.decided_by = "accepted", made_group, decision
            for i in group.document_indexes:
                tops[i] = made_group
    node_ids: list[str] = []
    canvas_before: list[dict[str, Any]] = []
    if params.arrange and proposal.folder_id and chosen:
        in_order = [d for d in proposal.documents if d.state == "accepted"]
        node_ids = list(dict.fromkeys(f"doc:{tops[d.index]}" for d in in_order))
        canvas_before = [row.model_dump(mode="json") for row in _load_canvas_layout(db, proposal.folder_id)
                         if row.item_id in set(node_ids)]
        arrange_impl(db, proposal.folder_id, node_ids, "grid")
    store.write(db, proposal)
    touched = sorted({*made, *prototypes_before, *(pid for d in chosen for pid in d.page_ids)})
    after = {"proposal_id": proposal.id, "made": made, "values_made": values_made,
             "prototypes_before": prototypes_before, "kind_records_before": kind_records_before,
             "folder_id": proposal.folder_id,
             "canvas_before": canvas_before, "node_ids": node_ids, "states_before": states_before}
    spec = ChangeSpec(domains=["document", "canvas"], target_ids=touched, after=after, emit_type="document.updated",
                      document_ids=touched, emit_fn=_emit(proposal.folder_id, node_ids))
    return {"accepted": [d.index for d in chosen], "groups_made": made}, spec


@action("finddocs.unaccept", FindDocumentsUnacceptParams, domains=["document", "canvas"], undoable=False)
def _action_unaccept(db: Any, params: FindDocumentsUnacceptParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.api.routes.document.classifications import delete_value_impl
    from fichero_server.api.routes.document.documents import ungroup_document_impl
    from fichero_server.api.routes.interpretation.canvas import (
        CanvasLayoutRestoreParams,
        _action_restore_canvas_layout,
    )
    from fichero_server.models import Document

    restored: list[str] = []
    for group_id in reversed(params.made):
        _group, children = ungroup_document_impl(db, group_id)
        restored += [c.id for c in children]
    for page_id, key in params.prototypes_before.items():
        page = db.get(Document, page_id)
        if page is not None:
            page.prototype_key = key
            if page_id in params.kind_records_before:
                _restore_kind_record(page, params.kind_records_before[page_id])
            db.save(page)
    for value_id in params.values_made:
        delete_value_impl(db, value_id)
    if params.folder_id and params.node_ids:
        _action_restore_canvas_layout(db, CanvasLayoutRestoreParams(
            folder_id=params.folder_id, rows=params.canvas_before, current_item_ids=params.node_ids), ctx)
    proposal = store.read(db, params.proposal_id)
    _restate(proposal, params.states_before)
    store.write(db, proposal)
    touched = sorted({*params.made, *restored, *params.prototypes_before})
    spec = ChangeSpec(domains=["document", "canvas"], target_ids=touched,
                      before={"proposal_id": params.proposal_id, "made": params.made},
                      after={"restored": restored}, emit_type="document.updated", document_ids=touched,
                      emit_fn=_emit(params.folder_id, params.node_ids))
    return {"restored": restored}, spec


def _invert_reject(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    return ("finddocs.restate", {"proposal_id": after["proposal_id"], "states_before": after["states_before"]}) \
        if after else None


@action("finddocs.reject", FindDocumentsRejectParams, domains=["document"], undoable=True, invert=_invert_reject)
def _action_reject(db: Any, params: FindDocumentsRejectParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    states_before = _states(proposal)
    unknown = sorted(set(params.document_indexes) - {d.index for d in proposal.documents})
    if unknown:
        raise LookupError(f"the proposal has no documents {unknown}")
    decision = _decision(proposal, ctx)
    for d in proposal.documents:
        if d.index in set(params.document_indexes) and d.state == "proposed":
            d.state, d.decided_by = "rejected", decision
    store.write(db, proposal)
    return ({"rejected": params.document_indexes},
            ChangeSpec(domains=["document"], target_ids=[proposal.id],
                       after={"proposal_id": proposal.id, "states_before": states_before}))


@action("finddocs.restate", FindDocumentsRestateParams, domains=["document"], undoable=False)
def _action_restate(db: Any, params: FindDocumentsRestateParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    proposal = store.read(db, params.proposal_id)
    _restate(proposal, params.states_before)
    store.write(db, proposal)
    return {"proposal_id": proposal.id}, ChangeSpec(domains=["document"], target_ids=[proposal.id])
