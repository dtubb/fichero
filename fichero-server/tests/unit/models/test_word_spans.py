"""#5190, ruled 2026-09-28: when a person's edit of a line takes a word's text out, that word's
reading is retired. These pin WHICH words leave (`source.textedit.a-word-leaves-the-line`); each
case is one the spec names, because each is a way a looser match would keep a reading the edit
took out (or retire one it kept)."""

from fichero_server.models.word_spans import words_that_leave

WORDS = [("w1", "and"), ("w2", "the"), ("w3", "king"), ("w4", "said")]


def test_an_untouched_line_keeps_every_word() -> None:
    assert words_that_leave(WORDS, ["and the king said"]) == set()


def test_a_deleted_word_leaves_and_its_neighbours_stay() -> None:
    assert words_that_leave(WORDS, ["and king said"]) == {"w2"}


def test_one_letter_or_a_case_change_or_fused_punctuation_is_the_word_leaving() -> None:
    """The word's reading records ink: a person correcting it in the line corrected the line."""
    assert words_that_leave(WORDS, ["and the kyng said"]) == {"w3"}
    assert words_that_leave(WORDS, ["And the king said"]) == {"w1"}
    assert words_that_leave(WORDS, ["and the king said."]) == {"w4"}


def test_a_word_moved_within_the_line_leaves() -> None:
    """Matched by text alone it could pick the wrong one of two equal words."""
    assert words_that_leave(WORDS, ["said and the king"]) == {"w4"}
    two_thes = [("a", "the"), ("b", "king"), ("c", "the")]
    assert words_that_leave(two_thes, ["the king"]) == {"c"}


def test_split_or_joined_words_leave_both() -> None:
    assert words_that_leave(WORDS, ["andthe king said"]) == {"w1", "w2"}
    assert words_that_leave([("x", "andthe"), ("y", "king")], ["and the king"]) == {"x"}


def test_whitespace_never_counts_and_nfc_is_the_only_normalisation() -> None:
    assert words_that_leave(WORDS, ["  and   the\tking said "]) == set()
    composed = [("e", "café")]
    assert words_that_leave(composed, ["café"]) == set()  # same letters, other encoding
    assert words_that_leave([("s", "ſanct")], ["sanct"]) == {"s"}  # "ſ" is not "s"


def test_a_later_edit_maps_against_the_earlier_edit_not_the_words_again() -> None:
    """Edit 1 deletes "the"; edit 2 then deletes "king". Mapping edit 2 against the words would
    misalign; against edit 1 it takes out exactly "king", and "the" stays out."""
    assert words_that_leave(WORDS, ["and king said", "and said"]) == {"w2", "w3"}


def test_a_word_of_two_tokens_stays_only_whole() -> None:
    words = [("ny", "New York"), ("c", "city")]
    assert words_that_leave(words, ["New York city"]) == set()
    assert words_that_leave(words, ["New city"]) == {"ny"}


def test_right_to_left_text_needs_no_case_of_its_own() -> None:
    """Logical order, never visual: a Hebrew line is the same token sequence."""
    hebrew = [("h1", "בראשית"), ("h2", "ברא"), ("h3", "אלהים")]
    assert words_that_leave(hebrew, ["בראשית אלהים"]) == {"h2"}
