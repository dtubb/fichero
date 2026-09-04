"""SVO rows must name someone and assert one thing (#4666).

The defects pinned here are the ones Daniel found in the Caciques Indios run
on 2026-09-04: a browser showing "they" as the subject of nearly every
statement, and rows like ``Andres otorgamos que damos mostrando tenemos cargo``
that are a name welded onto a clause fragment.
"""

from __future__ import annotations

import pytest

from fichero_server.knowledge.svo_quality import (
    MAX_OBJECT_WORDS,
    MAX_VERB_WORDS,
    claim_rejection,
    is_pronoun_subject,
    trim_predicate,
)


class TestPronounSubjects:
    @pytest.mark.parametrize(
        "subject",
        ["they", "They", "THEY", "them", "we", "he", "it", "someone"],
    )
    def test_english_pronouns_are_not_subjects(self, subject):
        assert is_pronoun_subject(subject)

    @pytest.mark.parametrize(
        "subject",
        ["ellos", "Ellos", "ellas", "nosotros", "él", "Él", "este", "aquellos"],
    )
    def test_spanish_pronouns_are_not_subjects_accents_and_all(self, subject):
        assert is_pronoun_subject(subject)

    @pytest.mark.parametrize(
        "subject",
        [
            "Andres xptoval Hernandez Varela",
            "la Corte",
            "El Cerrito",
            "Puerto de Mérida",
            "Nuestra Señora de la Candelaria",
        ],
    )
    def test_real_names_survive(self, subject):
        assert not is_pronoun_subject(subject)

    def test_empty_is_not_a_pronoun(self):
        # Absence is handled by the caller as "no subject", which is a
        # different fact from "a subject that names nobody".
        assert not is_pronoun_subject("")
        assert not is_pronoun_subject(None)

    def test_leading_article_does_not_smuggle_a_pronoun_through(self):
        assert is_pronoun_subject("the they")


class TestTrimPredicate:
    def test_daniels_run_on_verb_becomes_verb_plus_object(self):
        # The real row: "Andres otorgamos que damos mostrando tenemos cargo."
        verb, obj = trim_predicate("otorgamos que damos mostrando tenemos", "cargo")
        assert len(verb.split()) <= MAX_VERB_WORDS
        # Nothing is discarded — the overflow lands in the object.
        assert "tenemos" in obj and "cargo" in obj

    def test_a_real_predicate_is_left_alone(self):
        assert trim_predicate("served as", "alcalde of Popayán") == (
            "served as",
            "alcalde of Popayán",
        )

    def test_periphrastic_spanish_verb_fits_the_cap(self):
        verb, obj = trim_predicate("se ha de dar", "poder")
        assert verb == "se ha de dar"
        assert obj == "poder"

    def test_overflow_with_no_object_still_keeps_every_word(self):
        verb, obj = trim_predicate("a b c d e f", "")
        assert f"{verb} {obj}".split() == ["a", "b", "c", "d", "e", "f"]


class TestClaimRejection:
    def test_pronoun_subject_is_rejected_by_name(self):
        reason = claim_rejection("they", "is", "a person")
        assert reason and "pronoun" in reason

    def test_empty_predicate_is_rejected(self):
        assert claim_rejection("Andres", "", "")

    def test_clause_dump_object_is_rejected(self):
        obj = " ".join(["palabra"] * (MAX_OBJECT_WORDS + 1))
        reason = claim_rejection("Andres", "dijo", obj)
        assert reason and "clause dump" in reason

    def test_a_real_claim_passes(self):
        assert claim_rejection("Andres", "otorgó", "poder al cacique") is None

    def test_verb_only_claim_passes(self):
        # The writer synthesises an object from a verb-only claim; that is a
        # documented path, not a rejection.
        assert claim_rejection("Andres", "compareció", "") is None
