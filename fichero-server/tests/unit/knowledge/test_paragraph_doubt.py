"""Doubt in the paragraph: a person's decision, sources in words, a single unsure source (#6839).

spec: kg-paragraph-realisation (`kg.para.doubt-is-attribution`, `kg.para.no-figure-no-hedge`,
`kg.para.sources-are-counted-in-words`, `kg.para.person-decision-is-plain`)
"""
from __future__ import annotations

import re

from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)

PAGE = "ent-ines"


class _Db:
    def __init__(self, claims, links=()):
        self.claims = claims
        self.links = list(links)
        self.entity = KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel")

    def get(self, model, key):
        return self.entity

    def query_json_list_intersects(self, model, field, values):
        return list(self.claims)

    def query(self, model, **kw):
        return [x for x in self.links if all(getattr(x, k) == v for k, v in kw.items())] if model.__name__ == "KnowledgeClaimLink" else []

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
    entity = KnowledgeEntity(canonical_name="Ana")
    db.save(entity)
    claim = KnowledgeClaim(text="Ana vendió una casa", svo_subject="Ana", svo_verb="vendió", svo_object="una casa",
                           subject_entity_id=entity.id, entity_ids=[entity.id], source_languages=["es"],
                           source_document_id="doc-1", epistemic_status=EpistemicStatus.tentative)
    db.save(claim)
    body = client.get(f"/api/kg/entities/{entity.id}/readable").json()
    assert body["paragraph"] == "Ana, al parecer, vendió una casa (una sola fuente)."
    assert body["sentences"][0]["clauses"][0]["doubt"] == "one_source_unsure"
