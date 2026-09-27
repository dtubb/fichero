#!/usr/bin/env python3
"""The speed trial's page: GENERATED, from distributions MEASURED on named real pages (#4940).

    PYTHONPATH=fichero-server/src .venv/bin/python scripts/perf_fixture.py measure
    PYTHONPATH=fichero-server/src .venv/bin/python scripts/perf_fixture.py write <shapes> <out.page.xml>

`source.perf.declared-fixture`: one committed fixture whose shape count, nesting and size
distribution come from a named real page, and whose own file says it is generated.

WHY GENERATED. The trial's number is 20,000 shapes on one page. The densest real page in
the repository is Transkribus's table page at 576 shapes, and no real file here has
character-level shapes. A real 20,000-shape page is a newspaper at character level; we have
none we may vendor. So the page is generated -- and says so -- from what IS real:

* MEASURED on the named pages, and committed as the samples themselves
  (`perf_trial_fixture.json`): lines per region, words per line, characters per word (from
  each word's real TEXT), and each word's width relative to its line's height.
  `test_perf_fixture.py` re-measures the named files and requires the committed samples to
  match, so the declaration is checked rather than asserted.
* CHOSEN, and declared as chosen: characters split their word's width equally; regions are
  flowed into columns so the text block has the page's proportions; the whole page is scaled uniformly so the requested number of shapes
  fits on one page. Uniform scaling keeps every RELATIVE size real; the absolute size is
  that of small, dense print, which is the case a 20,000-shape page is.

Deterministic: the same count and seed give the same page, so two runs measure one page.
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fichero-server" / "tests" / "unit" / "formats" / "fixtures"
DISTRIBUTION = Path(__file__).with_name("perf_trial_fixture.json")
#: The real pages the distributions are measured on: both have word-level shapes with text.
SOURCES = ("ocrd_gt_aepinus_0020.page.xml", "altoxml_glyph_00001.alto.xml")
SEED = 20260927
#: A large scan, in pixels, so PAGE XML's integer coordinates keep sub-word precision.
IMAGE_SIZE = (12000, 16000)


def _box(segment) -> list[float] | None:
    if segment.rect:
        return segment.rect
    if segment.polygon:
        xs = [p[0] for p in segment.polygon]
        ys = [p[1] for p in segment.polygon]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    return None


def measure() -> dict:
    """The samples, re-measured from the named real files."""
    from fichero_server.formats import format_for, read_page

    samples: dict[str, list] = defaultdict(list)
    for name in SOURCES:
        data = (FIXTURES / name).read_bytes()
        page = read_page(format_for(name, data).name, data)
        by_ref = {s.ref: s for s in page.segments}
        children = defaultdict(list)
        for segment in page.segments:
            if segment.parent_ref:
                children[segment.parent_ref].append(segment)
        for segment in page.segments:
            if segment.kind == "region":
                lines = sum(1 for c in children[segment.ref] if c.kind == "line")
                if lines:
                    samples["lines_per_region"].append(lines)
            elif segment.kind == "line":
                words = sum(1 for c in children[segment.ref] if c.kind == "word")
                if words:
                    samples["words_per_line"].append(words)
            elif segment.kind == "word":
                if segment.readings and segment.readings[0][1]:
                    samples["chars_per_word"].append(len(segment.readings[0][1]))
                line = by_ref.get(segment.parent_ref or "")
                own, parent = _box(segment), _box(line) if line else None
                # A ZERO-WIDTH box is real (one of the source pages has one) and has no
                # place to be drawn: generated at x=0 it lay outside the page and the
                # importer refused the whole fixture. Excluded, and the declaration says so.
                if own and parent and parent[3] > 0 and own[2] > 0:
                    samples["word_width_over_line_height"].append(round(own[2] / parent[3], 3))
    return {
        "generated": True,
        "declaration": (
            "GENERATED page for the segment editor's speed trial. Nesting, characters per "
            "word and word width relative to line height are SAMPLED from the real pages in "
            "`sources` (zero-width word boxes excluded: they have no place to be drawn); "
            "characters splitting their word equally, columns, and one uniform scale "
            "to fit the shape count are CHOSEN. Not a real page."
        ),
        "sources": list(SOURCES),
        "seed": SEED,
        "samples": {key: samples[key] for key in sorted(samples)},
    }


def generate(shape_count: int, distribution: dict | None = None, seed: int | None = None):
    """A SourcePage of at least `shape_count` shapes: regions > lines > words > characters."""
    from fichero_server.formats import PageSegment, SourcePage

    dist = distribution or json.loads(DISTRIBUTION.read_text(encoding="utf-8"))
    rng = random.Random(dist["seed"] if seed is None else seed)
    s = dist["samples"]

    # Build each REGION as a block in line-height units, relative to its own top-left.
    column_width = 60.0  # line heights; about a column of print
    blocks: list[tuple[float, list[tuple[str, str, str | None, list[float]]]]] = []
    count = 0
    region_index = 0
    while count < shape_count:
        region_ref = f"r{region_index}"
        rows: list[tuple[str, str, str | None, list[float]]] = []
        y = 0.0
        for line_index in range(rng.choice(s["lines_per_region"])):
            line_ref = f"{region_ref}l{line_index}"
            x = 0.0
            words = []
            for word_index in range(rng.choice(s["words_per_line"])):
                width = rng.choice(s["word_width_over_line_height"])
                if x + width > column_width:
                    break
                words.append((f"{line_ref}w{word_index}", x, width))
                x += width + 0.3
            rows.append(("line", line_ref, region_ref, [0.0, y, max(x, 1.0), 1.0]))
            for word_ref, wx, width in words:
                rows.append(("word", word_ref, line_ref, [wx, y, width, 1.0]))
                chars = rng.choice(s["chars_per_word"])
                for c in range(chars):
                    rows.append(("character", f"{word_ref}c{c}", word_ref, [wx + c * width / chars, y, width / chars, 1.0]))
            y += 1.4
        height = max(y, 1.0)
        blocks.append((height, [("region", region_ref, None, [0.0, 0.0, column_width, height]), *rows]))
        count += 1 + len(rows)
        region_index += 1

    # Flow the blocks into columns so the text block has the PAGE's proportions: a column
    # height H with (columns x column pitch) / H = page width / page height.
    pitch = column_width + 3.0
    total = sum(h + 1.0 for h, _ in blocks)
    target = (total * pitch * IMAGE_SIZE[1] / IMAGE_SIZE[0]) ** 0.5
    raw: list[tuple[str, str, str | None, list[float]]] = []
    x0 = y0 = 0.0
    tallest = 0.0
    for height, rows in blocks:
        if y0 > 0 and y0 + height > target:
            x0 += pitch
            y0 = 0.0
        for kind, ref, parent, (bx, by, bw, bh) in rows:
            raw.append((kind, ref, parent, [x0 + bx, y0 + by, bw, bh]))
        y0 += height + 1.0
        tallest = max(tallest, y0)

    width = x0 + column_width
    height = max(tallest, 1.0)
    scale = 1.0 / max(width / IMAGE_SIZE[0], height / IMAGE_SIZE[1])  # units -> pixels

    page = SourcePage(image_size=IMAGE_SIZE, producer="perf_fixture.py (generated)")
    page.foreign["perf:declaration"] = dist["declaration"]
    for kind, ref, parent, (bx, by, bw, bh) in raw:
        page.segments.append(
            PageSegment(
                kind=kind,
                ref=ref,
                parent_ref=parent,
                rect=[bx * scale / IMAGE_SIZE[0], by * scale / IMAGE_SIZE[1],
                      bw * scale / IMAGE_SIZE[0], bh * scale / IMAGE_SIZE[1]],
            )
        )
    return page


def main(argv: list[str]) -> int:
    if argv[:1] == ["measure"]:
        DISTRIBUTION.write_text(json.dumps(measure(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DISTRIBUTION}")
        return 0
    if len(argv) == 3 and argv[0] == "write":
        from fichero_server.formats import write_page

        page = generate(int(argv[1]))
        data, _ = write_page("pagexml", page)  # validated on the way out
        Path(argv[2]).write_bytes(data)
        print(f"{len(page.segments)} shapes -> {argv[2]}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
