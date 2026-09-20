"""Readable KG representation — the deterministic NLG pipeline.

spec: kg-readable-representation

Stage 1 (content determination) and stage 2 (document structuring / ordering) of the
Reiter & Dale pipeline. Pure functions over KnowledgeClaim, no LLM, no I/O — the
headless foundation the biography/regest/gazetteer renderings build on. Test-first.
"""
from __future__ import annotations


from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.knowledge.readable import (
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
    a = _svo("Ana", "witnessed", "the Nóvita will", subject_entity_id="ana", source_languages=["en"])
    b = _svo("Ana", "witnessed", "the Quibdó sale", subject_entity_id="ana", source_languages=["en"])
    result = aggregate_claims([a, b])
    assert len(result) == 1
    agg = result[0]
    assert agg.subject == "Ana" and agg.verb == "witnessed"
    assert agg.count == 2
    assert agg.objects == ["the Nóvita will", "the Quibdó sale"]
    assert agg.claim_ids == [a.id, b.id]


def test_different_verbs_stay_separate_groups_in_first_seen_order():
    a = _svo("Ana", "witnessed", "a will", subject_entity_id="ana")
    b = _svo("Ana", "owned", "a mine", subject_entity_id="ana")
    result = aggregate_claims([a, b])
    assert [(g.verb, g.count) for g in result] == [("witnessed", 1), ("owned", 1)]


def test_aggregation_dedupes_objects_but_counts_every_claim():
    a = _svo("Ana", "witnessed", "a will", subject_entity_id="ana", source_languages=["en"])
    b = _svo("Ana", "witnessed", "a will", subject_entity_id="ana", source_languages=["en"])  # same object, distinct claim
    agg = aggregate_claims([a, b])[0]
    assert agg.count == 2
    assert agg.objects == ["a will"]  # distinct objects


def test_single_claim_aggregates_to_count_one():
    a = _svo("Ana", "born in", "Quibdó")
    agg = aggregate_claims([a])[0]
    assert agg.count == 1 and agg.objects == ["Quibdó"]


def test_a_claim_with_no_resolved_subject_entity_never_merges():
    """Ruling A (#4836): text-only identity is not safe enough to found a
    merge on -- a claim with no resolved subject entity always groups
    alone, even against another claim with matching subject/verb TEXT."""
    a = _svo("Ana", "witnessed", "a will")  # no subject_entity_id
    b = _svo("Ana", "witnessed", "a sale")  # no subject_entity_id
    result = aggregate_claims([a, b])
    assert len(result) == 2
    assert {g.claim_ids[0] for g in result} == {a.id, b.id}


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
    a = _svo("Ana", "witnessed", "a will", claim_location="Nóvita", subject_entity_id="ana", source_languages=["en"])
    b = _svo("Ana", "witnessed", "a sale", claim_location="Quibdó", subject_entity_id="ana", source_languages=["en"])
    c = _svo("Ana", "witnessed", "a deed", claim_location="Nóvita", subject_entity_id="ana", source_languages=["en"])  # duplicate place
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


def test_realises_aggregated_objects_and_places_in_spanish():
    """kg.read.aggregation-keeps-objects (#4649): a count used to REPLACE the
    objects here ("atestiguó 3 veces") -- fixed to always list them."""
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "atestiguó", "un testamento", claim_location="Nóvita", subject_entity_id="ana", source_languages=["es"])
    b = _svo("Ana", "atestiguó", "una venta", claim_location="Quibdó", subject_entity_id="ana", source_languages=["es"])
    c = _svo("Ana", "atestiguó", "una escritura", claim_location="Nóvita", subject_entity_id="ana", source_languages=["es"])
    agg = aggregate_claims([a, b, c])[0]
    assert render_aggregation(agg, language="es") == (
        "Ana atestiguó un testamento, una venta y una escritura (en Nóvita y Quibdó)."
    )


