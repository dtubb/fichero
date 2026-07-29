"""Real Apple Vision OCR integration tests.

Marked with @pytest.mark.requires_apple_vision so they're auto-skipped
on non-macOS or when PyObjC's Quartz/Vision modules aren't importable
(see fichero-server/tests/conftest.py for the probe).

Cost: zero. Apple Vision is on-device + free. Runtime: ~1-3s per test
on Apple Silicon for the small fixture images this file generates.

These tests cover the boundary that unit tests deliberately mock —
real macOS framework calls. They're the only place we catch bugs like:
  - PyObjC threading issues with Quartz (#830)
  - Pillow normalisation failures on TIF / progressive JPEG (#796)
  - Apple Vision returning empty silently on hard pages (#834)

Run targeted:
    PYTHONPATH=fichero-server/src .venv/bin/pytest \\
        fichero-server/tests/integration/test_apple_vision_real.py -v
"""

from __future__ import annotations

import os
import pytest


def _apple_vision_runtime_ready() -> bool:
    """Real Vision smoke is opt-in and requires a usable macOS GUI session."""
    if os.getenv("FICHERO_RUN_APPLE_VISION_REAL") != "1":
        return False
    try:
        import Quartz  # noqa: F401
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _apple_vision_runtime_ready(),
    reason="Real Apple Vision smoke is opt-in and requires a usable macOS Vision runtime",
)


@pytest.fixture(scope="module")
def sample_text_image(tmp_path_factory):
    """Generate a small PNG with deterministic, easily-recognised text.

    Pillow renders three lines of high-contrast text on white. Apple
    Vision recognises this in well under a second. Module-scoped so we
    don't regenerate the image once per test.
    """
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 30), "FICHERO TEST PAGE", fill="black", font=font)
    draw.text((20, 90), "Apple Vision OCR", fill="black", font=font)
    draw.text((20, 150), "PYTHON INTEGRATION", fill="black", font=font)

    out = tmp_path_factory.mktemp("vision") / "sample.png"
    img.save(out)
    return out


@pytest.fixture(scope="module")
def blank_image(tmp_path_factory):
    """A pure-white 100x100 PNG with no text. Apple Vision should
    recognise nothing and return an empty string — letting us pin the
    silent-empty contract documented in #834."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), "white")
    out = tmp_path_factory.mktemp("vision") / "blank.png"
    img.save(out)
    return out


def test_vision_recognises_known_text(sample_text_image):
    """Real Apple Vision OCR on a fixture PNG returns text containing
    each of the three rendered phrases. This is the smoke test — proves
    Vision is reachable, the Pillow normalise pass works, and CGImage
    creation hasn't regressed."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    text = apple_vision_ocr(str(sample_text_image), language="en")

    # Vision is good but not always perfect on display fonts; assert
    # case-insensitive substring matches on each line, not exact equality.
    upper = text.upper()
    assert "FICHERO" in upper, f"missing FICHERO in: {text!r}"
    assert "APPLE VISION" in upper, f"missing APPLE VISION in: {text!r}"
    assert "INTEGRATION" in upper, f"missing INTEGRATION in: {text!r}"


def test_vision_empty_on_blank_image(blank_image):
    """Pure-white image returns empty string. Documents the silent-empty
    behaviour from #834 — the wrapper currently returns "" with no
    warning, which is the bug filed against that issue. This test pins
    the current behaviour so when #834 lands a fix (log + retry-with-
    fast-level), this test will need updating."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    text = apple_vision_ocr(str(blank_image), language="en")
    assert text == "", f"expected empty result on blank, got {text!r}"


def test_vision_handles_missing_file_cleanly():
    """Non-existent file path raises a structured error (not a Python
    AttributeError or KeyError from inside CG). The wrapper has an
    explicit existence check at vision_base.py:297."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    with pytest.raises((ValueError, RuntimeError)) as exc_info:
        apple_vision_ocr("/nonexistent/path/that/wont/exist.png", language="en")

    msg = str(exc_info.value).lower()
    assert "not found" in msg or "could not" in msg or "failed" in msg


@pytest.mark.parametrize("language", ["en", "es"])
def test_vision_accepts_language_codes(sample_text_image, language):
    """Both supported language hints (English, Spanish) accept and route
    through the lang_map at vision_base.py:395-402 without error. We
    don't assert WHICH text comes back (Spanish hint won't change English
    fixture much), just that the call completes."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr
    text = apple_vision_ocr(str(sample_text_image), language=language)
    assert isinstance(text, str)
