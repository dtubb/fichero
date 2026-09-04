"""No row in the archive may carry an RTF escape where a letter belongs (#4666).

Daniel, 2026-09-04, reading the SVO browser on a 17th-century Spanish corpus:
the statements said "ca\\'f1istin" and "se\\'f1or". The manuscript says
"cañistin" and "señor". The escapes came from an app-edited transcription
stored as inline RTF source (``ArtifactRichTextCodec``'s storage contract) that
the extraction path read raw and handed to a model, which echoed it back.

The reader stripped that markup at display time, so nobody saw it until it had
been persisted as the archive's own words.
"""

from __future__ import annotations

import re

from fichero_server.loaders.rtf_text import decode_rtf_hex_escapes, to_plain_text

# The signature Daniel spotted. Nothing that reaches an artifact or a KG row
# may match it.
RTF_ESCAPE = re.compile(r"\\'[0-9a-fA-F]{2}")

# A verbatim page from the Caciques Indios library, as it is stored today.
CACIQUES_RTF = (
    "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2907\n"
    "\\cocoatextscaling0\\cocoaplatform0"
    "{\\fonttbl\\f0\\fswiss\\fcharset0 Helvetica;}\n"
    "{\\colortbl;\\red255\\green255\\blue255;}\n"
    "{\\*\\expandedcolortbl;;}\n"
    "\\pard\\tx560\\pardirnatural\\partightenfactor0\n\n"
    "\\f0\\fs24 \\cf0 muy poderosos]\\\n"
    "[Sello]\\\n"
    "00533\\\n"
    "Andres xptoval Hernandez Varela ca\\'f1istin\\\n"
    "estantes en nuestro se\\'f1or y deste puerto de merida\\\n"
    "}"
)


class TestSourceConversion:
    def test_the_stored_page_becomes_prose(self):
        text = to_plain_text(CACIQUES_RTF)
        assert not RTF_ESCAPE.search(text)
        assert "cañistin" in text
        assert "señor" in text
        assert "\\rtf1" not in text
        assert "fonttbl" not in text
        assert "Helvetica" not in text

    def test_line_breaks_survive_so_words_do_not_weld_together(self):
        # "ca\\'f1istin\\<newline>estantes" must not become "cañistinestantes":
        # a word no historian recognises is a word the extractor will build a
        # claim out of.
        text = to_plain_text(CACIQUES_RTF)
        assert "cañistinestantes" not in text
        assert "cañistin" in text and "estantes" in text


class TestResidualEscapes:
    def test_a_fragment_that_is_not_a_whole_rtf_document_is_still_repaired(self):
        # `_strip_rtf` requires a `{\rtf` prefix; a claim, an object phrase or a
        # pasted excerpt has none, and used to keep its escapes forever.
        assert to_plain_text("se\\'f1or de la tierra") == "señor de la tierra"

    def test_multi_byte_runs_decode_as_one_character(self):
        assert decode_rtf_hex_escapes("\\'c3\\'b1") == "ñ"

    def test_plain_text_is_returned_untouched(self):
        for text in ("class of '92", "the '49ers", "señor", ""):
            assert to_plain_text(text) == text

    def test_an_undecodable_escape_is_left_alone_not_replaced(self):
        # Corrupting a byte we cannot read would be worse than showing it.
        assert "\\'" in decode_rtf_hex_escapes("\\'81", encoding="cp932")

    def test_output_is_nfc_so_search_matches(self):
        decomposed = "señor"  # n + combining tilde
        assert to_plain_text(decomposed) == "señor"
