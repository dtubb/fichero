"""The on-device translator's protocol — and its refusals (2026-09-04).

Apple's Translation framework is free and offline, which makes it attractive
as the cheap tier of the translate step. The risk that comes with "free" is
that a failure looks like a success: a missing language pack, or a short
batch, would hand the archive plausible text that is not a translation of what
it claims to translate.

These tests are the protocol half — pure functions, no subprocess, no model.
The quality half is a 3-page spot-check against the LLM step, which the
program requires before any of this surfaces in Settings.
"""

from __future__ import annotations

import json

import pytest

from fichero_server.llm.apple_translation import (
    TranslationBridgeError,
    TranslationModelNotInstalledError,
    TranslationPairUnsupportedError,
    build_translate_request,
    parse_translate_response,
    raise_from_translate_stderr,
)


# =============================================================================
# The request states what the caller already knows
# =============================================================================


def test_request_carries_the_pair_and_the_texts():
    request = build_translate_request(["hola", "adiós"], source="es", target="en")
    assert request == {"source": "es", "target": "en", "texts": ["hola", "adiós"]}


def test_empty_strings_keep_their_place():
    """The response is positional; dropping one shifts every later pairing."""
    request = build_translate_request(["hola", "", "adiós"], source="es", target="en")
    assert request["texts"] == ["hola", "", "adiós"]


@pytest.mark.parametrize(
    ("texts", "source", "target"),
    [
        ([], "es", "en"),
        (["hola"], "", "en"),
        (["hola"], "  ", "en"),
        (["hola"], "es", ""),
    ],
    ids=["no-texts", "no-source", "blank-source", "no-target"],
)
def test_an_incomplete_request_is_refused_before_the_subprocess(texts, source, target):
    """A guess about the source language would be a second, weaker detector."""
    with pytest.raises(ValueError):
        build_translate_request(texts, source=source, target=target)


# =============================================================================
# The response is verified positionally, not trusted
# =============================================================================


def test_translations_come_back_in_order():
    stdout = json.dumps(
        {
            "source_language": "es",
            "target_language": "en",
            "translations": ["hello", "goodbye"],
            "model": "apple-translation",
        }
    ).encode()
    assert parse_translate_response(stdout, expected=2) == ["hello", "goodbye"]


def test_a_short_batch_is_refused_rather_than_paired_up():
    """The failure this test exists for: two translations for three pages
    would silently attach page 3's text to page 2's translation."""
    stdout = json.dumps({"translations": ["hello"]}).encode()
    with pytest.raises(TranslationBridgeError) as caught:
        parse_translate_response(stdout, expected=3)
    assert "refusing to pair them up" in str(caught.value)


@pytest.mark.parametrize(
    "stdout",
    [b"not json at all", b"{}", json.dumps({"translations": "hello"}).encode()],
    ids=["garbage", "no-key", "not-a-list"],
)
def test_a_malformed_payload_never_yields_text(stdout):
    with pytest.raises(TranslationBridgeError):
        parse_translate_response(stdout, expected=1)


# =============================================================================
# Refusals are TYPED — the caller must be able to act on them
# =============================================================================


def test_a_missing_language_pack_is_its_own_error_and_names_the_pair():
    """Only the USER can install a pair (macOS shows that sheet, not us), so
    the refusal has to say which pair and must not be mistaken for a generic
    failure that something else could retry."""
    stderr = json.dumps(
        {
            "kind": "not_installed",
            "error": "The es → en translation model is not downloaded on this Mac.",
        }
    ).encode()
    with pytest.raises(TranslationModelNotInstalledError) as caught:
        raise_from_translate_stderr(stderr, 1)
    assert "es → en" in str(caught.value)
    assert caught.value.kind == "not_installed"


def test_an_unsupported_pair_is_distinguishable_from_an_uninstalled_one():
    """One is fixable by downloading; the other never will be."""
    stderr = json.dumps(
        {"kind": "unsupported_pair", "error": "macOS does not translate xx → yy."}
    ).encode()
    with pytest.raises(TranslationPairUnsupportedError):
        raise_from_translate_stderr(stderr, 1)


def test_an_unknown_kind_still_raises_and_keeps_its_kind():
    stderr = json.dumps({"kind": "translation", "error": "boom"}).encode()
    with pytest.raises(TranslationBridgeError) as caught:
        raise_from_translate_stderr(stderr, 1)
    assert caught.value.kind == "translation"


def test_a_crash_with_no_payload_still_raises():
    """A bridge that died before emitting JSON must not read as success."""
    with pytest.raises(TranslationBridgeError):
        raise_from_translate_stderr(b"Segmentation fault", 139)


def test_every_refusal_is_an_exception_not_a_value():
    """The rule, stated once: this module never returns the source text.

    A translator that hands back its input on failure is the silent-fallback
    shape — the archive would record a 'translation' that is the original.
    """
    for stderr in (
        json.dumps({"kind": "not_installed", "error": "x"}).encode(),
        json.dumps({"kind": "unsupported_pair", "error": "x"}).encode(),
        json.dumps({"kind": "translation", "error": "x"}).encode(),
        b"",
    ):
        with pytest.raises(TranslationBridgeError):
            raise_from_translate_stderr(stderr, 1)
