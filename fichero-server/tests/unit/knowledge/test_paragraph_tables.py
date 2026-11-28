"""A language's table is one data file; the seam of verb and object is fixed on the entry path (#6842).

spec: kg-paragraph-realisation (`kg.para.table-is-data`, `kg.para.no-table-is-verbatim`, `kg.para.seams`)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from fichero_server.knowledge import readable
from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

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


def _claim(cid, verb, obj, lang="es", **kw) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel {verb} {obj}", svo_subject="Inés Valcárcel", svo_verb=verb,
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE],
        source_languages=[lang] if lang else [], **kw)


def _read(claims):
    sentences, _ = render_entry_with_mentions(_Db(claims), PAGE)
    return [s["text"] for s in sentences], sentences


def _french_table(directory: Path) -> None:
    (directory / "fr.json").write_text(json.dumps({
        "language": "fr", "and": "et", "at": "à", "times": "fois",
        "prepositions": ["à", "de", "en"], "contractions": {"de le": "du", "à le": "au"}}), encoding="utf-8")


def test_a_language_is_added_by_a_file_alone(tmp_path, monkeypatch):
    tables = tmp_path / "tables"
    shutil.copytree(readable.LANGUAGE_TABLES_DIR, tables)
    claims = [_claim("c1", "a vendu", "un cheval", "fr", time_start="1731-01-01"),
              _claim("c2", "a vendu", "un boeuf", "fr", time_start="1732-01-01")]
    before, _ = _read(claims)
    assert before == ["Inés Valcárcel a vendu un cheval (1731).", "Inés Valcárcel a vendu un boeuf (1732)."]
    _french_table(tables)
    monkeypatch.setattr(readable, "_TABLES", readable.load_language_tables(tables))
    after, sentences = _read(claims)
    assert after == ["Inés Valcárcel a vendu un cheval et un boeuf."]
    assert [g["origin"] for g in sentences[0]["segments"]][3] == "table:fr:and"


def test_a_table_file_that_lacks_a_key_is_refused(tmp_path):
    (tmp_path / "xx.json").write_text(json.dumps({"language": "xx", "and": "y"}), encoding="utf-8")
    with pytest.raises(ValueError, match="xx.json"):
        readable.load_language_tables(tmp_path)


def test_a_table_file_named_for_another_language_is_refused(tmp_path):
    _french_table(tmp_path)
    (tmp_path / "fr.json").rename(tmp_path / "de.json")
    with pytest.raises(ValueError, match="de.json"):
        readable.load_language_tables(tmp_path)


def test_a_language_without_a_table_takes_no_borrowed_word():
    claims = [_claim("c1", "a vendu", "un cheval", "fr", time_start="1731-01-01"),
              _claim("c2", "a vendu", "un boeuf", "fr", time_start="1731-06-01"),
              _claim("c3", "sold", "a mule", None, time_start="1740-05-09")]
    texts, sentences = _read(claims)
    assert texts == ["Inés Valcárcel a vendu un cheval (1731).", "Inés Valcárcel a vendu un boeuf (1731).",
                     "Inés Valcárcel sold a mule (1740)."]
    for sentence in sentences:
        assert {g["origin"].split(":")[0] for g in sentence["segments"]} <= {"claim", "punctuation"}


def test_the_entry_path_says_a_preposition_once():
    claims = [_claim("c1", "llegó a", "a Andagoya"), _claim("c2", "arrived at", "at Andagoya", "en")]
    texts, sentences = _read(claims)
    assert texts == ["Inés Valcárcel llegó a Andagoya.", "Inés Valcárcel arrived at Andagoya."]
    assert sentences[0]["segments"][2]["origin"] == "claim:c1:svo_object"


def test_a_joined_sentence_makes_the_contraction_once_at_the_verb():
    claims = [_claim("c1", "habló de", "el rey", time_start="1731-01-01"),
              _claim("c2", "habló de", "el mercado", time_start="1732-01-01")]
    texts, sentences = _read(claims)
    assert texts == ["Inés Valcárcel habló del rey (en 1731) y el mercado (en 1732)."]
    assert [g["origin"] for g in sentences[0]["segments"]][:4] == [
        "claim:c1:svo_subject", "claim:c1:svo_verb", "table:es:de el", "claim:c1:svo_object"]


def test_spanish_contractions_at_the_seam():
    claims = [_claim("c1", "habló de", "el rey"), _claim("c2", "fue a", "el mercado")]
    texts, sentences = _read(claims)
    assert texts == ["Inés Valcárcel habló del rey.", "Inés Valcárcel fue al mercado."]
    origins = [g["origin"] for g in sentences[0]["segments"]]
    assert origins == ["claim:c1:svo_subject", "claim:c1:svo_verb", "table:es:de el", "claim:c1:svo_object",
                       "punctuation"]


def test_the_route_prints_the_seam_fixed(client, db):
    with db.defer_embeddings():
        page = KnowledgeEntity(canonical_name="Inés Valcárcel")
        db.save(page)
        db.save(KnowledgeClaim(
            text="Inés Valcárcel habló de el rey", svo_subject="Inés Valcárcel", svo_verb="habló de",
            svo_object="el rey", subject_entity_id=page.id, entity_ids=[page.id], source_languages=["es"]))
    body = client.get(f"/api/kg/entities/{page.id}/readable").json()
    assert body["paragraph"] == "Inés Valcárcel habló del rey."
