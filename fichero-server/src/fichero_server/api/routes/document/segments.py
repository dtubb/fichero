"""Source-model slice 1 seam + slice 3 writes.

Slice 1: `GET /api/segments/document/{doc_id}` (writes nothing). One engine
call that returns a source's segments, whether they still live in today's
``Artifact.ocr_geometry`` blocks or, from slice 3 on, in real ``Segment``
records — the caller cannot tell which (`source.one-store`,
`source.seam.read-either-store`). Follows the shape of
``content_representations.py``.

Slice 3 (#4921) adds the first writes: `segment.pass_create`,
`segment.pass_delete`/`.pass_restore`, `segment.create`, `segment.create_many`,
and the internal `segment.delete` used only as `segment.create`'s inverse
(full delete/undo-with-versions for a segment is slice 5's). Every write is
one typed, audited action; the route calls `registry.invoke` directly in its
own body.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import request_actor
from fichero_server.api.library_header import optional_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import (
    Artifact,
    ContentRepresentation,
    Document,
    Segment,
    SegmentCarry,
    SegmentDeleted,
    SegmentForwarding,
    SegmentListResponse,
    SegmentMatch,
    SegmentPass,
    SegmentStale,
    SegmentVersion,
)
from fichero_server.models.anchors import SourceAnchor, validate_rect
from fichero_server.models.knowledge import Annotation, ProvenanceKind
from fichero_server.models.segments import (
    TILE_SIZE,
    PassRead,
    ProvisionalSegmentIdError,
    SegmentForwardingLoop,
    SegmentForwardingTooDeep,
    SegmentRead,
    changed_fields,
    assert_not_provisional,
    bbox_and_tile_from_anchor,
    forwards_to,
    grow_rect_by_half_tile,
    legacy_pass_id,
    pass_read_from_row,
    primary_live_segment_id,
    rects_intersect,
    resolve_segment,
    segment_liveness_reason,
    segment_read_from_row,
    segments_from_result,
    snapshot_segment_version,
    tiles_for_rect,
)

router = APIRouter(prefix="/segments")

#: Candidate-row clause for `db._query_where` (#4921 third look): a
#: CONSTANT, no interpolation -- the tile list binds as ONE `$tiles`
#: parameter (`list_contains`), never spliced placeholders. Checked by
#: `tests/unit/db/test_query_where_extra_sql_is_constant.py`.
_AREA_CANDIDATE_SQL = "(list_contains($tiles, tile) OR bbox_w > $tile_size OR bbox_h > $tile_size)"


def _resolve_action_ctx(
    *, actor: str, library_path: str | None, origin_window: str | None, db: Database,
) -> ActionContext:
    return ActionContext(
        actor=actor,
        library_path=library_path or str(db.path.parent),
        origin_window=origin_window,
    )


def _parse_area_param(area: str) -> tuple[float, float, float, float]:
    """``area=x,y,w,h`` (image fractions) -> a validated rect tuple.

    The public contract is a rectangle, the same form and validation as an
    anchor's rect (#4921 review: the 8x8 tile grid is an engine detail and
    must never reach the client). Raises `ValueError` on bad input; the
    route turns that into a 422.
    """
    parts = area.split(",")
    if len(parts) != 4:
        raise ValueError(f"area must be 'x,y,w,h', got {area!r}")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"area must be 'x,y,w,h' of numbers, got {area!r}") from exc
    validate_rect([x, y, w, h])
    return x, y, w, h


def _segment_row_sort_key(row: Segment) -> tuple:
    """Order a pass's real segments by `metadata["box_index"]` when a
    converted box recorded one (slice 6), else `(created_at, id)` -- never
    the bare `id`, which is a random uuid the app's index mapping cannot
    use (#4921 review)."""
    box_index = row.metadata.get("box_index")
    has_box_index = isinstance(box_index, int)
    return (
        0 if has_box_index else 1,
        box_index if has_box_index else 0,
        row.created_at.isoformat() if row.created_at else "",
        row.id,
    )


class SegmentPassMismatchError(ValueError):
    """A segment's `pass_id` names a pass over a DIFFERENT document."""


class SegmentParentMismatchError(ValueError):
    """A segment's `parent_segment_id` names a segment in another pass or
    document."""


class SegmentAnchorMismatchError(ValueError):
    """An anchor's `document_id` does not match the segment's own."""


class SegmentForwardingWouldLoop(ValueError):
    """Merging would close a cycle: `keep_id` already forwards (directly or
    transitively) to the segment being absorbed."""

    def __init__(self, keep_id: str, absorbed_id: str) -> None:
        self.keep_id = keep_id
        self.absorbed_id = absorbed_id
        super().__init__(
            f"cannot merge {absorbed_id!r} into {keep_id!r}: {keep_id!r} "
            f"already forwards to {absorbed_id!r} -- this would close a cycle"
        )


class MatchNeedsAPerson(ValueError):
    """Only a person accepts a match -- a machine's accept is refused."""


class MatchNotAccepted(ValueError):
    """`segment.carry` requires an `accepted` match."""


class SegmentNotLive(ValueError):
    """A merge, split or carry participant has already been deleted or
    merged away (#4922 second look): otherwise merging a deleted segment
    writes a `merged` note newer than its `deleted` one, and a delete
    quietly becomes a merge."""

    def __init__(self, segment_id: str, reason: str) -> None:
        self.segment_id = segment_id
        self.reason = reason
        super().__init__(
            f"segment {segment_id!r} is not live ({reason}) and cannot "
            "take part in this action"
        )


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProvisionalSegmentIdError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, SegmentStale):
        # Carries structured fields (#4923: "carrying segment_id,
        # expected_version, current_version and changed"), not just text --
        # a caller re-reads and retries from these, it does not parse prose.
        return HTTPException(status_code=409, detail={
            "message": str(exc),
            "segment_id": exc.segment_id,
            "expected_version": exc.expected_version,
            "current_version": exc.current_version,
            "changed": exc.changed,
        })
    if isinstance(exc, (SegmentPassMismatchError, SegmentParentMismatchError, SegmentForwardingWouldLoop, SegmentNotLive, SegmentDeleted)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (SegmentAnchorMismatchError, MatchNeedsAPerson, MatchNotAccepted, StatementsCarriedInStatementsStep)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (SegmentForwardingTooDeep, SegmentForwardingLoop)):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def _assert_not_provisional_http(id_value: str | None, *, what: str) -> None:
    """`assert_not_provisional`, converted to a 422 immediately (#4922
    third look: "a legacy: id refused on EVERY action" -- a BARE
    `assert_not_provisional` call raises `ProvisionalSegmentIdError`
    uncaught, which every slice 4 action here used to do, and which
    crashes as a 500 rather than answering 422)."""
    try:
        assert_not_provisional(id_value, what=what)
    except ProvisionalSegmentIdError as exc:
        raise _as_http_error(exc) from exc


def _provenance_kind_from_ctx(ctx: ActionContext) -> ProvenanceKind:
    """Same posture as `_new_pass_provenance_kind` below, without a
    provider/model (matches/merges have neither): a run behind the call
    means a machine did it; a real actor with no run means a person did;
    nothing given is honestly unknown -- never a trusting default."""
    if ctx.run_id:
        return ProvenanceKind.workflow
    if ctx.actor and ctx.actor not in {"", "system"}:
        return ProvenanceKind.human
    return ProvenanceKind.unknown


# ---------------------------------------------------------------------------
# GET /document/{doc_id} — the slice 1 seam, extended to read real rows too
# ---------------------------------------------------------------------------


