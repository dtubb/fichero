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
from fichero_server.llm.language_policy import (
    DIRECTION_ALTERNATING,
    DIRECTION_FOLLOWS_BASELINE,
    STATUS_UNKNOWN,
    resolve_direction,
)
from fichero_server.models import Artifact, ContentRepresentation, Document
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


def _artifact_and_box(
    db: Database, segment_id: str, artifact_memo: dict[str, Artifact | None] | None = None
) -> tuple[Artifact | None, int | None]:
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
    def artifact(artifact_id: str) -> Artifact | None:
        # A page's lines all read the SAME artifact, and hydrating it parses every box's JSON. One
        # fetch per derivation, not one per line (#5077: the refresh made this quadratic).
        if artifact_memo is None:
            return db.get(Artifact, artifact_id)
        if artifact_id not in artifact_memo:
            artifact_memo[artifact_id] = db.get(Artifact, artifact_id)
        return artifact_memo[artifact_id]

    if segment_id.startswith(LEGACY_ID_PREFIX):
        body = segment_id[len(LEGACY_ID_PREFIX) :]
        artifact_id, _, tail = body.rpartition(":")
        if not artifact_id or not tail.isdigit():
            return None, None
        return artifact(artifact_id), int(tail)

    row = db.get(Segment, segment_id)
    if row is None:
        return None, None
    box_index = row.metadata.get("box_index")
    if not isinstance(box_index, int) or isinstance(box_index, bool):
        return None, None
    pass_row = db.get(SegmentPass, row.pass_id)
    if pass_row is None or not pass_row.source_artifact_id:
        return None, None
    return artifact(pass_row.source_artifact_id), box_index


