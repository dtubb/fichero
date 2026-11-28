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
