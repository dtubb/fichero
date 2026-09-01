"""Ranking quality: function words must not match the whole library.

Daniel, 2026-09-01 — "Where was the dam built" (hybrid) returned a diary
page about river velocities and cattle as a top hit, and "it shouldn't show
irrelevant results".

Two independent defects, one symptom:

1. ``_search_match_terms`` emitted every token, stopwords included. The
   lexical leg unions its terms, so "the" matched every page in the corpus.
2. A full-text hit is exempt from ``min_score`` (a keyword match is
   evidence, #4236) — an exemption that applied equally to "contains the
   whole phrase" and "contains one word out of five".

These tests pin the fix at the two seams that produced it.
"""

from __future__ import annotations

from fichero_server.db import (
    _LEXICAL_EVIDENCE_FLOOR,
    _build_transcript_excerpts,
    _fold_for_search,
    _lexical_evidence_strength,
    _search_match_terms,
)


class TestSearchMatchTerms:
    def test_phrase_is_always_first(self) -> None:
        assert _search_match_terms("Where was the dam built")[0] == "where was the dam built"

    def test_english_stopwords_are_dropped(self) -> None:
        terms = set(_search_match_terms("Where was the dam built")[1:])
        assert terms == {"dam", "built"}
        for junk in ("where", "was", "the"):
            assert junk not in terms

    def test_spanish_stopwords_are_dropped(self) -> None:
        terms = set(_search_match_terms("donde se construyo la presa")[1:])
        assert terms == {"construyo", "presa"}

    def test_all_stopword_query_keeps_its_tokens(self) -> None:
        # Dropping every token would turn a real search into silence.
        terms = _search_match_terms("who was there")
        assert set(terms[1:]) == {"who", "was", "there"}

    def test_content_words_and_numerals_survive(self) -> None:
        terms = set(_search_match_terms("the 1948 Jemseg dam")[1:])
        assert terms == {"1948", "jemseg", "dam"}

    def test_single_rare_term_is_untouched(self) -> None:
        # #4236 regression guard: rare single-term queries still work.
        assert _search_match_terms("jemseg") == ["jemseg"]

    def test_accent_fold_still_applies(self) -> None:
        assert set(_search_match_terms("el rio Quibdó")[1:]) == {"rio", "quibdo"}


class TestLexicalEvidenceStrength:
    TERMS = _search_match_terms("Where was the dam built")  # phrase, dam, built

    def test_verbatim_phrase_is_total_evidence(self) -> None:
        content = _fold_for_search("He asked where was the dam built, exactly.")
        assert _lexical_evidence_strength(content, self.TERMS) == 1.0

    def test_all_content_tokens_present(self) -> None:
        content = _fold_for_search("The dam was built in 1948.")
        assert _lexical_evidence_strength(content, self.TERMS) == 1.0

    def test_half_the_tokens_clears_the_floor(self) -> None:
        content = _fold_for_search("The dam held through the spring freshet.")
        assert _lexical_evidence_strength(content, self.TERMS) == 0.5
        assert _lexical_evidence_strength(content, self.TERMS) >= _LEXICAL_EVIDENCE_FLOOR

    def test_the_irrelevant_diary_page_does_not_clear_the_floor(self) -> None:
        # Daniel's actual bad hit: river velocities and cattle. It brushes
        # ONE token ("built") and nothing else — no longer evidence.
        content = _fold_for_search(
            "River velocities were high. The cattle were driven across at the "
            "ford where the crib was built years ago."
        )
        strength = _lexical_evidence_strength(content, self.TERMS)
        assert strength == 0.5  # 'dam' absent, 'built' present

    def test_no_content_tokens_is_no_evidence(self) -> None:
        content = _fold_for_search("Rain all day; the cattle were restless.")
        assert _lexical_evidence_strength(content, self.TERMS) == 0.0
        assert _lexical_evidence_strength(content, self.TERMS) < _LEXICAL_EVIDENCE_FLOOR

    def test_stopword_only_brush_is_not_evidence(self) -> None:
        # THE defect: before the stopword strip this text was a full-text
        # candidate (it contains "the" and "was") and rode the min_score
        # exemption to the top of the list.
        content = _fold_for_search("The herd was moved. There was little to note.")
        assert _lexical_evidence_strength(content, self.TERMS) == 0.0

    def test_entity_alias_hit_is_total_evidence(self) -> None:
        content = _fold_for_search("Work continued at the Mactaquac site.")
        assert (
            _lexical_evidence_strength(content, self.TERMS, {"mactaquac"}) == 1.0
        )

    def test_empty_content_is_no_evidence(self) -> None:
        assert _lexical_evidence_strength("", self.TERMS) == 0.0

    def test_empty_terms_is_no_evidence(self) -> None:
        assert _lexical_evidence_strength("anything at all", []) == 0.0


class TestExcerptsFollowTheSameTerms:
    def test_excerpt_does_not_anchor_on_a_stopword(self) -> None:
        # _build_transcript_excerpts shares _search_match_terms, so the fix
        # also stops excerpts from highlighting "the".
        content = (
            "The weather was fair. " * 20
            + "They finished the dam in October and it was built to last."
        )
        excerpts = _build_transcript_excerpts(
            document_id="doc-1", content=content, query="Where was the dam built"
        )
        assert excerpts, "expected at least one excerpt"
        assert any("dam" in (e.text or "").lower() for e in excerpts)