@router.get("/document/{doc_id}", response_model=SegmentListResponse)
async def list_document_segments(
    doc_id: str,
    artifact_id: Optional[str] = Query(
        None, description="Restrict to one artifact's boxes, or one real pass's source artifact"
    ),
    pass_id: Optional[str] = Query(
        None, description="Restrict to one pass (legacy:<artifact_id>, or a real pass id)"
    ),
    kind: Optional[str] = Query(
        None, description="Restrict to one segment kind (region, line, word, ...)"
    ),
    area: Optional[str] = Query(
        None,
        description=(
            "Restrict to a rectangle, 'x,y,w,h' in image fractions (an anchor's "
            "rect form) -- every segment whose box intersects it comes back."
        ),
    ),
    db: Database = Depends(get_library_database),
) -> SegmentListResponse:
    """The segments of one source page: real `Segment`/`SegmentPass` rows
    where they exist for this document, PLUS the old boxes for artifacts
    that have not been converted (`source.one-store`,
    `source.seam.read-either-store`) — additive, never a replacement; slice 6
    is what converts a page, and nothing does that yet. Opening a page this
    way writes nothing, and a document with neither yet returns an empty
    list, not an error.

    Reads a page's segments **by kind and by area** (`source.store.bounded-reads`):
    `kind` and `area` (a rectangle, `x,y,w,h` in image fractions -- the
    8x8 tile grid a segment is filed under stays an engine detail) both
    narrow the query, together or separately, scoped to one pass at a time
    via its indexed `pass_id` -- never a whole-project scan. "By area" means
    every segment whose box INTERSECTS the rectangle, including a wide
    segment centred outside it.

    **Order.** Passes come back sorted by `(created_at, id)`; a pass's real
    segments are ordered by `metadata["box_index"]` when a converted box
    recorded one, else `(created_at, id)` — never by the bare (random) `id`.
    Legacy segments stay in the artifact's own box order.

    **A bad box never fails the page** (`source.seam.read-either-store`):
    a box the anchor cannot hold still comes back as a segment, with its
    rect/polygon unset and the reason in `metadata["geometry_problem"]`
    (`models/segments.py::_build_anchor`).
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    area_rect: tuple[float, float, float, float] | None = None
    if area:
        try:
            area_rect = _parse_area_param(area)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    by_pass: list[tuple[PassRead, list[SegmentRead]]] = []

    # Real rows first (slice 3). Each pass's OWN `pass_id` is the scope
    # (already narrowed to this document by the SegmentPass query below);
    # `kind`/`area` are additional filters pushed into the SAME indexed
    # query rather than fetched-then-filtered in Python.
    for pass_row in db.query(SegmentPass, document_id=doc_id):
        if pass_row.deleted_at is not None:
            continue
        if pass_id and pass_id != pass_row.id:
            continue
        if artifact_id and pass_row.source_artifact_id != artifact_id:
            continue
        if area_rect:
            # A segment is filed under the tile of its CENTRE only, so a
            # wide segment covering this rectangle could be centred outside
            # every tile it touches, AND a small segment can straddle a
            # tile edge with its centre just outside every touched tile
            # (#4921 review, third look). Candidates are rows in a tile the
            # rectangle GROWN BY HALF A TILE touches, OR bigger than one
            # tile on either axis; true intersection against the stored
            # bbox columns is the real filter, done in Python below.
            ax, ay, aw, ah = area_rect
            tiles = tiles_for_rect(*grow_rect_by_half_tile(ax, ay, aw, ah))
            params = {"tiles": tiles, "tile_size": TILE_SIZE}
            segment_filters: dict = {"pass_id": pass_row.id}
            if kind:
                segment_filters["kind"] = kind
            candidates = db._query_where(Segment, _AREA_CANDIDATE_SQL, params, **segment_filters)
            rows = [
                row
                for row in candidates
                if row.deleted_at is None
                and rects_intersect((row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h), area_rect)
            ]
        else:
            segment_filters = {"pass_id": pass_row.id}
            if kind:
                segment_filters["kind"] = kind
            rows = [row for row in db.query(Segment, **segment_filters) if row.deleted_at is None]
        if not rows and (kind or area_rect):
            continue
        # `metadata["box_index"]` when a converted box recorded one (slice 6),
        # else `(created_at, id)` -- never the bare `id`, which is random and
        # meaningless for the app's index mapping.
        rows.sort(key=_segment_row_sort_key)
        pass_segments = [
            segment_read_from_row(row, box_index=index) for index, row in enumerate(rows)
        ]
        # A pass made from an artifact carries that artifact's type (test-audit
        # B2, App slice A stage 2's notes) -- looked up here, since
        # `pass_read_from_row` has no `db` of its own.
        pass_artifact_type = None
        if pass_row.source_artifact_id:
            source_artifact = db.get(Artifact, pass_row.source_artifact_id)
            if source_artifact:
                pass_artifact_type = source_artifact.artifact_type
        by_pass.append((pass_read_from_row(pass_row, artifact_type=pass_artifact_type), pass_segments))

    # Then the old boxes, for whichever artifacts still carry them
    # (unconverted — every artifact, today, since nothing converts yet).
    query_kwargs: dict = {"document_id": doc_id}
    if artifact_id:
        query_kwargs["id"] = artifact_id
    artifacts = [a for a in db.query(Artifact, **query_kwargs) if a.ocr_geometry]
    for artifact in artifacts:
        this_pass_id = legacy_pass_id(artifact.id)
        if pass_id and pass_id != this_pass_id:
            continue
        pass_read, artifact_segments = segments_from_result(
            document_id=doc_id,
            artifact_id=artifact.id,
            result=artifact.ocr_geometry,
            provider=artifact.provider,
            model=artifact.model,
            run_id=artifact.run_id,
            created_at=artifact.created_at,
            artifact_type=artifact.artifact_type,
        )
        if kind:
            artifact_segments = [s for s in artifact_segments if s.kind == kind]
        if not artifact_segments and kind:
            # A kind filter that matched nothing on this artifact still
            # names its pass, once — but naming an EMPTY pass adds noise
            # with no segments behind it, so it is skipped rather than
            # returned with a dangling reference.
            continue
        by_pass.append((pass_read, artifact_segments))

    # Sort key as a string, not the datetime itself: `created_at` may be
    # `None` (no honest fallback exists), and comparing `None` against a
    # `datetime` raises — an empty string sorts first, which is the right
    # place for "unknown" anyway.
    by_pass.sort(key=lambda entry: (entry[0].created_at.isoformat() if entry[0].created_at else "", entry[0].id))

    passes = [pass_read for pass_read, _ in by_pass]
    segments = [segment for _, pass_segments in by_pass for segment in pass_segments]

    return SegmentListResponse(document_id=doc_id, passes=passes, segments=segments)


# ---------------------------------------------------------------------------
# Slice 3 writes
# ---------------------------------------------------------------------------


class SegmentPassCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    name: str
    run_id: Optional[str] = None
    source_artifact_id: Optional[str] = None


def _new_pass_provenance_kind(
    *, actor: str, run_id: str | None, provider: str | None, model: str | None,
) -> ProvenanceKind:
    """Set by the engine from how the write arrived: a run or a
    provider/model behind it means a machine made this pass; a real actor
    with neither means a person did; nothing given is honestly unknown --
    never a trusting default (same posture as `_derive_pass_provenance_kind`
    for a legacy artifact)."""
    if run_id or provider or model:
        return ProvenanceKind.workflow
    if actor and actor not in {"", "system"}:
        return ProvenanceKind.human
    return ProvenanceKind.unknown


def _create_pass_impl(db: Database, params: SegmentPassCreateParams, ctx: ActionContext) -> SegmentPass:
    assert_not_provisional(params.document_id, what="document_id")
    if params.source_artifact_id:
        assert_not_provisional(params.source_artifact_id, what="source_artifact_id")

    provider = model = None
    if params.source_artifact_id:
        source_artifact = db.get(Artifact, params.source_artifact_id)
        if source_artifact:
            provider, model = source_artifact.provider, source_artifact.model

    pass_row = SegmentPass(
        document_id=params.document_id,
        name=params.name,
        provenance_kind=_new_pass_provenance_kind(
            actor=ctx.actor, run_id=params.run_id, provider=provider, model=model,
        ),
        actor=ctx.actor,
        provider=provider,
        model=model,
        run_id=params.run_id,
        source_artifact_id=params.source_artifact_id,
    )
    db.save(pass_row)
    return pass_row


def _invert_pass_create(before, after, ctx: ActionContext):
    if not after:
        return None
    pass_id = after.get("pass_id")
    if not pass_id:
        return None
    return ("segment.pass_delete", {"pass_id": pass_id})


@action(
    "segment.pass_create",
    SegmentPassCreateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_pass_create,
)
def _action_pass_create(db: Database, params: SegmentPassCreateParams, ctx: ActionContext):
    try:
        pass_row = _create_pass_impl(db, params, ctx)
    except (ProvisionalSegmentIdError,) as exc:
        raise _as_http_error(exc) from exc
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[pass_row.id],
        before=None,
        after={"pass_id": pass_row.id},
        emit_type="pass.created",
        pass_ids=[pass_row.id],
        document_ids=[pass_row.document_id],
    )
    return pass_row.model_dump(mode="json"), spec


class SegmentPassDeleteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str


def _invert_pass_delete(before, after, ctx: ActionContext):
    if not before:
        return None
    pass_id = before.get("pass_id")
    if not pass_id:
        return None
    return ("segment.pass_restore", {"pass_id": pass_id})


@action(
    "segment.pass_delete",
    SegmentPassDeleteParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_pass_delete,
)
def _action_pass_delete(db: Database, params: SegmentPassDeleteParams, ctx: ActionContext):
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if not pass_row:
        raise HTTPException(status_code=404, detail=f"Pass not found: {params.pass_id}")
    from fichero_server.core.timeutil import utc_now

    pass_row.deleted_at = utc_now()
    db.save(pass_row)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[pass_row.id],
        before={"pass_id": pass_row.id},
        after=None,
        emit_type="pass.deleted",
        pass_ids=[pass_row.id],
        document_ids=[pass_row.document_id],
    )
    return {"pass_id": pass_row.id}, spec


class SegmentPassRestoreParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str


@action("segment.pass_restore", SegmentPassRestoreParams, domains=["segment"], undoable=False)
def _action_pass_restore(db: Database, params: SegmentPassRestoreParams, ctx: ActionContext):
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if not pass_row:
        raise HTTPException(status_code=404, detail=f"Pass not found: {params.pass_id}")
    pass_row.deleted_at = None
    db.save(pass_row)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[pass_row.id],
        before=None,
        after={"pass_id": pass_row.id},
        emit_type="pass.created",
        pass_ids=[pass_row.id],
        document_ids=[pass_row.document_id],
    )
    return {"pass_id": pass_row.id}, spec


def _validate_segment_placement(
    db: Database, *, document_id: str, pass_id: str, parent_segment_id: str | None,
    anchor: SourceAnchor,
) -> None:
    pass_row = db.get(SegmentPass, pass_id)
    if not pass_row or pass_row.document_id != document_id:
        raise SegmentPassMismatchError(
            f"pass {pass_id!r} is not a pass over document {document_id!r}"
        )
    if parent_segment_id:
        parent = db.get(Segment, parent_segment_id)
        if not parent or parent.pass_id != pass_id or parent.document_id != document_id:
            raise SegmentParentMismatchError(
                f"parent segment {parent_segment_id!r} is not in pass {pass_id!r} "
                f"of document {document_id!r}"
            )
    if anchor.document_id != document_id:
        raise SegmentAnchorMismatchError(
            f"anchor's document_id {anchor.document_id!r} does not match "
            f"the segment's document_id {document_id!r}"
        )


class SegmentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    anchor: SourceAnchor
    baseline: Optional[list[list[float]]] = None
    parent_segment_id: Optional[str] = None
    kind_raw: Optional[str] = None


def _build_segment_row(
    *, document_id: str, pass_id: str, spec: SegmentSpec, actor: str,
    provenance_kind: ProvenanceKind,
) -> Segment:
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(spec.anchor)
    return Segment(
        document_id=document_id,
        pass_id=pass_id,
        parent_segment_id=spec.parent_segment_id,
        kind=spec.kind,
        kind_raw=spec.kind_raw,
        anchor=spec.anchor,
        baseline=spec.baseline,
        bbox_x=bbox_x, bbox_y=bbox_y, bbox_w=bbox_w, bbox_h=bbox_h, tile=tile,
        doc_kind=f"{document_id}:{spec.kind}",
        provenance_kind=provenance_kind,
        created_by=actor,
    )


class SegmentCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    pass_id: str
    kind: str
    anchor: SourceAnchor
    baseline: Optional[list[list[float]]] = None
    parent_segment_id: Optional[str] = None
    kind_raw: Optional[str] = None


def _invert_segment_create(before, after, ctx: ActionContext):
    if not after:
        return None
    segment_ids = after.get("segment_ids")
    if not segment_ids:
        return None
    # A freshly created segment is always at version 1 (slice 5, #4923: real
    # `segment.delete` now takes a compare-and-set, so its inverse must
    # supply one) -- if something else touched it since creation, the
    # compare-and-set correctly refuses this undo as stale, which is right.
    return (
        "segment.delete",
        {"segment_ids": segment_ids, "expected_versions": {sid: 1 for sid in segment_ids}},
    )


@action(
    "segment.create",
    SegmentCreateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_create,
)
def _action_segment_create(db: Database, params: SegmentCreateParams, ctx: ActionContext):
    _assert_not_provisional_http(params.document_id, what="document_id")
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    if params.parent_segment_id:
        _assert_not_provisional_http(params.parent_segment_id, what="parent_segment_id")
    try:
        _validate_segment_placement(
            db, document_id=params.document_id, pass_id=params.pass_id,
            parent_segment_id=params.parent_segment_id, anchor=params.anchor,
        )
    except (SegmentPassMismatchError, SegmentParentMismatchError, SegmentAnchorMismatchError) as exc:
        raise _as_http_error(exc) from exc

    pass_row = db.get(SegmentPass, params.pass_id)
    spec_obj = SegmentSpec(
        kind=params.kind, anchor=params.anchor, baseline=params.baseline,
        parent_segment_id=params.parent_segment_id, kind_raw=params.kind_raw,
    )
    segment = _build_segment_row(
        document_id=params.document_id, pass_id=params.pass_id, spec=spec_obj,
        actor=ctx.actor, provenance_kind=pass_row.provenance_kind,
    )
    db.save(segment)
    change_spec = ChangeSpec(
        domains=["segment"],
        target_ids=[segment.id],
        before=None,
        after={"segment_ids": [segment.id]},
        emit_type="segment.created",
        segment_ids=[segment.id],
        pass_ids=[segment.pass_id],
        document_ids=[segment.document_id],
    )
    return {"segment_ids": [segment.id]}, change_spec


class SegmentCreateManyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    pass_id: str
    segments: list[SegmentSpec]


@action(
    "segment.create_many",
    SegmentCreateManyParams,
    domains=["segment"],
    undoable=True,
    # atomic=True like every other action (#4921 review): `save_many` now
    # joins the registry's ambient `with db.transaction():` via the
    # re-entrant `Database.transaction()` instead of issuing its own raw
    # BEGIN, so the rows and the audit row commit or roll back together --
    # a failed audit write can no longer leave segment rows with no record.
    invert=_invert_segment_create,
)
def _action_segment_create_many(db: Database, params: SegmentCreateManyParams, ctx: ActionContext):
    _assert_not_provisional_http(params.document_id, what="document_id")
    _assert_not_provisional_http(params.pass_id, what="pass_id")

    pass_row = db.get(SegmentPass, params.pass_id)
    rows: list[Segment] = []
    for spec in params.segments:
        if spec.parent_segment_id:
            _assert_not_provisional_http(spec.parent_segment_id, what="parent_segment_id")
        try:
            _validate_segment_placement(
                db, document_id=params.document_id, pass_id=params.pass_id,
                parent_segment_id=spec.parent_segment_id, anchor=spec.anchor,
            )
        except (SegmentPassMismatchError, SegmentParentMismatchError, SegmentAnchorMismatchError) as exc:
            raise _as_http_error(exc) from exc
        rows.append(
            _build_segment_row(
                document_id=params.document_id, pass_id=params.pass_id, spec=spec,
                actor=ctx.actor, provenance_kind=pass_row.provenance_kind,
            )
        )
    db.save_many(rows)
    segment_ids = [row.id for row in rows]
    change_spec = ChangeSpec(
        domains=["segment"],
        target_ids=segment_ids,
        before=None,
        after={"segment_ids": segment_ids},
        emit_type="segment.created",
        segment_ids=segment_ids,
        pass_ids=[params.pass_id],
        document_ids=[params.document_id],
    )
    return {"segment_ids": segment_ids}, change_spec


def _stale_changed_fields(db: Database, segment_id: str, expected_version: int, current_row: Segment) -> list[str]:
    """`SegmentStale.changed`: the field names that differ between the
    version the caller thought it was editing (the `SegmentVersion` row
    tagged with `expected_version` -- every bump past it writes exactly
    one, as a preimage) and the CURRENT live row. `[]` if that version was
    never snapshotted (expected_version was never actually superseded)."""
    candidates = db.query(SegmentVersion, segment_id=segment_id, version=expected_version)
    if not candidates:
        return []
    return changed_fields(candidates[0], current_row)


def _same_pass_and_document(db: Database, segment_ids: list[str]) -> dict[str, Segment]:
    """Fetch every id, 404 on a miss, and refuse (`SegmentPassMismatchError`,
    409) if they do not all share one pass and document -- the same rule
    `segment.merge` enforces, applied to every action that takes several
    segment ids together (#4923: "refusals from slices 3 and 4 apply to
    every new action")."""
    rows: dict[str, Segment] = {}
    for segment_id in segment_ids:
        row = db.get(Segment, segment_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        rows[segment_id] = row
    first = next(iter(rows.values()))
    for row in rows.values():
        if row.pass_id != first.pass_id or row.document_id != first.document_id:
            raise _as_http_error(SegmentPassMismatchError(
                "segments are not all in the same pass and document"
            ))
    return rows


class SegmentDeleteParams(BaseModel):
    """The real, versioned delete (`source.segment.delete-is-undoable`):
    compare-and-set per id, a `SegmentVersion` snapshot, and a `deleted`
    forwarding row -- replaces slice 3's internal stand-in (which only set
    `deleted_at`, undoable=False)."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str]
    expected_versions: dict[str, int]
    #: Capped (#4923 review): recorded inside the tamper-evident audit
    #: chain, where nothing can ever be purged -- an operator's short note
    #: about the delete, never a quote from a source. Whether even a short
    #: typed field belongs in the chain at all is the maintainer's open
    #: question (morning file, question 17/23), not settled here.
    reason: Optional[str] = Field(default=None, max_length=200)


def _invert_segment_delete(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look: "every inverse in this file
    follows one rule") -- `after["versions"]` is the state POST-delete
    (after `snapshot_segment_version`'s bump), which is what `undelete`
    (itself taking no `expected_version`) needs the ids for."""
    if not after:
        return None
    versions = after.get("versions")
    if not versions:
        return None
    return ("segment.undelete", {"segment_ids": list(versions.keys())})


@action(
    "segment.delete",
    SegmentDeleteParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_delete,
)
def _action_segment_delete(db: Database, params: SegmentDeleteParams, ctx: ActionContext):
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
        if segment_id not in params.expected_versions:
            raise HTTPException(
                status_code=422, detail=f"expected_versions is missing segment_id {segment_id!r}"
            )
    rows = _same_pass_and_document(db, params.segment_ids)

    now = utc_now()
    audit_id = uuid.uuid4().hex
    before_versions: dict[str, int] = {}
    after_versions: dict[str, int] = {}
    document_ids: set[str] = set()
    pass_ids: set[str] = set()
    for segment_id in params.segment_ids:
        row = rows[segment_id]
        if row.deleted_at is not None:
            raise _as_http_error(SegmentDeleted(segment_id))
        expected = params.expected_versions[segment_id]
        if row.version != expected:
            raise _as_http_error(SegmentStale(
                segment_id, expected, row.version,
                _stale_changed_fields(db, segment_id, expected, row),
            ))
        before_versions[segment_id] = row.version
        snapshot_segment_version(
            db, row, deleted=True, actor=ctx.actor, audit_id=audit_id, reason=params.reason,
        )
        row.deleted_at = now
        row.deleted_by = ctx.actor
        db.save(row)
        after_versions[segment_id] = row.version
        db.save(SegmentForwarding(
            document_id=row.document_id, old_segment_id=segment_id, kind="deleted",
            new_segment_ids=[], actor=ctx.actor, audit_id=audit_id, reason=params.reason,
            sequence=db.next_forwarding_sequence(),
        ))
        document_ids.add(row.document_id)
        pass_ids.add(row.pass_id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=list(params.segment_ids),
        before=before_versions,
        after={"segment_ids": params.segment_ids, "versions": after_versions},
        emit_type="segment.deleted",
        segment_ids=list(params.segment_ids),
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": params.segment_ids}, spec


class SegmentUndeleteParams(BaseModel):
    """`segment.delete`'s inverse -- also directly callable to bring a
    deleted segment back (`source.segment.delete-is-undoable`).

    Takes no `expected_version` (#4923 second look): a deleted segment
    cannot change -- `update`, `merge`, `split` and `carry` all refuse a
    not-live participant -- so "is it deleted" (checked below) is the
    WHOLE precondition. A stale undelete (already live) is a plain 409,
    not a `SegmentStale`."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str]


def _invert_segment_undelete(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look) -- `after["versions"]` is
    the state POST-undelete (after the bump), exactly what `segment.delete`
    needs as `expected_versions` to undo THIS undelete without meeting a
    stale row."""
    if not after:
        return None
    versions = after.get("versions")
    if not versions:
        return None
    return ("segment.delete", {"segment_ids": list(versions.keys()), "expected_versions": versions})


@action(
    "segment.undelete",
    SegmentUndeleteParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_undelete,
)
def _action_segment_undelete(db: Database, params: SegmentUndeleteParams, ctx: ActionContext):
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
    rows = _same_pass_and_document(db, params.segment_ids)

    audit_id = uuid.uuid4().hex
    before_versions: dict[str, int] = {}
    after_versions: dict[str, int] = {}
    document_ids: set[str] = set()
    pass_ids: set[str] = set()
    for segment_id in params.segment_ids:
        row = rows[segment_id]
        if row.deleted_at is None:
            raise HTTPException(status_code=409, detail=f"segment {segment_id!r} is not deleted")
        before_versions[segment_id] = row.version
        snapshot_segment_version(db, row, deleted=True, actor=ctx.actor, audit_id=audit_id)
        row.deleted_at = None
        row.deleted_by = None
        db.save(row)
        after_versions[segment_id] = row.version
        db.save(SegmentForwarding(
            document_id=row.document_id, old_segment_id=segment_id, kind="restored",
            new_segment_ids=[], actor=ctx.actor, audit_id=audit_id,
            sequence=db.next_forwarding_sequence(),
        ))
        document_ids.add(row.document_id)
        pass_ids.add(row.pass_id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=list(params.segment_ids),
        before=before_versions,
        after={"segment_ids": params.segment_ids, "versions": after_versions},
        emit_type="segment.restored",
        segment_ids=list(params.segment_ids),
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": params.segment_ids}, spec


class SegmentUpdateParams(BaseModel):
    """`document_id`/`pass_id` are deliberately absent (`extra="forbid"`
    refuses them outright) -- a segment never moves pass or document
    (`source.pass.never-overwrites`); that is a merge, not an update."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    expected_version: int
    anchor: Optional[SourceAnchor] = None
    baseline: Optional[list[list[float]]] = None
    kind: Optional[str] = None
    kind_raw: Optional[str] = None
    parent_segment_id: Optional[str] = None
    is_furniture: Optional[bool] = None


def _invert_via_previous_version(before, after, ctx: ActionContext):
    """`segment.update`/`.restore_version`'s shared inverse -- deliberately
    reads ONLY `after` (#4923: "undo restores from ordinary data", proven
    by a test that BLANKS the audit row's `before` and still restores).
    `snapshot_segment_version` always writes exactly one preimage (tagged
    with the OLD version number) and bumps by exactly one, so the version
    to restore to is ALWAYS `after.version - 1` -- true for undoing an
    update, a delete, an undelete, or a restore_version alike, without
    ever needing the audit's own `before`."""
    if not after:
        return None
    segment_id = after.get("segment_id")
    version = after.get("version")
    if not segment_id or not version:
        return None
    return (
        "segment.restore_version",
        {"segment_id": segment_id, "version": version - 1, "expected_version": version},
    )


_invert_segment_update = _invert_via_previous_version


@action(
    "segment.update",
    SegmentUpdateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_update,
)
def _action_segment_update(db: Database, params: SegmentUpdateParams, ctx: ActionContext):
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    if params.parent_segment_id:
        _assert_not_provisional_http(params.parent_segment_id, what="parent_segment_id")
    row = db.get(Segment, params.segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    if row.deleted_at is not None:
        raise _as_http_error(SegmentDeleted(params.segment_id))
    if row.version != params.expected_version:
        raise _as_http_error(SegmentStale(
            params.segment_id, params.expected_version, row.version,
            _stale_changed_fields(db, params.segment_id, params.expected_version, row),
        ))
    if params.anchor is not None and params.anchor.document_id != row.document_id:
        raise _as_http_error(SegmentAnchorMismatchError(
            f"anchor's document_id {params.anchor.document_id!r} does not "
            f"match the segment's document_id {row.document_id!r}"
        ))
    if params.parent_segment_id:
        parent = db.get(Segment, params.parent_segment_id)
        if not parent or parent.pass_id != row.pass_id or parent.document_id != row.document_id:
            raise _as_http_error(SegmentParentMismatchError(
                f"parent segment {params.parent_segment_id!r} is not in pass "
                f"{row.pass_id!r} of document {row.document_id!r}"
            ))

    audit_id = uuid.uuid4().hex
    before_version = row.version
    snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)

    if params.anchor is not None:
        row.anchor = params.anchor
        bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
        row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
    if params.baseline is not None:
        row.baseline = params.baseline
    if params.kind is not None:
        row.kind = params.kind
        row.doc_kind = f"{row.document_id}:{row.kind}"
    if params.kind_raw is not None:
        row.kind_raw = params.kind_raw
    if params.parent_segment_id is not None:
        row.parent_segment_id = params.parent_segment_id
    if params.is_furniture is not None:
        row.is_furniture = params.is_furniture
    db.save(row)

    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[row.id],
        before={"segment_id": row.id, "version": before_version},
        after={"segment_id": row.id, "version": row.version},
        emit_type="segment.updated",
        segment_ids=[row.id],
        pass_ids=[row.pass_id],
        document_ids=[row.document_id],
    )
    return {"segment_id": row.id, "version": row.version}, spec


class SegmentRestoreVersionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    version: int
    expected_version: int


_invert_segment_restore_version = _invert_via_previous_version


@action(
    "segment.restore_version",
    SegmentRestoreVersionParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_restore_version,
)
def _action_segment_restore_version(db: Database, params: SegmentRestoreVersionParams, ctx: ActionContext):
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    row = db.get(Segment, params.segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    if row.deleted_at is not None:
        raise _as_http_error(SegmentDeleted(params.segment_id))
    if row.version != params.expected_version:
        raise _as_http_error(SegmentStale(
            params.segment_id, params.expected_version, row.version,
            _stale_changed_fields(db, params.segment_id, params.expected_version, row),
        ))

    # Scoped by (segment_id, version) together -- can never target another
    # segment's row by construction (#4922-style review question, answered
    # the same way here: "restoring a version of another segment" is a 404,
    # never a silent cross-segment hit).
    candidates = db.query(SegmentVersion, segment_id=params.segment_id, version=params.version)
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"segment {params.segment_id!r} has no version {params.version}",
        )
    target = candidates[0]

    audit_id = uuid.uuid4().hex
    before_version = row.version
    snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)

    row.anchor = target.anchor
    row.baseline = target.baseline
    row.kind = target.kind
    row.kind_raw = target.kind_raw
    row.parent_segment_id = target.parent_segment_id
    row.is_furniture = target.is_furniture
    row.doc_kind = f"{row.document_id}:{row.kind}"
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
    row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
    db.save(row)

    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[row.id],
        before={"segment_id": row.id, "version": before_version},
        after={"segment_id": row.id, "version": row.version},
        emit_type="segment.updated",
        segment_ids=[row.id],
        pass_ids=[row.pass_id],
        document_ids=[row.document_id],
    )
    return {"segment_id": row.id, "version": row.version}, spec


# ---------------------------------------------------------------------------
# Slice 4 (#4922) -- matches, forwarding notes, a citable reference
# ---------------------------------------------------------------------------


class SegmentMatchProposeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_segment_id: str
    to_segment_id: str
    certainty: Optional[float] = None
    #: Capped (#4923 review): this is recorded inside the tamper-evident
    #: audit chain, where nothing can ever be purged -- an operator's short
    #: note about the match, never a quote from a source. Whether even a
    #: short typed field belongs in the chain at all is the maintainer's
    #: open question (morning file, question 17/23), not settled here.
    note: Optional[str] = Field(default=None, max_length=200)


def _invert_match_propose(before, after, ctx: ActionContext):
    if not after:
        return None
    match_id = after.get("match_id")
    if not match_id:
        return None
    return ("segment.match_withdraw", {"match_id": match_id})


@action(
    "segment.match_propose",
    SegmentMatchProposeParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_match_propose,
)
def _action_match_propose(db: Database, params: SegmentMatchProposeParams, ctx: ActionContext):
    _assert_not_provisional_http(params.from_segment_id, what="from_segment_id")
    _assert_not_provisional_http(params.to_segment_id, what="to_segment_id")
    from_row = db.get(Segment, params.from_segment_id)
    to_row = db.get(Segment, params.to_segment_id)
    if not from_row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.from_segment_id}")
    if not to_row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.to_segment_id}")

    match = SegmentMatch(
        document_id=from_row.document_id,
        from_segment_id=params.from_segment_id,
        to_segment_id=params.to_segment_id,
        state="proposed",
        proposed_by_kind=_provenance_kind_from_ctx(ctx),
        proposed_by=ctx.actor,
        certainty=params.certainty,
        note=params.note,
    )
    db.save(match)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[match.id],
        before=None,
        after={"match_id": match.id},
        emit_type="segment.matched",
        segment_ids=[params.from_segment_id, params.to_segment_id],
        document_ids=[from_row.document_id],
    )
    return {"match_id": match.id}, spec


