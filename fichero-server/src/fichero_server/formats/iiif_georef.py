"""IIIF Georeference Annotations, in and out (#5125).

Spec: `maps-and-georeference.md` (`source.geo.iiif-georef-in`, `-out`, `-round-trip`).

A Georeference Annotation says which pixels of a scan are which places on the earth: a
GeoJSON FeatureCollection of **ground control points** (GCPs), each a pixel position
(`resourceCoords`) and a WGS 84 Point, optionally a **mask** (an SVG polygon saying
which part of the image is the map), and a **transformation** (thin-plate spline,
polynomial of some order).

What it becomes here, and why:

* **A GCP is a `control-point` segment** with a `point` (the pixel end, normalised) and
  a `world` (the WGS 84 end). The spec rules a GCP a segment, not a by-product of a
  stored transform.
* **The mask is a `mask` segment** with a polygon. A sheet with two maps has two masks,
  each with its own GCPs, and the spec ties a GCP to its mask **by a typed link, not by
  being inside it**. The harness has no links, so that tie rides in
  `foreign["georef:mask"]` (the mask's `ref`). It is not faked as `parent_ref`: nesting
  is a different claim.
* **The transformation is the page's** (`SourcePage.transformation`): the spec makes it
  a property of the georeferencing PASS.

Two dialects are read, because Allmaps reads both and real files use both:

* **published** (georef/1): `resourceCoords`, the georef context, a `SpecificResource`
  target whose `source` has the image's width and height.
* **earlier**: `pixelCoords`, a target of `type: Image`, often inside an
  `AnnotationPage`; the pixel size is taken from the SVG selector's width and height.

Only the published dialect is written.

**Validation.** The extension publishes a JSON-LD context and normative prose, and no
JSON Schema. So `check()` is written from the prose, requirement by requirement, from
the text at https://iiif.io/api/extension/georef/ as read on 2026-09-27. Each rule below
quotes the sentence it enforces. If an official schema appears, it replaces this.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fichero_server.formats import register
from fichero_server.formats.harness import (
    FormatSpec,
    LossReport,
    PageSegment,
    SourcePage,
)

GEOREF_CONTEXT = "http://iiif.io/api/extension/georef/1/context.json"
PRESENTATION_CONTEXT = "http://iiif.io/api/presentation/3/context.json"

GCP_KIND = "control-point"
MASK_KIND = "mask"
#: The foreign key tying a GCP to its mask (see the module docstring).
MASK_LINK = "georef:mask"


# ---------------------------------------------------------------------------
# The checker, from the extension's normative text
# ---------------------------------------------------------------------------


def check(data: bytes) -> list[str]:
    """Problems with these bytes against the georef/1 extension's requirements, or []."""
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        return [f"not JSON: {exc}"]
    if not isinstance(doc, dict):
        return ["the top level is not a JSON object"]

    problems: list[str] = []
    # "The linked data context of this extension must be included before the IIIF
    # Presentation API linked data context on the top-level object."
    context = doc.get("@context")
    contexts = context if isinstance(context, list) else [context]
    if GEOREF_CONTEXT not in contexts:
        problems.append(f"@context: the top-level object must include {GEOREF_CONTEXT}")
    elif PRESENTATION_CONTEXT in contexts and contexts.index(GEOREF_CONTEXT) > contexts.index(
        PRESENTATION_CONTEXT
    ):
        problems.append("@context: the georef context must come before the Presentation context")

    if doc.get("type") == "AnnotationPage":
        items = doc.get("items")
        if not isinstance(items, list) or not items:
            return problems + ["an AnnotationPage must hold its annotations in `items`"]
        for index, item in enumerate(items):
            problems += [f"items[{index}]: {p}" for p in _check_annotation(item)]
        return problems
    return problems + _check_annotation(doc)


