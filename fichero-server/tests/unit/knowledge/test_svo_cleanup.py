from types import SimpleNamespace

from fichero_server.knowledge.svo_cleanup import (
    clean_extracted_claims,
    clean_svo_claims,
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
# clean_extracted_claims — the LLM extraction seam (extract_svo_only /
# extract_all). Before this, model claim dicts were persisted verbatim, so the
# repetition/run-ons/junk Daniel saw on the Istmina run never met the shared
# svo_quality standard. These prove the seam measurably reduces junk while
# keeping every genuinely distinct fact.
# ---------------------------------------------------------------------------


def test_istmina_shaped_run_before_after_counts():
    """A realistic per-entity batch from the LLM extractor: 9 raw claims in,
    4 real claims out. This is the BEFORE/AFTER the wiring buys us."""
    subject = "Andrés Restrepo"
    raw = [
        # Real claim.
        {"verb": "otorgó", "object": "poder a Juan Pérez", "claim_type": "action"},
        # Exact duplicate (the model re-asserting across chunks).
        {"verb": "otorgó", "object": "poder a Juan Pérez"},
        # Near-duplicate: a determiner ("el") inserted, same statement.
        {"verb": "otorgó", "object": "el poder a Juan Pérez"},
        # Distinct fact — different object.
        {"verb": "vendió", "object": "una mina en Istmina por 300 pesos"},
        # Distinct fact — SAME shape, different NUMBER: must survive.
        {"verb": "vendió", "object": "una mina en Istmina por 500 pesos"},
        # Junk: empty predicate.
        {"verb": "", "object": ""},
        # Junk: predicate is punctuation, not a word.
        {"verb": "]", "object": "["},
        # Junk: object only restates the subject.
        {"verb": "es", "object": "Andrés Restrepo"},
        # Run-on verb (7 words): trimmed, not dropped.
        {
            "verb": "registró la escritura pública firmada ante el",
            "object": "notario de Quibdó",
        },
    ]

    cleaned = clean_extracted_claims(subject, raw)

    # BEFORE: 9 raw claims. AFTER: 4 real, distinct claims.
    assert len(raw) == 9
    assert len(cleaned) == 4

    verbs_objects = [(c["verb"], c["object"]) for c in cleaned]
    assert ("otorgó", "poder a Juan Pérez") in verbs_objects
    assert ("vendió", "una mina en Istmina por 300 pesos") in verbs_objects
    assert ("vendió", "una mina en Istmina por 500 pesos") in verbs_objects
    # Run-on verb capped at 4 words; overflow moved into the object.
    assert ("registró la escritura pública", "firmada ante el notario de Quibdó") in verbs_objects


def test_extracted_claims_preserve_non_svo_fields():
    subject = "N. C. Marshall"
    cleaned = clean_extracted_claims(
        subject,
        [
            {
                "verb": "viajó a",
                "object": "Istmina",
                "source_text": "salí para Istmina",
                "epistemic_status": "asserted",
                "claim_type": "movement",
            }
        ],
    )
    assert len(cleaned) == 1
    assert cleaned[0]["source_text"] == "salí para Istmina"
    assert cleaned[0]["epistemic_status"] == "asserted"
    assert cleaned[0]["claim_type"] == "movement"


def test_extracted_claims_keep_distinct_numbers_and_dates():
    cleaned = clean_extracted_claims(
        "Ana",
        [
            {"verb": "pagó", "object": "3 pesos"},
            {"verb": "pagó", "object": "5 pesos"},
            {"verb": "ocupó", "object": "el cargo"},
            {"verb": "ocupó", "object": "el cargo en 1830"},
        ],
    )
    assert len(cleaned) == 4


def test_extracted_claims_drop_pronoun_subject():
    # A subject the entity tier should never have produced, but the LLM can.
    cleaned = clean_extracted_claims(
        "él",
        [{"verb": "firmó", "object": "la escritura"}],
    )
    assert cleaned == []


def test_extracted_claims_source_grounding_is_opt_in():
    claim = {"verb": "compró", "object": "una casa", "source_text": "unrelated page text"}
    # Off by default: a faithful reading whose surface differs from the excerpt
    # is kept.
    assert len(clean_extracted_claims("Ana", [claim])) == 1
    # On: the grounding rule applies (verb/object must appear on the page).
    assert clean_extracted_claims("Ana", [claim], source_grounding=True) == []
