"""TEI XML, in and out (#4945).

Spec: `formats-and-training.md` (`source.format.tei-in`, `.tei-out`,
`.round-trip-tei`); build notes: `build-notes-formats-harness.md`.

**TEI is not PAGE XML with different element names.** PAGE XML is a tree of shapes with text
hung on them. TEI is a DOCUMENT -- `<text>` with its own structure -- plus, separately, a
`<facsimile>` of `<surface>`s and `<zone>`s, and the two are joined by `@facs` pointers from the
text into the zones. So this module reads and writes TWO trees and the pointers between them, and
it does that against the same `SourcePage` every other format speaks: no field was added to
segments for TEI.

WHAT MAPS, and how:

* a **region** is an `<ab>` (text side) with a `<zone>` (image side), joined by `@facs`;
* a **line** is an `<lb facs="#zone"/>` milestone plus the text that follows it up to the next
  `<lb>` -- TEI lines are milestones, not containers, which is the shape difference that matters;
* a **word** is a `<w facs="#zone">` inside its line;
* a **baseline** is a `<path points>` inside the line's zone;
* **language, script and direction** are `@xml:lang` (`ar-Arab`: language, then script) and a
  CSS `@style` hint. `@xml:lang` on an `<lb>` does not scope the text after it, so a line that
  has any of these is wrapped in a `<seg>` carrying them;
* **several readings** are `<app><lem>` + `<rdg type=kind>`; which one counts is not expressible
  and is reported;
* **the reading order** is the order the text is written in.

WHAT IS KEPT, not thrown away (`source.format.keeps-unrecognised`): the whole `<teiHeader>`
verbatim on the page (`foreign["tei"]["teiHeader"]`), and the names of inline elements the model
has no field for, per segment. The header is written back when it still validates as TEI on its
own; a header that does not (a project's own namespace, an edition's custom ODD) is kept and
REPORTED as not written, because a file we write must validate.

WHAT REAL FILES TAUGHT. The TEI Consortium's own test file (`tests/unit/formats/fixtures/
tei_consortium_testtranscr.xml`): a surface whose frame does not start at 0, `@facs` on `<s>`
rather than `<lb>`, empty `<lb/>` after each line, and `<subst>`/`<add>`/`<del>`. An edition
(the Van Gogh Letters, not shipped: CC BY-NC-SA) added: zones with no coordinates at all, an
`<lb/>` written BEFORE the block that holds its text, a project namespace in the header, and many
pages per file split by `<pb>`; those dialects are reproduced as small hand-written files in
`TestDialectsAHandWrittenFileStandsInFor`, labelled as such. None of this is in a file we would
write ourselves, which is why real files are read first.
"""

from __future__ import annotations

import re
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
from fichero_server.formats.validation import parse

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
_XML_LANG = f"{{{XML_NS}}}lang"
_XML_ID = f"{{{XML_NS}}}id"

#: Text-side elements that are a REGION of text.
REGION_TAGS = frozenset({"ab", "p", "head", "l"})


class _NoAttributes:
    """An element with no attributes, for a segment the file makes but names nowhere."""

    def get(self, _name: str, default: Any = None) -> Any:
        return default


_NO_ATTRIBUTES = _NoAttributes()
#: Elements whose content is not the page's transcription.
NON_TRANSCRIPTION = frozenset({"note", "teiHeader", "facsimile"})
#: Inline elements the reader understands; anything else is recorded, not silently absorbed.
#: `foreign` key: the hands (their TEI labels, "m1", "m2") that wrote a line, in order.
TEI_HANDS = "tei:hands"

#: The side of a `<choice>` that is what the page says, as against what an editor made of it.
AS_WRITTEN = frozenset({"orig", "sic", "abbr"})

def _written_text(element: Any, kept: list | None = None, start: int = 0, marks: list | None = None) -> str:
    """`itertext()`, but a `<choice>` gives its as-written side only (never both, run together).

    With `kept`, each choice's OTHER side is appended to it as `_choice_record` makes it, `start`
    being where this element's text begins in its reading. With `marks`, the editor's marks inside
    (`MARK_TAGS`, #5179) are appended as the walker records them, at the same offsets."""
    parts = [element.text or ""]
    for child in element:
        if not isinstance(child.tag, str):
            pass
        elif _tag(child) == "choice":
            written, others = _choice_sides(child)
            if written is not None:
                if kept is not None:
                    at = start + len(_norm("".join(parts)))
                    kept.extend(_choice_record(at, written, other) for other in others)
                parts.append(_written_text(written))
        elif _tag(child) == "lb" and child.get("break") == "no":
            # A word that runs on across the line break: no space where the line broke.
            parts[-1] = parts[-1].rstrip()
            parts.append((child.tail or "").lstrip())
            continue
        else:
            at = start + len(_norm("".join(parts)))
            parts.append(_written_text(child, kept, at, marks))
            if marks is not None and _tag(child) in MARK_TAGS:
                end = start + len(_norm("".join(parts)))
                attrs = {name: child.get(name) for name in MARK_ATTRS if child.get(name) is not None}
                marks.append({"tag": _tag(child), "start": at, "end": end, "attrs": attrs})
        parts.append(child.tail or "")
    return "".join(parts)


def _choice_sides(choice: Any) -> tuple[Any, list]:
    """The as-written side of a `<choice>` (orig/sic/abbr; the first child if none is marked), and the rest."""
    sides = [c for c in choice if isinstance(c.tag, str)]
    written = next((c for c in sides if _tag(c) in AS_WRITTEN), sides[0] if sides else None)
    return written, [c for c in sides if c is not written]


def _choice_record(at: int, written: Any, other: Any) -> dict:
    return {
        "at": at,
        _tag(written): _norm(_written_text(written)).strip(),
        _tag(other): _norm(_written_text(other)).strip(),
    }


KNOWN_INLINE = frozenset({"lb", "pb", "w", "seg", "app", "lem", "rdg", "ab", "p", "head", "l",
                          "div", "text", "body", "TEI"})

#: The editor's marks on a stretch of text (#5179): recorded on the line (or region) as
#: `foreign["tei:marks"]`, each `{tag, start, end, attrs}` in code points of the line's reading, for
#: the import to write as editorial facts. `<gap>` is empty: its start is its end, a position.
MARK_TAGS = frozenset({"unclear", "supplied", "gap", "surplus", "add", "del", "delSpan"})
MARK_ATTRS = ("reason", "cert", "quantity", "unit", "extent", "place", "rend", "spanTo")
TEI_MARKS = "tei:marks"

