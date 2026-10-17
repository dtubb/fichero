"""A multi-page ALTO file imported on its own brings in every `<Page>` (#5310).

`importer.alto-multi-page-reads-every-page`. WHY: `alto.read` took the first `<Page>`, so the
rest of a newspaper-issue export vanished without a word. Each page now comes in as a child page
carrying only its own lines. If this regresses, page 2 is missing, or its lines sit under page 1.
"""

from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import alto
from fichero_server.models import ContentRepresentation, DocType, Document

NS = "http://www.loc.gov/standards/alto/ns-v4#"


def _page(n: int, words: list[str]) -> str:
    lines = "".join(
        f'<TextLine ID="p{n}l{i}" HPOS="10" VPOS="{10 + 20 * i}" WIDTH="80" HEIGHT="15">'
        f'<String ID="p{n}w{i}" CONTENT="{w}" HPOS="10" VPOS="{10 + 20 * i}" WIDTH="80" HEIGHT="15"/></TextLine>'
        for i, w in enumerate(words)
    )
    return (f'<Page ID="P{n}" WIDTH="100" HEIGHT="100"><PrintSpace><TextBlock ID="p{n}b" HPOS="0" VPOS="0" '
            f'WIDTH="100" HEIGHT="100">{lines}</TextBlock></PrintSpace></Page>')


ISSUE = (f'<?xml version="1.0" encoding="UTF-8"?><alto xmlns="{NS}"><Description>'
         "<MeasurementUnit>pixel</MeasurementUnit></Description><Layout>"
         + _page(1, ["alpha", "beta"]) + _page(2, ["gamma"]) + "</Layout></alto>").encode()


def test_read_pages_gives_each_page_only_its_own_lines():
    pages = alto.read_pages(ISSUE)
    words = [[t for s in p.segments if s.kind == "word" for _k, t in s.readings] for p in pages]
    assert words == [["alpha", "beta"], ["gamma"]]
    assert alto.read(ISSUE).segments == pages[0].segments, "read() stays the first page"


def test_imported_on_its_own_every_page_is_a_page_of_the_document(db, tmp_path: Path):
    path = tmp_path / "issue.alto.xml"
    path.write_bytes(ISSUE)
    ctx = ActionContext(actor="owner", is_bootstrap=True)
    document = db.get(Document, registry.invoke(db, "import.file", {"path": str(path)}, ctx).result["id"])
    pages = sorted(db.query(Document, parent_id=document.id, doc_type=DocType.page), key=lambda d: d.sequence)
    assert [p.sequence for p in pages] == [1, 2]
    got = [sorted(r.content for r in db.query(ContentRepresentation, document_id=p.id)
                       if r.producer_tool != "line-from-its-words") for p in pages]
    assert got == [["alpha", "beta"], ["gamma"]]
