"""The ingest limit is 200 megapixels (#5515, ruled 2026-09-28): a 150 MP scan opens; 201 MP is refused."""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.loaders import image_loader
from fichero_server.loaders.image_loader import UnsafeImageError, open_image_checked


def _scan(tmp_path, width, height):
    path = tmp_path / f"scan_{width}x{height}.png"
    Image.new("1", (width, height)).save(path)  # 1-bit keeps a 150 MP file small
    return path


def test_a_150_megapixel_scan_opens(tmp_path):
    img = open_image_checked(_scan(tmp_path, 15_000, 10_000))
    assert img.size == (15_000, 10_000)


def test_a_67_megapixel_photo_the_issue_named_opens(tmp_path):
    assert open_image_checked(_scan(tmp_path, 10_000, 6_700)).size == (10_000, 6_700)


def test_above_200_megapixels_is_refused_by_our_check(tmp_path):
    with pytest.raises((UnsafeImageError, Image.DecompressionBombError, Image.DecompressionBombWarning)):
        open_image_checked(_scan(tmp_path, 20_100, 10_000))


def test_pil_guard_moves_with_the_limit():
    assert Image.MAX_IMAGE_PIXELS >= image_loader._MAX_IMAGE_PIXELS


def test_the_reichsanzeiger_page_the_issue_named_gets_its_size_at_ingest(tmp_path):
    """#5183: a 74.8 MP newspaper page (10168x7352) was refused at 50 MP; ingest now records its size."""
    from types import SimpleNamespace

    from fichero_server.importers.ingest import _extract_image_metadata

    doc = SimpleNamespace(metadata={})
    _extract_image_metadata(doc, _scan(tmp_path, 10_168, 7_352))
    assert (doc.metadata["width"], doc.metadata["height"]) == (10_168, 7_352)


def test_a_refusal_names_the_pixel_count(tmp_path):
    with pytest.raises(UnsafeImageError, match=r"20100x10000"):
        open_image_checked(_scan(tmp_path, 20_100, 10_000))
