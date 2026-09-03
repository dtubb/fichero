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


def test_remove_repeated_phrases_keeps_non_adjacent_recurrence():
    # Diary formulae legitimately recur on different days; only immediately
    # adjacent duplicates are stutter (2026-09-02, Marshall sample: the old
    # global seen-set deleted the second "Went to church in the morning").
    t = "Jan 1. Went to church in the morning.\nJan 8. Went to church in the morning."
    assert TextCleaner.remove_repeated_phrases(t) == t


def test_remove_repeated_words_keeps_legitimate_doubles():
    t = "He said that that was all he had had since Tuesday."
    assert TextCleaner.remove_repeated_words(t) == t


def test_remove_repeated_words_collapses_triple_even_when_legitimate_double():
    assert TextCleaner.remove_repeated_words("that that that") == "that that"


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


def test_pathological_keeps_punctuationless_prose():
    # Handwritten diaries and HTR output routinely run 20+ words with no
    # punctuation. Length alone is never grounds for deletion (2026-09-02:
    # a legitimate 26-word Marshall diary sentence came back empty).
    prose = (
        "Went to town this morning and bought some flour sugar tea and "
        "tobacco then walked back home along the shore before dinner and "
        "split wood all afternoon"
    )
    assert TextCleaner.remove_pathological_patterns(prose) == prose


def test_pathological_still_drops_dominated_repetition_lines():
    # The per-line repetition check is the pathological-run guard.
    line = "spam " * 60  # >100 chars, >50 words, one token dominates
    assert TextCleaner.remove_pathological_patterns(line.strip()) == ""


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


def test_remove_specific_phrases_keeps_content_around_midline_phrase():
    # "Note:" (and other listed phrases) inside genuine document text must
    # not swallow the content before or after it. The old `.*?phrase.*?` +
    # DOTALL form deleted everything from the top of the text through the
    # phrase (2026-09-02, Marshall sample).
    t = "Jan 3. Cold morning. Note: the mail did not arrive.\nJan 4. Walked out."
    cleaned = TextCleaner.remove_specific_phrases(t)
    assert "Jan 3. Cold morning." in cleaned
    assert "Jan 4. Walked out." in cleaned


def test_remove_specific_phrases_strips_stacked_wrapper_prefixes():
    # Multiple wrapper phrases at the head of one line all come off.
    t = "here is the text: extracted text: El documento"
    assert TextCleaner.remove_specific_phrases(t) == "El documento"


def test_remove_specific_phrases_preserves_line_structure():
    # Single newlines stay single: the old join doubled every line break.
    t = "line one stays here\nline two stays here"
    assert TextCleaner.remove_specific_phrases(t) == t


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


def test_clean_text_end_to_end_preserves_diary_content():
    # The full pipeline on realistic diary text: nothing may vanish.
    t = (
        "Went to town this morning and bought some flour sugar tea and "
        "tobacco then walked back home along the shore before dinner and "
        "split wood all afternoon"
    )
    cleaned = TextCleaner.clean_text(t)
    for word in ("town", "flour", "tobacco", "shore", "afternoon"):
        assert word in cleaned


def test_clean_ocr_text_delegates_to_clean_text():
    assert clean_ocr_text("the the cat") == TextCleaner.clean_text("the the cat")


# ---------------------------------------------------------------------------
# Table awareness (2026-09-03): a tally/accounts page keeps its numbers
# ---------------------------------------------------------------------------

_MARSHALL_TALLY_PAGE = """1922
Cali and La Cumbre
97
Bogotá
18
7
Buenaventura
Inafui and Inapi
6
Quildo
5
5
Dredge ho. 3
Travelling
51
172
1,2
At Audagaya
3 6 5
Day trips frun Andagaya included in above (72).
dredge ho. 1
Condoto
34
53"""


def test_tabular_page_keeps_its_number_lines():
    """Live regression (Marshall dredge-tally page, 2026-09-03): the per-line
    'short pure number = page noise' drop deleted EVERY count on a page whose
    content IS a numeric table. When >=25% of non-empty lines are numeric-ish
    the page is a table and its numbers are kept.
    """
    cleaned = TextCleaner.remove_ocr_garbage_lines(_MARSHALL_TALLY_PAGE)
    for value in ("97", "18", "51", "172", "34", "53", "3 6 5", "1,2"):
        assert value in cleaned.splitlines(), f"tally value {value!r} was dropped"


def test_prose_page_still_drops_stray_number_lines():
    """A prose page with one stray page-number keeps the old behaviour."""
    prose = (
        "Went to church in the morning and wrote letters afterwards.\n"
        "42\n"
        "In the afternoon we walked to the river and back before supper.\n"
        "Dinner with the Marshalls; long talk about the dredge accounts."
    )
    cleaned = TextCleaner.remove_ocr_garbage_lines(prose)
    assert "42" not in cleaned.splitlines()
    assert "Went to church in the morning and wrote letters afterwards." in cleaned
