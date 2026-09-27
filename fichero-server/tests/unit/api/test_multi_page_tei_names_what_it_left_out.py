"""A multi-page TEI file imported onto one image names every page it did not take (#5143).

WHY: `format.import` reads ONE page. The Digital Genji is 24 page breaks (`<pb>`) in one file;
imported onto its first scan it answered success, with that page's lines, and 23 pages were
gone without a word -- the person had no way to know the rest of the edition was not in the
library. If this regresses, the answer stops counting the file's pages or stops naming the ones
left out. The expected side is counted from the file with plain lxml.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Status

GENJI = (Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
         / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml")
TEI = "{http://www.tei-c.org/ns/1.0}"
BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page_breaks() -> list[etree._Element]:
    root = etree.parse(str(GENJI)).getroot()
    return list(root.find(f"{TEI}text").iter(f"{TEI}pb"))


def _document(db) -> str:
    doc = Document(name="R0000022.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/R0000022.jpg", status=Status.completed)
    db.save(doc)
    return doc.id


def test_the_answer_counts_the_pages_and_names_each_one_left_out(db):
    pbs = _page_breaks()
    assert len(pbs) > 1

    result = registry.invoke(
        db, "format.import", {"document_id": _document(db), "path": str(GENJI)}, BOOT
    ).result

    assert result["pages_in_file"] == len(pbs)
    left_out = result["pages_left_out"]
    assert len(left_out) == len(pbs) - 1
    for pb, named in zip(pbs[1:], left_out):
        assert f"page {pb.get('n')}" in named and pb.get("corresp") in named, named


def test_taking_several_pages_leaves_out_only_the_others(db):
    pbs = _page_breaks()
    result = registry.invoke(
        db, "format.import",
        {"document_id": _document(db), "path": str(GENJI), "pages": [2, 3]}, BOOT,
    ).result
    assert len(result["pages_left_out"]) == len(pbs) - 2
    named = " ".join(result["pages_left_out"])
    assert f"page {pbs[1].get('n')} " not in named and f"page {pbs[2].get('n')} " not in named
    assert f"page {pbs[0].get('n')} " in named


def test_the_route_answers_with_the_pages_left_out(client):
    doc = client.post("/api/documents", json={"name": "R0000022.jpg"})
    assert doc.status_code in (200, 201), doc.text
    doc_id = doc.json()["id"]
    with GENJI.open("rb") as handle:
        response = client.post(
            f"/api/documents/{doc_id}/import", files={"file": (GENJI.name, handle)}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pages_in_file"] == len(_page_breaks())
    assert len(body["pages_left_out"]) == len(_page_breaks()) - 1
