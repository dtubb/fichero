"""Import a PDF's embedded annotation layer (/Annots) as Fichero annotations.

Bbox program step 3's missing half (2026-08-25): the W3C/IIIF EXPORT was
fixed with the 2026-08-20 review, but highlights and notes a person already
made in Preview/Acrobat never entered Fichero at all — the annotation layer
of a marked-up PDF silently vanished on import. Archival rule: what the
source carries, the record keeps.

Pure extraction is separated from persistence so the mapping is testable
without a database. Coordinates: PyMuPDF rects are top-left-origin points in
the page's own frame; normalizing by the page rect yields exactly the
fractions ``SourceAnchor`` stores, with ``rendition_id=None`` — the PDF
page's own frame IS the node frame for its rendered page child.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: PyMuPDF annot type codes → Fichero AnnotationKind values.
#: Text markup (highlight/underline/strikeout/squiggly) keeps its color as a
#: highlight; sticky notes and free text become notes. Everything else —
#: links, form widgets, stamps — is chrome, not scholarship, and is skipped.
_MARKUP_TYPES = {8: "Highlight", 9: "Underline", 10: "Squiggly", 11: "StrikeOut"}
_NOTE_TYPES = {0: "Text", 2: "FreeText"}
_REGION_TYPES = {4: "Square", 5: "Circle", 15: "Ink"}


def extract_pdf_annotations(pdf_path: str) -> list[dict[str, Any]]:
    """Every importable annotation in the PDF, one dict per annot.

    Returns dicts with: ``page_index``, ``kind`` ("highlight" | "note"),
    ``subtype`` (the PDF's own name), ``rect`` (normalized [x, y, w, h],
    top-left origin), ``quads`` (list of normalized quad rects for multi-line
    text markup, empty otherwise), ``text`` (the annot's /Contents),
    ``author``, ``color`` (hex or None), ``created`` (raw PDF date or None).

    A PDF with no annotation layer returns [] — cheaply, so ingest can call
    this unconditionally.
    """
    import fitz  # lazy: keep PyMuPDF off the engine boot path

    results: list[dict[str, Any]] = []
    with fitz.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf):
            page_rect = page.rect
            if page_rect.width <= 0 or page_rect.height <= 0:
                continue

            def normalized(rect: "fitz.Rect") -> list[float]:
                return [
                    rect.x0 / page_rect.width,
                    rect.y0 / page_rect.height,
                    max(rect.width, 0.0) / page_rect.width,
                    max(rect.height, 0.0) / page_rect.height,
                ]

            for annot in page.annots() or []:
                type_code = annot.type[0]
                subtype = annot.type[1]
                if type_code in _MARKUP_TYPES or type_code in _REGION_TYPES:
                    kind = "highlight"
                elif type_code in _NOTE_TYPES:
                    kind = "note"
                else:
                    continue

                quads: list[list[float]] = []
                if type_code in _MARKUP_TYPES and annot.vertices:
                    # QuadPoints arrive as 4 points per quad; each quad is one
                    # line fragment of a multi-line highlight.
                    points = annot.vertices
                    for i in range(0, len(points) - 3, 4):
                        xs = [p[0] for p in points[i:i + 4]]
                        ys = [p[1] for p in points[i:i + 4]]
                        quad = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
                        quads.append(normalized(quad))

                stroke = (annot.colors or {}).get("stroke")
                color = (
                    "#%02x%02x%02x" % tuple(int(c * 255) for c in stroke)
                    if stroke and len(stroke) == 3
                    else None
                )
                info = annot.info or {}
                results.append({
                    "page_index": page_index,
                    "kind": kind,
                    "subtype": subtype,
                    "rect": normalized(annot.rect),
                    "quads": quads,
                    "text": (info.get("content") or "").strip(),
                    "author": (info.get("title") or "").strip() or None,
                    "color": color,
                    "created": info.get("creationDate") or None,
                })
    return results


def import_pdf_annotations(
    db: Any,
    parent_document: Any,
    pdf_path: str,
    page_children_by_index: dict[int, Any] | None = None,
) -> int:
    """Persist the PDF's annotation layer as Annotation rows; returns count.

    Each annotation lands on its PAGE child when one exists (that is the node
    whose frame the coordinates describe), else on the parent with
    ``page_index`` carrying the page. Failure of any single annot logs and
    skips — a torn annot must not fail the import that carries the pages.
    """
    from fichero_server.models import SourceAnchor
    from fichero_server.models.knowledge import Annotation

    extracted = extract_pdf_annotations(pdf_path)
    if not extracted:
        return 0

    pages = page_children_by_index or {}
    saved = 0
    for raw in extracted:
        try:
            page_doc = pages.get(raw["page_index"])
            # The union rect only, for now: SourceAnchor.polygon is ONE
            # closed outline ([[x, y], …]), and a multi-line highlight's
            # quads are disjoint rects — forcing them into a polygon would
            # draw a lie. Per-quad fidelity is a follow-up refinement; the
            # quads are preserved in the extraction should it come.
            target_id = page_doc.id if page_doc else parent_document.id
            anchor = SourceAnchor(
                document_id=target_id,
                rect=raw["rect"],
                space="normalized",
            )
            annotation = Annotation(
                document_id=target_id,
                page_id=page_doc.id if page_doc else None,
                page_index=raw["page_index"],
                kind="highlight" if raw["kind"] == "highlight" else "note",
                text=raw["text"] or None,
                color=raw["color"],
                anchor=anchor,
                # The PDF's own author string when it has one — provenance
                # the file carried; else the layer name, so an imported annot
                # is always distinguishable from one made in Fichero.
                created_by=raw["author"] or "pdf_annots",
            )
            db.save(annotation)
            saved += 1
        except Exception as exc:
            logger.warning(
                "Skipping unimportable PDF annotation (page %s, %s): %s",
                raw.get("page_index"), raw.get("subtype"), exc,
            )
    if saved:
        logger.info(
            "Imported %d PDF annotation(s) from %s", saved, pdf_path
        )
    return saved
