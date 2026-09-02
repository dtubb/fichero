"""No image writer decides for itself what transparency becomes.

Daniel, 2026-09-02: background-removed images rendered on a BLACK ground.
The cause was not one bad line but a DECISION made independently in a dozen
places, identically wrong every time::

    if fmt == "jpeg" and image.mode in {"RGBA", "P"}:
        image = image.convert("RGB")

``convert("RGB")`` does not composite — it drops the alpha channel and keeps
the colour underneath, which for a cut-out is (0, 0, 0).

Fix-then-sweep: the fix is one shared owner
(``fichero_server.media.image_flatten.flatten_for_opaque_format``) and this
ledger, which fails if any writer starts making the decision locally again.
A grep-style seam guard, like the repo's other ledgers — it measures the
SHAPE of the code, so it catches a re-introduction that no behavioural test
would think to cover.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TOOLS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src" / "fichero_server" / "workflows" / "tools"
)
STORAGE = (
    Path(__file__).resolve().parents[3]
    / "src" / "fichero_server" / "db" / "storage.py"
)

# Two shapes drop alpha, and a single regex cannot tell them from the safe one:
#
#   BAD   mode in {"RGBA", "P"}          -> convert("RGB")   alpha IS converted
#   BAD   mode not in ("RGB", "L")       -> convert("RGB")   alpha not exempted
#   FINE  mode not in ("RGB","RGBA","L") -> convert("RGB")   alpha IS exempted
#
# The third is how the PNG paths in vision_base legitimately normalise exotic
# modes (CMYK, I;16) while letting transparency through untouched. An
# `in`-only pattern misses the second shape — which is the exact line that
# blackened every thumbnail — so the check reads the mode list instead of
# pattern-matching the whole line.
_MODE_TEST = re.compile(
    r'mode\s+(not\s+)?in\s+[({]([^)}]*)[)}][^\n]*\n\s*\S*\s*=\s*\S*\.convert\("RGB"\)'
)
_ALPHA_MODES = {"RGBA", "LA"}


def find_alpha_drop(source: str) -> str | None:
    """Return the offending snippet, or None when nothing drops alpha."""
    for match in _MODE_TEST.finditer(source):
        negated = bool(match.group(1))
        modes = set(re.findall(r'"([^"]+)"', match.group(2)))
        if negated:
            # Safe only when every alpha mode is exempted from the convert.
            if not _ALPHA_MODES & modes:
                return match.group(0)
        elif _ALPHA_MODES & modes:
            return match.group(0)
    return None


def _tool_sources() -> list[Path]:
    files = sorted(TOOLS_DIR.glob("*.py"))
    assert files, f"no tool sources under {TOOLS_DIR} — this guard measures nothing"
    return files


@pytest.mark.parametrize("path", _tool_sources(), ids=lambda p: p.name)
def test_no_workflow_tool_drops_alpha_to_flatten(path: Path):
    source = path.read_text()
    match = find_alpha_drop(source)
    assert match is None, (
        f"{path.name} resolves transparency locally by DROPPING the alpha "
        f"channel:\n\n{match}\n\n"
        "That flattens cut-outs to BLACK. Call "
        "fichero_server.media.image_flatten.flatten_for_opaque_format instead."
    )


def test_the_storage_rendition_path_uses_the_shared_owner():
    """Thumbnails and display renditions are where Daniel saw the black."""
    source = STORAGE.read_text()
    assert "flatten_for_opaque_format" in source
    assert find_alpha_drop(source) is None


def test_every_jpeg_save_in_the_tools_flattens_first():
    """A JPEG save path must resolve transparency through the shared owner.

    Pins the seven tools that each carried their own copy of the bad line.
    """
    expected = {
        "segment_images.py",
        "prepare_images.py",
        "enhance_images.py",
        "rotate_images.py",
        "split_images.py",
        "recombine_segments.py",
        "fuzzy_clean_images.py",
    }
    for name in expected:
        source = (TOOLS_DIR / name).read_text()
        assert 'if fmt == "jpeg":' in source, f"{name}: JPEG save path changed shape"
        assert "flatten_for_opaque_format(image)" in source, (
            f"{name} saves JPEG without routing transparency through the "
            "shared flatten"
        )


def test_the_guard_would_actually_fire():
    """A ledger nobody has seen fail is a ledger that proves nothing.

    Memory: every guardrail rule needs a fixture proving it FIRES.
    """
    offender = (
        'def _save(image, fmt):\n'
        '    if fmt == "jpeg" and image.mode in {"RGBA", "P"}:\n'
        '        image = image.convert("RGB")\n'
    )
    assert find_alpha_drop(offender) is not None, (
        "the seam pattern no longer matches the exact line it was written for"
    )


def test_the_guard_does_not_fire_on_the_fixed_shape():
    fixed = (
        'def _save(image, fmt):\n'
        '    if fmt == "jpeg":\n'
        '        image = flatten_for_opaque_format(image)\n'
    )
    assert find_alpha_drop(fixed) is None


def test_the_guard_does_not_fire_on_an_opaque_only_convert():
    """An analysis path that has no alpha to resolve is allowed to convert."""
    analysis = '    rgb = image.convert("RGB")\n'
    assert find_alpha_drop(analysis) is None


def test_the_guard_also_fires_on_the_original_storage_shape():
    """The line that blackened every thumbnail did not name an alpha mode at
    all — it named the modes to KEEP. An `in`-only pattern misses it."""
    offender = (
        '    if img.mode not in ("RGB", "L"):\n'
        '        img = img.convert("RGB")\n'
    )
    assert find_alpha_drop(offender) is not None


def test_the_guard_spares_a_convert_that_exempts_alpha():
    """vision_base's PNG paths normalise CMYK/I;16 while letting RGBA and LA
    through untouched. Flagging those would be a false positive."""
    safe = (
        '    if converted.mode not in ("RGB", "RGBA", "L"):\n'
        '        converted = converted.convert("RGB")\n'
    )
    assert find_alpha_drop(safe) is None
    safe_png = (
        '    if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):\n'
        '        img = img.convert("RGB")\n'
    )
    assert find_alpha_drop(safe_png) is None


# --- behaviour, not just shape -------------------------------------------
#
# The seam guard above reads code. These call the real savers, because a guard
# that only reads shape can be satisfied by code that still writes black.

_SAVERS = [
    ("segment_images", "_save_image"),
    ("prepare_images", "_save_prepared_image"),
    ("enhance_images", "_save_image"),
    ("rotate_images", "_save_image"),
    ("split_images", "_save_image"),
    ("recombine_segments", "_save_image"),
    ("fuzzy_clean_images", "_save_image"),
]


@pytest.mark.parametrize("module_name, saver_name", _SAVERS, ids=[m for m, _ in _SAVERS])
def test_each_tool_writes_transparency_as_white_jpeg(module_name, saver_name, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    import importlib

    module = importlib.import_module(f"fichero_server.workflows.tools.{module_name}")
    saver = getattr(module, saver_name)

    cutout = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    for x in range(5, 15):
        for y in range(5, 15):
            cutout.putpixel((x, y), (255, 0, 0, 255))

    out = tmp_path / f"{module_name}.jpg"
    saver(cutout, out, output_format="jpg", compression_quality=90)

    with Image.open(out) as written:
        corner = written.getpixel((0, 0))
        centre = written.getpixel((10, 10))
    assert min(corner) > 230, f"{module_name} wrote a {corner} background, not white"
    assert centre[0] > 200 and centre[1] < 60, (
        f"{module_name} lost the opaque content: {centre}"
    )
