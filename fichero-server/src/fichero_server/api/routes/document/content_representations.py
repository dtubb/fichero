"""Audited content-representation revision actions (#3443), and source-model
slice 8's reading actions (#4934, #4929, #4932).

A READING IS A `ContentRepresentation`. There is no second store of readings:
see the module docstring of `models/readings.py` for what lives where, and
`api/routes/document/segment_readings.py` for the READ seam that answers from
both this table and the artifacts where the engine's text still lives.
"""

from __future__ import annotations

import hashlib
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import APIRouter, Depends, HTTPException

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import (
    ContentRepresentation,
    ContentRepresentationListResponse,
    ContentRepresentationRevision,
    ContentRepresentationRevisionListResponse,
)
from fichero_server.models.geo import WORLD_POINT, world_point_content
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.source_declarations import assert_known_script
from fichero_server.models.readings import (
    ChoiceNeedsAPerson,
    ReadingAnchorMismatch,
    ReadingChoice,
    UnknownReadingKind,
    UnknownReadingLevel,
    assert_known_reading_kind,
    assert_known_reading_level,
    canonical_reading_kind_and_level,
    counting_level,
    reading_kind_filter,
)
from fichero_server.models.segments import (
    ProvisionalSegmentIdError,
    Segment,
    SegmentPass,
    SegmentPassChoice,
    SegmentVersion,
    assert_not_provisional,
    snapshot_segment_version,
    primary_live_segment_id,
    resolve_segment,
)
from fichero_server.core.off_loop import off_loop

router = APIRouter(prefix="/content-representations")


class RepresentationRevisionParams(BaseModel):
    """A revision's params. Its `content` is audited in full, unchanged from
    before slice 8: this action predates the digest rule and changing what an
    existing audit chain records would make old rows and new rows mean
    different things. New writes go through `representation.create`."""

    #: `extra="forbid"` since source-model slice 8 (#4934): a params model is
    #: the boundary where a client could smuggle in `provenance_kind` and be
    #: recorded as a person. Forbidding extras is what makes "engine-set"
    #: true rather than merely intended.
    model_config = ConfigDict(extra="forbid")

    representation_id: str
    content: str = Field(min_length=1)
    decision: str | None = None