def _check_annotation(annotation: Any) -> list[str]:
    if not isinstance(annotation, dict) or annotation.get("type") != "Annotation":
        return ["not an Annotation"]
    problems: list[str] = []
    # "The motivation property should be included ... and when included it must have
    # the value georeferencing."
    if "motivation" in annotation and annotation["motivation"] != "georeferencing":
        problems.append(f"motivation must be 'georeferencing', not {annotation['motivation']!r}")
    problems += _check_target(annotation.get("target"))
    problems += _check_body(annotation.get("body"))
    return problems


def _check_target(target: Any) -> list[str]:
    # "The value for target must either be a single and full IIIF resource, or a single
    # region within a IIIF resource represented as a Specific Resource."
    if isinstance(target, str):
        return []
    if not isinstance(target, dict):
        return ["target must be a IIIF resource or a SpecificResource"]
    if target.get("type") != "SpecificResource":
        return []
    if not target.get("source"):
        return ["a SpecificResource target must name its source"]
    selector = target.get("selector")
    if selector is None:
        return []
    if not isinstance(selector, dict) or selector.get("type") != "SvgSelector":
        return ["the target's selector must be an SvgSelector"]
    return _check_svg(str(selector.get("value", "")), target.get("source"))


def _check_svg(svg: str, source: Any) -> list[str]:
    """The SVG selector rules of section 3.3.2, each quoted."""
    from lxml import etree

    from fichero_server.formats.validation import safe_parser

    try:
        root = etree.fromstring(svg.encode("utf-8"), parser=safe_parser())
    except etree.XMLSyntaxError as exc:
        return [f"SvgSelector value is not well-formed: {exc}"]
    problems: list[str] = []
    children = [child for child in root if isinstance(child.tag, str)]
    # "The svg element must contain a single child element. This single child element
    # must either be a <polygon> or a <rect>."
    if len(children) != 1:
        problems.append(f"the svg must contain a single child element, not {len(children)}")
    for child in children:
        name = etree.QName(child).localname
        if name not in ("polygon", "rect"):
            problems.append(f"the svg's child must be a polygon or a rect, not {name}")
        # "When a rect element is used, the rx and ry attributes must not be used."
        if name == "rect" and ({"rx", "ry"} & set(child.attrib)):
            problems.append("a rect must not use rx or ry")
    # "The viewBox attribute must not be used on the svg element."
    if "viewBox" in root.attrib:
        problems.append("the svg must not use viewBox")
    # "The transform attribute must not be used on any of the SVG Selector's elements."
    if any("transform" in element.attrib for element in root.iter() if isinstance(element.tag, str)):
        problems.append("no SVG element may use transform")
    # "When these attributes are included, they must be equal to the width and height of
    # the targeted resource and they must be numbers without units."
    for axis in ("width", "height"):
        value = root.get(axis)
        if value is None:
            continue
        if not re.fullmatch(r"\d+(\.\d+)?", value):
            problems.append(f"the svg's {axis} must be a number without units, not {value!r}")
        elif isinstance(source, dict) and isinstance(source.get(axis), (int, float)):
            if float(value) != float(source[axis]):
                problems.append(
                    f"the svg's {axis} ({value}) must equal the resource's ({source[axis]})"
                )
    return problems


def _check_body(body: Any) -> list[str]:
    # "The value for body must be a GeoJSON Feature Collection. The Feature Collection
    # must only contain Features with Point geometries ..."
    if not isinstance(body, dict) or body.get("type") != "FeatureCollection":
        return ["body must be a GeoJSON FeatureCollection"]
    features = body.get("features")
    if not isinstance(features, list):
        return ["body.features must be a list"]
    problems: list[str] = []
    for index, feature in enumerate(features):
        where = f"body.features[{index}]"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            problems.append(f"{where} is not a Feature")
            continue
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            problems.append(f"{where}: only Point geometries are allowed")
        elif not _is_lon_lat(geometry.get("coordinates")):
            problems.append(f"{where}: coordinates must be [longitude, latitude] in range")
        # "Each Feature in the Feature Collection must have the resourceCoords property in
        # the properties property. The value is an array representing a resource
        # coordinate at (x, y) and must be exactly in that order."
        coords = (feature.get("properties") or {}).get("resourceCoords")
        if not _is_pair(coords):
            problems.append(f"{where}: properties.resourceCoords must be [x, y]")
    return problems


