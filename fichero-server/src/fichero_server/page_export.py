"""One page of the library as an interchange file (`source.format.everywhere`, #4943).

The bridge between the library and `fichero_server.formats`. The formats package deliberately touches
no database -- a reader turns bytes into a `SourcePage`, a writer turns a `SourcePage` into bytes --
so this module is where a library page becomes a `SourcePage`, and where the export's CHOICES are
made explicit (`source.format.export-choices`): which pass, which reading order, which kind of
reading. An export that did not say would be ambiguous the moment a page has two passes.

The loss report and the choices travel with the bytes. A report nobody sees is a swallow in a new
costume, so every surface (route, CLI, MCP) hands both to the person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from fichero_server.formats import LossReport, format_named, write_page
from fichero_server.formats.harness import PageOrder, PageSegment, SourcePage


class ExportRefused(LookupError):
    """The thing asked for is not there (no such document, pass or order)."""


@dataclass
class ExportChoices:
    """What was exported, stated (`source.format.export-choices`)."""

    document_id: str
    pass_id: str | None
    pass_basis: str | None
    pass_name: str | None
    order_id: str | None
    order_name: str
    reading_kind: str
    segment_count: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "pass_id": self.pass_id,
            "pass_basis": self.pass_basis,
            "pass_name": self.pass_name,
            "order_id": self.order_id,
            "order_name": self.order_name,
            "reading_kind": self.reading_kind,
            "segment_count": self.segment_count,
            "notes": list(self.notes),
        }


@dataclass
class PageExport:
    data: bytes
    filename: str
    format: str
    choices: ExportChoices
    report: LossReport


def page_from_library(
    db: Any,
    document_id: str,
    *,
    pass_id: str | None = None,
    order_id: str | None = None,
    reading_kind: str = "transcription",
) -> tuple[SourcePage, ExportChoices]:
    """The library's page as the one `SourcePage` every format speaks.

    Defaults are the spec's: the WORKING pass, the order as written, the counting reading of the
    requested kind. Whatever was used is returned in `ExportChoices`.
    """
    from fichero_server.api.routes.document.segment_readings import (
        counting_by_kind,
        document_text,
        readings_of_segment,
    )
    from fichero_server.models import Document, Segment
    from fichero_server.models.reading_orders import AS_WRITTEN, ReadingOrder, ReadingOrderEntry
    from fichero_server.models.segments import SegmentPass

    document = db.get(Document, document_id)
    if document is None:
        raise ExportRefused(f"document not found: {document_id}")
    try:
        derived = document_text(db, document_id, pass_id=pass_id, order=order_id, kind=reading_kind)
    except LookupError as exc:
        raise ExportRefused(str(exc)) from exc
    if derived.pass_id is None:
        raise ExportRefused(
            f"document {document_id} has no pass to export: nothing has been segmented or imported"
        )
    pass_row = db.get(SegmentPass, derived.pass_id)
    order_row = db.get(ReadingOrder, order_id) if order_id else None
    if order_id and order_row is None:
        raise ExportRefused(f"reading order not found: {order_id}")

    choices = ExportChoices(
        document_id=document_id,
        pass_id=derived.pass_id,
        pass_basis=derived.pass_basis,
        pass_name=pass_row.name if pass_row else None,
        order_id=order_id,
        order_name=order_row.name if order_row else AS_WRITTEN,
        reading_kind=reading_kind,
    )

    from fichero_server.api.routes.document.segment_readings import _segment_order_key

    # The page's order, the same key as its text (#5137): the database's row order is none.
    rows = sorted(
        (r for r in db.query(Segment, pass_id=derived.pass_id) if r.deleted_at is None),
        key=_segment_order_key,
    )
    ids = {r.id for r in rows}
    segments: list[PageSegment] = []
    for row in rows:
        items = [
            i for i in readings_of_segment(db, row.id)
            if i.kind == reading_kind and not i.retracted
        ]
        counted = counting_by_kind(db, row.id, items).get(reading_kind) if items else None
        counting_id = counted.representation_id if counted else None
        items.sort(key=lambda i: (i.id != counting_id, i.created_at))
        anchor = row.anchor
        # A segment its file placed nowhere is written with no shape: its whole-page anchor is
        # where the library keeps it, not a place anybody drew (`format_import.SHAPE_UNSTATED`).
        unstated = row.metadata.get("shape") == "unstated"
        segments.append(
            PageSegment(
                kind=row.kind,
                rect=list(anchor.rect) if anchor.rect and not unstated else None,
                polygon=[list(p) for p in anchor.polygon] if anchor.polygon and not unstated else None,
                baseline=[list(p) for p in row.baseline] if row.baseline else None,
                language=row.language,
                script=row.script,
                direction=row.direction,
                readings=[(i.kind, i.content) for i in items],
                ref=row.id,
                parent_ref=row.parent_segment_id if row.parent_segment_id in ids else None,
                # What the IMPORT kept because the model has no field for it
                # (`source.format.keeps-unrecognised`). Read back out here, or a file
                # imported into a library and then exported loses what the import
                # kept -- the write-back half was true format-to-format and false
                # library-to-format, which is how it passed every round-trip test.
                #
                # eScriptorium's `custom="structure {type:title;}"` is the case: it
                # survives PAGE XML in and out, and before this it did not survive a
                # library in between.
                foreign=dict(row.metadata.get("foreign") or {}),
            )
        )
    choices.segment_count = len(segments)
    if any(r.is_furniture for r in rows):
        choices.notes.append(
            "furniture segments (running heads, folio numbers) are included as segments; the "
            "derived page TEXT leaves them out"
        )

    orders: list[PageOrder] = []
    for order in db.query(ReadingOrder, pass_id=derived.pass_id):
        if order.deleted_at is not None:
            continue
        entries = sorted(db.query(ReadingOrderEntry, order_id=order.id), key=lambda e: e.position)
        orders.append(
            PageOrder(name=order.name, refs=[e.segment_id for e in entries if e.segment_id in ids], kind=order.kind)
        )
    orders.sort(key=lambda o: (o.name != choices.order_name, o.name != AS_WRITTEN))
    if not orders:
        # No named order was recorded: the order is box order, and it is written as one so the
        # format's reading order is never silently absent.
        ordered = sorted(rows, key=_segment_order_key)
        orders.append(PageOrder(name=AS_WRITTEN, refs=[r.id for r in ordered if r.kind == "region"] or [r.id for r in ordered]))
        choices.notes.append("no named reading order is recorded for this pass; box order was written")

    width = document.width
    height = document.height
    page = SourcePage(
        producer=(pass_row.model or pass_row.provider or pass_row.name) if pass_row else None,
        image_name=PurePosixPath(document.path or document.name or "").name or document.name,
        image_size=(int(width), int(height)) if width and height else None,
        # The DOCUMENT's own three facts (#5085), read from the document rather than
        # resolved onto every segment: a page states its language once, and a writer
        # that has to look at a line to find it will report a page with no language.
        language=document.language,
        script=document.script,
        direction=document.direction,
        segments=segments,
        orders=orders,
        signs=_declared_signs_used(db, segments),
    )
    return page, choices


def _declared_signs_used(db: Any, segments: list[PageSegment]) -> list[dict[str, Any]]:
    """The project's declared signs whose characters this page's readings use
    (`source.sign.export-honest`, #4939), for a format that can say what they mean."""
    from fichero_server.models.signs import DeclaredSign, code_point_char

    text = "".join(reading[1] for segment in segments for reading in segment.readings)
    return [
        {"id": sign.id, "name": sign.name, "code_point": sign.code_point,
         "list_references": list(sign.list_references)}
        for sign in db.all(DeclaredSign)
        if sign.deleted_at is None and sign.code_point and code_point_char(sign.code_point) in text
    ]


def export_page(
    db: Any,
    document_id: str,
    format_name: str,
    *,
    pass_id: str | None = None,
    order_id: str | None = None,
    reading_kind: str = "transcription",
) -> PageExport:
    """One page, validated, with the loss report and the choices that were made."""
    spec = format_named(format_name)  # UnknownFormat names what this build has
    page, choices = page_from_library(
        db, document_id, pass_id=pass_id, order_id=order_id, reading_kind=reading_kind
    )
    data, report = write_page(spec.name, page)
    stem = PurePosixPath(page.image_name or document_id).stem or document_id
    extension = {"tei": ".tei.xml", "pagexml": ".page.xml", "alto": ".alto.xml"}.get(spec.name, ".xml")
    return PageExport(data=data, filename=f"{stem}{extension}", format=spec.name, choices=choices, report=report)