#: `<note type=...>` that carries a word segment whose text is not in its line's text (#5083).
UNPLACED_WORD = "unplaced-word"
#: `foreign` key on a line placed only by its page's `<pb>` zone (#5141): the zone's id, so the
#: export writes `<pb facs="#id">` and bare `<lb/>`s, as the file did, not one zone per line.
PAGE_ZONE = "tei-page-zone"

DIRECTION_TO_STYLE = {
    "ltr": "direction: ltr",
    "rtl": "direction: rtl",
    "ttb": "writing-mode: vertical-rl",
}


def _tag(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag else str(tag)


def _norm(text: str) -> str:
    """Collapse the whitespace that is LAYOUT (a run containing a newline or tab: indentation
    between elements) and keep the whitespace that is TEXT (a double space inside a line). A blanket
    `\\s+` -> " " silently altered a transcription that has a double space (#5083's neighbour,
    found on the same Aepinus file); our own writer emits no layout whitespace at all."""
    return re.sub(r"[ \t\r\n\f\v]*[\n\t\r\f\v][ \t\r\n\f\v]*", " ", text)


# ---------------------------------------------------------------------------
# language / script / direction
# ---------------------------------------------------------------------------


def _lang_out(language: str | None, script: str | None, report: LossReport) -> str | None:
    """The model's language NAME (#2092) and ISO 15924 script as one BCP 47 `xml:lang`."""
    code: str | None = None
    if language:
        try:
            from iso639 import Lang

            lang = Lang(language)
            code = lang.pt1 or lang.pt3
        except Exception:  # noqa: BLE001 -- iso639 raises its own InvalidLanguageValue
            report.note(
                "language",
                1,
                f"{language!r} is not an ISO 639 language, so it has no `xml:lang` code; a "
                "project's own language cannot be stated in TEI's language attribute",
            )
    if code is None and script:
        code = "und"  # BCP 47's "undetermined", so the script can still be stated
    if code is None:
        return None
    return f"{code}-{script}" if script else code


def _lang_in(value: str | None) -> tuple[str | None, str | None, str | None]:
    """`ar-Arab` as `(name, script, unresolved_raw)`. A code that resolves to no language is
    returned raw so it can be KEPT rather than dropped."""
    if not value:
        return None, None, None
    parts = value.split("-")
    script = next((p.title() for p in parts[1:] if len(p) == 4 and p.isalpha()), None)
    primary = parts[0]
    if primary.lower() in ("und", "mis", "zxx"):
        return None, script, None
    try:
        from iso639 import Lang

        return Lang(primary).name, script, None
    except Exception:  # noqa: BLE001
        return None, script, value


def _direction_in(style: str | None) -> str | None:
    if not style:
        return None
    lowered = style.lower()
    if "direction" in lowered and "rtl" in lowered:
        return "rtl"
    if "direction" in lowered and "ltr" in lowered:
        return "ltr"
    if "vertical" in lowered:
        return "ttb"
    return None


# ---------------------------------------------------------------------------
# sniffing
# ---------------------------------------------------------------------------


def _sniff(data: bytes) -> bool:
    """TEI by its root element: `<TEI>` in the TEI namespace (or an unnamespaced `<TEI>`)."""
    from fichero_server.formats.validation import root_element

    root = root_element(data)
    return root is not None and (root[0] == TEI_NS or root[1] == "TEI")


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


def _points(raw: str, ox: float, oy: float, width: float, height: float) -> list[list[float]]:
    out: list[list[float]] = []
    for pair in raw.split():
        x_raw, sep, y_raw = pair.partition(",")
        if not sep:
            continue
        try:
            x, y = float(x_raw), float(y_raw)
        except ValueError:
            continue
        out.append([(x - ox) / width, (y - oy) / height])
    return out


class _Surface:
    """One `<surface>`: its own coordinate frame and its zones."""

    def __init__(self, element: Any) -> None:
        self.element = element
        self.image_name: str | None = None
        # the first graphic that is a direct child of the surface is THE image (zones carry
        # their own crops and thumbnails, which are not the page)
        for child in element:
            if _tag(child) == "graphic" and child.get("url"):
                self.image_name = child.get("url")
                break
        ulx, uly = _num(element.get("ulx")), _num(element.get("uly"))
        lrx, lry = _num(element.get("lrx")), _num(element.get("lry"))
        self.origin = (ulx or 0.0, uly or 0.0)
        self.size: tuple[float, float] | None = None
        if lrx is not None and lry is not None and lrx > (ulx or 0.0) and lry > (uly or 0.0):
            self.size = (lrx - (ulx or 0.0), lry - (uly or 0.0))

    def zones(self) -> dict[str, Any]:
        return {z.get(_XML_ID): z for z in self.element.iter(f"{{{TEI_NS}}}zone") if z.get(_XML_ID)}


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _zone_geometry(zone: Any, surface: _Surface) -> tuple[list[float] | None, list[list[float]] | None, list[list[float]] | None]:
    """`(rect, polygon, baseline)` normalised, or all None when the file gave no coordinates
    (a real file does that) or no frame to normalise them by."""
    if surface.size is None:
        return None, None, None
    (ox, oy), (w, h) = surface.origin, surface.size
    polygon = _points(zone.get("points"), ox, oy, w, h) if zone.get("points") else None
    rect = None
    ulx, uly, lrx, lry = (_num(zone.get(k)) for k in ("ulx", "uly", "lrx", "lry"))
    if None not in (ulx, uly, lrx, lry):
        rect = [(ulx - ox) / w, (uly - oy) / h, (lrx - ulx) / w, (lry - uly) / h]
    elif polygon:
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        rect = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    baseline = None
    for child in zone:
        if _tag(child) == "path" and child.get("points"):
            baseline = _points(child.get("points"), ox, oy, w, h) or None
    return rect, (polygon or None), baseline


def read_pages(data: bytes) -> list[SourcePage]:
    """Every page of a TEI file: one per `<pb>` (or one, when there is none)."""
    root = parse(data)
    if _tag(root) != "TEI":
        raise ValueError("no <TEI> root element: this is not a TEI document")

    surfaces = [_Surface(s) for s in root.iter(f"{{{TEI_NS}}}surface") if _tag(s.getparent()) == "facsimile"]
    zone_owner: dict[str, _Surface] = {}
    zones: dict[str, Any] = {}
    for surface in surfaces:
        for zid, zone in surface.zones().items():
            zones[zid] = zone
            zone_owner[zid] = surface
    surface_by_id = {s.element.get(_XML_ID): s for s in surfaces if s.element.get(_XML_ID)}

    header = next((c for c in root if _tag(c) == "teiHeader"), None)
    declared_signs = _signs_declared_in(header)
    header_xml = None
    if header is not None:
        from lxml import etree

        header_xml = etree.tostring(header, encoding="unicode")
    stated_makers = _responsibilities(header)
    text_el = next((c for c in root if _tag(c) == "text"), None)

    pages: list[dict[str, Any]] = []

    def new_page(pb: Any | None) -> dict[str, Any]:
        page = {"pb": pb, "segments": [], "regions": []}
        pages.append(page)
        return page

    # `hand`: the hand in effect -- a `<handShift new="#m2"/>` is a milestone that holds until the
    # next one, across lines and blocks, like `<lb>` (slice 14, `source.hand.attributed`).
    state: dict[str, Any] = {"page": None, "region": None, "line": None, "buffer": [], "counter": 0,
                             "line_page": None, "hand": None}

    def current_page() -> dict[str, Any]:
        return state["page"] or new_page(None)

    def add_segment(kind: str, element: Any, parent: PageSegment | None, page: dict[str, Any]) -> PageSegment:
        state["counter"] += 1
        segment = PageSegment(kind=kind, ref=element.get(_XML_ID) or f"{kind[0]}{state['counter']}")
        segment.parent_ref = parent.ref if parent is not None else None
        lang, script, raw = _lang_in(element.get(_XML_LANG))
        segment.language, segment.script = lang, script
        if raw:
            segment.foreign["xml:lang"] = raw
        segment.direction = _direction_in(element.get("style"))
        facs = (element.get("facs") or "").lstrip("#")
        page["segments"].append(segment)
        page.setdefault("facs", {})[segment.ref] = facs
        return segment

    def flush_line() -> None:
        line = state["line"]
        if line is None:
            return
        text = _norm("".join(state["buffer"])).strip()
        # An `<app>` whose `<lem>` IS the whole line offers whole-line alternatives: those are
        # readings of the line (our own writer's shape). A variant of PART of a line -- one word
        # of a papyrus -- is not a reading of the line: stored as one, it competed with the line
        # and, in a strict project, left the line with no counting text at all. It is kept with
        # its position, like a `<choice>`'s other side, until word-level segments can carry it.
        whole = []
        for kind, alt, lem_text, at in line.foreign.pop("_alts", []):
            if not text or lem_text == text:
                whole.append((kind, alt))
            else:
                line.foreign.setdefault("tei-app", []).append({"at": at, "lem": lem_text, "rdg": alt, "type": kind})
        if whole:
            line.foreign["_alts"] = whole
        if text:
            line.readings.insert(0, (line.foreign.pop("_kind", "transcription"), text))
        elif not line.foreign.get("_alts") and not page_facs_of(line):
            # A milestone that never got text or a zone is punctuation, not a line: real files
            # put `<lb/>` before `<lb/>` and before the block that holds the text.
            owner = state["line_page"]
            owner["segments"].remove(line)
        state["line"], state["buffer"] = None, []

    def page_facs_of(line: PageSegment) -> str:
        return state["line_page"].get("facs", {}).get(line.ref, "")

    def walk(element: Any, region: PageSegment | None, page: dict[str, Any]) -> None:
        tag = _tag(element)
        if tag == "note" and element.get("type") == UNPLACED_WORD and state["line"] is not None:
            # A word the line's own text does not contain (PAGE XML lets a `Word` carry text its
            # `TextLine` does not). It is a word segment of the line and NOT part of the line's text.
            word = add_segment("word", element, state["line"], page)
            text = _norm(_written_text(element)).strip()
            if text:
                word.readings.append(("transcription", text))
            _tail(element)
            return
        if tag in NON_TRANSCRIPTION or not isinstance(element.tag, str):
            return
        if tag == "pb":
            flush_line()
            state["page"] = page = new_page(element)
            state["region"] = region = None
            _tail(element)
            return
        verse_inside_a_line = (
            tag == "l" and state["line"] is not None
            and any(_tag(a) == "seg" for a in element.iterancestors())
        )
        # A poem INSIDE a printed line (the Digital Genji's waka: `<lb/><seg>　　<lg><l>..</l>
        # ..</lg>いとか</seg>`) is verse divisions of that line, not regions of the page. Read as
        # regions, the line was split into five and the text after the poem was DROPPED (#5143).
        if tag in REGION_TAGS and element.get("type") != "anonymous" and not verse_inside_a_line:
            # A `<lb/>` written just BEFORE its block still owns the block's first text (real
            # files do this): an open line with nothing in it is adopted, not flushed.
            adopt = state["line"] if (state["line"] is not None and not "".join(state["buffer"]).strip()) else None
            if adopt is None:
                flush_line()
            seg = add_segment("region", element, None, page)
            page["regions"].append(seg.ref)
            state["region"] = seg
            if adopt is not None:
                adopt.parent_ref = seg.ref
                # keep parents before children in the page's order
                page["segments"].remove(adopt)
                page["segments"].insert(page["segments"].index(seg) + 1, adopt)
            else:
                state["buffer"] = []
                state["line"] = None
            _children(element, seg, page)
            if state["line"] is None:
                # no lb inside: the region itself carries the text
                text = _norm("".join(state["buffer"])).strip()
                if text:
                    seg.readings.append(("transcription", text))
            flush_line()
            state["region"] = None
            _tail(element)
            return
        if tag == "lb":
            if state["line"] is None and region is not None and _norm("".join(state["buffer"])).strip():
                # Text BEFORE the first `<lb>` of a block that has no open line: a verse line
                # written `<l>text <lb/></l>`, its break AFTER the text (the TEI Consortium's
                # Hamlet). That text is a line of its own. It went nowhere -- the block took no
                # text once it had a line, and no line held it -- and the lines were dropped.
                leading = add_segment("line", _NO_ATTRIBUTES, region, page)
                state["line"], state["line_page"] = leading, page
                marks = region.foreign.pop(TEI_MARKS, None)
                if marks:
                    leading.foreign[TEI_MARKS] = marks
            flush_line()
            line = add_segment("line", element, region, page)
            state["line"], state["buffer"], state["line_page"] = line, [], page
            if state["hand"]:
                line.foreign[TEI_HANDS] = [state["hand"]]
            _tail(element)
            return
        if tag == "handShift":
            # The hand that writes from here on. A line keeps every hand that wrote in it, in order:
            # the one in effect when it began, and any that took over part-way along.
            new = (element.get("new") or "").lstrip("#").strip()
            if new:
                state["hand"] = new
                line = state["line"]
                if line is not None:
                    if not "".join(state["buffer"]).strip():
                        # Before any of the line's text: the new hand wrote the whole line.
                        line.foreign[TEI_HANDS] = [new]
                    elif new not in line.foreign.setdefault(TEI_HANDS, []):
                        line.foreign[TEI_HANDS].append(new)
            _tail(element)
            return
        if tag == "s" and element.get("facs"):
            # A sentence-level element pointing at a zone is the LINE in the encodings that put
            # `@facs` on `<s>` and follow it with an empty `<lb/>` (the TEI Consortium's own
            # transcription example does).
            flush_line()
            line = add_segment("line", element, region, page)
            state["line"], state["buffer"], state["line_page"] = line, [], page
            state["buffer"].append(_norm(_written_text(element)))
            flush_line()
            _tail(element)
            return
        if tag == "w":
            text = _norm(_written_text(element))
            line = state["line"]
            word = add_segment("word", element, line, page)
            if text.strip():
                word.readings.append(("transcription", text.strip()))
            state["buffer"].append(text)
            _tail(element)
            return
        if tag == "choice":
            # ONE stretch, two readings an encoder paired: as written, and regularised /
            # corrected / expanded (`readings-and-apparatus.md`, the `<choice>` note). Reading
            # both sides into the text invents a word on neither the page nor in the edition
            # ("κεχωνευμένακεχωνημένα", #5130). Until word-level segments can carry the pair as
            # two readings, the line's text takes the AS-WRITTEN side and the other side is kept
            # verbatim, with its position, and named by the export's loss report.
            written, others = _choice_sides(element)
            holder = state["line"] if state["line"] is not None else state["region"]
            at = len(_norm("".join(state["buffer"])).lstrip())
            if written is not None:
                _children(written, region, page)
            if holder is not None and written is not None:
                holder.foreign.setdefault("tei-choice", []).extend(
                    _choice_record(at, written, other) for other in others
                )
            _tail(element)
            return
        if tag == "app":
            lem = next((c for c in element if _tag(c) == "lem"), None)
            at = len(_norm("".join(state["buffer"])).lstrip())
            lem_text = ""
            if lem is not None:
                holder = state["line"] if state["line"] is not None else state["region"]
                kept: list = []
                marks: list = []
                lem_text = _written_text(lem, kept, at, marks)
                state["buffer"].append(lem_text)
                if holder is not None and kept:
                    holder.foreign.setdefault("tei-choice", []).extend(kept)
                if holder is not None and marks:
                    holder.foreign.setdefault(TEI_MARKS, []).extend(marks)
            line = state["line"]
            for rdg in (c for c in element if _tag(c) == "rdg"):
                alt = _norm(_written_text(rdg)).strip()
                if line is not None and alt:
                    line.foreign.setdefault("_alts", []).append(
                        (rdg.get("type") or "transcription", alt, _norm(lem_text).strip(), at)
                    )
            if lem is not None and lem.get("type") and state["line"] is not None:
                state["line"].foreign["_kind"] = lem.get("type")
            _tail(element)
            return
        if tag == "seg" and state["line"] is not None and not "".join(state["buffer"]).strip():
            line = state["line"]
            lang, script, raw = _lang_in(element.get(_XML_LANG))
            line.language, line.script = lang or line.language, script or line.script
            line.direction = _direction_in(element.get("style")) or line.direction
            if raw:
                line.foreign["xml:lang"] = raw
            if element.get("type"):
                line.foreign["_kind"] = element.get("type")
        elif tag not in KNOWN_INLINE and state["line"] is not None:
            state["line"].foreign.setdefault("inline", set()).add(tag)
        elif tag not in KNOWN_INLINE and state["region"] is not None:
            state["region"].foreign.setdefault("inline", set()).add(tag)
        start = _mark_at() if tag in MARK_TAGS else None
        if element.text:
            state["buffer"].append(element.text)
        _children(element, region, page, skip_text=True)
        if start is not None:
            _mark(element, start, _mark_at())
        _tail(element)

    def _mark_at() -> int:
        """Where the next character of the holder's reading is: the same offset `<choice>` uses."""
        return len(_norm("".join(state["buffer"])).lstrip())

    def _mark(element: Any, start: int, end: int, **extra: Any) -> None:
        holder = state["line"] if state["line"] is not None else state["region"]
        if holder is None:
            return
        attrs = {name: element.get(name) for name in MARK_ATTRS if element.get(name) is not None}
        holder.foreign.setdefault(TEI_MARKS, []).append(
            {"tag": _tag(element), "start": start, "end": end, "attrs": attrs, **extra})

    def _tail(element: Any) -> None:
        if element.tail:
            state["buffer"].append(element.tail)

    def _children(element: Any, region: PageSegment | None, page: dict[str, Any], skip_text: bool = False) -> None:
        if not skip_text and element.text:
            state["buffer"].append(element.text)
        for child in element:
            walk(child, region, state["page"] or page)

    if text_el is not None:
        first = new_page(None)
        state["page"] = first
        _children(text_el, None, first)
        flush_line()
    else:
        new_page(None)
    # A pb before any text leaves an empty first page that was never a page.
    pages = [p for i, p in enumerate(pages) if p["segments"] or i > 0 or len(pages) == 1]

    out: list[SourcePage] = []
    for index, raw_page in enumerate(pages):
        page = SourcePage()
        page.producer = stated_makers
        page.signs = [dict(sign) for sign in declared_signs]
        pb = raw_page["pb"]
        surface: _Surface | None = None
        if pb is not None:
            # `facs` is the usual pointer, but it may be an IMAGE URL (the Digital Genji's is a
            # IIIF crop); then `corresp="#zone_..."` is what names the zone (#5130). Only a
            # local `#id` is a pointer into this file's facsimile.
            for attr in ("facs", "corresp"):
                value = pb.get(attr) or ""
                target = value[1:] if value.startswith("#") else (value if attr == "facs" else "")
                surface = surface_by_id.get(target) or zone_owner.get(target) if target else None
                if surface is not None:
                    if target in zones:
                        page.foreign.setdefault("tei", {})["zone"] = target
                    break
        if surface is None and index < len(surfaces):
            surface = surfaces[index]
        if pb is not None:
            # What names this page, so a caller that takes some pages and not others can say
            # WHICH it left out (#5143): `<pb n>` is the page's number, `facs`/`corresp` its image.
            described = {k: pb.get(k) for k in ("n", "facs", "corresp") if pb.get(k)}
            if described:
                page.foreign.setdefault("tei", {})["pb"] = described
        if surface is not None:
            if surface.element.get(_XML_ID):
                page.foreign.setdefault("tei", {})["surface"] = surface.element.get(_XML_ID)
            page.image_name = surface.image_name
            if surface.size:
                page.image_size = (int(round(surface.size[0])), int(round(surface.size[1])))
        # A region OPENED before a page break owns lines on the NEXT page too (the Genji's one
        # `<p>` holds every page). A parent that is not on this page is no parent here: the
        # line stands alone, and a writer whose format needs a parent invents a marked one.
        on_page = {s.ref for s in raw_page["segments"]}
        for s in raw_page["segments"]:
            if s.parent_ref and s.parent_ref not in on_page:
                s.parent_ref = None
        parents_with_children = {s.parent_ref for s in raw_page["segments"] if s.parent_ref}
        kept_segments = [
            s for s in raw_page["segments"]
            if not (
                s.kind == "region" and not s.readings and s.ref not in parents_with_children
                and not raw_page.get("facs", {}).get(s.ref)
            )
        ]
        # a region with nothing in it and no zone is a wrapper (`<sp>`'s speaker, an empty `<ab/>`),
        # not a region of the page
        raw_page["regions"] = [r for r in raw_page["regions"] if any(k.ref == r for k in kept_segments)]
        page_zone = page.foreign.get("tei", {}).get("zone")
        for segment in kept_segments:
            facs = raw_page.get("facs", {}).get(segment.ref)
            if facs and facs in zones and facs in zone_owner:
                rect, polygon, baseline = _zone_geometry(zones[facs], zone_owner[facs])
                segment.rect, segment.polygon, segment.baseline = rect, polygon, baseline
            elif segment.kind == "line" and page_zone in zones and page_zone in zone_owner:
                # A line that names no zone of its own, on a page whose `<pb>` names one (the
                # Digital Genji: `<pb corresp="#zone_0005">`, then bare `<lb/>`s). The file
                # places the line in that zone and no more precisely, so its shape IS the zone
                # (#5141) -- not `unstated`, which would say the file gave no place at all.
                # Marked, so the export refers to the zone instead of minting one per line.
                rect, polygon, _ = _zone_geometry(zones[page_zone], zone_owner[page_zone])
                segment.rect, segment.polygon = rect, polygon
                segment.foreign[PAGE_ZONE] = page_zone
            alts = segment.foreign.pop("_alts", [])
            segment.readings.extend(alts)
            segment.foreign.pop("_kind", None)
            inline = segment.foreign.pop("inline", None)
            if inline:
                segment.foreign["tei-inline"] = sorted(inline)
            page.segments.append(segment)
        if raw_page["regions"]:
            page.orders.append(PageOrder(name="as-written", refs=list(raw_page["regions"])))
        tei_foreign: dict[str, Any] = {}
        if header_xml is not None:
            tei_foreign["teiHeader"] = header_xml
        if len(pages) > 1:
            tei_foreign["page"] = f"{index + 1} of {len(pages)}"
        if tei_foreign:
            # MERGED, not assigned: the page's zone is already recorded under "tei".
            page.foreign.setdefault("tei", {}).update(tei_foreign)
        out.append(page)
    # A "page" before the first `<pb>` that holds nothing once wrappers are dropped was never a
    # page (#5130): the Genji opens its `<p>` and an `<lb/>` before the first `<pb>`, and
    # `read()` returned that empty stub -- 25 real pages read as ZERO segments.
    if len(out) > 1 and pages[0]["pb"] is None and not out[0].segments:
        out = out[1:]
        for index, page in enumerate(out):
            if "page" in page.foreign.get("tei", {}):
                page.foreign["tei"]["page"] = f"{index + 1} of {len(out)}"
    return out


def _responsibilities(header: Any) -> str | None:
    """Who the FILE says made it (#5150): its `<respStmt>`s, `resp: name, name; resp: name`, in
    the header's order -- the Digital Genji names three transcribers, an encoder and an advisor.
    The file's claim, recorded as such."""
    if header is None:
        return None
    by_resp: dict[str, list[str]] = {}
    for stmt in header.iter(f"{{{TEI_NS}}}respStmt"):
        resp = next((c for c in stmt if _tag(c) == "resp"), None)
        role = " ".join("".join(resp.itertext()).split()) if resp is not None else ""
        names = [" ".join("".join(n.itertext()).split()) for n in stmt if _tag(n) in ("name", "persName", "orgName")]
        for name in (n for n in names if n):
            by_resp.setdefault(role or "responsible", []).append(name)
    return "; ".join(f"{role}: {', '.join(names)}" for role, names in by_resp.items()) or None


def describe_page(page: SourcePage, number: int) -> str:
    """How a person finds one page of a TEI file: `page 6 (#zone_0006)` -- its `<pb n>` and what
    its `<pb>` points at -- or `page 2 of the file` when the page break says nothing (#5143)."""
    pb = (page.foreign.get("tei") or {}).get("pb") or {}
    label = f"page {pb['n']}" if pb.get("n") else f"page {number} of the file"
    pointer = pb.get("corresp") or pb.get("facs")
    return f"{label} ({pointer})" if pointer else label


def read(data: bytes) -> SourcePage:
    """The first page of a TEI file (a multi-page file: use `read_pages`)."""
    return read_pages(data)[0]


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


def _points_out(points: list[list[float]], width: int, height: int) -> str:
    return " ".join(f"{int(round(x * width))},{int(round(y * height))}" for x, y in points)


def _rect_points(rect: list[float] | None) -> list[list[float]]:
    if not rect:
        return []
    x, y, w, h = rect
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def write(page: SourcePage, report: LossReport) -> bytes:
    """One page as TEI, with everything it cannot carry reported."""
    from lxml import etree

    def q(name: str) -> str:
        return f"{{{TEI_NS}}}{name}"

    width, height = pixel_grid(page, report, "TEI")

    root = etree.Element(q("TEI"), nsmap={None: TEI_NS})
    header = _header(page, report, root)
    facsimile = etree.SubElement(root, q("facsimile"))
    surface = etree.SubElement(
        facsimile, q("surface"), {_XML_ID: "surface1", "ulx": "0", "uly": "0", "lrx": str(width), "lry": str(height)}
    )
    etree.SubElement(surface, q("graphic"), url=page.image_name or "unknown.png")
    text_el = etree.SubElement(root, q("text"))
    body = etree.SubElement(text_el, q("body"))
    div = etree.SubElement(body, q("div"))

    by_ref = {s.ref: s for s in page.segments if s.ref}
    children: dict[str | None, list[PageSegment]] = {}
    for segment in page.segments:
        children.setdefault(segment.parent_ref if segment.parent_ref in by_ref else None, []).append(segment)

    zone_ids: dict[int, str] = {}

    def zone_for(segment: PageSegment) -> str | None:
        points = segment.polygon or _rect_points(segment.rect)
        if not points and not segment.baseline:
            return None
        zid = f"z{len(zone_ids) + 1}"
        zone_ids[id(segment)] = zid
        zone = etree.SubElement(surface, q("zone"), {_XML_ID: zid})
        if segment.polygon:
            zone.set("points", _points_out(segment.polygon, width, height))
        elif segment.rect:
            x, y, w, h = segment.rect
            zone.set("ulx", str(int(round(x * width))))
            zone.set("uly", str(int(round(y * height))))
            zone.set("lrx", str(int(round((x + w) * width))))
            zone.set("lry", str(int(round((y + h) * height))))
        if segment.baseline:
            etree.SubElement(zone, q("path"), points=_points_out(segment.baseline, width, height))
        return zid

    def describe(element: Any, segment: PageSegment) -> None:
        lang = _lang_out(segment.language, segment.script, report)
        if lang:
            element.set(_XML_LANG, lang)
        if segment.direction:
            style = DIRECTION_TO_STYLE.get(segment.direction)
            if style:
                element.set("style", style)
            else:
                report.note(
                    "direction",
                    1,
                    f"TEI has only a CSS style hint for direction (ltr, rtl, vertical); "
                    f"{segment.direction!r} has none",
                )
        if segment.foreign.get(TEI_HANDS):
            report.note(
                "hands",
                1,
                "the hands a line was written in (from <handShift>) are kept in the library as hands and "
                "attributions, and are not yet written back as <handShift>",
            )
        for variant in segment.foreign.get("tei-app", []):
            report.note(
                "variant readings",
                1,
                f"{segment.ref or segment.kind}, character {variant['at']}: <lem>{variant['lem']}</lem> kept, "
                f"<rdg>{variant['rdg']}</rdg> not written back -- a variant of part of a line needs "
                "word-level segments to carry",
            )
        for choice in segment.foreign.get("tei-choice", []):
            (w_tag, w_text), (o_tag, o_text) = [(k, v) for k, v in choice.items() if k != "at"][:2]
            # One line per choice: which side was dropped, and where, so nothing goes silently.
            report.note(
                "choice",
                1,
                f"{segment.ref or segment.kind}, character {choice['at']}: <{w_tag}>{w_text}</{w_tag}> kept, "
                f"<{o_tag}>{o_text}</{o_tag}> not written back -- a <choice>'s two sides are two readings, "
                "which need word-level segments to carry",
            )
        if segment.foreign.get("tei-inline"):
            report.note(
                "inline markup",
                len(segment.foreign["tei-inline"]),
                "the model has no field for TEI's inline elements (hi, rs, add, del, subst, c, anchor ...); "
                "the text of added, deleted and highlighted spans is kept (deleted letters stay in the "
                "reading, #5179), and the markup itself is not written back",
            )

    def text_into(parent: Any, segment: PageSegment) -> None:
        """A segment's readings as text inside `parent` (which has no text of its own yet)."""
        readings = segment.readings
        if not readings:
            return
        kind, first = readings[0]
        target = parent
        if kind != "transcription":
            target = etree.SubElement(parent, q("seg"), type=kind)
        if len(readings) > 1:
            app = etree.SubElement(target, q("app"))
            etree.SubElement(app, q("lem")).text = first
            for alt_kind, alt in readings[1:]:
                etree.SubElement(app, q("rdg"), type=alt_kind).text = alt
            report.note(
                "which reading counts",
                1,
                "TEI's apparatus lists rival readings but has no way to say WHICH one a "
                "project counts, so the choice is not carried",
            )
        else:
            _append_text(target, first)

    def _append_text(element: Any, text: str) -> None:
        last = element[-1] if len(element) else None
        if last is None:
            element.text = (element.text or "") + text
        else:
            last.tail = (last.tail or "") + text

    page_zones: dict[str, Any] = {}

    def page_zone_for(line: PageSegment) -> str:
        """The zone a `<pb>` names, written once and referred to by the page break, the way
        the file placed the line (#5141): a bare `<lb/>` under `<pb facs="#zone">`."""
        zid = str(line.foreign[PAGE_ZONE])
        if zid not in page_zones:
            zone = etree.SubElement(surface, q("zone"), {_XML_ID: zid})
            if line.polygon:
                zone.set("points", _points_out(line.polygon, width, height))
            elif line.rect:
                x, y, w, h = line.rect
                zone.set("ulx", str(int(round(x * width))))
                zone.set("uly", str(int(round(y * height))))
                zone.set("lrx", str(int(round((x + w) * width))))
                zone.set("lry", str(int(round((y + h) * height))))
            pb = etree.Element(q("pb"), facs=f"#{zid}")
            body.insert(len(page_zones), pb)
            page_zones[zid] = zone
        return zid

    def write_line(container: Any, line: PageSegment) -> None:
        lb = etree.SubElement(container, q("lb"))
        if line.foreign.get(PAGE_ZONE) and (line.rect or line.polygon):
            page_zone_for(line)
        else:
            zid = zone_for(line)
            if zid:
                lb.set("facs", f"#{zid}")
        words = [s for s in children.get(line.ref, []) if s.kind == "word"]
        others = [s for s in children.get(line.ref, []) if s.kind not in ("word",)]
        for other in others:
            report.note(f"{other.kind} segments", 1, "TEI has no place for this granularity beneath a line")
        needs_wrapper = bool(line.language or line.script or line.direction)
        holder = container
        if needs_wrapper:
            holder = etree.SubElement(container, q("seg"))
            describe(holder, line)
        else:
            describe(etree.Element("x"), line)  # reports inline-markup losses only
        if words and _words_in_text(holder, line, words, zone_for, describe, q, report):
            pass
        elif words:
            joined = " ".join(w.readings[0][1] for w in words if w.readings)
            if line.readings and line.readings[0][1] != joined:
                report.note(
                    "line reading beside its words",
                    1,
                    "a TEI line holds its words OR its own text, not both, so the line's text "
                    "that differs from its words' is not written",
                )
            for index, word in enumerate(words):
                w = etree.SubElement(holder, q("w"))
                wzid = zone_for(word)
                if wzid:
                    w.set("facs", f"#{wzid}")
                describe(w, word)
                if word.readings:
                    w.text = word.readings[0][1]
                if len(word.readings) > 1:
                    report.note("word alternatives", len(word.readings) - 1,
                                "TEI writes one reading per <w> here; rival word readings are not written")
                if index < len(words) - 1:
                    w.tail = " "
        else:
            text_into(holder, line)

    def write_region(region: PageSegment | None, members: list[PageSegment]) -> None:
        ab = etree.SubElement(div, q("ab"))
        if region is None:
            ab.set("type", "anonymous")
        else:
            zid = zone_for(region)
            if zid:
                ab.set("facs", f"#{zid}")
            describe(ab, region)
        lines = [s for s in members if s.kind == "line"]
        for other in members:
            if other.kind not in ("line", "word"):
                report.note(f"{other.kind} segments", 1, "TEI has no place for this granularity beneath a region")
        if region is not None and region.readings and lines:
            report.note(
                "region text beside its lines",
                1,
                "a TEI block holds its lines OR its own text, so text on a region that also "
                "has lines is not written",
            )
        for line in lines:
            write_line(ab, line)
        if region is not None and region.readings and not lines:
            text_into(ab, region)

    regions = [s for s in children.get(None, []) if s.kind == "region"]
    order = page.orders[0].refs if page.orders else []
    ranked = {ref: i for i, ref in enumerate(order)}
    regions.sort(key=lambda r: ranked.get(r.ref, len(ranked)))
    if len(page.orders) > 1:
        report.note(
            "named reading orders",
            len(page.orders) - 1,
            "a TEI text is written in ONE order; orders beyond the first are not written",
        )
    for region in regions:
        write_region(region, children.get(region.ref, []))
    loose = [s for s in children.get(None, []) if s.kind == "line"]
    if loose:
        anon = etree.SubElement(div, q("ab"), type="anonymous")
        for line in loose:
            write_line(anon, line)
    for segment in children.get(None, []):
        if segment.kind not in ("region", "line"):
            report.note(f"{segment.kind} segments", 1, "TEI's text has no element for this granularity")
    if not len(div):
        etree.SubElement(div, q("ab"), type="anonymous")

    _declare_signs(root, header, page, q)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=False)


