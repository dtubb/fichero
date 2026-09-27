"""The interchange harness itself (#4943).

The harness is where `source.format.one-model-one-harness` is either true or a
slogan: validation, the loss report and the round trip live here, so the fifth
format cannot forget them because no format implements them.
"""

from __future__ import annotations

import pytest

from fichero_server.formats import (
    FormatCannotRead,
    FormatSpec,
    LossReport,
    SourcePage,
    UnknownFormat,
    format_for,
    format_named,
    known_formats,
    read_page,
    register,
    validate,
    write_page,
)
from fichero_server.formats.harness import PageSegment

pytestmark = pytest.mark.source_model


class TestTheRegistryIsData:
    def test_the_shipped_formats_are_registered_by_importing_the_package(self):
        """`source.format.first-four` is DATA, not a branch: a caller that had to
        import each format first would be a caller that can forget one."""
        names = {spec.name for spec in known_formats()}

        assert "pagexml" in names

    def test_an_unknown_name_says_what_there_is(self):
        with pytest.raises(UnknownFormat) as raised:
            format_named("page-xml")
        assert "pagexml" in str(raised.value)

    def test_a_format_that_only_reads_refuses_to_write_by_name(self):
        register(FormatSpec(name="_test_readonly", extensions=(".zzz",), read=lambda data: SourcePage()))
        try:
            with pytest.raises(Exception) as raised:
                write_page("_test_readonly", SourcePage())
            assert "_test_readonly" in str(raised.value)
        finally:
            from fichero_server.formats import _REGISTRY

            _REGISTRY.pop("_test_readonly", None)

    def test_a_format_that_only_writes_refuses_to_read_by_name(self):
        register(
            FormatSpec(
                name="_test_writeonly", extensions=(".zzz",),
                write=lambda page, report: b"", schema=None,
            )
        )
        try:
            with pytest.raises(FormatCannotRead):
                read_page("_test_writeonly", b"")
        finally:
            from fichero_server.formats import _REGISTRY

            _REGISTRY.pop("_test_writeonly", None)


class TestValidationNeverPassesVacuously:
    """THE `[]`-MEANS-TWO-THINGS HAZARD, inside the harness itself.

    A format with no schema and a format whose schema is MISSING are opposite
    facts: the first cannot be validated by nature (YOLO labels are lines of
    numbers), the second is a broken install. Without the split, a missing schema
    file would report every export as valid — validation passing vacuously, which
    is the shape this programme has spent a day removing.
    """

    def test_a_format_with_no_schema_has_nothing_to_report(self):
        spec = FormatSpec(name="_no_schema", extensions=(".txt",), schema=None)

        assert validate(spec, b"anything at all") == []

    def test_a_format_whose_schema_is_missing_RAISES_rather_than_passing(self):
        spec = FormatSpec(
            name="_missing_schema", extensions=(".xml",), schema="not-installed.xsd"
        )

        with pytest.raises(FileNotFoundError) as raised:
            validate(spec, b"<x/>")
        assert "broken build" in str(raised.value)

    def test_pagexml_names_its_schema_so_a_missing_one_is_loud(self):
        """PAGE XML names its XSD even before the file is vendored, so an export
        attempt fails with "the schema is not installed" rather than quietly
        claiming validity. Conspicuously absent beats quietly optional."""
        spec = format_named("pagexml")

        assert spec.schema == "pagecontent-2019-07-15.xsd"
        assert spec.schema is not None


class TestTheLossReport:
    def test_it_merges_by_what_so_a_writer_can_call_it_per_segment(self):
        report = LossReport(format="pagexml")

        for _ in range(400):
            report.note("direction", 1, "no element for it")

        assert len(report.losses) == 1
        assert report.losses[0].count == 400

    def test_two_different_reasons_for_one_thing_stay_apart(self):
        """A count is not the whole story: "no element" and "the value is ours
        alone" are different explanations, and merging them would produce a report
        that cannot be acted on."""
        report = LossReport(format="pagexml")
        report.note("direction", 1, "no element for it")
        report.note("direction", 2, "the value is Fichero's own")

        assert len(report.losses) == 2
        assert {loss.count for loss in report.losses} == {1, 2}

    def test_the_lost_set_is_what_a_round_trip_subtracts(self):
        report = LossReport(format="pagexml")
        report.note("which reading counts", 1, "no element")

        assert report.lost == {"which reading counts"}

    def test_an_export_that_lost_nothing_says_so_rather_than_nothing(self):
        report = LossReport(format="pagexml")

        assert report.as_dict() == {"format": "pagexml", "losses": []}


class TestRecognisingAFile:
    def test_the_bytes_decide_between_formats_sharing_an_extension(self):
        pagexml = b'<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"/>'

        assert format_for("x.xml", pagexml).name == "pagexml"

    def test_an_unknown_file_is_not_guessed(self):
        assert format_for("x.unknownext", b"not anything we know") is None


class TestWritersCannotReachTheDatabase:
    def test_the_page_a_writer_sees_holds_no_row_and_no_id_of_ours(self):
        """The architectural claim, asserted rather than trusted: a reader produces
        and a writer consumes ONE flat shape, so no format can learn a second way to
        write a segment, and a writer cannot reach a column nobody mapped."""
        segment = PageSegment(kind="line")

        assert not hasattr(segment, "pass_id")
        assert not hasattr(segment, "document_id")
        assert not hasattr(segment, "id")
        # `ref` is the FILE's own id, used to resolve the file's reading order.
        assert segment.ref is None


class TestAReaderAndItsWriterAgreeOnTheKinds:
    """A kind a reader can produce must have an element its writer can emit.

    Found 2026-09-26 by a real file: PAGE XML's reader understood `GraphicRegion`
    and its writer did not, so the region was read and then **declared lost** —
    a loss report for something the format expresses perfectly well. That is worse
    than a plain bug: it is honest data destruction, dressed as transparency. The
    loss report is for what a FORMAT cannot carry, never for what a writer has not
    got round to.
    """

    def test_pagexml_can_write_every_kind_it_can_read(self):
        from fichero_server.formats.pagexml import ELEMENT_KINDS, KIND_ELEMENTS

        readable = set(ELEMENT_KINDS.values())
        writable = set(KIND_ELEMENTS)

        assert readable <= writable, (
            "these kinds can be read and not written, so they would be reported as "
            f"losses the format could actually carry: {sorted(readable - writable)}"
        )

    def test_alto_can_write_every_kind_it_can_read_or_says_why_not(self):
        """ALTO genuinely has fewer granularities than the model — there is no glyph
        element in the shape we use — so this asserts the honest version: any kind
        ALTO can read is writable, and a kind it cannot write is one it also cannot
        read."""
        from fichero_server.formats.alto import ELEMENT_KINDS, KIND_ELEMENTS

        readable = set(ELEMENT_KINDS.values())
        writable = set(KIND_ELEMENTS)

        assert readable <= writable, sorted(readable - writable)
