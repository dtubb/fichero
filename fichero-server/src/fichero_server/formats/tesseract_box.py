"""Tesseract box files: one character per line, with its box (#5174, ruled 2026-09-28).

`<glyph> <left> <bottom> <right> <top> <page>`, in PIXELS, with the origin at the BOTTOM-left (the
Tesseract training format). Each line becomes a `character` segment carrying its letter -- "a
Tesseract .box file becomes character segments carrying their letters". There are no lines or
regions in the file, so none are invented.

The file states no image size, and a bottom-left origin cannot be turned into the page's top-left
fractions without the page's height -- so, like QGIS `.points`, the boxes are placed on the size the
PAGE has recorded (`read_box(data, (width, height))`, called by `format.import`); the bytes-only
`read` exists for the registry and places nothing.

Read only: the format is a training artefact, and a writer is not asked for.
"""

from __future__ import annotations

import re

from fichero_server.formats import FormatSpec, SourcePage, register
from fichero_server.formats.harness import PageSegment

_LINE = re.compile(r"^(\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+) (\d+)$")


def _lines(data: bytes) -> list[str]:
    return [line for line in data.decode("utf-8").splitlines() if line.strip()]


def _sniff(data: bytes) -> bool:
    try:
        lines = _lines(data)
    except UnicodeDecodeError:
        return False
    return bool(lines) and all(_LINE.match(line) for line in lines)


def read_box(data: bytes, image_size: tuple[int, int] | None) -> SourcePage:
    """The file's characters as segments on a page of `image_size` pixels."""
    rows = []
    for number, line in enumerate(_lines(data), start=1):
        match = _LINE.match(line)
        if match is None:
            raise ValueError(f"line {number} is not '<glyph> <left> <bottom> <right> <top> <page>': {line!r}")
        glyph, left, bottom, right, top, page = match.groups()
        rows.append((glyph, int(left), int(bottom), int(right), int(top), int(page)))
    pages = sorted({row[5] for row in rows})
    if len(pages) > 1:
        raise ValueError(f"the file holds the boxes of {len(pages)} pages ({pages}); a page takes one page's boxes")
    page = SourcePage(producer="Tesseract box file", image_size=image_size)
    if image_size is None:
        return page
    width, height = image_size
    for index, (glyph, left, bottom, right, top, _page) in enumerate(rows):
        page.segments.append(PageSegment(
            kind="character",
            # Bottom-left origin -> the page's top-left fractions: the box's TOP edge is `top`
            # pixels up from the bottom, so height - top down from the top.
            rect=[left / width, (height - top) / height, (right - left) / width, (top - bottom) / height],
            readings=[("transcription", glyph)],
            ref=f"c{index + 1}",
        ))
    return page


def read(data: bytes) -> SourcePage:
    return read_box(data, None)


register(
    FormatSpec(
        name="tesseract-box",
        extensions=(".box",),
        read=read,
        write=None,
        schema=None,
        round_trips=False,
        sniff=_sniff,
    )
)
