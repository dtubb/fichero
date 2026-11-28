"""Doubt in the paragraph: a person's decision, a dispute, sources in words, a single unsure source (#6839).

spec: kg-paragraph-realisation (`kg.para.doubt-is-attribution`, `kg.para.no-figure-no-hedge`,
`kg.para.sources-are-counted-in-words`,
`kg.para.dispute-states-both`, `kg.para.person-decision-is-plain`)
"""
from __future__ import annotations

import json
import re
import shutil

from fichero_server.knowledge import readable
from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimRelationType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

PAGE = "ent-ines"


class _Db:
    def __init__(self, claims, links=()):
        self.claims = claims
        self.links = list(links)
        self.link_reads = []
        self.entity = KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel")

    def get(self, model, key):
        return self.entity

    def query_json_list_intersects(self, model, field, values):
        return list(self.claims)

    def query(self, model, **kw):
        assert model is not KnowledgeClaimLink, "links are read by the entry's statement ids (query_in)"
        return []

    def query_in(self, model, column, values):
        self.link_reads.append((model, column, sorted(values)))
        return [x for x in self.links if getattr(x, column) in set(values)]

    def entity_ids_by_canonical_name(self, names):
        return {}


def _claim(cid, verb, obj, lang="en", docs=("d1",), **kw) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel {verb} {obj}", svo_subject="Inés Valcárcel", svo_verb=verb,
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE], source_languages=[lang],
        source_document_id=docs[0] if docs else None, source_ids=list(docs[1:]), **kw)


def _read(claims, links=()):
    return render_entry_with_mentions(_Db(claims, links), PAGE)[0]


def _clause(sentences, cid):
    return next(c for s in sentences for c in s["clauses"] if cid in c["claim_ids"])


def test_a_single_unsure_statement_is_hedged_and_attributed():
    tentative = _read([_claim("c1", "sold", "a horse", epistemic_status=EpistemicStatus.tentative)])
    assert tentative[0]["text"] == "Inés Valcárcel, apparently, sold a horse (one source only)."
    assert _clause(tentative, "c1")["doubt"] == "one_source_unsure"
    low = _read([_claim("c1", "vendió", "un caballo", "es", confidence=0.2, confidence_source="measured")])
    assert low[0]["text"] == "Inés Valcárcel, al parecer, vendió un caballo (una sola fuente)."
    assert _clause(low, "c1")["doubt"] == "one_source_unsure"
    origins = {g["origin"] for g in low[0]["segments"]}
    assert {"table:es:hedge", "table:es:one_source"} <= origins
    # a statement with only its stored text takes the hedge after it
    bare = _read([KnowledgeClaim(id="c1", text="Inés Valcárcel sold a horse", subject_entity_id=PAGE,
                                 entity_ids=[PAGE], source_languages=["en"], source_document_id="d1",
                                 epistemic_status=EpistemicStatus.tentative)])
    assert bare[0]["text"] == "Inés Valcárcel sold a horse, apparently (one source only)."
    # a measured figure outside the low band is said plainly
    high = _read([_claim("c1", "sold", "a horse", confidence=0.9, confidence_source="measured")])
    assert high[0]["text"] == "Inés Valcárcel sold a horse."


def test_an_unsure_object_is_not_joined_into_a_plain_sentence():
    sentences = _read([
        _claim("c1", "sold", "a horse", docs=("d1", "d2")),
        _claim("c2", "sold", "an ox", docs=("d3",), epistemic_status=EpistemicStatus.tentative),
    ])
    assert [s["text"] for s in sentences] == [
        "Inés Valcárcel sold a horse (two sources).",
        "Inés Valcárcel, apparently, sold an ox (one source only).",
    ]


