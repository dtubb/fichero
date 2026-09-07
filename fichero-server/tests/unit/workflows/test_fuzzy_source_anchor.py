"""A light paraphrase still lands a page anchor (#4494 follow-up).

The verbatim contract (test_verbatim_source_text_contract.py) proved a
non-verbatim quote must never be stored as an exact quote. But the exact
substring search was ALSO too brittle in the other direction: a genuine
statement whose supporting quote dropped a word ("Also") or a filler
("Those") — a true light paraphrase of real page text — was refuted outright
and orphaned with no page anchor at all. That is the observed NYTimes-1918
case: the page reads "Also Believed to be Among Those in His Party", the
model quoted "believed to be among His Party", and the claim landed
unanchored (source_char_start null) even though the words plainly sit on the
page.

The fix anchors to the CLOSEST real span: it stores the page's OWN words (a
true substring, so highlight still lands) and keeps the model's version under
`model_paraphrase` so nothing pretends the alignment was exact.
"""

from __future__ import annotations

from fichero_server.workflows.tools.extractors import _fuzzy_anchor


PAGE = "Hindenburg Also Believed to be Among Those in His Party."
QUOTE = "believed to be among His Party"


class TestFuzzyAnchorSpanMath:
    """`_fuzzy_anchor` alone — no database, no spaCy, no model."""

    def test_a_light_paraphrase_finds_the_real_span(self):
        span = _fuzzy_anchor(PAGE, QUOTE)
        assert span is not None, "a quote whose words sit on the page must anchor"
        start, end = span
        # The span selects real page text spanning the matched words, whole-word
        # (so the page's trailing period rides along — the anchor covers real
        # page text, not a mid-word cut).
        assert PAGE[start:end] == "Believed to be Among Those in His Party."

    def test_an_exact_quote_also_anchors(self):
        span = _fuzzy_anchor(PAGE, "Among Those in His Party")
        assert span is not None
        start, end = span
        assert PAGE[start:end] == "Among Those in His Party."

    def test_unrelated_words_do_not_false_anchor(self):
        assert _fuzzy_anchor(PAGE, "the sluice wedged shut overnight") is None

    def test_a_one_word_quote_is_too_weak_to_anchor(self):
        # A single common word would match almost anything; refuse it.
        assert _fuzzy_anchor(PAGE, "Party") is None

    def test_a_scattered_match_does_not_stretch_across_the_page(self):
        long_page = "Hindenburg fled. " + ("filler word " * 40) + "His Party arrived."
        # "Hindenburg ... His Party" would span the whole page — reject it
        # rather than anchor a claim to 40 words of unrelated filler.
        assert _fuzzy_anchor(long_page, "Hindenburg His Party") is None


class TestTheRealWriterAnchorsAParaphrase:
    """Drives `_write_kg_rows` against a real database, like the verbatim
    contract's end-to-end class, so the mirror cannot drift."""

    def _saved_claim(self, tmp_path, source_text, page_excerpt):
        from fichero_server.db import Database
        from fichero_server.models import Document, DocType
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.workflows.tools.extractors import _write_kg_rows

        db = Database(tmp_path / "fuzzy.fichero")
        db.save(Document(id="doc-1", name="page.pdf", doc_type=DocType.file))
        section = {"key": "people", "entity_type": None}
        items = [{
            "name": "Hindenburg",
            "subject": "Hindenburg",
            "verb": "believed to be among",
            "object": "His Party",
            "source_text": source_text,
        }]
        _write_kg_rows(
            db, section, items, "doc-1",
            page_label="1", source_excerpt=page_excerpt,
            provider="fixture", model="fixture-v1",
            grounding_text=page_excerpt,
        )
        claims = list(db.query(KnowledgeClaim))
        assert claims, "the extractor saved no claim at all"
        return claims[0]

    def test_a_paraphrase_now_gets_a_page_anchor(self, tmp_path):
        claim = self._saved_claim(tmp_path, QUOTE, PAGE)
        assert claim.source_char_start is not None, (
            "a light paraphrase of real page text was left unanchored — the "
            "#4494 orphaning bug"
        )
        span = PAGE[claim.source_char_start:claim.source_char_end]
        assert span == "Believed to be Among Those in His Party."

    def test_the_stored_quote_is_the_pages_own_words(self, tmp_path):
        claim = self._saved_claim(tmp_path, QUOTE, PAGE)
        meta = claim.metadata or {}
        # source_text is a TRUE substring of the page (so it highlights),
        # never the model's paraphrase.
        assert meta.get("source_text") == "Believed to be Among Those in His Party."
        assert meta["source_text"] in PAGE

    def test_the_model_paraphrase_is_kept_and_labelled(self, tmp_path):
        claim = self._saved_claim(tmp_path, QUOTE, PAGE)
        meta = claim.metadata or {}
        assert meta.get("model_paraphrase") == QUOTE
        assert meta.get("source_text_anchor") == "fuzzy"
        assert "source_text_anchor_reason" in meta

    def test_a_truly_absent_quote_is_still_refuted(self, tmp_path):
        claim = self._saved_claim(tmp_path, "the sluice wedged shut overnight", PAGE)
        meta = claim.metadata or {}
        assert claim.source_char_start is None
        assert "source_text" not in meta
        assert meta.get("model_paraphrase") == "the sluice wedged shut overnight"
        assert meta.get("source_text_anchor") != "fuzzy"

    def test_an_exact_quote_is_unaffected(self, tmp_path):
        claim = self._saved_claim(tmp_path, "Among Those in His Party", PAGE)
        meta = claim.metadata or {}
        assert claim.source_char_start is not None
        assert meta.get("source_text") == "Among Those in His Party"
        # Exact match: not flagged as a fuzzy anchor, no paraphrase kept.
        assert "source_text_anchor" not in meta
        assert "model_paraphrase" not in meta