def _declare_signs(root: Any, header: Any, page: SourcePage, q: Any) -> None:
    """Declared signs out as TEI says them (`source.sign.export-honest`, #4939): each use of a
    sign's private-use character in the TEXT is wrapped `<g ref="#sign-…">`, and the header's
    `<encodingDesc><charDecl>` gives each a `<glyph>` with its name, its mapping, and its
    sign-list references. The character itself stays, so a reader without the declaration still
    has the text."""
    from lxml import etree

    from fichero_server.models.signs import code_point_char

    by_char = {
        code_point_char(sign["code_point"]): sign for sign in page.signs if sign.get("code_point")
    }
    if not by_char:
        return
    text_el = root.find(q("text"))
    used: set[str] = set()

    def split(text: str | None) -> list[Any]:
        """`text` as a list of str pieces and ("g", char) markers."""
        pieces: list[Any] = []
        buffer = ""
        for ch in text or "":
            if ch in by_char:
                if buffer:
                    pieces.append(buffer)
                    buffer = ""
                pieces.append(("g", ch))
                used.add(ch)
            else:
                buffer += ch
        if buffer:
            pieces.append(buffer)
        return pieces

    def g_for(ch: str) -> Any:
        g = etree.Element(q("g"), ref=f"#sign-{by_char[ch]['id']}")
        g.text = ch
        return g

    for element in list(text_el.iter()) if text_el is not None else []:
        if not isinstance(element.tag, str) or element.tag == q("g"):
            continue
        # The element's own text: the first plain piece stays as text, then each <g> and the
        # plain piece after it as that <g>'s tail, inserted before the element's first child.
        pieces = split(element.text)
        if any(isinstance(p, tuple) for p in pieces):
            element.text = pieces[0] if pieces and isinstance(pieces[0], str) else None
            rest = pieces[1:] if pieces and isinstance(pieces[0], str) else pieces
            position = 0
            last = None
            for piece in rest:
                if isinstance(piece, tuple):
                    last = g_for(piece[1])
                    element.insert(position, last)
                    position += 1
                elif last is not None:
                    last.tail = (last.tail or "") + piece
        for child in list(element):
            if child.tag == q("g") or not child.tail:
                continue
            pieces = split(child.tail)
            if not any(isinstance(p, tuple) for p in pieces):
                continue
            child.tail = pieces[0] if isinstance(pieces[0], str) else None
            anchor = child
            for piece in (pieces[1:] if isinstance(pieces[0], str) else pieces):
                if isinstance(piece, tuple):
                    g = g_for(piece[1])
                    anchor.addnext(g)
                    anchor = g
                else:
                    anchor.tail = (anchor.tail or "") + piece

    if not used:
        return
    encoding = header.find(q("encodingDesc"))
    if encoding is None:
        encoding = etree.Element(q("encodingDesc"))
        header.find(q("fileDesc")).addnext(encoding)
    char_decl = etree.SubElement(encoding, q("charDecl"))
    for ch in sorted(used):
        sign = by_char[ch]
        glyph = etree.SubElement(char_decl, q("glyph"), {_XML_ID: f"sign-{sign['id']}"})
        # `<localProp name="name">`, not `<glyphName>`: TEI P5 4.x removed glyphName, and the
        # vendored schema refused it -- the export validation caught it.
        etree.SubElement(glyph, q("localProp"), name="name", value=sign.get("name") or sign["code_point"])
        for reference in sign.get("list_references") or []:
            etree.SubElement(glyph, q("note"), type="sign-list", subtype=str(reference.get("authority", ""))).text = str(
                reference.get("number", "")
            )
        etree.SubElement(glyph, q("mapping"), type="PUA").text = ch


