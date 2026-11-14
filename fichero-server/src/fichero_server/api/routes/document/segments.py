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
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fichero_server.media.rendition_boxes import SegmentsOnRendition
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
from fichero_server.api.main import get_library_database, get_library_database_for_write, readable_documents
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
from fichero_server.core.off_loop import off_loop

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


class SegmentRegionMismatchError(ValueError):
    """`segment.merge`'s participants do not all share one `parent_segment_id`
    (`source.textedit.backspace-joins-in-reading-order`: "refused with the
    reason across regions"). Two lines in different regions are not one
    continuation of the same passage, so backspace's line-join must not
    silently cross that boundary -- unlike the pass/document check above,
    NOTHING enforced this before this class existed."""


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


from fichero_server.llm.language_policy import BadDirection  # noqa: E402
from fichero_server.models.source_declarations import UnknownScript  # noqa: E402


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
    if isinstance(exc, (SegmentPassMismatchError, SegmentParentMismatchError, SegmentRegionMismatchError, SegmentForwardingWouldLoop, SegmentNotLive, SegmentDeleted, SegmentRestoreTargetGone, ArtifactNotInDocumentScope, SegmentMatchCrossDocument, SegmentPartGone, SegmentPassNotLive, SegmentPassIsConversionTarget)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (SegmentAnchorMismatchError, MatchNeedsAPerson, MatchNotAccepted, StatementsCarriedInStatementsStep, UnknownScript, BadDirection, UnknownCascadeFact)):
        # Slice 9 (#4938): a script this library cannot make sense of and a
        # direction outside the six. Converted HERE rather than at the call site
        # so there stays one place that maps a refusal to a status code.
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


class ScopedSegmentListResponse(BaseModel):
    """A page of segments across MANY documents (`source.editor.library-lists-segments`).

    Not `SegmentListResponse`: that one answers `document_id` and the page's passes,
    which a scoped list has neither of — the rows come from many documents and naming
    one would be a lie. `total` is the match count so a Library can page without
    fetching to find out how much there is.
    """

    items: list[SegmentRead]
    count: int
    #: Documents in the scope this caller may not read, and whose segments are therefore
    #: NOT in `items` or `total` (#5135). A count and never ids: naming a document the caller
    #: may not see would tell them it exists. 0 when nothing was withheld.
    withheld_documents: int = 0
    total: int
    #: The documents the scope resolved to, so a caller can tell an empty page
    #: ("nothing in these 40 documents") from an empty scope ("that folder has no
    #: documents") -- two different answers that both come back as no rows.
    document_ids: list[str]


def _with_texts(db: Database, rows: list[Segment], reads: list[SegmentRead]) -> list[SegmentRead]:
    """Each read's `text`: its counting transcription, for the whole list in one batch (#5139).

    Every real segment used to read `text: null` -- a caller could list 4,525 shapes and read
    none of them without one readings request each. A converted row whose words still come from
    its artifact keeps them; a stored reading is the answer otherwise.
    """
    from fichero_server.api.routes.document.segment_readings import counting_answers

    counted = counting_answers(db, rows)
    source_of = {row.id: getattr(row, "source_artifact_id", None) for row in rows}
    for read in reads:
        found = counted.get(read.id)
        if found is None:
            continue
        reading, answer = found
        # The label's facts (#6451): why this reading is the shown one, its level and who read it.
        read.counting_basis = answer.basis.value if answer is not None else "none"
        read.counting_level = reading.level
        read.read_by = reading.producer_model or reading.created_by
        if answer is None:
            continue  # none counts: the label names the newest person's reading; `text` is not claimed
        # A reading from another result than the one the pass came from (a later reader, a person) counts over the
        # words the pass's own result carried (#5707: after Read wrote a newer reading onto a Kraken pass's lines,
        # the list still served the pass's 00:40 words). The pass's own words stay where they are its result's.
        later = reading.derived_from_artifact_id != source_of.get(read.id)
        if read.text is None or later:
            read.text = reading.content
    return reads


@router.get("", response_model=ScopedSegmentListResponse)
async def list_segments_in_scope(
    request: Request,
    document_ids: Optional[str] = Query(
        None,
        description=(
            "Comma-separated document ids to list segments for. Either this or "
            "`parent_id`; `parent_id` resolves to a folder's descendants."
        ),
    ),
    parent_id: Optional[str] = Query(
        None, description="A folder (or page-bearing document): its descendants are the scope"
    ),
    kind: Optional[str] = Query(
        None, description="Restrict to one segment kind (region, line, word, ...)"
    ),
    pass_id: Optional[str] = Query(None, description="Restrict to one pass"),
    include_furniture: bool = Query(
        True, description="Include running heads, folio numbers and catchwords"
    ),
    limit: int = Query(200, ge=1, le=1000, description="Page size; bounded on purpose"),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str | None = Depends(optional_library_path),
) -> ScopedSegmentListResponse:
    """`GET /api/segments` — a bounded page of segments across a SCOPE.

    For `source.editor.library-lists-segments` (#4941): every other segments read is
    per document or per segment, so a Library listing segments would have had to ask
    once per page of the book. That is the N+1 the one-store seam exists to avoid,
    and moving it into the engine is the only way a project-wide list of lines is
    answerable at all.

    Only REAL rows. The per-document route also serves the old boxes of artifacts
    nobody has converted (`source.seam.read-either-store`), and that resolution is
    per artifact by nature — it reads one artifact's block and numbers its boxes.
    Doing it across a scope would mean hydrating every geometry blob in the folder to
    answer one page, which is the cost this endpoint exists to avoid. So a scoped list
    shows what has been converted, and says so here rather than appearing to show
    everything.

    `limit` is capped at 1000 by the signature (`source.store.bounded-reads`): a
    caller cannot ask for a whole project in one request, because a page of a library
    view never needs it and an agent asking for it would be asking for the thing that
    takes the engine down.
    """
    if (document_ids is None) == (parent_id is None):
        raise HTTPException(
            status_code=422,
            detail=(
                "Give exactly one of `document_ids` or `parent_id`: two scopes cannot "
                "be intersected here, and no scope would mean the whole library."
            ),
        )

    if document_ids is not None:
        scope = [value.strip() for value in document_ids.split(",") if value.strip()]
    else:
        # The tree walk lives here, not in the persistence method: what a scope IS
        # is a question about documents, and paging segment rows is a question about
        # segments. Mixing them would make the read's cost depend on a tree it
        # cannot see.
        scope = [parent_id] if parent_id else []
        frontier = list(scope)
        seen = set(scope)
        while frontier:
            children = db.query(Document, parent_id=frontier.pop())
            for child in children:
                if child.id in seen:
                    continue
                seen.add(child.id)
                scope.append(child.id)
                frontier.append(child.id)

    # ACCESS CONTROL (#5135): the router's read check sees ONE id from the query at most
    # (`parent_id`; `document_ids` is a list), so a scope is never trusted. Every document in
    # it is checked the way a single-document read is, and the ones this caller may not read
    # are withheld -- and COUNTED, so a shorter list is never a silent one.
    from fichero_server.knowledge.trash_visibility import visible_document_ids  # noqa: PLC0415

    scope = visible_document_ids(db, scope)  # a trashed document's segments are out of view with it
    readable = readable_documents(request, x_fichero_library_path, scope)
    withheld = len(scope) - len(readable)
    scope = readable

    rows, total = db.segments_page(
        document_ids=scope,
        kind=kind,
        pass_id=pass_id,
        include_furniture=include_furniture,
        limit=limit,
        offset=offset,
    )
    items = _with_texts(db, rows, [segment_read_from_row(row) for row in rows])
    return ScopedSegmentListResponse(
        items=items, count=len(items), total=total, document_ids=scope,
        withheld_documents=withheld,
    )


@router.get("/document/{doc_id}/on-rendition/{rendition_id}", response_model=SegmentsOnRendition)
@off_loop
def segments_on_a_rendition(doc_id: str, rendition_id: str, db: Database = Depends(get_library_database)) -> SegmentsOnRendition:
    """The page's live segments' boxes in this rendition's pixels, so the Preview can draw them on it (#6420)."""
    from fichero_server.media.rendition_boxes import segments_on_rendition
    from fichero_server.models import Rendition

    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    rendition = db.get(Rendition, rendition_id)
    if rendition is None or rendition.document_id != doc_id:
        raise HTTPException(status_code=404, detail=f"Rendition not found on this page: {rendition_id}")
    return segments_on_rendition(db, doc, rendition, db.query(Segment, document_id=doc_id))


class SegmentProblem(BaseModel):
    """One thing wrong with a page's segments (`segment-editor.validate-before-export`)."""

    kind: str = Field(description="no-shape, self-crossing, no-baseline, line-outside-regions, empty-region, overlap, "
                                  "order-repeat, order-gap, order-missing or words-do-not-tile.")
    segment_ids: list[str]
    detail: str
    pass_id: str
    order_id: Optional[str] = None
    share: Optional[float] = None


class SegmentValidation(BaseModel):
    document_id: str
    problems: list[SegmentProblem]


@router.get("/document/{doc_id}/validate", response_model=SegmentValidation)
@off_loop
def validate_document_segments(doc_id: str, db: Database = Depends(get_library_database)) -> SegmentValidation:
    """What is wrong with the page's segments, per pass, before an export (`segment-editor.validate-before-export`):
    reads, writes nothing. An empty list is a page with nothing to fix."""
    from fichero_server.media import segment_checks
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    if not db.get(Document, doc_id):
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    rows = [row for row in db.query(Segment, document_id=doc_id) if row.deleted_at is None]
    problems: list[SegmentProblem] = []
    for pass_id in sorted({row.pass_id for row in rows}):
        in_pass = [row for row in rows if row.pass_id == pass_id]
        orders = [
            (order, list(db.query(ReadingOrderEntry, order_id=order.id)))
            for order in db.query(ReadingOrder, pass_id=pass_id) if order.deleted_at is None
        ]
        texts = {}
        for row in in_pass:
            if row.kind == "line":
                counted = _counting_readings(db, row.id)
                _rid, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
                if text:
                    texts[row.id] = text
        problems.extend(
            SegmentProblem(pass_id=pass_id, **problem) for problem in segment_checks.check_pass(in_pass, orders, texts)
        )
    return SegmentValidation(document_id=doc_id, problems=problems)


class DoubtfulLine(BaseModel):
    segment_id: str
    #: The lowest confidence the line has (its shape's, its words' cuts'); 0 with a validator finding; None when
    #: nothing measured it.
    confidence: Optional[float] = None
    #: Why it is doubtful, in words: "shape 42%", "cut 30%", and each finding's kind ("no-baseline", …).
    reasons: list[str] = []


class DoubtfulLines(BaseModel):
    document_id: str
    pass_id: Optional[str] = None
    lines: list[DoubtfulLine]


@router.get("/document/{doc_id}/doubtful", response_model=DoubtfulLines)
@off_loop
def doubtful_lines(doc_id: str, db: Database = Depends(get_library_database)) -> DoubtfulLines:
    """The page's lines on its working pass by confidence, lowest first (`segment-editor.low-confidence-lens`): a line
    with a validator finding first, then the least sure shape or word cut, then lines nothing measured. Reads, writes
    nothing; the Check lens lists it and Next Doubtful steps through it."""
    from fichero_server.api.routes.document.segment_readings import working_pass
    from fichero_server.media import segment_checks
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    if not db.get(Document, doc_id):
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    pass_id = working_pass(db, doc_id).pass_id
    rows = [row for row in db.query(Segment, document_id=doc_id) if row.deleted_at is None and row.pass_id == pass_id]
    orders = [
        (order, list(db.query(ReadingOrderEntry, order_id=order.id)))
        for order in db.query(ReadingOrder, pass_id=pass_id) if order.deleted_at is None
    ] if pass_id else []
    findings: dict[str, list[str]] = {}
    for problem in segment_checks.check_pass(rows, orders, {}):
        for segment_id in problem["segment_ids"]:
            findings.setdefault(segment_id, []).append(problem["kind"])
    cuts: dict[str, float] = {}
    for row in rows:
        sure = (row.metadata or {}).get("cut_confidence")
        if row.kind == "word" and row.parent_segment_id and isinstance(sure, (int, float)):
            cuts[row.parent_segment_id] = min(cuts.get(row.parent_segment_id, 1.0), float(sure))

    lines = []
    for row in rows:
        if row.kind != "line":
            continue
        reasons, measured = list(dict.fromkeys(findings.get(row.id, []))), []
        if row.confidence is not None:
            measured.append(row.confidence)
            reasons.append(f"shape {round(row.confidence * 100)}%")
        if row.id in cuts:
            measured.append(cuts[row.id])
            reasons.append(f"cut {round(cuts[row.id] * 100)}%")
        confidence = 0.0 if findings.get(row.id) else (min(measured) if measured else None)
        lines.append(DoubtfulLine(segment_id=row.id, confidence=confidence, reasons=reasons))
    lines.sort(key=lambda line: (line.confidence is None, line.confidence or 0.0))
    return DoubtfulLines(document_id=doc_id, pass_id=pass_id, lines=lines)


class SimplifiedShape(BaseModel):
    segment_id: str
    #: None: the outline (or baseline) is already as simple as the tolerance allows.
    polygon: Optional[list[list[float]]] = None
    baseline: Optional[list[list[float]]] = None


class SimplifyPreview(BaseModel):
    document_id: str
    shapes: list[SimplifiedShape]


@router.get("/document/{doc_id}/simplify-preview", response_model=SimplifyPreview)
@off_loop
def preview_simplify_segments(
    doc_id: str,
    segment_ids: list[str] = Query(..., description="The segments the slider simplifies."),
    tolerance: float = Query(..., gt=0, description="How far, in image pixels, the simpler shape may stray."),
    db: Database = Depends(get_library_database),
) -> SimplifyPreview:
    """What `segment.simplify` would write at this tolerance, written nowhere (`segment-editor.vertices`): the Shape
    popover's slider draws it live and sends the action once on release. A shape it would not change is left out."""
    rows = []
    for segment_id in dict.fromkeys(segment_ids):
        row = db.get(Segment, segment_id)
        if row is None or row.deleted_at is not None or row.document_id != doc_id:
            raise HTTPException(status_code=404, detail=f"Segment not found on this page: {segment_id}")
        rows.append(row)
    return SimplifyPreview(document_id=doc_id, shapes=[
        SimplifiedShape(segment_id=row.id, polygon=polygon, baseline=baseline)
        for row, polygon, baseline in _simplified_shapes(db, rows, tolerance)
    ])


@router.get("/document/{doc_id}", response_model=SegmentListResponse)
@off_loop
def list_document_segments(
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
            elif pass_row.source_artifact_type is not None:
                # The result was deleted (#5066): its type was kept on the pass, and the words are the
                # segments' own readings now.
                pass_artifact_type = pass_row.source_artifact_type
            elif db.get(Artifact, pass_row.source_artifact_id) is not None:
                # It exists, it just belongs to somebody else's page. No text
                # is the honest answer, and it is logged, never silent.
                logger.warning(
                    "pass %s on document %s names artifact %s, which belongs to a "
                    "different document; serving its segments without text rather "
                    "than another document's words (#4958)",
                    pass_row.id, doc_id, pass_row.source_artifact_id,
                )
        pass_segments = _with_texts(db, rows, [
            segment_read_from_row(
                row,
                box_index=index,
                source_block=source_block,
                source_artifact_id=pass_row.source_artifact_id,
            )
            for index, row in enumerate(rows)
        ])
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
        if area_rect:
            # The SAME rule as the rows above (#4985, `source.seam.area-applies-to-either-store`):
            # each box's rectangle is the one it would have as a row (`_converted_box_columns`), so a
            # page answers an area the same before and after it converts.
            from fichero_server.models.segments import _converted_box_columns

            artifact_segments = [
                s for s in artifact_segments
                if rects_intersect(tuple(_converted_box_columns(s)[:4]), area_rect)
            ]
        if not artifact_segments and (kind or area_rect):
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
    _mark_working_pass(db, doc_id, passes, segments)

    return SegmentListResponse(document_id=doc_id, passes=passes, segments=segments)


def _mark_working_pass(db: Database, doc_id: str, passes: list[PassRead], segments: list[SegmentRead]) -> None:
    """Say which pass is the page's working pass, and why (#5156), worked out once per page, never
    per row -- by `working_pass`, the one answer the text, the Order list and export read (#5467).

    It used to rank here with a rule of its own for the PROVISIONAL passes (an unconverted result's
    boxes) and with only the passes this response held, so a filtered read and the page's text could
    name different passes. The provisional rule now lives in `resolve_working_pass`, and the page's
    every pass and result is judged whatever this read was filtered to.

    The same ranking says which pass the image draws (`resolve_drawn_pass`, #5467) and each pass's
    place in it, so the app draws `drawn` and keeps no fallback ranking of its own."""
    from fichero_server.api.routes.document.segment_readings import passes_with_shapes, ranked_passes
    from fichero_server.models.readings import resolve_drawn_pass

    ranked = ranked_passes(db, doc_id)
    drawn_id = resolve_drawn_pass(ranked, passes_with_shapes(db, doc_id)) if ranked else None
    place = {answer.pass_id: index for index, answer in enumerate(ranked)}
    for pass_read in passes:
        pass_read.rank = place.get(pass_read.id)
        pass_read.drawn = pass_read.id == drawn_id
        pass_read.shapeless = drawn_id is not None and place.get(pass_read.id) == 0 and pass_read.id != drawn_id
        if pass_read.rank == 0:
            pass_read.working = True
            pass_read.working_basis = ranked[0].basis.value


# ---------------------------------------------------------------------------
# Slice 3 writes
# ---------------------------------------------------------------------------


class SegmentPassCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description='The document (page) the new pass belongs to.')
    name: str = Field(description="The pass's name, as the Layers list shows it.")
    run_id: Optional[str] = Field(default=None, description='The run that produced this pass, when a run did.')
    source_artifact_id: Optional[str] = Field(default=None, description='The artifact the pass was read from, when it came from one.')