def provisional_readings(
    db: Database,
    segment_id: str,
    *,
    allowed_kinds: list[str] | None = None,
    artifact_memo: dict[str, Artifact | None] | None = None,
    located: tuple[Artifact | None, int | None] | None = None,
) -> list[ReadingRead]:
    """This segment's readings that still live in an artifact.

    `located` is the `(artifact, box_index)` a caller that already holds the row has worked out
    (`_readings_for_live_rows`), so a whole page does not look every row up again.

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
    artifact, box_index = located if located is not None else _artifact_and_box(db, segment_id, artifact_memo)
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


def readings_of_segment(
    db: Database, segment_id: str, *, artifact_memo: dict[str, Artifact | None] | None = None
) -> list[ReadingRead]:
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
    items.extend(provisional_readings(db, live_id, artifact_memo=artifact_memo))
    return items


def _document_readings(db: Database, document_id: str) -> list[ContentRepresentation]:
    """Every stored reading of a document, loaded ONCE per derivation (slice 12, #4940).

    `_text_bearing_rows` needs them for their segment ids and `_readings_for_live_rows` for
    their content. Each used to query them itself, so every reading was hydrated twice: on the
    Cherokee page (3,910 words) the second load was most of the derivation's time.
    """
    return list(db.query(ContentRepresentation, document_id=document_id))


def _text_bearing_rows(
    db: Database,
    document_id: str,
    pass_id: str,
    *,
    readings: list[ContentRepresentation] | None = None,
) -> list[Segment]:
    """The rows of `pass_id` that can have a reading -- the only rows `document_text` uses.

    `readings` is the document's stored readings when the caller has them already
    (`_document_readings`); omitted, they are loaded here.

    A row has a reading when a stored reading names it, or -- in a pass converted from a
    machine artifact -- when it recorded its box in that artifact (`metadata["box_index"]`,
    the provisional reading's key). Every other row is skipped by the derivation anyway, so it
    is not loaded: the ids come from the readings table and one SQL scan, and only those rows
    are hydrated. The same rows, in the same order, as loading the whole pass
    (`TestTheTextIsDerivedFromTheLinesThatCarryIt`).
    """
    if readings is None:
        readings = _document_readings(db, document_id)
    ids = {rep_row.segment_id for rep_row in readings if rep_row.segment_id}
    pass_row = db.get(SegmentPass, pass_id)
    if pass_row is not None and pass_row.source_artifact_id:
        ids.update(db.segment_ids_with_box_index(pass_id))
    if not ids:
        return []
    return [row for row in db.query_in(Segment, "id", sorted(ids)) if row.pass_id == pass_id]


def counting_texts(db: Database, rows: list[Segment], kind: str = "transcription") -> dict[str, str]:
    """Each row's COUNTING reading of `kind`, by segment id, for a list of rows at once (#5139).

    What a segment list hands back as `text`: the same answer the page's text uses for that
    segment (`counting_by_kind`, the project's rule, a person's choice), so a list row and the
    page can never disagree. ONE readings query and one choices query for the whole list, by
    segment id (indexed) -- not a request per segment, which is what a caller had to do before,
    and not a whole document's readings for one page of a library listing. A row with no
    reading of `kind`, or none that counts, is absent.
    """
    ids = [row.id for row in rows]
    if not ids:
        return {}
    by_segment: dict[str, list[ReadingRead]] = {}
    for rep_row in db.query_in(ContentRepresentation, "segment_id", ids):
        if rep_row.kind == kind:
            by_segment.setdefault(rep_row.segment_id, []).append(_reading_read_from_row(rep_row))
    if not by_segment:
        return {}
    rule = project_record_rule(db)
    choices: dict[str, list[ReadingChoice]] = {}
    for choice in db.query_in(ReadingChoice, "segment_id", list(by_segment)):
        choices.setdefault(choice.segment_id, []).append(choice)
    texts: dict[str, str] = {}
    for segment_id, items in by_segment.items():
        counted = counting_by_kind(db, segment_id, items, rule=rule, choices=choices.get(segment_id, [])).get(kind)
        if counted is not None and counted.representation_id is not None:
            texts[segment_id] = next(i.content for i in items if i.id == counted.representation_id)
    return texts


def _readings_for_live_rows(
    db: Database,
    rows: list[Segment],
    document_id: str,
    artifact_memo: dict[str, Artifact | None],
    *,
    readings: list[ContentRepresentation] | None = None,
) -> dict[str, list[ReadingRead]]:
    """`readings_of_segment` for every row of a page at once -- the SAME items, in the same order.

    Slice 12 (#4940): deriving a 20,000-segment page took ~14.5 s, and every text-changing undo
    pays it. `readings_of_segment` is the right call for ONE id that may have moved; for a page's
    LIVE rows already in hand it re-walked forwarding for ids that are by definition themselves,
    ran one representation query and one `reading_kinds` query per row, and fetched each row and
    its pass again for the provisional half. Here: one representation query for the document,
    the kinds once, each pass once, no forwarding walk.
    """
    by_segment: dict[str, list[ReadingRead]] = {row.id: [] for row in rows}
    if readings is None:
        readings = _document_readings(db, document_id)
    for rep_row in readings:
        if rep_row.segment_id in by_segment:
            by_segment[rep_row.segment_id].append(_reading_read_from_row(rep_row))
    kinds = reading_kinds(db)
    passes: dict[str, SegmentPass | None] = {}

    def artifact(artifact_id: str) -> Artifact | None:
        if artifact_id not in artifact_memo:
            artifact_memo[artifact_id] = db.get(Artifact, artifact_id)
        return artifact_memo[artifact_id]

    for row in rows:
        box_index = row.metadata.get("box_index")
        if not isinstance(box_index, int) or isinstance(box_index, bool):
            continue
        if row.pass_id not in passes:
            passes[row.pass_id] = db.get(SegmentPass, row.pass_id)
        pass_row = passes[row.pass_id]
        if pass_row is None or not pass_row.source_artifact_id:
            continue
        by_segment[row.id].extend(
            provisional_readings(
                db, row.id, allowed_kinds=kinds, artifact_memo=artifact_memo,
                located=(artifact(pass_row.source_artifact_id), box_index),
            )
        )
    return by_segment


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
    db: Database,
    segment_id: str,
    items: list[ReadingRead],
    *,
    rule: Any = None,
    choices: list[ReadingChoice] | None = None,
) -> dict[str, CountingAnswer]:
    """The counting answer for each kind present, worked out fresh.

    Nothing about it is stored (`source.reading.chosen-is-worked-out`), so
    this is computed on every read rather than cached: a cache would be a
    second, stale copy of exactly the fact this design refuses to store.
    """
    # `rule` and `choices` may be handed in by a caller deriving a whole page, which fetches them
    # ONCE (slice 12: one choice query per line was most of a dense page's remaining cost). The
    # answer is the same either way -- it is still worked out fresh, never stored.
    if rule is None:
        rule = project_record_rule(db)
    if choices is None:
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


class TextBlock(BaseModel):
    """One directional run of the derived text (`source.textedit.reader-shows-segments`,
    #5001): a maximal, in-order stretch of spans sharing the same region AND the same
    resolved direction. A block boundary is a DIRECTION CHANGE, not a direction value --
    a whole-page `rtl` region is one block; a boustrophedon region, where each line's own
    stated direction alternates, is one block PER LINE, because there is no shared
    orientation two alternating lines can be laid out under at once.

    `alternating` and `follows-baseline` are per-segment values with no single orientation
    of their own (`languages-scripts-signs.md`'s six-value list), so a segment resolving to
    either NEVER merges with a neighbour even when the neighbour resolves to the same
    non-orientable value -- there is nothing to share a block under.
    """

    #: The line's parent region, or None for a line with no region parent.
    region_segment_id: str | None
    #: The resolved direction shared by every span in this block, or None when the first
    #: span's own direction could not be resolved at all (`STATUS_UNKNOWN`).
    direction: str | None
    #: Which rung of the cascade decided it (`source.dir.per-segment`'s own cascade) --
    #: never invented, so a reader can tell a stated direction from a derived one.
    direction_level: str | None
    spans: list[DerivedTextSpan]
    #: This block's own slice of the derived text (a subrange of `DerivedText.text`), so
    #: a block can be rendered on its own without re-slicing by hand.
    text: str


class OmittedSegment(BaseModel):
    """A segment a named order names and the text does not contain, and WHY.

    Before this existed (#5090) every such segment was dropped by one
    `if sid in by_id`, and four different things looked identical: a line
    somebody deleted, furniture the caller asked to leave out, a segment of
    ANOTHER pass -- which is how a cross-pass flow reads, and is the bug -- and
    an id naming nothing at all. The first two are correct and expected; the
    third silently shortens a transcription, which is the worst failure this
    programme has, because nothing looks wrong.

    So the reason is reported rather than the omission being hidden. A caller
    that sees `other_pass` knows a continuation is missing; one that sees
    `deleted` knows the text is complete.
    """

    segment_id: str
    #: `deleted`, `furniture`, `other_pass` or `unknown`.
    reason: str
    #: For `other_pass`, the pass that actually holds the segment, so a caller
    #: can go and read it. `None` for every other reason.
    pass_id: str | None = None


class DerivedText(BaseModel):
    text: str
    spans: list[DerivedTextSpan]
    #: The pass the text was read from, and why that pass.
    pass_id: str | None = None
    pass_basis: str
    kind: str
    #: The named reading order the CALLER asked for, or `None`. With `None` the text follows the
    #: pass's own `as-written` order when that order holds every line (so a line a person moved
    #: reads where they put it, Q5), and the file's / box order otherwise -- which, for an import,
    #: is the same sequence until something is moved.
    order: str | None = None
    #: Segments the named order names that this text does not contain, each with
    #: its reason (#5090). Always empty for box order, which names nothing it
    #: cannot read.
    omitted: list[OmittedSegment] = []
    #: One entry per directional run (#5001's `reader-shows-segments`). Always present,
    #: never re-derived by a second caller: the SAME spans this text already carries,
    #: grouped, so the two can never disagree about what the page contains.
    blocks: list[TextBlock] = []


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
        # ONLY the human rows are fetched: the question is "does this pass hold a person's
        # segment", and hydrating every row of a 20,000-segment import to ask it made the
        # working-pass check cost seconds (#5086, found measuring a dense import).
        # A COUNT, not the rows: an imported pass is all human rows, and loading 20,000 of them to
        # ask "is there one?" was half of a dense page's derivation (slice 12).
        human_live = db.count(
            Segment, pass_id=pass_row.id, provenance_kind=ProvenanceKind.human.value, deleted_at=None,
        )
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
                has_human_segment=human_live > 0,
                from_text_layer=from_text_layer,
                created_at=pass_row.created_at,
            )
        )
    return candidates


def _as_written_sequence(db: Database, pass_id: str) -> dict[str, int] | None:
    """Each segment's place when the pass's `as-written` order is walked depth first, each level
    by position (a block, then its lines, then their words), or None when the pass has no such
    order. One query for the order's entries, read as four columns, not hydrated rows."""
    from fichero_server.api.routes.document.reading_orders import as_written_order

    order = as_written_order(db, pass_id)
    if order is None:
        return None
    children: dict[str | None, list[tuple[float, str, str]]] = {}
    for entry_id, segment_id, parent_id, position in db.reading_order_entry_rows(order.id):
        children.setdefault(parent_id, []).append((position, entry_id, segment_id))
    sequence: dict[str, int] = {}
    pending: list[tuple[float, str, str]] = sorted(children.get(None, []), reverse=True)
    while pending:
        _position, entry_id, segment_id = pending.pop()
        sequence.setdefault(segment_id, len(sequence))
        pending.extend(sorted(children.get(entry_id, []), reverse=True))
    return sequence


def _segment_order_key(row: Segment) -> tuple:
    """Box order: the position a converted row recorded, then its place down and
    ACROSS the page, then its id.

    ponytail: box order, not a named reading order. Named orders are slice 10
    (`source.order.named-multiple`); until one exists, inventing an ordering
    cleverer than "the order the boxes came in" would be the engine guessing
    at a scholarly decision. `DerivedText.order` reports `None` so a caller is
    never told a named order was used when none was.

    `bbox_x` is in the key, and its absence was a DEFECT (found 2026-09-26 while
    grounding slice 10): without it, two segments on the same line -- identical
    `bbox_y`, no `box_index`, which is every hand-drawn word on one line -- fell
    through to `row.id`, a random uuid. The words of a line came out in uuid
    order. `media/ocr_geometry.py::reading_order` sorts boxes top-then-LEFT for
    exactly this reason; this key now matches it, which is also what makes
    slice 10's `as-written` order able to agree with both.

    `row.id` stays as the LAST resort so the sort is total and stable, never as
    a meaningful position (#4921: a random uuid is not an order).
    """
    for key in ("box_index", "file_position"):
        # `box_index`: a converted row's box. `file_position`: an imported row's place in its
        # file (#5137) -- the FILE's order wins over geometry, which interleaves columns and
        # scrambles vertical text. A pass has one or the other, never both.
        recorded = row.metadata.get(key)
        if isinstance(recorded, int) and not isinstance(recorded, bool):
            return (0, recorded, 0.0, 0.0, row.id)
    return (1, 0, row.bbox_y, row.bbox_x, row.id)


def _why_omitted(
    db: Database, segment_id: str, pass_id: str, *, include_furniture: bool
) -> OmittedSegment:
    """Why a segment a named order names is not in the derived text.

    Four answers, and telling them apart is the whole point (#5090): `deleted`
    and `furniture` are the text being correct, `other_pass` is a cross-pass
    flow's continuation going missing, and `unknown` is an order naming an id
    that never existed -- which would be a bug in whatever wrote the entry.

    One indexed lookup per omitted segment, and the list is normally empty; this
    costs nothing on the ordinary path.
    """
    row = db.get(Segment, segment_id)
    if row is None:
        return OmittedSegment(segment_id=segment_id, reason="unknown")
    if row.pass_id != pass_id:
        # The cross-pass flow. Reported WITH the pass that holds it, because a
        # caller that wants the continuation needs somewhere to go.
        return OmittedSegment(
            segment_id=segment_id, reason="other_pass", pass_id=row.pass_id
        )
    if row.deleted_at is not None:
        return OmittedSegment(segment_id=segment_id, reason="deleted")
    if row.is_furniture and not include_furniture:
        return OmittedSegment(segment_id=segment_id, reason="furniture")
    # On the pass, live, not furniture, and still not in the rows: that should be
    # impossible, and guessing a reason would be worse than admitting it.
    return OmittedSegment(segment_id=segment_id, reason="unknown")


#: WHICH DERIVATION wrote a cached page text (`page_text_cache.DERIVATION_STAMP`). Bump it in the
#: same commit as any change to what `document_text` produces, and re-pin the digest below.
#:
#: Why a number and not "the cache is refreshed when something changes": #5148 changed the
#: derivation (a region's own text stopped doubling its lines), and every page cached before the
#: fix kept the doubled text, because nothing on those pages changed. A changed derivation under
#: an unchanged stamp is exactly that bug; a bumped stamp makes the next read re-derive the page,
#: once. 1: before stamping. 2: text once (#5148) and direction from line shapes (#5147).
#: 3: the stored line map carries each line's direction (#5147 Reader half).
DERIVATION_VERSION = 3
#: sha256 of the derivation's source (`derivation_source_digest`), pinned beside the version so a
#: change to the code without a bump fails `test_derivation_version.py`.
DERIVATION_SOURCE_SHA256 = "42e44a29b34e1f954e25534ee32c001271adca664d46c7db1bcdfb75afc77868"


def derivation_source_digest() -> str:
    """sha256 over the source of the functions that decide a page's derived text."""
    import hashlib
    import inspect

    functions = (
        document_text, _text_bearing_rows, _readings_for_live_rows, _document_readings,
        _segment_order_key, _direction_of, _lines_are_vertical,
    )
    return hashlib.sha256("\n".join(inspect.getsource(f) for f in functions).encode()).hexdigest()


def _direction_of(
    row: Segment, document: Any, text: str | None, lines_are_vertical: bool | None = None
) -> tuple[str | None, str | None]:
    """A span's direction and the rung that said so. With nothing stated anywhere, the text's own
    characters decide (#5137: Syriac and Hebrew lines came out `ltr`), and for a script that may
    be vertical, the page's line shapes (#5147)."""
    resolved = resolve_direction(
        segment=row, document=document, text=text, lines_are_vertical=lines_are_vertical
    )
    return (resolved.language if resolved.status != STATUS_UNKNOWN else None), resolved.level


def _lines_are_vertical(rows: list[Segment], document: Any) -> bool | None:
    """Whether this page's lines are columns (`lines_are_columns`), measured in the page's pixels
    when its size is known. Lines with no shape of their own -- `shape: unstated`, or placed only
    by their page's TEI zone -- are not measured: their box is not the line's."""
    from fichero_server.formats.tei import PAGE_ZONE
    from fichero_server.llm.language_policy import lines_are_columns

    metadata = getattr(document, "metadata", None) or {}
    width = metadata.get("width") if isinstance(metadata.get("width"), (int, float)) else 1
    height = metadata.get("height") if isinstance(metadata.get("height"), (int, float)) else 1
    boxes: list[tuple[float, float]] = []
    for row in rows:
        if row.kind != "line" or row.anchor is None or not row.anchor.rect:
            continue
        meta = row.metadata or {}
        if meta.get("shape") == "unstated" or (meta.get("foreign") or {}).get(PAGE_ZONE):
            continue
        _x, _y, w, h = row.anchor.rect
        boxes.append((w * width, h * height))
    return lines_are_columns(boxes)


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
    ordered_segment_ids: list[str] | None = None
    named_order = None
    if order is not None:
        # Slice 10 (#4930): the page's text follows a NAMED order. `order` is an
        # order's id, and it must belong to the pass being read -- a text
        # assembled from one pass's readings in another pass's order would be a
        # sentence nobody wrote.
        from fichero_server.api.routes.document.reading_orders import (
            entries_in_sequence,
            order_for_text,
        )

        named_order = order_for_text(db, order)
        ordered_segment_ids = [
            row.segment_id for row in entries_in_sequence(db, named_order.id)
        ]
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
            text="", spans=[], pass_id=None, pass_basis=answer.basis.value, kind=kind,
            order=order,
        )

    if named_order is not None and named_order.pass_id != answer.pass_id:
        from fichero_server.models.reading_orders import OrderIsOfAnotherPass

        # This comment used to CLAIM the invariant and nothing enforced it: an
        # order of another pass produced an empty text, and (before #5090) an
        # empty text with no explanation. Writing the refusals down for the api
        # reference is what found it. A flow is no exception here -- a flow
        # belongs to the pass it was made on and continues onto others.
        raise OrderIsOfAnotherPass(named_order.id, named_order.pass_id, answer.pass_id)

    # Loaded once and handed to both readers below (#4940): each used to load them itself.
    document_readings = _document_readings(db, document_id)
    rows = [
        row
        for row in (
            # The default order needs only the rows that can CARRY text (slice 12, #4940): on a
            # 20,000-shape page ~2.9 s of 3.3 s was loading every character and word just to
            # skip it for having no reading. A named order still needs every row, because it
            # must say why each id it names is missing.
            _text_bearing_rows(db, document_id, answer.pass_id, readings=document_readings)
            if ordered_segment_ids is None
            else db.query(Segment, pass_id=answer.pass_id)
        )
        if row.deleted_at is None and (include_furniture or not row.is_furniture)
    ]
    omitted: list[OmittedSegment] = []
    if ordered_segment_ids is None:
        # The pass's `as-written` order decides, when it holds every line that carries text (Q5:
        # a line moved in the order reads where it was moved to). It is built from the same file
        # position as `_segment_order_key` (format.import, #5137), so until a person moves
        # something the two are the same sequence and the text is byte-identical. A line the
        # order does not hold means the order cannot speak for the page, and the old rule decides
        # the WHOLE page -- never a mix of two orders.
        sequence = _as_written_sequence(db, answer.pass_id)
        if sequence is not None and rows and all(row.id in sequence for row in rows):
            rows.sort(key=lambda row: (sequence[row.id], row.id))
        else:
            rows.sort(key=_segment_order_key)
    else:
        # The NAMED order's sequence. Segments the order does not mention are LEFT
        # OUT rather than appended: an order is a claim about what reads and in
        # what sequence, and appending the rest would silently add text the order
        # does not claim.
        #
        # A segment the order NAMES and the pass does not hold is a different
        # matter, and it used to fall through the same `if sid in by_id` with no
        # trace (#5090). It is still left out -- reading another pass's readings
        # needs a decision about what `pass_id` and the `page_content` cache then
        # mean -- but it is now named and explained, so a deleted line and a
        # missing cross-pass continuation stop looking the same.
        by_id = {row.id: row for row in rows}
        omitted = [
            _why_omitted(db, sid, answer.pass_id, include_furniture=include_furniture)
            for sid in ordered_segment_ids
            if sid not in by_id
        ]
        rows = [by_id[sid] for sid in ordered_segment_ids if sid in by_id]

    # ponytail: one readings read per line, each an indexed lookup
    # (`idx_contentrepresentations_segment_id`,
    # `idx_readingchoices_segment_id`). For a fifty-line folio that is fifty
    # small queries, not a scan. If a whole-PROJECT derivation ever needs
    # this, the upgrade is one batched read per pass
    # (`query_in(ContentRepresentation, "segment_id", ids)`) feeding the same
    # pure counting function -- not a cache of the answer, which this design
    # deliberately does not store.
    document = db.get(Document, document_id)
    # Non-orientable per-segment values (`languages-scripts-signs.md`'s six-value list):
    # neither describes ONE orientation a block could be laid out under, so a segment
    # resolving to either always starts (and ends) its own block.
    _NON_ORIENTABLE = {DIRECTION_ALTERNATING, DIRECTION_FOLLOWS_BASELINE}

    artifact_memo: dict[str, Artifact | None] = {}
    pieces: list[str] = []
    spans: list[DerivedTextSpan] = []
    # (region_segment_id, direction, direction_level, span) for every span this text
    # carries, IN ORDER -- the same order `blocks` groups by; built alongside `spans`
    # rather than re-walked from them, so the two can never read the page differently.
    span_directions: list[tuple[str | None, str | None, str | None, DerivedTextSpan]] = []
    cursor = 0
    page_readings = _readings_for_live_rows(
        db, rows, document_id, artifact_memo, readings=document_readings
    )
    # EACH CHARACTER ONCE (#5148). PAGE XML carries text at every level: a region's own
    # TextEquiv is usually its lines joined. Reading both put the page's text on the page twice
    # -- line by line, then again as one paragraph (the Chinese table of contents). A row whose
    # children carry text of this kind is a rival reading of those children, not more of the
    # page: the finest level that has text is the page's text, and the coarser reading stays a
    # reading of its own segment (readings route, export), just not a second copy here.
    carrying = {row.id for row in rows if any(item.kind == kind for item in page_readings[row.id])}
    read_through_children = {
        row.parent_segment_id for row in rows if row.id in carrying and row.parent_segment_id
    }
    # Once per page: are its lines columns? Only asked of a text whose script may be vertical.
    vertical = _lines_are_vertical(rows, document)
    record_rule = project_record_rule(db)
    choices_by_segment: dict[str, list[ReadingChoice]] = {}
    for choice in db.query_in(ReadingChoice, "segment_id", [row.id for row in rows]):
        choices_by_segment.setdefault(choice.segment_id, []).append(choice)
    for row in rows:
        items = [item for item in page_readings[row.id] if item.kind == kind]
        if not items or row.id in read_through_children:
            continue
        counted = counting_by_kind(
            db, row.id, items, rule=record_rule, choices=choices_by_segment.get(row.id, []),
        ).get(kind)
        if counted is None or counted.representation_id is None:
            # The line HAS readings and none of them counts (a strict project
            # where people disagree). Leaving a hole would be a lie about the
            # page; so would picking one. The span records the gap.
            span = DerivedTextSpan(
                segment_id=row.id, representation_id=None, start=cursor, end=cursor
            )
            direction, direction_level = _direction_of(row, document, None, vertical)
            spans.append(span)
            span_directions.append((row.parent_segment_id, direction, direction_level, span))
            continue
        text = next(
            item.content for item in items if item.id == counted.representation_id
        )
        direction, direction_level = _direction_of(row, document, text, vertical)
        start = cursor
        pieces.append(text)
        cursor += len(text)
        span = DerivedTextSpan(
            segment_id=row.id,
            representation_id=counted.representation_id,
            start=start,
            end=cursor,
        )
        spans.append(span)
        span_directions.append((row.parent_segment_id, direction, direction_level, span))
        cursor += 1  # the separator below

    joined = " ".join(pieces)

    blocks: list[TextBlock] = []
    for region_id, direction, direction_level, span in span_directions:
        non_orientable = direction in _NON_ORIENTABLE
        joins_previous = (
            blocks
            and not non_orientable
            and blocks[-1].region_segment_id == region_id
            and blocks[-1].direction == direction
            and blocks[-1].direction not in _NON_ORIENTABLE
        )
        if joins_previous:
            blocks[-1].spans.append(span)
        else:
            blocks.append(
                TextBlock(
                    region_segment_id=region_id,
                    direction=direction,
                    direction_level=direction_level,
                    spans=[span],
                    text="",
                )
            )
    for block in blocks:
        block.text = joined[block.spans[0].start:block.spans[-1].end]

    return DerivedText(
        text=joined,
        spans=spans,
        pass_id=answer.pass_id,
        pass_basis=answer.basis.value,
        kind=kind,
        omitted=omitted,
        # Which order produced this text: the named one when asked for, `None` for
        # box order. Never a name the caller did not ask for -- a reader told an
        # order was used when it was not cannot check anything.
        order=order,
        blocks=blocks,
    )


@router.get("/document/{document_id}/text", response_model=DerivedText)
async def get_document_text(
    document_id: str,
    pass_id: Optional[str] = Query(None, description="Read a named pass instead of the working one"),
    order: Optional[str] = Query(
        None,
        description=(
            "Follow a named reading order (its id). Omit for box order, which is "
            "what the answer's `order: null` reports."
        ),
    ),
    kind: str = Query("transcription", description="Which kind of reading to join"),
    include_furniture: bool = Query(
        False, description="Include running heads, folio numbers and catchwords"
    ),
    db: Database = Depends(get_library_database),
) -> DerivedText:
    """`GET /api/segments/document/{document_id}/text` — the page's derived
    text and the spans that point back at the readings it came from.

    With `order`, the text follows that named order (`source.order.named-multiple`
    reaching the text, slice 10): a commentary order and an as-written order over
    the same page give different texts, which is the whole point of naming them.
    """
    try:
        return document_text(
            db,
            document_id,
            pass_id=pass_id,
            order=order,
            kind=kind,
            include_furniture=include_furniture,
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc
