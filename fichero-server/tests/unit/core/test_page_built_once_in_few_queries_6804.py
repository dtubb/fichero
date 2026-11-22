"""A page's export reads the library in a number of queries that does not grow with its lines (#6804:
`source.format.export-cost`).

WHY: building the page (`page_export.page_from_library`) looked up readings, counting and editorial facts one
segment at a time, so a 150-line page cost about 0.7 s a format. Counted here as calls to the database's
read methods while the page is exported through `export_page`, on a page of 3 lines and on one of 40 lines
imported from PAGE XML (`format.import`).
"""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.page_export import export_page

pytestmark = pytest.mark.source_model

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
READS = ("get", "query", "query_in", "all")


def _page_xml(lines: int) -> str:
    rows = "".join(
        f'<TextLine id="l{i}" custom="readingOrder {{index:{i};}}">'
        f'<Coords points="20,{20 + i * 12} 580,{20 + i * 12} 580,{30 + i * 12} 20,{30 + i * 12}"/>'
        f'<Baseline points="20,{28 + i * 12} 580,{28 + i * 12}"/>'
        f"<TextEquiv><Unicode>linea {i}</Unicode></TextEquiv></TextLine>"
        for i in range(lines)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15">'
        "<Metadata><Creator>test</Creator><Created>2026-10-08T00:00:00</Created>"
        "<LastChange>2026-10-08T00:00:00</LastChange></Metadata>"
        '<Page imageFilename="p.jpg" imageWidth="600" imageHeight="600">'
        '<TextRegion id="r0" custom="readingOrder {index:0;}"><Coords points="10,10 590,10 590,590 10,590"/>'
        + rows + "</TextRegion></Page></PcGts>"
    )


def _page_of(db, tmp_path, lines: int) -> str:
    photo = tmp_path / f"p{lines}.jpg"
    Image.new("RGB", (600, 600), (220, 220, 210)).save(photo)
    doc = Document(name=f"p{lines}.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   status=Status.completed)
    db.save(doc)
    xml = tmp_path / f"p{lines}.xml"
    xml.write_text(_page_xml(lines), encoding="utf-8")
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(xml)}, BOOT)
    return doc.id


def _reads(db, monkeypatch, doc_id: str, fmt: str) -> int:
    calls: list[str] = []
    for name in READS:
        original = getattr(Database, name)

        def counted(self, *args, _original=original, _name=name, **kwargs):
            calls.append(_name)
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(Database, name, counted)
    export_page(db, doc_id, fmt)
    return len(calls)


@pytest.mark.parametrize("fmt", ["pagexml", "alto", "tei"])
def test_the_reads_for_a_page_do_not_grow_with_its_lines(db, tmp_path, monkeypatch, fmt):
    small, large = _page_of(db, tmp_path, 3), _page_of(db, tmp_path, 40)
    export_page(db, small, fmt)  # the first export of a format in a process reads what later ones remember
    few, many = _reads(db, monkeypatch, small, fmt), _reads(db, monkeypatch, large, fmt)
    assert many == few, (few, many)
