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

from pydantic import BaseModel, ConfigDict, Field
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
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.readings import (
    ChoiceNeedsAPerson,
    ReadingAnchorMismatch,
    ReadingChoice,
    UnknownReadingKind,
    assert_known_reading_kind,
)
from fichero_server.models.segments import (
    ProvisionalSegmentIdError,
    Segment,
    SegmentPass,
    SegmentPassChoice,
    assert_not_provisional,
    primary_live_segment_id,
    resolve_segment,
)

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
async def list_revisions(
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
    assert_known_reading_kind(db, params.kind)

    segment: Segment | None = None
    if params.segment_id is not None:
        segment = _live_segment(db, params.segment_id)
        if segment.document_id != params.document_id:
            raise ValueError(
                f"segment {params.segment_id} is on document {segment.document_id}, "
                f"not {params.document_id}"
            )
        _check_anchor_against_segment(params.source_anchor, segment)

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
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
        producer_run_id=ctx.run_id,
    )
    db.save(reading)

    after = {
        "representation_id": reading.id,
        "segment_id": reading.segment_id,
        "kind": reading.kind,
        "content_sha256": _content_sha256(reading.content),
    }
    return reading.model_dump(mode="json"), ChangeSpec(
        domains=["representation", "segment"],
        target_ids=[reading.id],
        before=None,
        after=after,
        emit_type="representation.created",
        document_ids=[reading.document_id],
        segment_ids=[reading.segment_id] if reading.segment_id else [],
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


def _assert_a_person(ctx: ActionContext, what: str) -> None:
    """`source.reading.chosen-is-worked-out`: a machine produces candidates,
    it does not decide which one the record is."""
    kind = provenance_kind_from_ctx(ctx)
    if kind is not ProvenanceKind.human:
        raise ChoiceNeedsAPerson(what, kind.value)


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
    assert_not_provisional(params.representation_id, what="representation_id")
    segment = _live_segment(db, params.segment_id)
    reading = db.get(ContentRepresentation, params.representation_id)
    if reading is None:
        raise LookupError(f"Content representation not found: {params.representation_id}")
    if reading.segment_id not in (None, segment.id):
        raise ValueError(
            f"reading {reading.id} reads segment {reading.segment_id}, not {segment.id}"
        )

    existing = db.query(ReadingChoice, segment_id=segment.id, kind=params.kind)
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
    existing = db.query(ReadingChoice, segment_id=segment.id, kind=params.kind)
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

    existing = db.query(SegmentPassChoice, document_id=params.document_id)
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
