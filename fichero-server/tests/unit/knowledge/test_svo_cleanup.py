from types import SimpleNamespace

import pytest

from fichero_server.knowledge.svo_cleanup import (
    clean_svo_claims,
    collapse_dated_claims,
    collapse_near_duplicate_claims,
)


def _claim(id, subject, verb, object_phrase):
    return SimpleNamespace(id=id, subject_canonical=subject, predicate_verb=verb, object_phrase=object_phrase)


def test_dehyphenates_words_but_not_digit_ranges():
    clauses = clean_svo_claims([_claim("a", "Ana", "trans-\nferred", "land in 1830- 31")])
    assert clauses[0].predicate_verb == "transferred"
    assert clauses[0].object_phrase == "land in 1830- 31"


def test_dedup_preserves_sources_but_keeps_distinct_facts():
    clauses = clean_svo_claims([
        _claim("a", "Ana", "gave", "the house to Pedro"),
        _claim("b", "Ana", "given", "the house to Pedro"),
        _claim("c", "Ana", "gave", "the farm to Pedro"),
    ])
    assert len(clauses) == 2
    assert clauses[0].source_claim_ids == ("a", "b")
    assert clauses[1].source_claim_ids == ("c",)


def test_strips_only_leading_repeated_subject():
    clause = clean_svo_claims([_claim("a", "Ana", "said", "Ana: Pedro met Ana")])[0]
    assert clause.object_phrase == "Pedro met Ana"


def test_filler_determiner_insertion_collapses():
    # The gap beta testers hit: an inserted "said"/"the" left near-duplicates
    # standing because the old rule demanded an identical token SET.
    clauses = clean_svo_claims([
        _claim("a", "Ana", "signed", "the deed"),
        _claim("b", "Ana", "signed", "the said deed"),
    ])
    assert len(clauses) == 1
    assert clauses[0].source_claim_ids == ("a", "b")


def test_a_different_number_is_kept_distinct():
    clauses = clean_svo_claims([
        _claim("a", "Ana", "paid", "3 pesos"),
        _claim("b", "Ana", "paid", "5 pesos"),
    ])
    assert len(clauses) == 2


def test_an_added_date_is_kept_distinct():
    clauses = clean_svo_claims([
        _claim("a", "Ana", "held", "the office"),
        _claim("b", "Ana", "held", "the office in 1830"),
    ])
    assert len(clauses) == 2


# ---------------------------------------------------------------------------
# collapse_near_duplicate_claims — the missing piece on the LLM extraction path
# (_extract_claims_for_entity, shared by extract_all + extract_svo_only). That
# path already trims + rejects each claim; what it never did was collapse two
# SURVIVING claims that say the same thing — the repetition Daniel saw on the
# Istmina run. These prove the collapse measurably reduces repetition while
# keeping every genuinely distinct fact.
# ---------------------------------------------------------------------------


def test_istmina_repetition_before_after_counts():
    """A per-entity batch AS IT LEAVES the per-claim gate (already trimmed and
    rejected): 6 valid claims in, 4 distinct claims out — the two near-dups
    Daniel's run left standing are collapsed."""
    subject = "Andrés Restrepo"
    kept_by_gate = [
        {"verb": "otorgó", "object": "poder a Juan Pérez", "claim_type": "action"},
        # Exact duplicate — the model re-asserting across chunks.
        {"verb": "otorgó", "object": "poder a Juan Pérez"},
        # Near-duplicate — a determiner ("el") inserted, same statement.
        {"verb": "otorgó", "object": "el poder a Juan Pérez"},
        # Distinct fact — different object.
        {"verb": "vendió", "object": "una mina en Istmina por 300 pesos"},
        # Distinct fact — SAME shape, different NUMBER: must survive.
        {"verb": "vendió", "object": "una mina en Istmina por 500 pesos"},
        # Distinct fact — a date-extended assertion is its own fact.
        {"verb": "ocupó", "object": "el cargo en 1830"},
    ]

    cleaned = collapse_near_duplicate_claims(subject, kept_by_gate)

    # BEFORE: 6 surviving-but-repetitive claims. AFTER: 4 distinct claims.
    assert len(kept_by_gate) == 6
    assert len(cleaned) == 4

    verbs_objects = [(c["verb"], c["object"]) for c in cleaned]
    assert ("otorgó", "poder a Juan Pérez") in verbs_objects
    assert ("vendió", "una mina en Istmina por 300 pesos") in verbs_objects
    assert ("vendió", "una mina en Istmina por 500 pesos") in verbs_objects
    assert ("ocupó", "el cargo en 1830") in verbs_objects


