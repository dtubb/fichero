"""IIIF Georeference Annotations on two real Allmaps files (#5125; `maps-and-georeference.md`).

The first test of a format reads a file another tool wrote -- a round trip passes if both
directions share one mistake. So every assertion below is against numbers read off the
vendored files by eye, not against what our own writer produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.formats import (
    InvalidExport,
    PageSegment,
    SourcePage,
    format_for,
    read_page,
    round_trip,
    write_page,
)
from fichero_server.formats.iiif_georef import GCP_KIND, MASK_KIND, MASK_LINK, check

FIXTURES = Path(__file__).parent / "fixtures"
PARIS = FIXTURES / "allmaps_paris_thin_plate_spline.georef.json"
DELFT = FIXTURES / "allmaps_delft_earlier_dialect.georef.json"


def _gcps(page: SourcePage) -> list[PageSegment]:
    return [s for s in page.segments if s.kind == GCP_KIND]


class TestReadingThePublishedDialect:
    def test_it_is_recognised_by_its_bytes(self):
        assert format_for(PARIS.name, PARIS.read_bytes()).name == "iiif-georef"

    def test_the_gcps_are_point_segments_with_both_ends(self):
        """Feature 0: resourceCoords [336, 1742] on a 4708x1860 image, world [2.2860069, 48.860451]."""
        page = read_page("iiif-georef", PARIS.read_bytes())
        gcps = _gcps(page)
        assert len(gcps) == 4
        assert gcps[0].point == pytest.approx([336 / 4708, 1742 / 1860])
        assert gcps[0].world == (2.2860069, 48.860451)

    def test_the_mask_is_an_area_segment_and_the_gcps_name_it(self):
        page = read_page("iiif-georef", PARIS.read_bytes())
        [mask] = [s for s in page.segments if s.kind == MASK_KIND]
        assert mask.polygon[0] == pytest.approx([117 / 4708, 120 / 1860])
        assert len(mask.polygon) == 4
        assert {g.foreign[MASK_LINK] for g in _gcps(page)} == {mask.ref}

    def test_the_transformation_and_the_image_are_the_pages(self):
        page = read_page("iiif-georef", PARIS.read_bytes())
        assert page.transformation == {"type": "thinPlateSpline"}
        assert page.image_size == (4708, 1860)
        assert page.image_name == "https://iiif.archivelab.org/iiif/plangeneraldelex00unse$3"

    def test_it_passes_the_checker_as_published(self):
        assert check(PARIS.read_bytes()) == []


class TestReadingTheEarlierDialect:
    """Allmaps reads it and real annotations use it, so the reader must too."""

    def test_pixel_coords_are_read_and_the_size_comes_from_the_svg(self):
        page = read_page("iiif-georef", DELFT.read_bytes())
        assert page.image_size == (7636, 10474)
        gcps = _gcps(page)
        assert gcps[0].point == pytest.approx([853 / 7636, 8548 / 10474])
        assert gcps[0].world == (4.3582994, 52.0084484)

    def test_its_mask_has_fourteen_points(self):
        page = read_page("iiif-georef", DELFT.read_bytes())
        [mask] = [s for s in page.segments if s.kind == MASK_KIND]
        assert len(mask.polygon) == 14

    def test_the_published_checker_rejects_it_for_the_stated_reasons(self):
        """True of the file, and the reason readers never validate: real files are not all
        in the dialect the text publishes."""
        problems = check(DELFT.read_bytes())
        assert any("georef/1/context.json" in p for p in problems)
        assert any("resourceCoords" in p for p in problems)


class TestWriting:
    @pytest.mark.parametrize("path", [PARIS, DELFT], ids=["published", "earlier"])
    def test_every_real_file_exports_as_the_published_dialect(self, path):
        data, _ = write_page("iiif-georef", read_page("iiif-georef", path.read_bytes()))
        assert check(data) == []
        doc = json.loads(data)
        assert doc["@context"][0] == "http://iiif.io/api/extension/georef/1/context.json"

    @pytest.mark.parametrize("path", [PARIS, DELFT], ids=["published", "earlier"])
    def test_the_round_trip_keeps_gcps_mask_and_transformation(self, path):
        """`source.geo.iiif-georef-round-trip`: pixels are integers in the file, so
        normalised -> pixel -> normalised is exact here."""
        first = read_page("iiif-georef", path.read_bytes())
        again, report = round_trip("iiif-georef", first)
        shape = lambda page: [(s.kind, s.point, s.world, s.polygon) for s in page.segments]  # noqa: E731
        assert shape(again) == shape(first)
        assert again.transformation == first.transformation
        assert again.image_size == first.image_size

    def test_converting_the_earlier_dialect_names_what_it_did_not_write(self):
        _, report = write_page("iiif-georef", read_page("iiif-georef", DELFT.read_bytes()))
        assert "the plain image URL beside its IIIF service" in report.lost

    def test_segments_the_format_cannot_carry_are_reported_not_dropped(self):
        page = read_page("iiif-georef", PARIS.read_bytes())
        page.segments.append(PageSegment(kind="line", rect=[0.1, 0.1, 0.2, 0.05], readings=[("text", "Rue")]))
        _, report = write_page("iiif-georef", page)
        assert "segments other than control points and masks" in report.lost

    def test_two_masks_become_two_annotations_each_with_its_own_gcps(self):
        page = SourcePage(image_size=(1000, 1000), image_name="https://example.org/iiif/sheet")
        for ref, x in (("county", 0.1), ("town", 0.6)):
            page.segments.append(PageSegment(kind=MASK_KIND, ref=ref, polygon=[[x, 0.1], [x + 0.3, 0.1], [x + 0.3, 0.4]]))
            gcp = PageSegment(kind=GCP_KIND, point=[x + 0.1, 0.2], world=(4.0 + x, 52.0))
            gcp.foreign[MASK_LINK] = ref
            page.segments.append(gcp)
        data, _ = write_page("iiif-georef", page)
        doc = json.loads(data)
        assert doc["type"] == "AnnotationPage"
        assert [len(item["body"]["features"]) for item in doc["items"]] == [1, 1]
        again = read_page("iiif-georef", data)
        masks = {s.ref: s for s in again.segments if s.kind == MASK_KIND}
        for gcp in _gcps(again):
            assert gcp.world[0] - 4.0 == pytest.approx(masks[gcp.foreign[MASK_LINK]].polygon[0][0])

    def test_no_pixel_size_is_refused_rather_than_invented(self):
        page = SourcePage(segments=[PageSegment(kind=GCP_KIND, point=[0.5, 0.5], world=(0.0, 0.0))])
        with pytest.raises(ValueError, match="pixel size"):
            write_page("iiif-georef", page)


class TestTheChecker:
    """Each rule quoted in `iiif_georef.py` from the extension text, fired once."""

    @staticmethod
    def _published() -> dict:
        return json.loads(PARIS.read_bytes())

    def _problems(self, doc: dict) -> list[str]:
        return check(json.dumps(doc).encode())

    def test_a_viewbox_is_refused(self):
        doc = self._published()
        doc["target"]["selector"]["value"] = doc["target"]["selector"]["value"].replace("<svg ", '<svg viewBox="0 0 1 1" ')
        assert any("viewBox" in p for p in self._problems(doc))

    def test_an_svg_size_that_is_not_the_resources_is_refused(self):
        doc = self._published()
        doc["target"]["selector"]["value"] = doc["target"]["selector"]["value"].replace('width="4708"', 'width="4000"')
        assert any("must equal the resource" in p for p in self._problems(doc))

    def test_a_non_point_feature_is_refused(self):
        doc = self._published()
        doc["body"]["features"][0]["geometry"] = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        assert any("only Point geometries" in p for p in self._problems(doc))

    def test_the_contexts_in_the_wrong_order_are_refused(self):
        doc = self._published()
        doc["@context"] = list(reversed(doc["@context"]))
        assert any("before the Presentation context" in p for p in self._problems(doc))

    def test_a_wrong_motivation_is_refused(self):
        doc = self._published()
        doc["motivation"] = "painting"
        assert any("motivation" in p for p in self._problems(doc))

    def test_an_invalid_export_is_no_file(self, monkeypatch):
        """`source.format.export-validated` holds for this format too: the harness runs
        the checker on every write."""
        import fichero_server.formats.iiif_georef as module

        page = read_page("iiif-georef", PARIS.read_bytes())
        spec = module.register.__globals__["_REGISTRY"]["iiif-georef"]
        monkeypatch.setitem(
            module.register.__globals__["_REGISTRY"], "iiif-georef",
            type(spec)(**{**spec.__dict__, "check": lambda data: ["forced"]}),
        )
        with pytest.raises(InvalidExport):
            write_page("iiif-georef", page)
