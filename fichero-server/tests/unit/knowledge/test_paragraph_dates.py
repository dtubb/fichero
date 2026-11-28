"""A statement's date is said at the level held, leads its sentence, and undated statements come last (#6837).

spec: kg-paragraph-realisation (`kg.para.date-at-stored-level`, `kg.para.date-bound-and-about`,
`kg.para.date-leads-the-sentence`, `kg.para.order-by-time`)
"""
from __future__ import annotations

import pytest

from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import EvidenceBasis, EvidentialDateRange, KnowledgeClaim, KnowledgeEntity

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


def _claim(cid, verb, obj, lang, **kw) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel {verb} {obj}", svo_subject="Inés Valcárcel", svo_verb=verb,
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE], source_languages=[lang], **kw)


def _dv(start=None, end=None, basis=EvidenceBasis.asserted, **kw) -> EvidentialDateRange:
    return EvidentialDateRange(start=start, end=end, basis=basis, **kw)


def _read(claims):
    sentences, _ = render_entry_with_mentions(_Db(claims), PAGE)
    return sentences


def _one(lang, **kw) -> str:
    return _read([_claim("c1", "vendió" if lang == "es" else "sold", "un caballo" if lang == "es" else "a horse", lang, **kw)])[0]["text"]


LEVELS = [
    # (claim fields, Spanish sentence, English sentence)
    (dict(time_start="1702-03-14", time_end="1702-03-14", time_precision="day"),
     "El 14 de marzo de 1702, Inés Valcárcel vendió un caballo.", "On 14 March 1702, Inés Valcárcel sold a horse."),
    (dict(time_start="1731-06-01", time_end="1731-06-30", time_precision="month"),
     "En junio de 1731, Inés Valcárcel vendió un caballo.", "In June 1731, Inés Valcárcel sold a horse."),
    (dict(time_start="1733-01-01", time_end="1733-12-31", time_precision="year"),
     "En 1733, Inés Valcárcel vendió un caballo.", "In 1733, Inés Valcárcel sold a horse."),
    (dict(time_start="1746-01-01", time_end="1749-12-31", time_precision="range"),
     "De 1746 a 1749, Inés Valcárcel vendió un caballo.", "From 1746 to 1749, Inés Valcárcel sold a horse."),
    (dict(time_start="1733-01-01"),
     "En 1733, Inés Valcárcel vendió un caballo.", "In 1733, Inés Valcárcel sold a horse."),
]


@pytest.mark.parametrize("fields,es,en", LEVELS)
def test_each_level_reads_as_its_row_of_the_table(fields, es, en):
    assert _one("es", **fields) == es
    assert _one("en", **fields) == en


def test_a_year_stored_as_first_of_january_never_reads_as_a_day_and_the_clause_says_the_level():
    sentence = _read([_claim("c1", "vendió", "un caballo", "es", time_start="1733-01-01", time_precision="year")])[0]
    assert sentence["clauses"][0]["date"]["level"] == "year"
    assert sentence["clauses"][0]["date"]["text"] == "en 1733"


@pytest.mark.parametrize("flags,es,en,level", [
    (dict(circa=True), "Hacia 1738, Inés Valcárcel vendió un caballo.", "About 1738, Inés Valcárcel sold a horse.", "about"),
    (dict(open_end=True), "En 1738 o después, Inés Valcárcel vendió un caballo.",
     "In or after 1738, Inés Valcárcel sold a horse.", "after"),
    (dict(open_start=True), "En 1738 o antes, Inés Valcárcel vendió un caballo.",
     "In or before 1738, Inés Valcárcel sold a horse.", "before"),
    (dict(basis=EvidenceBasis.inferred), "El 2 de mayo de 1738 (fecha inferida), Inés Valcárcel vendió un caballo.",
     "On 2 May 1738 (date inferred), Inés Valcárcel sold a horse.", "day"),
])
def test_a_bound_and_an_about_date_never_read_as_exact(flags, es, en, level):
    fields = dict(date_values=[_dv(start="1738-05-02", precision="day", **flags)])
    assert _one("es", **fields) == es
    assert _one("en", **fields) == en
    clause = _read([_claim("c1", "sold", "a horse", "en", **fields)])[0]["clauses"][0]
    assert clause["date"]["level"] == level