class SegmentMatchWithdrawParams(BaseModel):
    """Internal: `segment.match_propose`'s inverse only."""

    model_config = ConfigDict(extra="forbid")

    match_id: str


@action("segment.match_withdraw", SegmentMatchWithdrawParams, domains=["segment"], undoable=False)
def _action_match_withdraw(db: Database, params: SegmentMatchWithdrawParams, ctx: ActionContext):
    match = db.get(SegmentMatch, params.match_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"Match not found: {params.match_id}")
    db.delete(match)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[params.match_id],
        before={"match_id": params.match_id},
        after=None,
        emit_type="segment.matched",
        segment_ids=[match.from_segment_id, match.to_segment_id],
        document_ids=[match.document_id],
    )
    return {"match_id": params.match_id}, spec


class SegmentMatchIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str


def _invert_match_state_change(before, after, ctx: ActionContext):
    if not before or not after:
        return None
    return (
        "segment.match_set_state",
        {"match_id": after.get("match_id"), "state": before.get("state")},
    )


@action(
    "segment.match_accept",
    SegmentMatchIdParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_match_state_change,
)
def _action_match_accept(db: Database, params: SegmentMatchIdParams, ctx: ActionContext):
    match = db.get(SegmentMatch, params.match_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"Match not found: {params.match_id}")
    if _provenance_kind_from_ctx(ctx) != ProvenanceKind.human:
        raise _as_http_error(MatchNeedsAPerson("only a person can accept a match"))
    before_state = match.state
    match.state = "accepted"
    match.accepted_by = ctx.actor
    match.accepted_at = utc_now()
    db.save(match)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[match.id],
        before={"match_id": match.id, "state": before_state},
        after={"match_id": match.id, "state": match.state},
        emit_type="segment.matched",
        segment_ids=[match.from_segment_id, match.to_segment_id],
        document_ids=[match.document_id],
    )
    return {"match_id": match.id, "state": match.state}, spec