def _new_pass_provenance_kind(
    *, ctx: ActionContext, run_id: str | None, provider: str | None, model: str | None,
) -> ProvenanceKind:
    """Set by the engine from how the write arrived: a provider/model behind the pass means a
    machine made it; otherwise the ONE rule every source-model write uses,
    `provenance_kind_from_ctx` -- which reads the run the REQUEST came from and the MCP surface.
    This used to be a second copy that read only a `run_id` in the params, so a run creating a
    pass under its own context stamped it `human` (#4868/#4869's class), and an agent's pass was
    never `agent`."""
    if provider or model:
        return ProvenanceKind.workflow
    if run_id and not ctx.run_id:
        return ProvenanceKind.workflow
    return provenance_kind_from_ctx(ctx)


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
            ctx=ctx, run_id=params.run_id, provider=provider, model=model,
        ),
        actor=ctx.actor,
        provider=provider,
        model=model,
        run_id=params.run_id or ctx.run_id,
        source_artifact_id=params.source_artifact_id,
    )
    db.save(pass_row)
    # Slice 10 (#4930): a pass has its `as-written` order from the moment it
    # exists, so no page is ever shown an empty order list while it visibly has
    # lines. Entries arrive with the segments (`_place_in_as_written` below).
    # Local import: `reading_orders` imports this module for
    # `provenance_kind_from_ctx`, so a module-level import here would be a cycle.
    from fichero_server.api.routes.document.reading_orders import ensure_as_written_order

    ensure_as_written_order(
        db,
        document_id=pass_row.document_id,
        pass_id=pass_row.id,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
    )
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


class SegmentPassGroundTruthParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str
    #: True marks the pass ground truth; False unmarks it.
    ground_truth: bool


def _invert_pass_ground_truth(before, after, ctx: ActionContext):
    if not before:
        return None
    return ("segment.pass_ground_truth", {"pass_id": before["pass_id"], "ground_truth": before["ground_truth"]})


@action(
    "segment.pass_ground_truth",
    SegmentPassGroundTruthParams,
    # `representation`: on a marked pass the file's readings count as a person's, so the page's text
    # (and which pass is working) can change; the text cache refreshes on it.
    domains=["segment", "representation"],
    undoable=True,
    invert=_invert_pass_ground_truth,
)
def _action_pass_ground_truth(db: Database, params: SegmentPassGroundTruthParams, ctx: ActionContext):
    """Mark a pass as ground truth, or unmark it (#5513, `source.onboard.ground-truth-from-files`).

    A person vouching that a pass's transcriptions are corrected: imported PAGE/ALTO/TEI arrive as the
    FILE's (`external_import`), and only a person can say they are right. Who made the pass is not
    rewritten; the mark is its own fact on the pass, read through `made_by_a_person` by the bake-off,
    the evaluation and the working pass, and by the readings' counting. Undo puts the mark back as it was.
    """
    _assert_not_provisional_http(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if pass_row is None or pass_row.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Pass not found: {params.pass_id}")
    before = {"pass_id": pass_row.id, "ground_truth": pass_row.ground_truth}
    pass_row.ground_truth = params.ground_truth
    db.save(pass_row)
    after = {"pass_id": pass_row.id, "ground_truth": pass_row.ground_truth}
    return after, ChangeSpec(
        domains=["segment", "representation"],
        target_ids=[pass_row.id],
        before=before,
        after=after,
        emit_type="segment.pass_updated",
        pass_ids=[pass_row.id],
        document_ids=[pass_row.document_id],
    )


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

    document_id: str = Field(description='The document (page) the segment is on.')
    pass_id: str = Field(description='The pass (layer) the segment joins.')
    kind: str = Field(description="The segment's kind: region, line, word, ...")
    anchor: SourceAnchor = Field(description='Where the segment sits on the page: a box or polygon in page coordinates.')
    baseline: Optional[list[list[float]]] = Field(default=None, description="The line's baseline as [[x, y], ...] points in page coordinates.")
    parent_segment_id: Optional[str] = Field(default=None, description="The segment this one sits inside (a line's region).")
    kind_raw: Optional[str] = Field(default=None, description='The kind as the source format named it (e.g. a PAGE XML region type).')
    #: `segment-editor.marker`: a freehand stroke, simplified on the way in so the record never holds a point per pixel.
    smoothing: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="Simplify the outline and baseline as drawn by hand: 0 keeps nearly every bend, 1 the fewest points.",
    )
    #: `segment-editor.marker`: a line drawn as a baseline gets its outline from the ink, as Redraw Outline does.
    outline_from_baseline: bool = Field(
        default=False, description="Draw the line's outline from its baseline and the page's ink.",
    )
    #: `segment-editor.paintbrush`: the Paintbrush's stroke, `[x, y, width]` per point (x and y in page fractions, the
    #: width in image pixels): the painted area becomes the outline, the path the baseline.
    brush_stroke: Optional[list[list[float]]] = Field(
        default=None,
        description="A Paintbrush stroke, [x, y, width] per point (width in image pixels): its painted area is the outline, its path the baseline.",
    )
    #: `segment-editor.edge.overlapping-regions`: with no parent given, the engine puts the segment in the region that
    #: holds most of it.
    place_in_region: bool = Field(
        default=False,
        description="With no parent given, put the segment in the region holding most of it (the smaller on a tie).",
    )


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


def _simple_anchor(anchor: SourceAnchor | None) -> tuple[SourceAnchor | None, bool]:
    """`segment-editor.edge.self-intersecting`: a self-crossing outline is never written. The anchor with its polygon
    made the outer boundary of the area it covers, and its rect the bound of that; and whether it was changed."""
    from fichero_server.media import line_join

    if anchor is None or not anchor.polygon or len(anchor.polygon) < 4:
        return anchor, False
    polygon, simplified = line_join.simple_outline(anchor.polygon)
    if not simplified:
        return anchor, False
    x0, y0, x1, y1 = line_join.bounds(polygon)
    return anchor.model_copy(update={"polygon": polygon, "rect": [x0, y0, x1 - x0, y1 - y0]}), True


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

    anchor, simplified = _simple_anchor(params.anchor)
    spec_obj = SegmentSpec(
        kind=params.kind, anchor=anchor, baseline=params.baseline,
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
    if simplified:
        segment.metadata = {**(segment.metadata or {}), "outline_simplified": True}
    db.save(segment)
    _place_in_as_written(db, segment, ctx)
    return segment


def _place_in_as_written(db: Database, segment: Segment, ctx: ActionContext) -> None:
    """Put a new segment into its pass's `as-written` order, at its PAGE place.

    Slice 10 (#4930). Not an append: `as-written` is the order the source was
    written in, so a line drawn last but positioned third belongs third. The
    place is worked out by `place_in_page_order`, which uses the one imported
    sort; this function only decides WHETHER there is an order to place it in.

    A pass made before slice 10 has no `as-written` order and does not get one
    here: making one silently on a write would invent a machine's order inside
    somebody's editing session, and the migration story for old libraries is the
    order being made on demand (`reading_order.create(seed_from_pass=True)`),
    which is one call and is auditable.
    """
    from fichero_server.api.routes.document.reading_orders import (
        as_written_order,
        place_in_page_order,
    )

    order = as_written_order(db, segment.pass_id)
    if order is None:
        return
    place_in_page_order(db, order, segment)


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
    params, outline = _marker_shapes(db, params)
    if params.place_in_region and params.parent_segment_id is None and params.kind != "region":
        region = _containing_region(db, params)
        if region is not None:
            params = params.model_copy(update={"parent_segment_id": region.id})
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
    answer: dict = {"segment_ids": [segment.id]}
    if outline is not None:
        answer["outline"] = outline
    if (segment.metadata or {}).get("outline_simplified"):
        # `segment-editor.edge.self-intersecting`: the answer says the outline was simplified.
        answer["simplified"] = True
    return answer, change_spec


def _containing_region(db: Database, params: SegmentCreateParams, minimum_span: float = 0.004) -> Segment | None:
    """The live region of the pass that holds MOST (over half) of the new segment's bounds, the smaller on a tie
    (`segment-editor.edge.overlapping-regions`, `SegmentShapes.containingRegion`'s rule); None when none does. A flat
    baseline is padded to `minimum_span`, as it is drawn."""
    from fichero_server.media import line_join

    anchor = params.anchor
    points = list(anchor.polygon or []) + list(params.baseline or [])
    for shape in anchor.shapes or []:
        points += list(shape.points or [])
    if anchor.rect:
        x, y, w, h = anchor.rect
        points += [[x, y], [x + w, y + h]]
    if not points:
        return None
    x0, y0, x1, y1 = line_join.bounds(points)
    if x1 - x0 < minimum_span:
        x0, x1 = (x0 + x1 - minimum_span) / 2, (x0 + x1 + minimum_span) / 2
    if y1 - y0 < minimum_span:
        y0, y1 = (y0 + y1 - minimum_span) / 2, (y0 + y1 + minimum_span) / 2
    area = (x1 - x0) * (y1 - y0)
    scored = []
    for row in db.query(Segment, pass_id=params.pass_id):
        if row.kind != "region" or row.deleted_at is not None or row.document_id != params.document_id:
            continue
        rx, ry, rw, rh = row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h
        width = min(x1, rx + rw) - max(x0, rx)
        height = min(y1, ry + rh) - max(y0, ry)
        if width > 0 and height > 0:
            scored.append((width * height / area, rw * rh, row))
    held = [entry for entry in scored if entry[0] > 0.5]
    return min(held, key=lambda entry: (-entry[0], entry[1]))[2] if held else None


#: `segment-editor.marker`: the Douglas-Peucker tolerance, in image pixels, at smoothing 0 and 1.
MARKER_TOLERANCE_PX = (0.5, 5.0)


def _marker_shapes(db: Database, params: SegmentCreateParams) -> tuple[SegmentCreateParams, str | None]:
    """A Marker stroke made ready to store (`segment-editor.marker`): the outline and baseline as drawn simplified at
    `smoothing` in the page image's pixels, and a line drawn as a baseline given its outline from the ink. Answers the
    params to create with and, when an outline was asked for, "drawn" or "none" (no ink along the baseline: the line
    keeps its baseline alone, and the answer says so). Params with neither are returned untouched."""
    if params.smoothing is None and not params.outline_from_baseline and not params.brush_stroke:
        return params, None
    from fichero_server.media import line_join, outline_from_baseline

    document = db.get(Document, params.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {params.document_id}")
    image, forward, back = _page_image_for_lines(db, document)
    anchor, baseline = params.anchor, params.baseline
    if params.brush_stroke:
        from fichero_server.media import paint_stroke

        low, high = MARKER_TOLERANCE_PX
        pixels = forward([p[:2] for p in params.brush_stroke])
        made = paint_stroke.painted(
            [[x, y, p[2]] for (x, y), p in zip(pixels, params.brush_stroke) if len(p) >= 3],
            low + (high - low) * (params.smoothing if params.smoothing is not None else 0.5),
        )
        if made is None:
            raise HTTPException(status_code=422, detail="the brush stroke painted nothing: every point needs a width")
        outline, centre = made
        polygon = [[round(x, 6), round(y, 6)] for x, y in back(outline)]
        x0, y0, x1, y1 = line_join.bounds(polygon)
        anchor = anchor.model_copy(update={"polygon": polygon, "rect": [x0, y0, x1 - x0, y1 - y0], "shapes": None})
        baseline = [[round(x, 6), round(y, 6)] for x, y in back(centre)]
        return params.model_copy(update={"anchor": anchor, "baseline": baseline, "brush_stroke": None}), None
    if params.smoothing is not None:
        low, high = MARKER_TOLERANCE_PX
        tolerance = low + (high - low) * params.smoothing
        if anchor.polygon and len(anchor.polygon) > 3:
            fewer = _fewer_points(anchor.polygon, True, 3, tolerance, forward, back)
            if fewer is not None:
                x0, y0, x1, y1 = line_join.bounds(fewer)
                anchor = anchor.model_copy(update={"polygon": fewer, "rect": [x0, y0, x1 - x0, y1 - y0]})
        if baseline and len(baseline) > 2:
            baseline = _fewer_points(baseline, False, 2, tolerance, forward, back) or baseline
    outline = None
    if params.outline_from_baseline and baseline and len(baseline) >= 2:
        neighbours = [
            row.baseline for row in db.query(Segment, pass_id=params.pass_id)
            if row.deleted_at is None and row.baseline and len(row.baseline) >= 2
        ]
        [drawn] = outline_from_baseline.outlines(image, [forward(baseline)], [forward(line) for line in neighbours], None)
        outline = "none" if drawn is None else "drawn"
        if drawn is not None:
            polygon = [[round(x, 6), round(y, 6)] for x, y in back(drawn)]
            x0, y0, x1, y1 = line_join.bounds(polygon)
            anchor = anchor.model_copy(update={"polygon": polygon, "rect": [x0, y0, x1 - x0, y1 - y0], "shapes": None})
    return params.model_copy(update={"anchor": anchor, "baseline": baseline}), outline


def _fewer_points(points, closed: bool, least: int, tolerance: float, forward, back) -> list[list[float]] | None:
    """Douglas-Peucker on `points` (page fractions) in the image's pixels; None when it would not drop a point or would
    leave fewer than `least`."""
    import cv2
    import numpy as np

    pixels = np.array(forward(points), dtype=np.float32).reshape(-1, 1, 2)
    kept = cv2.approxPolyDP(pixels, tolerance, closed).reshape(-1, 2).tolist()
    if len(kept) < least or len(kept) >= len(points):
        return None
    return [[round(x, 6), round(y, 6)] for x, y in back(kept)]


class SegmentCreateManyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description='The document (page) the segments are on.')
    pass_id: str = Field(description='The pass (layer) the segments join.')
    segments: list[SegmentSpec] = Field(description='The segments to create, each with its kind and anchor.')


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


def _unchanged_since(db: Database, segment_id: str, expected_version: int, current_row: Segment) -> bool:
    """Whether the row holds EXACTLY what it held at `expected_version`, though its number moved on.

    For a RESTORE only -- the undo path. Each update's inverse restores `version - 1` checked against
    the version the update made. Undo two edits of one segment, newest first: undoing the newer one is
    itself a restore, which bumps the number while putting back the older edit's result. The older
    edit's undo then met a number it did not expect and was refused (409), so the second ⌘Z of any
    two successive edits of one segment -- two moves, a reshape then a baseline -- failed (found
    2026-09-28 pinning Reshape's undo). A number that moved while the CONTENT is what the caller
    saw is not somebody else's work; content that differs still is, and is still refused.
    """
    snapshots = db.query(SegmentVersion, segment_id=segment_id, version=expected_version)
    return bool(snapshots) and not changed_fields(snapshots[0], current_row)


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

    segment_ids: list[str] = Field(description='The segments to delete.')
    expected_versions: dict[str, int] = Field(description="Each segment's version as last read, {segment_id: version}; a changed segment is refused.")
    #: Capped (#4923 review): recorded inside the tamper-evident audit
    #: chain, where nothing can ever be purged -- an operator's short note
    #: about the delete, never a quote from a source. Whether even a short
    #: typed field belongs in the chain at all is the maintainer's open
    #: question (morning file, question 17/23), not settled here.
    reason: Optional[str] = Field(default=None, max_length=200, description='A short note about the delete (kept in the audit log).')


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
    params: dict = {"segment_ids": list(versions.keys())}
    if after.get("order_entries"):
        params["order_entries"] = after["order_entries"]
    return ("segment.undelete", params)


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
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries

    order_entries = remove_segment_entries(db, list(params.segment_ids))
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=list(params.segment_ids),
        before=before_versions,
        after={"segment_ids": params.segment_ids, "versions": after_versions, "order_entries": order_entries},
        emit_type="segment.deleted",
        segment_ids=list(params.segment_ids),
        pass_ids=list(pass_ids),
        document_ids=list(document_ids),
    )
    return {"segment_ids": params.segment_ids}, spec


