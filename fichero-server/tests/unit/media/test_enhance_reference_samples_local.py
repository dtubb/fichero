"""LOCAL ONLY: the CLAHE enhance run (contrast, yellowing, sharpen) against the legacy tool's own output on the owner's typed pages
(`image.enhance.contrast-clahe`, #6190). The pages are archive material and are never committed: set FICHERO_IMAGE_PREP_SAMPLES to a
folder holding, for each page, `<name>.before.<ext>` (the legacy crop) and `<name>.reference.<ext>` (the legacy enhanced file), and
optionally `<name>.profile` containing `handwritten` or `typescript` (default handwritten). With the variable unset the test skips.
The mean absolute difference per channel must stay under 3/255."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

THRESHOLD = 3.0
ROOT = os.environ.get("FICHERO_IMAGE_PREP_SAMPLES")


def _pairs():
    if not ROOT or not Path(ROOT).is_dir():
        return []
    out = []
    for before in sorted(Path(ROOT).glob("*.before.*")):
        name = before.name.split(".before.")[0]
        reference = next(iter(sorted(Path(ROOT).glob(f"{name}.reference.*"))), None)
        if reference is not None:
            profile_file = Path(ROOT) / f"{name}.profile"
            profile = profile_file.read_text().strip() if profile_file.is_file() else "handwritten"
            out.append((name, before, reference, profile))
    return out


@pytest.mark.skipif(not _pairs(), reason="FICHERO_IMAGE_PREP_SAMPLES is unset or holds no before/reference pairs")
@pytest.mark.parametrize("name, before, reference, profile", _pairs(), ids=[p[0] for p in _pairs()])
def test_the_clahe_enhance_matches_the_legacy_reference_within_3_of_255(name, before, reference, profile):
    from fichero_server.media.image_ops import apply_operation

    with Image.open(before) as opened:
        page = opened.convert("RGB")
    out = apply_operation(page, {"op": "enhance", "params": {"method": "clahe", "profile": profile}})
    with Image.open(reference) as opened:
        want = opened.convert("RGB").resize(out.size)
    diff = np.abs(np.asarray(out, "float32") - np.asarray(want, "float32")).mean()
    assert diff < THRESHOLD, f"{name}: mean difference {diff:.2f}/255, limit {THRESHOLD}"


def test_the_check_is_wired_even_when_no_samples_are_given(monkeypatch, tmp_path):
    """The local test's reader finds a before/reference pair and its profile in a folder (drawn here, not an archive page)."""
    for suffix, colour in (("before", 120), ("reference", 130)):
        Image.new("RGB", (40, 30), (colour, colour, colour)).save(tmp_path / f"p1.{suffix}.png")
    (tmp_path / "p1.profile").write_text("typescript")
    monkeypatch.setattr(__import__(__name__, fromlist=["x"]), "ROOT", str(tmp_path))
    (pair,) = _pairs()
    assert pair[0] == "p1" and pair[3] == "typescript"