@action(
    "segment.match_reject",
    SegmentMatchIdParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_match_state_change,
)
def _action_match_reject(db: Database, params: SegmentMatchIdParams, ctx: ActionContext):
    match = db.get(SegmentMatch, params.match_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"Match not found: {params.match_id}")
    before_state = match.state
    match.state = "rejected"
    db.save(match)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[match.id],
        before={"match_id": match.id, "state": before_state},
        after={"match_id": match.id, "state": match.state},
        emit_type="segment.matched",
        segment_ids=[match.from_segment_id, match.to_segment_id],
        document_ids=[match.document_id],
    )
    return {"match_id": match.id, "state": match.state}, spec


class SegmentMatchSetStateParams(BaseModel):
    """Internal: `segment.match_accept`/`.match_reject`'s inverse only."""

    model_config = ConfigDict(extra="forbid")

    match_id: str
    state: str


@action("segment.match_set_state", SegmentMatchSetStateParams, domains=["segment"], undoable=False)
def _action_match_set_state(db: Database, params: SegmentMatchSetStateParams, ctx: ActionContext):
    match = db.get(SegmentMatch, params.match_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"Match not found: {params.match_id}")
    match.state = params.state
    if params.state != "accepted":
        match.accepted_by = None
        match.accepted_at = None
    db.save(match)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[match.id],
        before=None,
        after={"match_id": match.id, "state": match.state},
        emit_type="segment.matched",
        segment_ids=[match.from_segment_id, match.to_segment_id],
        document_ids=[match.document_id],
    )
    return {"match_id": match.id, "state": match.state}, spec


