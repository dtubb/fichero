"""Source-model slice 8 (#4934, #4929, #4932) — the ONE read of a segment's
readings, answering from both stores.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8", sections "Where
readings actually live today" and "Routes".

THE PROBLEM, stated plainly because it decides the whole shape of this file.
`ContentRepresentation` is a well-made record for a reading, and until this
slice NOTHING IN THE ENGINE EVER CREATED ONE. Every transcription, translation
and cleaned text a workflow makes is an ``Artifact`` row. So a naive slice 8
would start writing readings into the representation table and leave the
engine with TWO stores of readings — the exact fault this programme exists to
remove.

So readings get what segments got in slices 1 and 6: **one read seam, then
writers move one at a time.** This module is that seam. It answers with real
``ContentRepresentation`` rows AND with *provisional readings* read out of
artifacts, and a caller cannot tell which it got. A provisional reading's id
is ``legacy-reading:<artifact_id>:<box_index>`` and is refused on every write
(``assert_not_provisional``), because it names a run's output, not a record
somebody can correct in place.

**Nothing copies artifact text into readings, ever, in bulk.** A person
correcting a provisional reading writes ONE real reading naming the artifact
it came from (``derived_from_artifact_id``). Workflow tools move to writing
readings tool by tool, in later slices, each in its own commit, and an
artifact stays the record of a *run's output*.

Its own module, with the same ``/segments`` prefix as `segments.py` and
`segment_pictures.py`, so it reads as one resource to every client — the
pattern slice 7 set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import Artifact, ContentRepresentation
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.readings import (
    ChoiceNeedsAPerson,
    CountingAnswer,
    PassAnswer,
    PassBasis,
    PassCandidate,
    ReadingAnchorMismatch,
    ReadingCandidate,
    ReadingChoice,
    UnknownReadingKind,
    legacy_reading_segment_id,
    project_record_rule,
    reading_kinds,
    resolve_counting,
    resolve_working_pass,
)
from fichero_server.models.segments import (
    LEGACY_ID_PREFIX,
    ProvisionalSegmentIdError,
    Segment,
    SegmentPass,
    SegmentPassChoice,
    derive_pass_provenance_kind,
    primary_live_segment_id,
    resolve_segment,
)

router = APIRouter(prefix="/segments")


class ReadingRead(BaseModel):
    """One reading, read either from the representation table or from an
    artifact. The caller cannot tell which — `source.one-store`."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    #: True when this reading still lives in an ``Artifact`` row. Its id is
    #: refused on every write path.
    provisional: bool
    document_id: str
    segment_id: str | None = None
    kind: str
    content: str
    language: str | None = None
    script: str | None = None
    level: str | None = None
    #: Who made it — engine-set for a real row, derived from the artifact's
    #: provider and model for a provisional one. Never a trusting default.
    provenance_kind: ProvenanceKind
    #: WHICH person or agent (`source.reading.author-and-guideline`). For a
    #: provisional reading it is the artifact's provider: the run's own name is
    #: the only author that text has.
    created_by: str | None = None
    machine_confidence: float | None = None
    char_confidences: list[float] | None = None
    char_positions: list[float] | None = None
    read_from_rendition_id: str | None = None
    guideline: str | None = None
    corrects_representation_id: str | None = None
    derived_from_representation_id: str | None = None
    #: The artifact a provisional reading was read out of, or that a real
    #: reading corrects.
    derived_from_artifact_id: str | None = None
    pair_id: str | None = None
    pair_role: str | None = None
    #: Withdrawn (`representation.retract`). The row stays; it stops counting.
    retracted: bool = False
    source_anchor: SourceAnchor | None = None
    created_at: datetime


