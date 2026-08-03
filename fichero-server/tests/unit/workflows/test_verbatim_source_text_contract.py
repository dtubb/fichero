"""A quote must be verbatim, or it is not a quote (#4494).

Apple Intelligence was observed (3 of 12 live runs) populating a claim's
`source_text` with a TRANSLATED sentence — "La Imprenta Oficial published the
decree the next day." — which is neither a substring of the source paragraph
nor in its language. The pipeline correctly declined to give it a char-offset
anchor, and then persisted it as the claim's quote anyway.

So a translated paraphrase entered the archive labelled as source material,
with only the navigation missing. That is the worst shape available: it looks
like evidence, reads like evidence, and a historian following it back to the
manuscript will not find those words, because they were never there.

The project's north star is facts with provenance. A quote that is not
verbatim is not provenance — it is paraphrase wearing quotation marks.

These tests drive `_normalize_and_save_claims`'s persistence decision directly
with fixture items, so nothing here needs a model, live or paid. What that
leaves unexercised is stated in the module's report: whether Apple Intelligence
still translates, and how often.
"""

from __future__ import annotations

import pytest


SPANISH_PAGE = (
    "El día siguiente la Imprenta Oficial publicó el decreto en la gaceta. "
    "El escribano registró la venta ante testigos."
)
VERBATIM = "El escribano registró la venta ante testigos."
TRANSLATED = "La Imprenta Oficial published the decree the next day."


def _meta_and_excerpt(source_text, page_excerpt, predicate=None):
    """Reproduce the extractor's persistence decision for one item.

    Mirrors the block under test rather than importing it, because that block
    lives inside a long save loop with a database. Kept deliberately small and
    checked against the real code by the integration test below.
    """
    raw = (source_text or "").strip()
    char_start = char_end = None
    verbatim = paraphrase = unverified = None
    if raw:
        if page_excerpt:
            idx = page_excerpt.find(raw)
            if idx >= 0:
                verbatim, char_start, char_end = raw, idx, idx + len(raw)
            else:
                paraphrase = raw
        else:
            verbatim = unverified = raw
    excerpt = verbatim or predicate or page_excerpt or None
    meta = {}
    if verbatim:
        meta["source_text"] = verbatim
        if unverified:
            meta["source_text_unverified"] = True
            meta["source_text_unverified_reason"] = (
                "no page text available to verify the quote against"
            )
    elif paraphrase:
        meta["model_paraphrase"] = paraphrase
        meta["source_text_rejected_reason"] = "not found verbatim in the page text"
    return meta, excerpt, char_start, char_end


class TestATranslatedQuoteNeverLandsInAVerbatimField:
    """The observed defect, pinned."""

    def test_a_translated_sentence_is_not_stored_as_source_text(self):
        meta, _, _, _ = _meta_and_excerpt(TRANSLATED, SPANISH_PAGE)
        assert "source_text" not in meta, (
            "a translated sentence was persisted in the field the inspector "
            "renders as a verbatim quote — that is paraphrase wearing "
            "quotation marks"
        )

    def test_it_is_kept_under_a_field_that_says_what_it_is(self):
        """Discarding it would lose a real signal about what the model did;
        promoting it is the defect. Labelled is the third option."""
        meta, _, _, _ = _meta_and_excerpt(TRANSLATED, SPANISH_PAGE)
        assert meta["model_paraphrase"] == TRANSLATED
        assert "not found verbatim" in meta["source_text_rejected_reason"]

    def test_it_does_not_displace_the_real_page_text_either(self):
        """The half the issue does not mention: a non-verbatim string used to
        become `source_excerpt` as well, so the model's paraphrase replaced the
        actual page chunk. Same substitution, one field over."""
        _, excerpt, _, _ = _meta_and_excerpt(TRANSLATED, SPANISH_PAGE)
        assert excerpt == SPANISH_PAGE
        assert excerpt != TRANSLATED

    def test_it_gets_no_anchor(self):
        _, _, start, end = _meta_and_excerpt(TRANSLATED, SPANISH_PAGE)
        assert start is None and end is None


class TestAGenuineQuoteIsUnaffected:
    """The fix must not cost the working case — a real quote still anchors."""

    def test_a_verbatim_quote_is_stored_and_anchored(self):
        meta, excerpt, start, end = _meta_and_excerpt(VERBATIM, SPANISH_PAGE)
        assert meta["source_text"] == VERBATIM
        assert "model_paraphrase" not in meta
        assert excerpt == VERBATIM
        assert SPANISH_PAGE[start:end] == VERBATIM, (
            "the anchor must select exactly the quoted span"
        )


