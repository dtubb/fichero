"""Source-model slice 6 (#4924) -- first-edit conversion, and the one live
view of an artifact's boxes.

Two halves, in the order they must be built:

1. **`live_geometry`** -- the ONE answer to "what are this artifact's boxes
   right now". Before conversion that is the stored `ocr_geometry` block;
   after conversion it is an ordered projection of the segment rows. Every
   consumer that wants a person's CURRENT page calls this; nothing reads
   `Artifact.ocr_geometry` directly except the two callers that genuinely
   want the machine's original (see `PERMITTED_RAW_GEOMETRY_READERS`).
2. The conversion action itself (built on top, in this same module so it
   cannot collide with the segment-actions file).

Why a projection at all: the app does not read segments yet (app stage 2,
#4954, is held), and every one of its region readers addresses a box by its
POSITION in the artifact's box list. The projection keeps that invariant
true -- position N of the projection is row N of the pass's live read order
-- so the unchanged app keeps working through a conversion it cannot see.
**When app stage 2 lands, delete `live_geometry`'s projection branch and
this module's callers in `artifacts.py` (#4954).**
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, ContentRepresentation, Document
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import (
    Annotation,
    KnowledgeClaim,
    ProvenanceKind,
)
from fichero_server.models.segments import (
    Segment,
    SegmentPass,
    SegmentPassChoice,
    AnchorBasis,
    ResolvedAnchor,
    derive_pass_provenance_kind,
    converted_segment_id,
    words_for_row,
    converted_pass_id,
    rows_from_reads,
    segments_from_result,
)

logger = logging.getLogger(__name__)


class ConversionRefusal(Exception):
    """Base for every typed refusal this module raises.

    It exists so ONE handler at the ASGI boundary can map all of them,
    rather than a try/except repeated at every route that can reach a
    conversion -- which today is the seam, `GET /api/artifacts/{id}`, the
    artifact list, the document VIEW, `/region`, `/text-regions`, the
    generic `POST /api/actions/invoke`, the chat tool path and four
    workflow tools. The same argument `_handle_bare_authorization_error`
    makes next door: a per-route handler has to be repeated everywhere and
    is inevitably missed somewhere.

    `status_code` is each class's own answer to "what should a caller be
    told", set beside its reason rather than guessed at the boundary.
    """

    status_code: int = 409


class ConversionMarkerDangling(ConversionRefusal, RuntimeError):
    """An artifact says its boxes became a pass, and that pass is not there.

    NEVER a fall back to the stored block. The block is the state BEFORE a
    person's edits; serving it because the rows could not be found would
    silently undo their work on screen and, worse, look fine. Raising is the
    only honest answer -- the library needs repair, not a guess.
    """

    status_code = 409

    def __init__(self, artifact_id: str, pass_id: str, why: str) -> None:
        self.artifact_id = artifact_id
        self.pass_id = pass_id
        super().__init__(
            f"artifact {artifact_id!r} says its boxes became pass {pass_id!r}, "
            f"but that pass {why}; refusing to serve the superseded block"
        )


def is_converted(artifact: Artifact) -> bool:
    """`source.store.ids-on-first-edit`: an artifact is converted when its
    MARKER is set, never because some pass happens to name it (any caller
    can make such a pass by hand through `POST /api/segments/passes`)."""
    return artifact.geometry_superseded_by_pass_id is not None


class GeometryFrozenByConversion(ConversionRefusal, RuntimeError):
    """Something tried to write `ocr_geometry` onto a converted artifact.

    From a page's first edit its block is the record of what the MACHINE
    produced and is never written again. Replacing it in place would leave
    the rows holding one page's shapes while the block holds another's
    words, so the projection would serve a box's outline with a different
    box's text -- plausible on screen, wrong, and nothing raised.

    The honest answer for a tool that has produced NEW boxes is a NEW
    artifact, which is what every other producer already does; only the
    in-place update path can reach this.
    """

    status_code = 409

    def __init__(self, artifact_id: str, pass_id: str) -> None:
        self.artifact_id = artifact_id
        self.pass_id = pass_id
        super().__init__(
            f"artifact {artifact_id!r} was converted to segments (pass "
            f"{pass_id!r}); its geometry block is the machine's own record and "
            "is never written again -- save a NEW artifact instead"
        )


def assert_geometry_writable(artifact: Artifact) -> None:
    """Refuse an in-place write of `ocr_geometry` on a converted artifact.

    The ONE place any writer checks, so a future in-place update path has
    something to call rather than a rule to remember."""
    if is_converted(artifact):
        raise GeometryFrozenByConversion(
            artifact.id, artifact.geometry_superseded_by_pass_id or ""
        )


def marker_from_the_store(db: Any, artifact_id: str, current: Artifact | None) -> str | None:
    """Which pass, if any, this artifact's boxes became -- read from the
    STORE, never from a payload being restored (#4924).

    THE INVARIANT, and the whole of the fix: **a restore never decides
    whether a page is converted.** A recorded dump is a picture of the
    past; whether the boxes are rows NOW is a fact about the present.
    Taking it from the payload is what let an old undo silently un-convert
    a page and leave two stores side by side.

    Two cases, both covered because the answer comes from one place. The
    row still exists (undo of `update` or `regions_edit`): its own marker
    is the answer. The row is gone (undo of `delete`, or a document
    restore replaying artifact snapshots): the conversion's ids are
    REPEATABLE, so "is that artifact's pass there?" is a complete
    question -- and if it is, the restored row is marked again rather than
    coming back as an unconverted twin of a page that already has rows.

    Used by BOTH restore paths: `artifacts.py::_restore_artifact_impl` and
    `documents.py`'s bulk restore of recorded artifact snapshots.
    """
    if current is not None and current.geometry_superseded_by_pass_id:
        return current.geometry_superseded_by_pass_id
    pass_id = converted_pass_id(artifact_id)
    pass_row = db.get(SegmentPass, pass_id)
    if pass_row is not None and pass_row.deleted_at is None:
        return pass_id
    return None


class ArtifactGeometryRestoreRefused(ConversionRefusal, ValueError):
    """An undo would have written a pre-conversion snapshot over a page
    whose boxes are now segments.

    THE TRAP THIS CLOSES. `artifact.restore` is the inverse of THREE
    actions -- `artifact.update`, `artifact.delete` and
    `artifact.regions_edit` -- and it works by writing a whole recorded row
    back. A dump recorded BEFORE the page was converted has no marker. So:
    move a box by the old route, convert the page later, then undo that old
    move, and the restore clears the marker while the pass and rows stay.
    The seam then returns the rows AND the block's provisional boxes --
    every box twice -- `live_geometry` serves the stale block, and the page
    can never be converted again because the second guard finds the pass.
    Two stores, stuck.
    """

    status_code = 409

    def __init__(self, artifact_id: str, pass_id: str) -> None:
        self.artifact_id = artifact_id
        self.pass_id = pass_id
        super().__init__(
            f"artifact {artifact_id!r} cannot have its stored geometry restored: "
            f"its boxes became segments (pass {pass_id!r}) since that snapshot "
            "was taken. Undo the change on its segments instead"
        )


def restored_artifact_row(db: Any, payload: dict, *, refuse_different_boxes: bool) -> Artifact:
    """One recorded artifact snapshot, made safe to write back.

    THE INVARIANT: **a restore never decides whether a page is converted,
    and never rewrites a kept block.** A recorded dump is a picture of the
    past; whether the boxes are rows NOW, and what the machine originally
    produced, are facts about the present that the snapshot cannot speak
    for.

    Shared by BOTH restore paths -- `artifacts.py::_restore_artifact_impl`
    (undo of update/delete/regions_edit) and `documents.py`'s bulk replay
    of artifact snapshots when a document is restored -- because they are
    the same defect if they disagree.

    `refuse_different_boxes` is the one difference. A single artifact undo
    REFUSES a snapshot whose boxes differ from the kept block, so a person
    is told their undo cannot apply. A bulk document restore cannot refuse
    the whole document over one artifact, so it keeps the block silently
    and restores everything else. Either way THE BLOCK IS NEVER WRITTEN on
    a converted artifact, which is what #4990's resolver will rest on: the
    kept block's boxes never move, so the rectangle a mark was made from
    can always be found in it.
    """
    artifact = Artifact(**payload) if not isinstance(payload, Artifact) else payload
    current = db.get(Artifact, artifact.id)
    marker = marker_from_the_store(db, artifact.id, current)

    if marker is not None and current is not None:
        kept = current.ocr_geometry  # raw-geometry-ok: comparing against the frozen record itself
        # `artifact` is built from the PAYLOAD, not read from the store, so
        # this is the snapshot being compared AGAINST the store.
        restoring = artifact.ocr_geometry  # raw-geometry-ok: the payload's own boxes, not a stored row's
        if kept is not None:
            if refuse_different_boxes and restoring is not None and restoring != kept:
                raise ArtifactGeometryRestoreRefused(artifact.id, marker)
            # Everything else in the snapshot may be restored (content,
            # provider, reviewed, ...); the boxes stay exactly as they are.
            artifact.ocr_geometry = kept

    artifact.geometry_superseded_by_pass_id = marker
    return artifact


def converted_pass_of(db: Any, artifact: Artifact) -> SegmentPass:
    """The live pass an artifact's boxes became, or `ConversionMarkerDangling`."""
    pass_id = artifact.geometry_superseded_by_pass_id
    if pass_id is None:
        raise ValueError(f"artifact {artifact.id!r} is not converted")
    pass_row = db.get(SegmentPass, pass_id)
    if pass_row is None:
        raise ConversionMarkerDangling(artifact.id, pass_id, "does not exist")
    if pass_row.deleted_at is not None:
        raise ConversionMarkerDangling(artifact.id, pass_id, "is deleted")
    return pass_row


def live_rows_in_order(db: Any, pass_id: str) -> list[Segment]:
    """A pass's live segments in the ONE order the app is given them.

    The single source of the ordering, used by BOTH the projection below and
    the translation of the app's box positions into rows. Two orderings would
    mean the app moving box 3 and the engine moving a different one.
    """
    # The sort key lives beside the seam that reads it. Imported, never
    # copied: a second copy of this rule is exactly how the app's positions
    # and the engine's rows would drift apart.
    # TODO(#4924 step 5): move `_segment_row_sort_key` down to
    # `models/segments.py`, beside `Segment`, and import it from there.
    from fichero_server.api.routes.document.segments import _segment_row_sort_key

    rows = [row for row in db.query(Segment, pass_id=pass_id) if row.deleted_at is None]
    rows.sort(key=_segment_row_sort_key)
    return rows


def _box_for_row(
    row: Segment, source_box: OCRGeometryBox | None, words: str | None = None
) -> OCRGeometryBox:
    """One live row as the box the unchanged app expects.

    The row's ANCHOR is authoritative for the shape -- that is what an edit
    changes. Everything the row has no opinion about (the words, the char
    span, the page, who produced it) is copied from the box it was converted
    from, which is why the block is kept. A row with no source box is one a
    person drew after conversion: it gets the same honest provenance
    `_edit_regions_impl`'s ADD branch writes today.
    """
    rect = row.anchor.rect
    if rect is None and row.anchor.polygon:
        xs = [p[0] for p in row.anchor.polygon]
        ys = [p[1] for p in row.anchor.polygon]
        rect = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    if rect is None:
        # An undrawable box. The app draws a zero-size placeholder and,
        # crucially, still counts it -- so every later position stays put.
        rect = [0.0, 0.0, 0.0, 0.0]

    if source_box is not None:
        # EVERYTHING THE ROW HAS AN OPINION ABOUT COMES FROM THE ROW
        # (#4924 review, step 5). The source box supplies only what a row
        # does not carry -- the provider that produced it, its page, its
        # own metadata. Its shape, its level and its char span are the
        # row's, because an edit changes those: after a combine the row is
        # a `region` spanning its members, and reading the level off the
        # box it happened to keep would report a `word`.
        update = {
            "bbox": list(rect),
            "text": words if words is not None else source_box.text,
            "level": row.kind,
            "char_start": row.anchor.char_start,
            "char_end": row.anchor.char_end,
        }
        if row.metadata.get("member_box_indexes"):
            # A combined box is a person's work and says so, exactly as
            # today's combine does -- a reader that ranks or trusts
            # geometry must not mistake it for the machine's own.
            update["provider"] = "user"
            update["source"] = "combine"
        return source_box.model_copy(update=update)

    hand_drawn = row.provenance_kind is ProvenanceKind.human
    return OCRGeometryBox(
        text="",
        bbox=list(rect),
        level=row.kind,
        confidence=row.confidence,
        page_index=row.metadata.get("page_index"),
        provider="user" if hand_drawn else None,
        source="manual" if hand_drawn else None,
    )


def geometry_from_rows(block: OCRGeometryResult | None, rows: list[Segment]) -> OCRGeometryResult:
    """The projection: the artifact's kept block with its boxes replaced by
    the live rows, in order.

    Everything ABOUT the result rather than about one box -- the result's own
    text (which every box's `char_start`/`char_end` indexes into), the
    provider, the model, the rendition the boxes were measured on, the
    curation log -- is the block's, unchanged. Only `boxes` is rebuilt.
    """
    base = block or OCRGeometryResult(provider="user", boxes=[])
    source_boxes = base.boxes
    boxes = [
        _box_for_row(
            row,
            source_boxes[row.metadata["box_index"]]
            if isinstance(row.metadata.get("box_index"), int)
            and not isinstance(row.metadata.get("box_index"), bool)
            and 0 <= row.metadata["box_index"] < len(source_boxes)
            else None,
            words_for_row(base, row.metadata),
        )
        for row in rows
    ]
    return base.model_copy(update={"boxes": boxes})


def live_geometry(db: Any, artifact: Artifact) -> OCRGeometryResult | None:
    """THE one read of an artifact's boxes as they are NOW.

    Before conversion: the stored block, exactly as today. After conversion:
    an ordered projection of the segment rows, so a person's edits are what
    every reader sees. A marker with no live pass behind it RAISES.

    Call this -- not `artifact.ocr_geometry` -- from anything that shows,
    counts, measures or resolves against a person's current page. Reading the
    raw field instead is how a claim's highlight ends up pointing at where a
    box used to be: silently, with nothing raising, on the one page somebody
    has actually curated.
    """
    if not is_converted(artifact):
        return artifact.ocr_geometry
    pass_row = converted_pass_of(db, artifact)
    return geometry_from_rows(artifact.ocr_geometry, live_rows_in_order(db, pass_row.id))


def live_box_count(db: Any, artifact: Artifact) -> int:
    """`region_count` for an artifact, live.

    Cheap for the unconverted case -- no query at all -- which is every
    artifact until its page's first edit.

    For a converted one it asks the DATABASE to count, and never hydrates a
    row: `region_count` rides on every list response, the document view is
    the hottest route there is, and building the whole projection there --
    every row loaded and sorted, every box copied -- to answer "how many"
    measured 735 ms for one dense page (2026-09-20). A count is 1 ms.
    """
    if not is_converted(artifact):
        # raw-geometry-ok: an unconverted artifact's block IS its live geometry
        return len(artifact.ocr_geometry.boxes) if artifact.ocr_geometry else 0
    pass_row = converted_pass_of(db, artifact)
    return db.count(Segment, pass_id=pass_row.id, deleted_at=None)


#: The ONLY places allowed to read `Artifact.ocr_geometry` directly rather
#: than through `live_geometry`. Both want the MACHINE'S ORIGINAL, not the
#: person's current page, and say so:
#:
#: * the conversion itself, which is what turns the original into rows;
#: * the projection above, which rebuilds the person's page FROM the original.
#:
#: Everything else -- serialisation, counts, span resolution, the workflow
#: tools that measure a page -- wants the live answer. Enforced by
#: `scripts/check_raw_geometry_readers.py`.
PERMITTED_RAW_GEOMETRY_READERS = (
    "fichero-server/src/fichero_server/api/routes/document/segment_conversion.py",
    "fichero-server/src/fichero_server/api/routes/document/segments.py",
)


# ---------------------------------------------------------------------------
# The action: a page's boxes become lasting segments, once, on its first edit
# ---------------------------------------------------------------------------


class AlreadyConverted(ConversionRefusal, ValueError):
    """This artifact's boxes are already segment rows.

    Raised on two different looks, and both are needed. The route's look
    happens OUTSIDE the transaction and can be beaten by a racing request;
    the action's looks happen inside it, where the transaction gate
    serialises them. The route catches this and re-routes the same request
    down the converted branch, once -- the routing decision made again on
    fresh state, never a fallback.
    """

    status_code = 409

    def __init__(self, artifact_id: str, pass_id: str) -> None:
        self.artifact_id = artifact_id
        self.pass_id = pass_id
        super().__init__(
            f"artifact {artifact_id!r} was already converted to pass {pass_id!r}"
        )


class ConvertedIdAlreadyTaken(ConversionRefusal, ValueError):
    """One of the ids this conversion would mint is already a segment.

    The conversion's ids are REPEATABLE ON PURPOSE, derived from the
    artifact and a box position by a formula that is in an open-source
    file. That is what makes a lazy conversion equal an eager one -- and it
    also means a future converted box's id can be worked out in advance.
    `Database.save_many` is `INSERT ... ON CONFLICT (id) DO UPDATE`, so a
    row already sitting on one of those ids would be silently OVERWRITTEN
    rather than colliding.

    No caller can choose a segment id today (`SegmentCreateParams` has no
    such field, and `_create_segment_impl`'s keyword is in-process only and
    refuses a collision of its own), so this is not reachable now. It costs
    one query and removes a class of silent overwrite for good; "not
    reachable today" is not a property worth relying on.
    """

    status_code = 409

    def __init__(self, artifact_id: str, taken: list[str]) -> None:
        self.artifact_id = artifact_id
        self.taken = taken
        shown = ", ".join(taken[:5]) + ("..." if len(taken) > 5 else "")
        super().__init__(
            f"converting artifact {artifact_id!r} would write {len(taken)} "
            f"segment id(s) that already exist ({shown}); refusing rather than "
            "overwriting rows this conversion did not make"
        )


class NothingToConvert(ConversionRefusal, ValueError):
    """No artifact on this document carries boxes that are not already rows."""

    status_code = 409

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"document {document_id!r} has no unconverted boxes to convert")