# --- merge / unmerge ---------------------------------------------------


class SegmentMergeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str]
    keep_id: str


def _invert_merge(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look: "no inverse takes geometry
    from the audit record; inverses carry ids and version numbers, read
    from after") -- `after["absorbed_versions"]` names each absorbed
    segment's PRE-merge version, which `segment.unmerge` restores FROM THE
    SNAPSHOT `segment.merge` already wrote (never from this dict's own
    content -- it carries no geometry)."""
    if not after:
        return None
    absorbed_versions = after.get("absorbed_versions")
    if not absorbed_versions:
        return None
    return ("segment.unmerge", {"versions": absorbed_versions})


@action(
    "segment.merge",
    SegmentMergeParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_merge,
)
def _action_merge(db: Database, params: SegmentMergeParams, ctx: ActionContext):
    if len(params.segment_ids) < 2:
        raise HTTPException(status_code=422, detail="merge needs two or more segment_ids")
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
    _assert_not_provisional_http(params.keep_id, what="keep_id")
    if params.keep_id not in params.segment_ids:
        raise HTTPException(
            status_code=422, detail=f"keep_id {params.keep_id!r} is not among segment_ids"
        )

    rows: dict[str, Segment] = {}
    for segment_id in params.segment_ids:
        row = db.get(Segment, segment_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        rows[segment_id] = row
    keep_row = rows[params.keep_id]
    first = next(iter(rows.values()))
    for row in rows.values():
        if row.pass_id != first.pass_id or row.document_id != first.document_id:
            raise _as_http_error(
                SegmentPassMismatchError(
                    "segments being merged are not all in the same pass and document"
                )
            )

    # #4922 second look: EVERY participant, including keep_id, must be
    # LIVE -- otherwise a soft-deleted segment could be "merged", writing
    # a `merged` note NEWER than its `deleted` one, quietly turning a
    # delete into a merge.
    for segment_id in params.segment_ids:
        reason = segment_liveness_reason(db, segment_id)
        if reason is not None:
            raise _as_http_error(SegmentNotLive(segment_id, reason))

    absorbed_ids = [sid for sid in params.segment_ids if sid != params.keep_id]
    for absorbed_id in absorbed_ids:
        # #4922 review: merging into a segment that ALREADY FORWARDS TO the
        # one being absorbed would close a cycle -- refused before anything
        # is written. With every participant now confirmed live, above,
        # this can only ever be true for keep_id == absorbed_id (a live id
        # forwards nowhere) -- the safety net its docstring says it is.
        if forwards_to(db, params.keep_id, absorbed_id):
            raise _as_http_error(SegmentForwardingWouldLoop(params.keep_id, absorbed_id))

    audit_id = uuid.uuid4().hex
    absorbed_versions: dict[str, int] = {}
    forwarding_ids = []
    now = utc_now()
    for absorbed_id in absorbed_ids:
        row = rows[absorbed_id]
        pre_merge_version = row.version
        # #4923: every action that changes a segment writes the version
        # snapshot (preimage) and bumps `Segment.version` -- merge and
        # split are named explicitly as needing this. `unmerge` restores
        # FROM this exact snapshot (segment_id, pre_merge_version), never
        # from geometry carried in the audit's own before/after.
        snapshot_segment_version(db, row, deleted=True, actor=ctx.actor, audit_id=audit_id)
        row.deleted_at = now
        row.deleted_by = ctx.actor
        db.save(row)
        absorbed_versions[absorbed_id] = pre_merge_version
        forwarding = SegmentForwarding(
            document_id=row.document_id,
            old_segment_id=absorbed_id,
            kind="merged",
            new_segment_ids=[params.keep_id],
            actor=ctx.actor,
            audit_id=audit_id,
            sequence=db.next_forwarding_sequence(),
        )
        db.save(forwarding)
        forwarding_ids.append(forwarding.id)

    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[params.keep_id, *absorbed_ids],
        before=None,
        after={
            "kept_id": params.keep_id, "forwarding_ids": forwarding_ids,
            "absorbed_versions": absorbed_versions,
        },
        emit_type="segment.merged",
        segment_ids=[params.keep_id, *absorbed_ids],
        pass_ids=[keep_row.pass_id],
        document_ids=[keep_row.document_id],
    )
    return {"kept_id": params.keep_id, "forwarding_ids": forwarding_ids}, spec


class SegmentUnmergeParams(BaseModel):
    """Internal: `segment.merge`'s inverse only. Ids and version numbers
    ONLY (#4923 second look) -- geometry is never carried here; each
    absorbed segment is restored from the `SegmentVersion` snapshot
    `segment.merge` itself wrote, the SAME path `segment.restore_version`
    uses, so a segment's state comes back by exactly one path."""

    model_config = ConfigDict(extra="forbid")

    #: segment_id -> the version to restore it to (its own pre-merge
    #: version; the snapshot at that number is what merge itself wrote).
    versions: dict[str, int]


@action("segment.unmerge", SegmentUnmergeParams, domains=["segment"], undoable=False)
def _action_unmerge(db: Database, params: SegmentUnmergeParams, ctx: ActionContext):
    audit_id = uuid.uuid4().hex
    restored_ids = []
    document_ids: set[str] = set()
    pass_ids: set[str] = set()
    for segment_id, version in params.versions.items():
        _assert_not_provisional_http(segment_id, what="segment_id")
        row = db.get(Segment, segment_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        # #4923 second look: restore FROM THE SNAPSHOT merge itself wrote --
        # the SAME path `segment.restore_version` uses, never a second
        # restore path built from the audit's own params.
        candidates = db.query(SegmentVersion, segment_id=segment_id, version=version)
        if not candidates:
            raise HTTPException(
                status_code=404, detail=f"segment {segment_id!r} has no version {version}"
            )
        target = candidates[0]
        # The version only ever goes UP: a fresh preimage of the CURRENT
        # (still merged-away) state, then apply the target's fields --
        # never `row.version = version` (that would move it BACKWARDS).
        snapshot_segment_version(db, row, deleted=True, actor=ctx.actor, audit_id=audit_id)
        row.anchor = target.anchor
        row.baseline = target.baseline
        row.kind = target.kind
        row.kind_raw = target.kind_raw
        row.parent_segment_id = target.parent_segment_id
        row.is_furniture = target.is_furniture
        row.doc_kind = f"{row.document_id}:{row.kind}"
        bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
        row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
        row.deleted_at = None
        row.deleted_by = None
        db.save(row)
        db.save(SegmentForwarding(
            document_id=row.document_id,
            old_segment_id=segment_id,
            kind="restored",
            new_segment_ids=[],
            actor=ctx.actor,
            audit_id=audit_id,
            sequence=db.next_forwarding_sequence(),
        ))
        restored_ids.append(segment_id)
        document_ids.add(row.document_id)
        pass_ids.add(row.pass_id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=restored_ids,
        before=None,
        after={"segment_ids": restored_ids},
        emit_type="segment.merged",
        segment_ids=restored_ids,
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": restored_ids}, spec


# --- split / unsplit -----------------------------------------------------


class SegmentSplitPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: SourceAnchor
    baseline: Optional[list[list[float]]] = None


class SegmentSplitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    parts: list[SegmentSplitPart]


def _invert_split(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look) -- `pre_split_version` names
    the snapshot `segment.split` itself wrote for the kept id; `unsplit`
    restores FROM IT, never from geometry carried here."""
    if not after:
        return None
    segment_id = after.get("kept_id")
    pre_split_version = after.get("pre_split_version")
    if not segment_id or pre_split_version is None:
        return None
    return (
        "segment.unsplit",
        {
            "segment_id": segment_id, "version": pre_split_version,
            "new_segment_ids": after.get("new_segment_ids", []),
        },
    )


@action(
    "segment.split",
    SegmentSplitParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_split,
)
def _action_split(db: Database, params: SegmentSplitParams, ctx: ActionContext):
    if len(params.parts) < 2:
        raise HTTPException(status_code=422, detail="split needs two or more parts")
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    original = db.get(Segment, params.segment_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    reason = segment_liveness_reason(db, params.segment_id)
    if reason is not None:
        raise _as_http_error(SegmentNotLive(params.segment_id, reason))
    for part in params.parts:
        if part.anchor.document_id != original.document_id:
            raise _as_http_error(SegmentAnchorMismatchError(
                f"part anchor's document_id {part.anchor.document_id!r} does not "
                f"match the segment's document_id {original.document_id!r}"
            ))

    audit_id = uuid.uuid4().hex
    pre_split_version = original.version
    # #4923: every action that changes a segment writes the version
    # snapshot (preimage) and bumps `Segment.version` -- named explicitly
    # for merge and split. `unsplit` restores FROM this exact snapshot
    # (segment_id, pre_split_version) -- the audit's own before/after
    # carries no geometry, only this version number.
    snapshot_segment_version(db, original, deleted=False, actor=ctx.actor, audit_id=audit_id)

    first_part, *rest_parts = params.parts
    original.anchor = first_part.anchor
    original.baseline = first_part.baseline
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(original.anchor)
    original.bbox_x, original.bbox_y, original.bbox_w, original.bbox_h, original.tile = (
        bbox_x, bbox_y, bbox_w, bbox_h, tile,
    )
    db.save(original)

    new_ids: list[str] = []
    new_rows: list[Segment] = []
    for part in rest_parts:
        spec_obj = SegmentSpec(
            kind=original.kind, anchor=part.anchor, baseline=part.baseline,
            parent_segment_id=original.parent_segment_id,
        )
        row = _build_segment_row(
            document_id=original.document_id, pass_id=original.pass_id, spec=spec_obj,
            actor=ctx.actor, provenance_kind=original.provenance_kind,
        )
        new_rows.append(row)
        new_ids.append(row.id)
    if new_rows:
        db.save_many(new_rows)

    forwarding = SegmentForwarding(
        document_id=original.document_id,
        old_segment_id=params.segment_id,
        kind="split",
        # The original id "stays on one part" -- included here so a caller
        # resolving the pre-split id sees every resulting id, including its
        # own (`resolve_segment`/`_forwarding_walk` treat a self-reference
        # as live, never as a hop).
        new_segment_ids=[params.segment_id, *new_ids],
        actor=ctx.actor,
        audit_id=audit_id,
        sequence=db.next_forwarding_sequence(),
    )
    db.save(forwarding)

    change_spec = ChangeSpec(
        domains=["segment"],
        target_ids=[params.segment_id, *new_ids],
        before=None,
        after={
            "kept_id": params.segment_id, "new_segment_ids": new_ids,
            "forwarding_id": forwarding.id, "pre_split_version": pre_split_version,
        },
        emit_type="segment.split",
        segment_ids=[params.segment_id, *new_ids],
        pass_ids=[original.pass_id],
        document_ids=[original.document_id],
    )
    return (
        {"kept_id": params.segment_id, "new_segment_ids": new_ids, "forwarding_id": forwarding.id},
        change_spec,
    )


class SegmentUnsplitParams(BaseModel):
    """Internal: `segment.split`'s inverse only. Ids and a version number
    ONLY (#4923 second look) -- restores from the `SegmentVersion` snapshot
    `segment.split` itself wrote (the same path `segment.restore_version`
    uses), never from geometry carried in the params."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    #: The pre-split version to restore the kept segment to.
    version: int
    new_segment_ids: list[str] = []


@action("segment.unsplit", SegmentUnsplitParams, domains=["segment"], undoable=False)
def _action_unsplit(db: Database, params: SegmentUnsplitParams, ctx: ActionContext):
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    row = db.get(Segment, params.segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    candidates = db.query(SegmentVersion, segment_id=params.segment_id, version=params.version)
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"segment {params.segment_id!r} has no version {params.version}",
        )
    target = candidates[0]

    deleted_ids = []
    for new_id in params.new_segment_ids:
        new_row = db.get(Segment, new_id)
        if new_row is not None:
            db.delete(new_row)
            deleted_ids.append(new_id)

    audit_id = uuid.uuid4().hex
    # The version only ever goes UP: a fresh preimage of the CURRENT
    # (post-split) state, then apply the target's fields -- never
    # `row.version = params.version` (that would move it BACKWARDS).
    snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
    row.anchor = target.anchor
    row.baseline = target.baseline
    row.kind = target.kind
    row.kind_raw = target.kind_raw
    row.parent_segment_id = target.parent_segment_id
    row.is_furniture = target.is_furniture
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
    row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
    row.doc_kind = f"{row.document_id}:{row.kind}"
    db.save(row)
    db.save(SegmentForwarding(
        document_id=row.document_id,
        old_segment_id=params.segment_id,
        kind="restored",
        new_segment_ids=[],
        actor=ctx.actor,
        audit_id=audit_id,
        sequence=db.next_forwarding_sequence(),
    ))
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[params.segment_id, *deleted_ids],
        before=None,
        after={"segment_id": params.segment_id},
        emit_type="segment.split",
        segment_ids=[params.segment_id, *deleted_ids],
        pass_ids=[row.pass_id],
        document_ids=[row.document_id],
    )
    return {"segment_id": params.segment_id}, spec


# --- carry / uncarry -----------------------------------------------------

#: kind name -> (model, its anchor field, its document-id field). NEVER a
#: claim (#4922 review): a claim is knowledge, not a mark on a page --
#: copying one would say the same statement twice in the graph, seen twice
#: by every table, export, count, biography and embedding. `kinds` that
#: name a statement are refused by `StatementsCarriedInStatementsStep`
#: below, never silently accepted here.
_CARRY_MODELS: dict[str, tuple[type[BaseModel], str, str]] = {
    "reading": (ContentRepresentation, "source_anchor", "document_id"),
    "annotation": (Annotation, "anchor", "document_id"),
}


class StatementsCarriedInStatementsStep(ValueError):
    """`claim_evidence`/`claim`/`statement` is refused from `segment.carry`
    (#4922 review, corrected from the spec's own earlier mistake): a claim
    is knowledge, never a page mark, so it is carried by giving the SAME
    claim one more place it rests on (a `SourceSupport`) -- the statements
    step, with slice 8, once a claim can carry a `segment_id`. Never a
    second claim row."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            f"{kind!r} cannot be carried by segment.carry -- statements are "
            "carried in the statements step (slice 8), by giving the same "
            "claim one more place it rests on, never a second claim"
        )


#: Named kinds that are refused outright (never silently treated as
#: "unknown") because they name a STATEMENT, not a mark on a page.
_STATEMENT_CARRY_KINDS = frozenset({"claim_evidence", "claim", "statement"})


def _anchor_matches_segment(anchor: SourceAnchor | None, segment: Segment) -> bool:
    """Exact match, same tolerance as slice 6's planned re-pointing (1e-6 on
    all four rect numbers, same `rendition_id`) -- never by overlap or
    nearness."""
    if anchor is None or anchor.rect is None or segment.anchor.rect is None:
        return False
    if anchor.document_id != segment.document_id:
        return False
    if anchor.rendition_id != segment.anchor.rendition_id:
        return False
    return all(abs(a - b) <= 1e-6 for a, b in zip(anchor.rect, segment.anchor.rect))


def _records_anchored_to(db: Database, carried_kind: str, segment: Segment) -> list[BaseModel]:
    model, anchor_field, doc_field = _CARRY_MODELS[carried_kind]
    candidates = db.query(model, **{doc_field: segment.document_id})
    return [row for row in candidates if _anchor_matches_segment(getattr(row, anchor_field, None), segment)]


def _carried_anchor(original_anchor: SourceAnchor | None, to_segment: Segment) -> SourceAnchor:
    """`to_segment`'s own anchor, but keeping the ORIGINAL's character span
    (#4922 review): a wholesale anchor replacement drops
    `char_start`/`char_end` even when the carried text is the same string,
    which is real information a caller may still need (e.g. a highlight
    over a specific run of characters, not just the whole segment)."""
    anchor = to_segment.anchor
    if original_anchor is not None and (original_anchor.char_start is not None or original_anchor.char_end is not None):
        anchor = anchor.model_copy(update={
            "char_start": original_anchor.char_start,
            "char_end": original_anchor.char_end,
        })
    return anchor


def _copy_record_to_segment(carried_kind: str, original: BaseModel, to_segment: Segment) -> BaseModel:
    """One copy of `original`, re-anchored to `to_segment`'s own place --
    NEVER a move (`source.segment.carry-across-a-match`: the original stays
    where it was). Every OTHER field is carried across unchanged via
    `model_copy` (including its maker -- `producer_tool`/`producer_model`/
    `review_state` for a reading -- so it does not look hand-made), so
    nothing this slice does not know about is silently dropped."""
    if carried_kind == "reading":
        original_anchor = getattr(original, "source_anchor", None)
        return original.model_copy(update={
            "id": uuid.uuid4().hex,
            "document_id": to_segment.document_id,
            "source_anchor": _carried_anchor(original_anchor, to_segment),
            "created_at": utc_now(),
        })
    if carried_kind == "annotation":
        original_anchor = getattr(original, "anchor", None)
        return original.model_copy(update={
            "id": uuid.uuid4().hex,
            "document_id": to_segment.document_id,
            "anchor": _carried_anchor(original_anchor, to_segment),
        })
    raise ValueError(f"unknown carried_kind: {carried_kind!r}")  # unreachable: params model validates


class SegmentCarryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    kinds: list[str]


def _invert_carry(before, after, ctx: ActionContext):
    if not after:
        return None
    carry_ids = after.get("carry_ids")
    if not carry_ids:
        return None
    return ("segment.uncarry", {"carry_ids": carry_ids})


@action("segment.carry", SegmentCarryParams, domains=["segment"], undoable=True, invert=_invert_carry)
def _action_carry(db: Database, params: SegmentCarryParams, ctx: ActionContext):
    match = db.get(SegmentMatch, params.match_id)
    if not match:
        raise HTTPException(status_code=404, detail=f"Match not found: {params.match_id}")
    if match.state != "accepted":
        raise _as_http_error(MatchNotAccepted(
            f"match {params.match_id!r} is not accepted (state: {match.state!r})"
        ))
    for kind in params.kinds:
        if kind in _STATEMENT_CARRY_KINDS:
            raise _as_http_error(StatementsCarriedInStatementsStep(kind))
        if kind not in _CARRY_MODELS:
            raise HTTPException(status_code=422, detail=f"unknown carried kind: {kind!r}")

    from_row = db.get(Segment, match.from_segment_id)
    to_row = db.get(Segment, match.to_segment_id)
    if not from_row or not to_row:
        raise HTTPException(status_code=404, detail="matched segment not found")

    # #4922 second look: both ends of the match must be LIVE -- carrying
    # onto (or from) a segment that has since been deleted or merged away
    # makes no sense and would anchor the copy nowhere real.
    for segment_id in (match.from_segment_id, match.to_segment_id):
        reason = segment_liveness_reason(db, segment_id)
        if reason is not None:
            raise _as_http_error(SegmentNotLive(segment_id, reason))

    # `source.segment.carry-across-a-match`: "one to one" across ACCEPTED
    # matches only -- one old line became two (many-to-many) is exactly the
    # case a reading must not be silently duplicated across.
    from_count = len(db.query(SegmentMatch, from_segment_id=match.from_segment_id, state="accepted"))
    to_count = len(db.query(SegmentMatch, to_segment_id=match.to_segment_id, state="accepted"))
    one_to_one = from_count == 1 and to_count == 1

    carry_ids: list[str] = []
    copy_ids: list[str] = []
    not_carried: list[dict] = []
    for kind in params.kinds:
        if kind == "reading" and not one_to_one:
            not_carried.append({"kind": kind, "reason": "match is not one-to-one"})
            continue
        for original in _records_anchored_to(db, kind, from_row):
            copy = _copy_record_to_segment(kind, original, to_row)
            db.save(copy)
            carry = SegmentCarry(
                match_id=match.id, carried_kind=kind, original_id=original.id, copy_id=copy.id,
            )
            db.save(carry)
            carry_ids.append(carry.id)
            copy_ids.append(copy.id)

    spec = ChangeSpec(
        domains=["segment"],
        target_ids=[match.id, *carry_ids],
        before=None,
        after={"carry_ids": carry_ids, "copy_ids": copy_ids, "not_carried": not_carried},
        emit_type="segment.matched",
        segment_ids=[match.from_segment_id, match.to_segment_id],
        pass_ids=[from_row.pass_id, to_row.pass_id],
        document_ids=[from_row.document_id, to_row.document_id],
    )
    return {"carry_ids": carry_ids, "copy_ids": copy_ids, "not_carried": not_carried}, spec


class SegmentUncarryParams(BaseModel):
    """Internal: `segment.carry`'s inverse only. Removes exactly the
    copies it lists -- never the originals."""

    model_config = ConfigDict(extra="forbid")

    carry_ids: list[str]


@action("segment.uncarry", SegmentUncarryParams, domains=["segment"], undoable=False)
def _action_uncarry(db: Database, params: SegmentUncarryParams, ctx: ActionContext):
    removed_carry_ids: list[str] = []
    removed_copy_ids: list[str] = []
    for carry_id in params.carry_ids:
        carry = db.get(SegmentCarry, carry_id)
        if not carry:
            continue
        model, _anchor_field, _doc_field = _CARRY_MODELS[carry.carried_kind]
        copy_row = db.get(model, carry.copy_id)
        if copy_row is not None:
            db.delete(copy_row)
            removed_copy_ids.append(carry.copy_id)
        db.delete(carry)
        removed_carry_ids.append(carry_id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=removed_carry_ids,
        before=None,
        after={"carry_ids": removed_carry_ids, "copy_ids": removed_copy_ids},
        emit_type="segment.matched",
    )
    return {"carry_ids": removed_carry_ids, "copy_ids": removed_copy_ids}, spec


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/passes", response_model=SegmentPass)
async def create_pass(
    params: SegmentPassCreateParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> SegmentPass:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.pass_create", params.model_dump(mode="json"), ctx)
    return SegmentPass.model_validate(result.result)


@router.delete("/passes/{pass_id}")
async def delete_pass(
    pass_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.pass_delete", {"pass_id": pass_id}, ctx)
    return result.result


@router.post("", response_model=SegmentRead)
async def create_segment(
    params: SegmentCreateParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> SegmentRead:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.create", params.model_dump(mode="json"), ctx)
    segment_id = result.result["segment_ids"][0]
    return segment_read_from_row(db.get(Segment, segment_id))


@router.post("/bulk")
async def create_segments_bulk(
    params: SegmentCreateManyParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.create_many", params.model_dump(mode="json"), ctx)
    segment_ids = result.result["segment_ids"]
    return {
        "segments": [
            segment_read_from_row(db.get(Segment, segment_id)).model_dump(mode="json")
            for segment_id in segment_ids
        ]
    }


# ---------------------------------------------------------------------------
# Slice 4 (#4922) routes
# ---------------------------------------------------------------------------


@router.post("/matches")
async def propose_match(
    params: SegmentMatchProposeParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.match_propose", params.model_dump(mode="json"), ctx)
    match = db.get(SegmentMatch, result.result["match_id"])
    return match.model_dump(mode="json") if match else result.result


@router.post("/matches/{match_id}/accept")
async def accept_match(
    match_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.match_accept", {"match_id": match_id}, ctx)
    return result.result


@router.post("/matches/{match_id}/reject")
async def reject_match(
    match_id: str,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.match_reject", {"match_id": match_id}, ctx)
    return result.result


@router.post("/merge")
async def merge_segments(
    params: SegmentMergeParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.merge", params.model_dump(mode="json"), ctx)
    return result.result


@router.post("/split")
async def split_segment(
    params: SegmentSplitParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.split", params.model_dump(mode="json"), ctx)
    return result.result


@router.post("/carry")
async def carry_across_match(
    params: SegmentCarryParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.carry", params.model_dump(mode="json"), ctx)
    return result.result


class SegmentReferenceResponse(BaseModel):
    reference: str
    segment_id: str


@router.get("/{segment_id}/reference", response_model=SegmentReferenceResponse)
async def segment_reference(
    segment_id: str,
    db: Database = Depends(get_library_database),
) -> SegmentReferenceResponse:
    """`source.segment.citable`: a plain, stable string
    (`fichero:segment/<library_uuid>/<document_id>/<segment_id>`) worked
    out on request, never stored -- `library_uuid` from the existing
    `library_identity` table. Resolving it (following any forwarding) is
    `POST /api/locations/resolve`'s job, not this route's."""
    _assert_not_provisional_http(segment_id, what="segment_id")
    row = db.get(Segment, segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    library_uuid = db.library_uuid() or "unknown"
    reference = f"fichero:segment/{library_uuid}/{row.document_id}/{segment_id}"
    return SegmentReferenceResponse(reference=reference, segment_id=segment_id)


# ---------------------------------------------------------------------------
# Slice 5 (#4923) -- versions, and refusing a stale edit
# ---------------------------------------------------------------------------


@router.put("/{segment_id}", response_model=SegmentRead)
async def update_segment(
    segment_id: str,
    params: SegmentUpdateParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> SegmentRead:
    if params.segment_id != segment_id:
        raise HTTPException(
            status_code=422,
            detail=f"path segment_id {segment_id!r} does not match body segment_id {params.segment_id!r}",
        )
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    registry.invoke(db, "segment.update", params.model_dump(mode="json"), ctx)
    return segment_read_from_row(db.get(Segment, segment_id))


@router.post("/delete")
async def delete_segments(
    params: SegmentDeleteParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.delete", params.model_dump(mode="json"), ctx)
    return result.result


@router.post("/undelete")
async def undelete_segments(
    params: SegmentUndeleteParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.undelete", params.model_dump(mode="json"), ctx)
    return result.result


class SegmentRestoreVersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    expected_version: int


@router.post("/{segment_id}/restore-version", response_model=SegmentRead)
async def restore_segment_version(
    segment_id: str,
    body: SegmentRestoreVersionBody,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> SegmentRead:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    params = {
        "segment_id": segment_id, "version": body.version, "expected_version": body.expected_version,
    }
    registry.invoke(db, "segment.restore_version", params, ctx)
    return segment_read_from_row(db.get(Segment, segment_id))


@router.get("/{segment_id}/versions", response_model=list[SegmentVersion])
async def list_segment_versions(
    segment_id: str,
    db: Database = Depends(get_library_database),
) -> list[SegmentVersion]:
    """`source.segment.versioned-alone`: one segment's own history, read
    without touching any other segment's rows."""
    _assert_not_provisional_http(segment_id, what="segment_id")
    rows = db.query(SegmentVersion, segment_id=segment_id)
    rows.sort(key=lambda r: r.version)
    return rows


class SegmentDetailResponse(BaseModel):
    segment: SegmentRead
    #: True when `segment_id` had been forwarded (merged, split, or
    #: deleted-then-restored) and this is a DIFFERENT, live id.
    resolved_from_forwarding: bool = False
    trail: list[SegmentForwarding] = []


@router.get("/{segment_id}", response_model=SegmentDetailResponse)
async def get_segment(
    segment_id: str,
    db: Database = Depends(get_library_database),
) -> SegmentDetailResponse:
    """The live row for `segment_id`, resolving through `resolve_segment`
    when it has been forwarded (and saying so) -- never a silent
    substitution."""
    _assert_not_provisional_http(segment_id, what="segment_id")
    row = db.get(Segment, segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    if row.deleted_at is None:
        return SegmentDetailResponse(segment=segment_read_from_row(row), resolved_from_forwarding=False)

    resolved = resolve_segment(db, segment_id)
    live_id = primary_live_segment_id(resolved)
    if live_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"segment {segment_id!r} was deleted and has no live successor",
        )
    live_row = db.get(Segment, live_id)
    if not live_row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {live_id}")
    return SegmentDetailResponse(
        segment=segment_read_from_row(live_row),
        resolved_from_forwarding=(live_id != segment_id),
        trail=resolved.trail,
    )
