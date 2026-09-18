"""Readable KG representation — the deterministic NLG pipeline.

spec: kg-readable-representation

Stage 1 (content determination) and stage 2 (document structuring / ordering) of the
Reiter & Dale pipeline. Pure functions over KnowledgeClaim, no LLM, no I/O — the
headless foundation the biography/regest/gazetteer renderings build on. Test-first.
"""
from __future__ import annotations

import pytest

from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.knowledge.readable import (
    Aggregation,
    Ordering,
    aggregate_claims,
    order_claims,
    select_entry_claims,
)


def _claim(text: str, **kw) -> KnowledgeClaim:
    return KnowledgeClaim(text=text, **kw)


# ---- Stage 1: content determination -------------------------------------------------

def test_selects_claims_where_subject_is_the_entity():
    c = _claim("A born in Quibdó", subject_entity_id="e1")
    other = _claim("B lived in Nóvita", subject_entity_id="e2")
    assert select_entry_claims([c, other], "e1") == [c]


def test_selects_claims_where_entity_is_mentioned_in_entity_ids():
    c = _claim("A witnessed B's will", subject_entity_id="e2", entity_ids=["e2", "e1"])
    assert select_entry_claims([c], "e1") == [c]


def test_excludes_unrelated_claims_and_empty_is_empty():
    other = _claim("B lived in Nóvita", subject_entity_id="e2", entity_ids=["e2"])
    assert select_entry_claims([other], "e1") == []
    assert select_entry_claims([], "e1") == []


def test_selection_preserves_input_order():
    a = _claim("first", subject_entity_id="e1")
    b = _claim("second", subject_entity_id="e1")
    assert select_entry_claims([a, b], "e1") == [a, b]


# ---- Stage 2: document structuring (ordering) ---------------------------------------

def test_chronological_orders_by_time_start():
    late = _claim("1799 event", time_start="1799-05-01")
    early = _claim("1780 event", time_start="1780-01-01")
    assert order_claims([late, early], Ordering.chronological) == [early, late]


def test_chronological_puts_undated_last_and_stable():
    dated = _claim("dated", time_start="1790-01-01")
    undated1 = _claim("undated one")
    undated2 = _claim("undated two")
    ordered = order_claims([undated1, dated, undated2], Ordering.chronological)
    assert ordered == [dated, undated1, undated2]  # dated first; undated keep input order


def test_by_source_groups_by_document_then_offset():
    d_a2 = _claim("doc A later", source_document_id="A", source_char_start=200)
    d_b = _claim("doc B", source_document_id="B", source_char_start=10)
    d_a1 = _claim("doc A earlier", source_document_id="A", source_char_start=50)
    ordered = order_claims([d_a2, d_b, d_a1], Ordering.by_source)
    # A's claims grouped and in offset order, then B's.
    assert ordered == [d_a1, d_a2, d_b]


def test_by_source_puts_sourceless_claims_last():
    manual = _claim("manually asserted")  # no source_document_id
    sourced = _claim("from a doc", source_document_id="A", source_char_start=0)
    assert order_claims([manual, sourced], Ordering.by_source) == [sourced, manual]


# ---- Stage 3: aggregation -----------------------------------------------------------

def _svo(s, v, o, **kw):
    return KnowledgeClaim(text=f"{s} {v} {o}", svo_subject=s, svo_verb=v, svo_object=o, **kw)


def test_aggregates_same_subject_verb_into_one_with_count_and_objects():
    a = _svo("Ana", "witnessed", "the Nóvita will")
    b = _svo("Ana", "witnessed", "the Quibdó sale")
    result = aggregate_claims([a, b])
    assert len(result) == 1
    agg = result[0]
    assert agg.subject == "Ana" and agg.verb == "witnessed"
    assert agg.count == 2
    assert agg.objects == ["the Nóvita will", "the Quibdó sale"]
    assert agg.claim_ids == [a.id, b.id]


def test_different_verbs_stay_separate_groups_in_first_seen_order():
    a = _svo("Ana", "witnessed", "a will")
    b = _svo("Ana", "owned", "a mine")
    result = aggregate_claims([a, b])
    assert [(g.verb, g.count) for g in result] == [("witnessed", 1), ("owned", 1)]


def test_aggregation_dedupes_objects_but_counts_every_claim():
    a = _svo("Ana", "witnessed", "a will")
    b = _svo("Ana", "witnessed", "a will")  # same object, distinct claim
    agg = aggregate_claims([a, b])[0]
    assert agg.count == 2
    assert agg.objects == ["a will"]  # distinct objects


