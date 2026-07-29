"""Method-level coverage for the deterministic ``TextCleaner`` pipeline in
``fichero_server.workflows.tools.text_cleaning``. The existing ``test_clean_text.py``
covers the prompt-building + a couple of end-to-end passes; this file exercises
each individual pure string transform and its edge cases.
"""

from __future__ import annotations

from fichero_server.workflows.tools.text_cleaning import TextCleaner, clean_ocr_text


# ===========================================================================
# remove_repeated_words
# ===========================================================================


def test_remove_repeated_words_consecutive_case_insensitive():
    assert TextCleaner.remove_repeated_words("the the CAT cat dog") == "the CAT dog"


def test_remove_repeated_words_keeps_non_adjacent_dupes():
    # Only *consecutive* duplicates collapse.
    assert TextCleaner.remove_repeated_words("cat dog cat") == "cat dog cat"


# ===========================================================================
# remove_repeated_phrases
# ===========================================================================


def test_remove_repeated_phrases_drops_repeated_5grams():
    assert TextCleaner.remove_repeated_phrases("a b c d e a b c d e") == "a b c d e"


def test_remove_repeated_phrases_keeps_unique():
    assert TextCleaner.remove_repeated_phrases("a b c d e f g h i j") == "a b c d e f g h i j"


# ===========================================================================
# combine_single_word_paragraphs
# ===========================================================================


def test_combine_single_word_paragraphs():
    text = "one\ntwo\nthree words here\nfour"
    assert TextCleaner.combine_single_word_paragraphs(text) == "one two\nthree words here\nfour"


# ===========================================================================
# split_long_lines
# ===========================================================================


def test_split_long_lines_wraps_at_max():
    assert TextCleaner.split_long_lines("aaa bbb ccc", max_length=7) == "aaa bbb\nccc"


def test_split_long_lines_short_line_untouched():
    assert TextCleaner.split_long_lines("short line", max_length=72) == "short line"


def test_split_long_lines_unbreakable_word_emitted_whole():
    word = "x" * 80
    assert TextCleaner.split_long_lines(word, max_length=10) == word


# ===========================================================================
# clean_line_spacing
# ===========================================================================


def test_clean_line_spacing_collapses_spaces_and_blank_runs():
    assert TextCleaner.clean_line_spacing("a   b\n\n\n\nc  ") == "a b\n\nc"


# ===========================================================================
# normalize_obvious_ocr_tokens
# ===========================================================================


def test_normalize_obvious_ocr_tokens():
    assert TextCleaner.normalize_obvious_ocr_tokens("DEL CHOCO and CIBCEITO") == "DEL CHOCÓ and CIRCUITO"


def test_normalize_obvious_ocr_tokens_case_insensitive():
    # Patterns use IGNORECASE.
    assert "CIRCUITO" in TextCleaner.normalize_obvious_ocr_tokens("cibceito")


# ===========================================================================
# remove_ocr_garbage_lines
# ===========================================================================


def test_garbage_keeps_year_lines():
    assert TextCleaner.remove_ocr_garbage_lines("1876") == "1876"
    assert TextCleaner.remove_ocr_garbage_lines("2023") == "2023"


def test_garbage_drops_repeated_char_and_number_and_separator_lines():
    assert TextCleaner.remove_ocr_garbage_lines("0000000000000000") == ""
    assert TextCleaner.remove_ocr_garbage_lines("12345") == ""
    assert TextCleaner.remove_ocr_garbage_lines("-------") == ""


def test_garbage_drops_tiny_alpha_residue():
    assert TextCleaner.remove_ocr_garbage_lines("ab") == ""


def test_garbage_keeps_real_content_and_blank_lines():
    assert TextCleaner.remove_ocr_garbage_lines("El escribano firma") == "El escribano firma"
    # Blank lines between content are preserved.
    assert TextCleaner.remove_ocr_garbage_lines("real line\n\nmore text") == "real line\n\nmore text"


# ===========================================================================
# remove_pathological_patterns
# ===========================================================================


def test_pathological_removes_guess_runs():
    assert TextCleaner.remove_pathological_patterns("[Guess:a] [Guess:b] [Guess:c] real") == "real"


def test_pathological_strips_punctuationless_word_soup():
    soup = " ".join(str(i) for i in range(25))  # 25 word-tokens, no punctuation
    assert TextCleaner.remove_pathological_patterns(soup) == ""


def test_pathological_preserves_real_punctuated_prose():
    prose = (
        "The notary, in the year of our Lord, signed the deed before witnesses, "
        "and then departed the town of Quibdó early."
    )
    # Punctuation breaks the 20+ word run, so genuine prose is untouched.
    assert TextCleaner.remove_pathological_patterns(prose) == prose


# ===========================================================================
# remove_specific_phrases
# ===========================================================================


def test_remove_specific_phrases_strips_wrapper():
    assert TextCleaner.remove_specific_phrases("here is the text: El documento") == "El documento"


def test_remove_specific_phrases_no_crash_on_blank_or_empty():
    # Regression guard: the join over clean_lines must not IndexError when the
    # input reduces to nothing.
    assert TextCleaner.remove_specific_phrases("") == ""
    assert TextCleaner.remove_specific_phrases("   \n  \n") == ""


# ===========================================================================
# clean_text end-to-end + public alias
# ===========================================================================


def test_clean_text_empty_and_whitespace():
    assert TextCleaner.clean_text("") == ""
    assert TextCleaner.clean_text("   \n  ") == ""


def test_clean_text_keeps_real_prose():
    prose = "The notary signed the deed before witnesses."
    assert "notary" in TextCleaner.clean_text(prose)


def test_clean_ocr_text_delegates_to_clean_text():
    assert clean_ocr_text("the the cat") == TextCleaner.clean_text("the the cat")
