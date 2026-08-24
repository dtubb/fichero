"""`KnowledgeClaim.source_bbox` -> `source_anchor` (2026-08-22).

The old field was four bare numbers documented as "[x, y, width, height] in
PDF page coordinates" — PIXELS — while `Annotation.bbox` next door held
NORMALIZED fractions. Two fields spelled the same way, in two different
coordinate spaces, neither declaring which. `SourceAnchor` makes the space and
the rendition explicit, so a rect can no longer be read against the wrong frame.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.claim.claims import (
    ClaimPatchRequest,
    _apply_claim_patch,
)
from fichero_server.models.anchors import AnchorSpace, SourceAnchor
from fichero_server.models.knowledge import KnowledgeClaim


def _claim(**kwargs) -> KnowledgeClaim:
    return KnowledgeClaim(text="t", source_document_id="doc-1", **kwargs)


class TestTheFieldIsGone:
    def test_the_old_field_no_longer_exists(self):
        assert "source_bbox" not in KnowledgeClaim.model_fields

    def test_a_claim_can_carry_an_anchor(self):
        anchor = SourceAnchor(document_id="doc-1", rect=[0.1, 0.2, 0.3, 0.4])
        assert _claim(source_anchor=anchor).source_anchor.rect == [0.1, 0.2, 0.3, 0.4]

    def test_an_anchorless_claim_is_still_valid(self):
        """Most claims are text-only; the anchor is genuinely optional and its
        absence must never be forced into a placeholder rect."""
        assert _claim().source_anchor is None


class TestTheSpaceIsNowDeclared:
    def test_a_pymupdf_result_records_pixels_honestly(self):
        """`page.search(excerpt)` returns PDF page coordinates. Previously that
        landed in the same field shape as a normalized rect and nothing
        distinguished them."""
        anchor = SourceAnchor(
            document_id="doc-1", rect=[72.0, 144.0, 200.0, 24.0],
            space=AnchorSpace.pixel,
        )
        claim = _claim(source_anchor=anchor)
        assert claim.source_anchor.space is AnchorSpace.pixel
        assert claim.source_anchor.rect[2] == 200.0

    def test_a_normalized_anchor_is_distinguishable_from_a_pixel_one(self):
        """The whole point: [0, 0, 1, 1] means the WHOLE page normalized, and a
        1x1 pixel box otherwise. Only `space` separates them."""
        whole = SourceAnchor(document_id="d", rect=[0, 0, 1, 1])
        tiny = SourceAnchor(document_id="d", rect=[0, 0, 1, 1], space=AnchorSpace.pixel)
        assert whole.space is not tiny.space


class TestPatchApplication:
    """A PATCH arrives as JSON, so the value threaded to the claim is a DICT."""

    def test_a_patched_anchor_is_readable_BEFORE_any_reload(self):
        """The regression guard. `model_dump()` flattens nested models, so
        assigning the dumped value left the claim holding a dict and
        `claim.source_anchor.rect` raised AttributeError until the row was
        re-read. A DB round-trip test cannot see this — serialization
        re-validates on the way back in."""
        claim = _claim()
        request = ClaimPatchRequest.model_validate(
            {"source_anchor": {"document_id": "doc-1", "rect": [0, 0, 0.5, 1]}}
        )
        data = request.model_dump(exclude_unset=True)

        _apply_claim_patch(claim, data, typed={k: getattr(request, k) for k in data})

        assert isinstance(claim.source_anchor, SourceAnchor)
        assert claim.source_anchor.rect == [0.0, 0.0, 0.5, 1.0]

    def test_derived_keys_still_apply(self):
        """`svo_verb`/`predicate_canonical` are derived INSIDE the patch and are
        not request attributes, so they must fall through to the plain value
        rather than being dropped by the typed overlay."""
        claim = _claim()
        request = ClaimPatchRequest.model_validate({"predicate_verb": "wrote"})
        data = request.model_dump(exclude_unset=True)

        _apply_claim_patch(claim, data, typed={k: getattr(request, k) for k in data})

        assert claim.predicate_verb == "wrote"
        assert claim.predicate_canonical is not None

    def test_the_patch_still_works_without_the_typed_overlay(self):
        """`typed` is optional; omitting it must not break scalar patches."""
        claim = _claim()
        _apply_claim_patch(claim, {"source_page_label": "12"})
        assert claim.source_page_label == "12"


class TestRefusals:
    def test_a_malformed_rect_is_rejected_not_coerced(self):
        """A claim pointing at the wrong place is worse than one pointing
        nowhere."""
        with pytest.raises(ValueError):
            SourceAnchor(document_id="d", rect=[0.1, 0.2])

    def test_a_normalized_rect_outside_the_page_is_rejected(self):
        with pytest.raises(ValueError):
            SourceAnchor(document_id="d", rect=[0.5, 0.0, 0.9, 1.0])
