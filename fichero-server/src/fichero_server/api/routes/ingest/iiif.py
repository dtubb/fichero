"""IIIF API Routes (dev tier, backend-first 0.1.0 slice).

Embedded IIIF Image Server API — serves local images via IIIF Image API v2.1.
References: https://iiif.io/api/image/2.1/
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fichero_server.models.anchors import AnchorSpace
from fichero_server.api.routes.document.renditions import IMAGE_MEDIA_TYPES
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models.knowledge import Annotation, AnnotationKind
from fichero_server.models import Document, FileType
from fichero_server.security.path_security import resolve_document_source_path
from fichero_server.db.storage import get_display, get_thumbnail, resolve_source
from fichero_server.db.storage import settings as storage_settings
from fichero_server.core.utf16_offsets import utf16_range_to_codepoint_range

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iiif", tags=["iiif"])


# =============================================================================
# IIIF Constants
# =============================================================================

IIIF_API_VERSION = "2.1"
IIIF_CONTEXT = "http://iiif.io/api/image/2/context.json"


# =============================================================================
# IIIF Image Information Response
# =============================================================================


class ImageServiceProfile(BaseModel):
    """IIIF Image API service profile."""

    formats: list[str] = Field(default_factory=lambda: ["jpg", "png"])
    qualities: list[str] = Field(default_factory=lambda: ["default", "color", "gray"])
    supports: list[str] = Field(default_factory=list)


class ImageInfoResponse(BaseModel):
    """IIIF Image Information Response (info.json)."""

    model_config = ConfigDict(populate_by_name=True)

    context: str = IIIF_CONTEXT
    id: str = Field(..., alias="@id")
    protocol: str = "http://iiif.io/api/image"
    width: int
    height: int
    tiles: list[dict[str, Any]] | None = None
    profile: list[Any] = Field(default_factory=list)


# =============================================================================
# IIIF Manifest Models
# =============================================================================


def _get_image_path(
    doc: Document, library_root: Path | None = None
) -> Path | None:
    """Get the image file path for a document."""
    if doc.file_type not in (FileType.image, FileType.pdf) and not doc.path:
        return None

    candidate = (
        get_display(doc, package_path=library_root)
        or get_thumbnail(doc, package_path=library_root)
        or resolve_source(doc, library_root=library_root)
    )
    if candidate is None:
        return None
    # Same authority as db.storage.resolve_source: a LINK-mode source lives
    # where the user left it, not inside the package (#4230).
    return resolve_document_source_path(
        candidate, library_root, storage_base=storage_settings.base_path
    )


def _get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Get image dimensions."""
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as exc:
        logger.error(f"Failed to get image dimensions: {exc}")
        return (1024, 1024)  # Default fallback


