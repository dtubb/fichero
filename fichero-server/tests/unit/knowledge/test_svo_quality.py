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
    grounded_fraction,
    is_pronoun_subject,
    trim_predicate,
    ungrounded_span,
)

# The page the defects were found on, as it reads once the RTF is converted.
CACIQUES_PAGE = (
    "muy poderosos]\n[Sello]\n00533\n"
    "Andres xptoval Hernandez Varela cañistin\n"
    "estantes en nuestro señor y deste puerto de merida\n"
    "dezimos que nosotros somos a tomar la confesion\n"
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


class TestGrounding:
    """Daniel, 2026-09-04: the output "seemed to do weird bad Spanish".

    A model asked for facts about a notarial page writes modern Spanish it
    composed itself — grammatical, plausible, and not what the manuscript
    says. The words ARE the evidence.
    """

    def test_a_span_copied_from_the_page_is_grounded(self):
        assert not ungrounded_span("cañistin", CACIQUES_PAGE)
        assert not ungrounded_span("puerto de merida", CACIQUES_PAGE)

    def test_a_fluent_paraphrase_is_rejected(self):
        # Perfectly good Spanish. Not on the page.
        assert ungrounded_span("fue nombrado gobernador de la provincia", CACIQUES_PAGE)

    def test_accents_do_not_decide_grounding(self):
        # "merida" on the page, "Mérida" from the model — the same word.
        assert not ungrounded_span("Puerto de Mérida", CACIQUES_PAGE)

    def test_one_inflected_token_in_three_still_grounds(self):
        assert grounded_fraction("tomar la confesión judicial", CACIQUES_PAGE) >= 2 / 3
        assert not ungrounded_span("tomar la confesión judicial", CACIQUES_PAGE)

    def test_a_single_invented_word_is_not_grounded(self):
        assert ungrounded_span("gobernador", CACIQUES_PAGE)

    def test_the_check_fails_open_when_it_cannot_run(self):
        # No page text to compare against is not evidence of invention.
        assert not ungrounded_span("anything at all", None)
        assert not ungrounded_span("anything at all", "")
        # A span of nothing but function words has nothing to ground.
        assert not ungrounded_span("de la", CACIQUES_PAGE)

    def test_rejection_names_the_ungrounded_side(self):
        reason = claim_rejection(
            "Andres", "otorgó", "fue nombrado gobernador", CACIQUES_PAGE
        )
        assert reason and "not on the page" in reason

    def test_a_grounded_claim_from_the_real_page_passes(self):
        assert claim_rejection("Andres", "somos", "a tomar la confesion", CACIQUES_PAGE) is None
