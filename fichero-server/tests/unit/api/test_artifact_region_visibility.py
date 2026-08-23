"""Clicking a Detect Regions artifact should show something.

Daniel: clicking one in the artifact list "just selects it — nothing shows the
regions found". The engine half of that is small and specific: geometry rides
only on the single-artifact GET (#4309), because a page's word boxes run to
hundreds of records and list endpoints stay lean. So the list carried NO way
to know an artifact had regions at all, let alone how many.

A count cannot be derived from a null geometry — and null is exactly what a
list response carries.
"""

from __future__ import annotations

from fichero_server.api.routes.document.artifacts import _artifact_response
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact


def _artifact(boxes=2, rendition_id=None) -> Artifact:
    return Artifact(
        document_id="doc-1",
        artifact_type="regions",
        content="text",
        version=1,
        reviewed=False,
        ocr_geometry=OCRGeometryResult(
            provider="apple",
            rendition_id=rendition_id,
            boxes=[
                # Stacked within the page: `0.1 * i` runs off the bottom once
                # i reaches 10, and validate_rect rightly refuses it.
                OCRGeometryBox(
                    text=f"w{i}", bbox=[0.1, i / (boxes + 1), 0.2, 0.02]
                )
                for i in range(boxes)
            ],
        ),
    )


class TestTheListCanSayHowMany:
    def test_the_count_survives_the_lean_list_response(self):
        """The whole point: geometry is stripped, the count is not."""
        response = _artifact_response(_artifact(boxes=12), include_geometry=False)

        assert response.ocr_geometry is None
        assert response.region_count == 12

    def test_the_count_is_also_right_on_the_full_response(self):
        response = _artifact_response(_artifact(boxes=12), include_geometry=True)

        assert response.ocr_geometry is not None
        assert response.region_count == 12

    def test_an_artifact_with_no_geometry_reports_zero(self):
        plain = Artifact(
            document_id="doc-1", artifact_type="transcription",
            content="text", version=1, reviewed=False,
        )
        assert _artifact_response(plain).region_count == 0

    def test_an_empty_box_set_reports_zero_not_absent(self):
        """A regions run that found nothing is a real outcome and must be
        distinguishable from a run that never happened — both show 0 here, but
        the artifact EXISTS, which is the distinction the list can draw."""
        empty = Artifact(
            document_id="doc-1", artifact_type="regions", version=1, reviewed=False,
            ocr_geometry=OCRGeometryResult(provider="apple", boxes=[]),
        )
        assert _artifact_response(empty).region_count == 0


class TestTheListCanSayWHICHPicture:
    """Per the frame contract: boxes measured on a crop must not be drawn on
    the page. The client needs that from the LIST, before it fetches anything."""

    def test_the_frame_rides_on_the_lean_response(self):
        response = _artifact_response(
            _artifact(rendition_id="rend-crop"), include_geometry=False
        )
        assert response.geometry_rendition_id == "rend-crop"

    def test_the_documents_own_frame_is_None(self):
        assert _artifact_response(_artifact()).geometry_rendition_id is None

    def test_it_mirrors_the_geometry_when_geometry_is_present(self):
        response = _artifact_response(
            _artifact(rendition_id="rend-crop"), include_geometry=True
        )
        assert response.geometry_rendition_id == response.ocr_geometry.rendition_id
