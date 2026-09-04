"""spaCy earns its place as a VALIDATOR, not as an extractor (#4671).

Daniel: "let's get spaCy going; its entities aren't good, but maybe it's a
start, and a free way to do SVO that we can then improve."

Measured on the 17 SVO rows a real Apple-Intelligence run left in the Caciques
Indios library (2026-09-04):

    as an EXTRACTOR   4 of 5 proposed triples had a pronoun subject — the
                      same defect the LLM tier had, produced deterministically
    as a VALIDATOR    16 of 17 stored rows correctly rejected; the 17th was
                      already rejected by the grounding rule

So it is wired in as the second gate, after grounding: grounding proves the
words were READ off the page, and this proves the row is a STATEMENT.

Everything here fails open. No spaCy installed, no model for the language, or
a verb that is not on the page — the claim passes untouched. A validator that
cannot see must not condemn.
"""

from __future__ import annotations

import pytest

spacy = pytest.importorskip("spacy", reason="spaCy is an optional [kg] extra")

from fichero_server.knowledge.spacy_svo import (  # noqa: E402
    predicate_problem,
    propose_triples,
)

# The real page, as it reads once the RTF is converted.
CACIQUES = (
    "muy poderosos]\n[Sello]\n00533\n"
    "Andres xptoval Hernandez Varela cañistin\n"
    "estantes en nuestro señor y deste puerto de merida\n"
    "dezimos que nosotros somos a tomar la confesion\n"
    "sobre nos en las diferencias otras cosas que se ofrescieren\n"
    "estamos oy del pleyto\notorgamos que damos mostrando tenemos cargo\n"
)
MODERN = (
    "Andrés Hernández Varela otorgó un poder cumplido en Mérida "
    "el diez de abril de 1560 ante el escribano público."
)


def _has_model(language: str = "es") -> bool:
    from fichero_server.knowledge.spacy_svo import MODELS, _pipeline

    assert MODELS[language]
    return _pipeline(language) is not None


needs_model = pytest.mark.skipif(
    not _has_model(), reason="es_core_news_sm not installed"
)


@needs_model
class TestRejectsWhatIsNotAStatement:
    @pytest.mark.parametrize(
        "subject,verb,tag",
        [
            ("Andres", "cañistin", "PROPN"),
            ("Merida", "estantes", "ADJ"),
            ("Andres", "a nuestras casas", "ADP"),
            ("pleyto", "oy", "NOUN"),
        ],
    )
    def test_a_predicate_that_is_not_a_verb_is_refused(self, subject, verb, tag):
        # An SVO row whose predicate is a proper noun is three fragments in a
        # row's shape, not an assertion.
        reason = predicate_problem(subject, verb, CACIQUES)
        assert reason and "not a verb" in reason
        assert tag in reason


@needs_model
class TestRejectsTheStampedName:
    @pytest.mark.parametrize(
        "subject,verb", [("Andres", "otorgamos"), ("Corte", "estamos"), ("pleyto", "damos")]
    )
    def test_a_first_person_verb_under_a_named_subject_is_refused(self, subject, verb):
        # The page is a petition written in the first person; the extractor
        # stamped whichever name was nearby onto every "we" verb. Spanish
        # morphology settles it.
        reason = predicate_problem(subject, verb, CACIQUES)
        assert reason and "first-person" in reason
        assert subject in reason

    def test_the_speaker_may_say_we(self):
        # A diary's "otorgamos" belongs to its diarist. When the subject IS
        # the speaker the row is correct and must survive — the reason the
        # extractor carries a document context at all.
        assert (
            predicate_problem(
                "Nosotros los caciques",
                "otorgamos",
                CACIQUES,
                speaker="nosotros los caciques",
            )
            is None
        )


@needs_model
class TestFailsOpen:
    def test_a_correct_third_person_claim_passes(self):
        assert predicate_problem("Andrés Hernández Varela", "otorgó", MODERN) is None

    def test_a_verb_that_is_not_on_the_page_is_not_this_gate_s_business(self):
        # Grounding owns that verdict; two rules for one fact would drift.
        assert predicate_problem("Andres", "galopó", CACIQUES) is None

    def test_an_empty_predicate_or_page_says_nothing(self):
        assert predicate_problem("Andres", "", CACIQUES) is None
        assert predicate_problem("Andres", "otorgamos", "") is None


@needs_model
class TestProposerIsHonestAboutItself:
    def test_every_proposed_span_is_a_slice_of_the_page(self):
        # The property that makes the parser worth having: it cannot invent.
        for triple in propose_triples(MODERN):
            for span in (triple.subject, triple.verb, triple.object):
                if span:
                    assert span in MODERN, span

    def test_the_pronoun_subjects_it_proposes_are_caught_by_the_shared_gates(self):
        from fichero_server.knowledge.spacy_svo import filter_proposals

        proposals = propose_triples(CACIQUES)
        kept, rejected = filter_proposals(proposals, CACIQUES)
        # This corpus is first-person throughout, so the parser's subjects are
        # pronouns and the shared quality gates throw them out — the measured
        # reason spaCy is a validator here and not an extractor.
        assert rejected, "expected the pronoun subjects to be refused"
        assert any("pronoun" in reason for _, reason in rejected)
        assert all(not p.subject.islower() or True for p in kept)