def test_realises_aggregated_objects_and_places_in_english():
    """kg.read.aggregation-keeps-objects (#4649): see the Spanish case above."""
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "witnessed", "a will", claim_location="Nóvita", subject_entity_id="ana", source_languages=["en"])
    b = _svo("Ana", "witnessed", "a sale", claim_location="Quibdó", subject_entity_id="ana", source_languages=["en"])
    agg = aggregate_claims([a, b])[0]
    assert render_aggregation(agg, language="en") == (
        "Ana witnessed a will and a sale (at Nóvita and Quibdó)."
    )


def test_a_declared_language_with_no_glue_table_never_merges():
    """kg.read.aggregation-never-crosses-languages, kg.read.source-language-only
    (#4836): a language that IS declared but has no glue table ("fr") used to
    merge and take English "and" inside a French sentence. A language the
    module cannot join in, it does not join: each claim stays its own sentence,
    in its own words. The empty-language case is the same rule."""
    from fichero_server.knowledge.readable import render_aggregation
    a = _svo("Ana", "témoigna", "un testament", source_languages=["fr"], subject_entity_id="ana")
    b = _svo("Ana", "témoigna", "une vente", source_languages=["fr"], subject_entity_id="ana")
    result = aggregate_claims([a, b])
    assert len(result) == 2
    rendered = " ".join(render_aggregation(g, g.language or "en") for g in result)
    assert " and " not in rendered

def test_aggregation_never_crosses_languages_even_with_matching_text():
    """The bug, run: two claims whose subject/verb TEXT happens to match --
    one Spanish, one English -- used to merge into one group because the old
    key was (subject, verb) text only and never looked at language at all.
    Same resolved subject entity, so ruling A does not also explain the
    split -- language alone must."""
    es = _svo("Ana", "murio en", "Quibdo", source_languages=["es"], subject_entity_id="ana")
    en = _svo("Ana", "murio en", "Novita", source_languages=["en"], subject_entity_id="ana")
    result = aggregate_claims([es, en])
    assert len(result) == 2
    assert {g.language for g in result} == {"es", "en"}


def test_aggregation_groups_share_a_language_field():
    a = _svo("Ana", "witnessed", "a will", source_languages=["en"], subject_entity_id="ana")
    b = _svo("Ana", "witnessed", "a sale", source_languages=["en"], subject_entity_id="ana")
    agg = aggregate_claims([a, b])[0]
    assert agg.language == "en"


# ---- same name, different entity ids never merge -------------------------------------


def test_same_name_different_entity_ids_never_merge():
    """A father and son (or two unrelated namesakes) sharing a written name
    must never merge just because the text normalizes the same way."""
    father = _svo("Juan Perez", "sold", "a mine", subject_entity_id="ent-father")
    son = _svo("Juan Perez", "sold", "a house", subject_entity_id="ent-son")
    result = aggregate_claims([father, son])
    assert len(result) == 2
    assert {g.subject_entity_id for g in result} == {"ent-father", "ent-son"}


def test_same_entity_id_still_merges_regardless_of_name_spelling_drift():
    """The identity key is entity-id-first: once resolved, spelling drift in
    the extracted subject text (OCR, alias) does not re-split an aggregation."""
    a = _svo("Juan Perez", "sold", "a mine", subject_entity_id="ent-1", source_languages=["en"])
    b = _svo("Juan Pérez", "sold", "a house", subject_entity_id="ent-1", source_languages=["en"])
    result = aggregate_claims([a, b])
    assert len(result) == 1
    assert result[0].objects == ["a mine", "a house"]


# ---- ruling B: a prepositional object never merges with anything (#4836) -------------
#
# The real extraction shape (since 7c6f1aae5): a sale with a recipient is TWO claims
# sharing subject+verb -- (subject, "sold", "the mine") and (subject, "sold",
# "to Pedro Mosquera") -- not one claim with a combined object phrase.


