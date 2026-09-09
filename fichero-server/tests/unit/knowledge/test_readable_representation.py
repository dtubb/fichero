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