def _document_or_404(db: Database, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or getattr(doc, "deleted_at", None) is not None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return doc


def _iiif_base_url(document_id: str) -> str:
    return f"/api/iiif/iiif/{document_id}"


def _iiif_canvas_id(document_id: str, rendition_id: str | None = None) -> str:
    """The canvas an annotation's coordinates belong to.

    Was hard-coded to `/canvas/1` for every annotation on every document
    (2026-08-20 review): a synthetic per-document canvas with NO rendition
    dimension, so an exported annotation could not say which image its
    percentages were percentages OF. W3C gives `target.source` for exactly
    this and it was being filled with a constant.

    A rendition-scoped canvas is emitted when the anchor names one; documents
    whose annotations predate rendition-aware anchors still get canvas/1, which
    is the honest answer for a coordinate whose frame was never recorded.
    """
    if rendition_id:
        return f"{_iiif_base_url(document_id)}/canvas/{rendition_id}"
    return f"{_iiif_base_url(document_id)}/canvas/1"


def _annotation_motivation(kind: AnnotationKind) -> str:
    return {
        AnnotationKind.highlight: "highlighting",
        AnnotationKind.note: "commenting",
        AnnotationKind.comment: "commenting",
        AnnotationKind.bookmark: "bookmarking",
        AnnotationKind.rating: "assessing",
    }.get(kind, "commenting")


def _annotation_exact_text(doc: Document, ann: Annotation) -> str | None:
    if (
        not doc.page_content
        or ann.char_start is None
        or ann.char_end is None
    ):
        return None
    cp_start, cp_end = utf16_range_to_codepoint_range(
        doc.page_content, ann.char_start, ann.char_end
    )
    return doc.page_content[cp_start:cp_end] or None


def _annotation_target(doc: Document, ann: Annotation) -> dict[str, Any]:
    selectors: list[dict[str, Any]] = []
    if ann.char_start is not None and ann.char_end is not None:
        selectors.append(
            {
                "type": "TextPositionSelector",
                "start": ann.char_start,
                "end": ann.char_end,
            }
        )
        if exact := _annotation_exact_text(doc, ann):
            selectors.append(
                {
                    "type": "TextQuoteSelector",
                    "exact": exact,
                }
            )
    rect = ann.anchor.rect if ann.anchor else None
    region_selector: dict[str, Any] | None = None
    if rect and len(rect) == 4:
        x, y, width, height = rect
        # Media Fragments defines BOTH forms, and which one is correct depends
        # on the space the anchor declares. Emitting `pct:` for a rect that is
        # already in pixels would put a silently wrong region into an archival
        # export — worse than a wrong crop on screen, because it leaves the
        # building as standards-compliant data somebody else will trust.
        if ann.anchor and ann.anchor.space is AnchorSpace.pixel:
            value = f"xywh={x:g},{y:g},{width:g},{height:g}"
        else:
            value = (
                f"xywh=pct:{x * 100:g},{y * 100:g},"
                f"{width * 100:g},{height * 100:g}"
            )
        region_selector = {
            "type": "FragmentSelector",
            "conformsTo": "http://www.w3.org/TR/media-frags/",
            "value": value,
        }

    target: dict[str, Any] = {
        "source": _iiif_canvas_id(
            doc.id, ann.anchor.rendition_id if ann.anchor else None
        )
    }

    # NESTED, not flattened (2026-08-20 review). A bare list of selectors reads
    # as "ANY of these locates the target"; the real relationship is "this text
    # span, WITHIN this region". W3C's `refinedBy` says precisely that, and
    # emitting a flat list threw the containment away — the export claimed less
    # than the data knew.
    if region_selector and selectors:
        region_selector["refinedBy"] = (
            selectors[0] if len(selectors) == 1 else selectors
        )
        target["selector"] = region_selector
    elif region_selector:
        target["selector"] = region_selector
    elif selectors:
        target["selector"] = selectors[0] if len(selectors) == 1 else selectors
    return target


def build_document_annotation_page(db: Database, doc: Document) -> dict[str, Any]:
    annotations = _dedupe_annotations(
        db.query_in(Annotation, "document_id", [doc.id]),
        db.query_in(Annotation, "page_id", [doc.id]),
    )
    items: list[dict[str, Any]] = []
    for ann in annotations:
        body = None
        if ann.text:
            body = {
                "type": "TextualBody",
                "value": ann.text,
                "format": "text/plain",
            }
        items.append(
            {
                "id": f"/api/documents/{doc.id}/annotations/{ann.id}",
                "type": "Annotation",
                "motivation": _annotation_motivation(ann.kind),
                "body": body,
                "target": _annotation_target(doc, ann),
            }
        )
    items.extend(_record_annotations(db, doc))
    return {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": f"/api/documents/{doc.id}/annotations.jsonld",
        "type": "AnnotationPage",
        "items": items,
    }


def _record_creator(made_by: dict[str, Any] | None, *, provider: str | None = None,
                    model: str | None = None) -> dict[str, Any] | None:
    """Who made a record, as a W3C `creator`: the run and its model (Software) for a machine's, the
    person for a person's; None when the record does not say."""
    if made_by and made_by.get("by") == "person":
        return {"type": "Person", "name": made_by.get("name") or "person"}
    made_by = made_by or {}
    run_id, model, provider = made_by.get("run_id"), made_by.get("model") or model, made_by.get("provider") or provider
    if not (run_id or model or provider):
        return None
    creator: dict[str, Any] = {"type": "Software", "name": model or provider}
    if run_id:
        creator["id"] = f"fichero:run:{run_id}"
    if provider and model:
        creator["nickname"] = provider
    return creator


def _record_target(doc: Document, segment_id: str | None, seg_start: int | None, seg_end: int | None,
                   reading_id: str | None, page_start: int | None, page_end: int | None,
                   exact: str | None) -> dict[str, Any] | None:
    """A record's place as a W3C target: its line (the segment) with the span in the reading it was
    measured on when the page is tied, else the page with the words it quotes (and their position in
    the page text when the words are there). None when it has no place to point at."""
    if segment_id and seg_start is not None and seg_end is not None:
        selectors: list[dict[str, Any]] = [{"type": "TextPositionSelector", "start": seg_start, "end": seg_end}]
        if exact:
            selectors.append({"type": "TextQuoteSelector", "exact": exact})
        target: dict[str, Any] = {"source": f"/api/segments/{segment_id}",
                                  "scope": f"/api/documents/{doc.id}", "selector": selectors}
        if reading_id:
            target["reading"] = f"/api/content-representations/{reading_id}"
        return target
    text = doc.page_content or ""
    if page_start is not None and page_end is not None and 0 <= page_start < page_end <= len(text):
        exact = text[page_start:page_end]
        return {"source": _iiif_canvas_id(doc.id, None), "selector": [
            {"type": "TextQuoteSelector", "exact": exact},
            {"type": "TextPositionSelector", "start": page_start, "end": page_end},
        ]}
    if exact and exact in text:
        return {"source": _iiif_canvas_id(doc.id, None), "selector": {"type": "TextQuoteSelector", "exact": exact}}
    return None


def _record_annotations(db: Database, doc: Document) -> list[dict[str, Any]]:
    """The page's names and statements as Web Annotations (#5603, `source.extract.exported`), read from
    the same record the export stream reads (`export_service.record_mentions`, `claim_record_columns`):
    a name is `identifying` its entity, a statement `describing` the words it rests on, each with who made
    it. A name the page does not write (unanchored) has nowhere to point and is not written."""
    from fichero_server.export_service import claim_record_columns, record_mentions
    from fichero_server.models.knowledge import KnowledgeClaim

    out: list[dict[str, Any]] = []
    for mention in record_mentions(db, [doc.id]):
        target = _record_target(doc, mention["segment_id"], mention["segment_char_start"],
                                mention["segment_char_end"], mention["reading_id"], mention["char_start"],
                                mention["char_end"], mention["excerpt"] if mention["char_start"] is not None else None)
        if target is None:
            continue
        annotation: dict[str, Any] = {
            "id": f"/api/documents/{doc.id}/mentions/{mention['mention_id']}",
            "type": "Annotation",
            "motivation": "identifying",
            "body": {"type": "SpecificResource", "source": f"/api/entities/{mention['entity_id']}",
                     "purpose": "identifying", "label": mention["canonical_name"],
                     "entityType": mention["entity_type"]},
            "target": target,
        }
        creator = _record_creator(mention["made_by"])
        if creator:
            annotation["creator"] = creator
        out.append(annotation)
    for claim in db.query(KnowledgeClaim, source_document_id=doc.id):
        if claim.merged_into_id:
            continue
        cols = claim_record_columns(claim)
        quoted = (claim.metadata or {}).get("source_text")
        target = _record_target(doc, cols["segment_id"], cols["segment_char_start"], cols["segment_char_end"],
                                cols["reading_id"], cols["source_char_start"], cols["source_char_end"], quoted)
        if target is None:
            continue
        annotation = {
            "id": f"/api/documents/{doc.id}/claims/{claim.id}",
            "type": "Annotation",
            "motivation": "describing",
            "body": [{"type": "TextualBody", "value": claim.text, "format": "text/plain", "purpose": "describing"},
                     *({"type": "SpecificResource", "source": f"/api/entities/{entity_id}", "purpose": "tagging"}
                       for entity_id in claim.entity_ids)],
            "target": target,
        }
        if cols["date_normalized"] or cols["time_start"]:
            annotation["body"].append({"type": "TextualBody", "purpose": "tagging", "format": "text/plain",
                                       "value": cols["date_normalized"] or cols["time_start"]})
        creator = _record_creator(None, provider=claim.provider, model=claim.model)
        if creator:
            annotation["creator"] = creator
        out.append(annotation)
    return out


def _dedupe_annotations(*groups: list[Annotation]) -> list[Annotation]:
    seen: set[str] = set()
    rows: list[Annotation] = []
    for group in groups:
        for row in group:
            if row.id in seen:
                continue
            seen.add(row.id)
            rows.append(row)
    return rows


def _by_reference_canvas(doc: Document) -> dict[str, Any] | None:
    """A page that came in by reference, painted from the archive's own image and service exactly
    as the archive published them; nothing is re-hosted (`iiif.export.points-at-original`)."""
    meta = doc.metadata or {}
    if not meta.get("by_reference") or not meta.get("iiif_image"):
        return None
    canvas_id = meta.get("iiif_id") or _iiif_canvas_id(doc.id)
    body: dict[str, Any] = {"id": meta["iiif_image"], "type": "Image",
                            "format": meta.get("iiif_image_format") or "image/jpeg",
                            "width": meta.get("width"), "height": meta.get("height")}
    if meta.get("iiif_service_object"):
        body["service"] = [meta["iiif_service_object"]]
    return {
        "id": canvas_id, "type": "Canvas", "label": {"en": [doc.name or "Canvas 1"]},
        "width": meta.get("width"), "height": meta.get("height"),
        "annotations": [{"id": _lines_page_url(doc.id), "type": "AnnotationPage"}],
        "items": [{"id": f"{canvas_id}/page/1", "type": "AnnotationPage", "items": [{
            "id": f"{canvas_id}/painting/1", "type": "Annotation", "motivation": "painting",
            "body": body, "target": canvas_id}]}],
    }


def _lines_page_url(doc_id: str) -> str:
    return f"/api/iiif/iiif/lines/{doc_id}"


def build_lines_annotation_page(db: Database, doc: Document, canvas_id: str, width: int, height: int) -> dict[str, Any]:
    """The working pass's lines as IIIF annotations on the canvas (`iiif.export.segments-as-annotations`):
    each the counting reading's text, language and maker, at line granularity, placed in the
    CANVAS's pixels (Fichero keeps coordinates normalised, so a remote page's lines land on the
    archive's own image whatever size was fetched). Read through the one page exporter
    (`page_from_library`), so the pass and reading chosen are the ones every format writes."""
    from fichero_server.models.segments import SegmentPass
    from fichero_server.page_export import ExportRefused, page_from_library

    try:
        page, choices = page_from_library(db, doc.id)
    except ExportRefused:
        return {"@context": "http://www.w3.org/ns/anno.jsonld", "id": _lines_page_url(doc.id),
                "type": "AnnotationPage", "items": []}
    made = db.get(SegmentPass, choices.pass_id) if choices.pass_id else None
    maker = None
    if made is not None:
        human = str(getattr(made.provenance_kind, "value", made.provenance_kind)) == "human"
        maker = {"type": "Person" if human else "Software",
                 "name": (made.actor if human else "/".join(p for p in (made.provider, made.model) if p)) or made.name}
    items = []
    for index, seg in enumerate(page.segments):
        points = seg.polygon or ([[seg.rect[0], seg.rect[1]], [seg.rect[0] + seg.rect[2], seg.rect[1] + seg.rect[3]]]
                                 if seg.rect else None)
        if seg.kind != "line" or not seg.readings or not points:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x, y = round(min(xs) * width), round(min(ys) * height)
        w, h = round((max(xs) - min(xs)) * width), round((max(ys) - min(ys)) * height)
        body: dict[str, Any] = {"type": "TextualBody", "value": seg.readings[0][1], "format": "text/plain"}
        language = seg.language or doc.language
        if language:
            body["language"] = language
        item: dict[str, Any] = {"id": f"{canvas_id}/line/{seg.ref or index}", "type": "Annotation",
                                "motivation": "supplementing", "textGranularity": "line",
                                "body": body, "target": f"{canvas_id}#xywh={x},{y},{w},{h}"}
        if maker:
            item["creator"] = maker
        items.append(item)
    return {"@context": ["http://www.w3.org/ns/anno.jsonld", "http://iiif.io/api/extension/text-granularity/context.json"],
            "id": _lines_page_url(doc.id), "type": "AnnotationPage", "items": items}


def build_iiif_manifest(db: Database, doc: Document) -> dict[str, Any]:
    remote = _by_reference_canvas(doc)
    if remote is not None:
        manifest = {"@context": "http://iiif.io/api/presentation/3/context.json",
                    "id": f"{_iiif_base_url(doc.id)}/manifest", "type": "Manifest",
                    "label": {"en": [doc.name or "Untitled"]}, "items": [remote],
                    "annotations": [{"id": f"/api/documents/{doc.id}/annotations.jsonld", "type": "AnnotationPage"}]}
        rights = (doc.metadata or {}).get("iiif_rights") or {}
        if rights.get("rights"):
            manifest["rights"] = rights["rights"]
        statement = rights.get("required_statement") or (
            {"label": "Attribution", "value": rights["attribution"]} if rights.get("attribution") else None)
        if statement:
            # "none": IIIF's key for a value whose language the archive did not state.
            manifest["requiredStatement"] = {"label": {"none": [statement["label"]]},
                                             "value": {"none": [statement["value"]]}}
        return manifest
    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {doc.id}"
        )
    width, height = _get_image_dimensions(image_path)
    base_url = _iiif_base_url(doc.id)
    manifest_url = f"{base_url}/manifest"
    annotation_page_url = f"/api/documents/{doc.id}/annotations.jsonld"
    canvas = {
        "id": _iiif_canvas_id(doc.id),
        "type": "Canvas",
        "label": {"en": [doc.name or "Canvas 1"]},
        "width": width,
        "height": height,
        "items": [
            {
                "id": f"{base_url}/page/1",
                "type": "AnnotationPage",
                "items": [
                    {
                        "id": f"{base_url}/painting/1",
                        "type": "Annotation",
                        "motivation": "painting",
                        "body": {
                            "id": f"{base_url}/full/full/0/default.jpg",
                            "type": "Image",
                            "format": "image/jpeg",
                            "width": width,
                            "height": height,
                            "service": [
                                {
                                    "id": base_url,
                                    "type": "ImageService2",
                                    "profile": "http://iiif.io/api/image/2/level1.json",
                                }
                            ],
                        },
                        "target": _iiif_canvas_id(doc.id),
                    }
                ],
            }
        ],
        "annotations": [{"id": _lines_page_url(doc.id), "type": "AnnotationPage"},
                        {"id": annotation_page_url, "type": "AnnotationPage"}],
    }
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": manifest_url,
        "type": "Manifest",
        "label": {"en": [doc.name or "Untitled"]},
        "items": [canvas],
    }
    description = getattr(doc, "description", None)
    if description:
        manifest["summary"] = {"en": [description]}
    return manifest


