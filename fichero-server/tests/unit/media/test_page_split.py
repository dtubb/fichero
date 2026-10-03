"""Gutter finding and the split decision, pinned on 11 real notebook photos (`prep.split-at-the-gutter`, #5382).

The fixture holds measured column-brightness profiles of Sergio Mosquera's notebook photos (3000 x 2000),
taken inside Apple Vision's document outline: numbers, not images, because the notebooks' rights
are not yet confirmed. Eight are open notebooks with a spiral that sits 50-250 px off the photo's
centre; three are closed covers. The review that chose this design is fichero-projects
`projects/sergio-notebooks/prep-review.md`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fichero_server.media import page_split as ps

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "page_split" / "sergio_gutter_profiles.json"
PHOTOS = json.loads(FIXTURE.read_text())["photos"]
SPREADS = [p for p in PHOTOS if p["expect"]["decision"] == "split"]
COVERS = [p for p in PHOTOS if p["expect"]["decision"] == "single_page"]


def _outline(photo) -> ps.Outline:
    return ps.Outline(tuple(photo["outline"]), photo["outline_confidence"], "apple-vision")


def _plan(photo, **kw) -> dict:
    outline = _outline(photo)
    offset, confidence = ps.find_gutter(np.array(photo["profile"], dtype=np.float32), step=photo["profile_step"])
    gutter = outline.box[0] + offset if outline.aspect >= ps.SINGLE_PAGE_MAX_ASPECT else None
    return ps.plan_split(tuple(photo["size"]), outline, gutter, confidence, **kw)


def test_fixture_covers_spreads_and_covers():
    """WHY: the thresholds below were chosen on these photos; if the fixture lost its covers or its
    spreads, the tests would pass while no longer guarding either way the split can go wrong."""
    assert len(SPREADS) == 8 and len(COVERS) == 3


@pytest.mark.parametrize("photo", SPREADS, ids=[p["photo"] for p in SPREADS])
def test_an_open_notebook_is_cut_on_its_spiral(photo):
    """WHY: a cut off the spiral slices through a page's writing, and the reader then gets half lines
    from both pages. The expected band is where the spiral is on that photo (the legacy split's
    measured cut +-70 px, about half the ring width, or read by eye for C02_002)."""
    plan = _plan(photo)
    lo, hi = photo["expect"]["spiral_px"]
    assert plan["decision"] == "split", plan["reason"]
    assert lo <= plan["gutter_x"] <= hi, f"cut at {plan['gutter_x']}, spiral at {lo}-{hi}"
    left, right = plan["pages"]
    assert left[0] + left[2] == right[0] == plan["gutter_x"], "the two pages meet at the gutter, no gap or overlap"


def test_the_image_middle_misses_the_spiral_on_most_spreads():
    """WHY this exists at all: today's split_images cuts every photo at its middle (x = 1500). On six
    of these eight spreads the middle is outside the spiral, so a fixed half cuts into the text. If
    this ever stops holding, the fixture no longer tests what the gutter search is for."""
    misses = [p["photo"] for p in SPREADS if not (p["expect"]["spiral_px"][0] <= p["size"][0] // 2 <= p["expect"]["spiral_px"][1])]
    assert len(misses) >= 6, misses


@pytest.mark.parametrize("photo", COVERS, ids=[p["photo"] for p in COVERS])
def test_a_closed_notebook_is_never_cut(photo):
    """WHY: the legacy split cut two of these three covers in half, because it measured the whole
    photo and a cover's edge looks like a spiral. An outline narrower than it is tall (0.68-0.73
    here; spreads are 1.36-1.43) is one page."""
    plan = _plan(photo)
    assert plan["decision"] == "single_page"
    assert plan["pages"] == [[photo["outline"][0], photo["outline"][1],
                              photo["outline"][2] - photo["outline"][0], photo["outline"][3] - photo["outline"][1]]]


def test_a_spread_with_an_unclear_gutter_is_proposed_not_cut():
    """WHY (`prep.unsure-becomes-a-proposal`): a wrong cut changes the library; an unsure one must
    show up for a person instead. The lowest real spread confidence was 0.19, so a threshold above it
    must turn that photo into a proposal with its cut recorded, and one page, not two."""
    low = min(SPREADS, key=lambda p: _plan(p)["gutter_confidence"])
    plan = _plan(low, min_confidence=_plan(low)["gutter_confidence"] + 0.01)
    assert plan["decision"] == "proposed" and plan["needs_review"]
    assert len(plan["pages"]) == 1 and plan["gutter_x"] is not None


def test_the_real_spreads_all_clear_the_default_threshold():
    """WHY: the default must not turn the measured spreads into proposals; if it did, every open
    notebook would wait for review and the job would do nothing."""
    assert all(_plan(p)["gutter_confidence"] >= ps.MIN_GUTTER_CONFIDENCE for p in SPREADS)


def test_pages_come_out_in_reading_order():
    """WHY: page order is the reading order of the notebook; a right-to-left script reads the right
    page first, and the order is what the children's sequence records."""
    photo = SPREADS[0]
    ltr, rtl = _plan(photo), _plan(photo, direction="rtl")
    assert ltr["pages"][0][0] < ltr["pages"][1][0]
    assert rtl["pages"] == list(reversed(ltr["pages"]))


def test_a_wide_outline_without_a_gutter_is_a_proposal():
    """WHY: a wide single sheet (a ledger page photographed landscape) has no dark band; its depth is
    near 0 and it must not be cut at whatever column happens to be darkest."""
    outline = ps.Outline((0, 0, 1500, 1000), 0.99, "apple-vision")
    offset, confidence = ps.find_gutter(np.full(375, 200.0) + np.random.default_rng(0).normal(0, 1, 375))
    plan = ps.plan_split((1500, 1000), outline, offset, confidence)
    assert plan["decision"] == "proposed"


def test_column_profile_leaves_out_the_outline_edges():
    """WHY: the outline's top and bottom touch the table and the ruler; a dark strip there must not
    pull a column's mean down and fake a gutter."""
    gray = np.full((100, 40), 200, dtype=np.uint8)
    gray[:5, 20] = 0  # dark only in the top 5 rows of column 20
    profile = ps.column_profile(gray, (0, 0, 40, 100), step=1)
    assert profile[20] == pytest.approx(200.0)


def test_whole_frame_says_so():
    """WHY: when Vision is unavailable the split still runs on the whole image, and its result must say
    the outline was not found rather than pass the frame off as a detection."""
    outline = ps.whole_frame(300, 200)
    assert outline.method == "frame" and outline.box == (0, 0, 300, 200) and outline.confidence == 0.0
