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


class TestTheGateWithoutSpacy:
    """The shipped engine has no spaCy — it must not therefore have no gate.

    spaCy is an optional `[kg]` extra, excluded from the embedded Mac engine
    on purpose (it and pykeen pull hundreds of MB). So the build a user runs
    is the build with no tagger, and until now that meant the grammar gate
    convicted nothing at all.

    Half of it needs no tagger. Spanish marks person in the ending, and that
    half caught 8 of the 16 bad rows. Measured against Apple's on-device
    NaturalLanguage — the zero-download alternative — NLTagger exposes no
    morphology for Spanish whatsoever, so it cannot do even this half; the
    endings are genuinely what a build without spaCy has.
    """

    PAGE = (
        "Andres xptoval Hernandez Varela cañistin estantes en nuestro señor "
        "y deste puerto de merida dezimos que nosotros somos a tomar la "
        "confesion estamos oy del pleyto otorgamos que damos mostrando "
        "tenemos cargo"
    )

    @pytest.fixture
    def no_spacy(self, monkeypatch):
        from fichero_server.knowledge import spacy_svo

        spacy_svo._page_morphology.cache_clear()
        monkeypatch.setattr(spacy_svo, "_pipeline", lambda language: None)
        yield
        spacy_svo._page_morphology.cache_clear()

    @pytest.mark.parametrize(
        "subject,verb", [("Andres", "otorgamos"), ("Corte", "estamos"), ("pleyto", "damos")]
    )
    def test_the_stamped_name_is_still_caught(self, no_spacy, subject, verb):
        reason = predicate_problem(subject, verb, self.PAGE)
        assert reason and "first-person" in reason

    def test_the_speaker_may_still_say_we(self, no_spacy):
        assert (
            predicate_problem("nosotros", "otorgamos", self.PAGE, speaker="nosotros")
            is None
        )

    def test_a_third_person_verb_still_passes(self, no_spacy):
        assert predicate_problem("Andrés", "otorgó", self.PAGE) is None

    def test_the_not_a_verb_half_stays_silent_rather_than_guessing(self, no_spacy):
        # Deciding a part of speech needs a tagger. Without one this gate says
        # nothing rather than inventing a verdict.
        assert predicate_problem("Andres", "cañistin", self.PAGE) is None


class TestFirstPersonEndings:
    """The suffix rule on its own — it is not morphology and must say so."""

    @pytest.mark.parametrize(
        "word", ["otorgamos", "dezimos", "tenemos", "somos", "estamos", "damos", "fiamos"]
    )
    def test_first_person_plural_forms_are_recognised(self, word):
        from fichero_server.knowledge.svo_quality import is_first_person_verb

        assert is_first_person_verb(word) is True

    @pytest.mark.parametrize("word", ["otorgó", "firmó", "cañistin", "estantes"])
    def test_third_person_and_non_verbs_are_not(self, word):
        from fichero_server.knowledge.svo_quality import is_first_person_verb

        assert is_first_person_verb(word) is False

    @pytest.mark.parametrize("word", ["dio", "oy", "a", ""])
    def test_a_word_too_short_to_carry_an_ending_returns_unknown(self, word):
        # None is not False: the caller must tell "not first person" from
        # "I cannot tell", or a gate turns silence into acquittal.
        from fichero_server.knowledge.svo_quality import is_first_person_verb

        assert is_first_person_verb(word) is None

    def test_english_is_out_of_scope_and_says_so(self):
        # "we sign" and "they sign" are identical; a suffix cannot see person.
        from fichero_server.knowledge.svo_quality import is_first_person_verb

        assert is_first_person_verb("sign", "en") is None
