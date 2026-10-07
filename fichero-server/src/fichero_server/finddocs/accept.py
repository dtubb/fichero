"""Accepting a Find the Documents proposal: one audited action, undone as one (`finddocs.accept-makes-groups`, #5550).

`finddocs.accept` takes a stored proposal and accepts its documents (all, the ones named, or those at least
`min_confidence` sure), in order, through the functions the app's own commands use:

* each document of two or more pages becomes a group node of its pages (`group_documents_impl`, the Group
  command's, #5303), named for its kind and date; a document of one page stays that page;
* its proposed prototype is assigned (`assign_document_prototype_impl`), the prototype made first when the
  project has none of that name (`create_value_impl`);
* each proposed group whose documents are all accepted becomes a group of those documents, in its order;
* the folder's canvas is laid out in the documents' order (`arrange_impl`, the Arrange command's).

Its inverse, `finddocs.unaccept`, ungroups what it made (newest first, so every page returns to its slot),
puts back each page's prototype, removes the prototypes it made, restores the canvas rows it moved
(`canvas.layout.restore`'s own code) and sets the proposal back to proposed: one undo restores the folder.
`finddocs.reject` marks documents rejected (kept for learning, `finddocs.corrections-teach`), undone the same way.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.finddocs import job as store
from fichero_server.models.found_documents import (
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
    folder_id: str | None = None
    canvas_before: list[dict[str, Any]] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    states_before: dict[str, Any] = Field(default_factory=dict)


class FindDocumentsRestateParams(BaseModel):
    proposal_id: str
    states_before: dict[str, Any]


def _states(proposal: Any) -> dict[str, Any]:
    return {"documents": {str(d.index): [d.state, d.accepted_as] for d in proposal.documents},
            "groups": {str(g.index): [g.state, g.accepted_as] for g in proposal.groups}}


def _restate(proposal: Any, states: dict[str, Any]) -> None:
    for d in proposal.documents:
        d.state, d.accepted_as = states.get("documents", {}).get(str(d.index), [d.state, d.accepted_as])
    for g in proposal.groups:
        g.state, g.accepted_as = states.get("groups", {}).get(str(g.index), [g.state, g.accepted_as])


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

    proposal = store.read(db, params.proposal_id)
    states_before = _states(proposal)
    chosen = _chosen(proposal, params)
    made: list[str] = []
    values_made: list[str] = []
    prototypes_before: dict[str, str | None] = {}
    for document in chosen:
        pages = [pid for pid in document.page_ids if (page := db.get(Document, pid)) is not None and not page.deleted_at]
        if not pages:
            raise LookupError(f"document {document.index + 1}'s pages are gone")
        if document.prototype_key:
            _ensure_prototype(db, document.prototype_key, document.kind or document.prototype_key, values_made)
        if len(pages) >= 2:
            group = group_documents_impl(db, DocumentGroupParams(name=document.name, child_ids=pages))
            target = group.id
            made.append(target)
            if document.prototype_key:
                # The group is this action's own, not yet committed: the assign route's impl reads committed
                # rows only, so the new node takes its prototype as it is made.
                group.prototype_key = document.prototype_key
                db.save(group)
        else:
            target = pages[0]
            prototypes_before[target] = db.get(Document, target).prototype_key
            if document.prototype_key:
                assign_document_prototype_impl(db, target, PrototypeAssignRequest(prototype_key=document.prototype_key))
        document.state, document.accepted_as = "accepted", target
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
            group.state, group.accepted_as = "accepted", made_group
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
             "prototypes_before": prototypes_before, "folder_id": proposal.folder_id,
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
    for d in proposal.documents:
        if d.index in set(params.document_indexes) and d.state == "proposed":
            d.state = "rejected"
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