def test_object_slot_is_prepositional_matches_the_claims_own_language():
    from fichero_server.knowledge.readable import _is_prepositional_object
    assert _is_prepositional_object("to Pedro Mosquera", "en") is True
    assert _is_prepositional_object("a Pedro Mosquera", "es") is True
    assert _is_prepositional_object("a Pedro Mosquera", "en") is False  # not English's table
    assert _is_prepositional_object("the mine", "en") is False
    assert _is_prepositional_object("a will", "es") is True  # "a" IS a Spanish preposition
    assert _is_prepositional_object("a will", None) is False  # unknown language: not flagged
    assert _is_prepositional_object(None, "en") is False


def test_prepositional_object_never_merges_with_a_plain_one_english():
    """The real two-claim sale shape: the recipient claim must stay solo."""
    patient = _svo("Juan Asprilla", "sold", "the mine",
                    subject_entity_id="asprilla", source_languages=["en"])
    recipient = _svo("Juan Asprilla", "sold", "to Pedro Mosquera",
                      subject_entity_id="asprilla", source_languages=["en"])
    result = aggregate_claims([patient, recipient])
    assert len(result) == 2
    assert {g.claim_ids[0] for g in result} == {patient.id, recipient.id}


def test_prepositional_object_never_merges_with_a_plain_one_spanish():
    """The gravest case named in the ruling: Spanish "a" marks a PERSON
    direct object, so this pair must never merge under one conjunction."""
    patient = _svo("Juan Asprilla", "vendió", "la mina",
                    subject_entity_id="asprilla", source_languages=["es"])
    recipient = _svo("Juan Asprilla", "vendió", "a Pedro Mosquera",
                      subject_entity_id="asprilla", source_languages=["es"])
    result = aggregate_claims([patient, recipient])
    assert len(result) == 2
    assert {g.claim_ids[0] for g in result} == {patient.id, recipient.id}


def test_two_prepositional_objects_never_merge_with_each_other_either():
    """Ruling B is unconditional: a prepositional-object claim never merges
    with ANYTHING, including another prepositional-object claim."""
    a = _svo("Juan Asprilla", "sold", "to Pedro Mosquera",
             subject_entity_id="asprilla", source_languages=["en"])
    b = _svo("Juan Asprilla", "sold", "to Marta Escobar",
             subject_entity_id="asprilla", source_languages=["en"])
    result = aggregate_claims([a, b])
    assert len(result) == 2


def test_plain_objects_still_merge_when_one_sibling_claim_is_prepositional():
    """A group of three where one object is prepositional merges the two
    plain ones and leaves the third alone, in stable order."""
    plain1 = _svo("Juan Asprilla", "sold", "the mine",
                   subject_entity_id="asprilla", source_languages=["en"])
    prepositional = _svo("Juan Asprilla", "sold", "to Pedro Mosquera",
                          subject_entity_id="asprilla", source_languages=["en"])
    plain2 = _svo("Juan Asprilla", "sold", "a house",
                  subject_entity_id="asprilla", source_languages=["en"])
    result = aggregate_claims([plain1, prepositional, plain2])
    assert len(result) == 2
    plain_group = next(g for g in result if g.count == 2)
    solo_group = next(g for g in result if g.count == 1)
    assert plain_group.objects == ["the mine", "a house"]
    assert plain_group.claim_ids == [plain1.id, plain2.id]
    assert solo_group.claim_ids == [prepositional.id]


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
    """A page for "Ana" is a mention, not the object, of a claim about Anastasia.

    Distinct verbs deliberately: same-subject-same-verb claims now MERGE
    (#4839/#4649, tested separately below), and this test is about the
    per-claim role inference, not aggregation.
    """
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    juan = _entity(db, "Juan")
    about_other = _svo("Juan", "pagó a", "Anastasia Mena", subject_entity_id=juan.id,
                       entity_ids=[juan.id, ana.id])
    about_ana = _svo("Juan", "escribió a", "Ana", subject_entity_id=juan.id,
                     entity_ids=[juan.id, ana.id])
    db.save(about_other)
    db.save(about_ana)
    roles = {s["text"]: s["role"] for s in render_entry(db, ana.id)}
    assert roles["Juan pagó a Anastasia Mena."] == "mention"
    assert roles["Juan escribió a Ana."] == "object"