@action(
    "representation.revise",
    RepresentationRevisionParams,
    domains=["representation"],
    undoable=False,
)
def revise_representation(
    db: Database,
    params: RepresentationRevisionParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Create a user revision without changing the source representation."""
    representation = db.get(ContentRepresentation, params.representation_id)
    if representation is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    revision = ContentRepresentationRevision(
        representation_id=representation.id,
        content=params.content,
        reviewer=ctx.actor,
        # Source-model slice 8 (#4934): the honest answer, worked out from HOW
        # the write arrived, not from what the caller said. `reviewer` above
        # still records the actor name; this records what kind of thing it was.
        provenance_kind=provenance_kind_from_ctx(ctx),
        decision=params.decision,
    )
    db.save(revision)
    snapshot = revision.model_dump(mode="json")
    return snapshot, ChangeSpec(
        domains=["representation"],
        target_ids=[representation.id, revision.id],
        before=None,
        after=snapshot,
        emit_type="representation.revised",
        document_ids=[representation.document_id],
    )


@router.get("/document/{document_id}", response_model=ContentRepresentationListResponse)
async def list_representations(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> ContentRepresentationListResponse:
    items = db.query(ContentRepresentation, document_id=document_id)
    return ContentRepresentationListResponse(items=items, count=len(items))


@router.get(
    "/{representation_id}/revisions",
    response_model=ContentRepresentationRevisionListResponse,
)
@off_loop
def list_revisions(
    representation_id: str,
    db: Database = Depends(get_library_database),
) -> ContentRepresentationRevisionListResponse:
    if db.get(ContentRepresentation, representation_id) is None:
        raise HTTPException(404, f"Content representation not found: {representation_id}")
    items = db.query(ContentRepresentationRevision, representation_id=representation_id)
    return ContentRepresentationRevisionListResponse(items=items, count=len(items))


@router.post("/{representation_id}/revisions", response_model=ContentRepresentationRevision)
async def create_revision(
    representation_id: str,
    payload: RepresentationRevisionParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ContentRepresentationRevision:
    result = registry.invoke(
        db,
        "representation.revise",
        {**payload.model_dump(), "representation_id": representation_id},
        ctx,
    )
    return ContentRepresentationRevision.model_validate(result.result)


# ===========================================================================
# Source-model slice 8 (#4934, #4929, #4932) — a reading is a written record
#
# Spec: `build-notes-readings-cascade-orders.md`, "Slice 8", section
# "Actions". Every params model below is `extra="forbid"` and carries NO `id`
# and NO `provenance_kind`: the engine decides who made a reading, from how
# the write arrived (#4868, #4869).
#
# WHAT THE AUDIT ROW MAY CARRY. `after` is `{representation_id, segment_id,
# kind, content_sha256}` — an id and a digest, NEVER the text. The audit chain
# is not a second copy of the edition: a person's transcription of a line
# belongs in the row they wrote, once, and the undo of a create is a
# RETRACTION, which needs no content to perform. A digest still proves which
# text the action wrote, which is the honest purpose of putting it there.
# ===========================================================================


def _content_sha256(content: str) -> str:
    """The digest that stands in for the text in an audit row."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _as_http_error(exc: Exception) -> HTTPException:
    """Typed refusals as 4xx, so a caller sees a refusal, not a crash."""
    if isinstance(exc, HTTPException):
        return exc  # already a refusal with its status (the stale 409 carries its own detail)
    if isinstance(exc, ProvisionalSegmentIdError):
        return HTTPException(422, str(exc))
    if isinstance(exc, (UnknownReadingKind, UnknownReadingLevel, ReadingAnchorMismatch)):
        return HTTPException(422, str(exc))
    if isinstance(exc, ChoiceNeedsAPerson):
        return HTTPException(403, str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(500, str(exc))


def _refuse_if_the_counting_reading_moved(
    db: Database, params: RepresentationCreateParams, segment: Segment | None
) -> None:
    """The compare-and-set of a reading write (`source.textedit.stale-keeps-your-words`).

    Readings are immutable and several coexist, so what can move under a writer is WHICH ONE COUNTS
    (a correction or a choice made meanwhile). The writer says which counted when it read; if another
    counts now, the write is refused -- 409, naming the reading that counts now and its text, so the
    writer can offer keep-mine / take-theirs / compare -- and NOTHING is written. The typed words stay
    with the writer; the engine never keeps a half-applied edit.
    """
    if segment is None:
        raise HTTPException(status_code=422, detail="expected_counting_id needs the segment_id whose counting reading it names")
    refuse_if_counting_moved(db, segment, params.kind, params.level, params.expected_counting_id)


def refuse_if_counting_moved(db: Database, segment: Segment, kind: str, level: str | None, expected: str | None) -> None:
    """409 (naming the reading that counts now) unless `expected` is the reading that counts for this kind at this level."""
    from fichero_server.api.routes.document.segment_readings import counting_by_kind_and_level, readings_of_segment

    items = readings_of_segment(db, segment.id)
    # The reading that counts AT THE LEVEL being written (`source.reading.counts-per-level`): an expanded
    # reading written against the as-written one that counts is not stale because of it.
    answer = counting_by_kind_and_level(db, segment.id, items).get((kind, counting_level(level)))
    current = answer.representation_id if answer is not None else None
    if current == expected:
        return
    text = next((item.content for item in items if item.id == current), None)
    raise HTTPException(status_code=409, detail={
        "reason": "stale",
        "message": (f"another {kind} counts for this segment now; nothing was written. "
                    "Keep yours (write again against the one that counts), take theirs, or compare."),
        "segment_id": segment.id,
        "kind": kind,
        "expected_counting_id": expected,
        "counting_representation_id": current,
        "counting_text": text,
    })


def _live_segment(db: Database, segment_id: str) -> Segment:
    """The segment a write names, refusing a provisional id.

    `source.seam.provisional-ids-refused`: a `legacy:` id names a POSITION in
    today's geometry blob, and a reading hung on one would point at something
    that moves the next time the page is re-run. Resolved through
    `resolve_segment` so a reading written against an id that has since been
    merged away lands on the segment that id now means, rather than on a row
    nobody can see.
    """
    assert_not_provisional(segment_id, what="segment_id")
    resolved = resolve_segment(db, segment_id)
    live_id = primary_live_segment_id(resolved)
    if live_id is None:
        raise LookupError(f"Segment not found or deleted: {segment_id}")
    row = db.get(Segment, live_id)
    if row is None:
        raise LookupError(f"Segment not found: {segment_id}")
    return row


def _check_anchor_against_segment(
    anchor: SourceAnchor | None, segment: Segment, representation_id: str | None = None
) -> None:
    """A reading's own anchor must be able to belong to its segment.

    A reading MAY carry an anchor finer than the segment (a stretch of a line,
    a word inside it). It may NOT carry one naming a different document or a
    different page, because then two records disagree about where one piece of
    text is, and nothing in the system can say which is right.

    ponytail: document and page only. Checking that a rect lies INSIDE the
    segment's shape is the obvious next rung and is deliberately not taken —
    a reading legitimately anchored to a word that a later edit moved just
    outside its line's box would start being refused, and a refusal that fires
    on correct data is worse than a check that fires late. Tighten this when
    `source.segment.picture-by-shape`'s masking gives an exact containment
    test to reuse.
    """
    if anchor is None:
        return
    if anchor.document_id and anchor.document_id != segment.document_id:
        raise ReadingAnchorMismatch(
            representation_id,
            f"anchor names document {anchor.document_id}, segment is on {segment.document_id}",
        )
    segment_page = segment.anchor.page_id
    if anchor.page_id and segment_page and anchor.page_id != segment_page:
        raise ReadingAnchorMismatch(
            representation_id,
            f"anchor names page {anchor.page_id}, segment is on {segment_page}",
        )


class RepresentationCreateParams(BaseModel):
    """`representation.create` — one new reading. A CORRECTION IS A CREATE:
    nothing ever edits the text of a reading somebody already wrote
    (`source.reading.corrections-are-new`)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    #: The line this reads. Optional because a reading of a whole page is a
    #: real thing; never a provisional id.
    segment_id: str | None = None
    kind: str
    content: str
    language: str | None = None
    script: str | None = None
    #: How normalised (`source.reading.level-recorded`). Never inferred.
    level: str | None = None
    #: Worked out from the segment when absent, so the common caller says
    #: nothing and still gets an anchored reading.
    source_anchor: SourceAnchor | None = None
    derived_from_representation_id: str | None = None
    #: What this corrects, when what it corrects is a real reading.
    corrects_representation_id: str | None = None
    #: What this corrects, when what it corrects is text still living in an
    #: artifact (a provisional reading has no id to correct). THE ONLY link
    #: between the two stores, and it points from the new record to the old
    #: output — never a copy of the text, and never in bulk.
    derived_from_artifact_id: str | None = None
    guideline: str | None = None
    read_from_rendition_id: str | None = None
    #: Where this reading's language and script came from (slice 9, #4938).
    #: Accepted from the caller because a reading's language is the caller's
    #: claim — unlike `provenance_kind`, which is about WHO is writing and must
    #: stay engine-set. Omitted means NEVER DETERMINED, which is the honest
    #: default: a reading whose language nobody has established says so rather
    #: than inheriting a guess.
    language_meta: dict | None = None
    script_meta: dict | None = None
    #: The reading that COUNTED for this segment and kind when the writer read it
    #: (`source.textedit.stale-keeps-your-words`; decided 2026-09-28 by the lead as a default). When
    #: given, the write is a compare-and-set: if another reading counts now, it is refused with 409,
    #: naming the one that counts, and nothing is written. Absent, today's behaviour.
    expected_counting_id: str | None = None
    #: The recogniser's certainty about this reading, 0 to 1, where it gave one (#5694: Names is not run on a page
    #: read too uncertainly to name anyone). Kept on a machine's reading only.
    machine_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    def audit_params(self) -> dict:
        """The audit row gets every argument EXCEPT the words, and a digest in
        their place (`_audit_params`). The reading itself already holds the
        text, once; the undo of a create is a retraction, which needs none of
        it; and a digest still proves which text this call wrote."""
        recorded = self.model_dump(mode="json")
        recorded.pop("content", None)
        recorded["content_sha256"] = _content_sha256(self.content)
        return recorded


def _invert_representation_create(before, after, ctx: ActionContext):
    """Undo of a create is a RETRACTION -- which needs no content from the
    audit row, which is why the audit row is allowed to hold none."""
    if not after:
        return None
    representation_id = after.get("representation_id")
    if not representation_id:
        return None
    return ("representation.retract", {"representation_id": representation_id})


def _write_reading(
    db: Database, params: RepresentationCreateParams, ctx: ActionContext
) -> tuple[ContentRepresentation, dict, list[str]]:
    """Check and write ONE reading; the body `representation.create` and `representation.create_many`
    share, so a batch can never accept a reading the single write would refuse. Returns the reading,
    its audit `after`, and the retired word segments."""
    assert_known_reading_kind(db, params.kind)
    # `source.reading.normalized-text-is-a-level`: a write under an older kind (`normalized_text`) is
    # stored as the kind at its level -- a transcription, regularised unless it names its own level.
    kind, level = canonical_reading_kind_and_level(params.kind, params.level)
    params = params.model_copy(update={"kind": kind, "level": level})
    # `source.reading.levels`: a level outside the library's list is refused, naming the list; an older
    # spelling (`normalised`, the recipes' `as-written`) is stored as the level it means.
    params = params.model_copy(update={"level": assert_known_reading_level(db, params.level)})
    if params.kind == WORLD_POINT:
        # A place on the earth is checked and stored in WGS 84 with the CRS it arrived in, or held
        # unconverted as `unknown` -- never guessed (`models/geo.py`, #5122).
        params = params.model_copy(update={"content": world_point_content(params.content)})
    if params.script:
        # `source.lang.project-declared`: a private-use script code is refused
        # unless this library declared it. Checked on the WRITE only -- a
        # reading stored under a code whose declaration was later removed must
        # still read back, the same rule the reading kinds follow.
        assert_known_script(db, params.script)

    segment: Segment | None = None
    if params.segment_id is not None:
        segment = _live_segment(db, params.segment_id)
        if segment.document_id != params.document_id:
            raise ValueError(
                f"segment {params.segment_id} is on document {segment.document_id}, "
                f"not {params.document_id}"
            )
        _check_anchor_against_segment(params.source_anchor, segment)

    if params.expected_counting_id is not None:
        _refuse_if_the_counting_reading_moved(db, params, segment)

    if params.corrects_representation_id is not None:
        assert_not_provisional(
            params.corrects_representation_id, what="corrects_representation_id"
        )
        if db.get(ContentRepresentation, params.corrects_representation_id) is None:
            raise LookupError(
                f"Reading to correct not found: {params.corrects_representation_id}"
            )
    if params.derived_from_representation_id is not None:
        assert_not_provisional(
            params.derived_from_representation_id, what="derived_from_representation_id"
        )

    anchor = params.source_anchor
    if anchor is None:
        # Worked out from the segment, so the common caller says nothing and
        # still gets a reading that knows where it is.
        anchor = (
            segment.anchor.model_copy()
            if segment is not None
            else SourceAnchor(document_id=params.document_id)
        )

    reading = ContentRepresentation(
        document_id=params.document_id,
        segment_id=segment.id if segment is not None else None,
        kind=params.kind,
        content=params.content,
        language=params.language,
        script=params.script,
        level=params.level,
        source_anchor=anchor,
        derived_from_representation_id=params.derived_from_representation_id,
        corrects_representation_id=params.corrects_representation_id,
        derived_from_artifact_id=params.derived_from_artifact_id,
        guideline=params.guideline,
        read_from_rendition_id=params.read_from_rendition_id,
        language_meta=params.language_meta,
        script_meta=params.script_meta,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
        producer_run_id=ctx.run_id,
    )
    if reading.provenance_kind is not ProvenanceKind.human:
        reading.machine_confidence = params.machine_confidence
    db.save(reading)

    after = {
        "representation_id": reading.id,
        "segment_id": reading.segment_id,
        "kind": reading.kind,
        "content_sha256": _content_sha256(reading.content),
    }
    # A person's reading of a LINE retires the words it took out (#5190). Worked out at read
    # time, never written; named here so the audit says which words this edit retired, and in
    # `segment_ids` so open windows redraw them. A machine's line reading retires nothing.
    retired_words: list[str] = []
    if segment is not None and segment.kind == "line" and reading.provenance_kind is ProvenanceKind.human:
        from fichero_server.api.routes.document.segment_readings import retired_word_readings
        from fichero_server.models.readings import project_record_rule

        retired_words = sorted(retired_word_readings(db, segment, reading.kind, project_record_rule(db)))
        if retired_words:
            after["retired_word_segment_ids"] = retired_words
    return reading, after, retired_words


@action(
    "representation.create",
    RepresentationCreateParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=_invert_representation_create,
)
def create_representation(
    db: Database,
    params: RepresentationCreateParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Write one reading (`source.reading.set`).

    Adding a reading CHANGES NO OTHER ROW. Three readings of one line coexist;
    a correction names its target and leaves the target's text exactly as it
    was. That is the whole shape of `source.reading.corrections-are-new`, and
    it is why there is no update action here at all.
    """
    reading, after, retired_words = _write_reading(db, params, ctx)
    return reading.model_dump(mode="json"), ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[reading.id],
        before=None,
        after=after,
        emit_type="representation.created",
        document_ids=[reading.document_id],
        segment_ids=([reading.segment_id] if reading.segment_id else []) + retired_words,
    )


class LineLeftOut(BaseModel):
    """A line whose text was deleted entirely: marked left out, never deleted."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    expected_version: int


class RepresentationCreateManyParams(BaseModel):
    """`representation.create_many` — a Reader edit that touched several lines.

    `readings` are written exactly as `representation.create` writes them. `left_out` are lines
    whose text was deleted entirely: each is marked `is_furniture` (left out of the Reader text),
    its segment is NEVER deleted, and nothing is written for it."""

    model_config = ConfigDict(extra="forbid")

    readings: list[RepresentationCreateParams] = Field(default_factory=list)
    left_out: list[LineLeftOut] = Field(default_factory=list)

    def audit_params(self) -> dict:
        return {
            "readings": [item.audit_params() for item in self.readings],
            "left_out": [item.model_dump(mode="json") for item in self.left_out],
        }

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.readings and not self.left_out:
            raise ValueError("representation.create_many needs a reading or a line left out")
        return self


def _restores_from(left_out: list[dict]) -> list[dict]:
    """Restores that put the marked lines back. Each entry is `{segment_id, from_version,
    to_version}`: the row's version before and after the action ran. One snapshot, one bump, so
    `from_version` names the preimage to restore and `to_version` is what the row is now."""
    return [
        {"segment_id": i["segment_id"], "version": i["from_version"], "expected_version": i["to_version"]}
        for i in left_out
    ]


def _invert_create_many(before, after, ctx: ActionContext):
    if not after:
        return None
    return (
        "representation.retract_many",
        {
            "representation_ids": after.get("representation_ids") or [],
            "restores": _restores_from(after.get("left_out") or []),
        },
    )


@action(
    "representation.create_many",
    RepresentationCreateManyParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=_invert_create_many,
)
def create_many_representations(
    db: Database, params: RepresentationCreateManyParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """One Reader edit across lines: ONE audit row, ONE undo step, all or nothing.

    Every left-out line is checked (live, at the version the page saw) BEFORE anything is written,
    so a stale line refuses the whole edit instead of saving half of it."""
    from fichero_server.api.routes.document.segments import (
        _live_current_row,
        _refuse_repeated_ids,
    )

    _refuse_repeated_ids([item.segment_id for item in params.left_out])
    rows = [_live_current_row(db, item.segment_id, item.expected_version) for item in params.left_out]

    audit_id = uuid.uuid4().hex
    created: list[ContentRepresentation] = []
    retired: list[str] = []
    for item in params.readings:
        reading, _after, retired_words = _write_reading(db, item, ctx)
        created.append(reading)
        retired += retired_words
    left_out: list[dict] = []
    for row in rows:
        from_version = row.version
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        row.is_furniture = True
        db.save(row)
        left_out.append({"segment_id": row.id, "from_version": from_version, "to_version": row.version})

    segment_ids = sorted(
        {r.segment_id for r in created if r.segment_id} | {item["segment_id"] for item in left_out} | set(retired)
    )
    after = {"representation_ids": [r.id for r in created], "left_out": left_out}
    result = {
        "representations": [r.model_dump(mode="json") for r in created],
        "left_out": left_out,
    }
    return result, ChangeSpec(
        audit_id=audit_id,
        domains=["representation", "segment"],
        target_ids=[r.id for r in created] + [item["segment_id"] for item in left_out],
        before=None,
        after=after,
        emit_type="representation.created",
        document_ids=sorted({r.document_id for r in created} | {row.document_id for row in rows}),
        segment_ids=segment_ids,
        pass_ids=sorted({row.pass_id for row in rows}),
    )


class RepresentationRetractParams(BaseModel):
    """`representation.retract` — withdraw a reading. THE ROW STAYS."""

    model_config = ConfigDict(extra="forbid")

    representation_id: str


def _invert_representation_retract(before, after, ctx: ActionContext):
    if not before:
        return None
    representation_id = before.get("representation_id")
    if not representation_id:
        return None
    return ("representation.unretract", {"representation_id": representation_id})


@action(
    "representation.retract",
    RepresentationRetractParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=_invert_representation_retract,
    # Redo of an undone `representation.create` (whose inverse is this retract) brings back the
    # SAME reading with `unretract`. The default redo replays the create's AUDITED params, and
    # those carry a digest, not the words (`audit_params`), so ⌘⇧Z answered 422 "content: Field
    # required" (#5057).
    redo_via_own_invert=True,
)
def retract_representation(
    db: Database,
    params: RepresentationRetractParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Stop a reading counting, WITHOUT deleting it.

    Something that was said and then withdrawn is part of the record: a
    scholar's retracted reading of a line is evidence about the line, and
    about the scholar. It stops being a candidate; it does not stop existing.
    """
    assert_not_provisional(params.representation_id, what="representation_id")
    reading = db.get(ContentRepresentation, params.representation_id)
    if reading is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    before = {
        "representation_id": reading.id,
        "segment_id": reading.segment_id,
        "kind": reading.kind,
        "retracted_at": reading.retracted_at.isoformat() if reading.retracted_at else None,
    }
    if reading.retracted_at is None:
        db.save(reading.model_copy(update={"retracted_at": utc_now()}))
    return {"representation_id": reading.id, "retracted": True}, ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[reading.id],
        before=before,
        after={"representation_id": reading.id, "retracted": True},
        emit_type="representation.retracted",
        document_ids=[reading.document_id],
        segment_ids=[reading.segment_id] if reading.segment_id else [],
    )


