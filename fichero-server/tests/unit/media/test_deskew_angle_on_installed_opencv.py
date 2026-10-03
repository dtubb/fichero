"""Deskew estimates a real tilt under the OpenCV that is installed (#5385).

WHY: OpenCV 5 changed `HoughLinesP` to return lines shaped (N, 4) instead of (N, 1, 4); both
estimators unpacked `line[0]`, so Straighten returned a 500 on every page. The estimate now lives
in one place (`media.image_ops.detect_deskew_angle`) and accepts either shape. This draws ruled
lines tilted by a known angle and checks the estimate, through the route's own entry point too,
so a future OpenCV change fails here rather than on someone's archive.
"""
from __future__ import annotations

import math

import pytest
from PIL import Image, ImageDraw

cv2 = pytest.importorskip("cv2")


def _tilted_lines(degrees: float) -> Image.Image:
    im = Image.new("RGB", (1200, 900), "white")
    d = ImageDraw.Draw(im)
    slope = math.tan(math.radians(degrees))
    for y in range(100, 850, 40):
        d.line([(100, y), (1100, y + slope * 1000)], fill="black", width=3)
    return im


@pytest.mark.parametrize("degrees", [4.0, -3.0])
def test_the_estimate_finds_the_drawn_tilt(degrees):
    from fichero_server.media.image_ops import detect_deskew_angle

    assert detect_deskew_angle(_tilted_lines(degrees)) == pytest.approx(degrees, abs=0.6)


def test_straighten_uses_the_same_estimate():
    from fichero_server.api.routes.ingest.image_editing import _estimate_straighten_angle
    from fichero_server.media.image_ops import detect_deskew_angle

    im = _tilted_lines(4.0)
    assert _estimate_straighten_angle(im) == detect_deskew_angle(im) != 0.0
