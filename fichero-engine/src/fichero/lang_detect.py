"""
Lightweight language detection for catalogue / extractor / cleanup tools.

Default scope: English vs Spanish (the two languages Fichero ships
prompts for today). Returns the canonical English name of the language
that callers can pass straight into the prompt builders. Falls back
to English when the text is too short or empty (the prompts read
fine in English even if the doc is something else; better than the
prior "Spanish on every doc" hardcoded default).

Pure stdlib — no langdetect / fasttext dependency. The detector is
intentionally trivial: count Spanish-only diacritics + a small set of
high-frequency stop words per language. Handles mixed-language text
by picking the dominant signal. For ambiguous or scientific text
(few diacritics, few stop words) it falls back to English.

If we need more languages later (Portuguese, French, Italian, Latin),
extend `_LANG_HINTS` — same pattern.
"""

from __future__ import annotations

import re
from collections import Counter

# Word-boundary patterns for the most discriminating high-frequency
# stop words. Kept short on purpose — the goal is fast detection from
# even a 200-char sample, not perfect coverage.
_LANG_HINTS: dict[str, set[str]] = {
    "Spanish": {
        "el", "la", "los", "las", "de", "del", "en", "que", "y", "o",
        "una", "uno", "unos", "unas", "no", "por", "con", "para", "se",
        "su", "sus", "es", "son", "fue", "han", "más", "como", "pero",
        "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    },
    "English": {
        "the", "a", "an", "of", "in", "that", "and", "or", "to", "is",
        "was", "for", "with", "on", "at", "by", "from", "this", "these",
        "those", "be", "are", "as", "but", "not", "have", "has", "had",
        "it", "its", "he", "she", "they", "we", "you",
    },
}

# Spanish-specific diacritics + punctuation as strong signal. English
# imports basically never use these (loanwords aside).
_SPANISH_MARKERS = re.compile(r"[ñÑ¿¡áéíóúÁÉÍÓÚ]")

# Word tokeniser — letters only, lowercased. Drops punctuation, digits,
# and any non-letter run. Unicode-aware so "España" tokenises cleanly.
_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def detect_language(text: str, default: str = "English") -> str:
    """Return the canonical English name of the dominant language in
    `text` ('English' or 'Spanish' today). Falls back to `default`
    when the text has no usable signal.
    """
    if not text:
        return default

    sample = text[:2000]
    spanish_marker_hits = len(_SPANISH_MARKERS.findall(sample))

    words = [w.lower() for w in _WORD_RE.findall(sample)]
    if not words:
        return default

    counts: Counter[str] = Counter()
    for word in words:
        for lang, hints in _LANG_HINTS.items():
            if word in hints:
                counts[lang] += 1

    # Heavy diacritic hit (>= 3 in 2000 chars) is a strong Spanish
    # vote — bias the count to break ties.
    if spanish_marker_hits >= 3:
        counts["Spanish"] += spanish_marker_hits

    if not counts:
        return default

    top, _ = counts.most_common(1)[0]
    # Require at least 3 hits; below that, sample is too noisy to trust.
    if counts[top] < 3:
        return default
    return top


def resolve_output_language(
    requested: str | None,
    text: str,
    default: str = "English",
) -> str:
    """Resolve a tool's `output_language` config value into a concrete
    language name. Treats "" / None / "auto" as "detect from text";
    everything else passes through unchanged so users can still pin a
    specific language in the workflow editor.
    """
    if requested and requested.lower() not in {"", "auto"}:
        return requested
    return detect_language(text, default=default)
