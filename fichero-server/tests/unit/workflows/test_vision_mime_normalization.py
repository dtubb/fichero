"""Provider-bound image MIME normalization — the file_to_data_uri seam.

Live defect (Transcribe Paleography Ensemble, T4 "Expand Semi-Diplomatic"):
a raw ``.tiff`` source reached the LLM vision path and the provider
rejected it with "Unsupported MIME type: image/tiff", failing the run.

Root cause in ``file_to_data_uri`` (vision_base.py):
 1. It labelled the data URI with the SOURCE file's MIME (``image/tiff``,
    ``image/bmp``, ...) even though vision providers only accept
    JPEG/PNG/WebP(/GIF on some).
 2. Worse, on the resize path it re-encoded the pixels to PNG but STILL
    stamped the source MIME on the URI — PNG bytes labelled image/tiff.
 3. With ``max_dimension=0`` it shipped the raw TIFF bytes verbatim.

The fix makes ``file_to_data_uri`` the single normalization seam: the
emitted MIME always matches the encoded bytes and is always a
provider-supported format (JPEG stays JPEG; everything unsupported is
re-encoded to PNG at full resolution, downscaled only past
``max_dimension``). Every vision node (process_vision, compare, extract,
similarity, video frames) routes through this one function.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import (
    VisionToolConfig,
    file_to_data_uri,
    process_vision,
)
from tests.fixture_paths import sample_file

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
TIFF_MAGICS = (b"II*\x00", b"MM\x00*")


def _decode(uri: str) -> tuple[str, bytes]:
    header, payload = uri.split(",", 1)
    mime = header.removeprefix("data:").split(";", 1)[0]
    return mime, base64.b64decode(payload)


def _write_tiff(path: Path, size: tuple[int, int] = (40, 30)) -> Path:
    Image.new("RGB", size, color=(200, 180, 120)).save(path, format="TIFF")
    return path


# ---------------------------------------------------------------------------
# The defect itself: TIFF must never leave the seam as image/tiff.
# These assertions FAIL against the pre-fix implementation — with
# max_dimension>0 it emitted PNG bytes labelled image/tiff, and with
# max_dimension=0 it emitted raw TIFF bytes labelled image/tiff.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("max_dimension", [2048, 0])
def test_tiff_never_emits_unsupported_mime(tmp_path: Path, max_dimension: int) -> None:
    tiff = _write_tiff(tmp_path / "scan.tiff")

    uri = file_to_data_uri(str(tiff), max_dimension=max_dimension)

    mime, payload = _decode(uri)
    assert mime != "image/tiff", (
        "OLD-PATH DEFECT: the seam labelled provider-bound data image/tiff, "
        "which providers reject with 'Unsupported MIME type: image/tiff'"
    )
    assert not payload.startswith(TIFF_MAGICS), "raw TIFF bytes reached the provider"
    assert mime == "image/png"
    assert payload.startswith(PNG_MAGIC), "label and bytes must agree"


def test_tiff_conversion_preserves_resolution(tmp_path: Path) -> None:
    tiff = _write_tiff(tmp_path / "small.tiff", size=(41, 29))

    mime, payload = _decode(file_to_data_uri(str(tiff), max_dimension=2048))

    assert mime == "image/png"
    with Image.open(io.BytesIO(payload)) as img:
        assert img.size == (41, 29), "no downscale below the provider limit"


def test_oversized_tiff_downscaled_to_limit(tmp_path: Path) -> None:
    tiff = _write_tiff(tmp_path / "big.tiff", size=(300, 40))

    _, payload = _decode(file_to_data_uri(str(tiff), max_dimension=100))

    with Image.open(io.BytesIO(payload)) as img:
        assert max(img.size) == 100


def test_shared_sample_tiff_fixture_converts(tmp_path: Path) -> None:
    """The real shared specimen (test-fixtures/files/sample.tiff) converts."""
    mime, payload = _decode(file_to_data_uri(str(sample_file("sample.tiff"))))
    assert mime == "image/png"
    assert payload.startswith(PNG_MAGIC)


def test_bmp_and_gif_normalize_with_matching_label(tmp_path: Path) -> None:
    for suffix, fmt in ((".bmp", "BMP"), (".gif", "GIF")):
        src = tmp_path / f"img{suffix}"
        Image.new("RGB", (10, 10), color=(1, 2, 3)).save(src, format=fmt)
        mime, payload = _decode(file_to_data_uri(str(src)))
        assert mime == "image/png", f"{suffix} must normalize to PNG"
        assert payload.startswith(PNG_MAGIC)


# ---------------------------------------------------------------------------
# Supported formats pass through untouched / stay self-consistent.
# ---------------------------------------------------------------------------


def test_jpeg_passthrough_bytes_untouched_when_no_resize(tmp_path: Path) -> None:
    jpg = tmp_path / "photo.jpg"
    Image.new("RGB", (20, 20), color=(9, 9, 9)).save(jpg, format="JPEG")

    mime, payload = _decode(file_to_data_uri(str(jpg), max_dimension=0))

    assert mime == "image/jpeg"
    assert payload == jpg.read_bytes(), "no-resize JPEG must pass through verbatim"


def test_jpeg_resize_path_keeps_jpeg_label_and_bytes(tmp_path: Path) -> None:
    jpg = tmp_path / "photo.jpg"
    Image.new("RGB", (200, 50), color=(9, 9, 9)).save(jpg, format="JPEG")

    mime, payload = _decode(file_to_data_uri(str(jpg), max_dimension=100))

    assert mime == "image/jpeg"
    assert payload.startswith(JPEG_MAGIC)


def test_png_label_matches_bytes_after_reencode(tmp_path: Path) -> None:
    png = tmp_path / "strip.png"
    Image.new("RGBA", (30, 30), color=(1, 2, 3, 255)).save(png, format="PNG")

    mime, payload = _decode(file_to_data_uri(str(png), max_dimension=2048))

    assert mime == "image/png"
    assert payload.startswith(PNG_MAGIC)


def test_undecodable_unsupported_format_raises(tmp_path: Path) -> None:
    """Garbage in an unsupported container fails HERE, not at the provider."""
    junk = tmp_path / "broken.tiff"
    junk.write_bytes(b"not an image at all")

    with pytest.raises(ValueError, match="provider-supported"):
        file_to_data_uri(str(junk))


# ---------------------------------------------------------------------------
# End-to-end through the T4 (transcribe_review → process_vision) path: a raw
# TIFF source unit must reach the vision LLM as a provider-safe PNG data URI
# and the unit must SUCCEED. Before the fix this unit failed the node with
# "1/N failed: Unsupported MIME type: image/tiff".
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t4_review_path_succeeds_on_tiff_source(tmp_path: Path) -> None:
    tiff = _write_tiff(tmp_path / "legajo-042.tiff", size=(60, 90))
    vision_mock = AsyncMock(return_value="hola mundo [rúbrica]")

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(tiff)],
            documents=[],
            prompt="Create a semi-diplomatic layer.",
            llm_config=LLMConfig(provider="openai", model="gpt-4o", api_key="k"),
            library_path="",
            task_id=None,
            tool_config=VisionToolConfig(
                artifact_type="transcription_review",
                update_page_content=False,
                trigger_embedding=False,
                supports_apple_vision=False,
            ),
            vision_mode="llm",
            force_ocr=True,
            context="prior transcription",
        )

    assert result.get("error") is None, f"T4 unit failed: {result.get('error')}"
    assert result["text"] == "hola mundo [rúbrica]"

    images = vision_mock.await_args.kwargs.get(
        "images",
        vision_mock.await_args.args[0] if vision_mock.await_args.args else [],
    )
    assert images, "vision LLM never received an image"
    mime, payload = _decode(images[0])
    assert mime == "image/png", "the TIFF must be normalized before the provider"
    assert payload.startswith(PNG_MAGIC)
