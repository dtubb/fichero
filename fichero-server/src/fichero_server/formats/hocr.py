"""hOCR, in and out (#4944).

Spec: `formats-and-training.md` (`source.format.hocr-in`, `.hocr-out`,
`.round-trip-hocr`); build notes: `build-notes-formats-harness.md`.

hOCR is not XML with a schema; it is **HTML with an agreed microformat**: classes
name the granularity (`ocr_page`, `ocr_carea`, `ocr_par`, `ocr_line`, `ocrx_word`)
and a `title` attribute carries the properties, semicolon-separated
(`bbox 12 34 56 78; baseline 0 -3; x_wconf 92`).

**So hOCR is the honest `schema=None` case the harness was built for**, and it is the
reason that split exists: a format with no schema BY NATURE returns no validation
problems, while a schema missing from an install RAISES. Collapsing the two would
make a broken install report every export as valid. hOCR proves the first half is a
real state and not a hedge.

**Language is a BCP 47 TAG here** (HTML's `lang`), as in ALTO — so of the three
formats built so far, two want tags and PAGE XML wants names. That is the third data
point for #5078: no choice of storage avoids a mapping, so the question is which
mapping loses nothing.
"""

from __future__ import annotations

from typing import Any

from fichero_server.formats import register
from fichero_server.formats.harness import (
    pixel_grid,
    FormatSpec,
    LossReport,
    PageOrder,
    PageSegment,
    SourcePage,
)
from fichero_server.formats.validation import parse_html

#: hOCR's classes against the model's granularities. `ocr_carea` is a content area
#: and `ocr_par` a paragraph; both are regions to the model, which has one word for
#: "a part of a page" and does not need two.
CLASS_KINDS: dict[str, str] = {
    "ocr_page": "page",
    "ocr_carea": "region",
    "ocr_par": "region",
    "ocr_line": "line",
    "ocr_textfloat": "line",
    "ocr_header": "line",
    "ocrx_word": "word",
    "ocr_word": "word",
}
KIND_CLASSES: dict[str, str] = {
    "region": "ocr_carea",
    "line": "ocr_line",
    "word": "ocrx_word",
}


def _sniff(data: bytes) -> bool:
    """hOCR by its own classes, never by `.html`.

    A page of ordinary HTML is not hOCR, and the microformat is the only thing that
    says so -- there is no namespace and no doctype to check.
    """
    head = data[:4096].lower()
    return b"ocr_page" in head or b"ocr_line" in head or b"ocrx_word" in head


def _properties(title: str | None) -> dict[str, str]:
    """`"bbox 1 2 3 4; x_wconf 92"` as `{"bbox": "1 2 3 4", "x_wconf": "92"}`.

    Unknown properties are KEPT, because hOCR's `title` is where engines put what the
    microformat has no class for (`textangle`, `cuts`, `nlp`), and dropping them
    would be the silent loss `keeps-unrecognised` forbids.
    """
    out: dict[str, str] = {}
    for part in (title or "").split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(" ")
        out[name.strip()] = value.strip()
    return out


def _classes(element: Any) -> list[str]:
    return (element.get("class") or "").split()


