"""A PAGE import saves each line's abbreviations opened, as its own reading at level `expanded` (#5651), tested to
the spec: `source.reading.abbreviation-markup-parsed` (docs/contributor_manual/specs/source/readings-and-apparatus.md).

WHY: the corpus's markup (`dha$.dicha`) and PAGE's `custom` abbrev tags were read only when names were looked
for; the line itself held no expanded reading, so the Reader could not show one and every reader of the text had
to re-parse the markup.
"""

from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Status

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)

CUSTOM = """<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">
  <Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">
    <TextRegion id="r1"><Coords points="10,10 990,10 990,200 10,200"/>
      <TextLine id="l1" custom="readingOrder {index:0;} abbrev {offset:4; length:3; expansion:dicha;}">
        <Coords points="20,20 980,20 980,80 20,80"/><Baseline points="20,75 980,75"/>
        <TextEquiv><Unicode>que dha Ana</Unicode></TextEquiv>
      </TextLine>
      <TextLine id="l2" custom="readingOrder {index:1;}">
        <Coords points="20,100 980,100 980,160 20,160"/><Baseline points="20,155 980,155"/>
        <TextEquiv><Unicode>sin abreviatura</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
"""


def _imported(db, tmp_path, source: Path) -> Document:
    doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(tmp_path / "p.jpg"),
                   status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(source)}, PERSON)
    return db.get(Document, doc.id)


def _expanded(db, doc_id) -> dict[str, ContentRepresentation]:
    return {r.segment_id: r for r in db.query(ContentRepresentation, document_id=doc_id) if r.level == "expanded"}


def test_inline_markup_becomes_each_lines_expanded_reading(db, tmp_path):
    doc = _imported(db, tmp_path, CORPUS)
    opened = _expanded(db, doc.id)
    assert opened, "no line was given its expanded reading"
    assert any("la dicha Anna Maria" in r.content for r in opened.values())
    assert all("$" not in r.content for r in opened.values())
    written = {r.id: r for r in db.query(ContentRepresentation, document_id=doc.id) if r.level is None}
    assert all(written[r.derived_from_representation_id].segment_id == r.segment_id for r in opened.values())
    assert "dha$.dicha" in doc.page_content  # the page's text stays the file's: expanded counts beside it


def test_page_custom_abbrev_tags_open_the_line_and_a_plain_line_gets_none(db, tmp_path):
    source = tmp_path / "custom.page.xml"
    source.write_text(CUSTOM, encoding="utf-8")
    doc = _imported(db, tmp_path, source)
    assert [r.content for r in _expanded(db, doc.id).values()] == ["que dicha Ana"]