@action(
    "representation.unretract",
    RepresentationRetractParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=lambda before, after, ctx: (
        ("representation.retract", {"representation_id": after["representation_id"]})
        if after
        else None
    ),
)
def unretract_representation(
    db: Database,
    params: RepresentationRetractParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Put a withdrawn reading back among the candidates (the inverse of a
    retraction, so undoing an undo of a create restores the reading)."""
    assert_not_provisional(params.representation_id, what="representation_id")
    reading = db.get(ContentRepresentation, params.representation_id)
    if reading is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    before = {
        "representation_id": reading.id,
        "retracted_at": reading.retracted_at.isoformat() if reading.retracted_at else None,
    }
    if reading.retracted_at is not None:
        db.save(reading.model_copy(update={"retracted_at": None}))
    return {"representation_id": reading.id, "retracted": False}, ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[reading.id],
        before=before,
        after={"representation_id": reading.id, "retracted": False},
        emit_type="representation.unretracted",
        document_ids=[reading.document_id],
        segment_ids=[reading.segment_id] if reading.segment_id else [],
    )


class SegmentRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    version: int
    expected_version: int


class RepresentationStateManyParams(BaseModel):
    """`representation.retract_many` / `.unretract_many`: the undo and redo of
    `representation.create_many`, as one audited step each."""

    model_config = ConfigDict(extra="forbid")

    representation_ids: list[str] = Field(default_factory=list)
    restores: list[SegmentRestore] = Field(default_factory=list)


def _set_readings_state_many(
    db: Database, params: RepresentationStateManyParams, ctx: ActionContext, *, retract: bool
) -> tuple[dict, ChangeSpec]:
    from fichero_server.api.routes.document.segments import (
        _copy_version_onto_row,
        _live_current_row,
        _refuse_repeated_ids,
    )

    _refuse_repeated_ids([item.segment_id for item in params.restores])
    readings = []
    for representation_id in params.representation_ids:
        assert_not_provisional(representation_id, what="representation_id")
        reading = db.get(ContentRepresentation, representation_id)
        if reading is None:
            raise LookupError(f"Content representation not found: {representation_id}")
        readings.append(reading)
    pairs = []
    for item in params.restores:
        row = _live_current_row(db, item.segment_id, item.expected_version, restoring=True)
        candidates = db.query(SegmentVersion, segment_id=item.segment_id, version=item.version)
        if not candidates:
            raise LookupError(f"segment {item.segment_id!r} has no version {item.version}")
        pairs.append((row, candidates[0]))

    audit_id = uuid.uuid4().hex
    for reading in readings:
        if (reading.retracted_at is None) == retract:
            db.save(reading.model_copy(update={"retracted_at": utc_now() if retract else None}))
    restored: list[dict] = []
    for row, target in pairs:
        from_version = row.version
        snapshot_segment_version(db, row, deleted=False, actor=ctx.actor, audit_id=audit_id)
        _copy_version_onto_row(row, target)
        db.save(row)
        restored.append({"segment_id": row.id, "from_version": from_version, "to_version": row.version})

    after = {"representation_ids": [r.id for r in readings], "left_out": restored}
    return after, ChangeSpec(
        audit_id=audit_id,
        domains=["representation", "segment"],
        target_ids=[r.id for r in readings] + [row.id for row, _t in pairs],
        before=None,
        after=after,
        emit_type="representation.retracted" if retract else "representation.unretracted",
        document_ids=sorted({r.document_id for r in readings} | {row.document_id for row, _t in pairs}),
        segment_ids=sorted({r.segment_id for r in readings if r.segment_id} | {row.id for row, _t in pairs}),
        pass_ids=sorted({row.pass_id for row, _t in pairs}),
    )


def _invert_state_many(target: str):
    def invert(before, after, ctx: ActionContext):
        if not after:
            return None
        return (
            target,
            {
                "representation_ids": after.get("representation_ids") or [],
                "restores": _restores_from(after.get("left_out") or []),
            },
        )

    return invert


@action(
    "representation.retract_many",
    RepresentationStateManyParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=_invert_state_many("representation.unretract_many"),
    redo_via_own_invert=True,
)
def retract_many_representations(db: Database, params: RepresentationStateManyParams, ctx: ActionContext):
    """Undo of `representation.create_many`: withdraw the readings and put the left-out lines back."""
    return _set_readings_state_many(db, params, ctx, retract=True)


@action(
    "representation.unretract_many",
    RepresentationStateManyParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=_invert_state_many("representation.retract_many"),
    redo_via_own_invert=True,
)
def unretract_many_representations(db: Database, params: RepresentationStateManyParams, ctx: ActionContext):
    """Redo of `representation.create_many`: bring the readings back and leave the lines out again."""
    return _set_readings_state_many(db, params, ctx, retract=False)


class RepresentationPairParams(BaseModel):
    """`representation.pair` — join two readings as written and read
    (`source.reading.written-read-pair`), which is a DIFFERENT relation from
    error and correction: "quiça" written and "quizá" read is not somebody
    being wrong."""

    model_config = ConfigDict(extra="forbid")

    written_id: str
    read_id: str


def _paired(db: Database, params: RepresentationPairParams) -> tuple:
    for field_name, value in (("written_id", params.written_id), ("read_id", params.read_id)):
        assert_not_provisional(value, what=field_name)
    written = db.get(ContentRepresentation, params.written_id)
    read = db.get(ContentRepresentation, params.read_id)
    for name, row in (("written_id", written), ("read_id", read)):
        if row is None:
            raise LookupError(f"Content representation not found ({name})")
    if written.segment_id != read.segment_id:
        raise ValueError(
            "a written-and-read pair is two readings of ONE segment; these name "
            f"{written.segment_id!r} and {read.segment_id!r}"
        )
    return written, read


@action(
    "representation.pair",
    RepresentationPairParams,
    domains=["representation"],
    undoable=True,
    invert=lambda before, after, ctx: (
        ("representation.unpair", {"written_id": after["written_id"], "read_id": after["read_id"]})
        if after
        else None
    ),
)
def pair_representations(
    db: Database,
    params: RepresentationPairParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    written, read = _paired(db, params)
    pair_id = written.pair_id or read.pair_id or uuid.uuid4().hex
    db.save(written.model_copy(update={"pair_id": pair_id, "pair_role": "written"}))
    db.save(read.model_copy(update={"pair_id": pair_id, "pair_role": "read"}))
    payload = {"written_id": written.id, "read_id": read.id, "pair_id": pair_id}
    return payload, ChangeSpec(
        domains=["representation"],
        target_ids=[written.id, read.id],
        before=None,
        after=payload,
        emit_type="representation.paired",
        document_ids=sorted({written.document_id, read.document_id}),
    )


@action(
    "representation.unpair",
    RepresentationPairParams,
    domains=["representation"],
    undoable=True,
    invert=lambda before, after, ctx: (
        ("representation.pair", {"written_id": after["written_id"], "read_id": after["read_id"]})
        if after
        else None
    ),
)
def unpair_representations(
    db: Database,
    params: RepresentationPairParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    written, read = _paired(db, params)
    before = {"written_id": written.id, "read_id": read.id, "pair_id": written.pair_id}
    for row in (written, read):
        db.save(row.model_copy(update={"pair_id": None, "pair_role": None}))
    payload = {"written_id": written.id, "read_id": read.id}
    return payload, ChangeSpec(
        domains=["representation"],
        target_ids=[written.id, read.id],
        before=before,
        after=payload,
        emit_type="representation.unpaired",
        document_ids=sorted({written.document_id, read.document_id}),
    )


class ReadingChooseParams(BaseModel):
    """`reading.choose` — "this is the reading that counts"."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    kind: str
    representation_id: str
    #: The reading that counted when the person looked (`source.compare.pick`): when another counts now the choice is
    #: refused (409, naming it) and nothing is written. Unset: no check, today's behaviour.
    expected_counting_id: str | None = None


def _assert_a_person(ctx: ActionContext, what: str) -> None:
    """`source.reading.chosen-is-worked-out`: a machine produces candidates,
    it does not decide which one the record is."""
    kind = provenance_kind_from_ctx(ctx)
    if kind is not ProvenanceKind.human:
        raise ChoiceNeedsAPerson(what, kind.value)


def _choice_level(db: Database, choice: ReadingChoice) -> str | None:
    """The level a choice is about: its reading's (None when the reading is not a stored row)."""
    reading = db.get(ContentRepresentation, choice.representation_id)
    return counting_level(reading.level) if reading is not None else None


def _supersede_choices(db: Database, rows: list, at) -> list[str]:
    """Stamp every live choice as superseded. Rows are NEVER deleted."""
    superseded: list[str] = []
    for row in rows:
        if row.superseded_at is None:
            db.save(row.model_copy(update={"superseded_at": at}))
            superseded.append(row.id)
    return superseded


@action(
    "reading.choose",
    ReadingChooseParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=lambda before, after, ctx: (
        (
            "reading.choose",
            {
                "segment_id": after["segment_id"],
                "kind": after["kind"],
                "representation_id": before["representation_id"],
            },
        )
        if after and before and before.get("representation_id")
        else (
            ("reading.unchoose", {"segment_id": after["segment_id"], "kind": after["kind"]})
            if after
            else None
        )
    ),
)
def choose_reading(
    db: Database,
    params: ReadingChooseParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Record which reading of one kind counts for one segment.

    The inverse is the EARLIER choice where there was one, and
    `reading.unchoose` where there was not -- so undo restores the state the
    historian was actually in, not merely "no choice".
    """
    _assert_a_person(ctx, "a reading")
    assert_known_reading_kind(db, params.kind)
    # A choice under an older kind (`normalized_text`) is a choice of the kind it is: its reading says
    # the level (`source.reading.normalized-text-is-a-level`).
    params = params.model_copy(update={"kind": reading_kind_filter(params.kind)[0]})
    assert_not_provisional(params.representation_id, what="representation_id")
    segment = _live_segment(db, params.segment_id)
    reading = db.get(ContentRepresentation, params.representation_id)
    if reading is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    if reading.segment_id not in (None, segment.id):
        raise ValueError(
            f"reading {reading.id} reads segment {reading.segment_id}, not {segment.id}"
        )

    if params.expected_counting_id is not None:
        refuse_if_counting_moved(db, segment, params.kind, reading.level, params.expected_counting_id)

    # A choice supersedes the earlier choices AT ITS OWN LEVEL only (`source.reading.counts-per-level`):
    # choosing which expanded reading counts says nothing about which as-written one does.
    level = counting_level(reading.level)
    # Filtered here, not in the query: a choice stored under an older kind reads as this one.
    existing = [
        row for row in db.query(ReadingChoice, segment_id=segment.id)
        if row.kind == params.kind and _choice_level(db, row) in (None, level)
    ]
    live = [row for row in existing if row.superseded_at is None]
    now = utc_now()
    _supersede_choices(db, existing, now)
    choice = ReadingChoice(
        document_id=segment.document_id,
        segment_id=segment.id,
        kind=params.kind,
        representation_id=reading.id,
        chosen_by=ctx.actor,
        chosen_at=now,
    )
    db.save(choice)

    before = {
        "choice_id": live[-1].id if live else None,
        "representation_id": live[-1].representation_id if live else None,
    }
    after = {
        "choice_id": choice.id,
        "segment_id": segment.id,
        "kind": params.kind,
        "representation_id": reading.id,
    }
    return after, ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[choice.id],
        before=before,
        after=after,
        emit_type="reading.chosen",
        document_ids=[segment.document_id],
        segment_ids=[segment.id],
    )


class ReadingUnchooseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    kind: str


@action(
    "reading.unchoose",
    ReadingUnchooseParams,
    domains=["representation", "segment"],
    undoable=True,
    invert=lambda before, after, ctx: (
        (
            "reading.choose",
            {
                "segment_id": before["segment_id"],
                "kind": before["kind"],
                "representation_id": before["representation_id"],
            },
        )
        if before and before.get("representation_id")
        else None
    ),
)
def unchoose_reading(
    db: Database,
    params: ReadingUnchooseParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Withdraw a choice, putting the segment back to "worked out"."""
    _assert_a_person(ctx, "a reading")
    segment = _live_segment(db, params.segment_id)
    # An older kind (`normalized_text`) withdraws the choices at its level only; a choice stored under
    # it reads as the kind it is, so it is filtered here rather than in the query.
    kind, level = reading_kind_filter(params.kind)
    params = params.model_copy(update={"kind": kind})
    existing = [
        row for row in db.query(ReadingChoice, segment_id=segment.id)
        if row.kind == kind and (level is None or _choice_level(db, row) in (None, level))
    ]
    live = [row for row in existing if row.superseded_at is None]
    _supersede_choices(db, existing, utc_now())
    before = {
        "segment_id": segment.id,
        "kind": params.kind,
        "representation_id": live[-1].representation_id if live else None,
    }
    after = {"segment_id": segment.id, "kind": params.kind, "representation_id": None}
    return after, ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[row.id for row in live],
        before=before,
        after=after,
        emit_type="reading.unchosen",
        document_ids=[segment.document_id],
        segment_ids=[segment.id],
    )


class PassChooseWorkingParams(BaseModel):
    """`pass.choose_working` — "this is the pass I am working on"."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    pass_id: str


@action(
    "pass.choose_working",
    PassChooseWorkingParams,
    domains=["segment"],
    undoable=True,
    invert=lambda before, after, ctx: (
        (
            "pass.choose_working",
            {"document_id": after["document_id"], "pass_id": before["pass_id"]},
        )
        if after and before and before.get("pass_id")
        # The FIRST choice on a page had no earlier one to go back to, and its undo used to fail
        # ("Action did not yield an inverse to apply") -- so ⌘Z on a person's first choice did
        # nothing (#5156). Its inverse is to retire the choice: the page goes back to its rule.
        else ("pass.clear_working", {"document_id": after["document_id"], "choice_id": after["choice_id"]})
        if after
        else None
    ),
)
def choose_working_pass(
    db: Database,
    params: PassChooseWorkingParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Record which pass a person is working on (`source.pass.working`).

    Slice 6 already writes these rows as a side effect of a page's first edit;
    this is the same record, chosen deliberately.
    """
    _assert_a_person(ctx, "a working pass")
    assert_not_provisional(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if pass_row is None:
        raise LookupError(f"Pass not found: {params.pass_id}")
    if pass_row.document_id != params.document_id:
        raise ValueError(
            f"pass {params.pass_id} is on document {pass_row.document_id}, "
            f"not {params.document_id}"
        )

    # A choice supersedes the earlier choices OF ITS OWN KIND only (#5122): choosing a
    # georeferencing pass must not retire a person's choice of the text pass, nor the reverse.
    from fichero_server.api.routes.document.segment_readings import georeferences

    kind = georeferences(pass_row)
    existing = [row for row in db.query(SegmentPassChoice, document_id=params.document_id)
                if georeferences(db.get(SegmentPass, row.pass_id)) == kind]
    live = [row for row in existing if row.superseded_at is None]
    now = utc_now()
    _supersede_choices(db, existing, now)
    choice = SegmentPassChoice(
        document_id=params.document_id,
        pass_id=params.pass_id,
        chosen_by=ctx.actor,
        chosen_at=now,
    )
    db.save(choice)

    before = {
        "choice_id": live[-1].id if live else None,
        "pass_id": live[-1].pass_id if live else None,
    }
    after = {
        "choice_id": choice.id,
        "document_id": params.document_id,
        "pass_id": params.pass_id,
    }
    return after, ChangeSpec(
        domains=["segment"],
        target_ids=[choice.id],
        before=before,
        after=after,
        emit_type="pass.working_chosen",
        document_ids=[params.document_id],
        pass_ids=[params.pass_id],
    )


class PassClearWorkingParams(BaseModel):
    """`pass.clear_working` -- retire a person's choice of working pass; the rule decides again."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    choice_id: str


@action(
    "pass.clear_working",
    PassClearWorkingParams,
    domains=["segment"],
    undoable=True,
    invert=lambda before, after, ctx: (
        ("pass.choose_working", {"document_id": after["document_id"], "pass_id": before["pass_id"]})
        if after and before and before.get("pass_id")
        else None
    ),
)
def clear_working_pass(
    db: Database,
    params: PassClearWorkingParams,
    ctx: ActionContext,
) -> tuple[dict, ChangeSpec]:
    """Retire one choice of working pass (#5156): the undo of a page's FIRST choice, which has no
    earlier choice to restore. The row is stamped superseded, never deleted; the page's working pass is
    then whatever the project's rule picks."""
    _assert_a_person(ctx, "a working pass")
    choice = db.get(SegmentPassChoice, params.choice_id)
    if choice is None or choice.document_id != params.document_id:
        raise LookupError(f"Working-pass choice not found on document {params.document_id}: {params.choice_id}")
    if choice.superseded_at is None:
        _supersede_choices(db, [choice], utc_now())
    before = {"choice_id": choice.id, "pass_id": choice.pass_id}
    after = {"document_id": params.document_id, "cleared_choice_id": choice.id}
    return after, ChangeSpec(
        domains=["segment"],
        target_ids=[choice.id],
        before=before,
        after=after,
        emit_type="pass.working_chosen",
        document_ids=[params.document_id],
        pass_ids=[choice.pass_id],
    )


@router.post("", response_model=ContentRepresentation)
async def create_representation_route(
    payload: RepresentationCreateParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ContentRepresentation:
    """`POST /api/content-representations` — write one reading."""
    try:
        result = registry.invoke(db, "representation.create", payload.model_dump(), ctx)
    except Exception as exc:  # typed refusals -> 4xx, never a 500
        raise _as_http_error(exc) from exc
    return ContentRepresentation.model_validate(result.result)


class RepresentationCreateManyResponse(BaseModel):
    """The readings written, the lines left out, and the audit id of the ONE undo step."""

    representations: list[ContentRepresentation]
    left_out: list[dict]
    audit_id: str


@router.post("/batch", response_model=RepresentationCreateManyResponse)
async def create_representations_batch_route(
    payload: RepresentationCreateManyParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RepresentationCreateManyResponse:
    """`POST /api/content-representations/batch` — one Reader edit across lines, one undo step."""
    try:
        result = registry.invoke(db, "representation.create_many", payload.model_dump(), ctx)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return RepresentationCreateManyResponse(
        representations=[ContentRepresentation.model_validate(r) for r in result.result["representations"]],
        left_out=result.result["left_out"],
        audit_id=result.audit_id,
    )