def _is_pair(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )


def _is_lon_lat(value: Any) -> bool:
    return _is_pair(value) and -180 <= value[0] <= 180 and -90 <= value[1] <= 90


# ---------------------------------------------------------------------------
# Reading, both dialects
# ---------------------------------------------------------------------------


class NotAGeoreferenceAnnotation(ValueError):
    """Raised for JSON that is not a Georeference Annotation, rather than returning an
    empty page: "not this format" and "a map with no control points" are different."""


def _sniff(data: bytes) -> bool:
    head = data[:4096].lstrip()
    if not head.startswith(b"{"):
        return False
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    annotations = _annotations(doc) if isinstance(doc, dict) else []
    return any(
        isinstance(a, dict) and a.get("motivation") == "georeferencing" for a in annotations
    )


def _annotations(doc: dict) -> list[Any]:
    if doc.get("type") == "AnnotationPage":
        return list(doc.get("items") or [])
    return [doc]


def read(data: bytes) -> SourcePage:
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise NotAGeoreferenceAnnotation(f"not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise NotAGeoreferenceAnnotation("the top level is not a JSON object")
    annotations = _annotations(doc)
    if not annotations or not all(isinstance(a, dict) for a in annotations):
        raise NotAGeoreferenceAnnotation("no annotations")

    page = SourcePage()
    page.foreign["georef:top"] = {
        key: doc[key] for key in ("id", "@context") if key in doc
    }
    page.foreign["georef:dialect"] = (
        "published" if _uses_resource_coords(annotations) else "earlier"
    )
    for index, annotation in enumerate(annotations):
        _read_annotation(page, annotation, index)
    return page


def _uses_resource_coords(annotations: list[dict]) -> bool:
    for annotation in annotations:
        for feature in ((annotation.get("body") or {}).get("features") or []):
            if "resourceCoords" in (feature.get("properties") or {}):
                return True
    return False


def _read_annotation(page: SourcePage, annotation: dict, index: int) -> None:
    target = annotation.get("target")
    source, selector = _source_and_selector(target)
    image_name, size = _image(source, selector)
    if page.image_name is None:
        page.image_name = image_name
    if page.image_size is None:
        page.image_size = size
    if page.image_size is None:
        raise NotAGeoreferenceAnnotation(
            "no pixel size in the target or its SVG selector, so its pixel coordinates "
            "cannot be placed on the page"
        )
    width, height = page.image_size

    body = annotation.get("body") or {}
    if page.transformation is None and isinstance(body.get("transformation"), dict):
        # ponytail: one transformation per page (the spec's pass property); a second
        # annotation stating a DIFFERENT one keeps it on its own mask's foreign.
        page.transformation = body["transformation"]

    mask_ref: str | None = None
    polygon = _svg_polygon(selector, width, height) if selector else None
    if polygon is not None:
        mask_ref = f"mask-{index}"
        mask = PageSegment(kind=MASK_KIND, polygon=polygon, ref=mask_ref)
        mask.foreign["georef:annotation"] = {
            key: annotation[key] for key in ("id", "@context", "motivation") if key in annotation
        }
        mask.foreign["georef:source"] = source
        if (
            isinstance(body.get("transformation"), dict)
            and body["transformation"] != page.transformation
        ):
            mask.foreign["georef:transformation"] = body["transformation"]
        page.segments.append(mask)
    else:
        page.foreign.setdefault("georef:annotation", {
            key: annotation[key] for key in ("id", "@context", "motivation") if key in annotation
        })
        page.foreign.setdefault("georef:source", source)

    for feature in body.get("features") or []:
        properties = feature.get("properties") or {}
        pixel = properties.get("resourceCoords", properties.get("pixelCoords"))
        world = (feature.get("geometry") or {}).get("coordinates")
        if not _is_pair(pixel) or not _is_pair(world):
            raise NotAGeoreferenceAnnotation(f"a control point without both ends: {feature!r}")
        gcp = PageSegment(
            kind=GCP_KIND,
            point=[pixel[0] / width, pixel[1] / height],
            world=(float(world[0]), float(world[1])),
        )
        if mask_ref is not None:
            gcp.foreign[MASK_LINK] = mask_ref
        extra = {k: v for k, v in properties.items() if k not in ("resourceCoords", "pixelCoords")}
        if extra:
            gcp.foreign["georef:properties"] = extra
        page.segments.append(gcp)


def _source_and_selector(target: Any) -> tuple[Any, dict | None]:
    if isinstance(target, str):
        return target, None
    if not isinstance(target, dict):
        return None, None
    selector = target.get("selector") if isinstance(target.get("selector"), dict) else None
    if target.get("type") == "SpecificResource":
        return target.get("source"), selector
    # The earlier dialect: the target IS the image, with the selector on it.
    return {k: v for k, v in target.items() if k != "selector"}, selector


def _image(source: Any, selector: dict | None) -> tuple[str | None, tuple[int, int] | None]:
    name = None
    size = None
    if isinstance(source, str):
        name = source
    elif isinstance(source, dict):
        name = source.get("@id") or source.get("id")
        if not name and isinstance(source.get("source"), str):
            name = source["source"]
        if isinstance(source.get("width"), int) and isinstance(source.get("height"), int):
            size = (source["width"], source["height"])
    if size is None and selector:
        size = _svg_size(str(selector.get("value", "")))
    return name, size


def _svg_size(svg: str) -> tuple[int, int] | None:
    width = re.search(r'\bwidth="(\d+)"', svg)
    height = re.search(r'\bheight="(\d+)"', svg)
    return (int(width.group(1)), int(height.group(1))) if width and height else None


def _svg_polygon(selector: dict, width: int, height: int) -> list[list[float]] | None:
    svg = str(selector.get("value", ""))
    points = re.search(r'<polygon[^>]*\bpoints="([^"]+)"', svg)
    if points:
        numbers = [float(n) for n in re.split(r"[\s,]+", points.group(1).strip()) if n]
        return [[numbers[i] / width, numbers[i + 1] / height] for i in range(0, len(numbers) - 1, 2)]
    rect = re.search(r"<rect\b([^>]*)>", svg)
    if rect:
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', rect.group(1)))
        x, y = float(attrs.get("x", 0)), float(attrs.get("y", 0))
        w, h = float(attrs["width"]), float(attrs["height"])
        return [[x / width, y / height], [(x + w) / width, y / height],
                [(x + w) / width, (y + h) / height], [x / width, (y + h) / height]]
    return None


# ---------------------------------------------------------------------------
# Writing, the published dialect
# ---------------------------------------------------------------------------


def write(page: SourcePage, report: LossReport) -> bytes:
    """A georeferencing pass as a georef/1 annotation (one mask) or an AnnotationPage
    (several), with everything it cannot carry reported."""
    if page.image_size is None:
        raise ValueError(
            "a georeference annotation needs the image's pixel size: resourceCoords are "
            "pixels, and there is no page to scale them to"
        )
    width, height = page.image_size
    masks = [s for s in page.segments if s.kind == MASK_KIND and s.polygon]
    gcps = [s for s in page.segments if s.kind == GCP_KIND and s.point and s.world]
    others = [s for s in page.segments if s not in masks and s not in gcps]
    if others:
        report.note(
            "segments other than control points and masks", len(others),
            "a georeference annotation carries only GCPs and the map's outline",
        )
    unworlded = [s for s in page.segments if s.kind == GCP_KIND and not (s.point and s.world)]
    if unworlded:
        report.note(
            "control points without both ends", len(unworlded),
            "a GCP needs a pixel position and a WGS 84 position",
        )
    for segment in gcps:
        if segment.readings:
            report.note("readings on control points", 1, "a GCP Feature has no text")
        if segment.language or segment.script or segment.direction:
            report.note("language, script and direction", 1, "not expressible on a GCP")

    if page.foreign.get("georef:dialect") == "earlier":
        report.note(
            "the plain image URL beside its IIIF service", 1,
            "the earlier dialect targets a JPEG with the service beside it; the published "
            "one names the service, so the service is written and the JPEG URL is not",
        )

    groups: list[tuple[PageSegment | None, list[PageSegment]]]
    if masks:
        by_ref = {m.ref: m for m in masks}
        groups = [(m, [g for g in gcps if g.foreign.get(MASK_LINK) == m.ref]) for m in masks]
        orphans = [g for g in gcps if g.foreign.get(MASK_LINK) not in by_ref]
        if orphans:
            groups[0][1].extend(orphans)
            report.note(
                "which mask a control point belongs to", len(orphans),
                "these GCPs named no mask on the page and were written with the first",
            )
    else:
        groups = [(None, gcps)]

    annotations = [
        _annotation(page, mask, members, width, height) for mask, members in groups
    ]
    context = [GEOREF_CONTEXT, PRESENTATION_CONTEXT]
    if len(annotations) == 1:
        doc = {"@context": context, **annotations[0]}
    else:
        doc = {"@context": context, "type": "AnnotationPage", "items": annotations}
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")


def _published_source(source: Any, image_name: str | None) -> dict:
    """The target's source in the published dialect: a IIIF resource.

    The earlier dialect's target is a plain `Image` (a JPEG URL) with the IIIF image
    service beside it; the published one names the SERVICE. So the service is promoted,
    which is the resource the pixel coordinates were measured on.
    """
    if isinstance(source, dict):
        services = source.get("service")
        if source.get("type") == "Image" and isinstance(services, list) and services:
            first = services[0]
            if isinstance(first, dict) and (first.get("@id") or first.get("id")):
                return dict(first)
        return dict(source)
    return {"id": source or image_name, "type": "Image"}


def _annotation(
    page: SourcePage, mask: PageSegment | None, gcps: list[PageSegment], width: int, height: int
) -> dict:
    kept = (mask.foreign.get("georef:annotation") if mask else page.foreign.get("georef:annotation")) or {}
    source = (mask.foreign.get("georef:source") if mask else page.foreign.get("georef:source"))
    source = _published_source(source, page.image_name)
    source = {**source, "width": width, "height": height}

    target: Any
    if mask is not None:
        points = " ".join(
            f"{round(x * width)},{round(y * height)}" for x, y in mask.polygon or []
        )
        target = {
            "type": "SpecificResource",
            "source": source,
            "selector": {
                "type": "SvgSelector",
                "value": f'<svg width="{width}" height="{height}"><polygon points="{points}" /></svg>',
            },
        }
    else:
        target = source

    body: dict[str, Any] = {"type": "FeatureCollection"}
    transformation = (mask.foreign.get("georef:transformation") if mask else None) or page.transformation
    if transformation:
        body["transformation"] = transformation
    body["features"] = [
        {
            "type": "Feature",
            "properties": {
                **(g.foreign.get("georef:properties") or {}),
                "resourceCoords": [round(g.point[0] * width), round(g.point[1] * height)],
            },
            "geometry": {"type": "Point", "coordinates": [g.world[0], g.world[1]]},
        }
        for g in gcps
    ]
    annotation: dict[str, Any] = {"type": "Annotation"}
    if "id" in kept:
        annotation["id"] = kept["id"]
    annotation["motivation"] = "georeferencing"
    annotation["target"] = target
    annotation["body"] = body
    return annotation


register(
    FormatSpec(
        name="iiif-georef",
        extensions=(".json", ".jsonld"),
        read=read,
        write=write,
        schema=None,
        # No XSD exists; the checker is written from the extension's normative prose.
        check=check,
        round_trips=True,
        sniff=_sniff,
    )
)
