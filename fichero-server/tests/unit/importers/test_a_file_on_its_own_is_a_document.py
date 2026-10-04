"""A TEI, PAGE or ALTO file imported on its own is one document holding every page (#5143).

`source.format.file-on-its-own-is-a-document`, ruled 2026-10-01. WHY: File › Import of the Digital
Genji chapter (24 `<pb>` pages) or the DTA Luther fables (8) made one text document of the raw XML:
no page, no pass, and the letter counts came in at page 1's (485 of 11,240; 752 of 15,051) where
anything did. The ruling: every page of the file comes in, as a page of one document, in the file's
order, and a page whose image is not there still comes in -- as a page without an image, named in
the report with what it points at so its scan can be put with it later. If this regresses, a page
of somebody's edition vanishes, or arrives as raw XML nobody can read as text.

The expected side is the TEI reader's own pages (the reader is pinned against plain lxml in
`tests/unit/formats/test_real_files_lose_no_text.py`): page for page, the letters each library page
holds equal the letters the reader found on that page of the file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import tei
from fichero_server.models import ContentRepresentation, DocType, Document
from fichero_server.models.segments import Segment, SegmentPass

CORPUS = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus"
GENJI = CORPUS / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml"
LUTHER = CORPUS / "dta_german_luther-fabeln.tei.xml"
ALTO = CORPUS / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"
PAGE = CORPUS / "escriptorium_syriac_onb-syr1-0001.page.xml"


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def _letters_on(db, page: Document, words: bool = False) -> int:
    """The letters of the page's imported pass: the first reading of each segment that is not a word
    (`words`: of every segment -- ALTO holds its text on words). A line's reading joined from its
    words (#5433, `source.reading.line-from-its-words`) is the same letters again, so it is not
    counted: this counts what the FILE gave."""
    passes = [p for p in db.query(SegmentPass, document_id=page.id) if p.deleted_at is None]
    assert len(passes) == 1, f"{page.name}: one imported pass, got {len(passes)}"
    segments = {s.id: s for s in db.query(Segment, pass_id=passes[0].id)}
    first: dict[str, str] = {}
    for reading in db.query(ContentRepresentation, document_id=page.id):
        if reading.producer_tool == "line-from-its-words":
            continue
        if reading.segment_id in segments and (words or segments[reading.segment_id].kind != "word"):
            first.setdefault(reading.segment_id, reading.content or "")
    return sum(_letters(t) for t in first.values())


def _pages(db, document: Document) -> list[Document]:
    return sorted(db.query(Document, parent_id=document.id, doc_type=DocType.page), key=lambda d: d.sequence)


def _import_alone(db, source: Path, tmp_path: Path):
    path = tmp_path / source.name
    shutil.copy(source, path)
    ctx = ActionContext(actor="owner", is_bootstrap=True)
    result = registry.invoke(db, "import.file", {"path": str(path)}, ctx)
    return db.get(Document, result.result["id"]), result


@pytest.mark.parametrize(("source", "pages", "letters"), [(GENJI, 24, 11_240), (LUTHER, 8, 15_051)],
                         ids=["genji", "luther"])
def test_every_page_of_a_tei_edition_arrives_with_all_its_letters(db, tmp_path, source, pages, letters):
    document, _ = _import_alone(db, source, tmp_path)
    in_file = tei.read_pages(source.read_bytes())
    assert len(in_file) == pages

    got = _pages(db, document)
    assert [p.sequence for p in got] == list(range(1, pages + 1)), "one page per <pb>, in the file's order"
    for page, read in zip(got, in_file):
        want = sum(_letters(t) for s in read.segments if s.kind != "word" for _k, t in s.readings[:1])
        assert _letters_on(db, page) == want, f"page {page.sequence}"
        pb_n = ((read.foreign.get("tei") or {}).get("pb") or {}).get("n")
        if pb_n:
            assert page.page_label == pb_n, "labelled with the file's own page number"
    assert sum(_letters_on(db, p) for p in got) == letters


def test_every_page_without_its_image_is_named_with_what_it_points_at(db, tmp_path):
    document, _ = _import_alone(db, GENJI, tmp_path)
    named = document.metadata["pages_without_image"]
    assert len(named) == 24, "no scan came with the file, so every page is named"
    assert named[0].startswith("page ") and "R0000022" in named[0], named[0]
    assert all(p.path is None for p in _pages(db, document)), "a page without an image has no file"


@pytest.mark.parametrize("source", [ALTO, PAGE], ids=["alto", "page"])
def test_a_page_or_alto_file_alone_is_a_document_with_its_page(db, tmp_path, source):
    from fichero_server.formats import format_for, read_page

    document, _ = _import_alone(db, source, tmp_path)
    data = source.read_bytes()
    read = read_page(format_for(source.name, data).name, data)
    (page,) = _pages(db, document)
    want = sum(_letters(t) for s in read.segments for _k, t in s.readings[:1])
    assert want and _letters_on(db, page, words=True) == want
    assert len(document.metadata["pages_without_image"]) == 1


def test_a_drop_of_the_file_alone_says_so_rather_than_calling_it_an_ordinary_file(client, db, tmp_path):
    path = tmp_path / LUTHER.name
    shutil.copy(LUTHER, path)
    body = client.post("/api/ingest/files", json={"paths": [str(path)]}).json()
    (document,) = body["documents"]
    assert body["unpaired"] == {}, "it is not left as an ordinary file"
    assert len(document["metadata"]["pages_without_image"]) == 8
    assert len(_pages(db, db.get(Document, document["id"]))) == 8


def test_an_upload_of_the_file_is_the_same_document(client, db):
    response = client.post("/api/documents/import", files={"file": (GENJI.name, GENJI.read_bytes(), "text/xml")})
    assert response.status_code == 200, response.text
    document = db.get(Document, response.json()["id"])
    assert len(_pages(db, document)) == 24
    assert sum(_letters_on(db, p) for p in _pages(db, document)) == 11_240


def test_one_undo_takes_the_document_and_its_pages_away(client, db, tmp_path):
    document, result = _import_alone(db, LUTHER, tmp_path)
    pages = [p.id for p in _pages(db, document)]
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    left = [db.get(Document, i) for i in [document.id, *pages]]
    assert all(d is None or d.deleted_at is not None for d in left)


def test_an_xml_file_that_is_not_interchange_stays_an_ordinary_file(db, tmp_path):
    path = tmp_path / "written" / "notes.xml"
    path.parent.mkdir()
    path.write_text("<notes><note>buy ink</note></notes>", encoding="utf-8")
    document, _ = _import_alone(db, path, tmp_path)
    assert _pages(db, document) == []
    assert "pages_without_image" not in (document.metadata or {})
