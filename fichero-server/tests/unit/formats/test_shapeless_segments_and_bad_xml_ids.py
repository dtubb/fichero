"""The two defect classes the real corpus found (#5130), pinned by what they are.

`test_real_corpus.py` proves the three files now work. These say WHY, so the fixes are
not simplified away: a worked-out shape must not come back as one somebody drew, and the
tolerance for a bad `xml:id` must stay exactly that narrow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from fichero_server.formats import PageSegment, SourcePage, read_page, write_page
from fichero_server.formats.pagexml import DERIVED_COORDS_CUSTOM
from fichero_server.formats.validation import parse

CORPUS = Path(__file__).parent / "fixtures" / "corpus"


class TestASegmentWithNoShape:
    """PAGE 2019 requires `Coords`. Calfa's lines have `<Coords points=""/>` and a baseline;
    eScriptorium's `eSc_dummyblock_` region has no `Coords` at all."""

    def _page(self) -> SourcePage:
        return SourcePage(
            image_size=(1000, 1000),
            segments=[
                PageSegment(kind="region", ref="r1"),
                PageSegment(kind="line", ref="l1", parent_ref="r1",
                            baseline=[[0.1, 0.2], [0.5, 0.2]], readings=[("transcription", "a")]),
                PageSegment(kind="line", ref="l2", parent_ref="r1",
                            polygon=[[0.1, 0.3], [0.6, 0.3], [0.6, 0.35], [0.1, 0.35]],
                            readings=[("transcription", "b")]),
            ],
        )

    def test_the_export_validates_with_worked_out_coords_and_says_so(self):
        data, report = write_page("pagexml", self._page())  # write_page validates
        assert "shapes worked out for segments that had none" in report.lost
        assert data.count(DERIVED_COORDS_CUSTOM.encode()) == 2  # the region and line l1

    def test_the_region_takes_its_childrens_bounds_and_the_line_its_baselines(self):
        data, _ = write_page("pagexml", self._page())
        root = etree.fromstring(data)
        ns = {"p": root.nsmap[None]}
        region = root.find(".//p:TextRegion", ns).find("p:Coords", ns).get("points")
        line = root.find(".//p:TextLine[@id='l1']", ns).find("p:Coords", ns).get("points")
        assert region == "100,200 600,200 600,350 100,350"
        assert line == "100,200 500,200 500,200 100,200"

    def test_a_re_import_gives_the_segments_back_WITHOUT_the_invented_shape(self):
        """The shape was ours, not the source's. Read back as drawn, it would be a box
        nobody drew, on a page a scholar is counting."""
        data, _ = write_page("pagexml", self._page())
        back = {s.ref: s for s in read_page("pagexml", data).segments}
        assert back["r1"].polygon is None and back["r1"].rect is None
        assert back["l1"].polygon is None and back["l1"].rect is None
        assert back["l2"].polygon is not None
        assert "custom" not in back["r1"].foreign

    def test_the_sources_own_custom_is_kept_beside_the_marker(self):
        page = self._page()
        page.segments[0].foreign["custom"] = "structure {type:DefaultLine;}"
        data, _ = write_page("pagexml", page)
        back = {s.ref: s for s in read_page("pagexml", data).segments}
        assert back["r1"].foreign["custom"] == "structure {type:DefaultLine;}"
        assert back["r1"].polygon is None


class TestAnXmlIdThatIsNotAnNcname:
    """Transkribus's TEI writes `<pb xml:id="0001_100_003_011_445.png">`. libxml2 refuses the
    whole file for it. The tolerance is for THAT error alone."""

    def test_the_value_is_kept_verbatim(self):
        root = parse(b'<a xml:id="0001_x.png"/>')
        assert root.get("{http://www.w3.org/XML/1998/namespace}id") == "0001_x.png"

    def test_any_other_error_still_refuses_the_file(self):
        """Recovery repairs silently; accepting it for anything else would import a broken
        file as if it were whole."""
        with pytest.raises(etree.XMLSyntaxError):
            parse(b"<a><b></a>")

    def test_a_bad_id_does_not_excuse_a_second_real_error(self):
        with pytest.raises(etree.XMLSyntaxError):
            parse(b'<a xml:id="1x"><b></a>')

    def test_the_transkribus_tei_file_reads_all_of_its_pages(self):
        from fichero_server.formats.tei import read_pages

        pages = read_pages((CORPUS / "transkribus_tibetan-layout_pagantibet-corr1.tei.xml").read_bytes())
        assert len(pages) == 26
