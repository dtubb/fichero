"""The editor's signs are DRAWN from editorial facts (`source.sure.brackets-are-drawn`).

What breaks without these: a restored stretch printed without its brackets (a reader takes the
editor's guess for what the scribe wrote), an unclear letter printed plain, or a sign stored in the
reading's text where every search and export would carry it as if the scribe had written it.
"""

from __future__ import annotations

from fichero_server.editorial.leiden import draw
from fichero_server.models.editorial import EditorialFact, EditorialFactKind as K


def fact(kind: K, start: int | None = None, end: int | None = None, **extra) -> EditorialFact:
    return EditorialFact(segment_id="s", kind=kind, char_start=start, char_end=end, **extra)


def test_each_kind_draws_its_sign_around_its_span():
    text = "abcdef"
    assert draw(text, [fact(K.restored, 1, 3)]) == "a[bc]def"
    assert draw(text, [fact(K.supplied, 1, 3)]) == "a<bc>def"
    assert draw(text, [fact(K.superfluous, 1, 3)]) == "a{bc}def"
    assert draw(text, [fact(K.deleted, 1, 3)]) == "a⟦bc⟧def"
    assert draw(text, [fact(K.added, 1, 3, place="above")]) == "a\\bc/def"
    assert draw(text, [fact(K.added, 1, 3, place="below")]) == "a/bc\\def"


def test_an_unclear_letter_carries_an_under_dot_and_its_text_is_unchanged():
    drawn = draw("abc", [fact(K.unclear, 0, 2)])
    assert drawn == "ạḅc"
    assert drawn.replace("̣", "") == "abc"          # the reading's own letters, untouched


def test_a_lost_stretch_with_no_text_is_a_gap_of_its_extent():
    assert draw("ab", [fact(K.lost, extent_quantity=3, extent_unit="character")]) == "ab[.3]"
    assert draw("ab", [fact(K.lost, extent="about two lines")]) == "ab[--- about two lines ---]"
    assert draw("ab", [fact(K.lost)]) == "ab[---]"


def test_nested_facts_draw_inside_out_and_the_text_is_never_changed():
    drawn = draw("abcdef", [fact(K.supplied, 1, 5), fact(K.unclear, 2, 3)])
    assert drawn == "a<bc̣de>f"


def test_a_span_that_does_not_fit_or_a_withdrawn_fact_is_not_drawn():
    from fichero_server.core.timeutil import utc_now

    assert draw("abc", [fact(K.restored, 2, 9)]) == "abc"
    assert draw("abc", [fact(K.restored, 0, 1, withdrawn_at=utc_now())]) == "abc"