def test_a_date_value_is_read_when_the_statement_has_no_point_in_time_and_keeps_its_written_form():
    fields = dict(date_values=[_dv(start="1741-03-04", precision="day", label="4 de marzo del año 41")])
    sentence = _read([_claim("c1", "vendió", "un caballo", "es", **fields)])[0]
    assert sentence["text"] == "El 4 de marzo de 1741, Inés Valcárcel vendió un caballo."
    assert sentence["clauses"][0]["date"]["as_written"] == "4 de marzo del año 41"
    origins = [g["origin"] for g in sentence["segments"]]
    assert origins[0] == "claim:c1:date_values"


def test_a_single_unit_sentence_opens_with_its_date():
    sentence = _read([_claim("c1", "sold", "a horse", "en", time_start="1733-01-01", time_precision="year")])[0]
    assert sentence["text"].startswith("In 1733, Inés Valcárcel")
    first = sentence["segments"][0]
    assert (first["start"], first["end"], first["origin"]) == (0, len("In 1733,"), "claim:c1:time_start")
    assert sentence["clauses"][0]["start"] == 0 and sentence["clauses"][0]["end"] == len(sentence["text"])


def test_a_joined_sentence_follows_each_object_with_its_own_date():
    claims = [
        _claim("c1", "sold", "a horse", "en", time_start="1731-01-01", time_precision="year"),
        _claim("c2", "sold", "an ox", "en", time_start="1745-06-01", time_precision="month"),
    ]
    sentence = _read(claims)[0]
    assert sentence["text"] == "Inés Valcárcel sold a horse (in 1731) and an ox (in June 1745)."
    first, second = sentence["clauses"]
    assert sentence["text"][first["start"]:first["end"]] == "a horse (in 1731)"
    assert sentence["text"][second["start"]:second["end"]] == "an ox (in June 1745)"
    assert first["claim_ids"] == ["c1"] and second["claim_ids"] == ["c2"]


def test_undated_units_come_last_under_their_own_words():
    claims = [
        _claim("c1", "vendió", "un buey", "es"),
        _claim("c2", "compró", "una casa", "es", time_start="1750-01-01", time_precision="year"),
    ]
    sentences = _read(claims)
    assert [s["claim_ids"] for s in sentences] == [["c2"], ["c1"]]
    assert sentences[1]["text"] == "Sin fecha conocida: Inés Valcárcel vendió un buey."
    assert sentences[1]["segments"][0]["origin"] == "table:es:undated"
    assert sentences[1]["clauses"][0]["date"] is None
    paragraph = " ".join(s["text"] for s in sentences)
    assert all(paragraph[s["start"]:s["end"]] == s["text"] for s in sentences)


def test_the_undated_words_are_said_once_and_only_after_a_dated_sentence():
    undated = [_claim("c1", "sold", "an ox", "en"), _claim("c2", "bought", "a house", "en")]
    assert [s["text"] for s in _read(undated)] == ["Inés Valcárcel sold an ox.", "Inés Valcárcel bought a house."]
    mixed = [*undated, _claim("c3", "owned", "a mine", "en", time_start="1700-01-01")]
    assert [s["text"] for s in _read(mixed)] == [
        "In 1700, Inés Valcárcel owned a mine.",
        "Undated: Inés Valcárcel sold an ox.",
        "Inés Valcárcel bought a house.",
    ]


def test_the_route_model_takes_a_clause_date_as_the_engine_gives_it():
    from fichero_server.api.routes.kg.render import ReadableSentence

    sentence = _read([_claim("c1", "vendió", "un caballo", "es", time_start="1733-01-01")])[0]
    clause = ReadableSentence(**sentence).clauses[0]
    assert (clause.date.text, clause.date.level) == ("en 1733", "year")
