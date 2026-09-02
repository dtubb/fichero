"""A transparent image flattens to WHITE, never to black.

Daniel, 2026-09-02: background-removed images rendered on a BLACK ground in
thumbnails and display renditions. Root cause in
``db/storage.py::_generate_image``::

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

JPEG has no alpha, so something has to decide what shows through — and
``convert("RGB")`` decides by simply DROPPING the alpha channel and keeping
whatever colour sits underneath. For a cut-out those pixels are (0, 0, 0), so
every removed background came back black. That reads as a ruined image rather
than a transparent one.

Standing ruling: transparent flattens to plain WHITE.

Both rendition paths (thumbnail and display) go through ``_generate_image``,
so fixing it there fixes both — these tests call it directly rather than
through the two wrappers, and a separate test pins that both wrappers still
route through it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.db import storage

Image = pytest.importorskip("PIL.Image")


def _rgba_fixture(path: Path) -> Path:
    """A 40x40 PNG: opaque red square in the middle, transparent corners.

    The transparent pixels carry BLACK underneath them — exactly what a
    background-removal tool leaves behind, and exactly what the old
    convert("RGB") surfaced.
    """
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (255, 0, 0, 255))
    img.save(path, "PNG")
    return path


def test_a_transparent_corner_comes_out_white_not_black(tmp_path):
    source = _rgba_fixture(tmp_path / "cutout.png")
    dest = tmp_path / "thumb.jpg"

    assert storage._generate_image(source, dest, (40, 40)) == dest

    with Image.open(dest) as out:
        assert out.mode == "RGB"
        r, g, b = out.getpixel((0, 0))
    # JPEG is lossy; a flat white corner still lands well above any black.
    assert (r, g, b) != (0, 0, 0), "transparent corner flattened to BLACK"
    assert min(r, g, b) > 230, f"transparent corner is not white: {(r, g, b)}"


def test_the_opaque_content_survives_the_flatten(tmp_path):
    """Compositing must not wash out what was actually there."""
    source = _rgba_fixture(tmp_path / "cutout.png")
    dest = tmp_path / "thumb.jpg"
    storage._generate_image(source, dest, (40, 40))

    with Image.open(dest) as out:
        r, g, b = out.getpixel((20, 20))
    assert r > 200 and g < 60 and b < 60, f"the red square did not survive: {(r, g, b)}"


def test_a_half_transparent_edge_blends_toward_white_not_black(tmp_path):
    """Anti-aliased edges are the reason to COMPOSITE rather than drop the
    channel: a 50%-alpha black pixel is grey over white, and stays pure black
    if the alpha is merely discarded."""
    source = tmp_path / "edge.png"
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 128))
    img.save(source, "PNG")
    dest = tmp_path / "edge.jpg"
    storage._generate_image(source, dest, (8, 8))

    with Image.open(dest) as out:
        r, g, b = out.getpixel((4, 4))
    assert r > 100, f"half-transparent black did not blend toward white: {(r, g, b)}"


def test_palette_transparency_is_flattened_too(tmp_path):
    """A P-mode PNG carries transparency in a tRNS chunk, not in its mode
    name — a mode check alone would miss it."""
    source = tmp_path / "palette.png"
    img = Image.new("P", (16, 16), 0)
    img.putpalette([0, 0, 0] + [255, 0, 0] * 255)
    img.info["transparency"] = 0
    img.save(source, "PNG", transparency=0)
    dest = tmp_path / "palette.jpg"
    storage._generate_image(source, dest, (16, 16))

    with Image.open(dest) as out:
        r, g, b = out.getpixel((0, 0))
    assert min(r, g, b) > 230, f"palette transparency flattened to {(r, g, b)}"


def test_an_opaque_rgb_image_is_untouched(tmp_path):
    """The flatten must be a no-op for images that have no transparency."""
    source = tmp_path / "opaque.png"
    Image.new("RGB", (16, 16), (12, 34, 56)).save(source, "PNG")
    dest = tmp_path / "opaque.jpg"
    storage._generate_image(source, dest, (16, 16))

    with Image.open(dest) as out:
        r, g, b = out.getpixel((8, 8))
    assert abs(r - 12) < 12 and abs(g - 34) < 12 and abs(b - 56) < 12


def test_both_rendition_paths_still_route_through_generate_image():
    """The fix lives in one place on purpose. If a rendition path ever grows
    its own PIL save, it grows its own black-background bug with it."""
    import inspect

    source = inspect.getsource(storage)
    assert source.count("_generate_image(") >= 3, (
        "thumbnail and display renditions no longer both call _generate_image"
    )
    # No caller may re-introduce the alpha-dropping line.
    body = inspect.getsource(storage._generate_image)
    assert 'img.convert("RGB")' not in body, (
        "_generate_image drops the alpha channel again instead of compositing"
    )
