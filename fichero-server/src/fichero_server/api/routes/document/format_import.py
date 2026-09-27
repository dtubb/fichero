"""Importing an interchange file INTO a library (#4943).

Spec: `formats-and-training.md` — `source.format.import-is-pass`,
`source.format.reimport-recognised`; build notes:
`build-notes-formats-harness.md`.

**Why this matters more than a fourth format.** Until now `SourcePage` never left
`formats/`: a PAGE XML file could be read into a transient object and written back
out, and **a user could not bring their eScriptorium export into a library.** Reading
into the model is not reading into the library. This is the path that turns three
readers into a feature.

`source.format.import-is-pass`, and the three things that follow:

* **It is a PASS**, so it gets the pass machinery — and an import does **NOT** become
  the working pass (ruled 2026-09-26). Arriving is not winning; promoting it would
  answer a scholarly question with a file operation, and curation is what decides
  which reading of a page counts.
* **It overwrites nothing.** Existing segments, readings and orders are untouched. An
  import is another opinion about the page, which is exactly what a pass is for.
* **Its provenance says a person brought a file**, through the one
  `provenance_kind_from_ctx` rule rather than a second copy of it.

`source.format.reimport-recognised` uses the mechanism the spec names — the
importer's content hash (→ #739) — stored where slice 1 already put a home for it:
`SegmentPass.import_file` and `.import_checksum`. **No second dedupe table**, because
a format-specific one beside the importer's is the duplication shape this programme
has met six times.

**Written in BATCHES, deliberately.** A dense page is 20,000 segments. The conversion
path learned this the hard way: rows go in one `save_many`, readings in another, order
entries in a third, and the order is written directly rather than by placing each
segment against its siblings — which would be quadratic on exactly the page where it
hurts. Tonight's gate died inside a single enormous DuckDB commit, so batch size is a
correctness concern and not only a speed one.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database_for_write
from fichero_server.api.routes.document.reading_orders import ensure_as_written_order
from fichero_server.api.routes.document.segments import (
    SegmentSpec,
    _build_segment_row,
    provenance_kind_from_ctx,
)
from fichero_server.db import Database
from fichero_server.formats import UnknownFormat, format_for, format_named, read_page
from fichero_server.formats.harness import SourcePage
from fichero_server.models import ContentRepresentation, Document, Segment
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.reading_orders import ReadingOrderEntry
from fichero_server.models.segments import SegmentPass


class UnrecognisedImportFile(ValueError):
    """Raised when nothing claims the file.

    Names what this build can read, because a caller with a `.xml` file that is
    neither PAGE XML nor ALTO nor TEI should be told which three it is not.
    """

    def __init__(self, filename: str, known: list[str]) -> None:
        self.filename = filename
        super().__init__(
            f"nothing recognises {filename!r}. This build reads: "
            + ", ".join(sorted(known))
            + ". The bytes decide, not the extension, so a renamed file is read on "
            "its content."
        )


class GeoreferencingNotYetImportable(ValueError):
    """Raised for a file whose segments carry WORLD positions (IIIF Georeference GCPs).

    The format reads (`formats/iiif_georef.py`) and round-trips format to format, but a
    library has nowhere to put a ground control point's world end until the GCP model
    lands (#5122). Importing anyway would keep the pixel end and drop the place on the
    earth, which is the half that makes it a control point. So: refused, by name. Before
    this, the same file was refused as having shapes "outside the page", which was true
    of nothing in it.
    """

    def __init__(self, filename: str, count: int) -> None:
        super().__init__(
            f"{filename} is a georeferencing file with {count} ground control point(s). "
            "Fichero reads and exports this format, but cannot yet keep a control point's "
            "world position in a library (#5122), so nothing was imported."
        )


class ShapesOutsideThePage(ValueError):
    """Raised when a file's shapes lie outside the page size it declares.

    **Refused, not guessed.** A segment IS a place on a source — the model requires a
    box because a segment with no place is not a segment — so there are only three
    possible answers for a shape below the bottom of its own page: invent a place
    (puts a scholar's block where it is not), drop it silently (loses their
    transcription), or refuse and say exactly what disagrees. The standing rule is to
    raise rather than substitute, and this is why.

    Found in eScriptorium's OWN export sample, whose page declares
    `imageHeight="206"` while four of its shapes run past y=245. A user meeting this
    needs to know their file is self-inconsistent, which no clamped import would tell
    them.
    """

    def __init__(self, filename: str, page: tuple[int, int] | None, refs: list[str]) -> None:
        self.refs = refs
        shown = ", ".join(refs[:4]) + (f" (and {len(refs) - 4} more)" if len(refs) > 4 else "")
        size = f"{page[0]}x{page[1]}" if page else "an unstated size"
        super().__init__(
            f"{filename!r} declares a page of {size}, and these segments lie outside "
            f"it: {shown}. Nothing was imported. A segment is a place on a source, so "
            "the alternatives would be to invent a place or to drop the text — the "
            "file's page size and its coordinates disagree and only its author can "
            "say which is right."
        )


class ImportArrivedBefore(ValueError):
    """Raised when this exact file is already a pass on this document.

    `source.format.reimport-recognised`: recognised, **not duplicated silently**. The
    refusal names the pass, so a caller can look at what they already have rather
    than wondering whether the import worked.
    """

    def __init__(self, filename: str, pass_id: str, checksum: str) -> None:
        self.pass_id = pass_id
        self.checksum = checksum
        super().__init__(
            f"{filename!r} is already on this document as pass {pass_id} "
            f"(same content, sha256 {checksum[:12]}…). Nothing was written. Delete "
            "that pass first if the file has changed meaning rather than content."
        )


def file_checksum(data: bytes) -> str:
    """The same sha256 over content the importer uses (→ #739)."""
    return hashlib.sha256(data).hexdigest()


def existing_import(db: Database, document_id: str, checksum: str) -> SegmentPass | None:
    """The live pass this exact file already made on this document, if any."""
    for row in db.query(SegmentPass, document_id=document_id):
        if row.deleted_at is None and row.import_checksum == checksum:
            return row
    return None


class FormatImportParams(BaseModel):
    """`path` is a file on disk the engine can read.

    Bytes are not a parameter: an action's params go into the audit row, and a
    megabyte of XML in the tamper-evident chain would be source text nobody can
    purge. The PATH is recorded; the content is read and turned into rows.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    path: str
    #: Force a format instead of recognising one. For a file whose bytes are
    #: ambiguous, never as a convenience.
    format: Optional[str] = None
    #: What to call the pass. Defaults to the file's own name, which is what a
    #: person recognises in a list of passes.
    name: Optional[str] = None


def _invert_format_import(before, after, ctx: ActionContext):
    """Undo an import by deleting the pass it made, which takes its segments with it.

    Reads only `after`, like every other inverse here.
    """
    pass_id = (after or {}).get("pass_id")
    return ("segment.pass_delete", {"pass_id": pass_id}) if pass_id else None


@action(
    "format.import",
    FormatImportParams,
    domains=["segment", "representation"],
    undoable=True,
    invert=_invert_format_import,
)
def _action_format_import(db: Database, params: FormatImportParams, ctx: ActionContext):
    """Read an interchange file into this library as a new pass."""
    path = Path(params.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {params.path}")
    document = db.get(Document, params.document_id)
    if document is None:
        raise HTTPException(
            status_code=404, detail=f"Document not found: {params.document_id}"
        )

    data = path.read_bytes()
    checksum = file_checksum(data)

    already = existing_import(db, params.document_id, checksum)
    if already is not None:
        raise _as_http_error(ImportArrivedBefore(path.name, already.id, checksum))

    if params.format:
        spec = format_named(params.format)
    else:
        spec = format_for(path.name, data)
        if spec is None or not spec.reads:
            raise _as_http_error(
                UnrecognisedImportFile(
                    path.name, [s.name for s in _readable_formats()]
                )
            )
    page = read_page(spec.name, data)

    result = write_page_into_library(
        db,
        document_id=params.document_id,
        page=page,
        format_name=spec.name,
        source_name=path.name,
        checksum=checksum,
        pass_name=params.name or path.name,
        ctx=ctx,
    )

    spec_change = ChangeSpec(
        domains=["segment", "representation"],
        target_ids=[result["pass_id"]],
        before=None,
        after=result,
        emit_type="pass.created",
        pass_ids=[result["pass_id"]],
        document_ids=[params.document_id],
    )
    return result, spec_change


def _anchor_for(
    document_id: str, segment: Any, page_size: tuple[int, int] | None = None
) -> tuple[SourceAnchor | None, str | None]:
    """The anchor for one imported segment, or `None` when no honest shape survives.

    **Real files disagree with their own declared page size.** eScriptorium's own
    exports place shapes past the `imageHeight` they declare — in their PAGE XML and
    in their ALTO — and `SourceAnchor` refuses a normalised rect that leaves the page,
    correctly, because a shape outside the page cannot be drawn on it.

    A shape that merely OVERLAPS the edge is clamped and the change recorded: a
    clamped coordinate is a change to what a file said, and that has to be visible.
    A shape ENTIRELY outside the page cannot be clamped into anything drawable, so this
    returns `None` and the import refuses — a segment is a place on a source, and the
    alternatives are to invent a place or to drop a transcription.

    **The check is about whether a drawable shape survives, not about which FIELD it
    came from.** The first version asked "is there a polygon?", and a wholly
    out-of-page polygon clamped into a FLAT four-point line passed it — zero area,
    four points, valid to the letter. Found by eScriptorium's ALTO export, where the
    reader fills a polygon from the rect.
    """
    problems: list[str] = []

    rect = segment.rect
    if rect is not None:
        clamped = _clamped_rect(rect)
        outside = rect[0] >= 1.0 or rect[1] >= 1.0 or rect[0] + rect[2] <= 0.0 or rect[1] + rect[3] <= 0.0
        if outside:
            problems.append(
                f"rect {[round(v, 4) for v in rect]} lies entirely outside the page "
                "the file declares"
            )
            rect = None
        elif clamped[2] <= 0.0 or clamped[3] <= 0.0:
            # DEGENERATE BUT INSIDE THE PAGE, which is a different fact from being
            # outside it and deserves a different answer. A real ALTO file writes
            # `WIDTH="0"` for a page number: the PLACE is real and only the extent is
            # unusable, so it is given one unit of the file's own grid and the change
            # is recorded. Refusing here would lose a transcription over a rounding
            # artefact; refusing an off-page block is refusing to invent a place, which
            # is not the same thing.
            minimum = _minimum_extent(page_size)
            widened = [
                clamped[0],
                clamped[1],
                max(clamped[2], minimum[0]),
                max(clamped[3], minimum[1]),
            ]
            problems.append(
                f"rect {[round(v, 5) for v in rect]} has no area in the file "
                f"(a zero width or height) and was given one unit of its own grid"
            )
            rect = _clamped_rect(widened)
        elif clamped != rect:
            problems.append(
                f"rect {[round(v, 4) for v in rect]} lay outside the page declared by "
                f"the file and was clamped to {[round(v, 4) for v in clamped]}"
            )
            rect = clamped

    polygon = segment.polygon
    if polygon is not None:
        clipped = [[min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)] for x, y in polygon]
        if _area(clipped) <= 0.0:
            problems.append(
                "its polygon has no area once clamped to the page, so the rect is the "
                "only shape kept"
            )
            polygon = None
        elif clipped != polygon:
            problems.append("polygon points outside the page were clamped to it")
            polygon = clipped

    if rect is None and polygon is None:
        return None, "; ".join(problems) or "no drawable shape"
    return (
        SourceAnchor(
            document_id=document_id,
            rect=rect,
            polygon=polygon,
            granularity=segment.kind,
        ),
        "; ".join(problems) or None,
    )


def _minimum_extent(page_size: tuple[int, int] | None) -> tuple[float, float]:
    """One unit of the file's own grid, or a small fraction when it states none.

    One PIXEL of the page the file declares, so a widened box is as small as that file
    can express -- not a round number of our choosing, which would be our shape rather
    than a repair of theirs.
    """
    if page_size and page_size[0] and page_size[1]:
        return (1.0 / page_size[0], 1.0 / page_size[1])
    return (1e-4, 1e-4)


def _area(polygon: list[list[float]]) -> float:
    """Twice the enclosed area, by the shoelace formula; 0 for a flat or empty shape.

    The reason this is here rather than a bounding-box check: a polygon clamped onto
    one edge of the page has a bounding box of zero height, but so does a legitimately
    thin line of text — the area is what says "this cannot be drawn".
    """
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index, (x0, y0) in enumerate(polygon):
        x1, y1 = polygon[(index + 1) % len(polygon)]
        total += x0 * y1 - x1 * y0
    return abs(total)


def _clamped_rect(rect: list[float]) -> list[float]:
    """`[x, y, w, h]` fitted inside the page, keeping the top-left where possible."""
    x, y, w, h = rect
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0 - x)
    h = min(max(h, 0.0), 1.0 - y)
    return [x, y, w, h]


def write_page_into_library(
    db: Database,
    *,
    document_id: str,
    page: SourcePage,
    format_name: str,
    source_name: str,
    checksum: str,
    pass_name: str,
    ctx: ActionContext,
) -> dict[str, Any]:
    """One `SourcePage` as a pass, its segments, their readings and its order.

    In BATCHES, and in this order: the pass, then the segments, then the readings,
    then the order's entries. Each `save_many` is one statement, and nothing places a
    segment by searching its siblings — the import of a dense page is where that cost
    would land.
    """
    pass_row = SegmentPass(
        document_id=document_id,
        name=pass_name,
        # ONE rule for who made this (#4868/#4869): a person brought a file, so the
        # pass is theirs; a runner importing is a machine's. Never a second copy of
        # the derivation.
        provenance_kind=provenance_kind_from_ctx(ctx),
        actor=ctx.actor,
        provider=page.producer,
        run_id=ctx.run_id,
        import_file=source_name,
        import_checksum=checksum,
    )
    db.save(pass_row)

    # The file's own ids are resolved to OURS here and nowhere else: a format's ref
    # is how the file refers to itself, never an id we store.
    rows: list[Segment] = []
    ids_by_ref: dict[str, str] = {}
    order: list[tuple[str, Any]] = []
    for index, segment in enumerate(page.segments):
        ref = segment.ref or f"{format_name}:{index}"
        ids_by_ref[ref] = uuid.uuid4().hex
        order.append((ref, segment))

    # Anchors are built ONCE and the placeability check reads the same objects, rather
    # than constructing each anchor twice. **Not a measured speed-up**: building them
    # twice and once both came out around a minute for 20,000 segments on a machine
    # with other work on it, so the honest claim is only that doing the same work once
    # is not worse. An import either happens or does not, so the check still runs
    # before the first write.
    worlded = sum(1 for _ref, segment in order if segment.world is not None)
    if worlded:
        raise _as_http_error(GeoreferencingNotYetImportable(source_name, worlded))

    anchors: dict[str, tuple[SourceAnchor | None, str | None]] = {
        ref: _anchor_for(document_id, segment, page.image_size)
        for ref, segment in order
    }
    unplaceable = [ref for ref, (anchor, _why) in anchors.items() if anchor is None]
    if unplaceable:
        raise _as_http_error(
            ShapesOutsideThePage(source_name, page.image_size, unplaceable)
        )

    for ref, segment in order:
        anchor, geometry_problem = anchors[ref]
        assert anchor is not None  # refused above; kept as a guard against reordering
        row = _build_segment_row(
            document_id=document_id,
            pass_id=pass_row.id,
            spec=SegmentSpec(
                kind=segment.kind,
                anchor=anchor,
                baseline=segment.baseline,
                parent_segment_id=ids_by_ref.get(segment.parent_ref or ""),
            ),
            actor=ctx.actor,
            provenance_kind=provenance_kind_from_ctx(ctx),
            id=ids_by_ref[ref],
        )
        # Slice 9's three facts arrive WITH the segment, with provenance saying the
        # file said so -- not a person and not a detector. An imported `rtl` Arabic
        # line is readable as such the moment the import finishes.
        row.language = segment.language
        row.script = segment.script
        row.direction = segment.direction
        meta = _from_the_file(format_name)
        if segment.language:
            row.language_meta = dict(meta)
        if segment.script:
            row.script_meta = dict(meta)
        if segment.direction:
            row.direction_meta = dict(meta)
        if segment.foreign:
            row.metadata = {**row.metadata, "foreign": dict(segment.foreign)}
        if geometry_problem:
            # The same key the conversion path uses for the same situation: the
            # anchor could not hold what the file said, and the row records it rather
            # than the difference being invisible.
            row.metadata = {**row.metadata, "geometry_problem": geometry_problem}
        rows.append(row)

    if rows:
        db.save_many(rows)

    readings: list[ContentRepresentation] = []
    for ref, segment in order:
        for kind, text in segment.readings:
            readings.append(
                ContentRepresentation(
                    document_id=document_id,
                    segment_id=ids_by_ref[ref],
                    kind=kind,
                    content=text,
                    language=segment.language,
                    script=segment.script,
                    source_anchor=SourceAnchor(
                        document_id=document_id, granularity=segment.kind
                    ),
                    provenance_kind=provenance_kind_from_ctx(ctx),
                    created_by=ctx.actor or None,
                )
            )
    if readings:
        db.save_many(readings)

    # The file's own reading order, as a named order. Written directly in the file's
    # sequence: placing each entry against its siblings would be quadratic, and the
    # file has already told us the order.
    entries: list[ReadingOrderEntry] = []
    reading_order = page.orders[0] if page.orders else None
    if reading_order is not None:
        as_written = ensure_as_written_order(
            db,
            document_id=document_id,
            pass_id=pass_row.id,
            provenance_kind=pass_row.provenance_kind,
            created_by=ctx.actor or None,
        )
        for position, ref in enumerate(reading_order.refs, start=1):
            segment_id = ids_by_ref.get(ref)
            if segment_id is None:
                continue
            entries.append(
                ReadingOrderEntry(
                    order_id=as_written.id, segment_id=segment_id, position=float(position)
                )
            )
        if entries:
            db.save_many(entries)

    return {
        "pass_id": pass_row.id,
        "format": format_name,
        "segments": len(rows),
        "readings": len(readings),
        "order_entries": len(entries),
        "checksum": checksum,
    }


def _from_the_file(format_name: str) -> dict[str, Any]:
    """The provenance an imported fact carries.

    `source=metadata` because the FILE said so — not `user` (no person judged it
    here) and not `detected` (nothing ran a detector). The level is the segment's,
    because that is where the file put it.
    """
    from fichero_server.llm.language_policy import (
        LEVEL_SEGMENT,
        SOURCE_METADATA,
        STATUS_KNOWN,
        build_language_meta,
    )

    return build_language_meta(
        status=STATUS_KNOWN,
        source=SOURCE_METADATA,
        level=LEVEL_SEGMENT,
        basis=f"stated by the imported {format_name} file",
    )


def _readable_formats() -> list[Any]:
    from fichero_server.formats import known_formats

    return [spec for spec in known_formats() if spec.reads]


def _as_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ImportArrivedBefore):
        # 409: the library already holds this, which is a state rather than a bad
        # request -- the caller did nothing wrong and nothing was written.
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (ShapesOutsideThePage, GeoreferencingNotYetImportable)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (UnrecognisedImportFile, UnknownFormat)):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# The route (`source.format.everywhere`, the app's half)
# ---------------------------------------------------------------------------

router = APIRouter()


class ErrorDetail(BaseModel):
    """The body this route's refusals actually send: `{"detail": "<a sentence>"}`.

    **Declared because it was not, and the omission ate the sentence** (#5089). Without
    a `responses=` entry FastAPI documents 422 as its own `HTTPValidationError`, whose
    `detail` is an ARRAY of field errors — and the generated Swift client decodes the
    body while producing the response, so a person picking the wrong file got a client
    decoding error instead of *"nothing recognises 'x.xml'. This build reads: …"*.
    **That sentence is the whole value of the refusal**: a scholar who chose the wrong
    file needs to be told what this build can read.

    The 409 is declared for the same reason even though it works today: it works only
    because nothing declared it, which is the same accident facing the other way.
    """

    detail: str


class ImportResponse(BaseModel):
    """What the app is told about an import.

    The counts are what a person wants to see (`812 segments, 806 readings`), and
    `format` is what was RECOGNISED rather than what they said it was -- a renamed
    eScriptorium export still reports `pagexml`, which is the answer to "did it read
    my file properly".
    """

    pass_id: str
    format: str
    segments: int
    readings: int
    order_entries: int
    checksum: str
    #: How many segments had a shape the file could not express properly. Surfaced
    #: rather than buried in rows: a page where forty boxes were repaired is a page
    #: somebody should look at.
    geometry_problems: int = 0


@router.post(
    "/documents/{doc_id}/import",
    response_model=ImportResponse,
    summary="Import a PAGE XML, ALTO, hOCR, TEI or YOLO file as a new pass",
    responses={
        404: {
            "model": ErrorDetail,
            "description": "No such document, or the uploaded file could not be read.",
        },
        409: {
            "model": ErrorDetail,
            "description": (
                "This exact file is already a pass on this document "
                "(`source.format.reimport-recognised`). Nothing was written, and the "
                "sentence names the pass that already holds it."
            ),
        },
        422: {
            "model": ErrorDetail,
            "description": (
                "Nothing recognises the file, or its shapes lie outside the page it "
                "declares. The sentence says which formats this build reads, or which "
                "segments disagree with the page size — it is the refusal's whole "
                "value and the app must show it rather than a decoding error."
            ),
        },
    },
)
async def import_document_page(
    doc_id: str,
    file: UploadFile = File(..., description="The interchange file"),
    format_name: Optional[str] = Query(
        None,
        alias="format",
        description="Force a format instead of recognising one from the bytes",
    ),
    name: Optional[str] = Query(None, description="What to call the pass"),
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ImportResponse:
    """`POST /api/documents/{doc_id}/import` — a file becomes a pass.

    The upload is spooled to a temporary file because the action takes a PATH: an
    action's parameters go into the tamper-evident audit row, and a megabyte of
    somebody's transcription in a chain nothing can purge is not a parameter. The path
    is recorded; the content becomes rows.

    The temporary file is removed afterwards **whatever happens**, including on a
    refusal -- an import that refuses should leave nothing behind, least of all a copy
    of a scholar's file in a temp directory.
    """
    import tempfile

    data = await file.read()
    suffix = Path(file.filename or "upload").suffix or ".xml"
    handle = tempfile.NamedTemporaryFile(
        prefix="fichero-import-", suffix=suffix, delete=False
    )
    try:
        handle.write(data)
        handle.close()
        # The pass is named after the file the PERSON chose, not the temporary copy.
        result = registry.invoke(
            db,
            "format.import",
            {
                "document_id": doc_id,
                "path": handle.name,
                **({"format": format_name} if format_name else {}),
                "name": name or file.filename or Path(handle.name).name,
            },
            ctx,
        ).result
    finally:
        Path(handle.name).unlink(missing_ok=True)

    problems = sum(
        1
        for row in db.query(Segment, pass_id=result["pass_id"])
        if row.metadata.get("geometry_problem")
    )
    return ImportResponse(**result, geometry_problems=problems)
