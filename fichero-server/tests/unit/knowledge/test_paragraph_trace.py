"""Every clause and character of the paragraph traces to statements (#6836).

spec: kg-paragraph-realisation (`kg.para.clause-carries-claim-ids`, `kg.para.every-character-has-an-origin`,
`kg.para.every-statement-is-said-once`, `kg.para.deterministic`, `kg.para.proposed-is-marked`)

No database and no route: `render_entry_with_mentions` reads a small in-memory stand-in.
"""
from __future__ import annotations

import random
import socket

import pytest

from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)

PAGE = "ent-ines"


class _Db:
    def __init__(self, claims: list[KnowledgeClaim]) -> None:
        self.claims = claims
        self.entity = KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel")

    def get(self, model, key):
        return self.entity

    def query_json_list_intersects(self, model, field, values):
        return list(self.claims)

    def query(self, model, **kw):
        return []


def _claim(cid, verb, obj, **kw) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel {verb} {obj}", svo_subject="Inés Valcárcel", svo_verb=verb,
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE], source_languages=["es"], **kw)


def _read(claims):
    sentences, _ = render_entry_with_mentions(_Db(claims), PAGE)
    return " ".join(s["text"] for s in sentences), sentences


def _merged():
    return [_claim("c1", "vendió", "una mula", time_start="1731-01-01"),
            _claim("c2", "vendió", "dos bueyes", time_start="1732-01-01"),
            _claim("c3", "vendió", "un huerto", time_start="1733-01-01")]


def test_a_joined_sentence_has_one_clause_per_unit():
    paragraph, sentences = _read(_merged() + [_claim("c4", "nació en", "Villa Arenal", time_start="1700-01-01")])
    assert len(sentences) == 2
    born, sold = sentences
    assert [c["claim_ids"] for c in born["clauses"]] == [["c4"]]
    assert [c["claim_ids"] for c in sold["clauses"]] == [["c1"], ["c2"], ["c3"]]
    assert [paragraph[c["start"]:c["end"]] for c in sold["clauses"]] == [
        "una mula (en 1731)", "dos bueyes (en 1732)", "un huerto (en 1733)"]
    assert (born["clauses"][0]["start"], born["clauses"][0]["end"]) == (born["start"], born["end"])


def test_every_character_traces_to_its_origin():
    claims = _merged()
    by_id = {c.id: c for c in claims}
    paragraph, sentences = _read(claims)
    fields = {"subject": "svo_subject", "verb": "svo_verb", "object": "svo_object"}
    assert fields  # origins name the stored field
    for s in sentences:
        covered = set()
        for seg in s["segments"]:
            covered.update(range(seg["start"], seg["end"]))
            text = paragraph[seg["start"]:seg["end"]]
            kind, _, rest = seg["origin"].partition(":")
            if kind == "claim":
                cid, _, field = rest.partition(":")
                if field == "time_start":
                    assert text == f"(en {getattr(by_id[cid], field)[:4]})"
                else:
                    assert text == getattr(by_id[cid], field)
            else:
                assert seg["origin"] in {"table:es:and", "punctuation"}
        assert all(i in covered for i in range(s["start"], s["end"]) if paragraph[i].isalnum())
    origins = [seg["origin"] for seg in sentences[0]["segments"]]
    assert origins == ["claim:c1:svo_subject", "claim:c1:svo_verb", "claim:c1:svo_object", "claim:c1:time_start",
                       "punctuation", "claim:c2:svo_object", "claim:c2:time_start", "table:es:and",
                       "claim:c3:svo_object", "claim:c3:time_start", "punctuation"]
    assert sentences[0]["segments"][0]["claim_ids"] == ["c1", "c2", "c3"]


def test_a_sentence_made_of_the_claim_text_names_the_text_field():
    lone = KnowledgeClaim(id="t1", text="Murió en San Telmo", subject_entity_id=PAGE, entity_ids=[PAGE])
    paragraph, sentences = _read([lone])
    assert paragraph == "Murió en San Telmo."
    assert [(g["origin"], paragraph[g["start"]:g["end"]]) for g in sentences[0]["segments"]] == [
        ("claim:t1:text", "Murió en San Telmo"), ("punctuation", ".")]


def test_every_selected_statement_is_in_exactly_one_clause():
    claims = _merged() + [_claim("c4", "nació en", "Villa Arenal", time_start="1700-01-01")]
    _, sentences = _read(claims)
    clause_ids = [cid for s in sentences for c in s["clauses"] for cid in c["claim_ids"]]
    assert sorted(clause_ids) == ["c1", "c2", "c3", "c4"]


def test_shuffled_input_gives_the_same_paragraph():
    claims = _merged() + [_claim("c4", "nació en", "Villa Arenal", time_start="1700-01-01")]
    first = _read(claims)
    for seed in range(5):
        shuffled = claims[:]
        random.Random(seed).shuffle(shuffled)
        assert _read(shuffled) == first


def test_no_model_is_called(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the paragraph reached the network")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    assert _read(_merged())[0].startswith("Inés Valcárcel vendió una mula")


@pytest.mark.parametrize("claims,states", [
    ([_claim("a", "nació en", "Villa Arenal")], ["proposed"]),
    ([_claim("a", "nació en", "Villa Arenal", curation_state=ClaimCurationState.curated)], ["reviewed"]),
    ([_claim("a", "nació en", "Villa Arenal", epistemic_status=EpistemicStatus.confirmed)], ["reviewed"]),
    ([_claim("a", "vendió", "una mula", curation_state=ClaimCurationState.curated),
      _claim("b", "vendió", "un huerto")], ["reviewed", "proposed"]),
])
def test_a_clause_says_proposed_or_reviewed(claims, states):
    _, sentences = _read(claims)
    assert [c["state"] for s in sentences for c in s["clauses"]] == states


def test_a_clause_carries_the_fields_later_steps_fill():
    claims = [_claim("a", "vendió", "una mula", source_document_id="d1", source_ids=["d1", "d2"])]
    clause = _read(claims)[1][0]["clauses"][0]
    assert (clause["role"], clause["revoiced"], clause["doubt"], clause["sources"]) == ("subject", False, "none", 2)
    assert clause["date"] is None and clause["place"] is None


def test_the_sentence_text_is_what_the_plain_renderer_gives():
    from fichero_server.knowledge.readable import _render_group_sentence, aggregate_claims

    undated = [c.model_copy(update={"time_start": None}) for c in _merged()]  # the plain renderer says no date
    for claims in (undated, [_claim("c4", "nació en", "Villa Arenal")],
                   [KnowledgeClaim(id="t1", text="Murió en San Telmo", subject_entity_id=PAGE, entity_ids=[PAGE])]):
        (group,) = aggregate_claims(claims)
        assert _read(claims)[0] == _render_group_sentence(group, claims[0])
