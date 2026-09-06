"""The shipped app has NO OpenCV bundled (hundreds of MB, excluded), yet engine
code uses cv2 for enhance / background-removal / deskew. Those paths must
DEGRADE, never crash, when cv2 is absent — otherwise a Dev Embedded / release
build raises ImportError at runtime the moment a user enhances an image.

Simulated by pinning ``sys.modules["cv2"] = None`` so ``import cv2`` raises
ImportError exactly as it would in an env without OpenCV.
"""

from __future__ import annotations

import sys

import pytest
from PIL import Image


@pytest.fixture
def no_cv2(monkeypatch):
    # A None entry makes `import cv2` raise ImportError, mirroring an env where
    # opencv-python-headless is not installed (the shipped app).
    monkeypatch.setitem(sys.modules, "cv2", None)
    yield


def test_remove_black_background_returns_image_when_cv2_absent(no_cv2):
    from fichero_server.media.image_ops import remove_black_background_opencv

    out = remove_black_background_opencv(Image.new("RGB", (8, 8), (0, 0, 0)))
    assert out.mode == "RGBA"  # graceful no-op, not an ImportError


def test_detect_deskew_angle_is_zero_when_cv2_absent(no_cv2):
    from fichero_server.media.image_ops import detect_deskew_angle

    assert detect_deskew_angle(Image.new("RGB", (8, 8), (255, 255, 255))) == 0.0


def test_image_editing_background_removal_degrades_when_cv2_absent(no_cv2):
    from fichero_server.api.routes.ingest.image_editing import (
        _remove_black_background_opencv,
    )

    out = _remove_black_background_opencv(Image.new("RGB", (8, 8), (0, 0, 0)))
    assert out.mode == "RGBA"
