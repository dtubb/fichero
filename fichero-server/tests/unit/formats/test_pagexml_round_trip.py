"""The PAGE XML round trip (#4944, `source.format.round-trip-pagexml`).

**The round trip subtracts exactly what the loss report names.** A writer that drops
something silently fails here; a writer that drops something and SAYS SO passes.
That makes honesty the acceptance criterion rather than completeness, which is the
only way this work is finishable — no format carries everything.

The trap this file is written against: **a round trip passes if both directions
share one mistake.** A writer that drops `direction` and a reader that supplies a
default agree with each other perfectly. So every assertion below is against the
MODEL's own values — the page built in the test — and never against what the other
end of our code produced.
"""

from __future__ import annotations

import pytest

from fichero_server.formats import round_trip, write_page
from fichero_server.formats.harness import PageOrder, PageSegment, SourcePage

pytestmark = pytest.mark.source_model


def _page() -> SourcePage:
    """A page that exercises every slice: two regions right-to-left, lines with
    baselines and polygons, language and script per segment, and a named order."""
    return SourcePage(
        producer="Fichero",
        image_name="folio_12r.jpg",
        image_size=(1000, 2000),
        segments=[
            PageSegment(
                kind="region", ref="r1", language="Arabic", script="Arab", direction="rtl",
                polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.2], [0.1, 0.2]],
            ),
            PageSegment(
                kind="line", ref="l1", parent_ref="r1", language="Arabic", script="Arab",
                direction="rtl",
                polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.15], [0.1, 0.15]],
                baseline=[[0.1, 0.145], [0.9, 0.145]],
                readings=[("transcription", "بسم الله الرحمن الرحيم")],
            ),
            PageSegment(
                kind="region", ref="r2", language="Spanish", script="Latn", direction="ltr",
                polygon=[[0.1, 0.3], [0.9, 0.3], [0.9, 0.4], [0.1, 0.4]],
            ),
        ],
        orders=[PageOrder(name="as-written", refs=["r1", "r2"])],
    )


class TestTheRoundTripHolds:
    def test_every_segment_comes_back_with_its_granularity_and_nesting(self):
        original = _page()

        returned, _report = round_trip("pagexml", original)

        assert [s.kind for s in returned.segments] == [s.kind for s in original.segments]
        by_ref = {s.ref: s for s in returned.segments}
        assert by_ref["l1"].parent_ref == "r1"

    def test_language_script_and_direction_survive_both_ways(self):
        """Asserted against the ORIGINAL's values, not against what our own writer
        emitted — a writer dropping `direction` and a reader defaulting it would
        agree with each other and tell us nothing."""
        original = _page()

        returned, report = round_trip("pagexml", original)

        by_ref = {s.ref: s for s in returned.segments}
        for segment in original.segments:
            came_back = by_ref[segment.ref]
            assert came_back.language == segment.language
            assert came_back.script == segment.script
            assert came_back.direction == segment.direction
        assert "direction" not in report.lost

    def test_the_text_survives_byte_for_byte_including_right_to_left(self):
        original = _page()

        returned, _report = round_trip("pagexml", original)

        by_ref = {s.ref: s for s in returned.segments}
        assert by_ref["l1"].readings == [("transcription", "بسم الله الرحمن الرحيم")]

    def test_the_named_order_survives_as_a_sequence(self):
        """Slice 10 is this element. The SEQUENCE is what must hold — positions are
        spacing and no format carries them."""
        original = _page()

        returned, _report = round_trip("pagexml", original)

        assert [order.refs for order in returned.orders] == [["r1", "r2"]]

    def test_coordinates_survive_to_the_precision_the_format_declares(self):
        """PAGE XML writes INTEGER PIXELS, so equality is the wrong assertion: a
        normalised 0.3333 on a 1000px page comes back 0.333. Half a pixel is the
        honest tolerance, and asserting equality would be asserting the format is
        lossless when it is not."""
        original = _page()
        half_a_pixel_x = 0.5 / 1000
        half_a_pixel_y = 0.5 / 2000

        returned, _report = round_trip("pagexml", original)

        by_ref = {s.ref: s for s in returned.segments}
        for segment in original.segments:
            for mine, theirs in zip(segment.polygon, by_ref[segment.ref].polygon):
                assert mine[0] == pytest.approx(theirs[0], abs=half_a_pixel_x)
                assert mine[1] == pytest.approx(theirs[1], abs=half_a_pixel_y)

    def test_the_baseline_survives_which_is_what_kraken_needs(self):
        original = _page()

        returned, _report = round_trip("pagexml", original)

        line = {s.ref: s for s in returned.segments}["l1"]
        assert line.baseline is not None
        assert len(line.baseline) == 2


class TestTheLossesAreDeclaredNotDiscovered:
    def test_several_readings_survive_but_WHICH_ONE_COUNTS_is_reported_lost(self):
        """PAGE XML's `TextEquiv` takes an index, so more than one reading is
        expressible — but a project's CHOICE of which one counts (slice 8) has no
        element. Declared, so the round trip subtracts it rather than a later reader
        discovering it."""
        page = _page()
        page.segments[1].readings = [
            ("transcription", "primera lectura"),
            ("transcription", "segunda lectura"),
        ]

        returned, report = round_trip("pagexml", page)

        line = {s.ref: s for s in returned.segments}["l1"]
        assert len(line.readings) == 2
        assert "which reading counts" in report.lost

    def test_a_direction_fichero_alone_has_is_reported_rather_than_dropped(self):
        """`alternating` (boustrophedon) and `follows-baseline` have no PAGE XML
        attribute. A writer that emitted nothing and said nothing would lose a fact
        about a real inscription silently."""
        page = _page()
        page.segments[0].direction = "alternating"

        _returned, report = round_trip("pagexml", page)

        assert "direction" in report.lost
        assert any("alternating" in loss.why for loss in report.losses)

    def test_orders_beyond_the_first_are_reported(self):
        page = _page()
        page.orders.append(PageOrder(name="the editor's order", refs=["r2", "r1"]))

        returned, report = round_trip("pagexml", page)

        assert len(returned.orders) == 1
        assert "named reading orders" in report.lost

    def test_a_page_with_no_pixel_size_says_the_grid_was_invented(self):
        page = _page()
        page.image_size = None

        _returned, report = round_trip("pagexml", page)

        assert "page size" in report.lost


class TestTheExportIsValidated:
    def test_the_written_bytes_validate_against_the_schema_on_disk(self):
        """`source.format.export-validated`. The schema is vendored
        (`formats/schemas/PROVENANCE.md`), so this is a real check against PRImA's
        own XSD rather than against our idea of it — and `write_page` raises rather
        than returning an invalid file, because a file that exists and does not
        validate is one somebody sends to a colleague."""
        data, _report = write_page("pagexml", _page())

        assert data.startswith(b"<?xml")
        assert b"pagecontent/2019-07-15" in data