def _signs_declared_in(header: Any) -> list[dict[str, Any]]:
    """TEI's `<charDecl>` glyphs back as declared signs, so a round trip keeps them."""
    if header is None:
        return []
    signs = []
    for glyph in header.iter(f"{{{TEI_NS}}}glyph"):
        mapping = next((m for m in glyph.iter(f"{{{TEI_NS}}}mapping") if (m.text or "").strip()), None)
        ch = (mapping.text or "").strip() if mapping is not None else ""
        glyph_id = glyph.get(_XML_ID) or ""
        name_prop = next(
            (lp.get("value") for lp in glyph.iter(f"{{{TEI_NS}}}localProp") if lp.get("name") == "name"), None
        )
        old_name = glyph.find(f"{{{TEI_NS}}}glyphName")  # older TEI: still read
        name = name_prop or ((old_name.text or "").strip() if old_name is not None else "") or glyph_id
        signs.append({
            "id": glyph_id[len("sign-"):] if glyph_id.startswith("sign-") else glyph_id,
            "name": name,
            "code_point": f"U+{ord(ch):04X}" if len(ch) == 1 else None,
            "list_references": [
                {"authority": note.get("subtype") or "", "number": (note.text or "").strip()}
                for note in glyph.iter(f"{{{TEI_NS}}}note") if note.get("type") == "sign-list"
            ],
        })
    return signs


