"""Unit tests for _strip_rtf — RTF markup → plain text converter (#1252)."""

from __future__ import annotations


from fichero.loaders.document_loader import _strip_rtf


class TestStripRtf:
    def test_plain_text_unchanged(self):
        assert _strip_rtf("Hello World") == "Hello World"

    def test_empty_string(self):
        assert _strip_rtf("") == ""

    def test_minimal_rtf_body_text(self):
        rtf = (
            r"{\rtf1\ansi\deff0"
            r"{\fonttbl{\f0 Times New Roman;}}"
            r"\f0\fs24 Hello World.\par}"
        )
        result = _strip_rtf(rtf)
        assert "Hello World." in result
        assert "\\rtf" not in result
        assert "fonttbl" not in result

    def test_bold_group_emits_text(self):
        rtf = r"{\rtf1\ansi {\\b Bold text} normal\par}"
        result = _strip_rtf(rtf)
        # The body text should survive stripping
        assert "normal" in result

    def test_fonttbl_content_dropped(self):
        rtf = (
            r"{\rtf1\ansi"
            r"{\fonttbl{\f0 Arial;}{\f1 Courier;}}"
            r"\pard Arial text here.\par}"
        )
        result = _strip_rtf(rtf)
        assert "Arial text here." in result
        # Font table definitions should NOT appear
        assert "Courier" not in result

    def test_colortbl_dropped(self):
        rtf = r"{\rtf1{\colortbl;\red255\green0\blue0;}Some text\par}"
        result = _strip_rtf(rtf)
        assert "Some text" in result
        assert "red255" not in result
        assert "colortbl" not in result

    def test_paragraph_breaks_become_newlines(self):
        rtf = r"{\rtf1\ansi First paragraph.\par Second paragraph.\par}"
        result = _strip_rtf(rtf)
        assert "First paragraph." in result
        assert "Second paragraph." in result
        assert "\n" in result

    def test_tab_control_word(self):
        # RTF control words are terminated by a space; \tab Col2 is correct.
        rtf = r"{\rtf1 Col1\tab Col2\par}"
        result = _strip_rtf(rtf)
        assert "Col1" in result
        assert "Col2" in result
        assert "\t" in result

    def test_no_rtf_magic_passthrough(self):
        plain = "Not RTF at all"
        assert _strip_rtf(plain) is plain

    def test_whitespace_leading(self):
        rtf = "  \n" + r"{\rtf1\ansi Text.\par}"
        result = _strip_rtf(rtf)
        assert "Text." in result
        assert "\\rtf" not in result

    def test_real_world_sample(self):
        # Minimal sample representative of what macOS clipboard pastes
        rtf = (
            r"{\rtf1\ansi\ansicpg1252\cocoartf2639"
            r"{\fonttbl\f0\froman\fcharset0 TimesNewRomanPSMT;}"
            r"{\colortbl;\red255\green255\blue255;}"
            r"\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0"
            r"\pard\tx566\tx1133\pardeftab720\partightenfactor0"
            r"\f0\fs24 \cf0 This is some historical text about Juan de la Cruz.\par}"
        )
        result = _strip_rtf(rtf)
        assert "Juan de la Cruz" in result
        assert "\\rtf" not in result
        assert "TimesNewRoman" not in result
        assert "cocoartf" not in result
