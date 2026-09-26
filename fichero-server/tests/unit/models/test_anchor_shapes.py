"""Slice 7 (#4925) -- shapes beyond the rectangle on the anchor.

Spec: `build-notes-shapes-and-anchor.md`, "`SourceAnchor` gains shapes
(additive)" and "The derived box"; design in `segments-and-geometry.md`
("Shape"). Behaviours pinned here: `source.segment.shape-kinds`, and the rule
that the rectangle's own checks do not loosen to let the new ones in.

The anchor grew four new ways to say "where" in one slice. The risk that
matters is not that a polygon fails to save -- it is that widening the type
quietly relaxes the rect rules that took the 2026-08-20 bbox review to get
right, so a box that was refused for pointing off the page starts being
accepted. `TestTheRectangleRulesDoNotLoosen` is a fixture of every rect
`validate_rect` refused before this slice, asserted to still be refused.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from fichero_server.models.anchors import (
    AnchorShape,
    AnchorShapeKind,
    AnchorSpace,
    SourceAnchor,
    shapes_bound,
    validate_points,
)

pytestmark = pytest.mark.source_model


def _anchor(**kwargs) -> SourceAnchor:
    return SourceAnchor(document_id="doc-1", **kwargs)


class TestEachKindStoresAndReadsBack:
    """`source.segment.shape-kinds`: a point, a path, a polygon, two
    polygons, and a time span each store and read back."""

    def test_a_point_is_one_place_and_encloses_nothing(self):
        anchor = _anchor(shapes=[AnchorShape(kind="point", points=[[0.5, 0.25]])])
        read = SourceAnchor.model_validate(anchor.model_dump())
        assert read.shapes[0].kind is AnchorShapeKind.point
        assert read.shapes[0].points == [[0.5, 0.25]]
        # A point has a place and no extent, so it gets no drawable rect.
        assert read.rect is None
        assert shapes_bound(read.shapes) == [0.5, 0.25, 0.0, 0.0]

    def test_an_open_path_is_not_closed_into_an_area(self):
        points = [[0.1, 0.5], [0.4, 0.55], [0.7, 0.62]]
        anchor = _anchor(shapes=[AnchorShape(kind="path", points=points)])
        read = SourceAnchor.model_validate(anchor.model_dump())
        assert read.shapes[0].kind is AnchorShapeKind.path
        assert read.shapes[0].points == points

    def test_a_polygon_round_trips(self):
        points = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.4], [0.1, 0.4]]
        read = SourceAnchor.model_validate(
            _anchor(shapes=[AnchorShape(kind="polygon", points=points)]).model_dump()
        )
        assert read.shapes[0].points == points

    def test_two_polygons_are_one_place(self):
        """The point of a LIST: a line and the mark beside it are one place as
        far as the record is concerned."""
        left = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]
        right = [[0.7, 0.6], [0.9, 0.6], [0.9, 0.8]]
        read = SourceAnchor.model_validate(
            _anchor(
                shapes=[
                    AnchorShape(kind="polygon", points=left),
                    AnchorShape(kind="polygon", points=right),
                ]
            ).model_dump()
        )
        assert [shape.points for shape in read.shapes] == [left, right]
        # One box around both, not two boxes and not the first one's.
        assert read.rect == pytest.approx([0.1, 0.1, 0.8, 0.7])

    def test_a_time_span_round_trips_and_has_no_box(self):
        read = SourceAnchor.model_validate(
            _anchor(
                media_ref="rec-1",
                shapes=[AnchorShape(kind="time", t_start=12.5, t_end=19.0)],
            ).model_dump()
        )
        assert read.shapes[0].t_start == 12.5
        assert read.shapes[0].t_end == 19.0
        assert read.shapes[0].points is None
        assert read.rect is None
        assert shapes_bound(read.shapes) is None

    def test_a_rect_shape_means_the_same_rectangle_by_two_corners_or_four(self):
        """The spec does not fix a spelling, so both mean the same box rather
        than one being refused for how it was written."""
        two = _anchor(shapes=[AnchorShape(kind="rect", points=[[0.2, 0.3], [0.5, 0.7]])])
        four = _anchor(
            shapes=[
                AnchorShape(
                    kind="rect",
                    points=[[0.2, 0.3], [0.5, 0.3], [0.5, 0.7], [0.2, 0.7]],
                )
            ]
        )
        assert two.rect == pytest.approx([0.2, 0.3, 0.3, 0.4])
        assert two.rect == pytest.approx(four.rect)


class TestAnAnchorSavedBeforeThisSliceMeansWhatItMeant:
    """Additive means additive: every anchor already on disk stays valid and
    reads the same. This is the whole reason `shapes` is optional."""

    def test_a_rect_only_anchor_is_unchanged(self):
        stored = {"document_id": "doc-1", "rect": [0.1, 0.2, 0.3, 0.4]}
        read = SourceAnchor.model_validate(stored)
        assert read.rect == [0.1, 0.2, 0.3, 0.4]
        assert read.shapes is None
        assert read.media_ref is None

    def test_a_polygon_anchor_keeps_its_polygon_field(self):
        """`polygon` is not migrated into `shapes` by this slice: rewriting
        stored rows is not additive, and both readings mean one place."""
        stored = {
            "document_id": "doc-1",
            "polygon": [[0.1, 0.1], [0.3, 0.1], [0.2, 0.3]],
        }
        read = SourceAnchor.model_validate(stored)
        assert read.polygon == [[0.1, 0.1], [0.3, 0.1], [0.2, 0.3]]
        assert read.shapes is None

    def test_a_pixel_space_anchor_still_admits_pixel_numbers(self):
        read = SourceAnchor.model_validate(
            {
                "document_id": "doc-1",
                "space": "pixel",
                "shapes": [{"kind": "point", "points": [[1200.0, 890.0]]}],
            }
        )
        assert read.space is AnchorSpace.pixel
        assert read.shapes[0].points == [[1200.0, 890.0]]


class TestTheRectangleRulesDoNotLoosen:
    """The fixture the spec asks for: every rect refused before this slice is
    still refused. A widened type is exactly when a guard gets dropped."""

    REFUSED = [
        pytest.param([0.1, 0.1, 0.0, 0.2], id="zero-width"),
        pytest.param([0.1, 0.1, 0.2, 0.0], id="zero-height"),
        pytest.param([0.5, 0.0, 0.9, 1.0], id="off-the-right-edge"),
        pytest.param([0.0, 0.5, 1.0, 0.9], id="off-the-bottom-edge"),
        pytest.param([float("nan"), 0.1, 0.2, 0.2], id="not-a-number"),
        pytest.param([float("inf"), 0.1, 0.2, 0.2], id="infinite"),
        pytest.param([-0.1, 0.1, 0.2, 0.2], id="negative"),
        pytest.param([1.2, 0.1, 0.2, 0.2], id="above-one"),
        pytest.param([0.1, 0.1, 0.2], id="three-numbers"),
        pytest.param([0.1, 0.1, 0.2, 0.2, 0.2], id="five-numbers"),
    ]

    @pytest.mark.parametrize("rect", REFUSED)
    def test_it_is_still_refused(self, rect):
        with pytest.raises(ValidationError):
            _anchor(rect=rect)

    @pytest.mark.parametrize("rect", REFUSED)
    def test_it_is_still_refused_with_shapes_beside_it(self, rect):
        """Not a way in: sending shapes does not buy a bad rect a pass."""
        with pytest.raises(ValidationError):
            _anchor(
                rect=rect,
                shapes=[AnchorShape(kind="point", points=[[0.5, 0.5]])],
            )

    def test_a_derived_rect_obeys_the_same_rules(self):
        """The engine derives it, so nothing checks it after the fact -- it
        must be constructed inside the rules."""
        anchor = _anchor(
            shapes=[AnchorShape(kind="polygon", points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])]
        )
        assert anchor.rect == pytest.approx([0.0, 0.0, 1.0, 1.0])
        SourceAnchor.model_validate(anchor.model_dump())  # refuses if it drifted

    def test_a_degenerate_bound_never_becomes_the_rect(self):
        """A level path has a real place and no height. `rect` promises a
        drawable rectangle, so it stays unset rather than holding a zero."""
        anchor = _anchor(shapes=[AnchorShape(kind="path", points=[[0.1, 0.5], [0.8, 0.5]])])
        assert anchor.rect is None
        assert shapes_bound(anchor.shapes) == pytest.approx([0.1, 0.5, 0.7, 0.0])


class TestTheRefusals:
    """Each typed refusal the spec lists, asserted on the message so the
    reason reaches the caller rather than a bare 'invalid anchor'."""

    def test_shapes_and_rect_that_disagree(self):
        with pytest.raises(ValidationError, match="disagrees with the shapes"):
            _anchor(
                rect=[0.9, 0.9, 0.05, 0.05],
                shapes=[
                    AnchorShape(kind="polygon", points=[[0.1, 0.1], [0.3, 0.1], [0.2, 0.3]])
                ],
            )

    def test_a_rect_that_agrees_within_float_drift_is_accepted(self):
        """The same tolerance the rect's own edge check allows: a bound
        assembled as 1/3 + 2/3 is geometrically perfect."""
        third = 1.0 / 3.0
        shapes = [AnchorShape(kind="rect", points=[[third, 0.1], [third + third, 0.4]])]
        anchor = _anchor(rect=[third, 0.1, third, 0.3], shapes=shapes)
        assert anchor.rect == [third, 0.1, third, 0.3]

    def test_a_path_of_one_point(self):
        with pytest.raises(ValidationError, match="path points needs at least 2"):
            AnchorShape(kind="path", points=[[0.1, 0.1]])

    def test_a_polygon_of_two_points(self):
        with pytest.raises(ValidationError, match="polygon points needs at least 3"):
            AnchorShape(kind="polygon", points=[[0.1, 0.1], [0.3, 0.1]])

    def test_a_point_of_two_points(self):
        with pytest.raises(ValidationError, match="exactly 1 point"):
            AnchorShape(kind="point", points=[[0.1, 0.1], [0.3, 0.1]])

    def test_a_point_outside_the_image(self):
        with pytest.raises(ValidationError, match=r"must be in \[0, 1\]"):
            _anchor(shapes=[AnchorShape(kind="point", points=[[1.4, 0.5]])])

    def test_a_time_span_with_no_media_ref(self):
        with pytest.raises(ValidationError, match="needs a media_ref"):
            _anchor(shapes=[AnchorShape(kind="time", t_start=1.0, t_end=2.0)])

    def test_a_time_span_that_does_not_move_forward(self):
        with pytest.raises(ValidationError, match="must be <"):
            AnchorShape(kind="time", t_start=5.0, t_end=5.0)

    def test_a_negative_time(self):
        with pytest.raises(ValidationError, match="t_start must be >= 0"):
            AnchorShape(kind="time", t_start=-1.0, t_end=2.0)

    def test_a_time_shape_carrying_points(self):
        with pytest.raises(ValidationError, match="carries no points"):
            AnchorShape(kind="time", t_start=1.0, t_end=2.0, points=[[0.1, 0.1]])

    def test_an_area_shape_carrying_a_time_span(self):
        with pytest.raises(ValidationError, match="only a time shape carries"):
            AnchorShape(kind="point", points=[[0.1, 0.1]], t_start=1.0)

    def test_a_shape_with_no_points_at_all(self):
        with pytest.raises(ValidationError, match="needs points"):
            AnchorShape(kind="polygon")

    def test_an_empty_shapes_list(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            _anchor(shapes=[])

    def test_a_point_that_is_not_a_pair(self):
        with pytest.raises(ValidationError, match=r"must be \[x, y\]"):
            AnchorShape(kind="point", points=[[0.1, 0.2, 0.3]])

    def test_a_point_that_is_not_a_number(self):
        with pytest.raises(ValidationError, match="must be finite"):
            AnchorShape(kind="point", points=[[float("nan"), 0.2]])

    def test_a_rect_beside_a_time_only_anchor(self):
        with pytest.raises(ValidationError, match="no shape has an extent"):
            _anchor(
                rect=[0.1, 0.1, 0.2, 0.2],
                media_ref="rec-1",
                shapes=[AnchorShape(kind="time", t_start=1.0, t_end=2.0)],
            )


class TestValidatePointsIsTheOneCheck:
    """`validate_rect` had to exist because the rule was applied to one field
    out of six. The point rule gets one function for the same reason."""

    def test_it_accepts_the_edge_within_drift(self):
        """One bit past 1.0 -- the smallest float there is above the edge, and
        what a coordinate assembled by arithmetic actually lands on."""
        drifted = math.nextafter(1.0, 2.0)
        assert drifted > 1.0, "the premise: this value is past the edge"
        assert validate_points([[drifted, 0.0]]) == [[drifted, 0.0]]

    def test_it_refuses_a_point_genuinely_past_the_edge(self):
        with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
            validate_points([[1.01, 0.0]])

    def test_pixel_space_admits_large_numbers(self):
        assert validate_points([[4032.0, 3024.0]], space=AnchorSpace.pixel) is not None

    def test_none_passes_through(self):
        assert validate_points(None) is None