def read(data: bytes) -> SourcePage:
    """One hOCR document as the model would have stored it.

    Coordinates are absolute pixels against the page's own `bbox`, so they normalise
    the same way ALTO's do -- and, as there, the page's declared size is what makes
    the stored geometry independent of anything else in the file.
    """
    # An HTML parser, not the XML one: hOCR IS HTML, and real engine output has
    # unclosed `<meta>` tags. Found by our own writer's output failing to read back.
    root = parse_html(data)

    page_el = next(
        (el for el in root.iter() if "ocr_page" in _classes(el)), None
    )
    if page_el is None:
        raise ValueError("no element of class ocr_page: this is not an hOCR document")

    page_props = _properties(page_el.get("title"))
    bbox = [int(float(v)) for v in page_props.get("bbox", "").split()] if page_props.get("bbox") else []
    width = bbox[2] - bbox[0] if len(bbox) == 4 else 0
    height = bbox[3] - bbox[1] if len(bbox) == 4 else 0

    page = SourcePage(image_size=(width, height) if width and height else None)
    if page_props.get("image"):
        page.image_name = page_props["image"].strip('"')
    system = next(
        (
            el.get("content")
            for el in root.iter()
            if el.tag.lower().endswith("meta") and el.get("name") == "ocr-system"
        ),
        None,
    )
    page.producer = system or None
    for key, value in page_props.items():
        if key not in ("bbox", "image", "ppageno", "scan_res"):
            page.foreign[f"hocr:{key}"] = value

    region_refs: list[str] = []
    for element in page_el.iter():
        kinds = [CLASS_KINDS[c] for c in _classes(element) if c in CLASS_KINDS]
        kind = next((k for k in kinds if k != "page"), None)
        if kind is None:
            continue
        props = _properties(element.get("title"))
        segment = PageSegment(kind=kind, ref=element.get("id"))

        parent = element.getparent()
        while parent is not None:
            parent_kinds = [CLASS_KINDS[c] for c in _classes(parent) if c in CLASS_KINDS]
            if any(k != "page" for k in parent_kinds):
                segment.parent_ref = parent.get("id")
                break
            parent = parent.getparent()

        if props.get("bbox") and width and height:
            values = [float(v) for v in props["bbox"].split()]
            if len(values) == 4:
                x0, y0, x1, y1 = values
                segment.rect = [
                    x0 / width, y0 / height, (x1 - x0) / width, (y1 - y0) / height
                ]
                segment.polygon = [
                    [x0 / width, y0 / height], [x1 / width, y0 / height],
                    [x1 / width, y1 / height], [x0 / width, y1 / height],
                ]
        text = "".join(element.itertext()).strip()
        if kind == "word" and text:
            segment.readings.append(("transcription", text))
        elif kind == "line" and text and not any(
            "ocrx_word" in _classes(child) or "ocr_word" in _classes(child)
            for child in element.iter()
        ):
            # A line with no word spans carries its own text. A line WITH them does
            # not, or the same words would be read twice.
            segment.readings.append(("transcription", text))
        # HTML's `lang` is a BCP 47 tag, like ALTO's LANG and unlike PAGE XML's name.
        if element.get("lang"):
            segment.language = element.get("lang")
        for key, value in props.items():
            if key not in ("bbox", "baseline"):
                segment.foreign[f"hocr:{key}"] = value
        if props.get("baseline") and segment.rect:
            # hOCR's baseline is a POLYNOMIAL relative to the line's box, not a
            # polyline: `baseline 0.008 -9` is slope and intercept. Kept verbatim
            # rather than converted into points that would claim a precision the
            # file does not have.
            segment.foreign["hocr:baseline"] = props["baseline"]
        if kind == "region" and segment.ref:
            region_refs.append(segment.ref)
        page.segments.append(segment)

    if region_refs:
        page.orders.append(PageOrder(name="as-written", refs=region_refs))
    return page


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as hOCR, with everything it cannot carry reported."""
    from lxml import etree

    width, height = pixel_grid(page, report, "hOCR")

    html = etree.Element("html")
    head = etree.SubElement(html, "head")
    etree.SubElement(
        head, "meta", name="ocr-system", content=page.producer or "fichero"
    )
    etree.SubElement(
        head,
        "meta",
        name="ocr-capabilities",
        content="ocr_page ocr_carea ocr_line ocrx_word",
    )
    body = etree.SubElement(html, "body")
    page_div = etree.SubElement(
        body,
        "div",
        **{
            "class": "ocr_page",
            "title": f'image "{page.image_name or "unknown"}"; bbox 0 0 {width} {height}',
        },
    )

    if len(page.orders) > 1:
        report.note(
            "named reading orders",
            len(page.orders) - 1,
            "hOCR's order is the document order of its elements, so only one can be "
            "expressed",
        )

    by_ref: dict[str, Any] = {}
    for index, segment in enumerate(page.segments):
        css = KIND_CLASSES.get(segment.kind)
        if css is None:
            report.note(
                f"{segment.kind} segments", 1, "hOCR has no class for this granularity"
            )
            continue
        ref = segment.ref or f"s{index}"
        parent_el = by_ref.get(segment.parent_ref or "", page_div)
        rect = segment.rect or _bounds(segment.polygon)
        title_parts = []
        if rect:
            x0 = int(round(rect[0] * width))
            y0 = int(round(rect[1] * height))
            x1 = int(round((rect[0] + rect[2]) * width))
            y1 = int(round((rect[1] + rect[3]) * height))
            title_parts.append(f"bbox {x0} {y0} {x1} {y1}")
        if segment.foreign.get("hocr:baseline"):
            title_parts.append(f"baseline {segment.foreign['hocr:baseline']}")
        elif segment.baseline:
            report.note(
                "baseline",
                1,
                "hOCR's baseline is a polynomial relative to the line's box, not a "
                "polyline, so a polyline baseline cannot be written without "
                "inventing a fit",
            )
        element = etree.SubElement(
            parent_el, "span", **{"class": css, "id": ref, "title": "; ".join(title_parts)}
        )
        by_ref[ref] = element

        if segment.language:
            element.set("lang", segment.language)
        if segment.script:
            report.note("script", 1, "hOCR has no script attribute")
        if segment.direction:
            report.note(
                "direction",
                1,
                "hOCR relies on HTML's `dir`, which is about display rather than the "
                "source's own direction, so it is not written",
            )
        if segment.readings:
            element.text = segment.readings[0][1]
        if len(segment.readings) > 1:
            report.note(
                "several readings",
                1,
                "an hOCR element holds one text, so alternatives and the choice "
                "between them are not expressible",
            )

    return etree.tostring(html, method="html", pretty_print=True)


def _bounds(polygon: list[list[float]] | None) -> list[float] | None:
    if not polygon:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


register(
    FormatSpec(
        name="hocr",
        extensions=(".hocr", ".html", ".htm"),
        read=read,
        write=write,
        # NO SCHEMA BY NATURE. hOCR is a microformat over HTML: there is nothing to
        # validate against, and saying so explicitly is what keeps it distinct from a
        # schema that is missing from the install (which raises). This is the case
        # `TestValidationNeverPassesVacuously` exists for.
        schema=None,
        round_trips=True,
        sniff=_sniff,
    )
)
