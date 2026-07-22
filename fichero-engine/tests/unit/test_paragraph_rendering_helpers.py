"""Unit coverage for the pure composition helpers in
``fichero.knowledge.paragraph``. The existing ``test_kg_paragraph_rendering.py``
covers ``render_paragraph_claims`` end-to-end through the DB/route; this file
exercises the individual string/grouping helpers and the marker-offset integrity
with in-memory ``KnowledgeClaim`` objects (no DB).
"""

from __future__ import annotations

from fichero.knowledge.paragraph import (
    ParagraphStyle,
    _claim_object,
    _claim_sentence,
    _claim_subject,
    _claim_verb,
    _combine_phrases,
    _group_claims,
    _is_mergeable_pair,
    _marker_token,
    _normalize,
    _sentence_end,
    _superscript_number,
    render_paragraph_claims,
)
from fichero.models.knowledge import KnowledgeClaim


def _claim(**kw) -> KnowledgeClaim:
    kw.setdefault("text", "fallback text")
    kw.setdefault("source_document_id", "d1")
    return KnowledgeClaim(**kw)


# ===========================================================================
# small string helpers
# ===========================================================================


def test_normalize_collapses_and_casefolds():
    assert _normalize("  Pérez   Signed ") == "pérez signed"
    assert _normalize(None) == ""


def test_sentence_end():
    assert _sentence_end("hello") == "hello."
    assert _sentence_end("done.") == "done."
    assert _sentence_end("really?") == "really?"
    assert _sentence_end("wow!") == "wow!"
    assert _sentence_end("   ") == ""


def test_combine_phrases_oxford_comma():
    assert _combine_phrases([]) == ""
    assert _combine_phrases(["a"]) == "a"
    assert _combine_phrases(["a", "b"]) == "a and b"
    assert _combine_phrases(["a", "b", "c"]) == "a, b, and c"
    # Trailing periods stripped, empties dropped.
    assert _combine_phrases(["a.", "", "b"]) == "a and b"


# ===========================================================================
# claim field extraction (canonical vs svo fallback)
# ===========================================================================


def test_claim_fields_prefer_canonical_over_svo():
    c = _claim(subject_canonical="Canon", svo_subject="Svo",
               predicate_verb="verbC", svo_verb="verbS",
               object_phrase="objC", svo_object="objS")
    assert _claim_subject(c) == "Canon"
    assert _claim_verb(c) == "verbC"
    assert _claim_object(c) == "objC"


def test_claim_fields_fall_back_to_svo():
    c = _claim(svo_subject="Svo", svo_verb="v", svo_object="o")
    assert _claim_subject(c) == "Svo"
    assert _claim_verb(c) == "v"
    assert _claim_object(c) == "o"


def test_claim_fields_none_when_absent():
    c = _claim()
    assert _claim_subject(c) is None
    assert _claim_verb(c) is None
    assert _claim_object(c) is None


# ===========================================================================
# _claim_sentence — SVO combinations + fallbacks
# ===========================================================================


def test_claim_sentence_full_svo():
    c = _claim(subject_canonical="Pérez", predicate_verb="signed", object_phrase="the deed")
    assert _claim_sentence(c) == "Pérez signed the deed."


def test_claim_sentence_verb_object_without_subject():
    c = _claim(predicate_verb="signed", object_phrase="the deed")
    assert _claim_sentence(c) == "signed the deed."


def test_claim_sentence_subject_verb_only():
    c = _claim(subject_canonical="Pérez", predicate_verb="departed")
    assert _claim_sentence(c) == "Pérez departed."


def test_claim_sentence_falls_back_to_text():
    c = _claim(text="A free-form claim.")
    assert _claim_sentence(c) == "A free-form claim."


# ===========================================================================
# merge + grouping
# ===========================================================================


def test_mergeable_same_subject_and_verb_different_object():
    a = _claim(subject_canonical="Pérez", predicate_verb="signed", object_phrase="deed")
    b = _claim(subject_canonical="pérez", predicate_verb="Signed", object_phrase="will")  # case-insens
    assert _is_mergeable_pair(a, b) is True


def test_not_mergeable_different_subject_or_missing_object():
    a = _claim(subject_canonical="Pérez", predicate_verb="signed", object_phrase="deed")
    diff = _claim(subject_canonical="Ana", predicate_verb="signed", object_phrase="will")
    no_obj = _claim(subject_canonical="Pérez", predicate_verb="signed")
    assert _is_mergeable_pair(a, diff) is False
    assert _is_mergeable_pair(a, no_obj) is False


def test_group_claims_merges_consecutive_only():
    a = _claim(id="a", subject_canonical="Pérez", predicate_verb="signed", object_phrase="deed")
    b = _claim(id="b", subject_canonical="Pérez", predicate_verb="signed", object_phrase="will")
    c = _claim(id="c", subject_canonical="Ana", predicate_verb="owned", object_phrase="land")
    groups = _group_claims([a, b, c])
    assert [[x.id for x in g] for g in groups] == [["a", "b"], ["c"]]


def test_group_claims_empty():
    assert _group_claims([]) == []


# ===========================================================================
# markers
# ===========================================================================


def test_superscript_and_marker_token():
    assert _superscript_number(12) == "¹²"
    assert _marker_token(3, ParagraphStyle.narrative) == "³"
    assert _marker_token(3, ParagraphStyle.list) == "[3]"
    assert _marker_token(3, ParagraphStyle.footnoted) == "[3]"


# ===========================================================================
# render_paragraph_claims — the three styles + offset integrity
# ===========================================================================


def _svo(id_, subj, verb, obj):
    return _claim(id=id_, subject_canonical=subj, predicate_verb=verb, object_phrase=obj)


def test_render_narrative_merges_and_offsets_align():
    claims = [
        _svo("c1", "Pérez", "signed", "the deed"),
        _svo("c2", "Pérez", "signed", "the will"),
        _svo("c3", "Ana", "owned", "land"),
    ]
    r = render_paragraph_claims(claims, style=ParagraphStyle.narrative)
    assert r.text == "Pérez signed the deed and the will. ¹ ² Ana owned land. ³"
    assert [(c.marker_index, c.claim_id) for c in r.citations] == [(1, "c1"), (2, "c2"), (3, "c3")]
    # Every marker's recorded offsets must slice back to its token — including
    # the multibyte superscript markers.
    for m in r.markers:
        assert r.text[m.start:m.end] == m.token


def test_render_list_style():
    r = render_paragraph_claims([_svo("c1", "Pérez", "signed", "the deed")], style=ParagraphStyle.list)
    assert r.text == "- Pérez signed the deed. [1]\n  source: d1"
    assert r.markers[0].token == "[1]"
    assert r.text[r.markers[0].start:r.markers[0].end] == "[1]"


def test_render_footnoted_appends_footnotes():
    claims = [_svo("c1", "Pérez", "signed", "the deed"), _svo("c2", "Ana", "owned", "land")]
    r = render_paragraph_claims(claims, style=ParagraphStyle.footnoted)
    assert "Footnotes:" in r.text
    assert "1. d1" in r.text
    assert "2. d1" in r.text


def test_render_empty_claims():
    r = render_paragraph_claims([], style=ParagraphStyle.narrative)
    assert r.text == ""
    assert r.citations == []
    assert r.markers == []