def test_collapse_keeps_first_occurrence_with_all_its_fields():
    cleaned = collapse_near_duplicate_claims(
        "Ana",
        [
            {
                "verb": "viajó a",
                "object": "Istmina",
                "source_text": "salí para Istmina",
                "epistemic_status": "asserted",
                "claim_type": "movement",
            },
            {"verb": "viajó a", "object": "Istmina"},  # near-dup, dropped
        ],
    )
    assert len(cleaned) == 1
    assert cleaned[0]["source_text"] == "salí para Istmina"
    assert cleaned[0]["epistemic_status"] == "asserted"
    assert cleaned[0]["claim_type"] == "movement"


def test_collapse_keeps_distinct_numbers_and_date_extensions():
    cleaned = collapse_near_duplicate_claims(
        "Ana",
        [
            {"verb": "pagó", "object": "3 pesos"},
            {"verb": "pagó", "object": "5 pesos"},
            {"verb": "ocupó", "object": "el cargo"},
            {"verb": "ocupó", "object": "el cargo en 1830"},
        ],
    )
    assert len(cleaned) == 4


def test_collapse_never_merges_across_different_subjects():
    # The helper is called per subject, so a different subject is a separate
    # call; within one subject a leading subject copy in the object is folded.
    cleaned = collapse_near_duplicate_claims(
        "Andrés",
        [
            {"verb": "otorgó", "object": "Andrés poder a Juan"},
            {"verb": "otorgó", "object": "poder a Juan"},
        ],
    )
    assert len(cleaned) == 1


# ---------------------------------------------------------------------------
# collapse_dated_claims — the same collapse for the claim-only DATE rows that
# extract_svo_only writes outside the per-entity loop.
# ---------------------------------------------------------------------------


def test_dated_claims_fold_within_a_date_but_stay_distinct_across_dates():
    claims = [
        {"date": "1830", "date_normalized": "1830-01-01", "verb": "firmó", "object": "la escritura"},
        # Same date, near-dup ("dicha" is notarial filler) — collapses.
        {"date": "1830", "date_normalized": "1830-01-01", "verb": "firmó", "object": "la dicha escritura"},
        # Same statement but a DIFFERENT date — a distinct fact, kept.
        {"date": "1842", "date_normalized": "1842-01-01", "verb": "firmó", "object": "la escritura"},
    ]
    cleaned = collapse_dated_claims(claims)
    assert len(cleaned) == 2
    assert sorted(c["date_normalized"] for c in cleaned) == ["1830-01-01", "1842-01-01"]


def test_dated_claims_fall_back_to_as_written_date_and_carry_fields():
    claims = [
        {"date": "el año de 1830", "verb": "nació", "object": "en Istmina", "source_text": "nació en Istmina"},
        {"date": "el año de 1830", "verb": "nació", "object": "en Istmina"},  # exact dup
    ]
    cleaned = collapse_dated_claims(claims)
    assert len(cleaned) == 1
    assert cleaned[0]["source_text"] == "nació en Istmina"


def test_dated_claims_keep_distinct_statements_on_one_date():
    claims = [
        {"date_normalized": "1830-01-01", "verb": "firmó", "object": "la escritura"},
        {"date_normalized": "1830-01-01", "verb": "pagó", "object": "300 pesos"},
    ]
    assert len(collapse_dated_claims(claims)) == 2


# ---------------------------------------------------------------------------
# QUALITY AUDIT (Daniel: "deduping svo... they need to be good"). A single
# realistic batch mixing GENUINE near-duplicates with GENUINE distinct claims,
# with a measured collapse ratio and — the load-bearing half — assertions that
# every distinct claim SURVIVES. These fail if dedup regresses to either
# over-merging (a distinct claim disappears) or under-merging (a dup survives).
# ---------------------------------------------------------------------------


