"""Dropping an eScriptorium / Transkribus export folder gives pages WITH their passes (#5132).

Before: every `.xml` became a raw text document beside the images, and the layout and
text never reached the page they describe. The folder here is built from REAL files in
the layouts real exports use:

* an OCR-D page renamed so its stem no longer matches -- paired by the `imageFilename`
  it states (which carries a folder path, `GT-PAGE/...tif`, matched by name);
* a Transkribus page in a `page/` subfolder beside its image, as Transkribus exports;
* eScriptorium's sample, naming `default.png`, which is not there -- UNPAIRED, named, and
  still imported as an ordinary file so nothing is lost;
* an XML that is not a layout format at all -- a text document, as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.importers.interchange_pairing import plan_pairs
from fichero_server.models import Document
from fichero_server.models.segments import Segment, SegmentPass

FORMATS = Path(__file__).resolve().parents[1] / "formats" / "fixtures"


def _image(path: Path, size=(40, 60)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


@pytest.fixture
def export_folder(tmp_path) -> Path:
    folder = tmp_path / "export"
    _image(folder / "aepinus_bekentnis_1548_0020.tif")
    (folder / "renamed_by_someone.xml").write_bytes((FORMATS / "ocrd_gt_aepinus_0020.page.xml").read_bytes())
    _image(folder / "M_Otterskirchen_012_0002.jpg")
    (folder / "page").mkdir()
    (folder / "page" / "M_Otterskirchen_012_0002.xml").write_bytes(
        (FORMATS / "transkribus_regions_only_0002.page.xml").read_bytes()
    )
    (folder / "orphan.page.xml").write_bytes((FORMATS / "escriptorium_export.page.xml").read_bytes())
    (folder / "notes.xml").write_text("<notes><note>not a layout file</note></notes>", encoding="utf-8")
    return folder


class TestThePairing:
    def test_the_stated_image_name_wins_over_the_stem_and_a_subfolder_finds_its_parent(self, export_folder):
        files = [p.resolve() for p in export_folder.rglob("*") if p.is_file()]
        plan = plan_pairs(files)
        pairs = {layout.name: image.name for layout, image in plan.pairs.items()}
        assert pairs == {
            "renamed_by_someone.xml": "aepinus_bekentnis_1548_0020.tif",
            "M_Otterskirchen_012_0002.xml": "M_Otterskirchen_012_0002.jpg",
        }

    def test_a_layout_file_with_no_image_is_unpaired_BY_NAME_and_never_guessed(self, export_folder):
        files = [p.resolve() for p in export_folder.rglob("*") if p.is_file()]
        plan = plan_pairs(files)
        [(layout, why)] = plan.unpaired.items()
        assert layout.name == "orphan.page.xml"
        assert "default.png" in why

    def test_two_images_sharing_a_stem_is_a_refusal_not_a_pick(self, tmp_path):
        _image(tmp_path / "p1.jpg")
        _image(tmp_path / "p1.png")
        page = (FORMATS / "escriptorium_export.page.xml").read_bytes().replace(b"default.png", b"elsewhere.png")
        (tmp_path / "p1.page.xml").write_bytes(page)
        plan = plan_pairs([p for p in tmp_path.iterdir()])
        assert not plan.pairs
        assert "2 images share the stem" in next(iter(plan.unpaired.values()))

    def test_an_xml_that_is_not_layout_is_not_a_candidate(self, export_folder):
        files = [p.resolve() for p in export_folder.rglob("*") if p.is_file()]
        plan = plan_pairs(files)
        assert "notes.xml" not in {p.name for p in [*plan.pairs, *plan.unpaired]}


class TestDroppingTheFolder:
    def test_the_images_become_pages_with_their_passes(self, db, export_folder):
        ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
        result = registry.invoke(db, "import.folder", {"path": str(export_folder)}, ctx).result

        report = result["interchange"]
        assert sorted(report["imported_as_passes"]) == ["M_Otterskirchen_012_0002.xml", "renamed_by_someone.xml"]
        assert list(report["unpaired"]) == ["orphan.page.xml"]
        assert report["not_imported"] == {}

        documents = {d.name: d for d in (db.get(Document, i) for i in result["document_ids"]) if d}
        # The paired layout files are NOT text documents any more ...
        assert "renamed_by_someone.xml" not in documents
        assert "M_Otterskirchen_012_0002.xml" not in documents
        # ... the unpaired one and the plain XML still are, so nothing was lost.
        assert "orphan.page.xml" in documents
        assert "notes.xml" in documents

        for image, layout in (
            ("aepinus_bekentnis_1548_0020.tif", "renamed_by_someone.xml"),
            ("M_Otterskirchen_012_0002.jpg", "M_Otterskirchen_012_0002.xml"),
        ):
            page = documents[image]
            passes = [p for p in db.all(SegmentPass) if p.document_id == page.id]
            assert len(passes) == 1, f"{image} should carry the pass from {layout}"
            segments = [s for s in db.all(Segment) if s.pass_id == passes[0].id]
            assert segments, f"the pass on {image} has no segments"

    def test_dropping_it_again_duplicates_no_pass(self, db, export_folder):
        ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
        registry.invoke(db, "import.folder", {"path": str(export_folder)}, ctx)
        passes_before = len(db.all(SegmentPass))
        registry.invoke(db, "import.folder", {"path": str(export_folder)}, ctx)
        assert len(db.all(SegmentPass)) == passes_before


class TestNothingThatLooksLikeInterchangeIsSilentlyText:
    """The maintainer's Aljamiado folder: 3 of 13 real ALTO files open with a long CHOCOMUFIN
    report comment before the root element. The sniffs looked at the first 2 KB, found
    nothing, and those files were neither paired nor named -- they would have imported as
    plain text with nobody told. Classification is by the ROOT now, however much precedes it,
    and anything whose root marks it as interchange is named if it does not pair."""

    def test_an_alto_file_with_a_long_leading_comment_pairs_with_its_image(self, tmp_path):
        alto = (FORMATS / "escriptorium_export.alto.xml").read_bytes()
        report = b"<!-- CHOCOMUFIN conversion report: " + b"line of report text. " * 2000 + b"-->\n"
        head, sep, rest = alto.partition(b"?>")
        (tmp_path / "page_1.xml").write_bytes(head + sep + b"\n" + report + rest.lstrip())
        assert len(report) > 40_000
        _image(tmp_path / "default.png")
        plan = plan_pairs([p.resolve() for p in tmp_path.iterdir()])
        assert {layout.name: image.name for layout, image in plan.pairs.items()} == {"page_1.xml": "default.png"}

    def test_a_tei_file_in_the_folder_is_named_not_silently_text(self, tmp_path):
        (tmp_path / "edition.xml").write_bytes((FORMATS / "tei_consortium_testtranscr.xml").read_bytes())
        plan = plan_pairs([p.resolve() for p in tmp_path.iterdir()])
        [(layout, why)] = plan.unpaired.items()
        assert layout.name == "edition.xml" and "TEI is an edition" in why

    def test_an_interchange_root_no_reader_claims_is_named(self, tmp_path):
        """A PAGE root in a namespace from a future release: nothing reads it, and a person
        must be told rather than find a text document where their layout should be."""
        (tmp_path / "future.xml").write_text(
            '<PcGtsNext xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2099-01-01"/>',
            encoding="utf-8",
        )
        plan = plan_pairs([p.resolve() for p in tmp_path.iterdir()])
        [(layout, why)] = plan.unpaired.items()
        assert "no reader here classifies it" in why and "PcGtsNext" in why

    def test_an_ordinary_xml_is_still_not_named(self, tmp_path):
        (tmp_path / "notes.xml").write_text("<!-- x -->\n<notes/>", encoding="utf-8")
        plan = plan_pairs([p.resolve() for p in tmp_path.iterdir()])
        assert not plan.pairs and not plan.unpaired
