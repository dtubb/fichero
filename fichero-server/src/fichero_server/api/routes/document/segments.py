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

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import request_actor
from fichero_server.api.library_header import optional_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import (
    Artifact,
    Document,
    Segment,
    SegmentListResponse,
    SegmentPass,
)
from fichero_server.models.anchors import SourceAnchor, validate_rect
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import (
    TILE_SIZE,
    PassRead,
    ProvisionalSegmentIdError,
    SegmentRead,
    assert_not_provisional,
    bbox_and_tile_from_anchor,
    grow_rect_by_half_tile,
    legacy_pass_id,
    pass_read_from_row,
    rects_intersect,
    segment_read_from_row,
    segments_from_result,
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


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProvisionalSegmentIdError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (SegmentPassMismatchError, SegmentParentMismatchError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, SegmentAnchorMismatchError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


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
        pass_segments = [segment_read_from_row(row) for row in rows]
        by_pass.append((pass_read_from_row(pass_row), pass_segments))

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
    assert_not_provisional(params.pass_id, what="pass_id")
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
    assert_not_provisional(params.pass_id, what="pass_id")
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
    return ("segment.delete", {"segment_ids": segment_ids})


@action(
    "segment.create",
    SegmentCreateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_create,
)
def _action_segment_create(db: Database, params: SegmentCreateParams, ctx: ActionContext):
    assert_not_provisional(params.document_id, what="document_id")
    assert_not_provisional(params.pass_id, what="pass_id")
    if params.parent_segment_id:
        assert_not_provisional(params.parent_segment_id, what="parent_segment_id")
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
    assert_not_provisional(params.document_id, what="document_id")
    assert_not_provisional(params.pass_id, what="pass_id")

    pass_row = db.get(SegmentPass, params.pass_id)
    rows: list[Segment] = []
    for spec in params.segments:
        if spec.parent_segment_id:
            assert_not_provisional(spec.parent_segment_id, what="parent_segment_id")
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


class SegmentDeleteParams(BaseModel):
    """Internal: used only as `segment.create`/`.create_many`'s inverse in
    this slice. Update and delete of a segment as a user-facing feature,
    with version compare-and-set, arrive in slice 5."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str]


@action("segment.delete", SegmentDeleteParams, domains=["segment"], undoable=False)
def _action_segment_delete(db: Database, params: SegmentDeleteParams, ctx: ActionContext):
    from fichero_server.core.timeutil import utc_now

    now = utc_now()
    document_ids: set[str] = set()
    pass_ids: set[str] = set()
    for segment_id in params.segment_ids:
        assert_not_provisional(segment_id, what="segment_id")
        row = db.get(Segment, segment_id)
        if not row:
            # Never silently skip and still list it in `after`/the event
            # (#4921 review): an id this action cannot find is a real
            # problem for whatever asked for its deletion (most often
            # `segment.create`'s own inverse), not a no-op to swallow.
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        row.deleted_at = now
        row.deleted_by = ctx.actor
        db.save(row)
        document_ids.add(row.document_id)
        pass_ids.add(row.pass_id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=list(params.segment_ids),
        before=None,
        after={"segment_ids": params.segment_ids},
        emit_type="segment.deleted",
        segment_ids=list(params.segment_ids),
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": params.segment_ids}, spec


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