def test_svo_dedup_quality_collapses_dups_never_merges_distinct():
    subject = "Andrés Restrepo"
    batch = [
        # --- one true statement, said four ways (all must collapse to 1) ---
        {"verb": "otorgó", "object": "poder a Juan Pérez"},
        {"verb": "otorgó", "object": "poder a Juan Pérez"},          # exact
        {"verb": "otorgó", "object": "el poder a Juan Pérez"},       # determiner
        {"verb": "otorgó", "object": "el mismo poder a Juan Pérez"}, # determiner + filler
        # --- genuinely DISTINCT claims (every one must survive) ---
        {"verb": "vendió", "object": "la mina a Juan Pérez"},        # different verb
        {"verb": "otorgó", "object": "poder a Pedro Lozano"},        # different object head
        {"verb": "pagó", "object": "300 pesos"},                     # numbers
        {"verb": "pagó", "object": "500 pesos"},                     # different number
        {"verb": "compró", "object": "la casa"},
        {"verb": "compró", "object": "la casa en 1842"},             # date-extended = distinct
    ]

    cleaned = collapse_near_duplicate_claims(subject, batch)

    # The 4 phrasings of "otorgó poder a Juan Pérez" collapse to 1; the other 6
    # are all distinct. 10 → 7.
    assert len(batch) == 10
    assert len(cleaned) == 7

    survivors = {(c["verb"], c["object"]) for c in cleaned}
    # Every DISTINCT claim survived — no false merge.
    for must_survive in [
        ("vendió", "la mina a Juan Pérez"),
        ("otorgó", "poder a Pedro Lozano"),
        ("pagó", "300 pesos"),
        ("pagó", "500 pesos"),
        ("compró", "la casa"),
        ("compró", "la casa en 1842"),
    ]:
        assert must_survive in survivors, f"distinct claim wrongly merged: {must_survive}"

    # The repetition is gone: exactly one "otorgó … Juan Pérez" statement remains.
    juan_statements = [c for c in cleaned if "Juan Pérez" in c["object"] and c["verb"] == "otorgó"]
    assert len(juan_statements) == 1


def test_svo_dedup_collapses_spanish_contraction_variants():
    # Approved widening of _FILLER_WORDS with de/del/al: a Spanish
    # preposition/contraction difference is not a different statement.
    cleaned = collapse_near_duplicate_claims(
        "Andrés",
        [
            {"verb": "otorgó", "object": "poder a Juan"},
            {"verb": "otorgó", "object": "poder al dicho Juan"},
            {"verb": "otorgó", "object": "poder del rey"},  # distinct: different noun
        ],
    )
    # "poder a Juan" == "poder al dicho Juan" (function words only); "poder del
    # rey" is a different statement (rey is a content word).
    assert len(cleaned) == 2


def test_widened_filler_never_merges_distinct_content():
    # The guard the lead required: after adding de/del/al, statements differing
    # only in CONTENT (names, nouns, numbers) MUST stay distinct.
    cleaned = collapse_near_duplicate_claims(
        "Andrés",
        [
            {"verb": "otorgó", "object": "poder a Juan"},
            {"verb": "otorgó", "object": "poder a Pedro"},        # different name
            {"verb": "vendió", "object": "casa de campo"},
            {"verb": "vendió", "object": "casa de playa"},        # different noun
            {"verb": "pagó", "object": "de 3 pesos"},
            {"verb": "pagó", "object": "de 5 pesos"},             # different number
            {"verb": "es", "object": "hijo del gobernador"},
            {"verb": "es", "object": "hijo del alcalde"},         # different role noun
        ],
    )
    # Every pair differs by a content token — none may collapse.
    assert len(cleaned) == 8


def test_svo_dedup_respects_word_order():
    # Same content words, different order = different statement — must NOT
    # collapse (statement_key keeps token order).
    cleaned = collapse_near_duplicate_claims(
        "Pedro",
        [
            {"verb": "prestó", "object": "dinero al hijo del gobernador"},
            {"verb": "prestó", "object": "gobernador del hijo dinero"},
        ],
    )
    assert len(cleaned) == 2
