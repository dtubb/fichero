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
    pixel_grid,
    FormatSpec,
    LossReport,
    PageOrder,
    PageSegment,
    SourcePage,
    xml_id,
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
    # A CELL IS A REGION, which is what PAGE XML itself says: PAGE 2019 gives a
    # `TextRegion` inside a `TableRegion` a `TableCellRole`, and the 2013 files
    # Transkribus writes use a `TableCell` element for the same thing.
    #
    # Found 2026-09-27 by a real file (`transkribus_abp_table_0019.page.xml`, a parish
    # register with one `TableRegion` and 516 cells): before this, cells were not in
    # this map, so the reader skipped them and the parent walk climbed PAST them to the
    # table. Every one of that page's 355 lines came back parented to the
    # `TableRegion` — and the schema forbids a `TextLine` directly under one, so the
    # export refused ("This element is not expected"). Import worked, export could
    # not: a real table page was unroundtrippable, and no round trip could have shown
    # it because our writer never emits a table.
    #
    # Mapped to `region` rather than a new `cell` kind on purpose. `source.segment.
    # table-cells` (#4928, [GAP]) is where row, column, spans and header-ness become
    # part of the model; until then a cell is a region whose `row`/`col`/`rowSpan`/
    # `colSpan` ride in `foreign`, so nothing is lost and nothing is invented.
    "TableCell": "region",
    "ImageRegion": "picture",
    "SeparatorRegion": "separator",
    "GraphicRegion": "graphic",
}
#: The reverse of `ELEMENT_KINDS`, and it must stay the reverse. Found 2026-09-26
#: by a real file: the reader understood `GraphicRegion` and the writer did not, so a
#: page's graphic was read, then DECLARED LOST -- a loss report for something the
#: format can express perfectly well.
#:
#: **That is worse than a silent drop with a clean conscience**: it is honest data
#: destruction, and the loss report is for what a format CANNOT carry, never for what
#: a writer did not get round to. Every kind the reader can produce has an element
#: here, and the test below asserts the two maps are inverses so the next added kind
#: cannot drift.
KIND_ELEMENTS: dict[str, str] = {
    "region": "TextRegion",
    "line": "TextLine",
    "word": "Word",
    "character": "Glyph",
    "table": "TableRegion",
    "picture": "ImageRegion",
    "separator": "SeparatorRegion",
    "graphic": "GraphicRegion",
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


#: The marker a SYNTHESISED parent carries (#5084). PAGE XML's schema requires a
#: `TextLine` to sit inside a region and a `Word` inside a line, but the model allows
#: a line nobody put in a region — a marginal note a scholar drew on its own is one.
#:
#: So the writer invents the parent the schema demands and MARKS it, and the reader
#: drops a marked parent again. **Following the off-page ruling**: write what the
#: format requires, record that we did, and give back what the source said — a
#: re-import must not return a region nobody drew.
IMPLICIT_ID_PREFIX = "fichero-implicit-"
IMPLICIT_CUSTOM = "fichero {implicit:true;}"
#: The same idea one level down (#5130): a segment the source gave NO shape -- Calfa's
#: lines are `<Coords points=""/>` with only a baseline, and eScriptorium writes a
#: `TextRegion` with no `Coords` at all -- still needs `Coords`, which PAGE 2019 requires.
#: So the writer works one out (the baseline's bounds, or a region's children's), MARKS
#: it, reports it, and the reader gives the segment back without it: a re-import must
#: not return a shape nobody drew.
DERIVED_COORDS_CUSTOM = "fichero {coords:derived;}"


def _is_implicit(element: Any) -> bool:
    """Whether this element is a parent WE invented rather than one the source had.

    Two signals, and either is enough: the `custom` marker (which survives any tool
    that preserves `custom`) and the id prefix (which survives a tool that does not).
    Belt and braces on purpose -- a marked parent read back as a real region is a
    region nobody drew, appearing in a scholar's page count.
    """
    return (
        IMPLICIT_CUSTOM in (element.get("custom") or "")
        or (element.get("id") or "").startswith(IMPLICIT_ID_PREFIX)
    )


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
    from fichero_server.formats.validation import root_element

    root = root_element(data)
    return root is not None and (root[0] in KNOWN_NAMESPACES or root[1].lower() == "pcgts")


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
    page.language = _language_in(page_el.get("primaryLanguage"))
    page.script = _script_in(page_el.get("primaryScript"))
    page.direction = DIRECTIONS_IN.get(page_el.get("readingDirection") or "")

    creator = next((child for child in root.iter() if _tag(child) == "Creator"), None)
    page.producer = (creator.text or "").strip() or None if creator is not None else None

    for element in page_el.iter():
        kind = ELEMENT_KINDS.get(_tag(element))
        if kind is None:
            continue
        if _is_implicit(element):
            # A parent we invented on a previous export. Dropped, so a round trip
            # returns the page the source described rather than our scaffolding.
            continue
        segment = PageSegment(kind=kind, ref=element.get("id"))
        parent = element.getparent()
        while parent is not None and _tag(parent) not in ELEMENT_KINDS:
            parent = parent.getparent()
        if parent is not None and not _is_implicit(parent):
            segment.parent_ref = parent.get("id")

        for child in element:
            child_tag = _tag(child)
            if (
                child_tag == "Coords"
                and child.get("points")
                and DERIVED_COORDS_CUSTOM not in (element.get("custom") or "")
            ):
                points = _points(child.get("points"), width, height)
                if len(points) >= 3:
                    segment.polygon = points
                elif points:
                    # TWO-POINT COORDS, which eScriptorium writes for its text
                    # blocks: `190,25 510,65` is a rectangle given by opposite
                    # corners, not a polygon. Found by importing their own export --
                    # `SourceAnchor` refuses a polygon of two points, correctly,
                    # because a two-point shape cannot be drawn.
                    #
                    # So it is read as the RECT it means, and the raw points are kept
                    # (`keeps-unrecognised`) rather than either inventing a third
                    # corner or dropping the shape.
                    xs = [point[0] for point in points]
                    ys = [point[1] for point in points]
                    segment.rect = [
                        min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
                    ]
                    segment.foreign["pagexml:coords"] = child.get("points")
            elif child_tag == "Baseline" and child.get("points"):
                segment.baseline = _points(child.get("points"), width, height) or None
            elif child_tag == "TextEquiv":
                text_el = next((c for c in child if _tag(c) == "Unicode"), None)
                text = (text_el.text if text_el is not None else child.text) or ""
                if text.strip():
                    segment.readings.append(("transcription", text))

        if segment.polygon and segment.rect is None:
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
        custom = (element.get("custom") or "").replace(DERIVED_COORDS_CUSTOM, "").strip()
        if custom:
            segment.foreign["custom"] = custom
        # A cell's place in its table. Kept because the model has no field for it yet
        # (`source.segment.table-cells`, #4928): dropping it would lose the ONE thing
        # that makes a table a table, and inventing a field for it here would decide a
        # behaviour that is not this format's to decide.
        for attribute in ("row", "col", "rowSpan", "colSpan"):
            if element.get(attribute) is not None:
                segment.foreign[f"pagexml:{attribute}"] = element.get(attribute)
        page.segments.append(segment)

    for element in root.iter():
        if _tag(element) != "OrderedGroup":
            continue
        indexed = [
            (_int_or(child.get("index"), position), position, child.get("regionRef"))
            for position, child in enumerate(element)
            if _tag(child) == "RegionRefIndexed" and child.get("regionRef")
        ]
        refs = [ref for _index, _position, ref in sorted(indexed)]
        if refs:
            if not page.orders:
                refs = _merge_custom_order(page, sorted(indexed))
            page.orders.append(
                PageOrder(name=element.get("id") or "as-written", refs=refs)
            )
    return page


#: `custom="readingOrder {index:2;}"`: Transkribus writes each region's place here as well as,
#: or instead of, in `<ReadingOrder>`.
_CUSTOM_ORDER_INDEX = re.compile(r"readingOrder\s*\{[^}]*?index\s*:\s*(\d+)")
#: `foreign` key on a region whose place the two sources of order disagree about (#5145).
ORDER_NOTE = "pagexml:reading-order"


def _int_or(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _merge_custom_order(page: SourcePage, indexed: list[tuple[int, int, str]]) -> list[str]:
    """The page's order when `<ReadingOrder>` names only SOME of its regions (#5145).

    The USS Albatross logbook names one region, at index 2, in its `<ReadingOrder>`; its two
    tables say `readingOrder {index:0;}` and `{index:1;}` in `custom`. Read as the group alone,
    the named region came first and the tables after it -- backwards. Here a top-level region
    the group does not name, with a `custom` index, is placed by that index among the named
    ones, whose relative order is kept. Where the two sources disagree, `<ReadingOrder>` wins
    (it is the element the schema defines for this), and the region carries a note saying so,
    which the export's loss report repeats. A region with neither is never dropped: it is not in
    the order, and `file_positions` puts it after the ordered ones in file order, as before.
    """
    named = {ref: index for index, _position, ref in indexed}
    entries: list[tuple[int, int, int, str]] = [
        (index, 0, position, ref) for index, position, ref in indexed
    ]
    # Text-bearing regions only. Transkribus numbers its SEPARATORS in `custom` too and leaves
    # them out of `<ReadingOrder>`: a line between columns is not something one reads, and
    # adding it would put three rules into a page's order of text.
    top_level = [
        s for s in page.segments if s.parent_ref is None and s.ref and s.kind in ("region", "table")
    ]
    for position, segment in enumerate(top_level):
        match = _CUSTOM_ORDER_INDEX.search(str(segment.foreign.get("custom") or ""))
        if match is None:
            continue
        custom_index = int(match.group(1))
        if segment.ref in named:
            if named[segment.ref] != custom_index:
                segment.foreign[ORDER_NOTE] = (
                    f"<ReadingOrder> puts it at index {named[segment.ref]} and its custom "
                    f"readingOrder at {custom_index}: <ReadingOrder> kept"
                )
            continue
        if custom_index in named.values():
            other = next(ref for ref, index in named.items() if index == custom_index)
            segment.foreign[ORDER_NOTE] = (
                f"its custom readingOrder index {custom_index} is also <ReadingOrder>'s index for "
                f"{other}: placed after {other}"
            )
        entries.append((custom_index, 1, position, segment.ref))
    return [ref for *_key, ref in sorted(entries)]


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as PAGE XML 2019, with everything it cannot carry reported.

    The losses are named here rather than discovered by a round trip, because a
    writer is the only thing that knows what it dropped.
    """
    from lxml import etree

    width, height = pixel_grid(page, report, "PAGE XML")
    clamped = _clamped_segment_count(page)
    if clamped:
        report.note(
            "points outside the page",
            clamped,
            "PAGE XML coordinates are non-negative and on the page, so points the source put "
            "outside it were clamped to its edge",
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

    # The PAGE's own facts (#5085). `PageType` carries these attributes for exactly
    # this purpose, so a document-level language is STATED rather than lost -- and
    # stated ONCE, where the page states it, instead of copied onto every line.
    page_language = _language_out(page.language, report)
    if page_language:
        page_el.set("primaryLanguage", page_language)
    page_script = _script_out(page.script, report)
    if page_script:
        page_el.set("primaryScript", page_script)
    if page.direction:
        mapped = DIRECTIONS_OUT.get(page.direction)
        if mapped:
            page_el.set("readingDirection", mapped)
        else:
            report.note(
                "direction",
                1,
                f"PAGE XML has no readingDirection for {page.direction!r}",
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
                # The SAME derivation as the element's own id, so the reference and the
                # element it names still match (#5084): an `xs:IDREF` that does not
                # resolve is a reading order pointing at nothing.
                regionRef=xml_id(ref),
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
        parent_el = by_ref.get(segment.parent_ref or "")
        if parent_el is None:
            # A REGION needs no parent: it belongs directly under `Page`. Only a line,
            # word or glyph has a required ancestor, and only then is one invented --
            # the first version wrapped every top-level region in an invented region,
            # which the schema refused and which would have been a page of phantom
            # blocks if it had not.
            parent_el = (
                page_el
                if segment.kind not in ("line", "word", "character")
                else _implicit_parents(
                    etree, page_el, segment.kind, ref, by_ref, report,
                    segment.rect or _bounds_of(segment.polygon), width, height,
                )
            )
        element = etree.SubElement(
            parent_el, f"{{{PAGE_NS_2019}}}{element_name}", id=xml_id(ref)
        )
        by_ref[ref] = element

        points = segment.polygon or _rect_points(segment.rect)
        if not points:
            derived = _rect_points(_derived_bounds(segment, page.segments))
            if derived:
                points = derived
                element.set("custom", DERIVED_COORDS_CUSTOM)
                report.note(
                    "shapes worked out for segments that had none",
                    1,
                    "PAGE XML requires Coords; this one was worked out from the baseline or "
                    f"the children, marked `{DERIVED_COORDS_CUSTOM}`, and dropped again on "
                    "re-import",
                )
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
        if segment.foreign.get(ORDER_NOTE):
            # The file's two statements of order disagreed on import, and one was kept (#5145).
            report.note("reading order", 1, f"{segment.ref}: {segment.foreign[ORDER_NOTE]}")
        # `source.format.keeps-unrecognised` has TWO halves, and this is the second:
        # content the model has no field for is kept on read AND WRITTEN BACK on
        # export to that format. Found by eScriptorium's own file: its
        # `custom="structure {type:title;}"` was being read into `foreign` and
        # dropped on the way out -- a silent loss, which is the one thing the loss
        # report exists to make impossible. Writing it back is the fix; declaring it
        # as a loss would have been settling for honest data destruction.
        if segment.foreign.get("custom"):
            # Composed with the derived-coords marker, never over it: overwriting it made
            # a worked-out region shape read back as one the source drew.
            element.set(
                "custom",
                " ".join(filter(None, [str(segment.foreign["custom"]), element.get("custom")])),
            )
        if segment.foreign.get("readingDirection") and not segment.direction:
            element.set("readingDirection", str(segment.foreign["readingDirection"]))

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


def _implicit_parents(
    etree: Any, page_el: Any, kind: str, ref: str, by_ref: dict, report: LossReport,
    rect: list[float] | None, width: int, height: int,
) -> Any:
    """The element a segment must sit inside, invented when the source had none (#5084).

    PAGE XML's schema puts a `TextLine` inside a region and a `Word` inside a line, so
    a line nobody put in a region -- a marginal note drawn on its own -- cannot be
    written where it belongs. Refusing would lose the note; writing it at the top level
    produces a file the schema rejects, which we would only learn from another tool.

    So the parent is invented, MARKED, and reported. The report matters: an invented
    region is a difference between the file and the page, and the rule all night has
    been that a change to what a source said must be visible.
    """
    #: What each granularity must sit inside, innermost last.
    chains = {
        "line": ["TextRegion"],
        "word": ["TextRegion", "TextLine"],
        "character": ["TextRegion", "TextLine", "Word"],
    }
    chain_names = chains.get(kind, ["TextRegion"])
    parent_el = page_el
    for depth, name in enumerate(chain_names):
        implicit_id = xml_id(f"{IMPLICIT_ID_PREFIX}{name.lower()}-{ref}")
        parent_el = etree.SubElement(
            parent_el,
            f"{{{PAGE_NS_2019}}}{name}",
            id=implicit_id,
            custom=IMPLICIT_CUSTOM,
        )
        # A region must carry `Coords` before its children, so an invented one takes
        # the CHILD's own box: exactly as big as the thing inside it, claiming nothing
        # extra about the page. Found by the schema refusing a parent with no shape.
        if rect:
            etree.SubElement(
                parent_el,
                f"{{{PAGE_NS_2019}}}Coords",
                points=_points_out(_rect_points(rect), width, height),
            )
        by_ref[implicit_id] = parent_el
    if chain_names:
        report.note(
            "implicit parents",
            1,
            "PAGE XML requires a line inside a region and a word inside a line; this "
            f"{kind} had none, so {', '.join(chain_names)} was invented, marked "
            f"`{IMPLICIT_CUSTOM}`, and is dropped again on re-import",
        )
    return parent_el


def _derived_bounds(segment: PageSegment, segments: list[PageSegment]) -> list[float] | None:
    """A box for a segment the source gave no shape: its baseline's bounds, else the union of
    its descendants' shapes, else its nearest ancestor's. None when there is nothing at all."""
    if segment.baseline:
        return _bounds_of(segment.baseline)
    boxes = []
    pending = [segment.ref] if segment.ref else []
    seen: set[str] = set()
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        for child in segments:
            if child.parent_ref != ref:
                continue
            box = child.rect or _bounds_of(child.polygon) or _bounds_of(child.baseline)
            if box:
                boxes.append(box)
            if child.ref:
                pending.append(child.ref)
    if not boxes:
        # Nothing of its own and nothing under it: a WORD with `<Coords points=""/>` in a real
        # NZZ page (#5130). The truthful box is its nearest ancestor's -- the word is somewhere
        # in its line -- and like every worked-out shape it is marked and dropped on re-import,
        # never claimed as drawn.
        by_ref = {s.ref: s for s in segments if s.ref}
        parent = by_ref.get(segment.parent_ref or "")
        seen_parents: set[str] = set()
        while parent is not None and parent.ref not in seen_parents:
            seen_parents.add(parent.ref)
            box = parent.rect or _bounds_of(parent.polygon) or _bounds_of(parent.baseline)
            if box:
                return box
            parent = by_ref.get(parent.parent_ref or "")
        return None
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    bottom = max(b[1] + b[3] for b in boxes)
    return [left, top, right - left, bottom - top]


def _bounds_of(polygon: list[list[float]] | None) -> list[float] | None:
    if not polygon:
        return None
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _rect_points(rect: list[float] | None) -> list[list[float]]:
    if not rect:
        return []
    x, y, w, h = rect
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _points_out(points: list[list[float]], width: int, height: int) -> str:
    """PAGE's `PointsType` is non-negative integers, so every point is CLAMPED to the page.

    A real Transkribus papyrus page has `points="165,-1 ..."` -- a line drawn a pixel above
    the image -- and writing it back unclamped made the whole export invalid (#5130). The
    writer reports how many segments were clamped (`_clamped_segment_count`), so the change
    to what the source said is visible.
    """
    return " ".join(
        f"{min(max(int(round(x * width)), 0), width)},{min(max(int(round(y * height)), 0), height)}"
        for x, y in points
    )


def _clamped_segment_count(page: SourcePage) -> int:
    """Segments with any point, box corner or baseline point outside the page."""
    def outside(points) -> bool:
        return any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in points)

    count = 0
    for segment in page.segments:
        shapes = [segment.polygon or [], segment.baseline or [], _rect_points(segment.rect)]
        if any(outside(shape) for shape in shapes if shape):
            count += 1
    return count


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
