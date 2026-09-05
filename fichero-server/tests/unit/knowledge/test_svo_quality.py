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
    near_duplicate,
    same_statement,
    statement_key,
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


class TestMalformedPredicate:
    """A "verb" of pure punctuation or digits is not a predicate (beta 2026-09).

    The page number "00533" and the stray "]" both appear verbatim on the
    Caciques page, so the grounding rule waves them through; the first-person
    rule sees no ending; nothing else looks. The row reads as a statement and
    is not one.
    """

    @pytest.mark.parametrize("verb", ["00533", "]", "- -", "1560", "..."])
    def test_a_predicate_with_no_letters_is_rejected(self, verb):
        # No source text: the alpha rule must convict on the predicate alone,
        # before grounding gets a say.
        reason = claim_rejection("Andres", verb, "poder")
        assert reason and "not a word" in reason

    def test_a_real_verb_with_a_number_in_it_survives(self):
        # A letter anywhere clears the gate; this rule only catches the
        # letter-less case, not "año 1560".
        assert claim_rejection("Andres", "otorgó", "poder en 1560") is None


class TestSelfReference:
    def test_object_that_only_restates_the_subject_is_rejected(self):
        reason = claim_rejection("Andres", "es", "Andres")
        assert reason and "restates the subject" in reason

    def test_self_reference_is_accent_and_case_folded(self):
        assert claim_rejection("Mérida", "es", "merida")

    def test_object_that_extends_the_subject_is_not_self_reference(self):
        # "Andres … Andres Hernández" says more than the subject does.
        assert claim_rejection("Andres", "es", "Andres Hernández Varela") is None


class TestStatementIdentity:
    """Recognising the same statement written twice (beta: "too much repetition")."""

    def test_punctuation_and_case_do_not_hide_a_duplicate(self):
        assert statement_key("Andres", "otorgó", "poder.") == statement_key(
            "ANDRES", "otorgó", "poder"
        )

    def test_a_leading_repeat_of_the_subject_in_the_object_is_dropped(self):
        assert statement_key("Andres", "otorgó", "Andres poder") == statement_key(
            "Andres", "otorgó", "poder"
        )

    def test_same_subject_and_predicate_are_near_duplicates(self):
        a = statement_key("Andres", "otorgó", "poder")
        b = statement_key("Andres", "otorgó", "poder.")
        assert near_duplicate(a, b)

    def test_a_predicate_that_subsumes_another_is_a_duplicate(self):
        # The parser's obj/obl double-emit: same subject and verb, one object a
        # longer form of the other.
        short = statement_key("Andres", "otorgó", "poder")
        long = statement_key("Andres", "otorgó", "poder cumplido a Juan")
        assert near_duplicate(short, long)

    def test_different_subjects_are_never_duplicates(self):
        a = statement_key("Andres", "otorgó", "poder")
        b = statement_key("Juan", "otorgó", "poder")
        assert not near_duplicate(a, b)

    def test_different_statements_about_one_subject_survive(self):
        a = statement_key("Andres", "otorgó", "poder al cacique")
        b = statement_key("Andres", "firmó", "la carta ante el escribano")
        assert not near_duplicate(a, b)


class TestSameStatement:
    """One shared predicate-identity standard for every dedup path."""

    def test_filler_and_determiner_insertion_is_the_same_statement(self):
        # The case svo_cleanup's token-set rule missed: an inserted "said"/"the".
        assert same_statement("signed the deed", "signed the said deed")
        assert same_statement("held the office", "held office")

    def test_a_different_number_is_a_different_statement(self):
        # Numbers are never filler — this must survive as two statements.
        assert not same_statement("paid 3 pesos", "paid 5 pesos")

    def test_an_added_date_is_a_different_statement(self):
        assert not same_statement("held the office", "held the office in 1830")

    def test_a_different_object_head_is_a_different_statement(self):
        assert not same_statement("gave the house to Pedro", "gave the farm to Pedro")

    def test_punctuation_and_case_noise_still_collapse(self):
        # The folded-equality step: surface noise never splits a statement.
        assert same_statement("arrived at Quibdo", "arrived at Quibdo.")
        assert same_statement("served as alcalde", "Served as  alcalde")

    def test_reordered_content_words_are_not_the_same(self):
        # Same words, opposite roles: order carries the meaning.
        assert not same_statement("Pedro met Ana", "Ana met Pedro")
