"""The Prepare Images actions on a page's edit chain: squaring, blank marks, proposals and a correction copied to a folder
(`prep.check.*`, #5382, #6192). Moved out of `image_editing.py`, which is over a thousand lines; that module imports this one
last, so the actions register with the rest and `router` gets the batch-preview route.
"""
from __future__ import annotations

import asyncio
import io
from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.ingest.image_editing import (
    IMAGE_EDIT_EMIT_TYPE,
    RotateImageActionParams,
    _apply_operation,
    _append_operation,
    _chain_ops_snapshot,
    _chain_result,
    _folder_images,
    _get_chain,
    _get_or_404_document,
    _image_chain_spec,
    _invert_image_chain,
    _load_source_image,
    _render_and_append,
    rotate_image_impl,
    _resolve_source_and_page,
    router,
    set_operations_impl,
)
from fichero_server.api.routes.ingest.image_prepare_shared import (
    MarkBlankOperationRequest,
    SquareOperationRequest,
    _answer_proposal,
    _invert_proposals,
    _proposal_state,
)
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Document, ImageEditChain


def square_image_impl(
    db: Database, document_id: str, request: SquareOperationRequest
) -> ImageEditChain:
    """A person's four corners squared into a page: the row says `who: person` (`prep.square.corner-handles-correct-it`)."""
    doc = _get_or_404_document(db, document_id)
    source_path, page = _resolve_source_and_page(db, doc, request.page)
    op = {"op": "square", "page": page, "params": {"quad": request.quad}, "who": "person"}
    run_value = ((doc.metadata or {}).get("prep_proposals") or {}).get("page_box") or (doc.metadata or {}).get("page_region")
    if run_value:  # the person's row replaces the run's and keeps the run's values beside it (a training label)
        op["replaces"] = {"by": run_value.get("by") or run_value.get("method"), "values": {
            "quad": run_value.get("quad"), "box": run_value.get("box"), "confidence": run_value.get("confidence")}}
    chain = _render_and_append(db, document_id, source_path, op, page)
    _answer_proposal(db, doc, "page_box")
    return chain


def mark_blank_impl(db: Database, document_id: str, blank: bool, *, who: str = "person",
                    reason: str | None = None) -> ImageEditChain:
    """Hide (blank) or unhide a page: the chain row and `exclude_from_processing` move together (`media.blank_page`).
    `who` is the person, or `run <id>` for a run's own hide (`page_crop`, through the action layer)."""
    from fichero_server.media.blank_page import mark_blank

    _get_or_404_document(db, document_id)
    mark_blank(db, document_id, blank, who=who,
               reason=reason or ("marked by a person" if blank else "unhidden by a person"))
    if not blank:  # shown again: through the steps it skipped
        from fichero_server.media.blank_page import queue_unhidden

        queue_unhidden(db, document_id)
    return _get_chain(db, document_id)


class SquareImageActionParams(SquareOperationRequest):
    document_id: str


class MarkBlankImageActionParams(MarkBlankOperationRequest):
    document_id: str
    #: A run's own hide says so (`run <id>`), with its reason; a person's click is the default.
    who: str = "person"
    reason: str | None = None


class RestoreProposalsParams(BaseModel):
    """Params for image.restore_proposals — put a page's proposals, the kinds a person answered and (when given) its edit
    chain back as they were: the inverse of a squaring or an Accept (`prep.check.correction-replaces-the-runs-row`)."""

    document_id: str
    proposals: dict[str, Any] = Field(default_factory=dict)
    answered: dict[str, Any] = Field(default_factory=dict)
    operations: list[dict[str, Any]] | None = None