class SegmentOrderEntryParams(BaseModel):
    """One order entry as `segment.delete` recorded it (`reading_orders.ENTRY_FIELDS`)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    order_id: str
    segment_id: str
    position: float
    parent_entry_id: Optional[str] = None
    version: int = 1


class SegmentUndeleteParams(BaseModel):
    """`segment.delete`'s inverse -- also directly callable to bring a
    deleted segment back (`source.segment.delete-is-undoable`).

    Takes no `expected_version` (#4923 second look): a deleted segment
    cannot change -- `update`, `merge`, `split` and `carry` all refuse a
    not-live participant -- so "is it deleted" (checked below) is the
    WHOLE precondition. A stale undelete (already live) is a plain 409,
    not a `SegmentStale`."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description='The deleted segments to bring back.')
    #: The order entries the delete took out (`remove_segment_entries`), written back where they were.
    #: Only entries OF these segments are accepted: an undelete puts back a segment's own places, never
    #: anyone else's.
    order_entries: list[SegmentOrderEntryParams] = Field(default_factory=list, description='The reading-order entries the delete took out, written back where they were.')


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
    strangers = [entry.segment_id for entry in params.order_entries if entry.segment_id not in rows]
    if strangers:
        raise HTTPException(status_code=422, detail=f"order_entries name segments not being restored: {strangers}")
    from fichero_server.api.routes.document.reading_orders import restore_segment_entries

    restore_segment_entries(db, [entry.model_dump() for entry in params.order_entries])
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

    segment_id: str = Field(description='The segment to change.')
    expected_version: int = Field(description="The segment's version as last read; a changed segment is refused.")
    anchor: Optional[SourceAnchor] = Field(default=None, description="The segment's new place on the page.")
    baseline: Optional[list[list[float]]] = Field(default=None, description="The line's new baseline as [[x, y], ...] points.")
    kind: Optional[str] = Field(default=None, description="The segment's new kind.")
    kind_raw: Optional[str] = Field(default=None, description='The kind as the source format named it.')
    parent_segment_id: Optional[str] = Field(default=None, description='The segment this one now sits inside.')
    is_furniture: Optional[bool] = Field(default=None, description='True marks the segment as page furniture (running heads, folio numbers).')
    mark_state: Optional[Literal['ticked', 'crossed', 'struck', 'none']] = Field(default=None, description='The segment\'s one mark: ticked, crossed, struck or none.')
    no_writing_model: Optional[str] = Field(default=None, description="The reader (model) that looked at this line and found no writing on it: the line counts as read for that reader, and a different one looks again (#5758).")
    unread_reason: Optional[str] = Field(default=None, description="Why a reader left this line without a reading, in words (a model's refusal, or an answer that was not a reading): the line stays unread and says so (#5894).")
    #: The cascade's three facts (slice 9, #4938). Set here rather than through
    #: an action of their own, because `segment.update` already owns the version
    #: snapshot, the stale check, the inverse and the audit row -- a second
    #: writer for the same row would be a second place to keep all four correct
    #: (`iterate, never replace`).
    #:
    #: **AND DELIBERATELY NOT IN `source_setting.set`**, which owns the same three
    #: facts at the PROJECT and NODE levels and refuses `level="segment"` by
    #: naming this action (ruled 2026-09-26, option A). The build notes designed
    #: one entry point for every level; by the time it was built, a segment's
    #: facts were ordinary columns beside its others, and routing them elsewhere
    #: would have made this the only segment action that cannot change some of the
    #: segment's own columns -- which a later reader finds odd and "fixes". If you
    #: came here to move these into `source_setting.set`, that is the reason not
    #: to, and it is written at both ends on purpose.
    #:
    #: `None` means NOT GIVEN, as it does for every field above; clearing a fact
    #: back to "never determined" is not expressible here and waits for
    #: `source_setting.clear`, which is the general project/node/segment action
    #: the build notes describe. Undo reverses a mis-set value in the meantime.
    language: Optional[str] = Field(default=None, description="The segment's language, a BCP 47 tag.")
    script: Optional[str] = Field(default=None, description="The segment's script, an ISO 15924 code.")
    direction: Optional[str] = Field(default=None, description="The segment's writing direction.")
    #: NOT accepted from a caller: `language_meta`, `script_meta` and
    #: `direction_meta` are provenance, and the engine writes them from `ctx`
    #: (#4868/#4869 -- a machine's claim recorded as a person's is the defect
    #: that rule exists for). `extra="forbid"` above turns an attempt into a 422.


def _apply_cascade_facts(
    db: Database, row: Segment, params: "SegmentUpdateParams", ctx: ActionContext
) -> None:
    """Set a segment's language, script and direction (slice 9, #4938).

    THE WRITE PATH the cascade was missing. Until this existed `Segment.language`
    and `.script` were fields no action could set, so `source.lang.many-per-page`
    could not be true end to end however faithfully the read seam carried them:
    a page comes back as three answers only if something can record three.

    Two rules it exists to keep in one place:

    * **Every script value is validated** (`assert_known_script`), the same call
      `representation.create` makes. One validated path and one unvalidated path
      for the same fact is the sibling-defect shape -- a fix that lands on one
      caller and not the others, with nothing flagging it.
    * **Provenance is engine-set, never client-supplied** (#4868/#4869). The
      caller sends a value; the meta is built here from `ctx`, so a runner's
      determination cannot be recorded as a person's judgement.
    """
    from fichero_server.llm.language_policy import (
        LEVEL_SEGMENT,
        SOURCE_DETECTED,
        SOURCE_USER,
        STATUS_KNOWN,
        assert_known_direction,
        build_language_meta,
    )
    from fichero_server.models.source_declarations import assert_known_script

    if params.language is None and params.script is None and params.direction is None:
        return

    by_a_person = provenance_kind_from_ctx(ctx) == ProvenanceKind.human
    source = SOURCE_USER if by_a_person else SOURCE_DETECTED
    who = "a person" if by_a_person else "this run"

    if params.script is not None:
        try:
            assert_known_script(db, params.script)
        except ValueError as refusal:
            raise _as_http_error(refusal) from refusal
    if params.direction is not None:
        try:
            assert_known_direction(params.direction)
        except ValueError as refusal:
            raise _as_http_error(refusal) from refusal

    for field, value in (
        ("language", params.language),
        ("script", params.script),
        ("direction", params.direction),
    ):
        if value is None:
            continue
        setattr(row, field, value)
        setattr(
            row,
            f"{field}_meta",
            build_language_meta(
                status=STATUS_KNOWN,
                source=source,
                level=LEVEL_SEGMENT,
                basis=f"set on this region by {who}",
            ),
        )


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

    simplified = False
    if params.anchor is not None:
        row.anchor, simplified = _simple_anchor(params.anchor)
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
        _mark_furniture(row, params.is_furniture)
    if params.mark_state is not None:
        row.mark_state = params.mark_state
    if params.no_writing_model is not None:
        row.metadata = {**(row.metadata or {}), "read_no_writing": {"model": params.no_writing_model}}
    if params.unread_reason is not None:
        row.metadata = {**(row.metadata or {}), "unread_reason": params.unread_reason}
    _apply_cascade_facts(db, row, params, ctx)
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
    answer: dict = {"segment_id": row.id, "version": row.version}
    if simplified:
        # `segment-editor.edge.self-intersecting`: a reshape that crossed itself is stored as its outer boundary.
        answer["simplified"] = True
    return answer, spec


#: The three facts a segment can carry from the cascade, plus the region-only
#: line progression. Named once so the clear action and its refusal cannot drift
#: from each other (slice 9, #4938).
CASCADE_FACT_KEYS: tuple[str, ...] = ("language", "script", "direction", "line_progression")


class UnknownCascadeFact(ValueError):
    """Raised when a clear names something that is not one of the four facts.

    Names the list, so a caller that sent `lang` or `encoding` is told what it
    may send -- and `encoding` in particular is the one somebody WILL try, since
    it is the third fact of `three-facts` but lives on the script row and not on
    a segment at all.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"{key!r} is not a fact a segment carries; this clears any of: "
            + ", ".join(CASCADE_FACT_KEYS)
            + (
                ". Encoding is a property of the SCRIPT, recorded on the script "
                "row, so there is nothing to clear here"
                if key == "encoding"
                else ""
            )
        )


class SegmentFactsClearParams(BaseModel):
    """Clear a segment's own language, script or direction back to NOT STATED.

    The segment-level half of the build notes' `source_setting.clear`; the
    project and node levels arrive with the general action.

    WHY A SEPARATE ACTION rather than a sentinel on `segment.update`: every
    optional field on that action means "not given", and overloading one of them
    to also mean "set this to nothing" would make `language=""` and
    `language=None` two different instructions distinguished by nothing a reader
    can see. Clearing is also the rarer, more deliberate act -- a curator saying
    "I was wrong to state this at all", which is not the same as correcting a
    value -- and it deserves its own audit row saying so.

    It shares `segment.update`'s snapshot and inverse, so an accidental clear is
    undone by the same restore path as any other change.
    """

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    expected_version: int
    #: Which facts to clear. Explicit rather than "all of them", because
    #: clearing a language while meaning to clear a direction is a data loss
    #: nothing warns about.
    keys: list[str]


_invert_segment_facts_clear = _invert_via_previous_version


@action(
    "segment.facts_clear",
    SegmentFactsClearParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_segment_facts_clear,
)
def _action_segment_facts_clear(
    db: Database, params: SegmentFactsClearParams, ctx: ActionContext
):
    """`source.lang.unknown-is-not-unexamined` as a WRITE: this restores the
    never-determined state, which is a different act from recording that
    something was examined and could not be told. That second thing is a value
    plus a meta saying `status=unknown`, and it is what `segment.update` writes;
    this leaves the meta empty, because nothing has been determined about this
    fact at this level any more.
    """
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    if not params.keys:
        raise HTTPException(status_code=422, detail="keys is empty: nothing to clear")
    for key in params.keys:
        if key not in CASCADE_FACT_KEYS:
            raise _as_http_error(UnknownCascadeFact(key))

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

    audit_id = uuid.uuid4().hex
    before_version = row.version
    snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)

    for key in params.keys:
        setattr(row, key, None)
        # The meta goes with it. A `language_meta` left behind would say a person
        # determined a language that is no longer there -- provenance for a fact
        # that does not exist is worse than none.
        if key != "line_progression":
            setattr(row, f"{key}_meta", None)
    db.save(row)

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id],
        # Ids and the field NAMES only -- a cleared value is not carried into the
        # audit chain, because the preimage already holds it and the chain cannot
        # be purged.
        before={"segment_id": row.id, "version": before_version, "cleared": list(params.keys)},
        after={"segment_id": row.id, "version": row.version},
        emit_type="segment.updated",
        segment_ids=[row.id],
        pass_ids=[row.pass_id],
        document_ids=[row.document_id],
    )
    return {"segment_id": row.id, "version": row.version, "cleared": list(params.keys)}, spec


class SegmentRestoreVersionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    version: int
    expected_version: int


_invert_segment_restore_version = _invert_via_previous_version


def _copy_version_onto_row(row: Segment, target: "SegmentVersion") -> None:
    """Every field a `SegmentVersion` records, copied back onto the live row.

    ONE place for this, used by `segment.restore_version` and
    `segment.restore_versions` alike, because a field one of them restores and the
    other forgets makes undo quietly partial for exactly one of the two paths — the
    kind of divergence no test catches until somebody undoes a bulk edit and finds a
    line's script still changed.
    """
    row.anchor = target.anchor
    row.baseline = target.baseline
    row.kind = target.kind
    row.kind_raw = target.kind_raw
    row.parent_segment_id = target.parent_segment_id
    row.is_furniture = target.is_furniture
    row.mark_state = target.mark_state
    # Slice 9 (#4938): restored with everything else. A fact the update can set
    # and the restore leaves behind would make undo quietly partial.
    row.language = target.language
    row.script = target.script
    row.direction = target.direction
    row.language_meta = target.language_meta
    row.script_meta = target.script_meta
    row.direction_meta = target.direction_meta
    row.line_progression = target.line_progression
    row.doc_kind = f"{row.document_id}:{row.kind}"
    bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
    row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile


#: What a restore can change that decides a page's DERIVED TEXT: which lines there are and
#: which count. The anchor, the baseline and the cascade facts do not.
_TEXT_FIELDS = ("parent_segment_id", "is_furniture", "kind", "pass_id")


def _restore_changes_text(row: Segment, target: SegmentVersion) -> bool:
    """Whether restoring `target` onto `row` can change the page's derived text (slice 12).

    The undo of a box MOVE is a `restore_version` that puts an anchor back. `segment.update`
    is already exempt from the page-text refresh when it changes only geometry, and its
    inverse was not: undoing one word's move on a 20,000-shape page re-derived the whole page
    and took 14 s against a 100 ms budget. Read BEFORE the copy, from the two rows in hand.
    """
    return any(getattr(row, name) != getattr(target, name) for name in _TEXT_FIELDS)


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
    if row.version != params.expected_version and not _unchanged_since(
        db, params.segment_id, params.expected_version, row
    ):
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
    text_relevant = _restore_changes_text(row, target)
    snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
    _copy_version_onto_row(row, target)
    db.save(row)

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id],
        before={"segment_id": row.id, "version": before_version},
        after={"segment_id": row.id, "version": row.version, "text_relevant": text_relevant},
        emit_type="segment.updated",
        segment_ids=[row.id],
        pass_ids=[row.pass_id],
        document_ids=[row.document_id],
    )
    return {"segment_id": row.id, "version": row.version}, spec


# ---------------------------------------------------------------------------
# Slice 13 (#4941) -- one edit across a selection is ONE action and ONE undo
# ---------------------------------------------------------------------------
#
# `segment.update` takes one segment. The editor's attribute verbs act on a SELECTION
# (`source.editor.set-kind`, `set-direction`, `set-language-script`), so before this a
# selection-wide edit was one audited action per line — and one undo step per line:
# ⌘Z after "set these five lines to heading" reverted one line at a time. Grouping the
# requests on the client would have made the undo story lie, so the fix is here.
#
# Two actions, each the other's inverse, mirroring `segment.update` /
# `segment.restore_version` exactly: an inverse reads ONLY `after` (#4923's rule), and
# every row restores to `after.version - 1` because `snapshot_segment_version` writes
# exactly one preimage and bumps exactly once.


class SegmentAttributeUpdate(BaseModel):
    """One row's part of a selection-wide edit.

    ATTRIBUTES ONLY — kind, furniture and the cascade's facts. Not a shape and not a
    parent: moving five lines' boxes at once is not a selection verb anyone has
    specified, and a bulk path for shapes would be a second place to get anchors,
    bboxes and tiles right.
    """

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    expected_version: int
    kind: Optional[str] = None
    is_furniture: Optional[bool] = None
    #: With `is_furniture` true: why a RULE left the line out ("too small"), kept on the line (`designer.clean.leaves-out-non-text`).
    left_out_reason: Optional[str] = Field(default=None, max_length=60)
    language: Optional[str] = None
    script: Optional[str] = None
    direction: Optional[str] = None


class SegmentUpdateManyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updates: list[SegmentAttributeUpdate] = Field(min_length=1, description='One change per segment, each with its id and version.')


class SegmentReparentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    expected_version: int


class SegmentReparentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[SegmentReparentItem] = Field(min_length=1, description='The segments to move, each with the version the caller saw.')
    parent_segment_id: Optional[str] = Field(default=None, description='The segment they now sit inside (a line into a region); none lifts them out to the page.')


class SegmentVersionRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    version: int
    expected_version: int


class SegmentRestoreVersionsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restores: list[SegmentVersionRestore] = Field(min_length=1)
    #: `segment-editor.reassign-by-drag`: the order entries `segment.reparent` moved, written back as they were
    #: (by id) in this same action. None leaves every entry alone, as `segment.update_many`'s undo needs.
    order_entries: Optional[list[SegmentOrderEntryParams]] = None


def _live_current_row(
    db: Database, segment_id: str, expected_version: int, *, restoring: bool = False
) -> Segment:
    """The row, refused unless it is real, live and at the version the caller saw.

    The same four refusals as the single-row actions, in the same order, so a bulk
    edit cannot be a way around any of them. `restoring` (the undo path only) also takes a row
    whose number moved while its content is what the caller saw (`_unchanged_since`).
    """
    _assert_not_provisional_http(segment_id, what="segment_id")
    row = db.get(Segment, segment_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    if row.deleted_at is not None:
        raise _as_http_error(SegmentDeleted(segment_id))
    if row.version != expected_version and not (restoring and _unchanged_since(db, segment_id, expected_version, row)):
        raise _as_http_error(SegmentStale(
            segment_id, expected_version, row.version,
            _stale_changed_fields(db, segment_id, expected_version, row),
        ))
    return row


def _mark_furniture(row: Any, value: bool, why: str | None = None) -> None:
    """`is_furniture`, and the marks that say who decided it: a rule's reason when it left the line out, and
    `kept_by_person` when a person brings a left-out line back, so the Leave Out stage never takes it out again
    (`designer.clean.leaves-out-non-text`, ## 1108)."""
    meta = dict(row.metadata or {})
    if value and not row.is_furniture and why:
        meta["left_out"] = {"why": why}
        meta.pop("kept_by_person", None)
    elif not value and row.is_furniture:
        meta.pop("left_out", None)
        meta["kept_by_person"] = True
    row.metadata = meta
    row.is_furniture = value


def _refuse_repeated_ids(ids: list[str]) -> None:
    """One row named twice would be snapshotted twice under one audit id, and the
    second compare-and-set would fail against the first's bump — a refusal of the
    caller's own request that reads like somebody else edited the line."""
    seen: set[str] = set()
    for segment_id in ids:
        if segment_id in seen:
            raise HTTPException(
                status_code=422,
                detail=f"segment {segment_id!r} is named twice in one bulk edit",
            )
        seen.add(segment_id)


def _invert_many_via_previous_version(before, after, ctx: ActionContext):
    """The shared inverse of both bulk actions, reading ONLY `after`.

    Every row restores to `after.version - 1`, for the reason the single-row inverse
    gives: one snapshot, one bump, always."""
    if not after:
        return None
    versions = after.get("versions") or []
    restores = [
        {"segment_id": item["segment_id"], "version": item["version"] - 1,
         "expected_version": item["version"]}
        for item in versions
        if item.get("segment_id") and item.get("version")
    ]
    if not restores:
        return None
    if after.get("order_entries") is not None:
        return ("segment.restore_versions", {"restores": restores, "order_entries": after["order_entries"]})
    return ("segment.restore_versions", {"restores": restores})


def _reposition_entries(db: Database, rows: list[Segment]) -> list[dict[str, Any]]:
    """Every order entry of `rows` moved to where page order puts it under the row's current parent
    (`segment-editor.reassign-by-drag`); answers the entries as they were, for the undo."""
    from fichero_server.api.routes.document.reading_orders import ENTRY_FIELDS, reposition_in_page_order
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    was: list[dict[str, Any]] = []
    for row in rows:
        for entry in db.query(ReadingOrderEntry, segment_id=row.id):
            order = db.get(ReadingOrder, entry.order_id)
            if order is None or order.deleted_at is not None:
                continue
            was.append({field: getattr(entry, field) for field in ENTRY_FIELDS})
            reposition_in_page_order(db, order, entry, row)
    return was


def _put_entries_back(db: Database, entries: list[SegmentOrderEntryParams]) -> list[dict[str, Any]]:
    """The entries written back as recorded (by id); answers them as they were just before, for a redo.
    An entry deleted since is written back whole."""
    from fichero_server.api.routes.document.reading_orders import ENTRY_FIELDS, restore_segment_entries
    from fichero_server.models.reading_orders import ReadingOrderEntry

    was: list[dict[str, Any]] = []
    for item in entries:
        entry = db.get(ReadingOrderEntry, item.id)
        if entry is None:
            restore_segment_entries(db, [item.model_dump()])
            continue
        was.append({field: getattr(entry, field) for field in ENTRY_FIELDS})
        entry.parent_entry_id, entry.position = item.parent_entry_id, item.position
        db.save(entry)
    return was


@action(
    "segment.update_many",
    SegmentUpdateManyParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_segment_update_many(db: Database, params: SegmentUpdateManyParams, ctx: ActionContext):
    """One attribute edit across a selection: ONE audit row, ONE undo step.

    ALL OR NOTHING. Every row is checked — real, live, at the caller's version — before
    any is written, so a stale line refuses the whole edit instead of leaving half the
    selection changed. That is the same rule `segment.delete` applies to its own list,
    and the same reason: half an edit is worse than none, because nothing on screen
    tells the person which half happened.
    """
    _refuse_repeated_ids([item.segment_id for item in params.updates])
    rows = [
        (_live_current_row(db, item.segment_id, item.expected_version), item)
        for item in params.updates
    ]

    audit_id = uuid.uuid4().hex
    before_versions: list[dict[str, Any]] = []
    after_versions: list[dict[str, Any]] = []
    for row, item in rows:
        before_versions.append({"segment_id": row.id, "version": row.version})
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        if item.kind is not None:
            row.kind = item.kind
            row.doc_kind = f"{row.document_id}:{row.kind}"
        if item.is_furniture is not None:
            _mark_furniture(row, item.is_furniture, item.left_out_reason)
        # The cascade's facts through the SAME writer `segment.update` uses, so a
        # script is validated and a fact's provenance is recorded identically on both
        # paths — two writers for one fact would be two answers about who set it.
        _apply_cascade_facts(db, row, item, ctx)
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row, _item in rows],
        before={"versions": before_versions},
        after={"versions": after_versions},
        emit_type="segment.updated",
        segment_ids=[row.id for row, _item in rows],
        pass_ids=sorted({row.pass_id for row, _item in rows}),
        document_ids=sorted({row.document_id for row, _item in rows}),
    )
    return {"versions": after_versions}, spec


@action(
    "segment.reparent",
    SegmentReparentParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_segment_reparent(db: Database, params: SegmentReparentParams, ctx: ActionContext):
    """Move segments under another segment (a line into a region): ONE audit row, ONE undo step.

    ALL OR NOTHING, like `segment.update_many`. The new parent must be live and in the same pass
    and document as every moved segment, must not be one of them, and must not sit inside one of
    them (a cycle). Each moved segment's entry, in every order that holds it, moves among the new
    parent's children by page position (`segment-editor.reassign-by-drag`); the undo puts them back.
    """
    _refuse_repeated_ids([item.segment_id for item in params.segments])
    rows = [_live_current_row(db, item.segment_id, item.expected_version) for item in params.segments]
    moved_ids = {row.id for row in rows}

    new_parent = None
    if params.parent_segment_id is not None:
        _assert_not_provisional_http(params.parent_segment_id, what="parent_segment_id")
        new_parent = db.get(Segment, params.parent_segment_id)
        if new_parent is None:
            raise HTTPException(status_code=404, detail=f"Segment not found: {params.parent_segment_id}")
        reason = segment_liveness_reason(db, new_parent.id)
        if reason is not None:
            raise _as_http_error(SegmentNotLive(new_parent.id, reason))
        for row in rows:
            if row.pass_id != new_parent.pass_id or row.document_id != new_parent.document_id:
                raise _as_http_error(SegmentParentMismatchError(
                    f"parent segment {new_parent.id!r} is not in pass {row.pass_id!r} of document {row.document_id!r}"
                ))
        # A segment may not move into itself or into anything it holds: walk up from the new parent.
        cursor, hops = new_parent, 0
        while cursor is not None and hops < 64:
            if cursor.id in moved_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"segment {cursor.id!r} cannot be moved into itself or something it holds",
                )
            cursor = db.get(Segment, cursor.parent_segment_id) if cursor.parent_segment_id else None
            hops += 1

    audit_id = uuid.uuid4().hex
    before_versions: list[dict[str, Any]] = []
    after_versions: list[dict[str, Any]] = []
    for row in rows:
        before_versions.append({"segment_id": row.id, "version": row.version})
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        row.parent_segment_id = params.parent_segment_id
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})
    order_entries = _reposition_entries(db, rows)

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row in rows],
        before={"versions": before_versions},
        after={"versions": after_versions, "order_entries": order_entries},
        emit_type="segment.updated",
        segment_ids=[row.id for row in rows],
        pass_ids=sorted({row.pass_id for row in rows}),
        document_ids=sorted({row.document_id for row in rows}),
    )
    return {"versions": after_versions}, spec


