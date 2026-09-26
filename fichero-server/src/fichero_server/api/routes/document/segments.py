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

import logging
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import request_actor
# Slice 6 (#4924). The seam's ONE import hunk for conversion; everything
# else slice 6 adds to this file lives inside `list_document_segments`.
# (`logging` above and `logger` below belong to this hunk too: the module
# had no logger, and the seam's #4958 refusal must be logged, not silent.)
from fichero_server.api.routes.document.segment_conversion import (
    ConversionMarkerDangling,
    converted_pass_of,
    is_converted,
)
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
from fichero_server.models.anchors import (
    PROVISIONAL_ID_PREFIXES,
    SourceAnchor,
    validate_rect,
)
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

logger = logging.getLogger(__name__)

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


class SegmentPassIsConversionTarget(ValueError):
    """#4958-class trap the slice 6 review found: deleting a pass a LIVE
    artifact's marker (`Artifact.geometry_superseded_by_pass_id`) names
    would make that marker dangling. `converted_pass_of` (`segment_
    conversion.py`) then correctly raises `ConversionMarkerDangling` on
    every read of that artifact's geometry, turning an ordinary, permitted,
    undoable pass-delete into a 500 on the artifact list and the document
    view -- the very page a person would open to put it right. This stops
    it at the source: an ordinary pass-delete is unaffected; only a pass a
    live artifact still points to is refused. What deleting a converted
    result's boxes should MEAN is a later slice's editor question -- this
    only stops the trap."""

    def __init__(self, pass_id: str, artifact_id: str) -> None:
        self.pass_id = pass_id
        self.artifact_id = artifact_id
        super().__init__(
            f"pass {pass_id!r} cannot be deleted: artifact {artifact_id!r} was "
            "converted to it and still points at it"
        )


class SegmentPassNotLive(ValueError):
    """#4957 review 3, item 1: a segment cannot be created into a pass
    that is already soft-deleted -- same class as `SegmentRestoreTargetGone`
    below (a restore into a dead container), for the forward CREATE path.
    A freshly made pass is always live, so this never refuses a legitimate
    create (including slice 6's conversion, which creates its own pass)."""

    def __init__(self, pass_id: str) -> None:
        self.pass_id = pass_id
        super().__init__(f"pass {pass_id!r} is deleted and cannot take new segments")


class SegmentMatchCrossDocument(ValueError):
    """#4958, same class as the pass/artifact leak: `segment.match_propose`
    set `SegmentMatch.document_id` from `from_segment_id` alone and never
    checked that `to_segment_id` belongs to the SAME document -- a carry
    across such a match would copy one document's reading onto another's
    segment. Refused outright; a match links two segments on ONE source,
    like `segment.merge`/`.split`/`.carry` already require."""

    def __init__(self, from_segment_id: str, from_document_id: str, to_segment_id: str, to_document_id: str) -> None:
        self.from_segment_id = from_segment_id
        self.to_segment_id = to_segment_id
        super().__init__(
            f"segment {from_segment_id!r} (document {from_document_id!r}) and "
            f"{to_segment_id!r} (document {to_document_id!r}) are not on the same document"
        )


class ArtifactNotInDocumentScope(ValueError):
    """#4958: an artifact named as a pass's `source_artifact_id`, or a
    segment's owning document, must belong to the SAME document scope --
    the document itself, a direct child page, or its parent (the exact
    aggregation `GET /api/artifacts/document/{doc_id}?include_descendants=
    true` already uses). Refuses a cross-document reference outright,
    rather than silently reading (or later rendering) one document's words
    on another's page to someone who may not have access to the source."""

    def __init__(self, artifact_id: str, *, artifact_document_id: str, requested_document_id: str) -> None:
        self.artifact_id = artifact_id
        self.artifact_document_id = artifact_document_id
        self.requested_document_id = requested_document_id
        super().__init__(
            f"artifact {artifact_id!r} belongs to document {artifact_document_id!r}, "
            f"not {requested_document_id!r} (or one of its pages/parent)"
        )


def _artifact_in_document_scope(db: Database, artifact: Artifact, document_id: str) -> bool:
    """Same scope `GET /api/artifacts/document/{doc_id}` uses with
    `include_descendants=True` (the seam's own "legacy aggregation"): the
    document itself, its direct children (pages), and its parent -- the
    ONE rule for "does this artifact belong here", never a second one
    (#4958)."""
    if artifact.document_id == document_id:
        return True
    doc = db.get(Document, document_id)
    if doc is not None and artifact.document_id == doc.parent_id:
        return True
    return any(
        artifact.document_id == child.id for child in db.query(Document, parent_id=document_id)
    )


class SegmentPartGone(ValueError):
    """#4957 review 3: under own-invert, `unsplit` derives `new_segment_ids`
    from its OWN redo's fresh `after`, so a named part should always
    exist. If it does not (a bug, or a hand-built replay), refuse loudly
    rather than silently treating a surprise as "nothing to do"."""

    def __init__(self, segment_id: str) -> None:
        self.segment_id = segment_id
        super().__init__(f"segment {segment_id!r} named in new_segment_ids does not exist")