def _words_in_text(holder: Any, line: PageSegment, words: list[PageSegment], zone_for: Any,
                   describe: Any, q: Any, report: LossReport) -> bool:
    """Write the line's OWN text with each word wrapped where it stands, so the line's text is
    exact and the words are still segments.

    A word whose text is not found in the line's text, in order, is NOT dropped and NOT merged
    into the line's text: it is written where it falls as `<note type="unplaced-word" facs>`, which
    the reader turns back into a word of the line that is not part of its text. PAGE XML allows a
    `Word` to carry text its `TextLine` does not (found on OCR-D's Aepinus ground truth: `J.E.W.`,
    #5083); declaring that a loss would have made the test pass and the word disappear.

    Found first by writing PAGE XML's punctuation-as-its-own-word back: joining the words with
    spaces turned "Monatsſchrift." into "Monatsſchrift .".
    """
    from lxml import etree

    if len(line.readings) != 1 or line.readings[0][0] != "transcription":
        return False
    if any(len(w.readings) != 1 for w in words):
        return False
    text = line.readings[0][1]
    position = 0
    cursor = 0
    last: Any = None

    def add_text(chunk: str) -> None:
        if not chunk:
            return
        if last is None:
            holder.text = (holder.text or "") + chunk
        else:
            last.tail = (last.tail or "") + chunk

    for word in words:
        token = word.readings[0][1]
        found = text.find(token, cursor) if token else -1
        if found < 0:
            element = etree.SubElement(holder, q("note"), type=UNPLACED_WORD)
            element.text = token
        else:
            add_text(text[position:found])
            element = etree.SubElement(holder, q("w"))
            element.text = token
            position = cursor = found + len(token)
        zid = zone_for(word)
        if zid:
            element.set("facs", f"#{zid}")
        describe(element, word)
        last = element
    add_text(text[position:])
    return True


