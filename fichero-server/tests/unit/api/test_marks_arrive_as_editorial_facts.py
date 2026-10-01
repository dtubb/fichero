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

import pytest
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


def test_deleted_letters_stay_in_the_reading_as_a_deletion_drawn_in_double_brackets(db, client):
    """Ruled 2026-09-28 (#5179), diplomatic: a `<del>`'s letters are IN the line's reading, and a
    `deleted` fact spans exactly them, drawn ⟦ ⟧. Before, the reader dropped them, so the reading
    said less than the page and the deletion was only "named, not imported". If this regresses,
    deleted letters vanish from the text again, or are shown as if never struck out."""
    from fichero_server.models import ContentRepresentation

    words = lambda text: " ".join(text.split())

    def as_written(el) -> str:
        """The letters the scribe wrote, by plain lxml: a <choice> gives its as-written side
        (orig/sic/abbr, else its first) -- the rule the reading follows for every <choice>."""
        parts = [el.text or ""]
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if etree.QName(child).localname == "choice":
                sides = [c for c in child if isinstance(c.tag, str)]
                chosen = next((c for c in sides if etree.QName(c).localname in {"orig", "sic", "abbr"}),
                              sides[0] if sides else None)
                parts.append(as_written(chosen) if chosen is not None else "")
            else:
                parts.append(as_written(child))
            parts.append(child.tail or "")
        return "".join(parts)

    expected = Counter(words(as_written(el)) for path in PAPYRI
                       for el in etree.parse(str(path)).getroot().iter("{*}del") if as_written(el).strip())
    assert expected                                                  # the premise, from the files
    seen = Counter()
    for path in PAPYRI:
        _doc, result = _import(db, path)
        assert not [n for n in result.result["not_imported"] if "<del>" in n["what"]]
    deletions = [f for f in db.all(EditorialFact) if f.kind == "deleted"]
    per_segment = Counter(f.segment_id for f in deletions)
    for fact in deletions:
        reading = db.get(ContentRepresentation, fact.representation_id)
        letters = reading.content[fact.char_start:fact.char_end]
        seen[words(letters)] += 1
        drawn = client.get(f"/api/editorial/segment/{fact.segment_id}").json()["drawn"]
        # Each deletion opens its own ⟦ (a <del> inside a <del> draws nested, ⟦απ⟦η⟧λασιας̣⟧ on
        # the real P.Oxy line), and its letters are there between the brackets.
        assert drawn.count("⟦") >= per_segment[fact.segment_id], drawn
        bare = drawn.replace("⟦", "").replace("⟧", "").replace(UNDERDOT, "")
        assert letters.replace(UNDERDOT, "").strip() in bare, (letters, drawn)
        assert "⟦" not in reading.content                             # drawn, never stored
    assert seen == expected                                          # every <del>, its own letters

def test_a_deletion_across_lines_is_a_deletion_on_every_line_it_runs_through(db):
    """`<delSpan spanTo="#x"/>` (#5179): the TEI Consortium sample strikes Hamlet from mid-line to
    the end of a later line (`#Ham92`, an `<lb>`), and a block up to the start of the next verse
    line (`#L4`). Diplomatic like `<del>` (ruled 2026-09-28): the letters stay in each reading and
    every line the span runs through gets a deleted fact over its part, so each is drawn ⟦ ⟧. It was
    named in `not_imported` as having "no one reading to span"."""
    from fichero_server.models import ContentRepresentation

    path = Path(__file__).parents[1] / "formats" / "fixtures" / "tei_consortium_testtranscr.xml"
    doc_id, result = _import(db, path)
    assert not any("delSpan" in n["what"] for n in result.result["not_imported"])

    texts = {r.segment_id: r.content for r in db.query(ContentRepresentation, document_id=doc_id)}
    deleted = {}
    for fact in db.all(EditorialFact):
        if fact.kind == "deleted" and fact.segment_id in texts:
            deleted.setdefault(texts[fact.segment_id], []).append(
                texts[fact.segment_id][fact.char_start:fact.char_end])

    assert deleted["So nightly toils the subject of the land,"] == ["nightly toils the subject of the land,"]
    for whole in ("And why such daily cast of brazen cannon,", "And foreign mart for implements of war;",
                  "Why such impress of shipwrights, whose sore task", "blah blah"):
        assert deleted[whole] == [whole], whole
    assert "Does not divide the Sunday from the week;" not in deleted, "the span ends where L4 begins"


def _facts_by_text(db, doc_id):
    from fichero_server.models import ContentRepresentation

    texts = {r.segment_id: r.content for r in db.query(ContentRepresentation, document_id=doc_id)}
    out = Counter()
    for fact in db.all(EditorialFact):
        if fact.segment_id in texts and fact.withdrawn_at is None and fact.char_start is not None:
            text = texts[fact.segment_id]
            # Stripped: TEI does not keep a reading's edge whitespace (the Syriac page's leading
            # no-break space), and a mark over the same letters is the same mark.
            out[(fact.kind.value, text[fact.char_start:fact.char_end].strip() if fact.char_end is not None else "@")] += 1
    return out


@pytest.mark.parametrize("path", PAPYRI + [SYRIAC], ids=lambda p: p.name)
def test_the_facts_go_back_out_as_tei_and_come_back_the_same(db, path):
    """#5179's write-back half: a library's editorial facts are written as the TEI elements an
    import reads them from (unclear, supplied, gap, surplus, del, add), so a page imported, exported
    and imported again carries the same facts over the same letters. Before this an export wrote
    the letters and none of the marks: an edition's apparatus lost on the way out."""
    from fichero_server.page_export import export_page

    doc_id, _ = _import(db, path)
    before = _facts_by_text(db, doc_id)
    assert before, "the file carries marks"
    exported = export_page(db, doc_id, "tei")
    again = tmp_file = Path(db.path).parent / f"{path.stem}.again.tei.xml"
    tmp_file.write_bytes(exported.data)
    doc_again, _ = _import(db, again)
    assert _facts_by_text(db, doc_again) == before


def _round_trip(db, doc_id, fmt, suffix):
    from fichero_server.page_export import export_page

    exported = export_page(db, doc_id, fmt)
    again = Path(db.path).parent / f"again-{doc_id}{suffix}"
    again.write_bytes(exported.data)
    doc_again, _ = _import(db, again)
    return doc_again


def test_a_page_xml_export_writes_the_unclear_facts_as_they_stand_now(db):
    """#5179, PAGE: the file's `unclear {offset;length}` marks come back out from the library's facts,
    not from the `custom` string kept at import, so a mark a person WITHDREW is not written back. Before
    this the kept string was written verbatim: the withdrawn mark came back on the next import."""
    doc_id, _ = _import(db, SYRIAC)
    before = _facts_by_text(db, doc_id)
    assert _facts_by_text(db, _round_trip(db, doc_id, "pagexml", ".page.xml")) == before

    withdrawn = next(f for f in db.all(EditorialFact)
                     if f.kind.value == "unclear" and f.segment_id == _line(db, doc_id, "l_57").id)
    registry.invoke(db, "editorial.withdraw", {"fact_id": withdrawn.id}, BOOT)
    after = _facts_by_text(db, _round_trip(db, doc_id, "pagexml", ".2.page.xml"))
    assert sum(after.values()) == sum(before.values()) - 1, "the withdrawn mark is not written back"