class ReadingListResponse(BaseModel):
    """A segment's readings AND which one counts, in one answer.

    The counting answer rides on the list DELIBERATELY: a client that had to
    make a second call for it would render the list first, and the first frame
    a person sees would show a machine's guess with no label on it.
    """

    items: list[ReadingRead]
    count: int
    #: Per kind, because "which translation counts" and "which transcription
    #: counts" are separate questions (`source.reading.chosen-is-worked-out`).
    counting: dict[str, CountingAnswer]


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProvisionalSegmentIdError):
        return HTTPException(422, str(exc))
    if isinstance(exc, (UnknownReadingKind, ReadingAnchorMismatch)):
        return HTTPException(422, str(exc))
    if isinstance(exc, ChoiceNeedsAPerson):
        return HTTPException(403, str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(500, str(exc))


def _artifact_and_box(db: Database, segment_id: str) -> tuple[Artifact | None, int | None]:
    """The artifact a segment's words still live in, and this segment's box in
    it — or ``(None, None)`` when there is no such block.

    Two shapes, one answer:

    * a PROVISIONAL segment id (``legacy:<artifact_id>:<n>``) names the
      artifact and the position outright;
    * a REAL row belongs to a pass, the pass names the artifact it was
      converted from, and the row recorded its own position at conversion
      (``metadata["box_index"]``). A row made from scratch recorded none, and
      correctly has no provisional reading.
    """
    if segment_id.startswith(LEGACY_ID_PREFIX):
        body = segment_id[len(LEGACY_ID_PREFIX) :]
        artifact_id, _, tail = body.rpartition(":")
        if not artifact_id or not tail.isdigit():
            return None, None
        return db.get(Artifact, artifact_id), int(tail)

    row = db.get(Segment, segment_id)
    if row is None:
        return None, None
    box_index = row.metadata.get("box_index")
    if not isinstance(box_index, int) or isinstance(box_index, bool):
        return None, None
    pass_row = db.get(SegmentPass, row.pass_id)
    if pass_row is None or not pass_row.source_artifact_id:
        return None, None
    return db.get(Artifact, pass_row.source_artifact_id), box_index


def provisional_readings(
    db: Database, segment_id: str, *, allowed_kinds: list[str] | None = None
) -> list[ReadingRead]:
    """This segment's readings that still live in an artifact.

    Offered ONLY when the artifact's own type is a reading kind this library
    knows: ``entities``, ``grouping`` and ``segmentation`` artifacts are
    outputs of a run, not readings of a line, and offering them as readings
    would be a lie about what they are.

    The text is the artifact's ``content`` sliced by the box's character span
    when the box carries one (#4309 keeps that link explicit), and the box's
    own ``text`` otherwise. Both come from the KEPT block, never from the live
    projection: the character spans index the artifact's own ``content``
    string, so reading them off an edited projection would slice the wrong
    text. raw-geometry-ok — this is the record of what the machine produced,
    which is exactly what a provisional reading reports.
    """
    artifact, box_index = _artifact_and_box(db, segment_id)
    if artifact is None or box_index is None:
        return []
    kinds = allowed_kinds if allowed_kinds is not None else reading_kinds(db)
    if artifact.artifact_type not in kinds:
        return []
    block = artifact.ocr_geometry  # raw-geometry-ok: see the docstring
    if block is None or not (0 <= box_index < len(block.boxes)):
        return []
    box = block.boxes[box_index]

    text: str | None = None
    if (
        box.char_start is not None
        and box.char_end is not None
        and artifact.content
        and box.char_end > box.char_start
    ):
        text = artifact.content[box.char_start : box.char_end]
    if not text:
        text = box.text or None
    if not text:
        return []

    return [
        ReadingRead(
            id=legacy_reading_segment_id(artifact.id, box_index),
            provisional=True,
            document_id=artifact.document_id,
            segment_id=segment_id,
            kind=artifact.artifact_type,
            content=text,
            provenance_kind=derive_pass_provenance_kind(
                provider=box.provider or artifact.provider,
                model=box.model or artifact.model,
            ),
            created_by=box.provider or artifact.provider,
            machine_confidence=box.confidence,
            derived_from_artifact_id=artifact.id,
            created_at=artifact.created_at,
        )
    ]


def _reading_read_from_row(row: ContentRepresentation) -> ReadingRead:
    return ReadingRead(
        id=row.id,
        provisional=False,
        document_id=row.document_id,
        segment_id=row.segment_id,
        kind=row.kind,
        content=row.content,
        language=row.language,
        script=row.script,
        level=row.level,
        # A row written before this slice has no recorded maker, and saying
        # `unknown` is the truth about it -- never `human`, which is the
        # defect #4868/#4869 exist to stop.
        provenance_kind=row.provenance_kind or ProvenanceKind.unknown,
        created_by=row.created_by,
        machine_confidence=row.machine_confidence,
        char_confidences=row.char_confidences,
        char_positions=row.char_positions,
        read_from_rendition_id=row.read_from_rendition_id,
        guideline=row.guideline,
        corrects_representation_id=row.corrects_representation_id,
        derived_from_representation_id=row.derived_from_representation_id,
        derived_from_artifact_id=row.derived_from_artifact_id,
        pair_id=row.pair_id,
        pair_role=row.pair_role,
        retracted=row.retracted_at is not None,
        source_anchor=row.source_anchor,
        created_at=row.created_at,
    )


def readings_of_segment(db: Database, segment_id: str) -> list[ReadingRead]:
    """Every reading of one segment, from BOTH stores.

    A real segment is resolved first (`resolve_segment`), so a reading written
    against an id that has since been merged away is still found under the
    segment that id now means -- an id never moves, and a reference to it must
    never dead-end.
    """
    live_id = segment_id
    if not segment_id.startswith(LEGACY_ID_PREFIX):
        resolved = resolve_segment(db, segment_id)
        live_id = primary_live_segment_id(resolved) or segment_id

    rows = list(db.query(ContentRepresentation, segment_id=live_id))
    if live_id != segment_id:
        rows.extend(db.query(ContentRepresentation, segment_id=segment_id))
    seen: set[str] = set()
    items: list[ReadingRead] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        items.append(_reading_read_from_row(row))
    items.extend(provisional_readings(db, live_id))
    return items


def _candidate(item: ReadingRead) -> ReadingCandidate:
    return ReadingCandidate(
        representation_id=item.id,
        kind=item.kind,
        provenance_kind=item.provenance_kind,
        created_at=item.created_at,
        retracted=item.retracted,
        provisional=item.provisional,
    )


def counting_by_kind(
    db: Database, segment_id: str, items: list[ReadingRead]
) -> dict[str, CountingAnswer]:
    """The counting answer for each kind present, worked out fresh.

    Nothing about it is stored (`source.reading.chosen-is-worked-out`), so
    this is computed on every read rather than cached: a cache would be a
    second, stale copy of exactly the fact this design refuses to store.
    """
    rule = project_record_rule(db)
    choices = list(db.query(ReadingChoice, segment_id=segment_id))
    answers: dict[str, CountingAnswer] = {}
    for kind in sorted({item.kind for item in items}):
        answers[kind] = resolve_counting(
            rule,
            [row for row in choices if row.kind == kind],
            [_candidate(item) for item in items if item.kind == kind],
        )
    return answers


@router.get("/{segment_id}/readings", response_model=ReadingListResponse)
async def list_segment_readings(
    segment_id: str,
    kind: Optional[str] = Query(None, description="Restrict to one reading kind"),
    db: Database = Depends(get_library_database),
) -> ReadingListResponse:
    """`GET /api/segments/{segment_id}/readings` — a segment's readings, with
    the counting answer for each kind.

    A READ, so a provisional segment id is accepted here: asking what a line
    says must work before anybody has edited the page.
    """
    try:
        items = readings_of_segment(db, segment_id)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    counting = counting_by_kind(db, segment_id, items)
    if kind is not None:
        items = [item for item in items if item.kind == kind]
        counting = {key: value for key, value in counting.items() if key == kind}
    return ReadingListResponse(items=items, count=len(items), counting=counting)


class ReadingChoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    representation_id: str


@router.post("/{segment_id}/readings/choice")
async def choose_segment_reading(
    segment_id: str,
    payload: ReadingChoiceBody,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, Any]:
    """`POST /api/segments/{segment_id}/readings/choice` — record which
    reading counts. Only a person may (`ChoiceNeedsAPerson`, 403)."""
    try:
        result = registry.invoke(
            db,
            "reading.choose",
            {"segment_id": segment_id, **payload.model_dump()},
            ctx,
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return result.result


# ===========================================================================
# A page's text is WORKED OUT (`source.point.text-is-derived`)
#
# Today's `Document.page_content` and an artifact's `content` are NOT
# rewritten and are not touched here. Consumers move to this call one by one,
# each in its own commit — the same discipline as the segment seam. A page's
# text having ONE derivation, from the working pass and each line's counting
# reading, is what makes "the text somebody sees" and "the readings somebody
# recorded" the same thing rather than two stores drifting apart.
# ===========================================================================

#: Passes read out of a file's own text layer (`importers/ingest.py`'s
#: `PDF_TEXT_GEOMETRY_ARTIFACT`). Not a recogniser's guess: the words the file
#: was made with. That is why `resolve_working_pass` ranks one above a newer
#: machine pass.
TEXT_LAYER_ARTIFACT_TYPE = "text_geometry"


class DerivedTextSpan(BaseModel):
    """Where one segment's reading sits in the derived text.

    The spans are the point of the whole answer: text with no way back to the
    line and the reading it came from is a wall of words, and every later
    feature -- a mark on a phrase, a search hit, an export -- needs the way
    back.
    """

    segment_id: str
    representation_id: str | None = None
    start: int
    end: int


class DerivedText(BaseModel):
    text: str
    spans: list[DerivedTextSpan]
    #: The pass the text was read from, and why that pass.
    pass_id: str | None = None
    pass_basis: str
    kind: str
    #: The named reading order used. `None` means box order -- named orders
    #: are slice 10, and saying `None` is honest about which is in force.
    order: str | None = None


def _pass_candidates(db: Database, document_id: str) -> list[PassCandidate]:
    """Every live pass of a document, with what the ranking needs to know.

    `has_human_segment` is worked out HERE and passed in, because
    `resolve_working_pass` must never read a pass's maker alone: a machine run
    a historian corrected by hand is theirs, and only its segments say so.
    """
    candidates: list[PassCandidate] = []
    for pass_row in db.query(SegmentPass, document_id=document_id):
        if pass_row.deleted_at is not None:
            continue
        rows = db.query(Segment, pass_id=pass_row.id)
        from_text_layer = False
        if pass_row.source_artifact_id:
            artifact = db.get(Artifact, pass_row.source_artifact_id)
            from_text_layer = (
                artifact is not None and artifact.artifact_type == TEXT_LAYER_ARTIFACT_TYPE
            )
        candidates.append(
            PassCandidate(
                pass_id=pass_row.id,
                provenance_kind=pass_row.provenance_kind,
                has_human_segment=any(
                    row.deleted_at is None and row.provenance_kind is ProvenanceKind.human
                    for row in rows
                ),
                from_text_layer=from_text_layer,
                created_at=pass_row.created_at,
            )
        )
    return candidates


def _segment_order_key(row: Segment) -> tuple:
    """Box order: the position a converted row recorded, then its place down
    the page, then its id.

    ponytail: box order, not a named reading order. Named orders are slice 10
    (`source.order.named-multiple`); until one exists, inventing an ordering
    cleverer than "the order the boxes came in" would be the engine guessing
    at a scholarly decision. `DerivedText.order` reports `None` so a caller is
    never told a named order was used when none was.
    """
    recorded = row.metadata.get("box_index")
    if isinstance(recorded, int) and not isinstance(recorded, bool):
        return (0, recorded, 0.0, row.id)
    return (1, 0, row.bbox_y, row.id)


def document_text(
    db: Database,
    document_id: str,
    *,
    pass_id: str | None = None,
    order: str | None = None,
    kind: str = "transcription",
    include_furniture: bool = False,
) -> DerivedText:
    """A page's text, worked out from its working pass and each line's
    counting reading (`source.point.text-is-derived`).

    Furniture -- a running head, a folio number, a catchword -- is LEFT OUT by
    default. It is on the page and it is properly a segment, but it is not the
    text of the document, and a search or an export that silently included it
    would put the page number in the middle of a sentence.
    """
    if order is not None:
        raise ValueError(
            "named reading orders arrive in slice 10 (source.order.named-multiple); "
            "pass order=None for box order"
        )
    candidates = _pass_candidates(db, document_id)
    if pass_id is not None:
        answer = PassAnswer(pass_id=pass_id, basis=PassBasis.chosen)
        if not any(row.pass_id == pass_id for row in candidates):
            raise LookupError(f"Pass not found on document {document_id}: {pass_id}")
    else:
        answer = resolve_working_pass(
            project_record_rule(db),
            list(db.query(SegmentPassChoice, document_id=document_id)),
            candidates,
        )
    if answer.pass_id is None:
        return DerivedText(
            text="", spans=[], pass_id=None, pass_basis=answer.basis.value, kind=kind
        )

    rows = [
        row
        for row in db.query(Segment, pass_id=answer.pass_id)
        if row.deleted_at is None and (include_furniture or not row.is_furniture)
    ]
    rows.sort(key=_segment_order_key)

    # ponytail: one readings read per line, each an indexed lookup
    # (`idx_contentrepresentations_segment_id`,
    # `idx_readingchoices_segment_id`). For a fifty-line folio that is fifty
    # small queries, not a scan. If a whole-PROJECT derivation ever needs
    # this, the upgrade is one batched read per pass
    # (`query_in(ContentRepresentation, "segment_id", ids)`) feeding the same
    # pure counting function -- not a cache of the answer, which this design
    # deliberately does not store.
    pieces: list[str] = []
    spans: list[DerivedTextSpan] = []
    cursor = 0
    for row in rows:
        items = [item for item in readings_of_segment(db, row.id) if item.kind == kind]
        if not items:
            continue
        counted = counting_by_kind(db, row.id, items).get(kind)
        if counted is None or counted.representation_id is None:
            # The line HAS readings and none of them counts (a strict project
            # where people disagree). Leaving a hole would be a lie about the
            # page; so would picking one. The span records the gap.
            spans.append(
                DerivedTextSpan(
                    segment_id=row.id, representation_id=None, start=cursor, end=cursor
                )
            )
            continue
        text = next(
            item.content for item in items if item.id == counted.representation_id
        )
        start = cursor
        pieces.append(text)
        cursor += len(text)
        spans.append(
            DerivedTextSpan(
                segment_id=row.id,
                representation_id=counted.representation_id,
                start=start,
                end=cursor,
            )
        )
        cursor += 1  # the separator below

    joined = " ".join(pieces)
    return DerivedText(
        text=joined,
        spans=spans,
        pass_id=answer.pass_id,
        pass_basis=answer.basis.value,
        kind=kind,
        order=None,
    )


@router.get("/document/{document_id}/text", response_model=DerivedText)
async def get_document_text(
    document_id: str,
    pass_id: Optional[str] = Query(None, description="Read a named pass instead of the working one"),
    kind: str = Query("transcription", description="Which kind of reading to join"),
    include_furniture: bool = Query(
        False, description="Include running heads, folio numbers and catchwords"
    ),
    db: Database = Depends(get_library_database),
) -> DerivedText:
    """`GET /api/segments/document/{document_id}/text` — the page's derived
    text and the spans that point back at the readings it came from."""
    try:
        return document_text(
            db,
            document_id,
            pass_id=pass_id,
            kind=kind,
            include_furniture=include_furniture,
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc
