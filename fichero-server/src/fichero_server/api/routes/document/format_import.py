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
* **Its provenance says it came from a file** (`external_import`, #5150): `actor` names who
  brought it and `provider` what the file says made it. Bringing a file is not writing it.

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

import re

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
)
from fichero_server.db import Database
from fichero_server.formats import UnknownFormat, format_for, format_named, read_page
from fichero_server.formats.harness import SourcePage
from fichero_server.models import ContentRepresentation, Document, Segment
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
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


def keep_original(db: Database, path: Path) -> str | None:
    """Copy an imported file into the library package, byte for byte, the way every library file
    is kept (`ingest._copy_to_library`: `files/<shard>/`, APFS clone where it can, verified), and
    answer its package-relative path (#5149). None for a library with no package on disk."""
    from fichero_server.importers.ingest import _copy_to_library

    if not getattr(db, "path", None):
        return None
    package = Path(db.path).parent
    kept = _copy_to_library(path, package)
    return kept.relative_to(package).as_posix()


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
    #: The file was UPLOADED into a temp folder the engine made: a YOLO dataset's class names
    #: are looked for in that folder only, never in the engine's folders above it.
    uploaded: bool = False
    #: A multi-page file (TEI: one page per `<pb>`): which pages, numbered from 1 in the file's
    #: order, become this pass. Omitted, the first. Several are ONE pass on this document --
    #: the Digital Genji puts two printed pages on one scan (#5143).
    pages: Optional[list[int]] = None


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
    if spec.name == "yolo":
        # A YOLO file's numbers mean what its DATASET says (#5130): read `classes.txt` /
        # `data.yaml` beside it, so YALTAi's 4 arrives as `MainZone`, not as our "region".
        from fichero_server.formats.yolo import class_names_beside, read as read_yolo

        names = class_names_beside(path, walk_up=not params.uploaded)
        page = read_yolo(data, names)
    elif spec.name == "qgis-points":
        # A .points file gives GCP pixel ends and no image size (#5122 maps C4): the page's own
        # recorded size places them; without one they cannot be placed, and that is said.
        from fichero_server.formats.qgis_points import read_points

        target = db.get(Document, params.document_id)
        width, height = (target.width, target.height) if target is not None else (None, None)
        if not (width and height):
            raise HTTPException(
                status_code=422,
                detail=f"{path.name} gives control points in pixels and no image size, and this page's "
                       "size is not recorded, so they cannot be placed on it",
            )
        page = read_points(data, (int(width), int(height)))
    elif spec.name == "tesseract-box":
        # Pixels from a BOTTOM-left origin and no image size (#5174): the page's own recorded size
        # places them, as for .points; without one they cannot be placed, and that is said.
        from fichero_server.formats.tesseract_box import read_box

        target = db.get(Document, params.document_id)
        width, height = (target.width, target.height) if target is not None else (None, None)
        if not (width and height):
            raise HTTPException(
                status_code=422,
                detail=f"{path.name} gives character boxes in pixels from the bottom of an image of no "
                       "stated size, and this page's size is not recorded, so they cannot be placed on it",
            )
        try:
            page = read_box(data, (int(width), int(height)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{path.name}: {exc}") from exc
    elif spec.name == "tei":
        page, pages_in_file, left_out = _tei_pages_taken(data, params.pages, path.name)
    else:
        if params.pages and params.pages != [1]:
            raise HTTPException(
                status_code=422,
                detail=f"{path.name} is a {spec.name} file: it has one page, so `pages` cannot name others",
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
        # Kept only once the file has been READ: an unreadable file leaves nothing behind (#5149).
        original=keep_original(db, path),
    )

    if spec.name == "tei":
        # Pages of the file NOT in this pass, named (#5143): a 25-page edition imported as its
        # first page used to report success and drop 24 pages without a word.
        result["pages_in_file"] = pages_in_file
        result["pages_left_out"] = left_out
    if spec.name == "yolo":
        # Class numbers nobody named: said out loud, not guessed quietly (#5138). Their boxes were
        # read by Fichero's own convention, which is right only for a file Fichero wrote.
        result["unknown_classes"] = sorted({
            s.foreign["yolo:class"] for s in page.segments if "yolo:class_name" not in s.foreign
        })
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


def _tei_pages_taken(data: bytes, wanted: list[int] | None, filename: str) -> tuple[Any, int, list[str]]:
    """The TEI pages this import takes, as ONE page; how many the file has; the ones left out.

    Several pages taken are merged in the file's order: their segments (whose refs are unique
    across the file) and their reading orders, one after the other. Each line keeps its own
    shape, so two printed pages on one scan stay two places on it.
    """
    from dataclasses import replace

    from fichero_server.formats.harness import PageOrder
    from fichero_server.formats.tei import describe_page, read_pages

    pages = read_pages(data)
    numbers = sorted(set(wanted or [1]))
    outside = [n for n in numbers if not 1 <= n <= len(pages)]
    if outside:
        raise HTTPException(
            status_code=422,
            detail=f"{filename} has {len(pages)} page(s); there is no page {', '.join(map(str, outside))}",
        )
    taken = [pages[n - 1] for n in numbers]
    page = taken[0]
    if len(taken) > 1:
        refs = [ref for p in taken for order in p.orders[:1] for ref in order.refs]
        page = replace(
            page,
            segments=[s for p in taken for s in p.segments],
            orders=[PageOrder(name=page.orders[0].name if page.orders else "as-written", refs=refs)]
            if refs else [],
        )
    left_out = [describe_page(p, n) for n, p in enumerate(pages, start=1) if n not in numbers]
    return page, len(pages), left_out


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

    point = getattr(segment, "point", None)
    if point is not None and segment.rect is None and segment.polygon is None:
        # A POINT (a ground control point, #5122): one place, not an area. Outside the page it
        # cannot be drawn, so it is refused like any other shape that leaves the page.
        if not (0.0 <= point[0] <= 1.0 and 0.0 <= point[1] <= 1.0):
            return None, f"point {[round(v, 4) for v in point]} lies outside the page the file declares"
        return SourceAnchor(
            document_id=document_id, granularity=segment.kind,
            shapes=[{"kind": "point", "points": [list(point)]}],
        ), None

    if segment.rect is None and segment.polygon is None:
        # A TEXT-ONLY segment: the file states no place for it at all (an EpiDoc edition, a TEI
        # line whose `<lb>` names no zone). It is not a shape outside the page -- there is no
        # shape -- so it is never refused. It is somewhere on THIS page, which is all the file
        # says, so it is anchored to the page and marked `shape: unstated`, and the export writes
        # no shape for it. Refusing it lost the transcription (acceptance defect 3).
        return SourceAnchor(document_id=document_id, rect=[0.0, 0.0, 1.0, 1.0], granularity=segment.kind), None

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


#: Where a segment stands in the file it was imported from (#5137): the order the page's text
#: and its export follow. `segment_readings._segment_order_key` reads it.
FILE_POSITION = "file_position"


#: A segment whose file stated no place for it (`_anchor_for`): its anchor is the whole page,
#: and nothing may draw it or export it as a shape.
SHAPE = "shape"
SHAPE_UNSTATED = "unstated"

#: The id the element had in its file (PAGE `@id`, ALTO `@ID`, TEI `@xml:id`).
SOURCE_ID = "source_id"

_PAGE_STRUCTURE_TYPE = re.compile(r"structure\s*\{[^}]*?type\s*:\s*([^;}]+)")


def raw_kind(segment: Any) -> str | None:
    """The file's own name for what a segment is, kept beside our `kind` (#5138).

    ALTO: the label of the first declared tag it references (SegmOnto's `MainZone`, Benedict's
    `LatinLine`). PAGE XML: `custom="structure {type:...}"` (eScriptorium and Transkribus). YOLO:
    the dataset's class name. None when the file names nothing.
    """
    for tag in segment.foreign.get("alto:tags", []):
        if tag.get("LABEL"):
            return str(tag["LABEL"])
    match = _PAGE_STRUCTURE_TYPE.search(str(segment.foreign.get("custom") or ""))
    if match:
        return match.group(1).strip()
    name = segment.foreign.get("yolo:class_name")
    return str(name) if name else None


def file_positions(order: list[tuple[str, Any]], reading_order: list[str]) -> dict[str, int]:
    """Each segment's place in the FILE's order: its top-level blocks in the file's own reading
    order (PAGE `ReadingOrder`, ALTO block order), blocks the reading order does not name after
    them in file order, and inside each block its lines and words in the order the file wrote them.

    The file's order, not the page's geometry (#5137): top-then-left interleaves two columns line by
    line and scrambles vertical right-to-left columns, and only the file knows which it meant.
    """
    known = {ref for ref, _segment in order}
    children: dict[str | None, list[str]] = {}
    for ref, segment in order:
        parent = segment.parent_ref if segment.parent_ref in known else None
        children.setdefault(parent, []).append(ref)
    roots = children.get(None, [])
    root_set = set(roots)
    named = [ref for ref in dict.fromkeys(reading_order) if ref in root_set]
    ordered_roots = named + [ref for ref in roots if ref not in set(named)]
    positions: dict[str, int] = {}
    stack = list(reversed(ordered_roots))
    while stack:
        ref = stack.pop()
        if ref in positions:
            continue
        positions[ref] = len(positions)
        stack.extend(reversed(children.get(ref, [])))
    for ref, _segment in order:  # a cycle of parents is unreachable from a root: file order
        positions.setdefault(ref, len(positions))
    return positions


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
    original: str | None = None,
) -> dict[str, Any]:
    """One `SourcePage` as a pass, its segments, their readings and its order.

    `original` is where the file's own bytes were kept (`keep_original`), package-relative.


    In BATCHES, and in this order: the pass, then the segments, then the readings,
    then the order's entries. Each `save_many` is one statement, and nothing places a
    segment by searching its siblings — the import of a dense page is where that cost
    would land.
    """
    # WHO MADE THIS: the FILE did (#5150). A person bringing a file is not its author: an
    # imported PAGE/ALTO page is often a machine's (Transkribus HTR, eScriptorium, OCR), and
    # stamping it `human` was the #4868/#4869 class again -- and put every import in the
    # hand-curated tier of the pass ladder. The pass, its segments and its readings are
    # `external_import`; `actor` says who brought it, `provider` what the file says made it
    # (`SourcePage.producer`: PAGE Creator/Transkribus, ALTO processingSoftware, TEI respStmt).
    # A person's later edits on the pass are theirs as usual.
    imported = ProvenanceKind.external_import
    pass_row = SegmentPass(
        document_id=document_id,
        name=pass_name,
        provenance_kind=imported,
        actor=ctx.actor,
        provider=page.producer,
        run_id=ctx.run_id,
        import_file=source_name,
        import_checksum=checksum,
        import_format=format_name,
        import_original=original,
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
    positions = file_positions(order, page.orders[0].refs if page.orders else [])

    # Anchors are built ONCE and the placeability check reads the same objects, rather
    # than constructing each anchor twice. **Not a measured speed-up**: building them
    # twice and once both came out around a minute for 20,000 segments on a machine
    # with other work on it, so the honest claim is only that doing the same work once
    # is not worse. An import either happens or does not, so the check still runs
    # before the first write.
    # A georeferencing file (#5122): its GCPs keep BOTH ends -- the pixel end as a point segment,
    # the world end as a `world-point` reading -- and the pass says its transformation. Refused by
    # name before the model existed.
    georeferencing = any(segment.world is not None for _ref, segment in order)
    transformation = None
    if georeferencing:
        from fichero_server.models.geo import transformation_from_iiif

        try:
            transformation = transformation_from_iiif(page.transformation)
        except ValueError as refusal:
            raise _as_http_error(refusal) from refusal
        pass_row.transformation = transformation
        db.save(pass_row)

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
                kind_raw=raw_kind(segment),
            ),
            actor=ctx.actor,
            provenance_kind=imported,
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
        row.metadata = {**row.metadata, FILE_POSITION: positions[ref]}
        if segment.rect is None and segment.polygon is None:
            row.metadata = {**row.metadata, SHAPE: SHAPE_UNSTATED}
        if segment.ref:
            # The file's own id for this element (#5138): how a segment is traced back to the
            # element it came from. Never used as OUR id -- a re-import mints new ones.
            row.metadata = {**row.metadata, SOURCE_ID: segment.ref}
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
                    provenance_kind=imported,
                    created_by=ctx.actor or None,
                )
            )
    # A GCP's world end (#5122): a `world-point` reading, WGS 84 lon/lat as the georef extension
    # writes it, through the one checker every world point goes through (`models.geo`).
    if georeferencing:
        from fichero_server.models.geo import WORLD_POINT, world_point

        for ref, segment in order:
            if segment.world is None:
                continue
            readings.append(ContentRepresentation(
                document_id=document_id, segment_id=ids_by_ref[ref], kind=WORLD_POINT,
                # The CRS the FILE states (a .points file's `#CRS`, or none: `unknown`), EPSG:4326
                # where the format fixes it (IIIF georef); held unconverted when it is not WGS 84.
                content=world_point({"coordinates": list(segment.world),
                                     "crs": segment.foreign.get("gcp:crs", "EPSG:4326"),
                                     "axis_order": segment.foreign.get("gcp:axis_order", "lon,lat")}).model_dump_json(),
                source_anchor=SourceAnchor(document_id=document_id, granularity=segment.kind),
                provenance_kind=imported, created_by=ctx.actor or None,
            ))
    if readings:
        db.save_many(readings)

    # What the file's editor SAID about stretches of the text (#5179): unclear, lost, restored,
    # supplied, superfluous, added -- editorial facts on the reading this import just made, the
    # file's claim (`external_import`, no person here as their maker), written in this same audited
    # action so its undo takes them with the pass. What cannot be a fact is named, not dropped.
    first_reading = {}
    for reading in readings:
        first_reading.setdefault(reading.segment_id, reading)
    facts, not_imported = _editorial_facts(order, ids_by_ref, first_reading, source_name, imported)
    if facts:
        db.save_many(facts)

    # Each GCP CONTROLS its mask (#5122): a typed link, because a sheet with two maps has two masks
    # and a GCP belongs to one by what the file says, not by lying inside it.
    if georeferencing:
        from fichero_server.formats.iiif_georef import MASK_LINK
        from fichero_server.models.typed_links import TypedLink

        links = [
            TypedLink(from_id=ids_by_ref[ref], to_id=ids_by_ref[segment.foreign[MASK_LINK]],
                      link_type="controls", provenance_kind=imported, created_by=ctx.actor or None)
            for ref, segment in order
            if segment.foreign.get(MASK_LINK) in ids_by_ref
        ]
        if links:
            db.save_many(links)

    # The hands the file names (an EpiDoc `<handShift>`), as project hands attributed to these
    # segments with the file as their source (slice 14, #4935).
    hands_by_segment = {
        ids_by_ref[ref]: list(segment.foreign.get("tei:hands") or [])
        for ref, segment in order if segment.foreign.get("tei:hands")
    }
    hand_attributions = 0
    if hands_by_segment:
        from fichero_server.api.routes.document.hands import hands_from_file

        hand_attributions = hands_from_file(
            db, hands_by_segment, edition=_edition_title(page) or source_name,
            source=f"file: {source_name}", ctx=ctx,
        )

    # The file's own reading order, as a named order -- EVERY segment, nested as the file nests
    # them (lines under their block, words under their line), in the file's order: the same
    # `file_position` the page's text follows (#5137), so the two cannot disagree. Every level has
    # entries, so a LINE can be moved, not only a block (Q5, lines move in the Reader's text).
    # Written directly in the file's sequence: placing each entry against its siblings would be
    # quadratic, and the file has already told us the order.
    entries: list[ReadingOrderEntry] = []
    if order:
        as_written = ensure_as_written_order(
            db,
            document_id=document_id,
            pass_id=pass_row.id,
            provenance_kind=pass_row.provenance_kind,
            created_by=ctx.actor or None,
        )
        entry_by_ref: dict[str, ReadingOrderEntry] = {}
        for ref, segment in sorted(order, key=lambda item: positions[item[0]]):
            parent = entry_by_ref.get(segment.parent_ref or "")
            entry = ReadingOrderEntry(
                order_id=as_written.id, segment_id=ids_by_ref[ref],
                position=float(positions[ref] + 1),
                parent_entry_id=parent.id if parent is not None else None,
            )
            entry_by_ref[ref] = entry
            entries.append(entry)
        db.save_many(entries)

    return {
        "pass_id": pass_row.id,
        "format": format_name,
        "segments": len(rows),
        "readings": len(readings),
        "order_entries": len(entries),
        "checksum": checksum,
        "hand_attributions": hand_attributions,
        "editorial_facts": len(facts),
        # What the file marked that the library does not hold, and why (#5179): never dropped quietly.
        "not_imported": not_imported,
    }


#: TEI `@cert` in words, as a certainty (#5179, the mapping).
_CERTAINTY = {"high": 0.9, "medium": 0.6, "low": 0.3}
_PAGE_UNCLEAR = re.compile(r"unclear\s*\{([^}]*)\}")


def _editorial_facts(order, ids_by_ref, first_reading, source_name, imported):
    """(EditorialFact rows, not-imported notes) for the marks the file makes (#5179's mapping):
    PAGE `unclear {offset;length}` in a line's `custom`, and TEI `tei:marks` recorded by the reader.
    Spans are code points into the reading made for that segment."""
    from fichero_server.formats.tei import TEI_MARKS
    from fichero_server.models.editorial import EditorialFact

    facts: list[EditorialFact] = []
    skipped: dict[tuple[str, str], int] = {}

    def skip(what: str, why: str) -> None:
        skipped[(what, why)] = skipped.get((what, why), 0) + 1

    for ref, segment in order:
        reading = first_reading.get(ids_by_ref[ref])
        text = reading.content if reading is not None else ""

        def fact(kind, start=None, end=None, **fields):
            spanned = start is not None
            if spanned and end is not None:
                end = min(end, len(text))
                if start >= end:
                    skip(f"an empty <{kind}> mark", "it covers no letters of the reading")
                    return
            facts.append(EditorialFact(
                segment_id=ids_by_ref[ref], kind=kind,
                representation_id=reading.id if (spanned and reading is not None) else None,
                char_start=start, char_end=end,
                provenance_kind=imported, created_by=None, source=f"file: {source_name}",
                **{k: v for k, v in fields.items() if v is not None},
            ))

        for body in _PAGE_UNCLEAR.findall(str(segment.foreign.get("custom") or "")):
            values = dict(part.split(":", 1) for part in body.replace(" ", "").split(";") if ":" in part)
            try:
                offset, length = int(values["offset"]), int(values["length"])
            except (KeyError, ValueError):
                skip("a PAGE unclear mark", "it states no offset and length")
                continue
            fact("unclear", offset, offset + length)

        for mark in segment.foreign.get(TEI_MARKS, []):
            tag, start, end, attrs = mark["tag"], mark["start"], mark["end"], mark.get("attrs", {})
            certainty = _CERTAINTY.get(attrs.get("cert", ""))
            quantity = float(attrs["quantity"]) if attrs.get("quantity", "").replace(".", "", 1).isdigit() else None
            extent = {"extent_quantity": quantity, "extent_unit": attrs.get("unit"),
                      "extent": None if quantity is not None else attrs.get("extent", "unknown")}
            if tag == "unclear":
                fact("unclear", start, end, reason=attrs.get("reason"), certainty=certainty)
            elif tag == "supplied":
                reason = attrs.get("reason")
                if reason == "lost":
                    fact("restored", start, end, certainty=certainty)
                else:
                    fact("supplied", start, end, certainty=certainty,
                         reason="omitted by the scribe" if reason == "omitted" else reason)
            elif tag == "gap":
                if attrs.get("reason") == "illegible":
                    fact("unclear", reason="illegible", **extent)     # position-only is not allowed for unclear
                else:
                    fact("lost", start, None, **extent)               # a position (abe343ae9)
            elif tag == "surplus":
                fact("superfluous", start, end)
            elif tag == "add":
                fact("added", start, end, place=attrs.get("place"))
            elif tag == "del":
                # Diplomatic (ruled 2026-09-28, #5179): the deleted letters are IN the reading and
                # this fact spans them, drawn ⟦ ⟧ -- never silently dropped from what the page says.
                fact("deleted", start, end)
            elif tag == "delSpan":
                skip("a deletion across lines (<delSpan>)", "it has no one reading to span")
    return facts, [{"what": what, "count": count, "why": why} for (what, why), count in sorted(skipped.items())]


def _edition_title(page: SourcePage) -> str | None:
    """A TEI file's own title (the first `<title>` in its header), to name the hands it declares."""
    header = str((page.foreign.get("tei") or {}).get("teiHeader") or "")
    match = re.search(r"<title[^>]*>([^<]+)</title>", header)
    return match.group(1).strip() if match else None


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
    if isinstance(exc, ShapesOutsideThePage):
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


#: The files a YOLO dataset keeps its class names in (`formats.yolo.class_names_beside`).
DATASET_FILES = frozenset({"classes.txt", "data.yaml"})


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
    #: YOLO: class numbers the file used that no dataset file named. Their boxes were read by
    #: Fichero's own convention; send the dataset's `classes.txt` or `data.yaml` to name them.
    unknown_classes: list[int] = []
    #: How many segments had a shape the file could not express properly. Surfaced
    #: rather than buried in rows: a page where forty boxes were repaired is a page
    #: somebody should look at.
    geometry_problems: int = 0
    #: TEI: how many pages (`<pb>`s) the file has, and each one NOT in this pass, by its `n` and
    #: what it points at (#5143). A multi-page edition imported onto one image takes one page;
    #: the rest are named here rather than dropped without a word.
    pages_in_file: int = 1
    pages_left_out: list[str] = []


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
    dataset: Optional[UploadFile] = File(
        None,
        description=(
            "YOLO only: the dataset's `classes.txt` or `data.yaml`, which says what each class "
            "number means. Placed beside the labels, where the import looks for it."
        ),
    ),
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
    import shutil
    import tempfile

    if dataset is not None and Path(dataset.filename or "").name not in DATASET_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"a YOLO dataset file is {' or '.join(sorted(DATASET_FILES))}, not {dataset.filename!r}",
        )
    data = await file.read()
    suffix = Path(file.filename or "upload").suffix or ".xml"
    # A DIRECTORY, not a lone file (#5138): a YOLO file's numbers mean what the dataset file
    # BESIDE it says, and a one-file upload used to leave that behind, so a drop capital arrived
    # as a `word`. The dataset file goes where `class_names_beside` looks.
    folder = Path(tempfile.mkdtemp(prefix="fichero-import-"))
    try:
        label_path = folder / f"upload{suffix}"
        label_path.write_bytes(data)
        if dataset is not None:
            (folder / Path(dataset.filename).name).write_bytes(await dataset.read())
        # The pass is named after the file the PERSON chose, not the temporary copy.
        result = registry.invoke(
            db,
            "format.import",
            {
                "document_id": doc_id,
                "path": str(label_path),
                **({"format": format_name} if format_name else {}),
                "name": name or file.filename or label_path.name,
                "uploaded": True,
            },
            ctx,
        ).result
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    problems = sum(
        1
        for row in db.query(Segment, pass_id=result["pass_id"])
        if row.metadata.get("geometry_problem")
    )
    return ImportResponse(**result, geometry_problems=problems)
