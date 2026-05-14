"""
Output-quality detection for the workflow quality gate (#1029).

A node can "succeed" — run without raising — yet return unusable output:
a page that OCR'd to box glyphs (`⍰⍰,⍰⍰`), a transcription that is mostly
`[ilegible]`. Without a gate the pipeline advances on that noise:
NER extracts nothing, catalogue summarises nothing, and every page shows
a green Completed badge. The user can't tell a clean run from a broken one.

`assess_text_quality` is the shared detector. The builder calls it after
every node and aborts the run when output is garbage, so the failure is
visible and the (cached) re-run is cheap.

Scope, deliberately narrow:
- This gate is about *garbage*, not *emptiness*. Empty output is handled
  separately by each tool, and an empty result can be legitimate.
- `[sin texto]` / `[no text]` are the transcribe prompt's explicit
  no-text sentinels — a valid result, not a failure.
"""

from __future__ import annotations

# Characters that signal decode/render failure rather than real content:
# U+FFFD REPLACEMENT CHARACTER and U+2370 APL FUNCTIONAL SYMBOL QUAD
# QUESTION (the `⍰` seen in broken OCR output). C0/C1 control characters
# other than tab/newline/carriage-return are counted too.
_BAD_GLYPHS = {"�", "⍰"}

# Fraction of non-whitespace characters that must be bad glyphs before the
# text is judged garbage. A clean page with one stray replacement char
# won't trip this; a page of box glyphs trips it easily.
_BAD_GLYPH_RATIO = 0.10

# Fraction of whitespace-split tokens that must be the `[ilegible]`
# sentinel before the text is judged garbage. The transcribe prompt emits
# `[ilegible]` inline for unreadable spots; a few are normal, a page made
# of them is a failed transcription.
_ILEGIBLE_TOKEN_RATIO = 0.4
_ILEGIBLE_MIN_COUNT = 3

# No-text sentinels — a valid "this page has no legible text" result, not
# a quality failure.
_NO_TEXT_SENTINELS = {"[sin texto]", "[no text]", "[sintexto]"}


def _is_bad_char(ch: str) -> bool:
    if ch in _BAD_GLYPHS:
        return True
    # C0/C1 control chars except the whitespace we expect in real text.
    code = ord(ch)
    if (code < 0x20 or 0x7F <= code <= 0x9F) and ch not in "\t\n\r":
        return True
    return False


def assess_text_quality(text: str) -> tuple[bool, str | None]:
    """Decide whether a node's text output is *garbage*.

    Returns ``(is_low_quality, reason)``. ``reason`` is a short
    human-readable string when low-quality, else ``None``.

    Empty / whitespace-only text and the `[sin texto]` / `[no text]`
    sentinels return ``(False, None)`` — emptiness is not this gate's
    job, and a genuine no-text result is valid.
    """
    if not text or not text.strip():
        return (False, None)

    stripped = text.strip()
    if stripped.lower() in _NO_TEXT_SENTINELS:
        return (False, None)

    non_ws = [ch for ch in stripped if not ch.isspace()]
    if non_ws:
        bad = sum(1 for ch in non_ws if _is_bad_char(ch))
        ratio = bad / len(non_ws)
        if ratio >= _BAD_GLYPH_RATIO:
            return (
                True,
                f"{ratio:.0%} of characters are unreadable glyphs "
                f"(decode/OCR failure)",
            )

    tokens = stripped.split()
    if tokens:
        ilegible = sum(
            1 for t in tokens if t.strip(".,;:").lower() == "[ilegible]"
        )
        if (
            ilegible >= _ILEGIBLE_MIN_COUNT
            and ilegible / len(tokens) >= _ILEGIBLE_TOKEN_RATIO
        ):
            return (
                True,
                f"{ilegible}/{len(tokens)} tokens are [ilegible] — "
                f"transcription mostly unreadable",
            )

    return (False, None)