@action(
    "image.square",
    SquareImageActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=_invert_proposals,
)
def _action_square(
    db: Database, params: SquareImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    state = _proposal_state(_get_or_404_document(db, params.document_id))
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = square_image_impl(db, params.document_id, params)
    spec = _image_chain_spec(
        params.document_id, before_ops, [dict(op) for op in chain.operations], domains=["image", "document"])
    spec.before = {**(spec.before or {}), **state}
    return _chain_result(chain), spec


class AcceptProposalParams(BaseModel):
    """Params for image.accept_proposal — a person looked at a page the run was unsure of and leaves it as it is."""

    document_id: str
    kind: str = Field(description="the proposal answered: page_box, turn or blank")


@action(
    "image.accept_proposal",
    AcceptProposalParams,
    domains=["document"],
    undoable=True,
    invert=_invert_proposals,
)
def _action_accept_proposal(
    db: Database, params: AcceptProposalParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc = _get_or_404_document(db, params.document_id)
    state = _proposal_state(doc)
    meta = dict(doc.metadata or {})
    meta["prep_proposals"] = {k: v for k, v in state["proposals"].items() if k != params.kind}
    meta["prep_answered"] = {**state["answered"], params.kind: "person"}
    doc.metadata = meta
    db.save(doc)
    return {"document_id": doc.id, "kind": params.kind}, ChangeSpec(
        domains=["document"], target_ids=[doc.id], before={"document_id": doc.id, **state},
        after={"document_id": doc.id, "proposals": meta["prep_proposals"], "answered": meta["prep_answered"]},
        emit_type="document.updated", document_ids=[doc.id])


@action(
    "image.restore_proposals",
    RestoreProposalsParams,
    domains=["image", "document"],
    undoable=False,  # it is the inverse of a squaring or an Accept; redo is the audit's own
)
def _action_restore_proposals(
    db: Database, params: RestoreProposalsParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    doc = _get_or_404_document(db, params.document_id)
    meta = dict(doc.metadata or {})
    meta["prep_proposals"] = dict(params.proposals)
    meta["prep_answered"] = dict(params.answered)
    doc.metadata = meta
    db.save(doc)
    chain = set_operations_impl(
        db, params.document_id, list(before_ops if params.operations is None else params.operations))
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, [dict(op) for op in chain.operations], domains=["image", "document"])


class RestoreBlankStateParams(BaseModel):
    """Params for image.restore_blank — put a page's hidden state and edit chain back as they were."""

    document_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)
    exclude_from_processing: bool = False
    blank_note: dict[str, Any] | None = None
    blank_proposal: dict[str, Any] | None = None


def _invert_mark_blank(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    """Undo of a mark: the page hidden or shown as it was, and the mark's row gone from its chain."""
    if not before or not before.get("document_id"):
        return None
    return "image.restore_blank", {
        "document_id": before["document_id"], "operations": before.get("operations", []),
        "exclude_from_processing": before.get("exclude_from_processing", False), "blank_note": before.get("blank_note"),
        "blank_proposal": before.get("blank_proposal"),
    }


@action(
    "image.mark_blank",
    MarkBlankImageActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=_invert_mark_blank,
)
def _action_mark_blank(
    db: Database, params: MarkBlankImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc = _get_or_404_document(db, params.document_id)
    state = {"exclude_from_processing": bool(doc.exclude_from_processing), "blank_note": (doc.metadata or {}).get("blank"),
             "blank_proposal": ((doc.metadata or {}).get("prep_proposals") or {}).get("blank")}
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = mark_blank_impl(db, params.document_id, params.blank, who=params.who, reason=params.reason)
    spec = _image_chain_spec(
        params.document_id, before_ops, [dict(op) for op in chain.operations], domains=["image", "document"])
    spec.before = {**(spec.before or {}), **state}
    return _chain_result(chain), spec


@action(
    "image.restore_blank",
    RestoreBlankStateParams,
    domains=["image", "document"],
    undoable=False,  # it is the inverse of a mark; redo is the audit's own
)
def _action_restore_blank(
    db: Database, params: RestoreBlankStateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    doc = _get_or_404_document(db, params.document_id)
    doc.exclude_from_processing = params.exclude_from_processing
    meta = dict(doc.metadata or {})
    if params.blank_note is None:
        meta.pop("blank", None)
    else:
        meta["blank"] = params.blank_note
    proposals = {k: v for k, v in (meta.get("prep_proposals") or {}).items() if k != "blank"}
    if params.blank_proposal is not None:  # a person's answer is taken back: the run's proposal is on the list again
        proposals["blank"] = params.blank_proposal
    if proposals or "prep_proposals" in meta:
        meta["prep_proposals"] = proposals
    doc.metadata = meta
    db.save(doc)
    chain = set_operations_impl(db, params.document_id, list(params.operations))
    return _chain_result(chain), _image_chain_spec(
        params.document_id, before_ops, [dict(op) for op in chain.operations], domains=["image", "document"])


# ---------------------------------------------------------------------------
# A correction applied to the folder (`prep.check.apply-correction-to-the-folder`, #6192)
# ---------------------------------------------------------------------------

BATCH_PREVIEW_SIDE = 480


class BatchPrepareOperation(BaseModel):
    """The correction to copy, in fractions of the upright frame (a square's four corners) or degrees (a turn)."""

    op: Literal["square", "rotate"]
    quad: list[Annotated[list[float], Field(min_length=2, max_length=2)]] | None = None
    angle: float | None = Field(default=None, ge=-360.0, le=360.0)

    def row_params(self) -> dict[str, Any]:
        if self.op == "square":
            if self.quad is None or len(self.quad) != 4:
                raise HTTPException(422, "a square needs its four corners")
            return {"quad": self.quad}
        if self.angle is None:
            raise HTTPException(422, "a turn needs its angle")
        return {"angle": self.angle, "expand": True}


class BatchPrepareRequest(BaseModel):
    folder_id: str
    operation: BatchPrepareOperation
    source_document_id: str | None = Field(
        default=None, description="the page the correction was made on: it already has it, so it is left out")


class BatchPreparePreviewItem(BaseModel):
    document_id: str
    name: str
    image_base64: str = Field(description="the page with the correction applied, a small JPEG; nothing is written")


class BatchPreparePreview(BaseModel):
    previews: list[BatchPreparePreviewItem]
    pages: int = Field(description="how many pages the batch would change")


def _batch_targets(db: Database, request: BatchPrepareRequest) -> tuple[list[tuple[Document, int]], list[dict[str, str]]]:
    """(page, source page number) the batch would change, and (page id, why) for each it leaves out: the page the correction
    came from, a page hidden as blank, one a person already squared or turned, one with no readable file."""
    from fichero_server.media.blank_page import is_hidden_blank

    targets: list[tuple[Document, int]] = []
    skipped: list[dict[str, str]] = []
    order = {doc_id: i for i, doc_id in enumerate(db.unit_of_work_ids())}  # the project's page order: first, middle, last mean it
    for doc in sorted(_folder_images(db, request.folder_id), key=lambda d: (order.get(d.id, len(order)), d.name)):
        if doc.id == request.source_document_id:
            continue
        chain = _get_chain(db, doc.id)
        if is_hidden_blank(doc):
            skipped.append({"id": doc.id, "why": "hidden as blank"})
        elif any(op.get("who") == "person" and op.get("op") == request.operation.op for op in (chain.operations if chain else [])):
            skipped.append({"id": doc.id, "why": f"a person already did a {request.operation.op} on it"})
        else:
            try:
                targets.append((doc, _resolve_source_and_page(db, doc, 1)[1]))
            except HTTPException as exc:
                skipped.append({"id": doc.id, "why": str(exc.detail)})
    return targets, skipped


@router.post("/batch-prepare/preview", response_model=BatchPreparePreview)
async def batch_prepare_preview(
    request: BatchPrepareRequest, db: Database = Depends(get_library_database)
) -> BatchPreparePreview:
    """The folder's first, middle and last page with the correction applied, before anything runs. Writes no row."""
    return await asyncio.to_thread(_batch_prepare_preview, db, request)


def _batch_prepare_preview(db: Database, request: BatchPrepareRequest) -> BatchPreparePreview:
    import base64

    targets, _skipped = _batch_targets(db, request)
    chosen = [targets[i] for i in sorted({0, len(targets) // 2, len(targets) - 1})] if targets else []
    op = {"op": request.operation.op, "page": 1, "params": request.operation.row_params()}
    previews = []
    for doc, page in chosen:
        source_path, _ = _resolve_source_and_page(db, doc, 1)
        picture = _apply_operation(_load_source_image(source_path, page=page), op)
        picture.thumbnail((BATCH_PREVIEW_SIDE, BATCH_PREVIEW_SIDE))
        out = io.BytesIO()
        picture.convert("RGB").save(out, format="JPEG", quality=80)
        previews.append(BatchPreparePreviewItem(
            document_id=doc.id, name=doc.name, image_base64=base64.b64encode(out.getvalue()).decode("ascii")))
    return BatchPreparePreview(previews=previews, pages=len(targets))


class BatchPrepareActionParams(BatchPrepareRequest):
    pass


def _page_state(db: Database, doc: Document) -> dict[str, Any]:
    return {"operations": _chain_ops_snapshot(db, doc.id), **_proposal_state(doc)}


class RestoreBatchParams(BaseModel):
    """Params for image.restore_batch — every page the batch touched back as it was (the whole-batch Undo)."""

    pages: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _invert_batch(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    if not before or "pages" not in before:
        return None
    return "image.restore_batch", {"pages": before["pages"]}


@action(
    "image.batch_prepare",
    BatchPrepareActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=_invert_batch,
)
def _action_batch_prepare(
    db: Database, params: BatchPrepareActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """One correction copied to every page of the folder, each row `who: person` carrying one `batch_id` (the audit's id),
    so the whole batch undoes as one audit and one page undoes by dropping its row."""
    import uuid

    targets, skipped = _batch_targets(db, params)
    batch_id = uuid.uuid4().hex
    row_params = params.operation.row_params()
    before: dict[str, dict[str, Any]] = {}
    for doc, page in targets:
        before[doc.id] = _page_state(db, doc)
        row = {"op": params.operation.op, "page": page, "params": row_params, "who": "person", "batch_id": batch_id,
               "created_at": utc_now().isoformat()}
        _append_operation(db, doc.id, row)
        if params.operation.op == "square":
            _answer_proposal(db, db.get(Document, doc.id), "page_box")
        elif params.operation.op == "rotate":
            _answer_proposal(db, db.get(Document, doc.id), "turn")
    result = {"batch_id": batch_id, "applied": [doc.id for doc, _ in targets], "skipped": skipped}
    return result, ChangeSpec(
        domains=["image", "document"], target_ids=[doc.id for doc, _ in targets], before={"pages": before},
        after={"batch_id": batch_id, "pages": list(before)}, audit_id=batch_id, emit_type=IMAGE_EDIT_EMIT_TYPE,
        document_ids=[doc.id for doc, _ in targets])


@action(
    "image.restore_batch",
    RestoreBatchParams,
    domains=["image", "document"],
    undoable=False,  # it is the inverse of a batch; redo is the audit's own
)
def _action_restore_batch(
    db: Database, params: RestoreBatchParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    for doc_id, state in params.pages.items():
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        meta = dict(doc.metadata or {})
        meta["prep_proposals"] = dict(state.get("proposals") or {})
        meta["prep_answered"] = dict(state.get("answered") or {})
        doc.metadata = meta
        db.save(doc)
        set_operations_impl(db, doc_id, list(state.get("operations") or []))
    return {"restored": list(params.pages)}, ChangeSpec(
        domains=["image", "document"], target_ids=list(params.pages), emit_type=IMAGE_EDIT_EMIT_TYPE,
        document_ids=list(params.pages), before=None, after={"pages": list(params.pages)})


class UndoBatchPageParams(BaseModel):
    """Params for image.undo_batch_page — one page leaves a batch: its row of that batch is dropped, the others stay."""

    document_id: str
    batch_id: str


@action(
    "image.undo_batch_page",
    UndoBatchPageParams,
    domains=["image"],
    undoable=True,
    invert=_invert_image_chain,
)
def _action_undo_batch_page(
    db: Database, params: UndoBatchPageParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_ops = _chain_ops_snapshot(db, params.document_id)
    kept = [op for op in before_ops if op.get("batch_id") != params.batch_id]
    chain = set_operations_impl(db, params.document_id, kept)
    return _chain_result(chain), _image_chain_spec(params.document_id, before_ops, [dict(op) for op in chain.operations])


@action(
    "image.rotate",
    RotateImageActionParams,
    domains=["image", "document"],
    undoable=True,
    invert=_invert_proposals,
)
def _action_rotate(
    db: Database, params: RotateImageActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    state = _proposal_state(_get_or_404_document(db, params.document_id))
    before_ops = _chain_ops_snapshot(db, params.document_id)
    chain = rotate_image_impl(db, params.document_id, params)
    spec = _image_chain_spec(
        params.document_id, before_ops, [dict(op) for op in chain.operations], domains=["image", "document"])
    spec.before = {**(spec.before or {}), **state}
    return _chain_result(chain), spec