def _serve_iiif_image(
    image_path: Path,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    fmt: str,
) -> Response:
    """Serve a IIIF image region."""
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

    try:
        with Image.open(image_path) as img:
            width, height = img.size

            # Handle region (simplified: "full" or "x,y,w,h")
            if region == "full":
                crop_box = (0, 0, width, height)
            elif "," in region:
                try:
                    x, y, w, h = [int(v) for v in region.split(",")]
                    crop_box = (x, y, x + w, y + h)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid region: {region}")
            else:
                crop_box = (0, 0, width, height)

            # Handle size (simplified: "full" or "w," or ",h" or "w,h")
            if size == "full":
                new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
            elif "," in size:
                parts = size.split(",")
                if parts[0]:
                    new_w = int(parts[0])
                    new_h = int(new_w * (crop_box[3] - crop_box[1]) / (crop_box[2] - crop_box[0]))
                    new_size = (new_w, new_h)
                elif parts[1]:
                    new_h = int(parts[1])
                    new_w = int(new_h * (crop_box[2] - crop_box[0]) / (crop_box[3] - crop_box[1]))
                    new_size = (new_w, new_h)
                else:
                    new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
            else:
                try:
                    new_size = (int(size), int(size))
                except ValueError:
                    new_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])

            # Handle rotation
            try:
                angle = int(rotation)
            except ValueError:
                angle = 0

            # Handle quality
            if quality == "gray":
                img = img.convert("L").convert("RGB")
            elif quality in ("default", "color"):
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

            # Apply transformations
            img = img.crop(crop_box)
            if angle != 0:
                img = img.rotate(angle, expand=True)
            if new_size != img.size:
                img = img.resize(new_size, Image.LANCZOS)

            # Output format
            fmt_upper = fmt.upper()
            if fmt_upper not in ("JPEG", "PNG", "WEBP"):
                fmt_upper = "JPEG"

            buffer = io.BytesIO()
            img.save(buffer, format=fmt_upper)
            buffer.seek(0)

            fmt_lower = fmt.lower()
            media_type = f"image/{fmt_lower}"
            if fmt_lower == "jpg":
                media_type = "image/jpeg"

            return Response(content=buffer.getvalue(), media_type=media_type)

    except Exception as exc:
        logger.error(f"IIIF image processing failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {exc}")