def test_a_table_without_doubt_words_says_two_unsure_objects_plainly(tmp_path, monkeypatch):
    tables = tmp_path / "tables"
    shutil.copytree(readable.LANGUAGE_TABLES_DIR, tables)
    (tables / "fr.json").write_text(json.dumps({
        "language": "fr", "and": "et", "at": "à", "times": "fois",
        "prepositions": ["à", "de", "en"], "contractions": {"de le": "du", "à le": "au"}}), encoding="utf-8")
    monkeypatch.setattr(readable, "_TABLES", readable.load_language_tables(tables))
    sentences = _read([
        _claim("c1", "a vendu", "un cheval", "fr", epistemic_status=EpistemicStatus.tentative),
        _claim("c2", "a vendu", "un boeuf", "fr", epistemic_status=EpistemicStatus.tentative),
    ])
    assert [s["text"] for s in sentences] == ["Inés Valcárcel a vendu un cheval et un boeuf."]
    assert _clause(sentences, "c1")["doubt"] == "one_source_unsure"


def test_an_unmeasured_figure_changes_no_word():
    for source in (None, "default", "llm_logprob"):
        sentences = _read([_claim("c1", "sold", "a horse", confidence=0.1, confidence_source=source)])
        assert sentences[0]["text"] == "Inés Valcárcel sold a horse."
        assert _clause(sentences, "c1")["doubt"] == "none"
    born = _read([_claim("c1", "sold", "a horse")])  # the stored 0.5 a statement is born with
    assert born[0]["text"] == "Inés Valcárcel sold a horse."
    assert not re.search(r"\d", born[0]["text"])


def test_two_documents_read_as_two_sources():
    one = _read([_claim("c1", "sold", "a horse", docs=("d1", "d2"))])
    assert one[0]["text"] == "Inés Valcárcel sold a horse (two sources)."
    assert _clause(one, "c1")["sources"] == 2
    merged = _read([_claim("c1", "vendió", "un caballo", "es", docs=("d1",)),
                    _claim("c2", "vendió", "un caballo", "es", docs=("d2",))])
    assert merged[0]["text"] == "Inés Valcárcel vendió un caballo (dos fuentes)."
    assert _clause(merged, "c1")["sources"] == 2
    # rule 4 comes before rule 5: two documents that are each tentative are said plainly
    tentative = _read([_claim("c1", "sold", "a horse", docs=("d1", "d2", "d3"),
                              epistemic_status=EpistemicStatus.tentative)])
    assert tentative[0]["text"] == "Inés Valcárcel sold a horse (three sources)."
    assert _clause(tentative, "c1")["doubt"] == "none"
    thirteen = _read([_claim("c1", "sold", "a horse", docs=tuple(f"d{n}" for n in range(13)))])
    assert thirteen[0]["text"] == "Inés Valcárcel sold a horse (13 sources)."
    # each joined object counts its own documents
    joined = _read([_claim("c1", "sold", "a horse", docs=("d1", "d2")), _claim("c2", "sold", "an ox")])
    assert joined[0]["text"] == "Inés Valcárcel sold a horse (two sources) and an ox."


def test_a_confirmed_statement_is_never_hedged():
    curated = _read([_claim("c1", "sold", "a horse", curation_state=ClaimCurationState.curated,
                            epistemic_status=EpistemicStatus.tentative)])
    assert curated[0]["text"] == "Inés Valcárcel sold a horse."
    assert _clause(curated, "c1")["doubt"] == "none"
    confirmed = _read([_claim("c1", "sold", "a horse", epistemic_status=EpistemicStatus.confirmed,
                              confidence=0.1, confidence_source="measured")])
    assert confirmed[0]["text"] == "Inés Valcárcel sold a horse."
    # a person's decision outranks the count of sources too
    counted = _read([_claim("c1", "sold", "a horse", docs=("d1", "d2"), curation_state=ClaimCurationState.curated)])
    assert counted[0]["text"] == "Inés Valcárcel sold a horse."


def test_a_hedge_is_served_by_the_route(client, db):
    with db.defer_embeddings():
        entity = KnowledgeEntity(canonical_name="Ana")
        db.save(entity)
        db.save(KnowledgeClaim(
            text="Ana vendió una casa", svo_subject="Ana", svo_verb="vendió", svo_object="una casa",
            subject_entity_id=entity.id, entity_ids=[entity.id], source_languages=["es"],
            source_document_id="doc-1", epistemic_status=EpistemicStatus.tentative))
    body = client.get(f"/api/kg/entities/{entity.id}/readable").json()
    assert body["paragraph"] == "Ana, al parecer, vendió una casa (una sola fuente)."
    assert body["sentences"][0]["clauses"][0]["doubt"] == "one_source_unsure"