class SegmentTranslateParams(BaseModel):
    """`segment-editor.group-drag`, `segment-editor.nudge`: the selection moved by one offset."""

    model_config = ConfigDict(extra="forbid")

    segments: list[SegmentReparentItem] = Field(min_length=1, description="The segments to move, each with the version the caller saw.")
    dx: float = Field(description="How far across, in fractions of the page.")
    dy: float = Field(description="How far down, in fractions of the page.")


def _anchor_points(row: Segment) -> list[list[float]]:
    """Every point a segment is drawn by: its rect's corners, outline, shapes and baseline."""
    anchor = row.anchor
    points: list[list[float]] = list(row.baseline or [])
    if anchor is not None:
        if anchor.rect:
            x, y, w, h = anchor.rect
            points += [[x, y], [x + w, y + h]]
        points += list(anchor.polygon or [])
        for shape in anchor.shapes or []:
            points += list(shape.points or [])
    return points


@action(
    "segment.translate",
    SegmentTranslateParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_segment_translate(db: Database, params: SegmentTranslateParams, ctx: ActionContext):
    """Move every named segment by ONE offset (`segment-editor.group-drag`): its rect, outline, shapes and baseline
    together, one action, one undo. All or nothing, like `segment.update_many`. The offset is held so the whole group
    stays on the page, which keeps its shape (one offset for all, never one per segment)."""
    _refuse_repeated_ids([item.segment_id for item in params.segments])
    rows = [_live_current_row(db, item.segment_id, item.expected_version) for item in params.segments]
    elsewhere = [row.id for row in rows if row.anchor is not None and row.anchor.rendition_id]
    if elsewhere:
        raise HTTPException(status_code=422, detail=f"segments measured on another image cannot be moved here: {elsewhere}")
    points = [point for row in rows for point in _anchor_points(row)]
    dx, dy = params.dx, params.dy
    if points:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        dx = min(max(dx, -min(xs)), 1.0 - max(xs))
        dy = min(max(dy, -min(ys)), 1.0 - max(ys))

    def moved(pts):
        return [[p[0] + dx, p[1] + dy, *p[2:]] for p in pts] if pts else pts

    audit_id = uuid.uuid4().hex
    before_versions, after_versions = [], []
    for row in rows:
        before_versions.append({"segment_id": row.id, "version": row.version})
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        anchor = row.anchor
        if anchor is not None:
            update: dict[str, Any] = {"polygon": moved(anchor.polygon)}
            if anchor.rect:
                update["rect"] = [anchor.rect[0] + dx, anchor.rect[1] + dy, *anchor.rect[2:]]
            if anchor.shapes:
                update["shapes"] = [shape.model_copy(update={"points": moved(shape.points)}) for shape in anchor.shapes]
            row.anchor = anchor.model_copy(update=update)
            row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_and_tile_from_anchor(row.anchor)
        row.baseline = moved(row.baseline)
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row in rows],
        before={"versions": before_versions},
        after={"versions": after_versions},
        emit_type="segment.updated",
        segment_ids=[row.id for row in rows],
        pass_ids=sorted({row.pass_id for row in rows}),
        document_ids=sorted({row.document_id for row in rows}),
    )
    return {"versions": after_versions, "dx": dx, "dy": dy}, spec


@action(
    "segment.restore_versions",
    SegmentRestoreVersionsParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
    # REDO GOES THROUGH THIS ROW'S OWN INVERSE, and the reason is structural rather than
    # a preference. The generic redo replays the original forward action with its
    # `expected_version`s freshened by `_refresh_replay_expected_versions` — which is
    # convention-keyed on a TOP-LEVEL `expected_version` or an `expected_versions` map.
    # A bulk edit's versions live one level down, inside `updates[]`, so the freshener
    # cannot see them and a replay compares against versions the undo already bumped:
    # refused as stale with no other writer in sight (found by
    # `test_redo_reapplies_every_line`, which failed before this line). The own-invert
    # path reads only this row's `after`, which is always current, so it cannot go stale.
    redo_via_own_invert=True,
)
def _action_segment_restore_versions(
    db: Database, params: SegmentRestoreVersionsParams, ctx: ActionContext
):
    """The inverse of `segment.update_many`, and its own inverse's target: restore many
    rows to named versions in ONE audited step. All or nothing, like the edit it undoes.
    """
    _refuse_repeated_ids([item.segment_id for item in params.restores])
    pairs = []
    for item in params.restores:
        row = _live_current_row(db, item.segment_id, item.expected_version, restoring=True)
        candidates = db.query(SegmentVersion, segment_id=item.segment_id, version=item.version)
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"segment {item.segment_id!r} has no version {item.version}",
            )
        pairs.append((row, candidates[0]))

    audit_id = uuid.uuid4().hex
    before_versions: list[dict[str, Any]] = []
    after_versions: list[dict[str, Any]] = []
    text_relevant = any(_restore_changes_text(row, target) for row, target in pairs)
    for row, target in pairs:
        before_versions.append({"segment_id": row.id, "version": row.version})
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        _copy_version_onto_row(row, target)
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})
    entries_were = None if params.order_entries is None else _put_entries_back(db, params.order_entries)
    # Entries put back move lines in `as-written`, which the page's text follows.
    text_relevant = text_relevant or bool(params.order_entries)

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row, _target in pairs],
        before={"versions": before_versions},
        after={"versions": after_versions, "text_relevant": text_relevant,
               **({"order_entries": entries_were} if entries_were is not None else {})},
        emit_type="segment.updated",
        segment_ids=[row.id for row, _target in pairs],
        pass_ids=sorted({row.pass_id for row, _target in pairs}),
        document_ids=sorted({row.document_id for row, _target in pairs}),
    )
    return {"versions": after_versions}, spec


