"""#5179, ruled 2026-09-28: search finds a line by the text that STANDS.

`source.sure.search-finds-what-stands` (readings-and-apparatus.md). A TEI `<subst>` keeps both its
added and its struck letters in the reading (diplomatic, ⟦ ⟧), so "M⟦m⟧anor" reads "Mmanor". Full
text search tokenizes that as ONE word, and a search for "Manor" -- the word that stands -- found
nothing. What breaks without these tests: the page's standing text (deletions left out) not kept
by the page-text cache, not refreshed when a deletion is recorded or withdrawn, or not indexed.
"""
from __future__ import annotations

from fichero_server.actions.page_text_cache import STANDING_TEXT
from fichero_server.actions.registry import registry
from fichero_server.models import ContentRepresentation, DocType, Document, FileType
from tests.unit.api.test_segment_readings import (
    _artifact,
    _convert,
    _converted_segments,
    _make_doc,
    _person,
    _write,
)


def _page_with_a_struck_letter(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    segment = _converted_segments(db, artifact.id)[0]
    reading = _write(db, segment, content="Mmanor house")
    fact = registry.invoke(db, "editorial.record", {
        "segment_id": segment.id, "kind": "deleted",
        "representation_id": reading.result["id"], "char_start": 1, "char_end": 2,
    }, _person())
    return doc, segment, fact


def _search(client, query):
    r = client.post("/api/search", json={"query": query, "search_type": "fulltext", "min_score": 0.0})
    assert r.status_code == 200, r.text
    return {item["document_id"] for item in r.json()["results"]}


def test_the_cache_keeps_the_text_that_stands_beside_the_page_text(db, client):
    doc, _segment, _fact = _page_with_a_struck_letter(db, client)
    stored = db.get(Document, doc.id)
    assert "Mmanor house" in stored.page_content, "the reading keeps the struck letter"
    assert "Manor house" in stored.metadata[STANDING_TEXT]
    assert "Mmanor" not in stored.metadata[STANDING_TEXT]


def test_withdrawing_the_deletion_removes_the_standing_text(db, client):
    doc, _segment, fact = _page_with_a_struck_letter(db, client)
    registry.invoke(db, "editorial.withdraw", {"fact_id": fact.result["fact_id"]}, _person())
    assert STANDING_TEXT not in db.get(Document, doc.id).metadata


def test_a_page_with_no_deletion_keeps_no_standing_text(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    _write(db, _converted_segments(db, artifact.id)[0], content="Mmanor house")
    assert STANDING_TEXT not in db.get(Document, doc.id).metadata


def test_full_text_search_finds_the_word_that_stands_and_the_struck_one(db, client):
    """With another page that says "Manor" plainly, the index HAS hits for the word, so search
    never falls back to scanning for it as a substring, and the page reading "Mmanor" went missing
    from the very search that should find it. The other page says "Manor" in the SAME case: the
    index's token match is case-sensitive (#5307), a separate defect this test does not lean on."""
    doc, _segment, _fact = _page_with_a_struck_letter(db, client)
    db.embed(db.get(Document, doc.id))
    other = Document(name="Plain", page_content="The Manor of Popayán", doc_type=DocType.file,
                     file_type=FileType.text)
    db.save(other)
    db.embed(other)
    assert other.id in _search(client, "Manor")
    assert doc.id in _search(client, "Manor"), "the word as it stands, the struck letter left out"
    assert doc.id in _search(client, "Mmanor"), "the letters as written are still found"
    assert db.query(ContentRepresentation, document_id=doc.id), "the reading itself is unchanged"