class SegmentRestoreTargetGone(ValueError):
    """Undelete, unmerge and unsplit refuse to restore a segment into a
    pass or under a parent that is no longer live (#4957 follow-up 2):
    without this check, an undo or a redo could bring a segment back
    live and yet invisible -- the read seam skips a soft-deleted pass
    entirely, and a segment under a deleted parent reads as orphaned."""

    def __init__(self, segment_id: str, *, container: str, container_id: str, reason: str) -> None:
        self.segment_id = segment_id
        self.container = container
        self.container_id = container_id
        self.reason = reason
        super().__init__(
            f"cannot restore segment {segment_id!r}: its {container} "
            f"{container_id!r} is not live ({reason})"
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
    if isinstance(exc, (SegmentPassMismatchError, SegmentParentMismatchError, SegmentForwardingWouldLoop, SegmentNotLive, SegmentDeleted, SegmentRestoreTargetGone, ArtifactNotInDocumentScope, SegmentMatchCrossDocument, SegmentPartGone, SegmentPassNotLive, SegmentPassIsConversionTarget)):
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


def provenance_kind_from_ctx(ctx: ActionContext) -> ProvenanceKind:
    """PUBLIC since source-model slice 8 (#4934), which needed the same
    answer for a reading: one function deciding "who made this" for every
    source-model write, because two copies of this rule would be two rules.

    Same posture as `_new_pass_provenance_kind` below, without a
    provider/model (matches/merges have neither): a run behind the call
    means a machine did it; the MCP surface means an agent did it (test-audit
    F15, 2026-09-20: the SAME rule `annotation.promote_to_claim` and
    `claims.py` already apply for `human` vs `agent`, #4868/#4869 --
    `ctx.via_mcp`, never a second copy of it); a real actor with neither
    means a person did; nothing given is honestly unknown -- never a
    trusting default."""
    if ctx.run_id:
        return ProvenanceKind.workflow
    if ctx.via_mcp:
        return ProvenanceKind.agent
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

    # This document's artifacts, loaded ONCE (#4924). Both loops below need
    # them -- the rows loop for a pass's type and its boxes' words, the block
    # loop for the boxes themselves -- and hydrating an `Artifact` parses and
    # VALIDATES every box in its `ocr_geometry`. Measured on a converted
    # 20,000-box page: two loads cost 405 ms of `_validate_bbox` alone, for a
    # read that returned 72 rows. One load halves it.
    #
    # Scoped to THIS document on purpose, and the rows loop uses membership of
    # this map as its answer to "may this artifact supply the words?" (#4958):
    # `segment.pass_create` does not check that `source_artifact_id` belongs to
    # `document_id`, so a pass here can name another document's artifact, and
    # filling text from it would be a read leak.
    artifacts_by_id: dict[str, Artifact] = {
        a.id: a for a in db.query(Artifact, document_id=doc_id)
    }

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
        # A pass made from an artifact carries that artifact's type (test-audit
        # B2, App slice A stage 2's notes) -- looked up here, since
        # `pass_read_from_row` has no `db` of its own. Slice 6 (#4924) reads
        # the SAME artifact once more for the words: until readings hang on
        # segments (slice 8), a converted box's text and its pass's text still
        # live in the artifact's kept `ocr_geometry` block.
        pass_artifact_type = None
        source_block = None
        if pass_row.source_artifact_id:
            # Membership of `artifacts_by_id` IS the #4958 check: the map holds
            # only THIS document's artifacts, so a pass naming another
            # document's artifact simply is not in it, and gets no words.
            source_artifact = artifacts_by_id.get(pass_row.source_artifact_id)
            if source_artifact is not None:
                pass_artifact_type = source_artifact.artifact_type
                source_block = source_artifact.ocr_geometry  # raw-geometry-ok: the words' one home until slice 8
            elif db.get(Artifact, pass_row.source_artifact_id) is not None:
                # It exists, it just belongs to somebody else's page. No text
                # is the honest answer, and it is logged, never silent.
                logger.warning(
                    "pass %s on document %s names artifact %s, which belongs to a "
                    "different document; serving its segments without text rather "
                    "than another document's words (#4958)",
                    pass_row.id, doc_id, pass_row.source_artifact_id,
                )
        pass_segments = [
            segment_read_from_row(
                row,
                box_index=index,
                source_block=source_block,
                source_artifact_id=pass_row.source_artifact_id,
            )
            for index, row in enumerate(rows)
        ]
        by_pass.append((
            pass_read_from_row(
                pass_row, artifact_type=pass_artifact_type, source_block=source_block
            ),
            pass_segments,
        ))

    # Then the old boxes, for whichever artifacts still carry them
    # (unconverted — every artifact, today, since nothing converts yet).
    artifacts = [
        a for a in artifacts_by_id.values()
        if a.ocr_geometry and (not artifact_id or a.id == artifact_id)
    ]
    for artifact in artifacts:
        # Slice 6 (#4924): an artifact whose boxes have BECOME rows is served
        # by the loop above, never here. Without this one `if`, a converted
        # page comes back with every box twice -- once as a real segment and
        # once as the provisional one it replaced.
        if is_converted(artifact):
            # Raises when the marker names no live pass. NEVER a quiet fall
            # back to the block: the block is the page as it was BEFORE its
            # owner's first edit, so serving it here would undo their work on
            # screen and look entirely correct doing it. Mapped to a 409 with
            # the artifact and pass named, because a person meeting this needs
            # to know WHICH page needs repair, not a bare 500.
            try:
                converted_pass_of(db, artifact)
            except ConversionMarkerDangling as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            continue
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
    never a trusting default (same posture as `derive_pass_provenance_kind`
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
        # #4958: refuse a nonexistent artifact (previously silently
        # accepted -- `provider`/`model` just stayed `None`) and refuse
        # one from OUTSIDE this document's scope. Slice 6 fills a
        # converted pass's text from its source block, so a pass on
        # document A naming document B's artifact would show B's words
        # on A's page to someone who may not have access to B.
        source_artifact = db.get(Artifact, params.source_artifact_id)
        if source_artifact is None:
            raise HTTPException(
                status_code=404, detail=f"Artifact not found: {params.source_artifact_id}"
            )
        if not _artifact_in_document_scope(db, source_artifact, params.document_id):
            raise _as_http_error(ArtifactNotInDocumentScope(
                source_artifact.id,
                artifact_document_id=source_artifact.document_id,
                requested_document_id=params.document_id,
            ))
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
    # #4957: undoing a `pass_create` invokes THIS action as the inverse; a
    # plain replay of `pass_create` on redo would mint a SECOND pass with a
    # new id and strand the first. Own-invert redoes THIS row's own
    # `pass_restore` (same pass id, soft-restored) instead.
    redo_via_own_invert=True,
)
def _action_pass_delete(db: Database, params: SegmentPassDeleteParams, ctx: ActionContext):
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if not pass_row:
        raise HTTPException(status_code=404, detail=f"Pass not found: {params.pass_id}")
    # #4957/#4958-class trap (slice 6 review): a LIVE artifact's own
    # conversion marker (`Artifact.geometry_superseded_by_pass_id`) may
    # name this pass -- deleting it would leave that marker dangling
    # (`segment_conversion.py::converted_pass_of` correctly raises
    # `ConversionMarkerDangling` on every later read of that artifact's
    # geometry). The persistence layer's own field-equality query, not a
    # second lookup of theirs: at most one artifact converts to any one
    # pass, so this is exact, not a scan-and-guess.
    converting_artifacts = db.query(Artifact, geometry_superseded_by_pass_id=params.pass_id)
    if converting_artifacts:
        raise _as_http_error(
            SegmentPassIsConversionTarget(params.pass_id, converting_artifacts[0].id)
        )
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
    # #4957 review 3, item 1: same class as follow-up 2's restore-target-
    # liveness check, on the forward CREATE path -- a segment born into an
    # already soft-deleted pass would be invisible from the moment it is
    # created (the read seam skips a deleted pass entirely). A freshly
    # made pass (slice 6's conversion path included) is always live, so
    # this never refuses a legitimate create.
    if pass_row.deleted_at is not None:
        raise SegmentPassNotLive(pass_id)
    if parent_segment_id:
        parent = db.get(Segment, parent_segment_id)
        if not parent or parent.pass_id != pass_id or parent.document_id != document_id:
            raise SegmentParentMismatchError(
                f"parent segment {parent_segment_id!r} is not in pass {pass_id!r} "
                f"of document {document_id!r}"
            )
        # Same reasoning as the pass check above: a child born under a
        # parent that is already deleted or merged away would be
        # unreachable from that parent from the moment it is created.
        reason = segment_liveness_reason(db, parent_segment_id)
        if reason is not None:
            raise SegmentNotLive(parent_segment_id, reason)
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


#: Every id minted in this store is `uuid.uuid4().hex` (`_new_id()` in
#: `models/segments.py`) -- 32 lowercase hex characters, no dashes. A
#: caller-supplied id (#4957 slice-6 prep) must be the SAME shape, never a
#: `legacy:` id (refused separately, earlier) and never an arbitrary
#: string a client could use to encode something outside this system.
_WELL_FORMED_ID = re.compile(r"[0-9a-f]{32}")


def _assert_well_formed_id_http(id_value: str, *, what: str) -> None:
    if not _WELL_FORMED_ID.fullmatch(id_value):
        raise HTTPException(
            status_code=422,
            detail=f"{what} {id_value!r} is not a well-formed id (expected 32 lowercase hex characters)",
        )


def _build_segment_row(
    *, document_id: str, pass_id: str, spec: SegmentSpec, actor: str,
    provenance_kind: ProvenanceKind, id: str | None = None,
) -> Segment:
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(spec.anchor)
    return Segment(
        **({"id": id} if id else {}),
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
    """No `id` field, on purpose (#4957 review 3): a client can reach this
    action through `POST /api/actions/invoke` or the chat-tools path, not
    only `POST /api/segments` -- an `id` field on THIS model would be
    reachable through all three, no matter what any ONE route refuses.
    A specific, precomputed id (slice 6's repeatable-on-purpose ids) is a
    keyword on `_create_segment_impl` below, for in-process callers that
    never go through `registry.invoke` at all."""

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


def _create_segment_impl(
    db: Database, params: SegmentCreateParams, ctx: ActionContext, *, segment_id: str | None = None,
) -> Segment:
    """The one path `segment.create` and any future IN-PROCESS caller
    (slice 6's conversion-on-first-edit, applying its own edit directly --
    build notes step 5 -- never through a nested `registry.invoke`) share
    to make a segment. `segment_id`, when given, is a keyword ONLY this
    Python function accepts -- never a field on `SegmentCreateParams`
    (#4957 review 3): that model is reachable by ANY caller through
    `POST /api/actions/invoke` or the chat-tools path, not only
    `POST /api/segments`, so a field on it can never be "in-process only"
    no matter what one route refuses. Refused (422) unless it is the SAME
    shape every id in this store already is, and refused (409, NEVER
    silently overwritten) if it is already in use by ANY segment, live or
    soft-deleted -- `Database.save` is `INSERT ... ON CONFLICT DO UPDATE`,
    so a colliding id would otherwise merge into that other row instead of
    creating a new one. This matters because slice 6's ids are repeatable
    ON PURPOSE (derived from the artifact and a position, in an open-source
    file): anyone with ordinary write access could work out a future
    converted box's id and claim it first."""
    _assert_not_provisional_http(params.document_id, what="document_id")
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    if params.parent_segment_id:
        _assert_not_provisional_http(params.parent_segment_id, what="parent_segment_id")
    if segment_id is not None:
        _assert_not_provisional_http(segment_id, what="id")
        _assert_well_formed_id_http(segment_id, what="id")
        if db.get(Segment, segment_id) is not None:
            raise HTTPException(status_code=409, detail=f"segment id {segment_id!r} is already in use")
    try:
        _validate_segment_placement(
            db, document_id=params.document_id, pass_id=params.pass_id,
            parent_segment_id=params.parent_segment_id, anchor=params.anchor,
        )
    except (SegmentPassMismatchError, SegmentParentMismatchError, SegmentAnchorMismatchError, SegmentPassNotLive, SegmentNotLive) as exc:
        raise _as_http_error(exc) from exc

    spec_obj = SegmentSpec(
        kind=params.kind, anchor=params.anchor, baseline=params.baseline,
        parent_segment_id=params.parent_segment_id, kind_raw=params.kind_raw,
    )
    # test-audit F14, 2026-09-20: the maker is set by the engine from WHO
    # ACTED, never inherited from the pass's own provenance -- a person
    # creating inside a machine pass (or a workflow run creating inside a
    # human pass) must be stored as what it actually is.
    segment = _build_segment_row(
        document_id=params.document_id, pass_id=params.pass_id, spec=spec_obj,
        actor=ctx.actor, provenance_kind=provenance_kind_from_ctx(ctx), id=segment_id,
    )
    db.save(segment)
    return segment


@action(
    "segment.create",
    SegmentCreateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_create,
    # #4957 review 2: NOT `redo_via_own_invert` -- unreachable by
    # construction. A `segment.create` audit row only ever gets
    # `inverse_of` set when create itself is being REPLAYED, and the row
    # that would replay it is `segment.delete` (opted in), which restores
    # via `segment.undelete` instead of ever reaching a second create. The
    # flag would be dead weight here, checked but never taken.
)
def _action_segment_create(db: Database, params: SegmentCreateParams, ctx: ActionContext):
    segment = _create_segment_impl(db, params, ctx)
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
    # #4957 review 2: NOT `redo_via_own_invert`, same reasoning as
    # `segment.create` -- unreachable by construction.
)
def _action_segment_create_many(db: Database, params: SegmentCreateManyParams, ctx: ActionContext):
    _assert_not_provisional_http(params.document_id, what="document_id")
    _assert_not_provisional_http(params.pass_id, what="pass_id")

    # test-audit F14, 2026-09-20: the maker is set by the engine from WHO
    # ACTED, never inherited from the pass -- same rule as `segment.create`.
    provenance_kind = provenance_kind_from_ctx(ctx)
    rows: list[Segment] = []
    for spec in params.segments:
        if spec.parent_segment_id:
            _assert_not_provisional_http(spec.parent_segment_id, what="parent_segment_id")
        try:
            _validate_segment_placement(
                db, document_id=params.document_id, pass_id=params.pass_id,
                parent_segment_id=spec.parent_segment_id, anchor=spec.anchor,
            )
        except (SegmentPassMismatchError, SegmentParentMismatchError, SegmentAnchorMismatchError, SegmentPassNotLive, SegmentNotLive) as exc:
            raise _as_http_error(exc) from exc
        rows.append(
            _build_segment_row(
                document_id=params.document_id, pass_id=params.pass_id, spec=spec,
                actor=ctx.actor, provenance_kind=provenance_kind,
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


def _require_expected_version(expected_versions: dict[str, int], segment_id: str) -> int:
    """#4957 review 3, item 2: the SAME "expected_versions is missing
    segment_id" 422 was hand-copied in `merge`/`unmerge`/`carry`/`unsplit`
    -- one helper, one message, used by all four."""
    if segment_id not in expected_versions:
        raise HTTPException(
            status_code=422, detail=f"expected_versions is missing segment_id {segment_id!r}"
        )
    return expected_versions[segment_id]


def _assert_restore_target_live(db: Database, row: Segment) -> None:
    """#4957 follow-up 2: refuse `undelete`/`unmerge`/`unsplit` when the
    segment's OWN pass or parent is no longer live, before restoring it.
    Without this, an undo or a redo can bring a segment back live and yet
    invisible: the read seam (`list_document_segments`) skips a
    soft-deleted pass entirely, and a segment whose parent has since been
    deleted or merged away reads as orphaned. Checked LAST, after every
    other refusal, so a caller sees the more specific reason first when
    several apply."""
    pass_row = db.get(SegmentPass, row.pass_id)
    if pass_row is None:
        # #4957 review 3: a `SegmentPass` row is only ever SOFT-deleted
        # (`segment.pass_delete` never hard-deletes) -- a segment naming
        # one that plain does not exist is a data problem, not a business
        # refusal a caller can act on. Never silently treated as "live".
        raise RuntimeError(
            f"segment {row.id!r} names pass {row.pass_id!r}, which does not exist"
        )
    if pass_row.deleted_at is not None:
        raise _as_http_error(SegmentRestoreTargetGone(
            row.id, container="pass", container_id=row.pass_id, reason="deleted",
        ))
    if row.parent_segment_id:
        reason = segment_liveness_reason(db, row.parent_segment_id)
        if reason is not None:
            raise _as_http_error(SegmentRestoreTargetGone(
                row.id, container="parent", container_id=row.parent_segment_id, reason=reason,
            ))


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
    # #4957: undoing a `segment.create` invokes THIS action as the inverse;
    # a plain replay of `segment.create` on redo would mint a BRAND NEW
    # segment id and strand the first. Own-invert redoes THIS row's own
    # `segment.undelete` (same segment id, soft-undeleted) instead. Does
    # NOT change `segment.delete`'s OWN undo/redo chain -- that chain's
    # acting row on redo is `segment.undelete`, a separate flag, left off
    # (replay-with-refresh already proven correct for it).
    redo_via_own_invert=True,
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
        audit_id=audit_id,
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
        _assert_restore_target_live(db, row)
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
        audit_id=audit_id,
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
        audit_id=audit_id,
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
        audit_id=audit_id,
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
    # #4957: `match_withdraw` (this action's inverse) has no `invert` of its
    # own, so the FIRST redo still mints a new match id -- but a second
    # undo (lap 2) previously replayed the withdraw of the FIRST, already-
    # gone match id, refusing and stranding the redo's own match forever.
    # Own-invert on THIS row (when it is itself the redo, i.e. a second
    # `match_propose` produced as an inverse) withdraws ITS OWN match id.
    redo_via_own_invert=True,
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
    # #4958, same class as the pass/artifact leak: a match must link two
    # segments on ONE document, never silently span two.
    if from_row.document_id != to_row.document_id:
        raise _as_http_error(SegmentMatchCrossDocument(
            params.from_segment_id, from_row.document_id,
            params.to_segment_id, to_row.document_id,
        ))

    match = SegmentMatch(
        document_id=from_row.document_id,
        from_segment_id=params.from_segment_id,
        to_segment_id=params.to_segment_id,
        state="proposed",
        proposed_by_kind=provenance_kind_from_ctx(ctx),
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
    if provenance_kind_from_ctx(ctx) != ProvenanceKind.human:
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
#
# #4957 review 3, item 3: `expected_versions`/`expected_version` is REQUIRED
# (no default) on the three actions a CLIENT calls directly -- `segment.
# merge`, `.split`, `.carry` -- and defaults to empty on their three
# inverses -- `.unmerge`, `.unsplit`, `.uncarry` -- which are reached only
# through the undo route's own invert (always supplies it fully, computed
# fresh from the acting row's own `after`) or a hand-built direct call
# (which then fails closed on the missing/mismatched token, never silently).
# One deliberate split across all six, not an inconsistency to fix in one
# and not the others.


class SegmentMergeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str]
    keep_id: str
    #: Compare-and-set, one entry per id in `segment_ids` (#4957 follow-up
    #: 1: "a redo is refused when something else changed the segment since"
    #: -- previously merge took no token at all, so a redo silently merged
    #: away a member someone had just reshaped). Checked against every
    #: participant's CURRENT `Segment.version` before anything is written,
    #: `keep_id` included even though merge itself never bumps it -- a
    #: concurrent edit to the kept segment is still something that changed
    #: since the caller last read it.
    expected_versions: dict[str, int]


def _invert_merge(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look: "no inverse takes geometry
    from the audit record; inverses carry ids and version numbers, read
    from after") -- `after["absorbed_versions"]` names each absorbed
    segment's PRE-merge version, which `segment.unmerge` restores FROM THE
    SNAPSHOT `segment.merge` already wrote (never from this dict's own
    content -- it carries no geometry). `after["versions"]` (#4957 follow-up
    1) names each absorbed segment's version AS LEFT BY THIS MERGE CALL --
    unmerge's own compare-and-set token, always fresh because it is worked
    out from the ACTING row's own `after`, never a replay of an earlier
    call's recorded params."""
    if not after:
        return None
    absorbed_versions = after.get("absorbed_versions")
    current_versions = after.get("versions")
    if not absorbed_versions or not current_versions:
        return None
    return (
        "segment.unmerge",
        {
            "versions": absorbed_versions,
            "expected_versions": {
                sid: current_versions[sid] for sid in absorbed_versions if sid in current_versions
            },
            "representation_ids": after.get("representation_ids", []),
        },
    )


@action(
    "segment.merge",
    SegmentMergeParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_merge,
    # #4957: `unmerge` (this action's inverse) has no `invert` of its own,
    # so a second undo (lap 2, undoing a REDONE merge) previously replayed
    # the FIRST unmerge's recorded pre-merge versions -- silently discarding
    # any edit another writer made to an absorbed segment between the undo
    # and the redo. Own-invert on THIS row (when it is itself the redo)
    # re-derives `absorbed_versions` from ITS OWN fresh `after`, which
    # `_action_merge` always snapshots from the absorbed segment's CURRENT
    # row right before merging -- so the other writer's edit is what gets
    # preserved, not the stale, months-earlier snapshot.
    redo_via_own_invert=True,
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
    # delete into a merge. Checked BEFORE the version compare-and-set
    # (#4957 review 3: same order `segment.update` uses) so a member
    # someone else DELETED is reported as "deleted", the more useful
    # reason, rather than "stale".
    for segment_id in params.segment_ids:
        reason = segment_liveness_reason(db, segment_id)
        if reason is not None:
            raise _as_http_error(SegmentNotLive(segment_id, reason))

    # #4957 follow-up 1: compare-and-set BEFORE anything is written, one id
    # at a time so the FIRST mismatch's own reason is the one reported --
    # never a partial merge.
    for segment_id in params.segment_ids:
        expected = _require_expected_version(params.expected_versions, segment_id)
        row = rows[segment_id]
        if row.version != expected:
            raise _as_http_error(SegmentStale(
                segment_id, expected, row.version,
                _stale_changed_fields(db, segment_id, expected, row),
            ))

    absorbed_ids = [sid for sid in params.segment_ids if sid != params.keep_id]
    for absorbed_id in absorbed_ids:
        # #4922 review: merging into a segment that ALREADY FORWARDS TO the
        # one being absorbed would close a cycle -- refused before anything
        # is written. With every participant now confirmed live, above,
        # this can only ever be true for keep_id == absorbed_id (a live id
        # forwards nowhere) -- the safety net its docstring says it is.
        if forwards_to(db, params.keep_id, absorbed_id):
            raise _as_http_error(SegmentForwardingWouldLoop(params.keep_id, absorbed_id))

    # #4957 slice-6 prep (item 4b), CORRECTED by the manager: `_action_merge`
    # makes no new segment -- it keeps `keep_id` and soft-deletes the
    # others, so there is nothing to re-derive for ordering here. The
    # kept row's own `box_index`/position is left exactly as it was, and
    # `keep_id` is taken as given, never re-chosen by this action; slice
    # 6's route is what picks the lowest-position member as `keep_id`.

    # Slice 8 (#4934): read every member's counting reading BEFORE anything is
    # soft-deleted, in the order the caller gave -- which IS the reading order
    # they were looking at when they merged. The members' own readings are
    # never touched: they stay on their soft-deleted segments and come back
    # with an unmerge, because unmerging restores the rows and the readings
    # were always hanging off them.
    readings_by_member = {
        segment_id: _counting_readings(db, segment_id) for segment_id in params.segment_ids
    }

    audit_id = uuid.uuid4().hex
    absorbed_versions: dict[str, int] = {}
    after_versions: dict[str, int] = {params.keep_id: keep_row.version}
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
        after_versions[absorbed_id] = row.version
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

    # Slice 8 (#4934): the kept segment's reading becomes the members'
    # readings joined in reading order, as a NEW reading whose maker is the
    # person who merged -- because joining two people's transcriptions is a
    # judgement somebody made, not something either of them wrote. Only kinds
    # that more than one member actually had are joined: a single member's
    # reading needs no new record, it is already on the kept segment or comes
    # back with an unmerge.
    merge_representation_ids: list[str] = []
    joined_kinds = {
        kind
        for counted in readings_by_member.values()
        for kind in counted
    }
    for kind in sorted(joined_kinds):
        pieces = [
            readings_by_member[segment_id][kind][1]
            for segment_id in params.segment_ids
            if kind in readings_by_member[segment_id]
        ]
        if len(pieces) < 2:
            continue
        merge_representation_ids.append(
            _derived_reading(
                db,
                document_id=keep_row.document_id,
                segment_id=params.keep_id,
                kind=kind,
                content=" ".join(pieces),
                ctx=ctx,
            )
        )

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[params.keep_id, *absorbed_ids],
        before=None,
        after={
            "kept_id": params.keep_id, "forwarding_ids": forwarding_ids,
            "absorbed_versions": absorbed_versions,
            # Slice 8 (#4934): the joined readings THIS merge added, so its
            # inverse retracts exactly those and nothing else.
            "representation_ids": merge_representation_ids,
            # #4957 follow-up 1: EVERY touched id's version as this call
            # left it -- `_refresh_replay_expected_versions` reads this to
            # freshen a replayed merge's `expected_versions` on redo, and
            # `_invert_merge` reads it to give `unmerge` a live token.
            "versions": after_versions,
        },
        emit_type="segment.merged",
        segment_ids=[params.keep_id, *absorbed_ids],
        pass_ids=[keep_row.pass_id],
        document_ids=[keep_row.document_id],
    )
    return (
        {
            "kept_id": params.keep_id, "forwarding_ids": forwarding_ids,
            "representation_ids": merge_representation_ids,
        },
        spec,
    )


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
    #: Compare-and-set, one entry per id in `versions` (#4957 follow-up 1):
    #: the segment's CURRENT `Segment.version`, as `segment.merge` (or a
    #: later redo of it) left it. Refuses a genuinely stale restore --
    #: someone reshaped the absorbed segment again since -- the same
    #: guarantee `segment.update`'s own compare-and-set gives a live edit.
    expected_versions: dict[str, int]
    #: Slice 8 (#4934): the joined readings the merge ADDED, to retract. The
    #: members' OWN readings need nothing done to them -- they never left their
    #: segments, so restoring the segments brings them back exactly.
    representation_ids: list[str] = []


@action("segment.unmerge", SegmentUnmergeParams, domains=["segment"], undoable=False)
def _action_unmerge(db: Database, params: SegmentUnmergeParams, ctx: ActionContext):
    audit_id = uuid.uuid4().hex
    # Slice 8 (#4934): the join this merge wrote stops counting again.
    _retract_readings(db, params.representation_ids)
    restored_ids = []
    after_versions: dict[str, int] = {}
    document_ids: set[str] = set()
    pass_ids: set[str] = set()

    # Check EVERY segment first, write none of them yet -- explicit,
    # rather than relying on the action's atomicity alone to make a
    # check-then-write-per-id loop safe (#4957 review 3: matches
    # `_action_unsplit`'s own shape).
    rows: dict[str, Segment] = {}
    targets: dict[str, SegmentVersion] = {}
    for segment_id, version in params.versions.items():
        _assert_not_provisional_http(segment_id, what="segment_id")
        row = db.get(Segment, segment_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        expected = _require_expected_version(params.expected_versions, segment_id)
        if row.version != expected:
            raise _as_http_error(SegmentStale(
                segment_id, expected, row.version,
                _stale_changed_fields(db, segment_id, expected, row),
            ))
        _assert_restore_target_live(db, row)
        # #4923 second look: restore FROM THE SNAPSHOT merge itself wrote --
        # the SAME path `segment.restore_version` uses, never a second
        # restore path built from the audit's own params.
        candidates = db.query(SegmentVersion, segment_id=segment_id, version=version)
        if not candidates:
            raise HTTPException(
                status_code=404, detail=f"segment {segment_id!r} has no version {version}"
            )
        rows[segment_id] = row
        targets[segment_id] = candidates[0]

    for segment_id, row in rows.items():
        target = targets[segment_id]
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
        after_versions[segment_id] = row.version
        document_ids.add(row.document_id)
        pass_ids.add(row.pass_id)
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=restored_ids,
        before=None,
        after={"segment_ids": restored_ids, "versions": after_versions},
        emit_type="segment.merged",
        segment_ids=restored_ids,
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": restored_ids}, spec


# --- readings across a split and a merge (slice 8, #4934) ----------------
#
# OWED BY SLICE 8 SO IT IS NOT RETROFITTED. Once a segment has readings,
# splitting or merging it has to say what happens to them, IN THE SAME ACTION
# -- these are parameters of the existing actions, never new actions. The
# alternative is the text editor (13b) discovering later that a merge silently
# lost two people's transcriptions, and bolting on a repair.
#
# Nothing here EDITS a reading. A split's parts and a merge's kept segment get
# NEW readings derived from the old ones, which is the same rule corrections
# follow (`source.reading.corrections-are-new`); the originals are untouched,
# so an undo has only to retract what was added.


def _counting_readings(db: Database, segment_id: str) -> dict[str, tuple[str, str]]:
    """``{kind: (representation_id, content)}`` for each kind that COUNTS on
    this segment right now.

    Imported locally: `segment_readings` imports THIS module, so a top-level
    import would be a cycle. The same shape `segment_conversion`'s callers use
    for `live_geometry`.
    """
    from fichero_server.api.routes.document.segment_readings import (
        counting_by_kind,
        readings_of_segment,
    )

    items = readings_of_segment(db, segment_id)
    answers = counting_by_kind(db, segment_id, items)
    counted: dict[str, tuple[str, str]] = {}
    for kind, answer in answers.items():
        if answer.representation_id is None:
            continue
        text = next(
            (item.content for item in items if item.id == answer.representation_id), None
        )
        if text is not None:
            counted[kind] = (answer.representation_id, text)
    return counted


def _derived_reading(
    db: Database,
    *,
    document_id: str,
    segment_id: str,
    kind: str,
    content: str,
    ctx: ActionContext,
    derived_from: str | None = None,
) -> str:
    """Write one reading derived from a split or a merge, and return its id.

    In-process, not through a nested `registry.invoke`: this is PART of the
    split or merge, one audited action with one undo step -- the same
    discipline slice 6 applied when conversion-on-first-edit wrote its own
    segments. `derived_from` is dropped when it names a PROVISIONAL reading,
    which has no record to point at; the text was still taken from it, and the
    anchor's `segment_id` says where it belongs.
    """
    if derived_from is not None and derived_from.startswith(PROVISIONAL_ID_PREFIXES):
        derived_from = None
    segment = db.get(Segment, segment_id)
    anchor = (
        segment.anchor.model_copy(update={"segment_id": segment_id})
        if segment is not None
        else SourceAnchor(document_id=document_id, segment_id=segment_id)
    )
    reading = ContentRepresentation(
        document_id=document_id,
        segment_id=segment_id,
        kind=kind,
        content=content,
        source_anchor=anchor,
        derived_from_representation_id=derived_from,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
        producer_run_id=ctx.run_id,
    )
    db.save(reading)
    return reading.id


def _retract_readings(db: Database, representation_ids: list[str]) -> None:
    """Undo of a split or a merge: the readings it ADDED stop counting.

    Retracted, not deleted -- the row stays, as it does for every other
    retraction. The readings the split or merge did not touch were never
    touched, so putting them back is nothing: they are already there.
    """
    for representation_id in representation_ids or []:
        row = db.get(ContentRepresentation, representation_id)
        if row is not None and row.retracted_at is None:
            db.save(row.model_copy(update={"retracted_at": utc_now()}))


# --- split / unsplit -----------------------------------------------------


class SegmentSplitPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: SourceAnchor
    baseline: Optional[list[list[float]]] = None
    #: Source-model slice 8 (#4934): the stretch of the line's reading this
    #: part takes, as ``[char_start, char_end]`` into the reading that counts.
    #: WITH NONE GIVEN the reading stays on the kept part and the new parts
    #: have none -- splitting a box is a statement about geometry, and guessing
    #: where to cut somebody's transcription is not the engine's business.
    reading_span: Optional[list[int]] = None


class SegmentSplitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    parts: list[SegmentSplitPart]
    #: Compare-and-set on the segment being split (#4957 follow-up 1) --
    #: the new parts are brand-new rows with nothing to compare yet, so
    #: only the one EXISTING id needs a token, the same shape
    #: `segment.update` already takes.
    expected_version: int


def _invert_split(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look) -- `pre_split_version` names
    the snapshot `segment.split` itself wrote for the kept id; `unsplit`
    restores FROM IT, never from geometry carried here. `after["versions"]`
    (#4957 follow-up 1) gives `unsplit` a live compare-and-set token for
    the kept id AND every new part, worked out from THIS call's own
    `after` -- always fresh, whichever lap it is."""
    if not after:
        return None
    segment_id = after.get("kept_id")
    pre_split_version = after.get("pre_split_version")
    current_versions = after.get("versions")
    if not segment_id or pre_split_version is None or not current_versions:
        return None
    new_segment_ids = after.get("new_segment_ids", [])
    return (
        "segment.unsplit",
        {
            "segment_id": segment_id, "version": pre_split_version,
            "expected_version": current_versions.get(segment_id),
            "new_segment_ids": new_segment_ids,
            "expected_versions": {
                new_id: current_versions[new_id] for new_id in new_segment_ids if new_id in current_versions
            },
            "representation_ids": after.get("representation_ids", []),
        },
    )


@action(
    "segment.split",
    SegmentSplitParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_split,
    # #4957: `unsplit` (this action's inverse) has no `invert` of its own,
    # so a second undo (lap 2, undoing a REDONE split) previously replayed
    # the FIRST unsplit's recorded params, naming the FIRST split's now-gone
    # part ids -- silently skipped, restoring the kept segment to full size
    # while the redo's OWN new parts stayed live on top of it (silent
    # corruption). Own-invert on THIS row (when it is itself the redo)
    # derives the unsplit from ITS OWN fresh `after`, naming the parts and
    # version this split actually made.
    redo_via_own_invert=True,
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
    if original.version != params.expected_version:
        raise _as_http_error(SegmentStale(
            params.segment_id, params.expected_version, original.version,
            _stale_changed_fields(db, params.segment_id, params.expected_version, original),
        ))
    for part in params.parts:
        if part.anchor.document_id != original.document_id:
            raise _as_http_error(SegmentAnchorMismatchError(
                f"part anchor's document_id {part.anchor.document_id!r} does not "
                f"match the segment's document_id {original.document_id!r}"
            ))
        if part.reading_span is not None and (
            len(part.reading_span) != 2 or part.reading_span[0] >= part.reading_span[1]
            or part.reading_span[0] < 0
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "reading_span must be [char_start, char_end] with "
                    f"0 <= start < end; got {part.reading_span!r}"
                ),
            )
    # Slice 8 (#4934): read what COUNTS before anything moves, so the parts are
    # cut from the reading the person was actually looking at.
    readings_before_split = (
        _counting_readings(db, params.segment_id)
        if any(part.reading_span is not None for part in params.parts)
        else {}
    )

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

    # #4957 slice-6 prep (item 4b, "check split... for the same ordering
    # question"): a converted page's read order comes from `metadata
    # ["box_index"]`. A new part carved out of `original` has none of its
    # own -- inheriting `original`'s keeps every part sorted together near
    # where the source line was, instead of the newer parts falling to the
    # end of a converted page's order (today's fallback for "no index").
    original_box_index = original.metadata.get("box_index")

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
        if isinstance(original_box_index, int):
            row.metadata = {**row.metadata, "box_index": original_box_index}
        new_rows.append(row)
        new_ids.append(row.id)
    if new_rows:
        db.save_many(new_rows)

    # Slice 8 (#4934): each part that named a stretch gets its own reading,
    # derived from the one that counted. The kept part is `params.segment_id`
    # and the new parts are `new_ids`, in the order the caller gave them.
    part_ids = [params.segment_id, *new_ids]
    split_representation_ids: list[str] = []
    for part, part_id in zip(params.parts, part_ids):
        if part.reading_span is None:
            continue
        start, end = part.reading_span
        for kind, (source_id, text) in readings_before_split.items():
            if start >= len(text):
                # The stretch is past the end of this kind's reading. Skipped
                # rather than refused: a caller cutting a transcription at a
                # sensible place should not be stopped because some OTHER kind
                # of reading of the same line happens to be shorter.
                continue
            split_representation_ids.append(
                _derived_reading(
                    db,
                    document_id=original.document_id,
                    segment_id=part_id,
                    kind=kind,
                    content=text[start:end],
                    ctx=ctx,
                    derived_from=source_id,
                )
            )

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
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[params.segment_id, *new_ids],
        before=None,
        after={
            "kept_id": params.segment_id, "new_segment_ids": new_ids,
            "forwarding_id": forwarding.id, "pre_split_version": pre_split_version,
            # #4957 follow-up 1: every touched id's version as THIS call
            # left it -- the kept id (bumped) and every new part (starts
            # at 1) -- so `_invert_split`/`_refresh_replay_expected_versions`
            # always have a live token to hand `unsplit`.
            "versions": {params.segment_id: original.version, **{new_id: 1 for new_id in new_ids}},
            # Slice 8 (#4934): the readings THIS split added, so its inverse
            # retracts exactly those and nothing else.
            "representation_ids": split_representation_ids,
        },
        emit_type="segment.split",
        segment_ids=[params.segment_id, *new_ids],
        pass_ids=[original.pass_id],
        document_ids=[original.document_id],
    )
    return (
        {
            "kept_id": params.segment_id, "new_segment_ids": new_ids,
            "forwarding_id": forwarding.id,
            "representation_ids": split_representation_ids,
        },
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
    #: Compare-and-set on the kept segment's CURRENT `Segment.version`
    #: (#4957 follow-up 1) -- distinct from `version` above, which names
    #: the OLD snapshot being restored TO.
    expected_version: int
    new_segment_ids: list[str] = []
    #: Compare-and-set, one entry per id in `new_segment_ids` (#4957
    #: follow-up 1): "an inverse must never hard-delete something a later
    #: step touched" -- a part someone has since edited or restored from a
    #: version is refused, not silently skipped, so the caller is told
    #: instead of the edit vanishing with the delete.
    expected_versions: dict[str, int] = {}
    #: Slice 8 (#4934): the readings the split ADDED, to retract. Named by the
    #: acting row's own `after`, never replayed from an earlier call's params.
    representation_ids: list[str] = []


@action("segment.unsplit", SegmentUnsplitParams, domains=["segment"], undoable=False)
def _action_unsplit(db: Database, params: SegmentUnsplitParams, ctx: ActionContext):
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    row = db.get(Segment, params.segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    if row.version != params.expected_version:
        raise _as_http_error(SegmentStale(
            params.segment_id, params.expected_version, row.version,
            _stale_changed_fields(db, params.segment_id, params.expected_version, row),
        ))
    _assert_restore_target_live(db, row)
    candidates = db.query(SegmentVersion, segment_id=params.segment_id, version=params.version)
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"segment {params.segment_id!r} has no version {params.version}",
        )
    target = candidates[0]

    # Compare-and-set EVERY part BEFORE deleting any of them -- "an inverse
    # must never hard-delete something a later step touched" (#4957 follow-
    # up 1). #4957 review 3: under own-invert `new_segment_ids` is always
    # derived from THIS split's own fresh `after`, so a named part should
    # always exist and always have a token -- either surprise is refused
    # loudly now, never silently treated as "nothing to do" or as an
    # ordinary stale compare-and-set.
    live_new_rows: dict[str, Segment] = {}
    for new_id in params.new_segment_ids:
        new_row = db.get(Segment, new_id)
        if new_row is None:
            raise _as_http_error(SegmentPartGone(new_id))
        expected = _require_expected_version(params.expected_versions, new_id)
        if new_row.version != expected:
            raise _as_http_error(SegmentStale(
                new_id, expected, new_row.version,
                _stale_changed_fields(db, new_id, expected, new_row),
            ))
        live_new_rows[new_id] = new_row

    audit_id = uuid.uuid4().hex
    now = utc_now()

    # Slice 8 (#4934): the readings the split ADDED stop counting again. Done
    # BEFORE the parts are soft-deleted only so the whole undo is one
    # transaction's worth of writes in one readable place; the order does not
    # matter, because a retraction touches the reading and nothing else.
    _retract_readings(db, params.representation_ids)

    # SOFT delete, with a forwarding note for each part (#4957 owed item).
    # This was the ONE hard delete left in the segment store, and it took
    # the parts' ids away with the rows: anything that had referred to a
    # part -- a mark, a claim, another segment's forwarding chain -- was
    # left pointing at nothing, with no record that the part had ever
    # existed. Soft-deleted, the id stays resolvable for good and
    # `resolve_segment` can say what became of it. NO SEGMENT is hard-
    # deleted anywhere any more; `match_withdraw` and `uncarry` still
    # remove a `SegmentMatch` and a `SegmentCarry` outright, and those are
    # the rest of the same owed item (#4957), not done here.
    #
    # It also makes "the count of all segments ever made in a pass"
    # monotonic again. Nothing depends on that any more -- the add id
    # scheme that did was dropped in slice 6 step 5 -- but it was a real
    # trap and it is worth saying it is gone.
    deleted_ids = []
    for new_id, new_row in live_new_rows.items():
        snapshot_segment_version(
            db, new_row, deleted=True, actor=ctx.actor, audit_id=audit_id,
            reason="unsplit",
        )
        new_row.deleted_at = now
        new_row.deleted_by = ctx.actor
        db.save(new_row)
        db.save(SegmentForwarding(
            document_id=new_row.document_id,
            old_segment_id=new_id,
            # `merged`, from the closed vocabulary, not a new word: the
            # part was folded back into the segment the split had taken it
            # from, which is exactly what a merged note means -- "not live
            # any more, look over there". `_forwarding_walk` already
            # follows it, so a reference to a part reaches the whole with
            # no new rule anywhere.
            kind="merged",
            new_segment_ids=[params.segment_id],
            actor=ctx.actor,
            audit_id=audit_id,
            sequence=db.next_forwarding_sequence(),
        ))
        deleted_ids.append(new_id)
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
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[params.segment_id, *deleted_ids],
        before=None,
        # #4957 follow-up 1: singular `version` (not `versions`), matching
        # `segment.update`/`.restore_version`'s own shared convention --
        # `_refresh_replay_expected_versions` reads THIS key to freshen
        # `segment.split`'s own singular `expected_version` when split is
        # replayed for the FIRST redo (`unsplit` has no `invert` of its
        # own, so that redo always takes the replay path, never own-invert).
        after={"segment_id": params.segment_id, "version": row.version},
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
    #: Compare-and-set on the matched segments (#4957 follow-up 1), keyed
    #: by `SegmentMatch.from_segment_id`/`.to_segment_id` -- carry itself
    #: never bumps either segment's version (it only copies readings/
    #: annotations across), but the caller's view of the match can still
    #: be stale if either end was reshaped since it was read.
    expected_versions: dict[str, int]


def _invert_carry(before, after, ctx: ActionContext):
    """`after["versions"]` (#4957 follow-up 1) gives `uncarry` a live
    compare-and-set token for the matched segments, worked out from THIS
    call's own `after` -- always fresh, whichever lap it is."""
    if not after:
        return None
    carry_ids = after.get("carry_ids")
    current_versions = after.get("versions")
    if not carry_ids or not current_versions:
        return None
    return (
        "segment.uncarry",
        {"carry_ids": carry_ids, "expected_versions": current_versions},
    )


@action(
    "segment.carry",
    SegmentCarryParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_carry,
    # #4957: `uncarry` (this action's inverse) has no `invert` of its own,
    # so a second undo (lap 2, undoing a REDONE carry) previously replayed
    # the FIRST uncarry's recorded carry_ids, which no longer exist -- the
    # redo's OWN copies were left stray, live forever. Own-invert on THIS
    # row (when it is itself the redo) uncarries ITS OWN fresh carry_ids.
    redo_via_own_invert=True,
)
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

    # #4957 follow-up 1: compare-and-set on both matched segments BEFORE
    # anything is written.
    for segment_id, row in ((match.from_segment_id, from_row), (match.to_segment_id, to_row)):
        expected = _require_expected_version(params.expected_versions, segment_id)
        if row.version != expected:
            raise _as_http_error(SegmentStale(
                segment_id, expected, row.version,
                _stale_changed_fields(db, segment_id, expected, row),
            ))

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
        after={
            "carry_ids": carry_ids, "copy_ids": copy_ids, "not_carried": not_carried,
            # #4957 follow-up 1: the matched segments' CURRENT versions --
            # unchanged by carry itself, but recorded here so `_invert_carry`
            # can hand `uncarry` a live token instead of a replay's stale one.
            "versions": {match.from_segment_id: from_row.version, match.to_segment_id: to_row.version},
        },
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
    #: Compare-and-set on the matched segments the named carries came from
    #: (#4957 follow-up 1), keyed by segment id -- derived from each
    #: carry's own `SegmentMatch`, since carry itself does not carry
    #: segment ids in its own params.
    #:
    #: #4957 review 3 note (no code change): the token guards the MATCHED
    #: segments, not the copies uncarry actually removes -- so an
    #: unrelated reshape of the to-segment AFTER a carry blocks undoing
    #: that carry, even though the copy itself was never touched. Fails
    #: CLOSED and says why (a `SegmentStale` on the to-segment), which is
    #: the safe default; the more precise guard would be a token on each
    #: copy itself, not the segment it was carried onto.
    expected_versions: dict[str, int] = {}


@action("segment.uncarry", SegmentUncarryParams, domains=["segment"], undoable=False)
def _action_uncarry(db: Database, params: SegmentUncarryParams, ctx: ActionContext):
    # Gather every carry row and the matched segments it touches BEFORE
    # deleting anything -- #4957 follow-up 1: "an inverse must never
    # hard-delete something a later step touched", refuse instead. A carry
    # id already gone (some other, legitimate action already removed it)
    # is still silently skipped, unchanged from before this follow-up.
    carries: list[SegmentCarry] = []
    segment_ids: set[str] = set()
    for carry_id in params.carry_ids:
        carry = db.get(SegmentCarry, carry_id)
        if carry is None:
            continue
        carries.append(carry)
        match = db.get(SegmentMatch, carry.match_id)
        if match is not None:
            segment_ids.add(match.from_segment_id)
            segment_ids.add(match.to_segment_id)

    for segment_id in segment_ids:
        row = db.get(Segment, segment_id)
        if row is None:
            continue
        expected = params.expected_versions.get(segment_id)
        if expected is None or row.version != expected:
            raise _as_http_error(SegmentStale(
                segment_id, expected if expected is not None else -1, row.version,
                _stale_changed_fields(db, segment_id, expected if expected is not None else -1, row),
            ))

    removed_carry_ids: list[str] = []
    removed_copy_ids: list[str] = []
    for carry in carries:
        model, _anchor_field, _doc_field = _CARRY_MODELS[carry.carried_kind]
        copy_row = db.get(model, carry.copy_id)
        if copy_row is not None:
            db.delete(copy_row)
            removed_copy_ids.append(carry.copy_id)
        db.delete(carry)
        removed_carry_ids.append(carry.id)
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=removed_carry_ids,
        before=None,
        after={
            "carry_ids": removed_carry_ids, "copy_ids": removed_copy_ids,
            "versions": {sid: v.version for sid in segment_ids if (v := db.get(Segment, sid)) is not None},
        },
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


class SegmentVersionListResponse(BaseModel):
    """Typed version-list envelope for the OpenAPI client.

    `{items, count}`, never a bare array: a bare list endpoint is the
    shape `test_no_new_bare_array_get_endpoint` exists to keep out (#1075,
    where a bare list and an envelope for the same idea drifted apart).
    """

    items: list[SegmentVersion]
    count: int


@router.get("/{segment_id}/versions", response_model=SegmentVersionListResponse)
async def list_segment_versions(
    segment_id: str,
    db: Database = Depends(get_library_database),
) -> SegmentVersionListResponse:
    """`source.segment.versioned-alone`: one segment's own history, read
    without touching any other segment's rows."""
    _assert_not_provisional_http(segment_id, what="segment_id")
    rows = db.query(SegmentVersion, segment_id=segment_id)
    rows.sort(key=lambda r: r.version)
    return SegmentVersionListResponse(items=rows, count=len(rows))


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