@router.patch("")
async def update_segments_many(
    params: SegmentUpdateManyParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    """`PATCH /api/segments` — one attribute edit across a selection, as one audited
    action and one undo step. Answers the new versions AND the audit id, so the app can
    offer ⌘Z for the whole edit without guessing which row to invert.

    PATCH on the collection, not `POST /update-many`: a partial modification of some of
    the collection's members is what PATCH means, and `check_rest_conventions` requires
    an `update_*` operation to be PUT or PATCH. The body carries `expected_version`s, and
    PATCH — unlike DELETE — carries a body reliably, which is the invariant that matters.
    """
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    try:
        result = registry.invoke(db, "segment.update_many", params.model_dump(mode="json"), ctx)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return {**result.result, "audit_id": result.audit_id}


# ---------------------------------------------------------------------------
# Slice 4 (#4922) -- matches, forwarding notes, a citable reference
# ---------------------------------------------------------------------------


class SegmentMatchProposeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_segment_id: str = Field(description='One end of the match.')
    to_segment_id: str = Field(description='The other end of the match.')
    certainty: Optional[float] = Field(default=None, description='How sure the proposer is, 0 to 1.')
    #: Capped (#4923 review): this is recorded inside the tamper-evident
    #: audit chain, where nothing can ever be purged -- an operator's short
    #: note about the match, never a quote from a source. Whether even a
    #: short typed field belongs in the chain at all is the maintainer's
    #: open question (morning file, question 17/23), not settled here.
    note: Optional[str] = Field(default=None, max_length=200, description='A short note about the match (kept in the audit log).')


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

    segment_ids: list[str] = Field(description='The segments to merge.')
    keep_id: str = Field(description='The segment that survives the merge.')
    #: Compare-and-set, one entry per id in `segment_ids` (#4957 follow-up
    #: 1: "a redo is refused when something else changed the segment since"
    #: -- previously merge took no token at all, so a redo silently merged
    #: away a member someone had just reshaped). Checked against every
    #: participant's CURRENT `Segment.version` before anything is written,
    #: `keep_id` included even though merge itself never bumps it -- a
    #: concurrent edit to the kept segment is still something that changed
    #: since the caller last read it.
    expected_versions: dict[str, int] = Field(description="Each segment's version as last read, {segment_id: version}; a changed segment is refused.")
    #: `segment-editor.merge-lines`: the kept line takes the members' joined outline (their union,
    #: bridged across a gap) and their baselines end to end, and the readings join, all in the page's
    #: reading order. Off, the kept row keeps its own shape, as the region-edit combine needs.
    join_geometry: bool = Field(False, description="Join the outlines and baselines onto the kept segment, in reading order.")
    #: `segment-editor.merge-lines`, owner 2026-11-13: members in other regions are moved into the kept
    #: segment's region and merged in the same action. Off, a merge across regions is refused, as the
    #: Reader's backspace join needs (`source.textedit.backspace-joins-in-reading-order`).
    move_into_region: bool = Field(False, description="Move members in other regions into the kept segment's region rather than refusing.")


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
            "order_entries": after.get("order_entries", []),
            "moved_children": after.get("moved_children", {}),
            "moved_children_parents": after.get("moved_children_parents", {}),
            "child_order_entries": after.get("child_order_entries", []),
            # The kept row's shape before a joined-geometry merge, restored from its snapshot.
            **({"keep_restore": {
                "segment_id": after["kept_id"], "version": after["kept_version"],
                "expected_version": current_versions[after["kept_id"]],
            }} if after.get("kept_version") is not None else {}),
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

    # `source.textedit.backspace-joins-in-reading-order`: "refused with the
    # reason across regions" -- two segments can share a pass/document and
    # still belong to different regions (different `parent_segment_id`,
    # including one set and one unset), and merging across that boundary
    # would silently splice two unrelated passages into one segment.
    for row in rows.values():
        if row.parent_segment_id != first.parent_segment_id and not params.move_into_region:
            raise _as_http_error(
                SegmentRegionMismatchError(
                    "segments being merged are not all in the same region"
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
    # `segment-editor.merge-lines`: with the geometry joined, everything joins in the PAGE's reading
    # order (the engine's, not the click order), and the readings with the script's separator.
    join_ids = list(params.segment_ids)
    separator = " "
    joined_shape = None
    if params.join_geometry:
        joined_shape = _joined_line_shape(db, rows, keep_row, readings_by_member)
        join_ids, separator = joined_shape["order"], joined_shape["separator"]

    # `segment-editor.merge-regions`: what the absorbed members held (a region's lines, a line's words) becomes the
    # kept one's, placed into its order by page position; read before anything is written.
    absorbed_set = set(absorbed_ids)
    children = (
        [row for row in db.query(Segment, pass_id=keep_row.pass_id)
         if row.deleted_at is None and row.parent_segment_id in absorbed_set]
        if params.join_geometry else []
    )

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
        # Moved into the kept line's region (`move_into_region`); the snapshot holds where it was.
        row.parent_segment_id = keep_row.parent_segment_id
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
            for segment_id in join_ids
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
                content=separator.join(pieces),
                ctx=ctx,
            )
        )

    # `segment-editor.merge-lines`: the kept line takes the joined shape, versioned like any reshape, so
    # its undo restores the snapshot written here.
    kept_version = None
    if joined_shape is not None:
        kept_version = keep_row.version
        snapshot_segment_version(db, keep_row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        keep_row.anchor = keep_row.anchor.model_copy(update={
            "polygon": joined_shape["outline"], "rect": joined_shape["rect"], "shapes": None,
        })
        keep_row.baseline = joined_shape["baseline"]
        bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(keep_row.anchor)
        keep_row.bbox_x, keep_row.bbox_y, keep_row.bbox_w, keep_row.bbox_h, keep_row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
        db.save(keep_row)
        after_versions[params.keep_id] = keep_row.version

    # The absorbed segments leave every reading order; unmerge writes the same rows back (2026-09-28).
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries

    order_entries = remove_segment_entries(db, absorbed_ids)
    moved_children, moved_children_parents, child_order_entries = _move_children_into(db, keep_row, children, ctx, audit_id)
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[params.keep_id, *absorbed_ids],
        before=None,
        after={
            "kept_id": params.keep_id, "forwarding_ids": forwarding_ids,
            "absorbed_versions": absorbed_versions,
            "order_entries": order_entries,
            # Slice 8 (#4934): the joined readings THIS merge added, so its
            # inverse retracts exactly those and nothing else.
            "representation_ids": merge_representation_ids,
            # #4957 follow-up 1: EVERY touched id's version as this call
            # left it -- `_refresh_replay_expected_versions` reads this to
            # freshen a replayed merge's `expected_versions` on redo, and
            # `_invert_merge` reads it to give `unmerge` a live token.
            "versions": after_versions,
            # The members' children moved to the kept segment, their parents before, and their order entries.
            "moved_children": moved_children,
            "moved_children_parents": moved_children_parents,
            "child_order_entries": child_order_entries,
            # The kept row's version before its shape was joined; None when it kept its own.
            "kept_version": kept_version,
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
            **({"version": keep_row.version, "order": join_ids} if joined_shape is not None else {}),
        },
        spec,
    )


def _joined_line_shape(
    db: Database, rows: dict[str, Segment], keep_row: Segment, readings: dict[str, dict[str, tuple[str, str]]]
) -> dict[str, Any]:
    """`segment-editor.merge-lines`: the members' order on the page, their joined outline and baseline,
    and the reading separator -- refused, before anything is written, when the shapes cannot be joined."""
    from fichero_server.api.routes.document.segment_readings import (
        _direction_of,
        _lines_are_vertical,
        direction_rungs,
    )
    from fichero_server.media import line_join

    frames = {(row.anchor.rendition_id, row.anchor.space) for row in rows.values() if row.anchor is not None}
    if len(frames) > 1:
        raise HTTPException(status_code=422, detail="the segments are drawn on different images, so their shapes cannot be joined")
    outlines = {sid: line_join.outline_of(row.anchor) for sid, row in rows.items()}
    shapeless = [sid for sid, outline in outlines.items() if outline is None]
    if shapeless:
        raise HTTPException(status_code=422, detail=f"segments with no shape cannot be joined: {shapeless}")
    document = db.get(Document, keep_row.document_id)
    shapes = [row for row in db.query(Segment, pass_id=keep_row.pass_id) if row.deleted_at is None]
    counted = readings.get(keep_row.id) or {}
    _rid, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
    direction, _level = _direction_of(
        keep_row, document, text, _lines_are_vertical(shapes, document), direction_rungs(db, document)
    )
    ids = list(rows)
    order = [ids[i] for i in line_join.join_order([outlines[sid] for sid in ids], direction)]
    outline = line_join.joined_outline([outlines[sid] for sid in order], direction)
    x0, y0, x1, y1 = line_join.bounds(outline)
    return {
        "order": order,
        "outline": outline,
        "rect": [x0, y0, x1 - x0, y1 - y0],
        "baseline": line_join.joined_baseline([rows[sid].baseline for sid in order], direction),
        "separator": line_join.reading_separator(keep_row.script),
    }


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
    #: The absorbed segments' order entries the merge took out, written back where they were. Only
    #: entries OF segments being restored are accepted.
    order_entries: list[SegmentOrderEntryParams] = Field(default_factory=list)
    #: `segment-editor.merge-lines`: the kept segment's shape before a joined-geometry merge, as
    #: `segment.restore_version`'s own three numbers, restored in this same action.
    keep_restore: Optional[SegmentRestoreVersionParams] = None
    #: `segment-editor.merge-regions`: the children the merge moved to the kept segment, {id: version as the merge
    #: left it}, the parent each had, and their order entries before; all put back.
    moved_children: dict[str, int] = {}
    moved_children_parents: dict[str, Optional[str]] = {}
    child_order_entries: list[SegmentOrderEntryParams] = Field(default_factory=list)


def _move_children_into(
    db: Database, keep_row: Segment, children: list[Segment], ctx: ActionContext, audit_id: str,
) -> tuple[dict[str, int], dict[str, Optional[str]], list[dict]]:
    """The absorbed members' children made the kept segment's, under `audit_id`, and placed in every order that held
    them by page position among the kept segment's own (`segment-editor.merge-regions`). Answers their versions, their
    parents before, and the order entries they had, for the undo."""
    if not children:
        return {}, {}, []
    from fichero_server.api.routes.document.reading_orders import place_in_page_order, remove_segment_entries
    from fichero_server.models.reading_orders import ReadingOrder

    entries = remove_segment_entries(db, [child.id for child in children])
    parents: dict[str, Optional[str]] = {}
    versions: dict[str, int] = {}
    for child in children:
        parents[child.id] = child.parent_segment_id
        snapshot_segment_version(db, child, deleted=False, actor=ctx.actor, audit_id=audit_id)
        child.parent_segment_id = keep_row.id
        db.save(child)
        versions[child.id] = child.version
    for order_id in dict.fromkeys(entry["order_id"] for entry in entries):
        order = db.get(ReadingOrder, order_id)
        if order is None or order.deleted_at is not None:
            continue
        for child in children:
            if any(entry["order_id"] == order_id and entry["segment_id"] == child.id for entry in entries):
                place_in_page_order(db, order, child)
    return versions, parents, entries


@action("segment.unmerge", SegmentUnmergeParams, domains=["segment"], undoable=False)
def _action_unmerge(db: Database, params: SegmentUnmergeParams, ctx: ActionContext):
    strangers = [entry.segment_id for entry in params.order_entries if entry.segment_id not in params.versions]
    if strangers:
        raise HTTPException(status_code=422, detail=f"order_entries name segments not being restored: {strangers}")
    keep_target = None
    if params.keep_restore is not None:
        keep_row = db.get(Segment, params.keep_restore.segment_id)
        if not keep_row:
            raise HTTPException(status_code=404, detail=f"Segment not found: {params.keep_restore.segment_id}")
        if keep_row.version != params.keep_restore.expected_version:
            raise _as_http_error(SegmentStale(
                keep_row.id, params.keep_restore.expected_version, keep_row.version,
                _stale_changed_fields(db, keep_row.id, params.keep_restore.expected_version, keep_row),
            ))
        found = db.query(SegmentVersion, segment_id=keep_row.id, version=params.keep_restore.version)
        if not found:
            raise HTTPException(status_code=404, detail=f"segment {keep_row.id!r} has no version {params.keep_restore.version}")
        keep_target = (keep_row, found[0])
    moved_rows: list[Segment] = []
    for child_id, expected in params.moved_children.items():
        child = db.get(Segment, child_id)
        if child is None or child.deleted_at is not None:
            raise _as_http_error(SegmentPartGone(child_id))
        if child.version != expected:
            raise _as_http_error(SegmentStale(
                child_id, expected, child.version, _stale_changed_fields(db, child_id, expected, child),
            ))
        moved_rows.append(child)
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
        row.mark_state = target.mark_state
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
    if keep_target is not None:
        keep_row, target = keep_target
        snapshot_segment_version(db, keep_row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        _copy_version_onto_row(keep_row, target)
        db.save(keep_row)
        restored_ids.append(keep_row.id)
        after_versions[keep_row.id] = keep_row.version
    from fichero_server.api.routes.document.reading_orders import restore_segment_entries

    restore_segment_entries(db, [entry.model_dump() for entry in params.order_entries])
    if moved_rows:
        from fichero_server.api.routes.document.reading_orders import remove_segment_entries

        remove_segment_entries(db, [child.id for child in moved_rows])
        for child in moved_rows:
            snapshot_segment_version(db, child, deleted=False, actor=ctx.actor, audit_id=audit_id)
            child.parent_segment_id = params.moved_children_parents.get(child.id)
            db.save(child)
        restore_segment_entries(db, [entry.model_dump() for entry in params.child_order_entries])
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


# --- redraw an outline from its baseline (segment-editor) -----------------


class SegmentRegenerateOutlineParams(BaseModel):
    """`segment-editor.regenerate-polygon-from-baseline`: Redraw Outline from Baseline (⌘⇧R)."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description="The lines whose outlines are drawn again from their baselines.")
    expected_versions: dict[str, int] = Field(description="Each segment's version as last read, {segment_id: version}; a changed segment is refused.")
    fixed_height: Optional[float] = Field(
        default=None, gt=0,
        description="A band this many image pixels tall over the baseline, for a line with no ink to measure.",
    )


def _page_image_for_lines(db: Database, document: Document):
    """The current page image as a PIL image, and the maps from the stored fractions (of the upright
    photograph) to its pixels and back."""
    from PIL import Image

    from fichero_server.media.current_image import ORIGINAL, current_page_image
    from fichero_server.media.upright import FRAME_UPRIGHT, open_in_frame

    found = current_page_image(db, document)
    if found is None:
        raise HTTPException(status_code=422, detail="the page has no image to draw outlines on")
    found = found.for_geometry()
    image = open_in_frame(found.path, FRAME_UPRIGHT) if found.kind == ORIGINAL else Image.open(found.path)
    width, height = image.size
    to_image = found.to_image

    def forward(points):
        carried = to_image.carry(points) if to_image is not None else points
        return [[x * width, y * height] for x, y in carried]

    def back(points):
        fractions = [[x / width, y / height] for x, y in points]
        return to_image.inverse().carry(fractions) if to_image is not None else fractions

    return image, forward, back


@action(
    "segment.regenerate_outline",
    SegmentRegenerateOutlineParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_regenerate_outline(db: Database, params: SegmentRegenerateOutlineParams, ctx: ActionContext):
    """Each line's outline drawn again from its baseline and the current page image, the page's other
    baselines as bounds so outlines do not overlap; one action, one undo. All or nothing: a line with no
    baseline, or one no outline could be drawn for, refuses the whole call and says which."""
    from fichero_server.media import outline_from_baseline

    if not params.segment_ids:
        raise HTTPException(status_code=422, detail="segment_ids is empty: nothing to redraw")
    _refuse_repeated_ids(params.segment_ids)
    rows: list[Segment] = []
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
        rows.append(_live_current_row(db, segment_id, _require_expected_version(params.expected_versions, segment_id)))
    if len({(row.document_id, row.pass_id) for row in rows}) > 1:
        raise _as_http_error(SegmentPassMismatchError("the lines being redrawn are not all in the same pass and document"))
    # `segment-editor.edge.no-baseline`: said, never guessed around; Add Baseline is the way on.
    no_baseline = [row.id for row in rows if not row.baseline or len(row.baseline) < 2]
    if no_baseline:
        raise HTTPException(status_code=422, detail=f"lines with no baseline cannot be redrawn from one: {no_baseline}")
    elsewhere = [row.id for row in rows if row.anchor is not None and row.anchor.rendition_id]
    if elsewhere:
        raise HTTPException(status_code=422, detail=f"lines measured on another image cannot be redrawn on this one: {elsewhere}")

    document = db.get(Document, rows[0].document_id)
    image, forward, back = _page_image_for_lines(db, document)
    chosen = {row.id for row in rows}
    neighbours = [
        row.baseline for row in db.query(Segment, pass_id=rows[0].pass_id)
        if row.deleted_at is None and row.id not in chosen and row.baseline and len(row.baseline) >= 2
    ]
    fixed = params.fixed_height
    drawn = outline_from_baseline.outlines(
        image, [forward(row.baseline) for row in rows], [forward(line) for line in neighbours], fixed,
    )
    undrawn = [row.id for row, outline in zip(rows, drawn) if outline is None]
    if undrawn:
        raise HTTPException(
            status_code=422,
            detail=f"no outline could be drawn for {undrawn}: no ink was found along the baseline; give a fixed height",
        )

    audit_id = uuid.uuid4().hex
    before_versions, after_versions = [], []
    for row, outline in zip(rows, drawn):
        polygon = [[round(x, 6), round(y, 6)] for x, y in back(outline)]
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        before_versions.append({"segment_id": row.id, "version": row.version})
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        row.anchor = row.anchor.model_copy(update={
            "polygon": polygon, "rect": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)], "shapes": None,
        })
        bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
        row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row in rows],
        before={"versions": before_versions},
        after={"versions": after_versions},
        emit_type="segment.updated",
        segment_ids=[row.id for row in rows],
        pass_ids=[rows[0].pass_id],
        document_ids=[rows[0].document_id],
    )
    return {"segment_ids": [row.id for row in rows], "versions": after_versions}, spec


class SegmentSimplifyParams(BaseModel):
    """`segment-editor.vertices`: Simplify (⌥⌘S): fewer points on each outline and baseline."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description="The segments whose outlines and baselines are simplified.")
    expected_versions: dict[str, int] = Field(description="Each segment's version as last read, {segment_id: version}; a changed segment is refused.")
    tolerance: float = Field(gt=0, description="How far, in image pixels, the simpler shape may stray from the one drawn.")


@action(
    "segment.simplify",
    SegmentSimplifyParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_simplify(db: Database, params: SegmentSimplifyParams, ctx: ActionContext):
    """Douglas-Peucker on each segment's outline (closed) and baseline (open), in the page image's pixels, so the
    tolerance means the same on every page; one action, one undo. A segment already as simple as the tolerance allows
    is left as it is and not bumped. An outline is never brought below three points, a baseline below two."""
    if not params.segment_ids:
        raise HTTPException(status_code=422, detail="segment_ids is empty: nothing to simplify")
    _refuse_repeated_ids(params.segment_ids)
    rows: list[Segment] = []
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
        rows.append(_live_current_row(db, segment_id, _require_expected_version(params.expected_versions, segment_id)))

    audit_id = uuid.uuid4().hex
    after_versions, simplified_ids = [], []
    for row, polygon, baseline in _simplified_shapes(db, rows, params.tolerance):
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        if polygon is not None:
            xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
            row.anchor = row.anchor.model_copy(update={
                "polygon": polygon, "rect": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
            })
            bbox_x, bbox_y, bbox_w, bbox_h, tile = bbox_and_tile_from_anchor(row.anchor)
            row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h, row.tile = bbox_x, bbox_y, bbox_w, bbox_h, tile
        if baseline is not None:
            row.baseline = baseline
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})
        simplified_ids.append(row.id)
    if not simplified_ids:
        raise HTTPException(status_code=422, detail="the shapes are already as simple as that tolerance allows")

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=simplified_ids,
        before=None,
        after={"versions": after_versions},
        emit_type="segment.updated",
        segment_ids=simplified_ids,
        pass_ids=[rows[0].pass_id],
        document_ids=[rows[0].document_id],
    )
    return {"segment_ids": simplified_ids, "versions": after_versions}, spec


