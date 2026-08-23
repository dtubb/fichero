"""Rect mapping between a node's frame and its parent's.

The Marshall case drives these: an opening is split 50/50 into a left and a
right page, and a box found on the left page must be showable on the opening
(and vice versa) without anyone re-deriving the arithmetic at each call site.
"""

from __future__ import annotations

import pytest

from fichero_server.media.region_math import (
    compose,
    compose_chain,
    rect_from_parent,
    rect_to_parent,
    weakest_confidence,
)
from fichero_server.models.anchors import AnchorSpace, NodeRegion, RegionConfidence

LEFT_HALF = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0], method="nominal-even-split")
RIGHT_HALF = NodeRegion(rect=[0.5, 0.0, 0.5, 1.0], method="nominal-even-split")


class TestRectToParent:
    def test_full_page_maps_onto_the_region_itself(self):
        """The property worth remembering: a node's whole frame IS its region
        in the parent."""
        assert rect_to_parent([0, 0, 1, 1], LEFT_HALF) == [0.0, 0.0, 0.5, 1.0]
        assert rect_to_parent([0, 0, 1, 1], RIGHT_HALF) == [0.5, 0.0, 0.5, 1.0]

    def test_box_on_left_page_lands_on_left_of_opening(self):
        # Centred horizontally on the left page -> quarter across the opening.
        mapped = rect_to_parent([0.5, 0.25, 0.2, 0.1], LEFT_HALF)
        assert mapped == pytest.approx([0.25, 0.25, 0.1, 0.1])

    def test_box_on_right_page_is_offset_past_the_fold(self):
        mapped = rect_to_parent([0.0, 0.0, 0.2, 0.1], RIGHT_HALF)
        assert mapped == pytest.approx([0.5, 0.0, 0.1, 0.1])

    def test_vertical_is_unscaled_for_a_full_height_region(self):
        mapped = rect_to_parent([0.0, 0.3, 1.0, 0.4], LEFT_HALF)
        assert mapped[1] == pytest.approx(0.3)
        assert mapped[3] == pytest.approx(0.4)

    def test_pixel_space_region_refuses_rather_than_guessing(self):
        pixel_region = NodeRegion(rect=[0, 0, 600, 900], space=AnchorSpace.pixel)
        with pytest.raises(ValueError, match="normalized space"):
            rect_to_parent([0, 0, 1, 1], pixel_region)


class TestRectFromParent:
    def test_round_trips_with_to_parent(self):
        original = [0.3, 0.4, 0.2, 0.15]
        there = rect_to_parent(original, RIGHT_HALF)
        back = rect_from_parent(there, RIGHT_HALF)
        assert back == pytest.approx(original)

    def test_returns_none_when_the_rect_is_on_the_other_page(self):
        """A box on the right of the opening is NOT on the left page. None is
        the honest answer and must not be read as 'at the origin'."""
        on_right_of_opening = [0.7, 0.2, 0.1, 0.1]
        assert rect_from_parent(on_right_of_opening, LEFT_HALF) is None

    def test_clips_a_rect_that_straddles_the_fold(self):
        """A line crossing the fold really is partly on each half; dropping
        the visible part would be worse than reporting it."""
        straddling = [0.45, 0.5, 0.10, 0.05]
        left = rect_from_parent(straddling, LEFT_HALF)
        right = rect_from_parent(straddling, RIGHT_HALF)
        assert left is not None and right is not None
        # Left page sees the first half of it, ending exactly at its edge.
        assert left[0] + left[2] == pytest.approx(1.0)
        # Right page sees the remainder, starting exactly at its edge.
        assert right[0] == pytest.approx(0.0)

    def test_edge_touching_rect_does_not_count_as_overlap(self):
        touching = [0.5, 0.0, 0.1, 0.1]  # starts exactly at the fold
        assert rect_from_parent(touching, LEFT_HALF) is None


