"""A rendered PDF page goes to the provider as JPEG, on a WHITE ground.

The same scanned page used to leave Fichero in two different formats depending
on where it came from. From a loose file, `file_to_data_uri` preserved the
source: a JPEG stayed JPEG at quality 95. From a PDF, `_cgimage_to_data_uri`
(then named `..._to_png_data_uri`) saved PNG unconditionally — at identical
pixel dimensions, because both paths bound to `max_dimension`.

PNG is built for flat graphics. A scan of a handwritten page is photographic —
paper grain, ink gradients, shadow — which is exactly what PNG handles worst.
The result was roughly a 5-10x upload for every page of every PDF, with base64
adding a third on top, and nothing in the logs saying so.

The second assertion here is the one that would bite silently. The Quartz
buffer is RGBA and JPEG carries no alpha, so a bare `convert("RGB")` puts the
page on a BLACK ground — the model would receive a black rectangle with the
faint ghost of a page on it and dutifully transcribe nothing. `file_to_data_uri`
already knew this and routes through `flatten_for_opaque_format`; so does this
path now. A test that only checked the MIME label would pass on a black page.

No engine, no model, no real PDF: Quartz is faked at the module boundary so the
real PIL encode path runs.
"""

from __future__ import annotations

import base64
import io
import random
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from fichero_server.workflows.tools import vision_base

WIDTH, HEIGHT = 240, 320


def _page_like_rgba() -> bytes:
    """A SCANNED page: white ground, shading, ink — and paper grain.

    The grain is the point, and leaving it out is how the first version of this
    test failed. A smooth synthetic gradient is nearly flat, and PNG stores
    flat regions superbly — it beat JPEG outright. Real archival scans are
    photographs of paper: per-pixel sensor and fibre noise, which is precisely
    what PNG cannot compress and JPEG discards cheaply.

    So the payload win is a property of PHOTOGRAPHIC content, not of the codecs
    in the abstract. Fichero's corpus is scans, which is why it applies here.
    A born-digital PDF page would be flatter — but a born-digital page has a
    text layer and never reaches this encoder at all.
    """
    rng = random.Random(20260904)  # deterministic: a size assertion must not flake
    img = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 255))
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            shade = 255 - (x * 12) // WIDTH - (y * 18) // HEIGHT
            if 40 < y % 80 < 48 and 20 < x < WIDTH - 20:
                shade = 40  # a line of ink
            shade = max(0, min(255, shade + rng.randint(-14, 14)))  # paper grain
            pixels[x, y] = (shade, shade, shade, 255)
    return img.tobytes()


@pytest.fixture
def fake_quartz(monkeypatch):
    """Enough Quartz for the encoder's happy path."""
    raw = _page_like_rgba()

    quartz = SimpleNamespace(
        CGImageGetWidth=lambda _img: WIDTH,
        CGImageGetHeight=lambda _img: HEIGHT,
        CGImageGetDataProvider=lambda _img: object(),
        CGDataProviderCopyData=lambda _provider: raw,
    )
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    return object()  # stands in for the CGImage


def _decode(uri: str) -> Image.Image:
    _header, _, payload = uri.partition(",")
    return Image.open(io.BytesIO(base64.b64decode(payload)))


def test_a_rendered_page_is_sent_as_jpeg(fake_quartz) -> None:
    uri = vision_base._cgimage_to_data_uri(fake_quartz, max_dimension=0)

    assert uri.startswith("data:image/jpeg;base64,"), (
        "a rendered PDF page must go out as JPEG, like the same page would if "
        "it arrived as a loose image file"
    )
    assert _decode(uri).format == "JPEG", "the MIME label must match the bytes"


def test_the_page_keeps_its_white_ground(fake_quartz) -> None:
    """The alpha drop must composite, not discard.

    JPEG carries no alpha. Discarding the channel instead of flattening turns
    the page black, and a MIME-label test would never notice.
    """
    decoded = _decode(vision_base._cgimage_to_data_uri(fake_quartz, max_dimension=0)).convert("RGB")

    corner = decoded.getpixel((2, 2))
    assert min(corner) > 180, (
        f"top-left pixel is {corner} — the page was flattened onto a dark "
        "ground, so the model receives a black rectangle"
    )


def test_jpeg_is_dramatically_smaller_than_the_png_it_replaced(fake_quartz) -> None:
    """The property the fix exists for, measured rather than asserted."""
    jpeg_uri = vision_base._cgimage_to_data_uri(fake_quartz, max_dimension=0)
    jpeg_bytes = len(base64.b64decode(jpeg_uri.partition(",")[2]))

    as_png = io.BytesIO()
    Image.frombytes("RGBA", (WIDTH, HEIGHT), _page_like_rgba()).save(as_png, format="PNG")
    png_bytes = as_png.tell()

    assert jpeg_bytes < png_bytes, (
        f"JPEG {jpeg_bytes}B is not smaller than PNG {png_bytes}B — the whole "
        "point of the change is the payload"
    )


def test_the_dimension_bound_still_applies(fake_quartz) -> None:
    """Changing the codec must not change the resize contract."""
    decoded = _decode(vision_base._cgimage_to_data_uri(fake_quartz, max_dimension=64))
    assert max(decoded.size) <= 64