def _simplified_shapes(
    db: Database, rows: list[Segment], tolerance: float,
) -> list[tuple[Segment, list[list[float]] | None, list[list[float]] | None]]:
    """What Simplify makes of each row: (row, outline or None, baseline or None), None where the tolerance changes
    nothing; rows it changes not at all are left out. The ONE computation `segment.simplify` writes and its preview
    shows (`segment-editor.vertices`). Writes nothing."""
    from fichero_server.media import line_join

    if len({(row.document_id, row.pass_id) for row in rows}) > 1:
        raise _as_http_error(SegmentPassMismatchError("the segments being simplified are not all in the same pass and document"))
    elsewhere = [row.id for row in rows if row.anchor is not None and row.anchor.rendition_id]
    if elsewhere:
        raise HTTPException(status_code=422, detail=f"segments measured on another image cannot be simplified here: {elsewhere}")

    document = db.get(Document, rows[0].document_id)
    _image, forward, back = _page_image_for_lines(db, document)

    def fewer(points: list[list[float]], closed: bool, least: int) -> list[list[float]] | None:
        return _fewer_points(points, closed, least, tolerance, forward, back)

    shapes = []
    for row in rows:
        polygon = fewer(row.anchor.polygon, True, 3) if row.anchor is not None and row.anchor.polygon else None
        baseline = fewer(row.baseline, False, 2) if row.baseline and len(row.baseline) > 2 else None
        if polygon is None and baseline is None:
            continue
        if polygon is not None:
            polygon, _crossed = line_join.simple_outline(polygon)  # dropping points can make an outline cross itself
        shapes.append((row, polygon, baseline))
    return shapes


class SegmentCutWordsParams(BaseModel):
    """`segment-editor.cut-words-from-positions`: Cut Words on lines."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description="The lines to cut into words.")
    expected_versions: dict[str, int] = Field(description="Each line's version as last read, {segment_id: version}; a changed line is refused.")


#: The cut sources a machine's cut can have; a word with another (a person's, an import's) is never replaced.
MACHINE_CUT_SOURCES = ("ctc", "ink-gap")


def _invert_cut_words(before, after, ctx: ActionContext):
    """Reads ONLY `after`: the words this cut made go, the machine's words it replaced come back."""
    if not after or not (after.get("made") or after.get("replaced")):
        return None
    return ("segment.uncut_words", {
        "made": after.get("made", {}), "replaced": after.get("replaced", []),
        "order_entries": after.get("order_entries", []),
    })


@action(
    "segment.cut_words",
    SegmentCutWordsParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_cut_words,
    # A redo mints new word ids, so its undo is derived from its own `after`, not the first undo's params.
    redo_via_own_invert=True,
)
def _action_cut_words(db: Database, params: SegmentCutWordsParams, ctx: ActionContext):
    """Each line's counting reading split at its spaces into `word` children (`segment-editor.cut-words-from-positions`):
    the cut between two words midway between where one ends and the next starts, from the recogniser's character
    positions (`cut_source: ctc`) or, without them, from the gaps in the ink (`cut_source: ink-gap`, low confidence,
    `segment-editor.cut-fallback-ink-gaps`); the line's outline cut across the baseline there. Each word records its
    source, confidence, the reading it was cut from and its stretch of it (`segment-editor.cut-records-source-and-
    confidence`). A machine's earlier words on the line are replaced; a person's are kept and not cut again. A line
    that cannot be cut is left alone and named. One action, one undo."""
    import numpy as np

    from fichero_server.api.routes.document.segment_readings import (
        _direction_of,
        _lines_are_vertical,
        direction_rungs,
    )
    from fichero_server.media import line_cut, line_join

    if not params.segment_ids:
        raise HTTPException(status_code=422, detail="segment_ids is empty: nothing to cut into words")
    _refuse_repeated_ids(params.segment_ids)
    rows: list[Segment] = []
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
        rows.append(_live_current_row(db, segment_id, _require_expected_version(params.expected_versions, segment_id)))
    if len({(row.document_id, row.pass_id) for row in rows}) > 1:
        raise _as_http_error(SegmentPassMismatchError("the lines being cut are not all in the same pass and document"))
    document = db.get(Document, rows[0].document_id)
    shapes = [row for row in db.query(Segment, pass_id=rows[0].pass_id) if row.deleted_at is None]
    vertical, rungs = _lines_are_vertical(shapes, document), direction_rungs(db, document)
    page = None  # the page image, opened only for a line that needs the ink

    plans, left_alone = [], []
    for row in rows:
        counted = _counting_readings(db, row.id)
        source_id, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
        if not text.strip():
            left_alone.append({"segment_id": row.id, "reason": "no-reading"})
            continue
        if not row.baseline or len(row.baseline) < 2:
            left_alone.append({"segment_id": row.id, "reason": "no-baseline"})
            continue
        outline = line_join.outline_of(row.anchor)
        if outline is None or (row.anchor is not None and row.anchor.rendition_id):
            left_alone.append({"segment_id": row.id, "reason": "no-outline" if outline is None else "another-image"})
            continue
        direction, _level = _direction_of(row, document, text, vertical, rungs)
        baseline = line_cut.reading_baseline(row.baseline, direction)
        spans = line_cut.word_spans(text)
        reading = db.get(ContentRepresentation, source_id) if source_id else None
        positions = reading.char_positions if reading is not None else None
        if positions is not None and len(positions) == len(text) and direction != "rtl":
            confidences = reading.char_confidences if reading.char_confidences and len(reading.char_confidences) == len(text) else None
            cuts, source = line_cut.cuts_from_positions(spans, positions, confidences), "ctc"
        else:
            if page is None:
                try:
                    image, forward, _back = _page_image_for_lines(db, document)
                    page = (np.asarray(image.convert("L")), forward)
                except HTTPException:
                    page = (None, None)
            gray, forward = page
            found = (line_cut.cuts_from_ink_gaps(gray, forward(outline), forward(baseline), len(spans) - 1)
                     if gray is not None else None)
            if found is None:
                left_alone.append({"segment_id": row.id, "reason": "no-positions-and-no-ink-gaps"})
                continue
            cuts, source = found, "ink-gap"
        fractions = [at for at, _sure in cuts]
        if any(b <= a for a, b in zip(fractions, fractions[1:])) or any(not 0 < at < 1 for at in fractions):
            left_alone.append({"segment_id": row.id, "reason": "cuts-out-of-order"})
            continue
        pieces = line_cut.baseline_pieces(baseline, fractions)
        x0, y0, x1, y1 = line_join.bounds(outline)
        reach = max(x1 - x0, y1 - y0)
        polygons = line_cut.cut_outline_along(outline, pieces, [line_cut.across(baseline, at, reach) for at in fractions])
        if polygons is None:
            left_alone.append({"segment_id": row.id, "reason": "outline-not-cut"})
            continue
        sureness = line_cut.word_sureness([sure for _at, sure in cuts], len(spans))
        plans.append((row, source_id, source, list(zip(spans, polygons, pieces, sureness))))
    if not plans:
        raise HTTPException(status_code=422, detail={"message": "no line could be cut into words", "left_alone": left_alone})

    audit_id = uuid.uuid4().hex
    now = utc_now()
    made: dict[str, int] = {}
    replaced: list[str] = []
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries

    replaced_entries: list[dict] = []
    for row, source_id, source, words in plans:
        children = [child for child in shapes if child.parent_segment_id == row.id and child.kind == "word"]
        machine = [child for child in children if (child.metadata or {}).get("cut_source") in MACHINE_CUT_SOURCES]
        kept = [child for child in children if child not in machine]
        for child in machine:
            snapshot_segment_version(db, child, deleted=True, actor=ctx.actor, audit_id=audit_id, reason="cut words again")
            child.deleted_at, child.deleted_by = now, ctx.actor
            db.save(child)
            replaced.append(child.id)
        replaced_entries.extend(remove_segment_entries(db, [child.id for child in machine]))
        kept_bounds = [line_join.bounds(o) for o in (line_join.outline_of(child.anchor) for child in kept) if o]
        for (start, end), polygon, piece, sure in words:
            wx0, wy0, wx1, wy1 = line_join.bounds(polygon)
            centre = ((wx0 + wx1) / 2, (wy0 + wy1) / 2)
            if any(bx0 <= centre[0] <= bx1 and by0 <= centre[1] <= by1 for bx0, by0, bx1, by1 in kept_bounds):
                continue  # a person's word is here already: matched by overlap, never duplicated
            word = _create_segment_impl(db, SegmentCreateParams(
                document_id=row.document_id, pass_id=row.pass_id, kind="word", parent_segment_id=row.id,
                anchor=row.anchor.model_copy(update={
                    "polygon": polygon, "rect": [wx0, wy0, wx1 - wx0, wy1 - wy0], "shapes": None, "granularity": "word",
                }),
                baseline=piece,
            ), ctx)
            word.metadata = {**(word.metadata or {}), "cut_source": source, "cut_confidence": sure,
                             "cut_from_representation_id": source_id, "reading_span": [start, end]}
            db.save(word)
            made[word.id] = word.version

    touched = [*made, *replaced]
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=touched,
        before=None,
        after={"made": made, "replaced": replaced, "order_entries": replaced_entries},
        emit_type="segment.created",
        segment_ids=touched,
        pass_ids=[rows[0].pass_id],
        document_ids=[rows[0].document_id],
    )
    return {"segment_ids": list(made), "replaced": replaced, "left_alone": left_alone}, spec


class SegmentCutCharactersParams(BaseModel):
    """`segment-editor.cut-characters`: Cut Characters on words."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description="The words to cut into characters.")
    expected_versions: dict[str, int] = Field(description="Each word's version as last read, {segment_id: version}; a changed word is refused.")


@action(
    "segment.cut_characters",
    SegmentCutCharactersParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_cut_words,
    redo_via_own_invert=True,
)
def _action_cut_characters(db: Database, params: SegmentCutCharactersParams, ctx: ActionContext):
    """Each word cut into `character` children (`segment-editor.cut-characters`), as Cut Words does a line: from the
    recogniser's character positions on its line's reading, between each two characters where the second starts, the
    word's outline cut across its line's baseline there. Each character records its source (`ctc`), the confidence at
    its cuts, the reading and its stretch of it. A word whose line has no positions (its words were cut from the ink),
    a right-to-left word or a single character is left alone and named. A machine's earlier characters are replaced, a
    person's kept. One action, one undo (`segment.uncut_words`)."""
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries
    from fichero_server.media import line_cut, line_join

    if not params.segment_ids:
        raise HTTPException(status_code=422, detail="segment_ids is empty: nothing to cut into characters")
    _refuse_repeated_ids(params.segment_ids)
    words = [
        _live_current_row(db, segment_id, _require_expected_version(params.expected_versions, segment_id))
        for segment_id in params.segment_ids
    ]
    plans, left_alone = [], []
    for word in words:
        meta = word.metadata or {}
        span, source_id = meta.get("reading_span"), meta.get("cut_from_representation_id")
        line = db.get(Segment, word.parent_segment_id) if word.parent_segment_id else None
        reading = db.get(ContentRepresentation, source_id) if source_id else None
        outline = line_join.outline_of(word.anchor)
        positions = reading.char_positions if reading is not None else None
        if not span or line is None or reading is None or positions is None or len(positions) != len(reading.content):
            left_alone.append({"segment_id": word.id, "reason": "no-positions"})
            continue
        if outline is None or not line.baseline or len(line.baseline) < 2 or not word.baseline:
            left_alone.append({"segment_id": word.id, "reason": "no-outline-or-baseline"})
            continue
        start, end = span
        if end - start < 2:
            left_alone.append({"segment_id": word.id, "reason": "one-character"})
            continue
        if (meta.get("direction") or line.direction) == "rtl" or positions[end - 1] < positions[start]:
            left_alone.append({"segment_id": word.id, "reason": "right-to-left"})
            continue
        x0, y0, x1, y1 = line_join.bounds(outline)
        reach = max(x1 - x0, y1 - y0) * 4
        strokes = [line_cut.across(line.baseline, positions[i], reach) for i in range(start + 1, end)]
        fractions = [hit for stroke in strokes for hit in line_cut.crossings(word.baseline, stroke)[:1]]
        if len(fractions) != len(strokes) or any(b <= a for a, b in zip(fractions, fractions[1:])):
            left_alone.append({"segment_id": word.id, "reason": "cuts-outside-the-word"})
            continue
        pieces = line_cut.baseline_pieces(word.baseline, fractions)
        polygons = line_cut.cut_outline_along(outline, pieces, strokes)
        if polygons is None:
            left_alone.append({"segment_id": word.id, "reason": "outline-not-cut"})
            continue
        confidences = reading.char_confidences if reading.char_confidences and len(reading.char_confidences) == len(reading.content) else None
        plans.append((word, source_id, [
            ((i, i + 1), polygon, piece, min(confidences[max(i - 1, start):i + 2]) if confidences else None)
            for i, polygon, piece in zip(range(start, end), polygons, pieces)
        ]))
    if not plans:
        raise HTTPException(status_code=422, detail={"message": "no word could be cut into characters", "left_alone": left_alone})

    audit_id = uuid.uuid4().hex
    now = utc_now()
    made: dict[str, int] = {}
    replaced: list[str] = []
    replaced_entries: list[dict] = []
    for word, source_id, characters in plans:
        children = [
            row for row in db.query(Segment, parent_segment_id=word.id)
            if row.deleted_at is None and row.kind == "character"
        ]
        machine = [child for child in children if (child.metadata or {}).get("cut_source") in MACHINE_CUT_SOURCES]
        if len(machine) < len(children):
            left_alone.append({"segment_id": word.id, "reason": "a-person-cut-it"})
            continue
        for child in machine:
            snapshot_segment_version(db, child, deleted=True, actor=ctx.actor, audit_id=audit_id, reason="cut characters again")
            child.deleted_at, child.deleted_by = now, ctx.actor
            db.save(child)
            replaced.append(child.id)
        replaced_entries.extend(remove_segment_entries(db, [child.id for child in machine]))
        for (begin, stop), polygon, piece, sure in characters:
            cx0, cy0, cx1, cy1 = line_join.bounds(polygon)
            character = _create_segment_impl(db, SegmentCreateParams(
                document_id=word.document_id, pass_id=word.pass_id, kind="character", parent_segment_id=word.id,
                anchor=word.anchor.model_copy(update={
                    "polygon": polygon, "rect": [cx0, cy0, cx1 - cx0, cy1 - cy0], "shapes": None,
                    "granularity": "character",
                }),
                baseline=piece,
            ), ctx)
            character.metadata = {**(character.metadata or {}), "cut_source": "ctc", "cut_confidence": sure,
                                  "cut_from_representation_id": source_id, "reading_span": [begin, stop]}
            db.save(character)
            made[character.id] = character.version
    if not made:
        raise HTTPException(status_code=422, detail={"message": "no word could be cut into characters", "left_alone": left_alone})

    touched = [*made, *replaced]
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=touched,
        before=None,
        after={"made": made, "replaced": replaced, "order_entries": replaced_entries},
        emit_type="segment.created",
        segment_ids=touched,
        pass_ids=sorted({word.pass_id for word in words}),
        document_ids=sorted({word.document_id for word in words}),
    )
    return {"segment_ids": list(made), "replaced": replaced, "left_alone": left_alone}, spec