class ArtifactNotOnThisDocument(ConversionRefusal, ValueError):
    """The `artifact_id` given belongs to a different document.

    `ActionRegistry.invoke` checks `document_id` and `artifact_id` as two
    INDEPENDENT targets (`authz.target_ids_from_params`), so an actor
    allowed to write both documents passes both checks while naming a pair
    that does not belong together. Nothing downstream would notice: the
    conversion would run on the named document and the edit on the named
    artifact.
    """

    status_code = 422

    def __init__(self, artifact_id: str, artifact_document_id: str, document_id: str) -> None:
        super().__init__(
            f"artifact {artifact_id!r} belongs to document "
            f"{artifact_document_id!r}, not {document_id!r}"
        )


class SegmentConvertAndEditParams(BaseModel):
    """One document, never a list (`source.store.no-batch-rewrite`).

    There is deliberately no `document_ids`: conversion is lazy, one page at
    a time, on that page's first edit. An eager whole-project conversion, if
    it is ever wanted, is this same action run once per page after a
    snapshot -- which is exactly why the ids it mints are repeatable.

    `edit` is a forward reference: `ArtifactRegionsEditRequest` lives in
    `artifacts.py`, which imports THIS module, so it cannot be imported
    here at module load. `artifacts.py` calls `model_rebuild` once it is
    defined -- the same pattern `ArtifactUpdateActionParams` already uses
    for `ArtifactUpdate`.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    #: The result the Source view was showing when the edit was made. Names
    #: the WORKING pass; it does not narrow what gets converted, because
    #: every result with boxes on this page becomes its own pass.
    artifact_id: str | None = None
    #: The curation edit that TRIGGERED this conversion, in the app's own
    #: shape and unchanged -- positions into the box list it was last
    #: given. Comes WITH `artifact_id` or not at all; with neither, this is
    #: the eager form of A1 (convert, edit nothing).
    edit: "ArtifactRegionsEditRequest | None" = None  # noqa: F821

    @model_validator(mode="after")
    def _artifact_and_edit_travel_together(self) -> "SegmentConvertAndEditParams":
        if (self.edit is None) != (self.artifact_id is None):
            raise ValueError(
                "artifact_id and edit come together or not at all: an edit "
                "with no artifact does not say which result it was made on, "
                "and an artifact with no edit is the eager form, which takes "
                "neither"
            )
        return self


def _artifacts_to_convert(db: Any, document_id: str) -> list[Artifact]:
    """Every result on this page with boxes that is not already rows.

    An artifact whose `ocr_geometry` has an EMPTY box list is left alone: it
    would make a pass with nothing in it, and the seam already answers for
    it as a provisional pass, so converting it would change the answer for
    no gain. (An `add` edit on such an artifact does need a pass to put the
    new box in -- that case arrives with the edit, in step 5.)
    """
    return [
        artifact
        for artifact in db.query(Artifact, document_id=document_id)
        # raw-geometry-ok: the conversion IS the reader of the machine's original
        if artifact.ocr_geometry and artifact.ocr_geometry.boxes
        and not is_converted(artifact)
    ]


def _convert_one(db: Any, artifact: Artifact) -> tuple[SegmentPass, list[Segment]]:
    """One result's boxes become one pass and its rows.

    Reads nothing but the artifact: `segments_from_result` is still the one
    mapping from a block to reads, and `rows_from_reads` the one translation
    from reads to rows. No second mapping exists, which is what makes the
    master test ("conversion changes nothing you can see") provable rather
    than merely hoped for.
    """
    pass_read, segment_reads = segments_from_result(
        document_id=artifact.document_id,
        artifact_id=artifact.id,
        # raw-geometry-ok: the conversion IS the reader of the machine's original
        result=artifact.ocr_geometry,
        provider=artifact.provider,
        model=artifact.model,
        run_id=artifact.run_id,
        created_at=artifact.created_at,
        artifact_type=artifact.artifact_type,
    )
    pass_row, rows = rows_from_reads(pass_read, segment_reads)

    # THE SECOND GUARD, and it is not the primary key (#4924 recon). `save`
    # and `save_many` are `INSERT ... ON CONFLICT (id) DO UPDATE`, so a
    # second conversion would not fail -- it would OVERWRITE, and the
    # overwrite would differ from the first: by then the winner's edit has
    # moved a box, and the loser would write that box back from the block at
    # version 1. A person's edit lost, with nothing raised. The ids are
    # repeatable, so asking whether this exact pass already exists is a
    # complete question, and it is asked INSIDE the transaction.
    existing = db.get(SegmentPass, pass_row.id)
    if existing is not None:
        raise AlreadyConverted(artifact.id, pass_row.id)

    # The SAME guard as the pass's, for the segments (#4924 review round 2).
    # One `query_in` on the id column, not a loop: a dense page is 20,000
    # ids and 20,000 `db.get` calls would cost more than the conversion.
    # Anything found means a row is sitting on an id this conversion is
    # about to write, and `save_many` would overwrite it without a word.
    taken = [row.id for row in db.query_in(Segment, "id", [r.id for r in rows])]
    if taken:
        raise ConvertedIdAlreadyTaken(artifact.id, taken)

    db.save(pass_row)
    # ONE batch, never a row at a time: a dense page is 20,000 rows, and
    # `save_many` joins the ambient transaction rather than opening its own,
    # so the rows and this action's audit row commit or roll back together.
    db.save_many(rows)

    # No `SegmentVersion` rows. Version rows are PREIMAGES -- `SegmentVersion`
    # says so itself ("no row is written at creation") and
    # `snapshot_segment_version` bumps `version` in place -- so writing one
    # here would leave every converted row at version 2 carrying a snapshot
    # of a state nothing ever superseded, and hand the app a stale
    # `expected_version` for a page nobody has edited.

    artifact.geometry_superseded_by_pass_id = pass_row.id
    db.save(artifact)
    return pass_row, rows


#: Every record kind that rests on a PLACE in a source: the four models
#: that carry a `SourceAnchor`.
#:
#: `(kind, model, anchor field, document field)`. The DOCUMENT FIELD is not
#: always `document_id`, and that is not a detail: a `KnowledgeClaim` and a
#: `SourceSupport` are scoped by `source_document_id`, and querying them by
#: `document_id` does not return nothing -- DuckDB refuses the statement
#: outright, because the column does not exist. Slice 4's `_CARRY_MODELS`
#: carries the same third element for the same reason.
#:
#: **SLICE 6 RE-POINTS NOTHING** (ruled 2026-09-20). None of these four has
#: a lasting segment reference to write into. `KnowledgeClaim` does have a
#: `source_segment_id` column, and it is NOT one: it predates the source
#: model, is client-supplied, is published in the API contract, has no
#: engine producer, and its older meaning is an entry in a segmentation
#: artifact's `data["segments"]`. Writing real `Segment` ids into it would
#: merge two meanings in one published column in real research libraries,
#: and "probably empty" is not evidence. So the matcher RUNS and every
#: match is REPORTED; nothing is written to any of the four. The evidence
#: of what WOULD be re-pointed is kept, and it costs nothing to reverse.
#: The three that are ROWS, queryable by their document.
ANCHORED_KINDS: tuple[tuple[str, type, str, str], ...] = (
    ("claim", KnowledgeClaim, "source_anchor", "source_document_id"),
    ("reading", ContentRepresentation, "source_anchor", "document_id"),
    ("annotation", Annotation, "anchor", "document_id"),
)

#: The fourth, `SourceSupport`, IS NOT A ROW. It is an embedded sub-model
#: with no `id` of its own, held in `source_supports` on `KnowledgeClaim`
#: (`models/knowledge.py:1999`) and on `KnowledgeEntity` (`:771`) -- it has
#: no table, and `db.query(SourceSupport, ...)` fails outright ("table
#: sourcesupports does not have a column named id"). So it is walked
#: through its parents, and reported as `<parent id>#<position>`, which is
#: the only honest way to name something with no id.
#:
#: KNOWN GAP, deliberate and reported rather than quietly skipped: only the
#: supports on this document's CLAIMS are walked, not those on ENTITIES. An
#: entity is scoped by `source_document_ids`, a LIST column, so finding the
#: entities that touch one page means scanning every entity in the library
#: -- a real cost on every first edit, for a report that writes nothing.
#: When a lasting segment reference exists to write, that walk can be paid
#: for once; until then it would be paid on every page for no effect.
SOURCE_SUPPORT_PARENTS_WALKED = ("claim",)

NO_SEGMENT_REFERENCE_YET = "no lasting segment reference on this record kind yet"


#: The tolerance `_anchor_matches_segment` allows on each of a rect's four
#: numbers. Kept here as the index's cell size so the two cannot drift: a
#: pair within the tolerance can differ by at most ONE cell on each axis,
#: which is what makes the neighbour probe below exactly equivalent to the
#: nested scan it replaces.
_ANCHOR_TOLERANCE = 1e-6


def _rect_cell(rect: list[float]) -> tuple[int, int, int, int]:
    return tuple(int(round(value / _ANCHOR_TOLERANCE)) for value in rect)  # type: ignore[return-value]


def _index_rows_by_place(rows: list[Segment]) -> dict[tuple, list[Segment]]:
    """Rows filed by `(rendition_id, cell)` so a record's place is a lookup.

    Replaces a nested scan of every anchored record against every row: on
    a dense page that was 20,000 comparisons per record, in Python, INSIDE
    the write transaction with the gate held.
    """
    index: dict[tuple, list[Segment]] = {}
    for row in rows:
        rect = row.anchor.rect
        if rect is None:
            # An undrawable box matches nothing by rect, and
            # `_anchor_matches_segment` says so too (it needs both rects).
            continue
        index.setdefault((row.anchor.rendition_id, _rect_cell(rect)), []).append(row)
    return index


def _row_at(index: dict[tuple, list[Segment]], anchor, matches) -> "Segment | None":
    """The row an anchor rests on, or None.

    Probes the anchor's own cell and its immediate neighbours -- 81 cells
    at most -- because two numbers within the tolerance can land either
    side of a cell boundary. Every candidate is then CONFIRMED with
    `_anchor_matches_segment`, so the answer is exactly the nested scan's,
    never a near miss let through by the index.
    """
    from itertools import product

    if anchor is None or anchor.rect is None:
        return None
    base = _rect_cell(anchor.rect)
    for offsets in product((0, -1, 1), repeat=4):
        cell = tuple(b + o for b, o in zip(base, offsets))
        for row in index.get((anchor.rendition_id, cell), ()):
            if matches(anchor, row):
                return row
    return None


def repointing_report(db: Any, rows: list[Segment]) -> dict[str, Any]:
    """Which anchored records WOULD land on which converted segment.

    Runs the matcher and WRITES NOTHING. Exact matches only -- the same
    rendition and all four rect numbers within 1e-6, via slice 4's
    `_anchor_matches_segment`, which was written for this and says so in
    its own docstring. Imported, never copied: one rule, one place. Never
    by overlap or nearness -- a record that NEARLY matches a box is a
    record about something else, and quietly attaching it would put a
    historian's claim on a line they never cited.

    Returns `{"repointed": [], "not_repointed": [...], "not_repointed_count":
    n}`. `repointed` is empty BY RULING, not by accident (see
    `ANCHORED_KINDS`). THE FULL LIST IS FOR THE RESULT ONLY: `after` is the
    audit row, and a page with two thousand marks on its lines would
    otherwise write two thousand entries into a chain that can never be
    trimmed. The count goes in the chain; the list goes to the caller.
    """
    from fichero_server.api.routes.document.segments import _anchor_matches_segment

    not_repointed: list[dict] = []
    if not rows:
        return {"repointed": [], "not_repointed": [], "not_repointed_count": 0}

    index = _index_rows_by_place(rows)
    document_id = rows[0].document_id

    def report(kind: str, record_id: str, segment_id: str) -> None:
        not_repointed.append({
            "kind": kind,
            "id": record_id,
            "segment_id": segment_id,
            "reason": NO_SEGMENT_REFERENCE_YET,
        })

    for kind, model, anchor_field, doc_field in ANCHORED_KINDS:
        for record in db.query(model, **{doc_field: document_id}):
            match = _row_at(index, getattr(record, anchor_field, None), _anchor_matches_segment)
            if match is not None:
                report(kind, record.id, match.id)
            # The embedded fourth kind, walked through the parent we are
            # already holding (see `SOURCE_SUPPORT_PARENTS_WALKED`).
            if kind == "claim":
                for position, support in enumerate(getattr(record, "source_supports", []) or []):
                    support_match = _row_at(
                        index, getattr(support, "source_anchor", None), _anchor_matches_segment
                    )
                    if support_match is not None:
                        report("source_support", f"{record.id}#{position}", support_match.id)

    return {
        "repointed": [],
        "not_repointed": not_repointed,
        "not_repointed_count": len(not_repointed),
    }


def _convert_execute(
    db: Any, params: SegmentConvertAndEditParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """`segment.convert_and_edit` -- one audited, atomic, undoable step.

    Every read below happens inside the registry's `db.transaction()`, and
    the FIRST of them takes the transaction gate (any `db.get` does), which
    is what makes the converted/not-converted look serialised rather than a
    guess two racing requests can both win.
    """
    audit_id = uuid.uuid4().hex

    # FIRST read inside the transaction: takes the gate and holds it to
    # COMMIT, so everything below sees one consistent world.
    document = db.get(Document, params.document_id)
    if document is None:
        raise DocumentNotFound(params.document_id)

    working_artifact = None
    if params.artifact_id is not None:
        working_artifact = db.get(Artifact, params.artifact_id)
        if working_artifact is None:
            raise ArtifactNotFound(params.artifact_id)
        # The permission layer checked `document_id` and `artifact_id` as two
        # INDEPENDENT targets, so a mismatched pair reaches here allowed.
        if working_artifact.document_id != params.document_id:
            raise ArtifactNotOnThisDocument(
                working_artifact.id, working_artifact.document_id, params.document_id
            )
        # A working artifact that is ALREADY converted is not an error when
        # an edit came with it: this is the ordinary second and later edit
        # of a page, and it is the same branch a REDO takes (the page is
        # still converted by then, so only the edit is re-applied). It is
        # also how the losing side of a race lands: it re-read the marker
        # inside this transaction, found it set, and simply edits the rows
        # the winner made -- the routing decision made again on fresh
        # state, not a fallback. With no edit there is genuinely nothing
        # left to do, and that is said.
        if is_converted(working_artifact) and params.edit is None:
            raise AlreadyConverted(
                working_artifact.id, working_artifact.geometry_superseded_by_pass_id or ""
            )

    artifacts = _artifacts_to_convert(db, params.document_id)
    if not artifacts and params.edit is None:
        raise NothingToConvert(params.document_id)

    pass_ids: list[str] = []
    artifact_ids: list[str] = []
    all_rows: list[Segment] = []
    for artifact in artifacts:
        pass_row, rows = _convert_one(db, artifact)
        pass_ids.append(pass_row.id)
        artifact_ids.append(artifact.id)
        all_rows.extend(rows)

    # THE TRIGGERING EDIT, applied in this same transaction and this same
    # audited action -- one audit row, one undo step.
    edit_record = None
    choice_id = None
    if params.edit is not None and working_artifact is not None:
        working = db.get(Artifact, working_artifact.id)
        if not is_converted(working):
            # The working result had no boxes to convert (an empty geometry,
            # or none at all) and the edit is an `add`: bootstrap the one
            # empty pass so the new box has somewhere to live -- today's
            # "bootstraps an empty user geometry", in the new store.
            working_pass = _bootstrap_empty_pass(db, working)
            pass_ids.append(working_pass.id)
            if working.id not in artifact_ids:
                artifact_ids.append(working.id)
        else:
            working_pass = converted_pass_of(db, working)
        edit_record = apply_edit_to_segments(
            db, working_pass, working.id, params.edit, ctx
        )
        choice_id = _record_working_pass(db, working_pass, ctx)

    report = repointing_report(db, all_rows)

    # THE AUDIT PAYLOAD: counts and ids only, nothing that grows with the
    # page. Not the segment ids -- a dense page is 20,000 of them, and they
    # are repeatable from `artifact_ids` anyway -- and not the
    # `not_repointed` LIST, because `after` IS the audit row and a page
    # with two thousand marks on its lines would write two thousand entries
    # into a chain that can never be trimmed.
    after = {
        "pass_ids": pass_ids,
        "artifact_ids": artifact_ids,
        "segment_count": len(all_rows),
        "repointed_count": len(report["repointed"]),
        "not_repointed_count": report["not_repointed_count"],
        "working_artifact_id": params.artifact_id,
        "choice_id": choice_id,
        # What the matching slice 5 action recorded for itself. The inverse
        # is worked out from THIS, by that action's own `invert`.
        "edit": edit_record,
    }
    # THE RESULT: what the caller gets back, where the full list belongs.
    # It is answered once and never stored.
    result = {
        **after,
        "repointed": report["repointed"],
        "not_repointed": report["not_repointed"],
    }
    spec = ChangeSpec(
        domains=["segment", "artifact", "document"],
        target_ids=[params.document_id, *artifact_ids],
        before={"document_id": params.document_id, "converted_artifact_ids": []},
        after=after,
        audit_id=audit_id,
        emit_type="segment.converted",
        # No `segment_ids` for the converted boxes, for the same reason
        # `after` carries none: the app re-reads the page on this event.
        pass_ids=pass_ids,
        artifact_ids=artifact_ids,
        document_ids=[params.document_id],
        # No `segment_ids` for the converted boxes -- the app re-reads the
        # page on `segment.converted` -- but the EDIT's own touched ids are
        # listed, so a store that patches items in place can find them.
        segment_ids=list(edit_record.get("segment_ids") or []) if edit_record else [],
    )
    return result, spec


def _invert_convert(before: dict | None, after: dict | None, ctx: ActionContext):
    """Undo the EDIT, keep the conversion (`source.store.undo-first-edit-keeps-conversion`).

    Returns `None` when there is no edit to undo -- which is every
    invocation until step 5. `None` is the undo route's own word for "this
    has no inverse", and it answers it with a clean 409; RAISING here
    instead would make the history list a conversion as undoable and then
    500 when somebody pressed it.

    The conversion itself is deliberately NOT undone. Reversing it would
    need the only hard delete in the segment store, of up to 20,000 rows
    and their versions, behind a "has anything depended on these since"
    test that cannot be written simply -- and when that test said no, a
    person's FIRST edit could not be undone at all, which is the worst
    outcome on the table. Keeping the conversion costs nothing anyone can
    see: that is exactly what the master test states. A true unconvert can
    still be added later as its own owner-only action, precisely because
    the ids are repeatable.
    """
    edit = (after or {}).get("edit")
    if not edit:
        return None
    # DELEGATED, never re-derived: the inverse of a first edit is the
    # matching slice 5 action's OWN inverse, worked out from the record
    # that action made for itself. Move becomes an update back to the
    # recorded geometry at the recorded version; delete becomes undelete;
    # add becomes delete; combine becomes unmerge. Slice 5's review
    # required an inverse to read only `after`, and this keeps that true
    # through conversion -- there is no second set of inverse rules here.
    # Most edits DELEGATE: the inverse of a first edit is the matching
    # slice 5 action's own inverse, worked out from the record that action
    # made for itself. One edit cannot -- a combine is two steps, and the
    # merge's inverse undoes only one of them -- so it names its inverse
    # outright. Still no second set of inverse rules: `segment.uncombine`
    # is built from `unmerge`'s and `restore_version`'s own internals.
    explicit = edit.get("inverse")
    if explicit:
        return explicit["action"], explicit["params"]
    reg = registry.get(edit["action"])
    if reg.invert is None:
        return None
    return reg.invert(edit.get("before"), edit.get("after"), ctx)


class NothingToUndo(ConversionRefusal, ValueError):
    """A conversion with no edit attached has nothing to undo.

    Refused rather than quietly succeeding: "undone" must never mean
    "nothing happened, and nothing will tell you".
    """

    status_code = 409

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(
            f"the conversion of document {document_id!r} carried no edit, and a "
            "conversion by itself is not undone (source.store."
            "undo-first-edit-keeps-conversion)"
        )


class DocumentNotFound(ConversionRefusal, ValueError):
    status_code = 404

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document not found: {document_id}")


class ArtifactNotFound(ConversionRefusal, ValueError):
    status_code = 404

    def __init__(self, artifact_id: str) -> None:
        super().__init__(f"Artifact not found: {artifact_id}")


action(
    "segment.convert_and_edit",
    SegmentConvertAndEditParams,
    domains=["segment", "artifact", "document"],
    undoable=True,
    invert=_invert_convert,
    # ONE transaction across several artifacts. A nested failure marks it
    # `rollback_only` and the outermost level rolls back and raises, so a
    # half-converted page cannot exist.
    atomic=True,
    # #4957: on redo, work from THIS action's own recorded `after` rather
    # than replaying its params. Replay would re-run the conversion branch,
    # and the edit it carries (step 5) can MINT a row -- the exact defect
    # class that fix exists for.
    redo_via_own_invert=True,
)(_convert_execute)


# ---------------------------------------------------------------------------
# Step 5 -- the edit half: the app's box POSITIONS become segment actions
# ---------------------------------------------------------------------------


class TextNeedsReadings(ConversionRefusal, ValueError):
    """An `add` carrying typed text on a converted page.

    After conversion there is nowhere lawful to keep it. Not the block --
    that is the machine's own record and is never written again. Not the
    audit chain, which carries ids and numbers. And a `metadata["text"]` on
    the row would be a second home for words that slice 8 then has to move
    row by row, which is the one thing the source model is built to avoid.

    Refused until readings hang on segments. The app never sends typed text
    on add today: both `addRegion` call sites take the empty default (the
    rubber-band draw and the word-promote), and the one region text field
    names a child document, not a box. So this refuses nothing a person can
    currently do.
    """

    status_code = 422

    def __init__(self) -> None:
        super().__init__(
            "a region added to a converted page cannot carry text yet: a "
            "segment's words live in readings, which arrive in a later slice "
            "(#4924). Draw the region, then transcribe it"
        )


class RegionIndexOutOfRange(ConversionRefusal, ValueError):
    """The app named a box position this page does not have.

    Positions come from the list the app was last given, and a page can
    change under it. Typed rather than an IndexError, so a client can tell
    "your view is stale" from "something broke".
    """

    status_code = 422

    def __init__(self, index: int, count: int) -> None:
        self.index = index
        super().__init__(
            f"region index {index} is out of range (this page has {count} boxes)"
        )


def _rows_for_indices(rows: list[Segment], indices: list[int]) -> list[Segment]:
    """The app's POSITIONS resolved against the one live order.

    Never `metadata["box_index"]` directly: after a delete the app's
    positions shift and the stored box indexes do not, so the stored number
    is a sort key and nothing else. `live_rows_in_order` is the single
    ordering both this and the projection use, which is what keeps the
    app's "position N" and the engine's row N the same row.
    """
    picked = []
    for index in indices:
        if index < 0 or index >= len(rows):
            raise RegionIndexOutOfRange(index, len(rows))
        picked.append(rows[index])
    return picked


# A box drawn AFTER conversion gets an ordinary `_new_id()`, not a
# repeatable one (#4924 step 5 review). A repeatable id bought nothing
# here -- an eager conversion has no add, and redo of an add is an
# UNDELETE of the same row, so the id already comes back -- and the only
# scheme available could wedge: it counted every segment ever made in the
# pass, and that count FALLS when `unsplit` hard-deletes parts, so after
# an undone split an add lands on a taken id and every later add on that
# pass is refused. The collision refusal inside `_create_segment_impl`
# stays: it is what makes a taken id a refusal rather than an overwrite.


def _union_rect(rects: list[list[float]]) -> list[float]:
    xs0 = [r[0] for r in rects]
    ys0 = [r[1] for r in rects]
    xs1 = [r[0] + r[2] for r in rects]
    ys1 = [r[1] + r[3] for r in rects]
    x, y = min(xs0), min(ys0)
    return [x, y, max(xs1) - x, max(ys1) - y]


def _bootstrap_empty_pass(db: Any, artifact: Artifact) -> SegmentPass:
    """The one empty pass for a result with no boxes, so a newly drawn
    region has somewhere to live.

    Today's `_edit_regions_impl` does the same thing in the old store: an
    `add` on an artifact with no geometry bootstraps an empty
    `OCRGeometryResult(provider="user")`. This is that, in the new store.
    The pass takes the SAME repeatable id it would have taken had the
    artifact carried boxes, so a page bootstrapped this way and a page
    converted normally cannot end up with different ids for the same
    result.
    """
    pass_row = SegmentPass(
        id=converted_pass_id(artifact.id),
        document_id=artifact.document_id,
        name=artifact.artifact_type,
        provenance_kind=derive_pass_provenance_kind(
            provider=artifact.provider, model=artifact.model
        ),
        actor=None,
        provider=artifact.provider,
        model=artifact.model,
        run_id=artifact.run_id,
        source_artifact_id=artifact.id,
        created_at=artifact.created_at,
    )
    existing = db.get(SegmentPass, pass_row.id)
    if existing is not None:
        raise AlreadyConverted(artifact.id, pass_row.id)
    db.save(pass_row)
    artifact.geometry_superseded_by_pass_id = pass_row.id
    db.save(artifact)
    return pass_row


def _record_working_pass(db: Any, pass_row: SegmentPass, ctx: ActionContext) -> str:
    """Record that this is the pass the person was working on.

    A page accumulates passes -- a machine run after conversion adds
    another -- so "which one am I looking at" would otherwise be guessed
    from dates. The edit that triggered the conversion names the result the
    Source view was showing, and that is worth keeping.

    A later choice SUPERSEDES an earlier one rather than replacing it:
    rows are never deleted, so what somebody was working on stays readable.
    """
    from fichero_server.core.timeutil import utc_now

    now = utc_now()
    for previous in db.query(SegmentPassChoice, document_id=pass_row.document_id):
        if previous.superseded_at is None and previous.pass_id != pass_row.id:
            previous.superseded_at = now
            db.save(previous)
    existing = next(
        (
            row for row in db.query(SegmentPassChoice, document_id=pass_row.document_id)
            if row.pass_id == pass_row.id and row.superseded_at is None
        ),
        None,
    )
    if existing is not None:
        return existing.id
    choice = SegmentPassChoice(
        document_id=pass_row.document_id, pass_id=pass_row.id, chosen_by=ctx.actor,
    )
    db.save(choice)
    return choice.id


def apply_edit_to_segments(
    db: Any, pass_row: SegmentPass, artifact_id: str, edit: Any, ctx: ActionContext
) -> dict:
    """One region edit, as the app sends it, applied to segment rows.

    Called from INSIDE `segment.convert_and_edit`'s own transaction, never
    through `registry.invoke`: a nested invoke would write a second audit
    row, and the whole point is one audited action and one undo step. The
    slice 5 actions' `execute` callables are used exactly as they are --
    they return `(result, ChangeSpec)` and write no audit row of their own
    -- so there is no second code path and no copy of their rules.

    Returns what `after["edit"]` records: the action's name and its own
    `before`/`after`, which is precisely what that action's `invert` reads.
    So undoing a first edit is that action's own inverse, worked out from
    its own record -- slice 5's review required an inverse to read only
    `after`, and this keeps that true through conversion.
    """
    from fichero_server.api.routes.document.artifacts import RegionEditOp
    from fichero_server.api.routes.document.segments import (
        SegmentCreateParams,
        SegmentDeleteParams,
        SegmentMergeParams,
        SegmentUpdateParams,
        _action_merge,
        _action_segment_delete,
        _action_segment_update,
        _create_segment_impl,
    )

    rows = live_rows_in_order(db, pass_row.id)
    indices = list(dict.fromkeys(edit.indices))  # dedupe, keep order -- as today

    def anchor_for(rect: list[float], like: SourceAnchor | None = None) -> SourceAnchor:
        """A rect the app sent, as an anchor -- refused with the SAME 422
        the old route gave when it is not a drawable place.

        `SourceAnchor` validates a rect more strictly than `OCRGeometryBox`
        does, and a raw pydantic `ValidationError` from deep inside an
        action is a 500. The old route answered 422 for an out-of-bounds
        box and must keep doing so.
        """
        from pydantic import ValidationError

        try:
            if like is not None:
                return like.model_copy(update={"rect": list(rect)}, deep=True).model_validate(
                    like.model_copy(update={"rect": list(rect)}).model_dump()
                )
            return SourceAnchor(document_id=pass_row.document_id, rect=list(rect))
        except ValidationError as exc:
            raise RegionEditShapeRefused(f"invalid region box: {exc}") from exc

    def run(execute, params) -> dict:
        _result, spec = execute(db, params, ctx)
        return {"before": spec.before, "after": spec.after, "segment_ids": spec.segment_ids}

    if edit.op is RegionEditOp.MOVE:
        if len(indices) != 1 or edit.bbox is None:
            raise RegionEditShapeRefused("move needs exactly one index and a bbox")
        row = _rows_for_indices(rows, indices)[0]
        recorded = run(
            _action_segment_update,
            SegmentUpdateParams(
                segment_id=row.id,
                expected_version=row.version,
                anchor=anchor_for(edit.bbox, like=row.anchor),
            ),
        )
        return {"action": "segment.update", **recorded}

    if edit.op is RegionEditOp.DELETE:
        if not indices:
            raise RegionEditShapeRefused("delete needs at least one index")
        picked = _rows_for_indices(rows, indices)
        recorded = run(
            _action_segment_delete,
            SegmentDeleteParams(
                segment_ids=[r.id for r in picked],
                expected_versions={r.id: r.version for r in picked},
            ),
        )
        return {"action": "segment.delete", **recorded}

    if edit.op is RegionEditOp.ADD:
        if edit.bbox is None:
            raise RegionEditShapeRefused("add needs a bbox")
        if (edit.text or "").strip():
            raise TextNeedsReadings()
        segment = _create_segment_impl(
            db,
            SegmentCreateParams(
                document_id=pass_row.document_id,
                pass_id=pass_row.id,
                kind=str(edit.level),
                anchor=anchor_for(edit.bbox).model_copy(
                    update={"granularity": str(edit.level)}
                ),
            ),
            ctx,
        )
        return {
            "action": "segment.create",
            "before": None,
            "after": {"segment_ids": [segment.id]},
            "segment_ids": [segment.id],
        }

    if edit.op is RegionEditOp.COMBINE:
        if len(indices) < 2:
            raise RegionEditShapeRefused("combine needs at least two indices")
        picked = _rows_for_indices(rows, indices)
        # THE KEPT ONE IS THE MEMBER AT THE LOWEST POSITION, so it keeps its
        # own id and its own `box_index` and therefore sorts into exactly
        # the slot today's `keep_at = min(indices)` puts the merged box in.
        # `_action_merge` leaves the kept row's shape untouched, so the
        # union is a second step below, in this same action.
        keep = min(picked, key=lambda r: rows.index(r))
        merged = run(
            _action_merge,
            SegmentMergeParams(
                segment_ids=[r.id for r in picked],
                keep_id=keep.id,
                expected_versions={r.id: r.version for r in picked},
            ),
        )
        # Now make the kept segment what today's combine produces: the union
        # rectangle, the members' char span, the members' box indexes for
        # the joined text, and the person's own.
        keep_row = db.get(Segment, keep.id)
        member_indexes = [
            r.metadata.get("box_index") for r in picked
            if isinstance(r.metadata.get("box_index"), int)
        ]
        rects = [r.anchor.rect for r in picked if r.anchor.rect is not None]
        starts = [r.anchor.char_start for r in picked]
        ends = [r.anchor.char_end for r in picked]
        anchor_update: dict = {}
        if rects:
            anchor_update["rect"] = _union_rect(rects)
        if all(v is not None for v in starts) and all(v is not None for v in ends):
            anchor_update["char_start"] = min(starts)
            anchor_update["char_end"] = max(ends)
        # The combined KIND, by today's rule: the members' own level when
        # they agree, `region` when they do not -- a combination of a word
        # and a line is a passage, not a word.
        levels = {r.kind for r in picked}
        combined_kind = next(iter(levels)) if len(levels) == 1 else "region"
        shaped = run(
            _action_segment_update,
            SegmentUpdateParams(
                segment_id=keep_row.id,
                expected_version=keep_row.version,
                anchor=keep_row.anchor.model_copy(
                    update={**anchor_update, "granularity": combined_kind}
                ),
                kind=combined_kind,
            ),
        )
        # `member_box_indexes` is what the read side joins the members'
        # texts from. Written straight onto the row: it is not geometry, so
        # it is not part of the update action's compare-and-set.
        reshaped = db.get(Segment, keep_row.id)
        metadata = dict(reshaped.metadata)
        existing = metadata.get("member_box_indexes") or []
        metadata["member_box_indexes"] = sorted(set(existing) | set(member_indexes))
        reshaped.metadata = metadata
        db.save(reshaped)
        # THE INVERSE IS ITS OWN, not the merge's. A combine is merge PLUS
        # this reshape, and `segment.unmerge` never touches the kept row --
        # it restores only the absorbed segments, because merge never
        # touched the kept row either. Undoing with unmerge alone left the
        # kept box shaped as the union, still reading all the joined words,
        # sitting on top of the boxes it swallowed. So combine names
        # `segment.uncombine`, which does all three steps in one action.
        #
        # Every number below is READ FROM WHAT THE FORWARD STEPS RECORDED,
        # never recomputed: `merged["after"]` for the members,
        # `shaped["before"]` for the version the reshape superseded.
        reshaped_now = db.get(Segment, keep_row.id)
        return {
            "action": "segment.merge",
            **merged,
            "reshaped": {"segment_id": keep_row.id, "after": shaped["after"]},
            "inverse": {
                "action": "segment.uncombine",
                "params": {
                    "versions": merged["after"]["absorbed_versions"],
                    "expected_versions": {
                        segment_id: version
                        for segment_id, version in merged["after"]["versions"].items()
                        if segment_id != keep_row.id
                    },
                    "keep_id": keep_row.id,
                    # The version the reshape superseded: `segment.update`
                    # writes its preimage AT that number and bumps past it.
                    "keep_version": shaped["before"]["version"],
                    "keep_expected_version": (
                        reshaped_now.version if reshaped_now is not None else keep_row.version
                    ),
                    "member_box_indexes_added": member_indexes,
                },
            },
        }

    raise RegionEditShapeRefused(f"unknown region edit op: {edit.op!r}")


class RegionEditShapeRefused(ConversionRefusal, ValueError):
    """The edit's own shape is wrong (a move with two indices, an add with
    no bbox). Same refusals `_edit_regions_impl` makes today, kept typed so
    they map to a 422 rather than a 500 wherever the action is reached."""

    status_code = 422


class SegmentUncombineParams(BaseModel):
    """The inverse of ONE combine, which is two steps and so needs its own.

    A combine is `segment.merge` PLUS a reshape of the kept segment to the
    union (rectangle, char span, kind) and the `member_box_indexes` that
    give it the members' joined words. `segment.unmerge` undoes only the
    merge: it restores the ABSORBED segments and never touches the kept
    row, because `segment.merge` never touched it either. Undoing a
    combine with unmerge alone therefore brought the swallowed boxes back
    UNDERNEATH a kept box still shaped as the union and still reading all
    their words -- the page not as it was, with nothing raised.
    """

    model_config = ConfigDict(extra="forbid")

    #: Handed straight to `segment.unmerge`.
    versions: dict[str, int]
    expected_versions: dict[str, int]
    #: The kept segment, and the version the reshape superseded -- the
    #: number `segment.update` recorded in its own `before`, so this reads
    #: only what the forward step wrote down.
    keep_id: str
    keep_version: int
    keep_expected_version: int
    #: EXACTLY the indexes this combine added, so combining twice and
    #: undoing once removes only the second combine's members and leaves
    #: the first's.
    member_box_indexes_added: list[int] = Field(default_factory=list)


def _action_uncombine(db: Any, params: SegmentUncombineParams, ctx: ActionContext):
    """Put a combined segment and its members back, in one action.

    Three steps, no new rules: `segment.unmerge`'s own internals bring the
    absorbed segments back, `segment.restore_version`'s bring the kept
    segment's shape back to the version the reshape superseded, and the
    member list this combine added is removed from the kept row's
    metadata -- which has to be done here because `metadata` is not part of
    `SegmentVersion`, so restoring a version does not clear it.

    `undoable=False`, like `segment.unmerge`: this IS an inverse. Redoing
    the combine is the outer action's replay, not this action's inverse.
    """
    from fichero_server.api.routes.document.segments import (
        SegmentRestoreVersionParams,
        SegmentUnmergeParams,
        _action_segment_restore_version,
        _action_unmerge,
    )

    _unmerged, unmerge_spec = _action_unmerge(
        db,
        SegmentUnmergeParams(
            versions=params.versions, expected_versions=params.expected_versions
        ),
        ctx,
    )
    _restored, restore_spec = _action_segment_restore_version(
        db,
        SegmentRestoreVersionParams(
            segment_id=params.keep_id,
            version=params.keep_version,
            expected_version=params.keep_expected_version,
        ),
        ctx,
    )

    # The joined words go with the shape. `metadata` is not versioned, so
    # nothing else would have cleared it.
    keep_row = db.get(Segment, params.keep_id)
    if keep_row is not None and params.member_box_indexes_added:
        metadata = dict(keep_row.metadata)
        remaining = [
            index for index in (metadata.get("member_box_indexes") or [])
            if index not in set(params.member_box_indexes_added)
        ]
        if remaining:
            metadata["member_box_indexes"] = remaining
        else:
            metadata.pop("member_box_indexes", None)
        keep_row.metadata = metadata
        db.save(keep_row)

    touched = list(dict.fromkeys(
        [*unmerge_spec.segment_ids, *restore_spec.segment_ids, params.keep_id]
    ))
    spec = ChangeSpec(
        domains=["segment"],
        target_ids=touched,
        before=None,
        after={"segment_ids": touched, "kept_id": params.keep_id},
        emit_type="segment.updated",
        segment_ids=touched,
        pass_ids=list(dict.fromkeys([*unmerge_spec.pass_ids, *restore_spec.pass_ids])),
        document_ids=list(dict.fromkeys(
            [*unmerge_spec.document_ids, *restore_spec.document_ids]
        )),
    )
    return {"segment_ids": touched}, spec


action(
    "segment.uncombine",
    SegmentUncombineParams,
    domains=["segment"],
    # An INVERSE, like `segment.unmerge`: it is what undo runs, not
    # something undo is run on.
    undoable=False,
)(_action_uncombine)


# ---------------------------------------------------------------------------
# Slice 6b (#4990) -- a mark follows its line when the line's box moves
# ---------------------------------------------------------------------------


def _anchor_matches_box(anchor: SourceAnchor, box: OCRGeometryBox, block_frame: str | None) -> bool:
    """Slice 4's one matching rule, against a BLOCK box rather than a row.

    Same tolerance on all four numbers and the same frame test as
    `_anchor_matches_segment`, because it is the same question asked of the
    other store. Never by overlap or nearness: a rectangle that NEARLY
    matches a box is about something else, and moving a historian's mark
    onto a line they never marked is worse than leaving it where they put it.
    """
    if anchor.rect is None:
        return False
    if anchor.rendition_id != block_frame:
        return False
    return all(abs(a - b) <= _ANCHOR_TOLERANCE for a, b in zip(anchor.rect, box.bbox))


def resolve_anchor(db: Any, anchor: SourceAnchor | None) -> ResolvedAnchor | None:
    """The one resolver every mark reader calls (#4990).

    Pure apart from its reads, writes nothing, and rewrites no stored
    anchor. Returns `None` only when there is no anchor at all, so a caller
    can pass whatever it holds.

    Only anchors that matched a box EXACTLY are helped, which is exactly
    the set slice 6 would have re-pointed. A mark drawn free stays where it
    was drawn.

    SOURCE-MODEL SLICE 8 (#4932): an anchor may now NAME its segment
    outright (`SourceAnchor.segment_id`), and when it does that is the answer
    -- no rectangle matching at all. A recorded fact beats a recovered one,
    and it is also the only thing that works for a segment that never came
    from a converted artifact. The rectangle path below stays for every
    anchor written before this slice, which is almost all of them.
    """
    if anchor is None:
        return None

    if anchor.segment_id:
        named = db.get(Segment, anchor.segment_id)
        if named is None:
            # The anchor names a segment that is not there. NOT silently
            # downgraded to a rectangle guess: the pointer was explicit, so
            # being unable to follow it is a fact the caller must see.
            return ResolvedAnchor(anchor=anchor, basis=AnchorBasis.stored)
        if named.deleted_at is not None:
            return ResolvedAnchor(
                anchor=anchor, basis=AnchorBasis.segment_deleted, segment_id=named.id
            )
        return ResolvedAnchor(
            anchor=named.anchor, basis=AnchorBasis.segment_named, segment_id=named.id
        )

    if anchor.rect is None or not anchor.document_id:
        return ResolvedAnchor(anchor=anchor, basis=AnchorBasis.stored)

    for artifact in db.query(Artifact, document_id=anchor.document_id):
        if not is_converted(artifact):
            continue
        # raw-geometry-ok: the kept block IS the permanent rectangle-to-position table
        block = artifact.ocr_geometry
        if block is None:
            continue
        position = next(
            (
                index for index, box in enumerate(block.boxes)
                if _anchor_matches_box(anchor, box, block.rendition_id)
            ),
            None,
        )
        if position is None:
            continue
        segment = db.get(Segment, converted_segment_id(artifact.id, position))
        if segment is None:
            # The block remembers the box, but no row was ever made for it
            # (or it was removed outright). Nothing to follow.
            continue
        if segment.deleted_at is not None:
            return ResolvedAnchor(
                anchor=anchor,
                basis=AnchorBasis.segment_deleted,
                segment_id=segment.id,
            )
        return ResolvedAnchor(
            anchor=segment.anchor,
            basis=AnchorBasis.segment,
            segment_id=segment.id,
        )

    return ResolvedAnchor(anchor=anchor, basis=AnchorBasis.stored)
