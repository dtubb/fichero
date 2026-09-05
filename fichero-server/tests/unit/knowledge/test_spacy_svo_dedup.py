"""The spaCy tier must not hand the writer the same statement twice.

Beta feedback, 2026-09: "too much repetition — better quality statements."
The dependency parser emits one candidate per object child of a verb, so a
single clause with both an ``obj`` and an ``obl`` becomes two rows that differ
only by a trailing phrase. These tests build ``ProposedTriple`` objects
directly — no model, so they run in every build, including the shipped engine
that ships without the optional ``[kg]`` extra — and pin that `filter_proposals`
and `dedupe_proposals` fold the repetition back to one row while keeping
genuinely distinct statements about the same subject.
"""

from __future__ import annotations

from fichero_server.knowledge.spacy_svo import (
    ProposedTriple,
    dedupe_proposals,
    filter_proposals,
)


def _triple(subject: str, verb: str, obj: str, *, source: str = "spacy:dep") -> ProposedTriple:
    sentence = f"{subject} {verb} {obj}".strip()
    return ProposedTriple(
        subject=subject,
        verb=verb,
        object=obj,
        sentence=sentence,
        char_start=0,
        char_end=len(sentence),
        source=source,
    )


class TestDedupeProposals:
    def test_exact_duplicates_collapse_to_one(self):
        proposals = [
            _triple("Andres", "otorgó", "poder"),
            _triple("Andres", "otorgó", "poder"),
        ]
        unique, dropped = dedupe_proposals(proposals)
        assert len(unique) == 1
        assert len(dropped) == 1
        assert dropped[0][1] == "duplicate of an earlier statement"

    def test_the_parsers_obj_obl_double_emit_folds_to_one(self):
        # Same subject and verb, one object a longer form of the other — the
        # canonical way the parser repeats itself.
        proposals = [
            _triple("Andres", "otorgó", "poder"),
            _triple("Andres", "otorgó", "poder cumplido a Juan"),
        ]
        unique, dropped = dedupe_proposals(proposals)
        assert len(unique) == 1
        assert len(dropped) == 1

    def test_distinct_statements_about_one_subject_survive(self):
        proposals = [
            _triple("Andres", "otorgó", "poder al cacique"),
            _triple("Andres", "firmó", "la carta ante el escribano"),
        ]
        unique, _ = dedupe_proposals(proposals)
        assert len(unique) == 2

    def test_same_predicate_different_subjects_survive(self):
        proposals = [
            _triple("Andres", "otorgó", "poder"),
            _triple("Juan", "otorgó", "poder"),
        ]
        unique, dropped = dedupe_proposals(proposals)
        assert len(unique) == 2
        assert not dropped

    def test_first_seen_wins(self):
        first = _triple("Andres", "otorgó", "poder")
        second = _triple("Andres", "otorgó", "poder.")
        unique, _ = dedupe_proposals([first, second])
        assert unique == [first]


class TestFilterProposalsDedupes:
    def test_filter_folds_duplicates_and_reports_them(self):
        # No source text, so the grounding gate fails open and only the dedup
        # pass acts — isolating the behaviour under test.
        proposals = [
            _triple("Andres", "otorgó", "poder"),
            _triple("Andres", "otorgó", "poder cumplido"),
            _triple("Juan", "compareció", "ante el escribano"),
        ]
        kept, rejected = filter_proposals(proposals, "")
        assert len(kept) == 2
        assert any(r == "duplicate of an earlier statement" for _, r in rejected)

    def test_dedup_runs_after_the_quality_gates_not_before(self):
        # A pronoun subject is rejected by the quality gate, never counted as a
        # duplicate — the two verdicts stay distinct in the log.
        proposals = [
            _triple("ellos", "otorgó", "poder"),
            _triple("Andres", "otorgó", "poder"),
        ]
        kept, rejected = filter_proposals(proposals, "")
        assert len(kept) == 1
        assert kept[0].subject == "Andres"
        assert any("pronoun" in r for _, r in rejected)
        assert not any("duplicate" in r for _, r in rejected)