def test_render_entry_orders_by_date_then_created_at_then_id(db):
    """Distinct verbs deliberately: same-subject-same-verb claims now MERGE
    (#4839/#4649, tested separately below), and this test is about ordering,
    not aggregation."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    late = _svo(
        "Ana", "signed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id],
        time_start="1799-01-01",
    )
    early = _svo(
        "Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id],
        time_start="1780-01-01",
    )
    undated = _svo(
        "Ana", "recorded", "a deed", subject_entity_id=ana.id, entity_ids=[ana.id],
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


def test_render_entry_includes_a_subject_claim_missing_from_its_own_entity_ids(db):
    """The two fields drift in real libraries; a subject's claim is never dropped."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    drifted = _svo("Ana", "nació en", "Quibdó", subject_entity_id=ana.id, entity_ids=[])
    db.save(drifted)
    sentences = render_entry(db, ana.id)
    assert [s["claim_ids"] for s in sentences] == [[drifted.id]]
    assert sentences[0]["role"] == "subject"


# ---- render_entry aggregation wiring (#4839/#4649) -----------------------------------
#
# aggregate_claims (stage 3) is now called by render_entry: claims sharing a subject
# IDENTITY and a verb (and language) merge into one sentence listing their objects.


def test_render_entry_sale_with_recipient_is_the_real_two_claim_shape_english(db):
    """The REAL extraction shape (since 7c6f1aae5, #4836): a sale with a
    recipient is TWO claims sharing subject+verb -- (subject, "sold", "the
    mine") and (subject, "sold", "to Pedro Mosquera") -- not one claim with
    a combined object phrase. Ruling B: the recipient claim is
    prepositional and must never merge, in EITHER language -- coordinating
    "the mine and to Pedro Mosquera" under one conjunction would misread the
    recipient as another thing sold."""
    from fichero_server.knowledge.readable import render_entry
    seller = _entity(db, "Marta Escobar")
    buyer = _entity(db, "Pedro Mosquera")
    patient = _svo(
        "Marta Escobar", "sold", "the mine",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["en"], time_start="1780-01-01",
    )
    recipient = _svo(
        "Marta Escobar", "sold", "to Pedro Mosquera",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["en"], time_start="1780-01-01",
    )
    db.save(recipient)
    db.save(patient)

    sentences = render_entry(db, seller.id)
    assert len(sentences) == 2
    texts = [s["text"] for s in sentences]
    assert texts == ["Marta Escobar sold the mine.", "Marta Escobar sold to Pedro Mosquera."]
    assert " and to " not in " ".join(texts)
    assert {s["claim_ids"][0] for s in sentences} == {patient.id, recipient.id}


def test_render_entry_sale_with_recipient_is_the_real_two_claim_shape_spanish(db):
    """The gravest case named in the ruling: Spanish "a" marks a PERSON
    direct object, so coordinating "la mina y a Pedro Mosquera" under "y"
    would read as Pedro being sold alongside the mine -- exactly the false
    sentence #4836 removed from extraction. Must render as two sentences."""
    from fichero_server.knowledge.readable import render_entry
    seller = _entity(db, "Marta Escobar")
    buyer = _entity(db, "Pedro Mosquera")
    patient = _svo(
        "Marta Escobar", "vendió", "la mina",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["es"], time_start="1780-01-01",
    )
    recipient = _svo(
        "Marta Escobar", "vendió", "a Pedro Mosquera",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["es"], time_start="1780-01-01",
    )
    db.save(recipient)
    db.save(patient)

    sentences = render_entry(db, seller.id)
    assert len(sentences) == 2
    texts = [s["text"] for s in sentences]
    assert texts == ["Marta Escobar vendió la mina.", "Marta Escobar vendió a Pedro Mosquera."]
    assert " y a " not in " ".join(texts)
    assert {s["claim_ids"][0] for s in sentences} == {patient.id, recipient.id}