def test_single_claim_aggregates_to_count_one():
    a = _svo("Ana", "born in", "Quibdó")
    agg = aggregate_claims([a])[0]
    assert agg.count == 1 and agg.objects == ["Quibdó"]


# ---- Stage 5: referring expressions -------------------------------------------------

def test_first_mention_uses_full_name():
    from fichero_server.knowledge.readable import referring_expression
    assert referring_expression("María de Córdoba", first_mention=True) == "María de Córdoba"


def test_subsequent_mention_uses_family_name():
    from fichero_server.knowledge.readable import referring_expression
    assert referring_expression("María de Córdoba", first_mention=False) == "Córdoba"


def test_single_token_name_is_unchanged_when_subsequent():
    from fichero_server.knowledge.readable import referring_expression
    assert referring_expression("Quibdó", first_mention=False) == "Quibdó"


def test_blank_name_is_empty():
    from fichero_server.knowledge.readable import referring_expression
    assert referring_expression("   ", first_mention=True) == ""


def test_aggregation_collects_place_distribution():
    # "seven witness appearances -> one sentence with a count and a place distribution"
    a = _svo("Ana", "witnessed", "a will", claim_location="Nóvita")
    b = _svo("Ana", "witnessed", "a sale", claim_location="Quibdó")
    c = _svo("Ana", "witnessed", "a deed", claim_location="Nóvita")  # duplicate place
    agg = aggregate_claims([a, b, c])[0]
    assert agg.count == 3
    assert agg.places == ["Nóvita", "Quibdó"]  # distinct, first-seen order


def test_aggregation_places_empty_when_no_locations():
    a = _svo("Ana", "born in", "Quibdó")
    assert aggregate_claims([a])[0].places == []


def test_chronological_falls_back_to_date_values_when_no_time_start():
    from fichero_server.models.knowledge import EvidenceBasis, EvidentialDateRange
    via_values = KnowledgeClaim(
        text="dated only via date_values",
        date_values=[EvidentialDateRange(basis=EvidenceBasis.asserted, start="1785-01-01")],
    )
    later = KnowledgeClaim(text="later, time_start", time_start="1799-01-01")
    # via_values (1785) sorts before later (1799) even though it has no time_start.
    assert order_claims([later, via_values], Ordering.chronological) == [via_values, later]


def test_chronological_uses_earliest_of_multiple_date_values():
    from fichero_server.models.knowledge import EvidenceBasis, EvidentialDateRange
    b = EvidenceBasis.asserted
    early = KnowledgeClaim(text="earliest wins", date_values=[
        EvidentialDateRange(basis=b, start="1799-01-01"),
        EvidentialDateRange(basis=b, start="1780-01-01"),
    ])
    mid = KnowledgeClaim(text="mid", time_start="1790-01-01")
    assert order_claims([mid, early], Ordering.chronological) == [early, mid]


# ---- Stage 6: realisation (Spanish + English) ---------------------------------------

def test_realises_single_claim_in_spanish():
    from fichero_server.knowledge.readable import render_aggregation
    agg = aggregate_claims([_svo("Ana", "nació en", "Quibdó")])[0]
    assert render_aggregation(agg, language="es") == "Ana nació en Quibdó."


def test_realises_aggregated_count_and_places_in_spanish():
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "atestiguó", "un testamento", claim_location="Nóvita")
    b = _svo("Ana", "atestiguó", "una venta", claim_location="Quibdó")
    c = _svo("Ana", "atestiguó", "una escritura", claim_location="Nóvita")
    agg = aggregate_claims([a, b, c])[0]
    assert render_aggregation(agg, language="es") == "Ana atestiguó 3 veces (en Nóvita y Quibdó)."


def test_realises_aggregated_count_and_places_in_english():
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "witnessed", "a will", claim_location="Nóvita")
    b = _svo("Ana", "witnessed", "a sale", claim_location="Quibdó")
    agg = aggregate_claims([a, b])[0]
    assert render_aggregation(agg, language="en") == "Ana witnessed 2 times (at Nóvita and Quibdó)."


def test_unknown_language_falls_back_to_english_glue():
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "witnessed", "a will", claim_location="Nóvita")
    b = _svo("Ana", "witnessed", "a sale", claim_location="Quibdó")
    agg = aggregate_claims([a, b])[0]
    assert render_aggregation(agg, language="xx") == "Ana witnessed 2 times (at Nóvita and Quibdó)."


# ---- The entry composer: render_entry(db, entity_id) — #4832 ------------------------


def _entity(db, canonical_name, **kw):
    from fichero_server.models.knowledge import KnowledgeEntity
    ent = KnowledgeEntity(canonical_name=canonical_name, **kw)
    db.save(ent)
    return ent


