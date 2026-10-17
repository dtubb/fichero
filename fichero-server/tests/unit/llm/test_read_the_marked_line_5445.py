"""`source.lines.read-the-marked-line` (#5445): a vision model reading Kraken's lines is shown the
target line alone, never a crop in which a neighbouring line is more complete than the target."""
from __future__ import annotations

from PIL import Image, ImageDraw

from fichero_server.llm import line_reader
from fichero_server.remote_read import runner

PAPER = (230, 220, 190)
ABOVE = (200, 0, 0)
TARGET = (0, 0, 200)
BELOW = (0, 150, 0)


def _page():
    page = Image.new("RGB", (1000, 400), PAPER)
    draw = ImageDraw.Draw(page)
    draw.rectangle((100, 125, 900, 144), fill=ABOVE)  # each line's writing is a bar on its 50 px band
    draw.rectangle((100, 165, 900, 184), fill=TARGET)
    draw.rectangle((100, 205, 900, 224), fill=BELOW)
    return page, [[100, 150], [900, 150], [900, 199], [100, 199]]


def _count(image, colour):
    return sum(n for n, c in image.getcolors(maxcolors=1_000_000) if c == colour)


def test_the_neighbours_are_masked_out_of_the_crop():
    """WHY: with the line above showing in the padding, a model read the line above (295 of 2,625
    teacher lines on one set); the crop must hold the target's writing and no other line's."""
    page, polygon = _page()
    crop = line_reader.crop_line(page, polygon)
    assert _count(crop, TARGET) == 801 * 20  # the whole target line
    for neighbour in (ABOVE, BELOW):  # at most the sliver of margin kept for ascenders, never a second line
        assert _count(crop, neighbour) < 0.2 * _count(crop, TARGET)
    assert crop.getpixel((crop.width // 2, crop.height // 2)) == TARGET


def test_the_runner_masks_as_the_line_reader_does():
    """WHY: the runner cannot import Fichero; a student must be shown the same cut where it reads at scale."""
    page, polygon = _page()
    assert runner.crop_line(page, polygon).tobytes() == line_reader.crop_line(page, polygon).tobytes()
