"""Fixture-driven coverage for the programmatic reflow passes in
``fichero_server.workflows.tools.text_passes`` — the mechanical cleanup a
book page needs with no model involved.

Every pass is asserted for idempotence: ``pass(pass(x)) == pass(x)``. That is
the property that makes the cleaner safe to re-run over a library.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.workflows.tools.text_cleaning import TextCleaner
from fichero_server.workflows.tools.text_passes import (
    TextCleanOptions,
    TextPassError,
    dehyphenate,
    is_list_block,
    is_table_block,
    is_verse_block,
    looks_like_page_number,
    normalize_whitespace,
    reflow_paragraphs,
    split_pages,
    strip_page_chrome,
    strip_page_chrome_text,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "text_cleaning"


# ===========================================================================
# Fixtures — one specimen per page shape the cleaner must recognise
# ===========================================================================

BOOK_PAGE = (
    "    The morning was cold and the road out of the village lay\n"
    "under a thin frost. He walked with his hands in his pock-\n"
    "ets, thinking of nothing in par tic u lar, and the dogs fol-\n"
    "lowed him as far as the bridge.\n"
    "    At the bridge he stopped. The water below was black and\n"
    "slow, and he watched it for a long while before turning\n"
    "back.\n"
)

SPANISH_PAGE = (
    "La compañía llegó al puerto en la ma-\n"
    "ñana del quince de julio de mil ochocientos noventa. La\n"
    "mañana era fría y el río bajaba turbio.\n"
)

POEM = (
    "Caminante, no hay camino,\n"
    "se hace camino al andar.\n"
    "Al andar se hace camino,\n"
    "y al volver la vista atrás\n"
)

LIST_PAGE = (
    "The inventory listed the following items in the storeroom:\n"
    "- one iron pot\n"
    "- two woollen blankets\n"
    "- a sack of maize\n"
)

TALLY_PAGE = (
    "1922\n"
    "Cali and La Cumbre\n"
    "97\n"
    "Bogotá\n"
    "18\n"
    "Travelling\n"
    "51\n"
    "172\n"
    "At Andagoya\n"
    "3 6 5\n"
)


# ===========================================================================
# 1. Whitespace normalization
# ===========================================================================


def test_normalize_whitespace_strips_trailing_and_collapses_runs():
    assert normalize_whitespace("a  b   c   \nd\t\te") == "a b c\nd e"


def test_normalize_whitespace_removes_invisible_characters():
    # Zero-width space, zero-width joiner, BOM — invisible but they break
    # every word-boundary heuristic downstream.
    assert normalize_whitespace("wo​rd‍﻿") == "word"


def test_normalize_whitespace_turns_nbsp_into_a_plain_space():
    assert normalize_whitespace("de cades") == "de cades"


def test_normalize_whitespace_collapses_blank_line_runs_to_one():
    assert normalize_whitespace("a\n\n\n\n\nb") == "a\n\nb"


def test_normalize_whitespace_preserves_indent_as_paragraph_signal():
    assert normalize_whitespace("    indented line") == "    indented line"
    assert normalize_whitespace("    indented", preserve_indent=False) == "indented"


def test_normalize_whitespace_is_idempotent():
    once = normalize_whitespace(BOOK_PAGE)
    assert normalize_whitespace(once) == once


# ===========================================================================
# 2. Dehyphenation
# ===========================================================================


def test_dehyphenate_joins_a_wrapped_word():
    assert "pockets" in dehyphenate(BOOK_PAGE)
    assert "followed" in dehyphenate(BOOK_PAGE)


def test_dehyphenate_leaves_no_trailing_hyphen_behind():
    out = dehyphenate(BOOK_PAGE)
    assert not any(line.rstrip().endswith("-") for line in out.split("\n"))


def test_dehyphenate_handles_spanish_accents():
    # The joined form must keep the tilde: "ma-\nñana" -> "mañana".
    assert "mañana del quince" in dehyphenate(SPANISH_PAGE)


def test_dehyphenate_joins_when_the_joined_form_appears_elsewhere():
    text = "The mining com-\npany arrived. The company left.\n"
    assert "company arrived" in dehyphenate(text)


def test_dehyphenate_keeps_the_hyphen_of_a_true_compound():
    # "gender-based" is written hyphenated elsewhere in the document, so the
    # line break must not silently weld it into one word.
    text = (
        "A study of gender-based violence in the region.\n"
        "The report described gender-\n"
        "based harm in detail.\n"
    )
    assert "gender-based harm" in dehyphenate(text)


def test_dehyphenate_keeps_the_hyphen_when_both_halves_stand_alone():
    text = (
        "The water was clear and the mill stood by the water.\n"
        "They followed the water-\n"
        "mill road, and the mill was closed.\n"
    )
    assert "water-mill road" in dehyphenate(text)


def test_dehyphenate_leaves_a_capitalised_continuation_alone():
    # "Juan-\nPérez" is a name, not a wrap.
    text = "The deed was signed by Juan-\nPérez before the notary.\n"
    assert dehyphenate(text) == text


def test_dehyphenate_ignores_a_hyphen_at_the_very_end_of_the_text():
    assert dehyphenate("a dash at the end -") == "a dash at the end -"


def test_dehyphenate_is_idempotent():
    once = dehyphenate(BOOK_PAGE)
    assert dehyphenate(once) == once


# ===========================================================================
# 3. Block classification
# ===========================================================================


def test_is_table_block_recognises_a_tally():
    assert is_table_block(TALLY_PAGE.strip().split("\n"))


def test_is_table_block_rejects_prose():
    assert not is_table_block(BOOK_PAGE.strip().split("\n"))


def test_is_verse_block_recognises_a_poem():
    assert is_verse_block(POEM.strip().split("\n"))


def test_is_verse_block_rejects_hard_wrapped_prose():
    assert not is_verse_block(BOOK_PAGE.strip().split("\n"))


def test_is_list_block_recognises_bullets_and_numbers():
    assert is_list_block(["- one", "- two", "- three"])
    assert is_list_block(["1. one", "2. two", "3. three"])


def test_is_list_block_rejects_prose():
    assert not is_list_block(["a sentence here", "and another one here"])


# ===========================================================================
# 4. Paragraph reflow
# ===========================================================================


def test_reflow_joins_hard_wrapped_prose_into_one_line():
    out = reflow_paragraphs(dehyphenate(normalize_whitespace(BOOK_PAGE)))
    paragraphs = out.split("\n\n")
    assert len(paragraphs) == 2
    assert paragraphs[0].startswith("The morning was cold")
    assert paragraphs[0].endswith("as far as the bridge.")
    assert "\n" not in paragraphs[0]


def test_reflow_treats_an_indent_as_a_paragraph_opening():
    out = reflow_paragraphs(normalize_whitespace(BOOK_PAGE))
    assert out.split("\n\n")[1].startswith("At the bridge he stopped.")


def test_reflow_treats_a_blank_line_as_a_hard_break():
    text = "first block of some text here\nthat wraps\n\nsecond block entirely\n"
    out = reflow_paragraphs(text)
    assert out.split("\n\n") == ["first block of some text here that wraps",
                                 "second block entirely"]


def test_reflow_leaves_a_tally_page_alone():
    out = reflow_paragraphs(TALLY_PAGE)
    for value in ("97", "18", "51", "172", "3 6 5"):
        assert value in out.split("\n"), f"tally value {value!r} was reflowed away"


def test_reflow_leaves_verse_line_breaks_intact():
    assert reflow_paragraphs(POEM) == POEM.strip()


def test_reflow_leaves_list_items_on_their_own_lines():
    out = reflow_paragraphs(LIST_PAGE)
    assert "- one iron pot" in out.split("\n")
    assert "- a sack of maize" in out.split("\n")


def test_reflow_leaves_a_standalone_heading_alone():
    text = "CHAPTER ONE\n\nthe prose of the chapter begins on this line\nand runs on.\n"
    out = reflow_paragraphs(text)
    assert out.split("\n\n")[0] == "CHAPTER ONE"


def test_reflow_does_not_absorb_ocr_soup_into_a_paragraph():
    # Soup must stay on its own line so the OCR-garbage pass can still drop it.
    text = (
        "the prose of this line runs to a normal wrap column here\n"
        "%%%$$$###@@@!!!\n"
        "and the prose continues after the soup line ends here too\n"
    )
    out = reflow_paragraphs(text)
    assert "%%%$$$###@@@!!!" in out.split("\n")


def test_reflow_of_empty_input_is_empty():
    assert reflow_paragraphs("") == ""
    assert reflow_paragraphs("   \n  \n") == ""


def test_reflow_is_idempotent():
    once = reflow_paragraphs(dehyphenate(normalize_whitespace(BOOK_PAGE)))
    assert reflow_paragraphs(once) == once


# ===========================================================================
# 5. Cross-page chrome removal
# ===========================================================================

_CHROME_PAGES = [
    "SHIFTING LIVELIHOODS\nthe first page of prose begins here.\n12",
    "SHIFTING LIVELIHOODS\nthe second page of prose is here.\n13",
    "SHIFTING LIVELIHOODS\nthe third page of prose is here.\n14",
]


def test_strip_page_chrome_removes_a_running_header():
    out = strip_page_chrome(_CHROME_PAGES)
    assert not any("SHIFTING LIVELIHOODS" in page for page in out)


def test_strip_page_chrome_removes_page_numbers():
    out = strip_page_chrome(_CHROME_PAGES)
    assert out == [
        "the first page of prose begins here.",
        "the second page of prose is here.",
        "the third page of prose is here.",
    ]


def test_strip_page_chrome_blurs_digits_so_numbered_headers_match():
    pages = [f"Chapter 3, page {n}\nbody of page {n} goes here." for n in (1, 2, 3)]
    out = strip_page_chrome(pages)
    assert not any(page.startswith("Chapter 3") for page in out)


def test_strip_page_chrome_needs_three_pages_before_it_acts():
    two = _CHROME_PAGES[:2]
    assert strip_page_chrome(two) == two


def test_strip_page_chrome_keeps_a_tally_pages_edge_numbers():
    """The 2026-09-03 Marshall regression, at the cross-page level: a page whose
    content IS numbers must not lose the ones that sit at its edges."""
    pages = ["Ledger\n97\n18", "Ledger\n51\n172", "Ledger\n34\n53"]
    out = strip_page_chrome(pages)
    for value in ("97", "18", "51", "172", "34", "53"):
        assert any(value in page.split("\n") for page in out), value


def test_strip_page_chrome_leaves_body_content_that_only_looks_repetitive():
    pages = ["a unique first line\nbody one", "b unique first line\nbody two",
             "c unique first line\nbody three"]
    assert strip_page_chrome(pages) == pages


def test_strip_page_chrome_rejects_a_non_list_argument():
    with pytest.raises(TextPassError):
        strip_page_chrome("not a list of pages")  # type: ignore[arg-type]


def test_strip_page_chrome_is_idempotent():
    once = strip_page_chrome(_CHROME_PAGES)
    assert strip_page_chrome(once) == once


def test_split_pages_splits_on_form_feed():
    assert split_pages("one\fTWO\fthree") == ["one", "TWO", "three"]


def test_strip_page_chrome_text_round_trips_a_form_feed_blob():
    blob = "\f".join(_CHROME_PAGES)
    out = strip_page_chrome_text(blob)
    assert "SHIFTING LIVELIHOODS" not in out
    assert "the second page of prose is here." in out


def test_strip_page_chrome_text_leaves_a_single_page_untouched():
    assert strip_page_chrome_text("only one page here") == "only one page here"


def test_looks_like_page_number():
    for line in ("12", "  7 ", "[42]", "(iv)", "xvii", "MCM"):
        assert looks_like_page_number(line), line
    for line in ("12 head of cattle", "1922 was the year", ""):
        assert not looks_like_page_number(line), line


# ===========================================================================
# 6. Options plumbing through TextCleaner.clean_text
# ===========================================================================


def test_clean_text_reflows_a_book_page_by_default():
    out = TextCleaner.clean_text(BOOK_PAGE)
    assert "pockets, thinking" in out
    assert out.split("\n\n")[0].count("\n") == 0


def test_clean_text_without_reflow_keeps_the_legacy_hard_wrap():
    out = TextCleaner.clean_text(
        BOOK_PAGE, TextCleanOptions(reflow_paragraphs=False)
    )
    assert all(len(line) <= 72 for line in out.split("\n"))


def test_clean_text_respects_a_disabled_hyphenation_toggle():
    out = TextCleaner.clean_text(
        BOOK_PAGE, TextCleanOptions(fix_hyphenation=False)
    )
    assert "pockets" not in out


def test_clean_text_honours_an_explicit_wrap_width():
    out = TextCleaner.clean_text(BOOK_PAGE, TextCleanOptions(wrap_width=40))
    assert all(len(line) <= 40 for line in out.split("\n"))


def test_clean_text_rejects_an_unknown_option():
    with pytest.raises(Exception):
        TextCleanOptions(reflow=True)  # type: ignore[call-arg]


def test_clean_text_is_idempotent_on_a_book_page():
    once = TextCleaner.clean_text(BOOK_PAGE)
    assert TextCleaner.clean_text(once) == once


def test_clean_text_is_idempotent_on_already_clean_prose():
    clean = (
        "The notary signed the deed before witnesses on the fifteenth of "
        "July, and the parties departed.\n\n"
        "The following morning the register was filed with the court."
    )
    assert TextCleaner.clean_text(clean) == clean


def test_clean_text_still_keeps_a_tally_pages_numbers():
    out = TextCleaner.clean_text(TALLY_PAGE)
    for value in ("97", "18", "51", "172", "3 6 5"):
        assert value in out.split("\n"), f"tally value {value!r} was dropped"


# ===========================================================================
# 7. A real book: four pages of Tubb, *Shifting Livelihoods* (2020)
# ===========================================================================


def _book_fixture() -> str:
    path = FIXTURES / "book_pages_raw.txt"
    if not path.is_file():  # pragma: no cover - fixture ships with the repo
        pytest.skip(f"book fixture missing: {path}")
    return path.read_text(encoding="utf-8")


def test_real_book_pages_lose_their_running_header_and_page_numbers():
    out = TextCleaner.clean_text(_book_fixture())
    # The running head is glyph-mangled by the PDF's font encoding; it is the
    # *repetition* across pages that identifies it, not its spelling.
    assert ".)$%,*\"!$.,)" not in out


def test_real_book_pages_have_no_end_of_line_hyphens_left():
    out = TextCleaner.clean_text(_book_fixture())
    assert not any(line.rstrip().endswith("-") for line in out.split("\n"))
    # ...and the words those breaks split are whole again.
    for word in ("cultural", "microorganisms", "Guardians"):
        assert word in out, word


def test_real_book_pages_collapse_to_paragraphs_not_lines():
    raw = _book_fixture()
    out = TextCleaner.clean_text(raw)
    assert len(out.splitlines()) < len(raw.splitlines()) / 5


def test_real_book_pages_keep_their_prose():
    out = TextCleaner.clean_text(_book_fixture())
    for phrase in (
        "the court required",
        "primitive accumulation",
        "artisanal mining",
    ):
        assert phrase in out, phrase


def test_real_book_pages_clean_idempotently():
    once = TextCleaner.clean_text(_book_fixture())
    assert TextCleaner.clean_text(once) == once