def _header(page: SourcePage, report: LossReport, root: Any) -> Any:
    """The `<teiHeader>`: the page's own, kept from a read, when it still validates as TEI on
    its own; otherwise a generated one, with the kept one reported as not written."""
    from lxml import etree

    def q(name: str) -> str:
        return f"{{{TEI_NS}}}{name}"

    kept = (page.foreign.get("tei") or {}).get("teiHeader")
    if kept:
        candidate = etree.fromstring(kept.encode("utf-8"))
        if _header_validates(candidate):
            root.append(candidate)
            return candidate
        report.note(
            "teiHeader",
            1,
            "the header this page was read with does not validate as TEI on its own (a project "
            "namespace or custom encoding), so it is kept on the page and NOT written; a "
            "generated header was written instead",
        )
    header = etree.SubElement(root, q("teiHeader"))
    file_desc = etree.SubElement(header, q("fileDesc"))
    title_stmt = etree.SubElement(file_desc, q("titleStmt"))
    etree.SubElement(title_stmt, q("title")).text = page.image_name or "Untitled page"
    pub = etree.SubElement(file_desc, q("publicationStmt"))
    etree.SubElement(pub, q("p")).text = "Exported from Fichero"
    source = etree.SubElement(file_desc, q("sourceDesc"))
    etree.SubElement(source, q("p")).text = page.producer or "Born digital in Fichero"
    return header


def _header_validates(header: Any) -> bool:
    from lxml import etree

    from fichero_server.formats.validation import validate_xml
    from fichero_server.formats.harness import SCHEMA_DIR

    wrapper = etree.Element(f"{{{TEI_NS}}}TEI", nsmap={None: TEI_NS})
    wrapper.append(etree.fromstring(etree.tostring(header)))
    facs = etree.SubElement(wrapper, f"{{{TEI_NS}}}text")
    body = etree.SubElement(facs, f"{{{TEI_NS}}}body")
    etree.SubElement(etree.SubElement(body, f"{{{TEI_NS}}}div"), f"{{{TEI_NS}}}ab").text = "x"
    return not validate_xml(etree.tostring(wrapper), SCHEMA_DIR / "tei_all.xsd")


register(
    FormatSpec(
        name="tei",
        extensions=(".xml", ".tei"),
        export_extension=".tei.xml",
        read=read,
        write=write,
        schema="tei_all.xsd",
        round_trips=True,
        sniff=_sniff,
        carries_declared_signs=True,
    )
)