class TestUncheckedIsNotTheSameAsRefuted:
    """"I looked and it is not there" and "I could not look" are different
    facts, and collapsing them costs something either way.

    My first fix rejected both, which would have stripped the quote from every
    NON-PAGINATED extraction — trading a false-evidence bug for a
    lost-provenance one. The issue asks for rejection when the check the anchor
    block already performs FAILS; where there is no page text, no check is
    performed. So an unchecked quote is kept and MARKED, not discarded.
    """

    def test_an_unchecked_quote_is_kept(self):
        meta, excerpt, _, _ = _meta_and_excerpt(VERBATIM, None)
        assert meta["source_text"] == VERBATIM
        assert excerpt == VERBATIM

    def test_but_it_is_marked_as_never_checked(self):
        """Legible rather than silently trusted. Nothing downstream should have
        to infer 'unverified' from a missing char offset."""
        meta, _, _, _ = _meta_and_excerpt(VERBATIM, None)
        assert meta["source_text_unverified"] is True
        assert "no page text" in meta["source_text_unverified_reason"]

    def test_a_checked_and_anchored_quote_carries_no_such_mark(self):
        meta, _, _, _ = _meta_and_excerpt(VERBATIM, SPANISH_PAGE)
        assert "source_text_unverified" not in meta

    def test_a_refuted_quote_is_marked_differently_from_an_unchecked_one(self):
        refuted, _, _, _ = _meta_and_excerpt(TRANSLATED, SPANISH_PAGE)
        unchecked, _, _, _ = _meta_and_excerpt(VERBATIM, None)
        assert "source_text_rejected_reason" in refuted
        assert "source_text_unverified_reason" in unchecked
        assert "source_text" not in refuted
        assert "source_text" in unchecked


class TestTheREALExtractorPersistsItThisWay:
    """Drives `_write_kg_rows` itself, not a copy of its logic.

    The helper above models the decision so the cases read clearly, but a
    hand-rolled mirror of production logic is exactly the "second copy that
    eventually disagrees" this codebase keeps getting bitten by. These drive
    the real writer against a real database and assert on the stored claim, so
    if the mirror drifts these fail and the mirror-based tests become the
    documentation they were meant to be.
    """

    def _saved_claim(self, tmp_path, source_text, page_excerpt):
        from fichero_server.db import Database
        from fichero_server.models import Document, DocType
        from fichero_server.models.knowledge import KnowledgeClaim
        from fichero_server.workflows.tools.extractors import _write_kg_rows

        db = Database(tmp_path / "verbatim.fichero")
        db.save(Document(id="doc-1", name="acta.pdf", doc_type=DocType.file))
        section = {"key": "people", "entity_type": None}
        items = [{
            "name": "el escribano",
            "subject": "el escribano",
            "verb": "registró",
            "object": "la venta",
            "source_text": source_text,
        }]
        _write_kg_rows(
            db, section, items, "doc-1",
            page_label="1r", source_excerpt=page_excerpt,
            provider="fixture", model="fixture-v1",
            grounding_text=page_excerpt,
        )
        claims = list(db.query(KnowledgeClaim))
        assert claims, "the extractor saved no claim at all"
        return claims[0]

    def test_a_translated_quote_is_not_persisted_as_source_text(self, tmp_path):
        claim = self._saved_claim(tmp_path, TRANSLATED, SPANISH_PAGE)
        meta = claim.metadata or {}
        assert meta.get("source_text") != TRANSLATED, (
            "the REAL extractor persisted a translated sentence as the claim's "
            "verbatim quote"
        )
        assert meta.get("model_paraphrase") == TRANSLATED
        assert claim.source_char_start is None

    def test_a_verbatim_quote_is_persisted_and_anchored(self, tmp_path):
        claim = self._saved_claim(tmp_path, VERBATIM, SPANISH_PAGE)
        meta = claim.metadata or {}
        assert meta.get("source_text") == VERBATIM
        assert "model_paraphrase" not in meta
        assert claim.source_char_start is not None
        span = SPANISH_PAGE[claim.source_char_start:claim.source_char_end]
        assert span == VERBATIM, "the stored anchor does not select the quote"

    def test_an_unchecked_quote_is_kept_and_marked_by_the_real_writer(self, tmp_path):
        """The non-paginated path, end to end. Rejecting here would have been a
        silent data loss across every extraction that runs without page text."""
        claim = self._saved_claim(tmp_path, VERBATIM, None)
        meta = claim.metadata or {}
        assert meta.get("source_text") == VERBATIM
        assert meta.get("source_text_unverified") is True
        assert claim.source_char_start is None

    def test_the_paraphrase_does_not_become_the_source_excerpt(self, tmp_path):
        claim = self._saved_claim(tmp_path, TRANSLATED, SPANISH_PAGE)
        assert claim.source_excerpt != TRANSLATED, (
            "the model's paraphrase displaced the real page text in "
            "source_excerpt — the same substitution one field over"
        )


@pytest.mark.parametrize(
    "quote",
    [
        VERBATIM,
        "El día siguiente la Imprenta Oficial publicó el decreto en la gaceta.",
        "la venta ante testigos",
    ],
)
def test_every_real_substring_of_the_page_still_counts_as_a_quote(quote):
    """The check must not become so strict that genuine quotes are rejected —
    that would trade a false-evidence bug for a lost-provenance one."""
    meta, _, start, end = _meta_and_excerpt(quote, SPANISH_PAGE)
    assert meta["source_text"] == quote
    assert SPANISH_PAGE[start:end] == quote