class SegmentUncutWordsParams(BaseModel):
    """Internal: `segment.cut_words`' inverse only."""

    model_config = ConfigDict(extra="forbid")

    #: The words the cut made, {id: version as it left them}.
    made: dict[str, int] = {}
    #: The machine's words it replaced, brought back with their order entries.
    replaced: list[str] = []
    order_entries: list[SegmentOrderEntryParams] = Field(default_factory=list)


@action("segment.uncut_words", SegmentUncutWordsParams, domains=["segment"], undoable=False)
def _action_uncut_words(db: Database, params: SegmentUncutWordsParams, ctx: ActionContext):
    """The words a Cut Words made go (soft-deleted, each with its note), and the ones it replaced come back where they
    were. Every made word is checked first: one somebody has since changed refuses the undo."""
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries, restore_segment_entries

    made_rows = []
    for word_id, expected in params.made.items():
        word = db.get(Segment, word_id)
        if word is None or word.deleted_at is not None:
            raise _as_http_error(SegmentPartGone(word_id))
        if word.version != expected:
            raise _as_http_error(SegmentStale(word_id, expected, word.version, _stale_changed_fields(db, word_id, expected, word)))
        made_rows.append(word)
    audit_id = uuid.uuid4().hex
    now = utc_now()
    for word in made_rows:
        snapshot_segment_version(db, word, deleted=True, actor=ctx.actor, audit_id=audit_id, reason="uncut words")
        word.deleted_at, word.deleted_by = now, ctx.actor
        db.save(word)
        db.save(SegmentForwarding(
            document_id=word.document_id, old_segment_id=word.id, kind="deleted", new_segment_ids=[],
            actor=ctx.actor, audit_id=audit_id, sequence=db.next_forwarding_sequence(),
        ))
    remove_segment_entries(db, [word.id for word in made_rows])
    restored = []
    for word_id in params.replaced:
        word = db.get(Segment, word_id)
        if word is None or word.deleted_at is None:
            continue
        snapshot_segment_version(db, word, deleted=True, actor=ctx.actor, audit_id=audit_id)
        word.deleted_at, word.deleted_by = None, None
        db.save(word)
        restored.append(word)
    restore_segment_entries(db, [entry.model_dump() for entry in params.order_entries])
    rows = made_rows + restored
    touched = [word.id for word in rows]
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=touched,
        before=None,
        after={"segment_ids": touched},
        emit_type="segment.deleted",
        segment_ids=touched,
        pass_ids=sorted({word.pass_id for word in rows}),
        document_ids=sorted({word.document_id for word in rows}),
    )
    return {"segment_ids": touched}, spec


class SegmentAddBaselineParams(BaseModel):
    """`segment-editor.edge.no-baseline`: Add Baseline on lines that have none."""

    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(description="The lines to give a proposed baseline.")
    expected_versions: dict[str, int] = Field(description="Each line's version as last read, {segment_id: version}; a changed line is refused.")


def proposed_baseline(rect: list[float], direction: str | None) -> list[list[float]]:
    """A baseline through a box in its line's direction, for a person to drag onto the ink: a quarter of the way up
    from the bottom of a horizontal line (where letters stand), down the middle of a vertical one."""
    x, y, w, h = rect
    if direction in ("ttb", "btt"):
        top, bottom = [x + w / 2, y], [x + w / 2, y + h]
        return [top, bottom] if direction == "ttb" else [bottom, top]
    standing = y + h * 0.75
    left, right = [x, standing], [x + w, standing]
    return [right, left] if direction == "rtl" else [left, right]


@action(
    "segment.add_baseline",
    SegmentAddBaselineParams,
    domains=["segment"],
    undoable=True,
    invert=_invert_many_via_previous_version,
)
def _action_add_baseline(db: Database, params: SegmentAddBaselineParams, ctx: ActionContext):
    """Each named line with no baseline gets one proposed through its box in its direction, marked
    `baseline: estimated`; a line that has one is left as it is. One action, one undo."""
    from fichero_server.api.routes.document.segment_readings import (
        _direction_of,
        _lines_are_vertical,
        direction_rungs,
    )

    if not params.segment_ids:
        raise HTTPException(status_code=422, detail="segment_ids is empty: no line to give a baseline")
    _refuse_repeated_ids(params.segment_ids)
    rows = []
    for segment_id in params.segment_ids:
        _assert_not_provisional_http(segment_id, what="segment_id")
        rows.append(_live_current_row(db, segment_id, _require_expected_version(params.expected_versions, segment_id)))
    if len({(row.document_id, row.pass_id) for row in rows}) > 1:
        raise _as_http_error(SegmentPassMismatchError("the lines are not all in the same pass and document"))
    wanting = [row for row in rows if (not row.baseline or len(row.baseline) < 2) and row.anchor is not None and row.anchor.rect]
    if not wanting:
        raise HTTPException(status_code=422, detail="every line named has a baseline already, or no box to draw one in")
    document = db.get(Document, rows[0].document_id)
    shapes = [row for row in db.query(Segment, pass_id=rows[0].pass_id) if row.deleted_at is None]
    vertical, rungs = _lines_are_vertical(shapes, document), direction_rungs(db, document)

    audit_id = uuid.uuid4().hex
    after_versions = []
    for row in wanting:
        counted = _counting_readings(db, row.id)
        _rid, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
        direction, _level = _direction_of(row, document, text, vertical, rungs)
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        row.baseline = [[round(x, 6), round(y, 6)] for x, y in proposed_baseline(list(row.anchor.rect), direction)]
        row.metadata = {**(row.metadata or {}), "baseline": "estimated"}
        db.save(row)
        after_versions.append({"segment_id": row.id, "version": row.version})

    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[row.id for row in wanting],
        before=None,
        after={"versions": after_versions},
        emit_type="segment.updated",
        segment_ids=[row.id for row in wanting],
        pass_ids=[rows[0].pass_id],
        document_ids=[rows[0].document_id],
    )
    return {"segment_ids": [row.id for row in wanting], "versions": after_versions}, spec


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


def estimated_cut(rect: list[float], fraction: float, direction: str | None) -> list[list[float]]:
    """Two rects from one, cut at `fraction` of the text along the line's direction: the FIRST is
    the text before the cut. `rtl` text starts at the right edge, `ttb` at the top."""
    x, y, w, h = rect
    if direction == "ttb":
        return [[x, y, w, h * fraction], [x, y + h * fraction, w, h * (1 - fraction)]]
    if direction == "rtl":
        return [[x + w * (1 - fraction), y, w * fraction, h], [x, y, w * (1 - fraction), h]]
    return [[x, y, w * fraction, h], [x + w * fraction, y, w * (1 - fraction), h]]


def _parts_cut_at(db: Database, original: Segment, offset: int) -> tuple[list["SegmentSplitPart"], bool]:
    """`at_offset` made into the two parts `segment.split` takes (#5154): reading spans at the
    character, boxes cut in proportion along the line's resolved direction. An estimate, because
    nothing records where a character sits on the image; `cut: estimated` says so on both rows."""
    from fichero_server.api.routes.document.segment_readings import (
        _direction_of,
        _lines_are_vertical,
        direction_rungs,
    )

    counted = _counting_readings(db, original.id)
    _rid, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
    if not 0 < offset < len(text):
        raise HTTPException(status_code=422, detail=f"at_offset {offset} is not inside the line's {len(text)} characters")
    anchor = original.anchor
    if anchor is None or not anchor.rect:
        raise HTTPException(status_code=422, detail="the line has no box to cut")
    document = db.get(Document, original.document_id)
    shapes = [row for row in db.query(Segment, pass_id=original.pass_id) if row.deleted_at is None]
    direction, _level = _direction_of(
        original, document, text, _lines_are_vertical(shapes, document), direction_rungs(db, document)
    )
    # `segment-editor.char-positions-kept`: where the recogniser placed the character, when it said; a right-to-left
    # line keeps the proportional cut, because its positions run along the baseline as drawn, not as read.
    positions = _reading_positions(db, _rid) if direction != "rtl" else None
    measured = positions is not None and len(positions) == len(text)
    fraction = positions[offset] if measured else offset / len(text)
    rects = estimated_cut(list(anchor.rect), fraction, direction)
    return [
        SegmentSplitPart(
            anchor=SourceAnchor(
                document_id=anchor.document_id, page_id=anchor.page_id,
                rendition_id=anchor.rendition_id, space=anchor.space, rect=rect,
                rotation=anchor.rotation, granularity=anchor.granularity,
            ),
            reading_span=span,
        )
        for rect, span in zip(rects, ([0, offset], [offset, len(text)]))
    ], measured


class SegmentSplitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: Optional[str] = Field(default=None, description='The segment to split (not with cut_path).')
    parts: list[SegmentSplitPart] = Field(default=[], description='The parts to split it into, each with its own anchor (or give at_offset).')
    #: Return in the Reader (#5154): split at this character of the line's counting reading,
    #: INSTEAD of giving `parts`. Nothing knows where a character sits on the image, so the box is
    #: cut in proportion (characters before / all characters) along the line's direction --
    #: left to right, right to left, or top to bottom -- and both parts are marked
    #: `metadata.cut = "estimated"`, for a person to reshape.
    at_offset: Optional[int] = Field(default=None, description="Split at this character of the line's reading instead of giving parts.")
    #: Compare-and-set on the segment being split (#4957 follow-up 1) --
    #: the new parts are brand-new rows with nothing to compare yet, so
    #: only the one EXISTING id needs a token, the same shape
    #: `segment.update` already takes.
    expected_version: Optional[int] = Field(
        default=None, description="The segment's version as last read; a changed segment is refused (not with cut_path)."
    )
    #: The Knife (`segment-editor.split-knife`): a stroke, points in the fractions of the page the lines are
    #: stored in, INSTEAD of `segment_id` and `parts`. Every line named in `expected_versions` whose baseline the
    #: stroke crosses is cut there, its outline along the stroke; a line it does not cross is left alone and
    #: named in the answer. One stroke over many lines is one action, one undo.
    cut_path: Optional[list[list[float]]] = Field(
        default=None, description="A knife stroke: split every named line whose baseline it crosses, at the crossings."
    )
    expected_versions: dict[str, int] = Field(
        default={}, description="With cut_path: the lines the stroke may cross, {segment_id: version as last read}."
    )


def _unsplit_params(split: dict) -> dict:
    """One split's record (`_split_one`) made into what `unsplit` takes to put it back."""
    new_segment_ids = split.get("new_segment_ids", [])
    current_versions = split["versions"]
    return {
        "segment_id": split["kept_id"], "version": split["pre_split_version"],
        "expected_version": current_versions.get(split["kept_id"]),
        "new_segment_ids": new_segment_ids,
        "expected_versions": {
            new_id: current_versions[new_id] for new_id in new_segment_ids if new_id in current_versions
        },
        "representation_ids": split.get("representation_ids", []),
        "moved_children": split.get("moved_children", {}),
    }


def _invert_split(before, after, ctx: ActionContext):
    """Reads ONLY `after` (#4923 second look) -- `pre_split_version` names
    the snapshot `segment.split` itself wrote for the kept id; `unsplit`
    restores FROM IT, never from geometry carried here. `after["versions"]`
    (#4957 follow-up 1) gives `unsplit` a live compare-and-set token for
    the kept id AND every new part, worked out from THIS call's own
    `after` -- always fresh, whichever lap it is."""
    if not after:
        return None
    if after.get("splits"):
        # A knife stroke: every line it cut goes back in one step.
        return ("segment.unsplit_many", {"splits": [_unsplit_params(split) for split in after["splits"]]})
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
    if params.cut_path is not None:
        return _knife_split(db, params, ctx)
    if params.segment_id is None or params.expected_version is None:
        raise HTTPException(status_code=422, detail="split needs segment_id and expected_version, or a cut_path")
    _assert_not_provisional_http(params.segment_id, what="segment_id")
    original = db.get(Segment, params.segment_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    estimated = params.at_offset is not None
    measured = False
    if estimated:
        if params.parts:
            raise HTTPException(status_code=422, detail="give parts or at_offset, not both")
        parts, measured = _parts_cut_at(db, original, params.at_offset)
        params = params.model_copy(update={"parts": parts})
        estimated = not measured
    if len(params.parts) < 2:
        raise HTTPException(status_code=422, detail="split needs two or more parts")
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
    split = _split_one(
        db, original, params.parts, estimated=estimated, readings_before_split=readings_before_split,
        ctx=ctx, audit_id=audit_id, measured=measured,
    )
    new_ids = split["new_segment_ids"]
    split_representation_ids = split["representation_ids"]
    pre_split_version = split["pre_split_version"]
    forwarding_id = split["forwarding_id"]

    change_spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=[params.segment_id, *new_ids],
        before=None,
        after={
            "kept_id": params.segment_id, "new_segment_ids": new_ids,
            "forwarding_id": forwarding_id, "pre_split_version": pre_split_version,
            # #4957 follow-up 1: every touched id's version as THIS call
            # left it -- the kept id (bumped) and every new part (starts
            # at 1) -- so `_invert_split`/`_refresh_replay_expected_versions`
            # always have a live token to hand `unsplit`.
            "versions": split["versions"],
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
            "forwarding_id": forwarding_id,
            "representation_ids": split_representation_ids,
        },
        change_spec,
    )


def _split_one(
    db: Database, original: Segment, parts: list[SegmentSplitPart], *, estimated: bool,
    readings_before_split: dict[str, tuple[str, str]], ctx: ActionContext, audit_id: str,
    children_by_part: list[list[Segment]] | None = None, measured: bool = False,
) -> dict:
    """One line split into `parts`, the first kept on the line's own id, under `audit_id`; the record its
    undo needs. Shared by a split at given parts and a knife stroke over many lines. `children_by_part`, one list
    per part, moves the line's words onto the part they fall in (`segment-editor.edge.knife-through-words`)."""
    pre_split_version = original.version
    # #4923: every action that changes a segment writes the version
    # snapshot (preimage) and bumps `Segment.version` -- named explicitly
    # for merge and split. `unsplit` restores FROM this exact snapshot
    # (segment_id, pre_split_version) -- the audit's own before/after
    # carries no geometry, only this version number.
    snapshot_segment_version(db, original, deleted=False, actor=ctx.actor, audit_id=audit_id)

    first_part, *rest_parts = parts
    # How the cut was placed: in proportion (`estimated`), or at the recogniser's own character position (`measured`).
    cut_mark = "estimated" if estimated else ("measured" if measured else None)
    if cut_mark:
        original.metadata = {**(original.metadata or {}), "cut": cut_mark}
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
        if cut_mark:
            row.metadata = {**row.metadata, "cut": cut_mark}
        new_rows.append(row)
        new_ids.append(row.id)
    if new_rows:
        db.save_many(new_rows)
        # The parts follow the line they were cut from in every order that holds it; unsplit takes them out.
        from fichero_server.api.routes.document.reading_orders import place_after

        place_after(db, original.id, new_ids)

    moved_children: dict[str, int] = {}
    for part_id, children in zip(new_ids, (children_by_part or [])[1:]):
        for child in children:
            snapshot_segment_version(db, child, deleted=False, actor=ctx.actor, audit_id=audit_id)
            child.parent_segment_id = part_id
            db.save(child)
            moved_children[child.id] = child.version

    # Slice 8 (#4934): each part that named a stretch gets its own reading,
    # derived from the one that counted. The kept part is `original.id`
    # and the new parts are `new_ids`, in the order the caller gave them.
    part_ids = [original.id, *new_ids]
    split_representation_ids: list[str] = []
    for part, part_id in zip(parts, part_ids):
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
        old_segment_id=original.id,
        kind="split",
        # The original id "stays on one part" -- included here so a caller
        # resolving the pre-split id sees every resulting id, including its
        # own (`resolve_segment`/`_forwarding_walk` treat a self-reference
        # as live, never as a hop).
        new_segment_ids=[original.id, *new_ids],
        actor=ctx.actor,
        audit_id=audit_id,
        sequence=db.next_forwarding_sequence(),
    )
    db.save(forwarding)
    return {
        "kept_id": original.id, "new_segment_ids": new_ids, "forwarding_id": forwarding.id,
        "pre_split_version": pre_split_version,
        "versions": {original.id: original.version, **{new_id: 1 for new_id in new_ids}},
        "representation_ids": split_representation_ids,
        "moved_children": moved_children,
    }


