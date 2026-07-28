"""Claim word order lives in ONE place (#4172).

Storage is role-keyed (`subject_canonical` / `predicate_verb` /
`object_phrase`) and encodes no word order, so supporting Arabic (VSO) or an
SOV language is a rendering change, not a migration. That is only true if the
ordering is actually centralised — it was hardcoded as an f-string in four
places, one of them JavaScript.

These pin two things: the helper behaves as the four replaced branches did, and
changing the order really does propagate to the renderers.
"""

from __future__ import annotations

import pytest

from fichero.knowledge import _common
from fichero.knowledge._common import order_statement_parts, render_statement


class TestOrdering:
    def test_all_three_roles_render_in_svo_order(self):
        assert order_statement_parts("Maria", "petitioned", "the court") == [
            "Maria",
            "petitioned",
            "the court",
        ]

    @pytest.mark.parametrize(
        ("subject", "verb", "obj", "expected"),
        [
            ("Maria", "petitioned", "the court", "Maria petitioned the court"),
            (None, "petitioned", "the court", "petitioned the court"),
            ("Maria", "petitioned", None, "Maria petitioned"),
            ("Maria", None, "the court", "Maria the court"),
        ],
    )
    def test_absent_roles_are_dropped(self, subject, verb, obj, expected):
        """Exactly the four branches _claim_sentence used to spell out."""
        assert render_statement(subject, verb, obj) == expected

    def test_empty_strings_count_as_absent(self):
        """Callers pass "" rather than None in places; no stray separators."""
        assert render_statement("", "petitioned", "the court") == "petitioned the court"
        assert render_statement("Maria", "", "") == "Maria"

    def test_separator_is_configurable_without_changing_order(self):
        assert (
            render_statement("Maria", "petitioned", "the court", separator=" → ")
            == "Maria → petitioned → the court"
        )


class TestOrderIsTheSinglePointOfChange:
    """The payoff: a future VSO/SOV renderer edits one tuple."""

    def test_reordering_propagates_to_render_statement(self, monkeypatch):
        monkeypatch.setattr(_common, "STATEMENT_ROLE_ORDER", ("verb", "subject", "object"))

        assert (
            _common.render_statement("Maria", "petitioned", "the court")
            == "petitioned Maria the court"
        )

    def test_reordering_propagates_to_claim_sentences(self, monkeypatch):
        """A VSO order must reach the paragraph renderer, not just the helper."""
        from fichero.knowledge import paragraph
        from fichero.models.knowledge import KnowledgeClaim

        claim = KnowledgeClaim(
            text="fallback text",
            subject_canonical="Maria",
            predicate_verb="petitioned",
            object_phrase="the court",
        )
        assert paragraph._claim_sentence(claim) == "Maria petitioned the court."

        monkeypatch.setattr(_common, "STATEMENT_ROLE_ORDER", ("verb", "subject", "object"))

        assert paragraph._claim_sentence(claim) == "petitioned Maria the court."


class TestClaimSentenceBehaviourUnchanged:
    """The centralisation had to be behaviour-identical."""

    @staticmethod
    def _claim(**kwargs):
        from fichero.models.knowledge import KnowledgeClaim

        return KnowledgeClaim(text="fallback text", **kwargs)

    def test_full_triple(self):
        from fichero.knowledge import paragraph

        claim = self._claim(
            subject_canonical="Maria", predicate_verb="petitioned", object_phrase="the court"
        )
        assert paragraph._claim_sentence(claim) == "Maria petitioned the court."

    def test_verb_and_object_without_subject(self):
        from fichero.knowledge import paragraph

        claim = self._claim(predicate_verb="petitioned", object_phrase="the court")
        assert paragraph._claim_sentence(claim) == "petitioned the court."

    def test_single_role_falls_back_to_claim_text(self):
        """A lone role is not a sentence — this was the implicit fourth branch."""
        from fichero.knowledge import paragraph

        assert paragraph._claim_sentence(self._claim(subject_canonical="Maria")) == (
            "fallback text."
        )
        assert paragraph._claim_sentence(self._claim(predicate_verb="petitioned")) == (
            "fallback text."
        )
