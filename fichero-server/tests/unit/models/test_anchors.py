"""The shared anchor/region invariants (2026-08-20 bbox review).

These exist because the rule they enforce was previously WRITTEN DOWN and
applied to one field out of six: ``validate_annotation_bbox`` guarded
``Annotation.bbox`` while ``SourceSupport.source_bbox``,
``KnowledgeClaim.source_bbox`` and ``ContentSourceAnchor.bbox`` accepted
negatives, values above 1, wrong lengths and NaN. A rule enforced in one place
reads as guaranteed everywhere, which is worse than no rule.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import (
    AnchorSpace,
    NodeRegion,
    RegionConfidence,
    SourceAnchor,
)


class TestRectValidation:
    def test_normalized_rect_accepted(self):
        region = NodeRegion(rect=[0.0, 0.0, 0.5, 1.0])
        assert region.rect == [0.0, 0.0, 0.5, 1.0]
        assert region.space is AnchorSpace.normalized

    @pytest.mark.parametrize(
        "rect,reason",
        [
            ([0, 0, 2, 1], "component above 1"),
            ([-0.1, 0, 0.5, 0.5], "negative component"),
            ([0, 0, 0, 1], "zero width"),
            ([0, 0, 0.5, 0], "zero height"),
            ([0, 0, 1], "too few elements"),
            ([0, 0, 0.5, 0.5, 0.5], "too many elements"),
            ([0, 0, float("nan"), 1], "NaN"),
            ([0, 0, float("inf"), 1], "infinity"),
        ],
    )
    def test_malformed_rect_rejected(self, rect, reason):
        with pytest.raises(ValidationError):
            NodeRegion(rect=rect)

    def test_pixel_space_allows_values_above_one(self):
        """The declaration-order trap: a field validator on ``rect`` runs
        BEFORE ``space`` is populated, so a pixel rect was judged against the
        0..1 rule and rejected. Caught by smoke test before it ever shipped."""
        region = NodeRegion(rect=[0, 0, 1200, 900], space=AnchorSpace.pixel)
        assert region.rect == [0.0, 0.0, 1200.0, 900.0]

    def test_pixel_space_still_rejects_negatives(self):
        with pytest.raises(ValidationError):
            NodeRegion(rect=[-1, 0, 1200, 900], space=AnchorSpace.pixel)


class TestNodeRegionHonesty:
    def test_defaults_to_nominal_not_measured(self):
        """A rect nobody verified must not read as a measurement. The Marshall
        openings are split 50/50 with the fold never measured."""
        assert NodeRegion(rect=[0, 0, 0.5, 1]).confidence is RegionConfidence.nominal

    def test_records_the_sidecar_method_verbatim(self):
        region = NodeRegion(
            rect=[0.0, 0.0, 0.5, 1.0],
            method="nominal-even-split",
            note="Even left/right split of the opening; the fold was not measured.",
        )
        assert region.method == "nominal-even-split"
        assert region.confidence is RegionConfidence.nominal

    def test_measured_and_user_are_distinguishable(self):
        measured = NodeRegion(rect=[0, 0, 0.5, 1], confidence=RegionConfidence.measured)
        user = NodeRegion(rect=[0, 0, 0.5, 1], confidence=RegionConfidence.user)
        assert measured.confidence is not user.confidence


class TestSourceAnchor:
    def test_rendition_id_is_carried(self):
        """The field whose absence was the original defect."""
        anchor = SourceAnchor(
            document_id="doc-1", rendition_id="ren-enhanced", rect=[0.1, 0.1, 0.2, 0.2]
        )
        assert anchor.rendition_id == "ren-enhanced"

    def test_rendition_id_defaults_to_none_meaning_the_node_frame(self):
        assert SourceAnchor(document_id="doc-1").rendition_id is None

    def test_refines_nests_a_span_inside_a_region(self):
        """W3C ``refinedBy``: a transcript span WITHIN a box WITHIN a page —
        the relationship the export currently flattens into an 'any of these'
        list."""
        anchor = SourceAnchor(
            document_id="doc-1",
            char_start=10,
            char_end=25,
            granularity="word",
            refines=SourceAnchor(
                document_id="doc-1", rect=[0.1, 0.2, 0.3, 0.05], granularity="line"
            ),
        )
        assert anchor.refines is not None
        assert anchor.refines.granularity == "line"
        assert anchor.granularity == "word"

    def test_text_only_anchor_needs_no_rect(self):
        anchor = SourceAnchor(document_id="doc-1", char_start=0, char_end=5)
        assert anchor.rect is None

    def test_inverted_char_span_rejected(self):
        with pytest.raises(ValidationError):
            SourceAnchor(document_id="doc-1", char_start=10, char_end=5)

    def test_equal_char_offsets_allowed_as_a_caret(self):
        anchor = SourceAnchor(document_id="doc-1", char_start=7, char_end=7)
        assert anchor.char_start == anchor.char_end


class TestPolygon:
    def test_polygon_accepted_for_non_rectangular_regions(self):
        """Marginalia down a slanted margin, a footnote wrapping a column —
        regions a rectangle cannot express."""
        anchor = SourceAnchor(
            document_id="doc-1",
            polygon=[[0.0, 0.0], [0.5, 0.05], [0.5, 0.9], [0.0, 0.85]],
            granularity="marginalia",
        )
        assert len(anchor.polygon) == 4

    def test_degenerate_polygon_rejected(self):
        with pytest.raises(ValidationError):
            SourceAnchor(document_id="doc-1", polygon=[[0, 0], [1, 1]])

    def test_out_of_range_polygon_point_rejected(self):
        with pytest.raises(ValidationError):
            SourceAnchor(document_id="doc-1", polygon=[[0, 0], [1, 0], [2, 2]])

    def test_malformed_polygon_point_rejected(self):
        with pytest.raises(ValidationError):
            SourceAnchor(document_id="doc-1", polygon=[[0, 0], [1, 0], [1, 1, 1]])


class TestRendition:
    def test_pure_resample_has_no_transform(self):
        """The common case and the rule's default: same frame as its node, so
        an anchor is portable across renditions with no maths at all."""
        rendition = Rendition(document_id="doc-1", role="enhanced", path="/x.jpg")
        assert rendition.transform is None

    def test_cropped_rendition_records_its_transform(self):
        """The honest exception: Marshall's `enhanced` really is
        cropped/deskewed relative to the original, so it says so rather than
        silently moving every box."""
        rendition = Rendition(
            document_id="doc-1",
            role="enhanced",
            path="/x.jpg",
            transform=NodeRegion(
                rect=[0.02, 0.01, 0.95, 0.98],
                confidence=RegionConfidence.measured,
                method="deskew-crop",
            ),
        )
        assert rendition.transform is not None
        assert rendition.transform.method == "deskew-crop"

    def test_role_is_free_form_so_staging_can_add_one(self):
        """Same reason ``Annotation.anchor_kind`` is a string: the pipeline
        must not wait for a model bump to name a new rendition role."""
        assert Rendition(document_id="d", role="hocr_overlay", path="/x").role == "hocr_overlay"

    def test_materialized_defaults_true_so_absence_is_explicit(self):
        rendition = Rendition(document_id="d", role="original", path="/x", storage="staged")
        assert rendition.materialized is True
        assert Rendition(
            document_id="d", role="original", path="/x", materialized=False
        ).materialized is False


class TestDocumentRegion:
    def test_document_carries_region_in_parent(self):
        doc = Document(
            name="left page",
            region_in_parent=NodeRegion(rect=[0.0, 0.0, 0.5, 1.0], method="nominal-even-split"),
        )
        assert doc.region_in_parent.rect == [0.0, 0.0, 0.5, 1.0]

    def test_region_is_optional_for_a_node_that_is_not_a_region(self):
        assert Document(name="a folder").region_in_parent is None

    def test_legacy_bbox_still_decodes(self):
        """Kept readable so pre-rename rows load; `_ensure_table` would also
        ADD COLUMN it back onto an older library regardless."""
        doc = Document(name="old", bbox=(0, 0, 100, 200))
        assert doc.bbox == (0, 0, 100, 200)