def _born(cid, start, end, precision, doc, offset=0, **kw):
    return _claim(cid, "nació en", "Villa Arenal", "es", docs=(doc,), time_start=start, time_end=end,
                  time_precision=precision, source_char_start=offset, **kw)


def _contradicts(a, b):
    return KnowledgeClaimLink(claim_id=a, related_claim_id=b, relation_type=ClaimRelationType.contradicts)


def test_a_dispute_is_one_sentence_with_both_readings():
    a = _born("c1", "1702-03-14", "1702-03-14", "day", "doc-a")
    b = _born("c2", "1704-01-01", "1704-12-31", "year", "doc-b")
    expected = "Inés Valcárcel nació en Villa Arenal el 14 de marzo de 1702 según una fuente y en 1704 según otra."
    for claims, link in (([a, b], _contradicts("c1", "c2")), ([b, a], _contradicts("c2", "c1"))):
        sentences = _read(claims, [link])
        assert [s["text"] for s in sentences] == [expected]  # one sentence, in source order whichever way
        assert sentences[0]["claim_ids"] == ["c1", "c2"]
        assert [(c["claim_ids"], c["doubt"]) for c in sentences[0]["clauses"]] == [(["c1"], "disputed"), (["c2"], "disputed")]
        origins = [g["origin"] for g in sentences[0]["segments"]]
        assert "table:es:according_one" in origins and "table:es:according_other" in origins
    # only a stored link makes a dispute: without one the two are said apart
    apart = _read([a, b])
    assert all("según" not in s["text"] for s in apart)
    # a link of another kind is no dispute
    assert all("según" not in s["text"] for s in _read([a, b], [KnowledgeClaimLink(
        claim_id="c1", related_claim_id="c2", relation_type=ClaimRelationType.supports)]))


def test_only_the_links_of_the_entrys_statements_are_read():
    a = _born("c1", "1702-03-14", "1702-03-14", "day", "doc-a")
    b = _born("c2", "1704-01-01", "1704-12-31", "year", "doc-b")
    db = _Db([a, b], [_contradicts("c1", "c2"), _contradicts("x1", "x2"), _contradicts("c1", "x2")])
    sentences = render_entry_with_mentions(db, PAGE)[0]
    assert db.link_reads == [(KnowledgeClaimLink, "claim_id", ["c1", "c2"])]
    assert [s["claim_ids"] for s in sentences] == [["c1", "c2"]]


def test_a_confirmed_statement_in_a_dispute_is_said_plainly():
    a = _born("c1", "1702-03-14", "1702-03-14", "day", "doc-a", curation_state=ClaimCurationState.curated)
    b = _born("c2", "1704-01-01", "1704-12-31", "year", "doc-b")
    sentences = _read([a, b], [_contradicts("c1", "c2")])
    assert all("según" not in s["text"] for s in sentences)
    assert _clause(sentences, "c1")["doubt"] == "none"


def test_a_dispute_is_served_by_the_route(client, db):
    with db.defer_embeddings():
        entity = KnowledgeEntity(canonical_name="Ana")
        db.save(entity)
        rows = [KnowledgeClaim(text="Ana nació en Quibdó", svo_subject="Ana", svo_verb="nació en", svo_object=obj,
                               subject_entity_id=entity.id, entity_ids=[entity.id], source_languages=["es"],
                               source_document_id=doc)
                for obj, doc in (("Quibdó", "doc-1"), ("Nóvita", "doc-2"))]
        for row in rows:
            db.save(row)
        db.save(_contradicts(rows[1].id, rows[0].id))
    body = client.get(f"/api/kg/entities/{entity.id}/readable").json()
    assert body["paragraph"] == "Ana nació en Quibdó según una fuente y Nóvita según otra."
    assert [c["doubt"] for c in body["sentences"][0]["clauses"]] == ["disputed", "disputed"]
