from types import SimpleNamespace

from fichero.knowledge.svo_cleanup import clean_svo_claims


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