# =============================================================================
# IIIF API Endpoints
# =============================================================================


@router.get(
    "/{identifier}/info.json",
    response_model=ImageInfoResponse,
    summary="IIIF Image Information",
    description="Returns IIIF Image API information (info.json).",
)
async def get_image_info(
    identifier: str,
    db: Database = Depends(get_library_database),
) -> ImageInfoResponse:
    """Get IIIF image information."""
    doc = _document_or_404(db, identifier)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {identifier}"
        )

    width, height = _get_image_dimensions(image_path)

    # Build base URL
    base_url = f"/api/iiif/{identifier}"

    return ImageInfoResponse(
        context=IIIF_CONTEXT,
        id=base_url,
        protocol="http://iiif.io/api/image",
        width=width,
        height=height,
        tiles=[
            {"width": 256, "height": 256, "scaleFactors": [1, 2, 4, 8]}
        ],
        profile=[
            "http://iiif.io/api/image/2/level1.json",
            {
                "formats": ["jpg", "png"],
                "qualities": ["default", "color", "gray"],
                "supports": [
                    "regionByPx",
                    "sizeByW",
                    "sizeByH",
                    "sizeByWh",
                ],
            },
        ],
    )


@router.get(
    "/{identifier}/{region}/{size}/{rotation}/{quality}.{format}",
    summary="IIIF Image Request",
    description="Serve image region via IIIF Image API. Reference: https://iiif.io/api/image/2.1/",
)
async def serve_iiif_image(
    identifier: str,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    format: str,
    db: Database = Depends(get_library_database),
) -> Response:
    """Serve IIIF image tile/region."""
    doc = _document_or_404(db, identifier)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {identifier}"
        )

    fmt_lower = format.lower()
    if fmt_lower == "jpg":
        fmt_lower = "jpeg"

    return _serve_iiif_image(image_path, region, size, rotation, quality, fmt_lower)


