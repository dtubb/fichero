"""What the SOURCE file says, read independently of the engine's own readers.

The engine's format readers are what is under test, so the expected side is parsed here
with plain lxml from the PAGE / ALTO elements themselves: every region, line, word and
glyph in document order, with its id, parent, exact text (the raw bytes of the Unicode /
CONTENT, not normalised), language, script, direction, polygon point count and baseline
presence, plus the file's stated reading order. Nothing here imports fichero_server.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from lxml import etree

PAGE_REGIONS = {
    "TextRegion", "TableRegion", "ImageRegion", "GraphicRegion", "SeparatorRegion", "MathsRegion",
    "ChemRegion", "MusicRegion", "AdvertRegion", "ChartRegion", "LineDrawingRegion", "NoiseRegion",
    "UnknownRegion", "CustomRegion", "MapRegion", "TableCell",
}
ALTO_BLOCKS = {"TextBlock", "Illustration", "GraphicalElement", "ComposedBlock"}


@dataclass
class El:
    level: str  # region | line | word | glyph
    tag: str
    id: str | None
    parent: str | None
    text: str | None
    language: str | None = None
    script: str | None = None
    direction: str | None = None
    polygon_points: int = 0
    has_baseline: bool = False
    custom: str | None = None


@dataclass
class Truth:
    format: str
    elements: list[El] = field(default_factory=list)
    reading_order: list[str] = field(default_factory=list)
    units: str | None = None

    def level(self, name: str) -> list[El]:
        return [e for e in self.elements if e.level == name]

    def as_dict(self) -> dict:
        return {"format": self.format, "units": self.units, "reading_order": self.reading_order,
                "elements": [asdict(e) for e in self.elements]}


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _page_text(el) -> str | None:
    # The element's OWN TextEquiv (direct child), first by @index if given.
    equivs = [c for c in el if _local(c) == "TextEquiv"]
    if not equivs:
        return None
    equivs.sort(key=lambda c: int(c.get("index", "0") or 0))
    for c in equivs[0]:
        if _local(c) == "Unicode":
            return c.text or ""
    return None


def _points(el) -> int:
    for c in el:
        if _local(c) == "Coords":
            pts = c.get("points")
            if pts:
                return len(pts.split())
            return sum(1 for p in c if _local(p) == "Point")
    return 0


def _page(root) -> Truth:
    t = Truth("pagexml")

    def walk(el, parent_id):
        name = _local(el)
        level = None
        if name in PAGE_REGIONS:
            level = "region"
        elif name == "TextLine":
            level = "line"
        elif name == "Word":
            level = "word"
        elif name == "Glyph":
            level = "glyph"
        my_id = parent_id
        if level:
            my_id = el.get("id")
            t.elements.append(El(
                level=level, tag=name, id=my_id, parent=parent_id, text=_page_text(el),
                language=el.get("primaryLanguage") or el.get("language"),
                script=el.get("primaryScript") or el.get("script"),
                direction=el.get("readingDirection"),
                polygon_points=_points(el),
                has_baseline=any(_local(c) == "Baseline" for c in el),
                custom=el.get("custom"),
            ))
        for c in el:
            walk(c, my_id)

    for page in root.iter("{*}Page"):
        walk(page, None)
        for ro in page.iter("{*}ReadingOrder"):
            for ref in ro.iter("{*}RegionRefIndexed", "{*}RegionRef"):
                t.reading_order.append(ref.get("regionRef"))
    return t


def _alto(root) -> Truth:
    t = Truth("alto")
    for mu in root.iter("{*}MeasurementUnit"):
        t.units = (mu.text or "").strip()

    def shape_points(el) -> int:
        for s in el:
            if _local(s) == "Shape":
                for p in s:
                    if _local(p) == "Polygon":
                        return len((p.get("POINTS") or "").replace(",", " ").split()) // 2 or len((p.get("POINTS") or "").split())
        return 4 if el.get("HPOS") is not None else 0

    def walk(el, parent_id):
        name = _local(el)
        level = {"TextLine": "line", "String": "word", "Glyph": "glyph"}.get(name)
        if name in ALTO_BLOCKS:
            level = "region"
        my_id = parent_id
        if level:
            my_id = el.get("ID")
            t.elements.append(El(
                level=level, tag=name, id=my_id, parent=parent_id,
                text=el.get("CONTENT") if name in ("String", "Glyph") else None,
                language=el.get("LANG") or el.get("{http://www.w3.org/XML/1998/namespace}lang"),
                script=None,
                direction=None,
                polygon_points=shape_points(el),
                has_baseline=bool(el.get("BASELINE")),
            ))
        for c in el:
            walk(c, my_id)

    for layout in root.iter("{*}Layout"):
        walk(layout, None)
    for ro in root.iter("{*}ReadingOrder"):
        for ref in ro.iter("{*}ElementRef"):
            t.reading_order.append(ref.get("REF"))
    return t


def read_truth(path: Path) -> Truth | None:
    root = etree.parse(str(path)).getroot()
    name = _local(root)
    if name == "PcGts":
        return _page(root)
    if name == "alto":
        return _alto(root)
    return None


if __name__ == "__main__":
    import json
    import sys
    from collections import Counter

    for arg in sys.argv[1:]:
        tr = read_truth(Path(arg))
        if tr is None:
            print(arg, "not PAGE/ALTO")
            continue
        levels = Counter(e.level for e in tr.elements)
        print(Path(arg).name, tr.format, tr.units, dict(levels),
              "lang", dict(Counter(e.language for e in tr.elements)),
              "dir", dict(Counter(e.direction for e in tr.elements)),
              "script", dict(Counter(e.script for e in tr.elements)),
              "text", sum(1 for e in tr.elements if e.text), "bl", sum(1 for e in tr.elements if e.has_baseline),
              "ro", len(tr.reading_order))