def _reading_positions(db: Database, representation_id: str | None) -> list[float] | None:
    """The recogniser's character positions on a reading, 0 to 1 along the line, when it gave them."""
    if representation_id is None:
        return None
    row = db.get(ContentRepresentation, representation_id)
    return row.char_positions if row is not None else None


def _knife_split(db: Database, params: SegmentSplitParams, ctx: ActionContext):
    """`segment-editor.split-knife`: every named line whose baseline the stroke crosses is split at each crossing,
    its outline cut along the stroke and each part given its stretch of baseline; the reading is cut at the
    character nearest the crossing when positions are known, else in proportion and marked `cut: estimated`.
    A line the stroke does not cross is left alone and named in the answer. All lines in one action, one undo."""
    from fichero_server.api.routes.document.segment_readings import (
        _direction_of,
        _lines_are_vertical,
        direction_rungs,
    )
    from fichero_server.media import line_cut, line_join

    if params.parts or params.at_offset is not None or params.segment_id is not None:
        raise HTTPException(status_code=422, detail="give a cut_path alone: not with segment_id, parts or at_offset")
    if len(params.cut_path) < 2 or any(len(point) < 2 for point in params.cut_path):
        raise HTTPException(status_code=422, detail="cut_path needs two or more [x, y] points")
    if not params.expected_versions:
        raise HTTPException(status_code=422, detail="expected_versions is empty: name the lines the stroke may cross")
    stroke = [[float(point[0]), float(point[1])] for point in params.cut_path]
    rows = []
    for segment_id, version in params.expected_versions.items():
        _assert_not_provisional_http(segment_id, what="segment_id")
        reason = segment_liveness_reason(db, segment_id)
        if reason is not None:
            raise _as_http_error(SegmentNotLive(segment_id, reason))
        rows.append(_live_current_row(db, segment_id, version))
    if len({(row.document_id, row.pass_id) for row in rows}) > 1:
        raise _as_http_error(SegmentPassMismatchError("the lines under the stroke are not all in the same pass and document"))

    document = db.get(Document, rows[0].document_id)
    shapes = [row for row in db.query(Segment, pass_id=rows[0].pass_id) if row.deleted_at is None]
    vertical, rungs = _lines_are_vertical(shapes, document), direction_rungs(db, document)
    planned: list[tuple[Segment, list[SegmentSplitPart], bool, dict, list[list[Segment]]]] = []
    left_alone: list[dict] = []
    for row in rows:
        if not row.baseline or len(row.baseline) < 2:
            # `segment-editor.edge.no-baseline`: said, never guessed around.
            left_alone.append({"segment_id": row.id, "reason": "no-baseline"})
            continue
        if row.anchor is None or row.anchor.rendition_id:
            left_alone.append({"segment_id": row.id, "reason": "another-image"})
            continue
        counted = _counting_readings(db, row.id)
        source_id, text = counted.get("transcription") or next(iter(counted.values()), (None, ""))
        direction, _level = _direction_of(row, document, text, vertical, rungs)
        baseline = line_cut.reading_baseline(row.baseline, direction)
        cuts = line_cut.crossings(baseline, stroke)
        if not cuts:
            left_alone.append({"segment_id": row.id, "reason": "grazed"})
            continue
        pieces = line_cut.baseline_pieces(baseline, cuts)
        polygons = line_cut.cut_outline(line_join.outline_of(row.anchor), pieces, stroke)
        if polygons is None:
            left_alone.append({"segment_id": row.id, "reason": "grazed"})
            continue
        offsets, estimated = line_cut.reading_offsets(cuts, len(text), _reading_positions(db, source_id))
        bounds = [0, *offsets, len(text)] if offsets else None
        parts = []
        for index, (polygon, piece) in enumerate(zip(polygons, pieces)):
            x0, y0, x1, y1 = line_join.bounds(polygon)
            parts.append(SegmentSplitPart(
                anchor=row.anchor.model_copy(update={
                    "polygon": polygon, "rect": [x0, y0, x1 - x0, y1 - y0], "shapes": None,
                }),
                baseline=piece,
                reading_span=[bounds[index], bounds[index + 1]] if bounds else None,
            ))
        # `segment-editor.edge.knife-through-words`: each word goes with the part its centre falls in.
        children_by_part: list[list[Segment]] = [[] for _ in polygons]
        for child in shapes:
            if child.parent_segment_id != row.id or child.id in params.expected_versions:
                continue
            child_outline = line_join.outline_of(child.anchor)
            if child_outline is None:
                children_by_part[0].append(child)
                continue
            x0, y0, x1, y1 = line_join.bounds(child_outline)
            children_by_part[line_cut.part_holding([(x0 + x1) / 2, (y0 + y1) / 2], polygons)].append(child)
        planned.append((
            row, parts, bool(text) and estimated and bounds is not None, counted if bounds else {}, children_by_part,
        ))
    if not planned:
        raise HTTPException(
            status_code=422,
            detail={"message": "the stroke crosses no named line's baseline", "left_alone": left_alone},
        )

    audit_id = uuid.uuid4().hex
    splits = [
        _split_one(
            db, row, parts, estimated=estimated, readings_before_split=readings, ctx=ctx, audit_id=audit_id,
            children_by_part=children,
        )
        for row, parts, estimated, readings, children in planned
    ]
    touched = [segment_id for split in splits for segment_id in (split["kept_id"], *split["new_segment_ids"])]
    change_spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=touched,
        before=None,
        after={
            "splits": splits,
            "versions": {key: value for split in splits for key, value in split["versions"].items()},
        },
        emit_type="segment.split",
        segment_ids=touched,
        pass_ids=[rows[0].pass_id],
        document_ids=[rows[0].document_id],
    )
    answer = {
        "splits": [
            {key: split[key] for key in ("kept_id", "new_segment_ids", "representation_ids", "moved_children")}
            for split in splits
        ],
        "left_alone": left_alone,
    }
    return answer, change_spec


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
    #: `segment-editor.edge.knife-through-words`: the words a knife moved onto a new part, {id: version as the
    #: split left it}; put back under the kept line before the parts go.
    moved_children: dict[str, int] = {}


@action("segment.unsplit", SegmentUnsplitParams, domains=["segment"], undoable=False)
def _action_unsplit(db: Database, params: SegmentUnsplitParams, ctx: ActionContext):
    checked = _unsplit_checked(db, params)
    audit_id = uuid.uuid4().hex
    row, deleted_ids = _unsplit_apply(db, params, *checked, ctx=ctx, audit_id=audit_id)
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


class SegmentUnsplitManyParams(BaseModel):
    """Internal: a knife stroke's inverse only -- one `unsplit` per line the stroke cut, in one step."""

    model_config = ConfigDict(extra="forbid")

    splits: list[SegmentUnsplitParams]


@action("segment.unsplit_many", SegmentUnsplitManyParams, domains=["segment"], undoable=False)
def _action_unsplit_many(db: Database, params: SegmentUnsplitManyParams, ctx: ActionContext):
    """Every line a knife stroke cut put back. All of them are checked before any is touched, so a part
    somebody has since edited refuses the whole undo rather than leaving half the stroke undone."""
    if not params.splits:
        raise HTTPException(status_code=422, detail="splits is empty: nothing to put back")
    checked = [_unsplit_checked(db, split) for split in params.splits]
    audit_id = uuid.uuid4().hex
    touched: list[str] = []
    versions: dict[str, int] = {}
    rows = []
    for split, found in zip(params.splits, checked):
        row, deleted_ids = _unsplit_apply(db, split, *found, ctx=ctx, audit_id=audit_id)
        touched.extend([split.segment_id, *deleted_ids])
        versions[split.segment_id] = row.version
        rows.append(row)
    spec = ChangeSpec(
        audit_id=audit_id,
        domains=["segment"],
        target_ids=touched,
        before=None,
        # `versions`, so a redo's replay of the stroke compares against the lines as this undo left them.
        after={"versions": versions},
        emit_type="segment.split",
        segment_ids=touched,
        pass_ids=sorted({row.pass_id for row in rows}),
        document_ids=sorted({row.document_id for row in rows}),
    )
    return {"segment_ids": list(versions)}, spec


def _unsplit_checked(db: Database, params: SegmentUnsplitParams) -> tuple[Segment, Any, dict[str, Segment]]:
    """Every refusal `unsplit` makes, before anything is written: the kept row, the version to restore it
    to, and the live parts to fold back."""
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
    for child_id, expected in params.moved_children.items():
        child = db.get(Segment, child_id)
        if child is None or child.deleted_at is not None:
            raise _as_http_error(SegmentPartGone(child_id))
        if child.version != expected:
            raise _as_http_error(SegmentStale(
                child_id, expected, child.version, _stale_changed_fields(db, child_id, expected, child),
            ))
    return row, target, live_new_rows


def _unsplit_apply(
    db: Database, params: SegmentUnsplitParams, row: Segment, target: Any, live_new_rows: dict[str, Segment],
    *, ctx: ActionContext, audit_id: str,
) -> tuple[Segment, list[str]]:
    """One split put back under `audit_id`: its readings retracted, its parts folded into the kept row."""
    now = utc_now()

    # Slice 8 (#4934): the readings the split ADDED stop counting again. Done
    # BEFORE the parts are soft-deleted only so the whole undo is one
    # transaction's worth of writes in one readable place; the order does not
    # matter, because a retraction touches the reading and nothing else.
    _retract_readings(db, params.representation_ids)
    # The words the knife moved go back under the kept line before their parts are deleted.
    for child_id in params.moved_children:
        child = db.get(Segment, child_id)
        snapshot_segment_version(db, child, deleted=False, actor=ctx.actor, audit_id=audit_id)
        child.parent_segment_id = params.segment_id
        db.save(child)

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
    # The parts leave every reading order with the parts (a redo of the split mints and places new ones).
    from fichero_server.api.routes.document.reading_orders import remove_segment_entries

    remove_segment_entries(db, deleted_ids)
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
    row.mark_state = target.mark_state
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
    return row, deleted_ids


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

    match_id: str = Field(description='The match to carry across.')
    kinds: list[str] = Field(description='What to carry: readings, annotations, ...')
    #: Compare-and-set on the matched segments (#4957 follow-up 1), keyed
    #: by `SegmentMatch.from_segment_id`/`.to_segment_id` -- carry itself
    #: never bumps either segment's version (it only copies readings/
    #: annotations across), but the caller's view of the match can still
    #: be stale if either end was reshaped since it was read.
    expected_versions: dict[str, int] = Field(description="Each matched segment's version as last read, {segment_id: version}.")


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


class PassGroundTruthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: True marks the pass ground truth; False unmarks it.
    ground_truth: bool = Field(description='True marks the pass ground truth; false unmarks it.')


class PassGroundTruthResponse(BaseModel):
    pass_id: str
    ground_truth: bool


@router.put("/passes/{pass_id}/ground-truth", response_model=PassGroundTruthResponse)
async def set_pass_ground_truth(
    pass_id: str,
    body: PassGroundTruthBody,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> PassGroundTruthResponse:
    """`PUT /api/segments/passes/{pass_id}/ground-truth` -- Mark as Ground Truth, or unmark (#5513).

    For corrected transcriptions imported without the mark: the bake-off and the evaluation count a
    marked pass's lines, and its readings are not labelled machine. Audited and undoable."""
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(
        db, "segment.pass_ground_truth", {"pass_id": pass_id, "ground_truth": body.ground_truth}, ctx,
    )
    return PassGroundTruthResponse(**result.result)


class PassOriginalResponse(BaseModel):
    """The file an imported pass was read from (#5149). `content_base64` is its bytes exactly as they
    arrived -- base64, so a file in any encoding comes back byte for byte; the app decodes it to show."""

    pass_id: str
    file_name: str | None = None
    import_format: str | None = None
    import_checksum: str | None = None
    media_type: str
    content_base64: str


@router.get("/passes/{pass_id}/original", response_model=PassOriginalResponse)
async def get_pass_original(
    pass_id: str,
    db: Database = Depends(get_library_database),
) -> PassOriginalResponse:
    """The file an imported pass was read from, byte for byte as it arrived (#5149): the Inspector's
    Making section offers it as "Show original". Read access to the pass's page is the check
    (`pass_id` resolves to its document). 404 for a pass not made from a kept file."""
    import base64
    from pathlib import Path

    row = db.get(SegmentPass, pass_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Pass not found: {pass_id}")
    if not row.import_original:
        raise HTTPException(status_code=404, detail=f"Pass {pass_id} was not made from a kept file")
    package = Path(db.path).parent.resolve()
    kept = (package / row.import_original).resolve()
    # Only ever a file under the package's own `files/`: the stored path is ours, but a path read
    # back from a row is still checked before a byte of it is served.
    if not kept.is_relative_to(package / "files") or not kept.is_file():
        raise HTTPException(status_code=404, detail=f"The original of pass {pass_id} is missing from the library")
    media_type = "application/xml" if kept.suffix.lower() in {".xml", ".html", ".hocr"} else "text/plain"
    return PassOriginalResponse(
        pass_id=row.id, file_name=row.import_file, import_format=row.import_format,
        import_checksum=row.import_checksum, media_type=media_type,
        content_base64=base64.b64encode(kept.read_bytes()).decode("ascii"),
    )


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


class SegmentMatchListResponse(BaseModel):
    """A page's segment matches (#5165), `{items, count}` -- never a bare array."""

    items: list[SegmentMatch]
    count: int


@router.get("/document/{doc_id}/matches", response_model=SegmentMatchListResponse)
async def list_document_matches(
    doc_id: str,
    state: Optional[str] = Query(None, description="proposed, accepted or rejected; all when omitted"),
    db: Database = Depends(get_library_database),
) -> SegmentMatchListResponse:
    """The matches recorded on one page (`source.segment.match-record`, #5165): what a person
    reviews -- accepts, rejects, or carries readings and marks across. Before this, a match could
    be proposed, accepted and rejected, and nothing could LIST them, so a proposal nobody had the
    id of could never be reviewed. Oldest first."""
    rows = [row for row in db.query(SegmentMatch, document_id=doc_id) if state is None or row.state == state]
    rows.sort(key=lambda row: (row.created_at, row.id))
    return SegmentMatchListResponse(items=rows, count=len(rows))


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


@router.post("/reparent")
async def reparent_segments(
    params: SegmentReparentParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    """`POST /api/segments/reparent` — move segments under another segment as one audited action and one undo step."""
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    try:
        result = registry.invoke(db, "segment.reparent", params.model_dump(mode="json"), ctx)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return {**result.result, "audit_id": result.audit_id}


@router.post("/regenerate-outline")
async def regenerate_outline(
    params: SegmentRegenerateOutlineParams,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
    x_fichero_origin_window: str | None = Header(default=None, alias="X-Fichero-Origin-Window"),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    ctx = _resolve_action_ctx(
        actor=actor, library_path=x_fichero_library_path,
        origin_window=x_fichero_origin_window, db=db,
    )
    result = registry.invoke(db, "segment.regenerate_outline", params.model_dump(mode="json"), ctx)
    return {**result.result, "audit_id": result.audit_id}


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

    version: int = Field(description='The earlier version to bring back.')
    expected_version: int = Field(description="The segment's current version as last read; a changed segment is refused.")


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
        [read] = _with_texts(db, [row], [segment_read_from_row(row)])
        return SegmentDetailResponse(segment=read, resolved_from_forwarding=False)

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
    [read] = _with_texts(db, [live_row], [segment_read_from_row(live_row)])
    return SegmentDetailResponse(
        segment=read,
        resolved_from_forwarding=(live_id != segment_id),
        trail=resolved.trail,
    )