class TestCompose:
    def test_two_hops_equal_one(self):
        """A box in a page in an opening: composing then mapping must equal
        mapping twice."""
        box_in_page = NodeRegion(rect=[0.2, 0.2, 0.4, 0.4])
        collapsed = compose(RIGHT_HALF, box_in_page)
        stepwise = rect_to_parent(box_in_page.rect, RIGHT_HALF)
        assert collapsed.rect == pytest.approx(stepwise)

    def test_method_records_both_hops(self):
        inner = NodeRegion(rect=[0.2, 0.2, 0.4, 0.4], method="user-drawn")
        assert compose(LEFT_HALF, inner).method == "nominal-even-split -> user-drawn"

    def test_chain_collapses_outermost_first(self):
        page = NodeRegion(rect=[0.5, 0.0, 0.5, 1.0])
        region = NodeRegion(rect=[0.0, 0.5, 1.0, 0.5])
        box = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0])
        chained = compose_chain([page, region, box])
        pairwise = compose(compose(page, region), box)
        assert chained.rect == pytest.approx(pairwise.rect)

    def test_empty_chain_is_none_not_a_full_page_region(self):
        """Inventing [0,0,1,1] would assert the node fills its parent — a real
        and different claim."""
        assert compose_chain([]) is None

    def test_single_element_chain_is_itself(self):
        assert compose_chain([LEFT_HALF]) is LEFT_HALF


class TestConfidencePropagation:
    def test_measured_through_nominal_becomes_nominal(self):
        """A chain is only as good as its shakiest link. Marshall's fold was
        never measured, so nothing derived through it may claim to be."""
        measured = NodeRegion(rect=[0.1, 0.1, 0.2, 0.2], confidence=RegionConfidence.measured)
        assert compose(LEFT_HALF, measured).confidence is RegionConfidence.nominal

    def test_measured_through_measured_stays_measured(self):
        outer = NodeRegion(rect=[0, 0, 0.5, 1], confidence=RegionConfidence.measured)
        inner = NodeRegion(rect=[0.1, 0.1, 0.2, 0.2], confidence=RegionConfidence.measured)
        assert compose(outer, inner).confidence is RegionConfidence.measured

    def test_user_outranks_measured_but_still_loses_to_nominal(self):
        user = NodeRegion(rect=[0.1, 0.1, 0.2, 0.2], confidence=RegionConfidence.user)
        measured = NodeRegion(rect=[0, 0, 0.5, 1], confidence=RegionConfidence.measured)
        assert weakest_confidence(user, measured) is RegionConfidence.measured
        assert weakest_confidence(user, LEFT_HALF) is RegionConfidence.nominal

    def test_no_regions_defaults_to_nominal(self):
        assert weakest_confidence() is RegionConfidence.nominal


class TestRegionsNameTheFrameTheyWereMeasuredOn:
    """`NodeRegion.rendition_id` (2026-08-23, Daniel's ruling).

    Frames CHAIN: an image is cut to spreads, then pages, then rotated,
    deskewed, background-removed, enhanced, and only then are entries
    extracted. A rect measured somewhere along that chain is meaningless
    without saying WHERE, so a region names its rendition for the same reason
    an anchor already did.
    """

    def test_absent_by_default_so_existing_rows_stay_valid(self):
        assert NodeRegion(rect=[0, 0, 1, 1]).rendition_id is None

    def test_composing_refuses_an_inner_measured_on_a_rendition(self):
        """A fraction of the ROTATED frame is not the same fraction of the
        original. This module has no database, so it cannot resolve the
        difference and must not compose past it."""
        outer = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0])
        inner = NodeRegion(rect=[0.0, 0.0, 1.0, 0.5], rendition_id="rend-rotated")

        with pytest.raises(ValueError, match="rend-rotated"):
            compose(outer, inner)

    def test_the_refusal_says_what_to_do_next(self):
        outer = NodeRegion(rect=[0, 0, 1, 1])
        inner = NodeRegion(rect=[0, 0, 1, 1], rendition_id="r1")
        with pytest.raises(ValueError, match="Resolve it through"):
            compose(outer, inner)

    def test_an_outer_rendition_propagates_to_the_result(self):
        """Collapsing two hops does not change WHICH PICTURE the answer is
        about — the composed region still lives in outer's frame."""
        outer = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0], rendition_id="rend-enhanced")
        inner = NodeRegion(rect=[0.0, 0.0, 1.0, 0.5])

        assert compose(outer, inner).rendition_id == "rend-enhanced"

    def test_the_ordinary_case_is_untouched(self):
        """Neither side names a rendition: the overwhelmingly common shape and
        it must compose exactly as before."""
        outer = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0])
        inner = NodeRegion(rect=[0.0, 0.0, 1.0, 0.5])

        composed = compose(outer, inner)
        assert composed.rect == [0.0, 0.0, 0.5, 0.5]
        assert composed.rendition_id is None
