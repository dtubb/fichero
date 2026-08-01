"""#4363: matching folds; storage never does.

The corpus is Spanish/French colonial material where the diacritic IS the
content. Two requirements people conflate, tested separately:

1. MATCHING folds — accents, case (including the casefold-only cases),
   Unicode normalization form, and compatibility variants must not change
   whether a query hits.
2. STORAGE does not fold — the fold is a pure query/match-time function; the
   only assertion possible at this layer is purity (no writes), which the
   route-level diplomatic/normalized split (#3312) carries further.

Adversarial set straight from the issue: NFC vs NFD, precomposed vs
combining, Greek final sigma, CJK width variants, ligatures, ß, a word whose
meaning changes with the accent, and offset-map correctness so highlights
land on the ORIGINAL characters.
"""

from __future__ import annotations

import unicodedata

from fichero_server.db import _fold_for_search, _fold_with_index


class TestMatchingFolds:
    def test_ascii_query_matches_full_diacritic_text(self):
        assert _fold_for_search("Choco") in _fold_for_search("el Chocó profundo")

    def test_nfc_and_nfd_forms_fold_identically(self):
        nfc = unicodedata.normalize("NFC", "Chocó")
        nfd = unicodedata.normalize("NFD", "Chocó")
        assert nfc != nfd  # the premise: different byte sequences
        assert _fold_for_search(nfc) == _fold_for_search(nfd) == "choco"

    def test_precomposed_and_combining_accents_fold_identically(self):
        precomposed = "café"          # é
        combining = "café"           # e + COMBINING ACUTE
        assert _fold_for_search(precomposed) == _fold_for_search(combining) == "cafe"

    def test_greek_final_sigma_needs_casefold_not_lower(self):
        # 'ς' lowercases to itself; only casefold equates it with 'σ'.
        assert _fold_for_search("ὈΔΥΣΣΕΎΣ").endswith("σ")
        assert _fold_for_search("οδυσσευς") == _fold_for_search("ΟΔΥΣΣΕΥΣ")

    def test_german_sharp_s_folds_to_ss(self):
        assert _fold_for_search("straße") == _fold_for_search("STRASSE")

    def test_cjk_fullwidth_folds_to_ascii(self):
        assert _fold_for_search("ｆｉｃｈｅｒｏ") == "fichero"

    def test_ligature_folds_to_letters(self):
        assert _fold_for_search("ﬁchero") == "fichero"

    def test_turkish_dotless_i_stays_distinct_by_decision(self):
        """Declared limitation, not an accident: equating i/ı needs locale
        knowledge a corpus-wide fold does not have. İ DOES fold to i."""
        assert _fold_for_search("ı") == "ı"
        assert _fold_for_search("İ") == "i"

    def test_a_word_whose_meaning_changes_with_the_accent_still_folds(self):
        # 'papa' (potato/pope) vs 'papá' (father) — search must find both;
        # DISPLAY keeps them distinct because storage never folds.
        assert _fold_for_search("papá") == _fold_for_search("papa")


class TestStorageNeverFolds:
    def test_the_fold_is_pure_and_leaves_its_input_alone(self):
        original = "Chocó — papá, straße, ﬁcheros"
        snapshot = str(original)
        _fold_for_search(original)
        _fold_with_index(original)
        assert original == snapshot  # str is immutable; the assertion is the
        # CONTRACT stated where future maintainers look: folding is
        # match-time only, storage keeps every mark (#3312).


class TestHighlightOffsetsSurviveTheFold:
    def test_every_folded_char_maps_to_its_original_index(self):
        text = "El Chocó: straße ﬁna"
        folded, index_map = _fold_with_index(text)
        assert len(folded) == len(index_map)
        # A match found in folded space maps back inside the original string,
        # onto the character that produced it.
        start = folded.find("choco")
        assert start != -1
        original_start, original_end = index_map[start], index_map[start + 4]
        assert text[original_start] == "C"
        assert text[original_end] in ("ó", "o")

    def test_one_to_many_expansions_map_to_the_one_original_char(self):
        folded, index_map = _fold_with_index("aßb")
        assert folded == "assb"
        # both 's' chars came from the single ß at original index 1
        assert index_map == [0, 1, 1, 2]

    def test_fold_with_index_agrees_with_fold_for_search(self):
        """The two folds are ONE definition — nothing forces them to agree
        except this test, and disagreement is exactly the two-things-nothing-
        forced-to-agree defect class."""
        for sample in ("Chocó", "ΟΔΥΣΣΕΎΣ", "straße", "ｆｕｌｌ", "ﬁle", "papá"):
            folded, _ = _fold_with_index(sample)
            assert folded == _fold_for_search(sample), sample
