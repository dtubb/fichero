"""ALTO, in and out (#4944).

Spec: `formats-and-training.md` (`source.format.alto-in`, `.alto-out`,
`.round-trip-alto`); build notes: `build-notes-formats-harness.md`.

**ALTO is where the one-harness design gets its first real test.** PAGE XML to ALTO
is PAGE XML in, ALTO out, through `SourcePage` — never a PAGE-to-ALTO path. Where a
detail maps awkwardly, the awkwardness goes in the LOSS REPORT; wanting a direct
path is the N² shape asking to be let in.

**THE TRAP, and it is not the coordinates you would expect.** ALTO declares a
`MeasurementUnit` — `pixel`, `mm10` (tenths of a millimetre) or `inch1200` — where
PAGE XML always means pixels. A reader that assumes pixels is silently wrong by a
factor on any file using another unit, and **nothing looks broken**: the numbers are
plausible, the shapes are the right shape, and every line sits in the wrong place by
the same ratio.

Two things follow, and the second is the subtle one:

* **Normalised coordinates are unit-FREE**, because the page declares its size in
  the same unit: `HPOS / Page@WIDTH` cancels. So the model's stored geometry is
  correct whatever the unit, which is a property of storing fractions rather than
  luck.
* **`image_size` is NOT unit-free.** The model means a pixel grid there, and an
  `mm10` page's `1003 x 1469` is not pixels. Converting needs a resolution ALTO
  need not state, so a non-pixel file gets `image_size=None`, the unit is kept in
  `foreign`, and the loss report says the pixel grid is unknown rather than
  inventing one. A page size silently 10× wrong is worse than an absent one.

ALTO has **no reading-order element** (unlike PAGE XML's `ReadingOrder`): the order
IS the document order of its blocks. So slice 10's first order is the block order,
and any further named order is a declared loss.
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
    xml_id,
)
from fichero_server.formats.validation import parse

#: ALTO's namespaces, v2 through v4. All three are READ -- a national library's
#: v2 file and a modern v4 one have the same element names -- and v4 is written.
ALTO_NS_V4 = "http://www.loc.gov/standards/alto/ns-v4#"
#: The ALTO release written and validated against: the latest (ruled 2026-09-27: we export
#: the latest schema, and our export is what is tested). 4.4 per the ALTO Editorial Board's
#: repository README ("Latest official schema version is 4.4"); loc.gov refuses scripts.
ALTO_WRITTEN_VERSION = "4.4"
ALTO_WRITTEN_SCHEMA = "alto-4-4.xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ALTO_NS_V3 = "http://www.loc.gov/standards/alto/ns-v3#"
ALTO_NS_V2 = "http://www.loc.gov/standards/alto/ns-v2#"
KNOWN_NAMESPACES = (ALTO_NS_V4, ALTO_NS_V3, ALTO_NS_V2)

#: The units ALTO may declare. `pixel` is the only one the model can also read as
#: an image size; the others are physical measurements and need a resolution the
#: file need not carry.
UNITS = ("pixel", "mm10", "inch1200")

#: ALTO's elements against the model's granularities. `String` is a WORD: ALTO has
#: no word/line ambiguity, which is one place it is clearer than PAGE XML.
ELEMENT_KINDS: dict[str, str] = {
    "TextBlock": "region",
    "TextLine": "line",
    "String": "word",
    "Illustration": "picture",
    "GraphicalElement": "graphic",
    "ComposedBlock": "region",
}
#: The reverse of `ELEMENT_KINDS`, and it must STAY the reverse: a kind the reader
#: can produce and the writer cannot emit would be reported as a loss the format can
#: actually carry -- honest data destruction, which is worse than a plain bug because
#: it looks like transparency. `Illustration` and `GraphicalElement` are ALTO's own
#: elements, so a picture and a graphic read from ALTO go back out as ALTO.
KIND_ELEMENTS: dict[str, str] = {
    "region": "TextBlock",
    "line": "TextLine",
    "word": "String",
    "picture": "Illustration",
    "graphic": "GraphicalElement",
}


class UnknownMeasurementUnit(ValueError):
    """Raised for a `MeasurementUnit` ALTO does not define.

    REFUSED rather than defaulted, which is the whole point: assuming pixels for an
    unknown unit would place every shape on the page by a factor nobody can see,
    and a file that declares a unit we do not understand is a file we cannot read
    correctly. Saying so is the only honest answer.
    """

    def __init__(self, unit: str) -> None:
        self.unit = unit
        super().__init__(
            f"ALTO declares MeasurementUnit {unit!r}, which is not one of "
            + ", ".join(UNITS)
            + ". Refusing rather than assuming pixels: an unknown unit would put "
            "every shape in the wrong place by a factor with nothing to show it."
        )


#: The marker a SYNTHESISED parent carries (#5084's ALTO half). ALTO's schema puts a
#: `String` inside a `TextLine` inside a `TextBlock`, so a word with neither cannot be
#: written where it belongs.
#:
#: **ALTO has no free-form attribute like PAGE XML's `custom`**, so the marker is the
#: ID PREFIX alone. That is weaker -- a tool that rewrites ids would erase it -- and it
#: is the strongest thing the format offers, which is worth stating rather than
#: pretending the two formats are equally markable.
IMPLICIT_ID_PREFIX = "fichero-implicit-"


def _is_implicit(element: Any) -> bool:
    return (element.get("ID") or "").startswith(IMPLICIT_ID_PREFIX)


def _tag(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag else str(tag)


def _sniff(data: bytes) -> bool:
    """ALTO by its ROOT element and namespace, never by `.xml` -- and never by a byte window,
    which a long leading comment defeats (#5132; `validation.root_element`)."""
    from fichero_server.formats.validation import root_element

    root = root_element(data)
    return root is not None and (root[0] in KNOWN_NAMESPACES or root[1].lower() == "alto")


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def read(data: bytes) -> SourcePage:
    """One ALTO file as the model would have stored it.

    Coordinates are normalised against the page's own declared size, which makes
    them unit-free; the UNIT is still read, because `image_size` is not.
    """
    root = parse(data)

    unit_el = next((el for el in root.iter() if _tag(el) == "MeasurementUnit"), None)
    unit = (unit_el.text or "").strip() if unit_el is not None else "pixel"
    if unit not in UNITS:
        raise UnknownMeasurementUnit(unit)

    page_el = next((el for el in root.iter() if _tag(el) == "Page"), None)
    if page_el is None:
        raise ValueError("no <Page> element: this is not an ALTO document")

    width = _float(page_el.get("WIDTH")) or 0.0
    height = _float(page_el.get("HEIGHT")) or 0.0

    page = SourcePage()
    # `Page@LANG` is read in every version. Found 2026-09-27 on kraken's own ALTO fixture
    # (an eScriptorium export of a Hebrew manuscript: `<Page ... LANG="hbo">`), which
    # declares 4.3 -- where Page@LANG does not exist -- and uses the attribute ALTO 4.4
    # added. The fact it states is true, so it is read whatever the declared version; and
    # since the writer emits 4.4, it is written back too.
    if page_el.get("LANG"):
        page.language = page_el.get("LANG")
    page.foreign["alto:MeasurementUnit"] = unit
    if width and height:
        # The page's size in ITS OWN unit, for every unit: the only record of its proportions
        # when the unit is not pixels, and what lets ALTO write it back as it came (#5130).
        page.page_extent = (float(width), float(height), unit)
    if unit == "pixel" and width and height:
        page.image_size = (int(width), int(height))

    filename = next((el for el in root.iter() if _tag(el) == "fileName"), None)
    if filename is not None and (filename.text or "").strip():
        page.image_name = filename.text.strip()
    software = next(
        (el for el in root.iter() if _tag(el) in ("softwareName", "processingSoftware")),
        None,
    )
    if software is not None:
        name = (software.text or "").strip()
        if not name:
            child = next((c for c in software if (c.text or "").strip()), None)
            name = (child.text or "").strip() if child is not None else ""
        page.producer = name or None

    block_refs: list[str] = []
    for element in page_el.iter():
        kind = ELEMENT_KINDS.get(_tag(element))
        if kind is None:
            continue
        if _is_implicit(element):
            # Something we invented on a previous export. A marked STRING carries a
            # line's own text, so the text goes back onto the line rather than being
            # dropped with the scaffolding -- losing it would be worse than the phantom
            # word we are avoiding.
            if kind == "word" and element.get("CONTENT"):
                parent = element.getparent()
                while parent is not None and _tag(parent) not in ELEMENT_KINDS:
                    parent = parent.getparent()
                if parent is not None:
                    owner = next(
                        (s for s in page.segments if s.ref == parent.get("ID")), None
                    )
                    if owner is not None and not owner.readings:
                        owner.readings.append(("transcription", element.get("CONTENT")))
            continue
        segment = PageSegment(kind=kind, ref=element.get("ID"))
        parent = element.getparent()
        while parent is not None and _tag(parent) not in ELEMENT_KINDS:
            parent = parent.getparent()
        if parent is not None and not _is_implicit(parent):
            segment.parent_ref = parent.get("ID")

        x = _float(element.get("HPOS"))
        y = _float(element.get("VPOS"))
        w = _float(element.get("WIDTH"))
        h = _float(element.get("HEIGHT"))
        if None not in (x, y, w, h) and width and height:
            segment.rect = [x / width, y / height, w / width, h / height]
        shape = next((c for c in element if _tag(c) == "Shape"), None)
        if shape is not None:
            polygon = next((c for c in shape if _tag(c) == "Polygon"), None)
            if polygon is not None and polygon.get("POINTS"):
                points = polygon.get("POINTS").replace(",", " ").split()
                pairs = [
                    [float(points[i]) / width, float(points[i + 1]) / height]
                    for i in range(0, len(points) - 1, 2)
                ]
                if len(pairs) >= 3:
                    segment.polygon = pairs
                elif pairs:
                    # TWO-POINT POLYGON, which eScriptorium writes in ALTO as well as
                    # in PAGE XML: two opposite corners, not a shape. A polygon of two
                    # points cannot be drawn, so it is read as the rect it means and
                    # the raw points are kept.
                    #
                    # **This fix landed on the PAGE XML reader first and not here**,
                    # and their own ALTO export is what found the sibling — the same
                    # one-caller-not-its-siblings shape this programme has met seven
                    # times. Both readers now agree.
                    xs = [point[0] for point in pairs]
                    ys = [point[1] for point in pairs]
                    segment.rect = [
                        min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
                    ]
                    segment.foreign["alto:polygon"] = polygon.get("POINTS")
        if segment.polygon is None and segment.rect:
            rx, ry, rw, rh = segment.rect
            segment.polygon = [[rx, ry], [rx + rw, ry], [rx + rw, ry + rh], [rx, ry + rh]]

        if element.get("CONTENT"):
            segment.readings.append(("transcription", element.get("CONTENT")))
        # ALTO's LANG is `xsd:language` -- a BCP 47 TAG, where PAGE XML's
        # primaryLanguage is a closed list of NAMES. The two interchange formats
        # disagree, so whichever the model stores, one export has to map.
        if element.get("LANG"):
            segment.language = element.get("LANG")
        if kind == "region" and segment.ref:
            block_refs.append(segment.ref)
        page.segments.append(segment)

    if block_refs:
        # ALTO has no ReadingOrder element: the order IS the document order of its
        # blocks. Naming it `as-written` is honest -- it is what the file says, and
        # the file has no way to say anything else.
        page.orders.append(PageOrder(name="as-written", refs=block_refs))
    return page


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as ALTO 4.4, with everything it cannot carry reported."""
    from lxml import etree

    # A page with no pixel grid but a STATED size in another unit is written back in that unit
    # and at that size (#5130): ALTO can say `mm10`, so nothing needs inventing. Before this a
    # `mm10` page came back as a square 1000x1000 `pixel` page and every shape was stretched.
    unit_out = "pixel"
    if page.image_size is None and page.page_extent is not None and page.page_extent[2] != "pixel":
        width, height, unit_out = page.page_extent
    else:
        width, height = pixel_grid(page, report, "ALTO")

    root = etree.Element(f"{{{ALTO_NS_V4}}}alto", nsmap={None: ALTO_NS_V4, "xsi": XSI_NS})
    # The release is DECLARED, not left to the reader: ALTO keeps one namespace for all of
    # 4.x, so only the schema file named here (and SCHEMAVERSION) says this is 4.4.
    root.set("SCHEMAVERSION", ALTO_WRITTEN_VERSION)
    root.set(
        f"{{{XSI_NS}}}schemaLocation",
        f"{ALTO_NS_V4} http://www.loc.gov/standards/alto/v4/{ALTO_WRITTEN_SCHEMA}",
    )
    description = etree.SubElement(root, f"{{{ALTO_NS_V4}}}Description")
    etree.SubElement(description, f"{{{ALTO_NS_V4}}}MeasurementUnit").text = unit_out
    source = etree.SubElement(
        description, f"{{{ALTO_NS_V4}}}sourceImageInformation"
    )
    etree.SubElement(source, f"{{{ALTO_NS_V4}}}fileName").text = (
        page.image_name or "unknown.tif"
    )

    layout = etree.SubElement(root, f"{{{ALTO_NS_V4}}}Layout")
    page_el = etree.SubElement(
        layout,
        f"{{{ALTO_NS_V4}}}Page",
        ID="P1",
        PHYSICAL_IMG_NR="1",
        WIDTH=str(int(width)),
        HEIGHT=str(int(height)),
    )
    print_space = etree.SubElement(
        page_el,
        f"{{{ALTO_NS_V4}}}PrintSpace",
        HPOS="0",
        VPOS="0",
        WIDTH=str(int(width)),
        HEIGHT=str(int(height)),
    )

    # ALTO 4.4 added `Page@LANG` (a BCP 47 tag). Until the writer moved to 4.4 the page's
    # language was DECLARED LOST, because 4.2 had nowhere for it; a real eScriptorium
    # export already wrote it. Script and direction still have no page-level attribute,
    # so they are declared lost rather than copied onto every line, which would turn one
    # stated fact into hundreds (#5085).
    if page.language:
        if _looks_like_a_tag(page.language):
            page_el.set("LANG", page.language)
        else:
            report.note(
                "the page's language",
                1,
                f"ALTO's Page@LANG is a BCP 47 tag and {page.language!r} is a language "
                "NAME, which ALTO cannot express",
            )
    for what, value in (("script", page.script), ("direction", page.direction)):
        if value:
            report.note(
                f"the page's {what}",
                1,
                f"ALTO states {what} per element and has no page-level attribute for it, and "
                "copying a page's fact onto every line would store a derived fact as a "
                "stated one",
            )

    if len(page.orders) > 1:
        report.note(
            "named reading orders",
            len(page.orders) - 1,
            "ALTO has no reading-order element: the order is the document order of "
            "its blocks, so only one order can be expressed",
        )

    ordered = _in_first_order(page)
    # Which lines already have words under them. ALTO requires a `TextLine` to hold at
    # least one `String`, and a converted page's lines usually have none -- their text
    # is on the line itself. So a line with a reading and no words gets an implicit
    # `String`, which is the implicit-parent ruling turned upside down: invent the
    # required CHILD, put the line's own reading in it, mark it, and drop it again on
    # re-import so a round trip does not grow a word per line.
    has_words = {
        segment.parent_ref
        for segment in page.segments
        if segment.kind == "word" and segment.parent_ref
    }
    by_ref: dict[str, Any] = {}
    for index, segment in enumerate(ordered):
        element_name = KIND_ELEMENTS.get(segment.kind)
        if element_name is None:
            report.note(
                f"{segment.kind} segments", 1, "ALTO has no element for this granularity"
            )
            continue
        ref = segment.ref or f"s{index}"
        parent_el = by_ref.get(segment.parent_ref or "")
        if parent_el is None:
            # A block belongs directly under `PrintSpace`; only a line or a word has a
            # required ancestor in ALTO.
            parent_el = (
                print_space
                if segment.kind not in ("line", "word", "character")
                else _implicit_parents(
                    etree, print_space, segment.kind, ref, by_ref, report, width, height
                )
            )
        attrs = {"ID": xml_id(ref)}
        rect = segment.rect or _bounds(segment.polygon)
        if rect:
            attrs.update(
                HPOS=str(int(round(rect[0] * width))),
                VPOS=str(int(round(rect[1] * height))),
                WIDTH=str(int(round(rect[2] * width))),
                HEIGHT=str(int(round(rect[3] * height))),
            )
        if segment.kind == "word":
            # `String@CONTENT` is REQUIRED (#5130): an untranscribed word -- the ordinary
            # state of a segmented page nobody has read yet -- is written `CONTENT=""`,
            # which `xsd:string` allows, and the reader takes an empty CONTENT as no
            # reading. Omitting the attribute failed 15 of 239 real pages.
            attrs["CONTENT"] = segment.readings[0][1] if segment.readings else ""
        element = etree.SubElement(
            parent_el, f"{{{ALTO_NS_V4}}}{element_name}", **attrs
        )
        by_ref[ref] = element

        if segment.language:
            # ALTO wants a BCP 47 tag. A language NAME (which is what the engine
            # stores, #2092, and what PAGE XML uses) is not one, so it cannot be
            # written here and the loss is reported rather than emitting something
            # that fails `xsd:language`.
            if _looks_like_a_tag(segment.language):
                element.set("LANG", segment.language)
            else:
                report.note(
                    "language",
                    1,
                    f"ALTO's LANG is a BCP 47 tag and {segment.language!r} is a "
                    "language NAME, which ALTO cannot express (PAGE XML is the "
                    "opposite: it takes names and refuses tags)",
                )
        if segment.script:
            report.note(
                "script",
                1,
                "ALTO has no script attribute; PAGE XML's primaryScript has no "
                "ALTO equivalent",
            )
        if segment.direction:
            report.note(
                "direction",
                1,
                "ALTO has no reading-direction attribute, so a right-to-left page "
                "reads as its coordinates alone",
            )
        # A TextLine must hold at least one String (the schema's sequence has no
        # minOccurs="0"), so an UNTRANSCRIBED line with no words gets the implicit String
        # too, with `CONTENT=""` -- writing none was the other half of #5130's defect.
        if segment.kind == "line" and ref not in has_words:
            # The required child, carrying the line's own words. Marked, so the reader
            # drops it and the line's text comes back on the LINE rather than as a word
            # nobody segmented.
            etree.SubElement(
                element,
                f"{{{ALTO_NS_V4}}}String",
                ID=xml_id(f"{IMPLICIT_ID_PREFIX}string-{ref}"),
                CONTENT=segment.readings[0][1] if segment.readings else "",
                HPOS=attrs.get("HPOS", "0"),
                VPOS=attrs.get("VPOS", "0"),
                WIDTH=attrs.get("WIDTH", "0"),
                HEIGHT=attrs.get("HEIGHT", "0"),
            )
            report.note(
                "implicit words",
                1,
                "ALTO requires a TextLine to hold a String, and this line has no words (its text, if any, is on "
                "the line itself), so one String was invented with an id marked "
                "`fichero-implicit-` and is dropped again on re-import",
            )
        elif segment.kind == "region" and segment.readings:
            report.note(
                "text on a region",
                1,
                "ALTO carries text on String elements only, and a region's own reading "
                "has nowhere to go (a line's is carried by an implicit String)",
            )
        if len(segment.readings) > 1:
            report.note(
                "several readings",
                1,
                "ALTO's CONTENT is one string per String element: alternatives and "
                "the choice between them are not expressible",
            )
        if segment.baseline:
            report.note(
                "baseline",
                1,
                "ALTO 4 has BASELINE on TextLine as a single y or a polyline "
                "depending on version; it is not written here rather than written "
                "in a shape a reader may misread",
            )

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _implicit_parents(
    etree: Any, print_space: Any, kind: str, ref: str, by_ref: dict,
    report: LossReport, width: int, height: int,
) -> Any:
    """The elements a segment must sit inside, invented when the source had none (#5084).

    ALTO refuses a `String` directly under `PrintSpace` -- **found the day ALTO first
    validated**, which is the whole argument for validating before handing over bytes.

    Each invented element needs a BOX, because ALTO's are required, so it takes the
    child's own: an invented block is exactly as big as the thing inside it, which is
    the least the format will accept and claims nothing extra about the page.
    """
    chains = {
        "word": ["TextBlock", "TextLine"],
        "line": ["TextBlock"],
        "character": ["TextBlock", "TextLine", "String"],
    }
    chain_names = chains.get(kind, ["TextBlock"])
    parent_el = print_space
    for name in chain_names:
        implicit_id = xml_id(f"{IMPLICIT_ID_PREFIX}{name.lower()}-{ref}")
        parent_el = etree.SubElement(
            parent_el,
            f"{{{ALTO_NS_V4}}}{name}",
            ID=implicit_id,
            HPOS="0", VPOS="0", WIDTH=str(int(width)), HEIGHT=str(int(height)),
        )
        by_ref[implicit_id] = parent_el
    report.note(
        "implicit parents",
        1,
        f"ALTO requires a {kind} inside {', '.join(chain_names)}; this one had none, "
        "so they were invented with an id marked `fichero-implicit-` and are dropped "
        "again on re-import",
    )
    return parent_el


def _in_first_order(page: SourcePage) -> list[PageSegment]:
    """The page's segments, regions in the first named order's sequence.

    ALTO's order IS its document order, so the ONE thing a writer can do to carry a
    named order is emit the blocks in that sequence. Segments the order does not
    mention keep their own relative order after it -- dropping them would lose
    content, and an order is a claim about sequence rather than about membership
    here, unlike the derived text where leaving them out is the point.
    """
    if not page.orders:
        return list(page.segments)
    wanted = {ref: index for index, ref in enumerate(page.orders[0].refs)}
    regions = [s for s in page.segments if s.kind == "region"]
    others = [s for s in page.segments if s.kind != "region"]
    regions.sort(key=lambda s: wanted.get(s.ref or "", len(wanted)))
    out: list[PageSegment] = []
    for region in regions:
        out.append(region)
        out.extend([s for s in others if s.parent_ref == region.ref])
        for line in [s for s in others if s.parent_ref == region.ref]:
            out.extend([s for s in others if s.parent_ref == line.ref])
    seen = {id(s) for s in out}
    out.extend([s for s in page.segments if id(s) not in seen])
    return out


def _bounds(polygon: list[list[float]] | None) -> list[float] | None:
    if not polygon:
        return None
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _looks_like_a_tag(value: str) -> bool:
    """Whether a language value could be a BCP 47 tag rather than a name.

    Deliberately shallow: `xsd:language` is what the schema enforces, so this only
    has to keep a NAME out. "Spanish" has no hyphen and eight letters; `es` and
    `es-MX` are what a tag looks like.
    """
    first = value.split("-", 1)[0]
    return 2 <= len(first) <= 3 and first.isalpha() and first.islower()


register(
    FormatSpec(
        name="alto",
        extensions=(".xml",),
        read=read,
        write=write,
        schema=ALTO_WRITTEN_SCHEMA,
        round_trips=True,
        sniff=_sniff,
    )
)
