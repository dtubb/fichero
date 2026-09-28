"""What a file's editor said about stretches of its text arrives as editorial facts (#5179;
`source.sure.editorial-facts`, `source.sure.brackets-are-drawn`, the "from a file" half).

WHY: a file that marks a stretch unclear, lost, restored, supplied, superfluous or added lost the
mark on import -- the reading kept the letters and dropped what the editor said about them, so a
papyrus's restorations read as if they were on the papyrus. Each mark is now a fact on the reading
the import made, the FILE's claim (`external_import`, no person as its maker, `source` naming the
file), written inside the import's own audited action so its undo takes them; what cannot be a fact
is named in `not_imported`, not dropped. If this regresses, an edition's apparatus disappears on
import, or a restoration is shown as the scribe's writing.

Real files through format.import: the eScriptorium Syriac PAGE page (six whole-line `unclear`
marks) and the DDbDP papyri (TEI). What each says is read with lxml.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import DocType, Document, FileType, Segment, Status
from fichero_server.models.editorial import EditorialFact
from tests.unit.api.test_page_text_follows_the_file import BOOT

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
SYRIAC = CORPUS / "escriptorium_syriac_onb-syr1-0001.page.xml"
PAPYRI = sorted(CORPUS.glob("ddbdp_greek-papyrus_*.tei.xml"))
GAP_13 = CORPUS / "ddbdp_greek-papyrus_sb.22.15276.tei.xml"
UNDERDOT = "̣"


def _import(db, path: Path):
    doc = Document(name=path.stem, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{path.stem}.jpg",
                   status=Status.completed)
    db.save(doc)
    result = registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, BOOT)
    return doc.id, result


def _line(db, doc_id: str, source_id: str) -> Segment:
    return next(s for s in db.all(Segment) if s.document_id == doc_id and s.metadata.get("source_id") == source_id)


def test_a_page_unclear_mark_is_a_fact_drawn_on_its_line(db, client):
    root = etree.parse(str(SYRIAC)).getroot()
    l57 = next(el for el in root.iter("{*}TextLine") if el.get("id") == "l_57")
    assert "unclear {offset:0; length:12;}" in l57.get("custom")
    text = "".join(l57.find("{*}TextEquiv/{*}Unicode").itertext())
    assert len(text) == 12                                        # the WHOLE line

    doc_id, _result = _import(db, SYRIAC)
    got = client.get(f"/api/editorial/segment/{_line(db, doc_id, 'l_57').id}").json()
    [fact] = got["items"]
    assert (fact["kind"], fact["char_start"], fact["char_end"]) == ("unclear", 0, 12)
    assert fact["source"] == f"file: {SYRIAC.name}" and fact["provenance_kind"] == "external_import"
    assert fact["created_by"] is None
    assert got["drawn"].count(UNDERDOT) == len(text)              # an under-dot on each of its 12
    reading = next(r for r in client.get(f"/api/segments/{fact['segment_id']}/readings").json()["items"]
                   if r["id"] == fact["representation_id"])
    assert reading["content"] == text and UNDERDOT not in reading["content"]   # drawn, never stored


def test_the_papyri_marks_arrive_each_kind_in_its_place(db, client):
    kinds: Counter = Counter()
    for path in PAPYRI:
        doc_id, result = _import(db, path)
        facts = [f for f in db.all(EditorialFact) if db.get(Segment, f.segment_id).document_id == doc_id]
        kinds.update(f.kind.value for f in facts)
        assert result.result["editorial_facts"] == len(facts)
    assert {"unclear", "restored", "lost", "superfluous", "added"} <= set(kinds), kinds

    # The mid-line gap of 13 is drawn at its place, not at the line's end.
    doc_id, _result = _import(db, GAP_13.with_name(GAP_13.name))
    lost = [f for f in db.all(EditorialFact) if f.kind.value == "lost" and f.extent_quantity == 13
            and db.get(Segment, f.segment_id).document_id == doc_id]
    assert lost, "the file's <gap quantity=13> arrived"
    fact = lost[0]
    drawn = client.get(f"/api/editorial/segment/{fact.segment_id}").json()["drawn"]
    assert "13" in drawn
    reading = next(r for r in client.get(f"/api/segments/{fact.segment_id}/readings").json()["items"]
                   if r["id"] == fact.representation_id)
    assert 0 < fact.char_start < len(reading["content"])            # a gap MID-line in the file
    marker = drawn.index("[--- 13 ---]")
    letters = lambda t: "".join(ch for ch in t if ch.isalpha())         # Leiden signs interleave letters
    after = letters(reading["content"][fact.char_start:])[:3]          # the letters the gap stands before
    assert after and letters(drawn[marker + len("[--- 13 ---]"):])[:3] == after   # ... follow it: in place


def test_undoing_the_import_takes_the_facts_with_it(db, client):
    doc_id, result = _import(db, SYRIAC)
    line = _line(db, doc_id, "l_57")
    assert client.get(f"/api/editorial/segment/{line.id}").json()["items"]
    assert client.post(f"/api/actions/audit/{result.audit_id}/undo").status_code == 200
    after = client.get(f"/api/editorial/segment/{line.id}")
    assert after.status_code == 404 or after.json()["items"] == []


def test_importing_the_same_file_again_does_not_double_them(db, client):
    import pytest
    from fastapi import HTTPException

    doc_id, _result = _import(db, SYRIAC)
    before = len(db.all(EditorialFact))
    with pytest.raises(HTTPException):
        registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(SYRIAC)}, BOOT)
    assert len(db.all(EditorialFact)) == before


def test_what_cannot_be_a_fact_is_named_not_dropped(db, client):
    dels = sum(1 for path in PAPYRI for el in etree.parse(str(path)).getroot().iter("{*}del"))
    assert dels
    named = Counter()
    for path in PAPYRI:
        _doc, result = _import(db, path)
        for note in result.result["not_imported"]:
            named[note["what"]] += note["count"]
    assert named["deleted text (<del>)"] > 0