def test_render_entry_merge_keeps_every_source_claim_id_in_order(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id], source_languages=["en"])
    b = _svo("Ana", "witnessed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id], source_languages=["en"])
    c = _svo("Ana", "witnessed", "a deed", subject_entity_id=ana.id, entity_ids=[ana.id], source_languages=["en"])
    db.save(a)
    db.save(b)
    db.save(c)
    sentences = render_entry(db, ana.id)
    assert len(sentences) == 1
    assert set(sentences[0]["claim_ids"]) == {a.id, b.id, c.id}
    assert "a will" in sentences[0]["text"]
    assert "a sale" in sentences[0]["text"]
    assert "a deed" in sentences[0]["text"]


def test_render_entry_never_merges_across_languages(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    es = _svo(
        "Ana", "murio en", "Quibdo", subject_entity_id=ana.id, entity_ids=[ana.id],
        source_languages=["es"],
    )
    en = _svo(
        "Ana", "murio en", "Novita", subject_entity_id=ana.id, entity_ids=[ana.id],
        source_languages=["en"],
    )
    db.save(es)
    db.save(en)
    sentences = render_entry(db, ana.id)
    assert len(sentences) == 2
    assert {s["language"] for s in sentences} == {"es", "en"}
    assert {s["claim_ids"][0] for s in sentences} == {es.id, en.id}


def test_render_entry_never_merges_same_name_different_entity_ids(db):
    """A father and son with the same written name, on the SAME page they
    both happen to be mentioned from, must never merge into one sentence
    that would misattribute one's act to the other."""
    from fichero_server.knowledge.readable import render_entry
    witness = _entity(db, "Testigo")
    father = _entity(db, "Juan Perez")
    son = _entity(db, "Juan Perez")
    father_claim = _svo(
        "Juan Perez", "sold", "a mine",
        subject_entity_id=father.id, entity_ids=[father.id, witness.id],
    )
    son_claim = _svo(
        "Juan Perez", "sold", "a house",
        subject_entity_id=son.id, entity_ids=[son.id, witness.id],
    )
    db.save(father_claim)
    db.save(son_claim)
    sentences = render_entry(db, witness.id)
    assert len(sentences) == 2
    assert {s["claim_ids"][0] for s in sentences} == {father_claim.id, son_claim.id}


def test_render_entry_offsets_still_slice_after_a_merge(db):
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id])
    b = _svo("Ana", "witnessed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id])
    c = _svo("Ana", "murió en", "Quibdó", subject_entity_id=ana.id, entity_ids=[ana.id])
    db.save(a)
    db.save(b)
    db.save(c)

    sentences = render_entry(db, ana.id)
    paragraph = " ".join(s["text"] for s in sentences)
    for s in sentences:
        assert paragraph[s["start"] : s["end"]] == s["text"]


def test_render_entry_merge_never_implies_order_or_cause_beyond_the_conjunction(db):
    """A merged sentence states its objects joined by a plain conjunction
    only -- never "then", "because", or any word implying sequence/causation
    the source claims do not themselves state."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo("Ana", "witnessed", "a will", subject_entity_id=ana.id, entity_ids=[ana.id], source_languages=["en"])
    b = _svo("Ana", "witnessed", "a sale", subject_entity_id=ana.id, entity_ids=[ana.id], source_languages=["en"])
    db.save(a)
    db.save(b)
    text = render_entry(db, ana.id)[0]["text"]
    for forbidden in (" then ", " because ", " so ", " therefore "):
        assert forbidden not in text
    assert text == "Ana witnessed a will and a sale."


def test_render_entry_spanish_merge_example(db, capsys):
    """Printed for the report: one Spanish merge example."""
    from fichero_server.knowledge.readable import render_entry
    ana = _entity(db, "Ana")
    a = _svo(
        "Ana", "atestiguó", "un testamento", subject_entity_id=ana.id, entity_ids=[ana.id],
        source_languages=["es"],
    )
    b = _svo(
        "Ana", "atestiguó", "una venta", subject_entity_id=ana.id, entity_ids=[ana.id],
        source_languages=["es"],
    )
    db.save(a)
    db.save(b)
    sentences = render_entry(db, ana.id)
    print("\n[readable/es] " + sentences[0]["text"])
    assert sentences[0]["text"] == "Ana atestiguó un testamento y una venta."
    assert sentences[0]["language"] == "es"
    assert sentences[0]["claim_ids"] == [a.id, b.id]


def test_render_entry_english_sale_with_recipient_example(db, capsys):
    """Printed for the report: the REAL two-claim sale shape in English --
    a plain patient claim plus a prepositional recipient claim -- rendered
    as two sentences, never coordinated under "and"."""
    from fichero_server.knowledge.readable import render_entry
    seller = _entity(db, "Marta Escobar")
    buyer = _entity(db, "Pedro Mosquera")
    patient = _svo(
        "Marta Escobar", "sold", "the mine",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["en"],
    )
    recipient = _svo(
        "Marta Escobar", "sold", "to Pedro Mosquera",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["en"],
    )
    db.save(patient)
    db.save(recipient)
    sentences = render_entry(db, seller.id)
    text = " ".join(s["text"] for s in sentences)
    print("\n[readable/en] " + text)
    assert text == "Marta Escobar sold the mine. Marta Escobar sold to Pedro Mosquera."
    assert " and to " not in text
    assert {s["claim_ids"][0] for s in sentences} == {patient.id, recipient.id}


def test_render_entry_spanish_sale_with_recipient_example(db, capsys):
    """Printed for the report: the same real two-claim sale shape in
    Spanish, where the risk is gravest -- "a" marks a PERSON direct object."""
    from fichero_server.knowledge.readable import render_entry
    seller = _entity(db, "Marta Escobar")
    buyer = _entity(db, "Pedro Mosquera")
    patient = _svo(
        "Marta Escobar", "vendió", "la mina",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["es"],
    )
    recipient = _svo(
        "Marta Escobar", "vendió", "a Pedro Mosquera",
        subject_entity_id=seller.id, entity_ids=[seller.id, buyer.id],
        source_languages=["es"],
    )
    db.save(patient)
    db.save(recipient)
    sentences = render_entry(db, seller.id)
    text = " ".join(s["text"] for s in sentences)
    print("\n[readable/es] " + text)
    assert text == "Marta Escobar vendió la mina. Marta Escobar vendió a Pedro Mosquera."
    assert " y a " not in text
    assert {s["claim_ids"][0] for s in sentences} == {patient.id, recipient.id}


def test_render_entry_never_merges_two_entity_less_same_name_claims(db):
    """Ruling A, at the render_entry level: two claims with the SAME written
    subject name but no resolved subject_entity_id at all must never merge
    -- a father and son sharing a name, neither yet linked to an entity."""
    from fichero_server.knowledge.readable import render_entry
    witness = _entity(db, "Testigo")
    a = _svo("Juan Perez", "witnessed", "a will", entity_ids=[witness.id])
    b = _svo("Juan Perez", "witnessed", "a sale", entity_ids=[witness.id])
    db.save(a)
    db.save(b)
    sentences = render_entry(db, witness.id)
    assert len(sentences) == 2
    assert {s["claim_ids"][0] for s in sentences} == {a.id, b.id}


def test_a_claim_that_declares_no_language_never_merges():
    """kg.read.aggregation-never-crosses-languages, kg.read.object-slot-has-no-role
    (#4836): with no declared language the prepositional check cannot run, so a
    recipient would merge and English glue would land in a Spanish sentence."""
    from fichero_server.knowledge.readable import aggregate_claims, render_aggregation

    sold = _svo("Juan Asprilla", "vendió", "la mina", subject_entity_id="e1", entity_ids=["e1"])
    to = _svo("Juan Asprilla", "vendió", "a Pedro Mosquera", subject_entity_id="e1", entity_ids=["e1"])
    sold.source_languages = []
    to.source_languages = []
    groups = aggregate_claims([sold, to])
    assert len(groups) == 2
    rendered = " ".join(render_aggregation(g, g.language or "en") for g in groups)
    assert " and a " not in rendered and " y a " not in rendered
