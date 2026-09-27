"""PAGE XML, in and out (#4944).

Spec: `formats-and-training.md` (`source.format.pagexml-in`, `.pagexml-out`,
`.round-trip-pagexml`); build notes: `build-notes-formats-harness.md`.

**Why PAGE XML is first.** Its shape is the one the source model already matches —
`Coords` is slice 2's polygon, `Baseline` is slice 2's baseline, TextRegion /
TextLine / Word are slice 1's granularities, `ReadingOrder` is slice 10, and
`primaryLanguage` / `script` / `readingDirection` are slice 9 — and it is what
eScriptorium speaks. So its round trip is the first real test of whether slices
3–10 hold together.

COORDINATES. PAGE XML writes INTEGER PIXELS against a stated page size; the model
stores normalised fractions. A reader divides by the page size, a writer multiplies
by it. That is lossy in the last decimal and the loss is inherent rather than a
defect: a round trip compares to the precision the format declares, and asserting
float equality would be asserting PAGE XML is lossless when it is not.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from fichero_server.formats import register
from fichero_server.formats.harness import (
    FormatSpec,
    LossReport,
    PageOrder,
    PageSegment,
    SourcePage,
)
from fichero_server.formats.validation import parse

#: WRITE 2019, READ BOTH (ruled 2026-09-26). The 2019 schema is what current tools
#: write, so writing the older one to please a single consumer would cost every
#: other reader the newer attributes; reading both is nearly free, because the
#: element names are identical and only the namespace differs.
#:
#: **The choice is EMPIRICAL and here is where the evidence would come from:** if a
#: real eScriptorium file round-trips through us and eScriptorium then refuses our
#: output, that is a finding which changes this ruling. Until somebody runs that,
#: 2019 is the better default rather than the proven one.
PAGE_NS_2019 = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
PAGE_NS_2013 = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"
KNOWN_NAMESPACES = (PAGE_NS_2019, PAGE_NS_2013)

#: The granularity each element means, in the model's own words
#: (`source.segment.open-kinds`).
ELEMENT_KINDS: dict[str, str] = {
    "TextRegion": "region",
    "TextLine": "line",
    "Word": "word",
    "Glyph": "character",
    "TableRegion": "table",
    "ImageRegion": "picture",
    "SeparatorRegion": "separator",
    "GraphicRegion": "graphic",
}
KIND_ELEMENTS: dict[str, str] = {
    "region": "TextRegion",
    "line": "TextLine",
    "word": "Word",
    "character": "Glyph",
}

#: PAGE XML's `readingDirection` values against the model's directions. `ttb` has no
#: PAGE XML equivalent -- the attribute covers horizontal reading only -- so a
#: vertical script's direction is a LOSS and is reported, which is exactly the case
#: a European-only tool gets silently wrong.
DIRECTIONS_OUT = {
    "ltr": "left-to-right",
    "rtl": "right-to-left",
    "ttb": "top-to-bottom",
    "btt": "bottom-to-top",
}
DIRECTIONS_IN = {value: key for key, value in DIRECTIONS_OUT.items()}


# ---------------------------------------------------------------------------
# PAGE XML's own closed vocabularies, READ FROM THE VENDORED SCHEMA
# ---------------------------------------------------------------------------
#
# FOUND 2026-09-26 by the export refusing to validate, which is the whole reason
# validation happens before the bytes are handed over:
#
# * `primaryLanguage` is an enumeration of 188 language **NAMES** ("Arabic",
#   "Spanish"), not BCP 47 tags. Writing `ar` is invalid PAGE XML.
# * `script` is 181 values of the form `"Arab - Arabic"` -- the ISO 15924 code, a
#   dash, and the English name. Writing the bare code is invalid too.
# * `readingDirection` has exactly the four straight directions and no more, which
#   is why `alternating` and `follows-baseline` are declared losses.
#
# The tables are PARSED FROM THE SCHEMA rather than transcribed. A hand-copied list
# of 188 names would be a second copy of a vocabulary we already ship on disk, and
# it would drift the first time the schema is updated -- the same duplication this
# programme has removed six times. Lazy and cached, so the 86 KB parse happens only
# if PAGE XML is actually used.


@lru_cache(maxsize=1)
def _schema_vocabularies() -> tuple[dict[str, str], dict[str, str]]:
    """`({language_name_lower: name}, {script_code: "Code - Name"})` from the XSD."""
    from fichero_server.formats.harness import SCHEMA_DIR

    path = SCHEMA_DIR / "pagecontent-2019-07-15.xsd"
    if not path.exists():
        raise FileNotFoundError(
            f"the PAGE XML schema is not installed at {path}; its own enumerations "
            "are what a writer needs, so this is a broken build rather than a "
            "format that cannot be validated"
        )
    text = path.read_text(encoding="utf-8")

    def values(type_name: str) -> list[str]:
        block = re.search(
            rf'<simpleType name="{type_name}".*?</simpleType>', text, re.S
        )
        return re.findall(r'value="([^"]+)"', block.group(0)) if block else []

    languages = {name.lower(): name for name in values("LanguageSimpleType")}
    scripts: dict[str, str] = {}
    for value in values("ScriptSimpleType"):
        code = value.split(" - ", 1)[0].strip()
        scripts[code] = value
    return languages, scripts


def _language_out(value: str | None, report: LossReport) -> str | None:
    """The model's language as PAGE XML's enumerated NAME, or None plus a loss.

    **The engine stores a language NAME (#2092), which is closer to PAGE XML than a
    tag would be** -- the enumeration is names, so `Spanish` passes straight through
    where `es` would be invalid. A tag is mapped when it is one of the handful the
    enumeration happens to spell, and otherwise reported: PAGE XML's list has 188
    languages and no way to say one it does not know, so a project working in a
    language outside it cannot state that language in PAGE XML at all. That is the
    colonial-archive case, and it is a loss of the FORMAT, reported rather than
    silently blanked.
    """
    if not value:
        return None
    languages, _scripts = _schema_vocabularies()
    matched = languages.get(value.strip().lower())
    if matched:
        return matched
    report.note(
        "language",
        1,
        f"PAGE XML's primaryLanguage is a closed list of 188 language NAMES and "
        f"{value!r} is not one of them, so this segment's language is not written",
    )
    return None


def _script_out(value: str | None, report: LossReport) -> str | None:
    """The model's ISO 15924 code as PAGE XML's `"Code - Name"` value, or a loss.

    A project-declared script (`Qaaa`-`Qabx`, `source.lang.project-declared`) is NOT
    in the enumeration -- PAGE XML ships `Zxxx`, `Zyyy` and `Zzzz` but no private-use
    range -- so a project's own script cannot be written as a script. It goes in the
    loss report, and `keeps-unrecognised` is where it survives.
    """
    if not value:
        return None
    _languages, scripts = _schema_vocabularies()
    matched = scripts.get(value.strip())
    if matched:
        return matched
    report.note(
        "script",
        1,
        f"PAGE XML's script list is ISO 15924 by name and has no entry for "
        f"{value!r} (its private-use range Qaaa-Qabx is absent), so a "
        "project-declared script cannot be written as a script",
    )
    return None


def _language_in(value: str | None) -> str | None:
    """PAGE XML's name as the model's language. A NAME stays a name (#2092)."""
    return value.strip() or None if value else None


def _script_in(value: str | None) -> str | None:
    """`"Arab - Arabic"` as `Arab`. The code is the part the model stores."""
    if not value:
        return None
    return value.split(" - ", 1)[0].strip() or None


def _tag(element: Any) -> str:
    """The local name, so 2013 and 2019 files read through one code path."""
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag else str(tag)


def _points(raw: str, width: int, height: int) -> list[list[float]]:
    """`"12,34 56,78"` as normalised `[[x, y], ...]`.

    Malformed pairs are SKIPPED rather than raising: a real file from a real tool
    sometimes has a stray token, and losing one point of a polygon is better than
    refusing a page — but a polygon that ends up with fewer than three points is
    reported by the caller rather than kept as a shape that cannot be drawn.
    """
    out: list[list[float]] = []
    for pair in raw.split():
        if "," not in pair:
            continue
        x_raw, _, y_raw = pair.partition(",")
        try:
            x, y = float(x_raw), float(y_raw)
        except ValueError:
            continue
        out.append([x / width if width else 0.0, y / height if height else 0.0])
    return out


def _sniff(data: bytes) -> bool:
    """PAGE XML by its own root element, not by its extension.

    PAGE XML, ALTO, hOCR and TEI are all `.xml`; only the root tells them apart, and
    a harness that trusted the extension would import an ALTO file as PAGE XML and
    report the emptiness as the file's fault.
    """
    head = data[:2048].lower()
    return b"pcgts" in head or any(ns.encode().lower() in head for ns in KNOWN_NAMESPACES)


def read(data: bytes) -> SourcePage:
    """One PAGE XML file as the model would have stored it.

    Reads a file somebody ELSE wrote -- which is the point. A round trip of our own
    output proves only that our writer agrees with our reader, and two consistently
    wrong halves achieve that too.
    """
    root = parse(data)
    page_el = next(
        (child for child in root.iter() if _tag(child) == "Page"), None
    )
    if page_el is None:
        raise ValueError("no <Page> element: this is not a PAGE XML document")

    width = int(float(page_el.get("imageWidth") or 0)) or 0
    height = int(float(page_el.get("imageHeight") or 0)) or 0
    page = SourcePage(
        image_name=page_el.get("imageFilename"),
        image_size=(width, height) if width and height else None,
    )
    creator = next((child for child in root.iter() if _tag(child) == "Creator"), None)
    page.producer = (creator.text or "").strip() or None if creator is not None else None

    for element in page_el.iter():
        kind = ELEMENT_KINDS.get(_tag(element))
        if kind is None:
            continue
        segment = PageSegment(kind=kind, ref=element.get("id"))
        parent = element.getparent()
        while parent is not None and _tag(parent) not in ELEMENT_KINDS:
            parent = parent.getparent()
        if parent is not None:
            segment.parent_ref = parent.get("id")

        for child in element:
            child_tag = _tag(child)
            if child_tag == "Coords" and child.get("points"):
                segment.polygon = _points(child.get("points"), width, height) or None
            elif child_tag == "Baseline" and child.get("points"):
                segment.baseline = _points(child.get("points"), width, height) or None
            elif child_tag == "TextEquiv":
                text_el = next((c for c in child if _tag(c) == "Unicode"), None)
                text = (text_el.text if text_el is not None else child.text) or ""
                if text.strip():
                    segment.readings.append(("transcription", text))

        if segment.polygon:
            xs = [point[0] for point in segment.polygon]
            ys = [point[1] for point in segment.polygon]
            segment.rect = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

        segment.language = _language_in(element.get("primaryLanguage"))
        # `primaryScript` on a region, line or word; `script` only on a Glyph.
        # Found by the export refusing to validate: the ScriptSimpleType exists on
        # several elements under different attribute names, and guessing one
        # produced invalid PAGE XML rather than a wrong-but-accepted file.
        segment.script = _script_in(
            element.get("primaryScript") or element.get("script")
        )
        direction = element.get("readingDirection")
        if direction:
            segment.direction = DIRECTIONS_IN.get(direction)
            if segment.direction is None:
                # An unrecognised direction is KEPT rather than dropped
                # (`keeps-unrecognised`): a file that says something we cannot map
                # has still said it.
                segment.foreign["readingDirection"] = direction
        if element.get("custom"):
            segment.foreign["custom"] = element.get("custom")
        page.segments.append(segment)

    for element in root.iter():
        if _tag(element) != "OrderedGroup":
            continue
        refs = [
            child.get("regionRef")
            for child in element
            if _tag(child) == "RegionRefIndexed" and child.get("regionRef")
        ]
        if refs:
            page.orders.append(
                PageOrder(name=element.get("id") or "as-written", refs=refs)
            )
    return page


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as PAGE XML 2019, with everything it cannot carry reported.

    The losses are named here rather than discovered by a round trip, because a
    writer is the only thing that knows what it dropped.
    """
    from lxml import etree

    width, height = page.image_size or (1000, 1000)
    if page.image_size is None:
        report.note(
            "page size",
            1,
            "the model stores normalised coordinates and this page had no pixel "
            "size recorded, so 1000x1000 was written and the original pixel grid "
            "cannot be recovered",
        )

    root = etree.Element(f"{{{PAGE_NS_2019}}}PcGts", nsmap={None: PAGE_NS_2019})
    metadata = etree.SubElement(root, f"{{{PAGE_NS_2019}}}Metadata")
    etree.SubElement(metadata, f"{{{PAGE_NS_2019}}}Creator").text = (
        page.producer or "Fichero"
    )
    etree.SubElement(metadata, f"{{{PAGE_NS_2019}}}Created").text = "1970-01-01T00:00:00"
    etree.SubElement(metadata, f"{{{PAGE_NS_2019}}}LastChange").text = (
        "1970-01-01T00:00:00"
    )
    page_el = etree.SubElement(
        root,
        f"{{{PAGE_NS_2019}}}Page",
        imageFilename=page.image_name or "unknown.png",
        imageWidth=str(width),
        imageHeight=str(height),
    )

    if page.orders:
        order_el = etree.SubElement(page_el, f"{{{PAGE_NS_2019}}}ReadingOrder")
        first = page.orders[0]
        group = etree.SubElement(
            order_el, f"{{{PAGE_NS_2019}}}OrderedGroup", id=first.name
        )
        for index, ref in enumerate(first.refs):
            etree.SubElement(
                group,
                f"{{{PAGE_NS_2019}}}RegionRefIndexed",
                index=str(index),
                regionRef=ref,
            )
        if len(page.orders) > 1:
            report.note(
                "named reading orders",
                len(page.orders) - 1,
                "PAGE XML holds ONE ReadingOrder per page, so orders beyond the "
                "first are not written",
            )

    by_ref: dict[str, Any] = {}
    for index, segment in enumerate(page.segments):
        element_name = KIND_ELEMENTS.get(segment.kind)
        if element_name is None:
            report.note(
                f"{segment.kind} segments",
                1,
                "PAGE XML has no element for this granularity",
            )
            continue
        ref = segment.ref or f"s{index}"
        parent_el = by_ref.get(segment.parent_ref or "", page_el)
        element = etree.SubElement(parent_el, f"{{{PAGE_NS_2019}}}{element_name}", id=ref)
        by_ref[ref] = element

        points = segment.polygon or _rect_points(segment.rect)
        if points:
            etree.SubElement(
                element,
                f"{{{PAGE_NS_2019}}}Coords",
                points=_points_out(points, width, height),
            )
        if segment.baseline:
            etree.SubElement(
                element,
                f"{{{PAGE_NS_2019}}}Baseline",
                points=_points_out(segment.baseline, width, height),
            )
        language = _language_out(segment.language, report)
        if language:
            element.set("primaryLanguage", language)
        script = _script_out(segment.script, report)
        if script:
            element.set("script" if element_name == "Glyph" else "primaryScript", script)
        if segment.direction:
            mapped = DIRECTIONS_OUT.get(segment.direction)
            if mapped:
                element.set("readingDirection", mapped)
            else:
                report.note(
                    "direction",
                    1,
                    f"PAGE XML has no readingDirection for {segment.direction!r} "
                    "(alternating and follows-baseline are Fichero's own)",
                )
        for reading_index, (_kind, text) in enumerate(segment.readings):
            equiv = etree.SubElement(
                element, f"{{{PAGE_NS_2019}}}TextEquiv", index=str(reading_index)
            )
            etree.SubElement(equiv, f"{{{PAGE_NS_2019}}}Unicode").text = text
        if len(segment.readings) > 1:
            report.note(
                "which reading counts",
                1,
                "PAGE XML's TextEquiv has an index but no way to say WHICH reading "
                "a project counts, so the choice is not carried",
            )

    # PAGE XML's content model is a SEQUENCE: Coords, then child TextLines, then
    # TextEquiv and TextStyle. Segments are written parent-before-child, so a
    # region's TextEquiv is created before its lines exist and ends up in front of
    # them -- valid-looking XML that the schema refuses.
    #
    # Found by writing a REAL file back (OCR-D's ground truth has text on regions
    # AND lines); the round trip of our own output never hit it, because our own
    # test page had no text on a region that also had lines. That is the round-trip
    # trap exactly: our reader accepted what our writer produced.
    #
    # `append` MOVES an existing child in lxml, so this puts each element's
    # TextEquiv back at the end where the schema expects it.
    for element in root.iter():
        for child in [c for c in element if _tag(c) in ("TextEquiv", "TextStyle")]:
            element.append(child)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _rect_points(rect: list[float] | None) -> list[list[float]]:
    if not rect:
        return []
    x, y, w, h = rect
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _points_out(points: list[list[float]], width: int, height: int) -> str:
    return " ".join(
        f"{int(round(x * width))},{int(round(y * height))}" for x, y in points
    )


register(
    FormatSpec(
        name="pagexml",
        extensions=(".xml",),
        read=read,
        write=write,
        # The XSD is not vendored yet, and `None` here would claim this format
        # CANNOT be validated, which is false. The schema file is named so the
        # harness raises a missing-schema error rather than passing validation
        # vacuously -- a broken install must not look like a valid export.
        schema="pagecontent-2019-07-15.xsd",
        round_trips=True,
        sniff=_sniff,
    )
)
