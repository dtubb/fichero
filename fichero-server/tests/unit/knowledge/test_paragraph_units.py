"""Units of the paragraph: one statement from several sources, and the two halves of one passage (#6840).

spec: kg-paragraph-realisation (`kg.para.same-statement-one-clause`, `kg.para.one-passage-one-sentence`)
"""
from __future__ import annotations

from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import EpistemicStatus, KnowledgeClaim, KnowledgeEntity

PAGE = "ent-ines"


class _Db:
    def __init__(self, claims):
        self.claims = claims
        self.entity = KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel")

    def get(self, model, key):
        return self.entity

    def query_json_list_intersects(self, model, field, values):
        return list(self.claims)

    def query(self, model, **kw):
        return []

    def query_in(self, model, column, values):
        return []

    def entity_ids_by_canonical_name(self, names):
        return {}


def _claim(cid, obj, doc="d1", year=None, **kw) -> KnowledgeClaim:
    dated = {"time_start": f"{year}-01-01", "time_end": f"{year}-12-31", "time_precision": "year"} if year else {}
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel vendió {obj}", svo_subject="Inés Valcárcel", svo_verb="vendió",
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE], source_languages=["es"],
        source_document_id=doc, **dated, **kw)


def _half(cid, obj, start=120, end=180, **kw) -> KnowledgeClaim:
    return _claim(cid, obj, source_page_label="f. 3r", source_char_start=start, source_char_end=end, **kw)


def _read(claims):
    return render_entry_with_mentions(_Db(claims), PAGE)[0]


def _paragraph(sentences):
    return " ".join(s["text"] for s in sentences)


def _clauses(sentences):
    return [c for s in sentences for c in s["clauses"]]


def test_same_statement_different_date_is_two_units():
    sentences = _read([_claim("c1", "una casa", "d1", 1702), _claim("c2", "una casa", "d2", 1704)])
    assert [(c["claim_ids"], c["date"]["text"]) for c in _clauses(sentences)] == [(["c1"], "en 1702"), (["c2"], "en 1704")]
    paragraph = _paragraph(sentences)
    assert "1702" in paragraph and "1704" in paragraph
    # the same date from two documents is one unit: one clause that names both statements
    same = _read([_claim("c1", "una casa", "d1", 1702), _claim("c2", "una casa", "d2", 1702)])
    assert [(c["claim_ids"], c["sources"]) for c in _clauses(same)] == [(["c1", "c2"], 2)]
    assert _paragraph(same).count("una casa") == 1


def test_an_unsure_statement_of_another_date_is_said_apart_from_the_plain_one():
    sentences = _read([
        _claim("c1", "una casa", "d1", 1702),
        _claim("c2", "una casa", "d2", 1704, epistemic_status=EpistemicStatus.tentative),
    ])
    assert [s["claim_ids"] for s in sentences] == [["c1"], ["c2"]]
    assert "al parecer" not in sentences[0]["text"] and "al parecer" in sentences[1]["text"]


def test_two_halves_of_one_passage_are_one_sentence_and_never_coordinated():
    sold, to = _half("c1", "una casa"), _half("c2", "a Pedro Mosquera")
    for claims in ([sold, to], [to, sold]):  # the plain object is first whichever is stored first
        sentences = _read(claims)
        assert [s["text"] for s in sentences] == ["Inés Valcárcel vendió una casa a Pedro Mosquera."]
        text = sentences[0]["text"]
        assert [(c["claim_ids"], text[c["start"]:c["end"]]) for c in sentences[0]["clauses"]] == [
            (["c1"], "Inés Valcárcel vendió una casa"), (["c2"], "a Pedro Mosquera")]
        assert sorted(sentences[0]["claim_ids"]) == ["c1", "c2"]
        assert not any(g["origin"] == "table:es:and" for g in sentences[0]["segments"])
        said = {g["origin"]: text[g["start"]:g["end"]] for g in sentences[0]["segments"]}
        assert said["claim:c1:svo_object"] == "una casa" and said["claim:c2:svo_object"] == "a Pedro Mosquera"
    dated = _read([_half("c1", "una casa", year=1743), _half("c2", "a Pedro Mosquera", year=1743)])
    assert [s["text"] for s in dated] == ["En 1743, Inés Valcárcel vendió una casa a Pedro Mosquera."]


def test_anything_less_than_the_same_stretch_stays_two_sentences():
    sold = _half("c1", "una casa")
    apart = {
        "another range": _half("c2", "a Pedro Mosquera", start=200, end=240),
        "another end": _half("c2", "a Pedro Mosquera", end=150),
        "another document": _half("c2", "a Pedro Mosquera", doc="d2"),
        "no range": _claim("c2", "a Pedro Mosquera"),
        "another date": _half("c2", "a Pedro Mosquera", year=1743),
    }
    for why, to in apart.items():
        assert sorted(s["claim_ids"] for s in _read([sold, to])) == [["c1"], ["c2"]], why
    # two plain objects on the stretch: the recipient belongs to neither by rule, so it stays alone
    three = _read([sold, _half("c3", "una mina"), _half("c2", "a Pedro Mosquera")])
    assert sorted(sorted(s["claim_ids"]) for s in three) == [["c1", "c3"], ["c2"]]
    # two prepositional objects on one stretch are never one sentence
    both = _read([_half("c1", "a Pedro Mosquera"), _half("c2", "en Cali")])
    assert sorted(s["claim_ids"] for s in both) == [["c1"], ["c2"]]


def _save(db, entity, verb, obj, doc, **kw) -> str:
    row = KnowledgeClaim(
        text=f"Ana {verb} {obj}", svo_subject="Ana", svo_verb=verb, svo_object=obj,
        subject_entity_id=entity.id, entity_ids=[entity.id], source_languages=["es"],
        source_document_id=doc, **kw)
    db.save(row)
    return row.id


def test_two_dates_of_one_statement_are_two_clauses_on_the_route(client, db):
    with db.defer_embeddings():
        entity = KnowledgeEntity(canonical_name="Ana")
        db.save(entity)
        first = _save(db, entity, "compró", "una mina", "doc-1",
                      time_start="1702-01-01", time_end="1702-12-31", time_precision="year")
        later = _save(db, entity, "compró", "una mina", "doc-2",
                      time_start="1704-01-01", time_end="1704-12-31", time_precision="year")
    body = client.get(f"/api/kg/entities/{entity.id}/readable").json()
    clauses = [c for s in body["sentences"] for c in s["clauses"]]
    assert [(c["claim_ids"], c["date"]["text"]) for c in clauses] == [([first], "en 1702"), ([later], "en 1704")]
    assert "1702" in body["paragraph"] and "1704" in body["paragraph"]


def test_two_halves_of_one_passage_are_one_sentence_on_the_route(client, db):
    with db.defer_embeddings():
        entity = KnowledgeEntity(canonical_name="Ana")
        db.save(entity)
        stretch = {"source_page_label": "f. 3r", "source_char_start": 120, "source_char_end": 180}
        to = _save(db, entity, "vendió", "a Pedro Mosquera", "doc-3", **stretch)
        sold = _save(db, entity, "vendió", "una casa", "doc-3", **stretch)
    body = client.get(f"/api/kg/entities/{entity.id}/readable").json()
    assert body["paragraph"] == "Ana vendió una casa a Pedro Mosquera."
    assert [c["claim_ids"] for c in body["sentences"][0]["clauses"]] == [[sold], [to]]
