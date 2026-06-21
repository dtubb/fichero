"""Tests for RTF hex-escape decoding in document_loader._strip_rtf (#2486).

Accented Spanish characters in RTF are encoded as \'XX (cp1252 byte).
Before this fix the state machine consumed ' as an unknown control symbol
and emitted the hex digits as plain text: \'f3 → f3 instead of ó.
"""
import pytest

from fichero.loaders.document_loader import _strip_rtf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rtf(body: str) -> str:
    """Wrap body text in a minimal RTF envelope."""
    return r"{\rtf1\ansi " + body + "}"


# ---------------------------------------------------------------------------
# Primary fix: full \'XX form inside valid RTF
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hex_escape,expected_char", [
    (r"\'f3", "ó"),   # cp1252 0xF3
    (r"\'fa", "ú"),   # cp1252 0xFA
    (r"\'f1", "ñ"),   # cp1252 0xF1
    (r"\'e9", "é"),   # cp1252 0xE9
    (r"\'E1", "á"),   # uppercase hex → á (cp1252 0xE1)
])
def test_single_hex_escape(hex_escape, expected_char):
    rtf = make_rtf(f"test{hex_escape}word")
    result = _strip_rtf(rtf)
    assert expected_char in result, f"Expected {expected_char!r} in {result!r}"
    assert "f3" not in result and "fa" not in result and "f1" not in result \
        or expected_char in result, "Hex residue present"


def test_full_spanish_sentence():
    """The canonical examples from issue #2486."""
    rtf = make_rtf(
        r"p\'fablico compareci\'f3 actu\'f3 a\'f1o N\'f3vita"
    )
    result = _strip_rtf(rtf)
    assert result == "público compareció actuó año Nóvita", repr(result)


def test_word_with_multiple_accents():
    # "actu\'f3 como notario" → "actuó como notario"
    rtf = make_rtf(r"actu\'f3 como notario")
    result = _strip_rtf(rtf)
    assert result == "actuó como notario", repr(result)


# ---------------------------------------------------------------------------
# Defensive fix: half-stripped 'XX form (backslash already removed)
# ---------------------------------------------------------------------------

def test_half_stripped_form_defensive():
    """When a prior pass stripped backslashes, 'f3 should still decode."""
    # RTF body already has apostrophe-hex (backslash was removed upstream)
    rtf = make_rtf("compareci'f3 actu'f3")
    result = _strip_rtf(rtf)
    assert "compareció" in result, repr(result)
    assert "actuó" in result, repr(result)


# ---------------------------------------------------------------------------
# Non-RTF text: must pass through unchanged
# ---------------------------------------------------------------------------

def test_plain_utf8_passthrough():
    plain = "El notario compareció como testigo del año público."
    assert _strip_rtf(plain) == plain


def test_plain_ascii_passthrough():
    plain = "Hello world. No accents here."
    assert _strip_rtf(plain) == plain


def test_non_rtf_with_apostrophe_passthrough():
    """An apostrophe in plain text (not RTF) must not be decoded."""
    plain = "don't strip this"
    assert _strip_rtf(plain) == plain


# ---------------------------------------------------------------------------
# RTF structural correctness: control groups still stripped
# ---------------------------------------------------------------------------

def test_fonttbl_group_stripped():
    rtf = r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}El p\'fablico.}"
    result = _strip_rtf(rtf)
    assert "público" in result
    assert "fonttbl" not in result
    assert "Arial" not in result


def test_par_becomes_newline():
    rtf = make_rtf(r"Line one\par Line two")
    result = _strip_rtf(rtf)
    assert "Line one" in result
    assert "Line two" in result