@router.get(
    "/lines/{document_id}",
    summary="A page's lines as IIIF annotations",
    description="The working pass's lines as a W3C AnnotationPage on the document's canvas: each the counting reading's text, language and maker, at line granularity, in canvas pixels.",
)
async def get_lines_annotation_page(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    doc = _document_or_404(db, document_id)
    meta = doc.metadata or {}
    if meta.get("by_reference"):
        canvas_id, width, height = meta.get("iiif_id") or _iiif_canvas_id(doc.id), meta.get("width"), meta.get("height")
    else:
        image_path = _get_image_path(doc, db.path.parent)
        if not image_path:
            raise HTTPException(status_code=404, detail=f"No image available for document: {doc.id}")
        (width, height), canvas_id = _get_image_dimensions(image_path), _iiif_canvas_id(doc.id)
    if not width or not height:
        raise HTTPException(status_code=404, detail=f"The canvas size of document {doc.id} is not known")
    return build_lines_annotation_page(db, doc, canvas_id, int(width), int(height))


@router.get(
    "/manifest/{document_id}",
    summary="IIIF Manifest",
    description="Returns IIIF Presentation API manifest for document.",
)
async def get_iiif_manifest(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """Get IIIF manifest for document."""
    doc = _document_or_404(db, document_id)
    return build_iiif_manifest(db, doc)


@router.get(
    "/image/{document_id}",
    summary="Direct Image Access",
    description="Direct access to document image (non-IIIF, for convenience).",
)
async def get_document_image(
    document_id: str,
    width: int | None = Query(default=None, ge=50, le=4096),
    height: int | None = Query(default=None, ge=50, le=4096),
    db: Database = Depends(get_library_database),
) -> Response:
    """Get document image with optional resize."""
    doc = _document_or_404(db, document_id)

    image_path = _get_image_path(doc, db.path.parent)
    if not image_path:
        raise HTTPException(
            status_code=404, detail=f"No image available for document: {document_id}"
        )

    # If no resize requested, return original
    if width is None and height is None:
        # Explicit media type — bare FileResponse falls back to the mimetypes
        # module, whose first-use init reads /etc/apache2/mime.types and dies
        # with PermissionError in the sandboxed engine (2026-08-21, same 500
        # the rendition-content route shipped with).
        return FileResponse(
            image_path,
            media_type=IMAGE_MEDIA_TYPES.get(
                image_path.suffix.lower(), "application/octet-stream"
            ),
        )

    # Resize requested
    from PIL import Image  # lazy (#3985): keep PIL off the engine boot path

    try:
        with Image.open(image_path) as img:
            orig_width, orig_height = img.size

            # Calculate new size
            if width and height:
                new_size = (width, height)
            elif width:
                ratio = width / orig_width
                new_size = (width, int(orig_height * ratio))
            else:  # height
                ratio = height / orig_height
                new_size = (int(orig_width * ratio), height)

            img = img.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buffer, format="JPEG")
            buffer.seek(0)

            return Response(content=buffer.getvalue(), media_type="image/jpeg")

    except Exception as exc:
        logger.error(f"Image resize failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {exc}")
