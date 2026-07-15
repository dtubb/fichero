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


@pytest.mark.parametrize(
    ("body", "expected"),
    [(r"\u20013?\u25991?", "中文"), (r"\u2360?\u2306?", "सं")],
)
def test_unicode_escapes(body, expected):
    assert expected in _strip_rtf(make_rtf(body))


def test_word_with_multiple_accents():
    # "actu\'f3 como notario" → "actuó como notario"
    rtf = make_rtf(r"actu\'f3 como notario")
    result = _strip_rtf(rtf)
    assert result == "actuó como notario", repr(result)


# ---------------------------------------------------------------------------
# #2505: bare 'XX form must NOT be decoded — it corrupts legit apostrophes
# ---------------------------------------------------------------------------

def test_bare_hex_apostrophe_class_of_92_unchanged():
    """'92 must not be decoded: '9' and '2' are hex digits, but this is plain text."""
    rtf = make_rtf("class of '92 reunion")
    result = _strip_rtf(rtf)
    assert "'92" in result, f"'92 must survive unchanged, got: {result!r}"
    assert "\x92" not in result and "\xfd" not in result, (
        f"'92 must not be decoded to cp1252 byte, got: {result!r}"
    )


def test_bare_hex_apostrophe_49ers_unchanged():
    """'49 must not be decoded: '4' and '9' are hex digits."""
    rtf = make_rtf("the '49ers played well")
    result = _strip_rtf(rtf)
    assert "'49" in result, f"'49 must survive unchanged, got: {result!r}"


def test_bare_hex_apostrophe_rock_n_roll_unchanged():
    """'n' contains 'n' which is not hex — but test that generic apostrophes survive."""
    rtf = make_rtf("rock 'n' roll and '98 vintage")
    result = _strip_rtf(rtf)
    assert "'98" in result, f"'98 must survive unchanged, got: {result!r}"


def test_half_stripped_form_not_decoded():
    """Bare 'XX form (backslash already removed) is NOT decoded (#2505 fix).

    Dropping the bare-hex pass means 'f3 in body text stays as 'f3 — acceptable
    because real RTF always has the backslash (\'f3) and the half-stripped form
    was speculative. The full \'XX form is the correct fix; the bare pass
    corrupted legitimate apostrophe text in actual corpora.
    """
    rtf = make_rtf("compareci'f3 actu'f3")
    result = _strip_rtf(rtf)
    # After fix: bare 'f3 is NOT decoded — compareció does not appear
    assert "compareció" not in result, (
        f"Bare 'f3 must not be decoded to ó after #2505 fix, got: {result!r}"
    )


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