def test_render_entry_offsets_slice_back_to_the_exact_sentence_text(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "nació en", "Quibdó", subject_entity_id=ana.id, entity_ids=[ana.id])
    b = _svo("Ana", "murió en", "Nóvita", subject_entity_id=ana.id, entity_ids=[ana.id])
    db.save(a)
    db.save(b)

    sentences = render_entry(db, ana.id)
    paragraph = " ".join(s["text"] for s in sentences)
    for s in sentences:
        assert paragraph[s["start"] : s["end"]] == s["text"]


def test_render_entry_every_sentence_carries_its_claim_id(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "nació en", "Quibdó", subject_entity_id=ana.id, entity_ids=[ana.id])
    db.save(a)

    sentences = render_entry(db, ana.id)
    assert len(sentences) == 1
    assert sentences[0]["claim_ids"] == [a.id]


def test_render_entry_keeps_the_true_subject_when_the_page_entity_is_the_object(db):
    """A claim on the OBJECT's page must never make the page entity its subject --
    the wrong-subject defect this whole plan exists to remove."""
    from fichero_server.knowledge.readable import render_entry
    seller = _entity(db, "Marta Escobar")
    buyer = _entity(db, "Pedro Mosquera")
    sale = _svo(
        "Marta Escobar",
        "sold",
        "the mine to Pedro Mosquera",
        subject_entity_id=seller.id,
        entity_ids=[seller.id, buyer.id],
    )
    db.save(sale)

    sentences = render_entry(db, buyer.id)
    assert len(sentences) == 1
    assert sentences[0]["text"] == "Marta Escobar sold the mine to Pedro Mosquera."
    assert sentences[0]["role"] == "object"
    assert sentences[0]["revoiced"] is False

    # on the SELLER's page the same claim keeps the same true subject too
    seller_sentences = render_entry(db, seller.id)
    assert seller_sentences[0]["text"] == sentences[0]["text"]
    assert seller_sentences[0]["role"] == "subject"


def test_render_entry_spanish_claim_stays_spanish(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    claim = _svo(
        "Ana", "nació en", "Quibdó", subject_entity_id=ana.id, entity_ids=[ana.id],
        source_languages=["es"],
    )
    db.save(claim)

    sentences = render_entry(db, ana.id)
    assert sentences[0]["language"] == "es"
    assert sentences[0]["text"] == "Ana nació en Quibdó."


def test_render_entry_language_is_none_when_claim_carries_none(db):
    """Unknown stays unknown -- never a guessed language label."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    claim = _svo("Ana", "nació en", "Quibdó", subject_entity_id=ana.id, entity_ids=[ana.id])
    db.save(claim)
    assert render_entry(db, ana.id)[0]["language"] is None


def test_render_entry_object_role_needs_a_whole_word_match(db):
    """A page for "Ana" is a mention, not the object, of a claim about Anastasia."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    juan = _entity(db, "Juan")
    about_other = _svo("Juan", "pagó a", "Anastasia Mena", subject_entity_id=juan.id,
                       entity_ids=[juan.id, ana.id])
    about_ana = _svo("Juan", "pagó a", "Ana", subject_entity_id=juan.id,
                     entity_ids=[juan.id, ana.id])
    db.save(about_other)
    db.save(about_ana)
    roles = {s["text"]: s["role"] for s in render_entry(db, ana.id)}
    assert roles["Juan pagó a Anastasia Mena."] == "mention"
    assert roles["Juan pagó a Ana."] == "object"


def test_render_entry_orders_by_date_then_created_at_then_id(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    late = _svo(
        "Ana", "witnessed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id],
        time_start="1799-01-01",
    )
    early = _svo(
        "Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id],
        time_start="1780-01-01",
    )
    undated = _svo(
        "Ana", "witnessed", "a deed", subject_entity_id=ana.id, entity_ids=[ana.id],
    )
    # save in a deliberately scrambled order
    db.save(late)
    db.save(undated)
    db.save(early)

    sentences = render_entry(db, ana.id)
    assert [s["claim_ids"][0] for s in sentences] == [early.id, late.id, undated.id]


def test_render_entry_ordering_is_stable_across_repeated_calls(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id])
    b = _svo("Ana", "witnessed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id])
    db.save(a)
    db.save(b)

    first = [s["claim_ids"][0] for s in render_entry(db, ana.id)]
    second = [s["claim_ids"][0] for s in render_entry(db, ana.id)]
    assert first == second


def test_render_entry_no_claims_returns_empty_list(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    assert render_entry(db, ana.id) == []
