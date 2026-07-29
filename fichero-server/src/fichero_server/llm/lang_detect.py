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
_SEGMENT_SPLIT_RE = re.compile(r"(?:\n\s*\n+|(?<=[.!?])\s+)")


def _looks_like_running_prose(segment: str) -> bool:
    """Heuristic filter for prose-like segments.

    Proper-noun lists and caption fragments tend to have too few function
    words to be trustworthy for language detection. Keep only segments with
    enough words and at least a little stop-word signal.
    """
    words = [w.lower() for w in _WORD_RE.findall(segment)]
    if len(words) < 6:
        return False

    stopword_hits = 0
    for word in words:
        if any(word in hints for hints in _LANG_HINTS.values()):
            stopword_hits += 1
            if stopword_hits >= 2:
                return True
    return False


def _select_detection_sample(text: str) -> str:
    """Prefer running prose over noun-heavy fragments for detection."""
    sample = text[:4000]
    prose_segments = [
        segment.strip()
        for segment in _SEGMENT_SPLIT_RE.split(sample)
        if _looks_like_running_prose(segment)
    ]
    if prose_segments:
        return " ".join(prose_segments)[:2000]
    return sample[:2000]


def detect_language(text: str, default: str = "English") -> str:
    """Return the canonical English name of the dominant language in
    `text` ('English' or 'Spanish' today). Falls back to `default`
    when the text has no usable signal.

    Counts FUNCTION WORDS (the/and/of/to vs el/y/de/a) as the primary
    signal. Spanish loanwords and proper nouns (Chocó, María, Sánchez)
    don't tip the balance — those appear in English text frequently and
    would otherwise force English archive-source documents into Spanish
    output (#823).

    Spanish diacritics are used ONLY as a tie-breaker when stop-word
    counts are close (within 1.5×), not as additional weight. Spanish
    must outweigh English by ≥ 1.5× in stop-word counts to win.
    """
    if not text:
        return default

    sample = _select_detection_sample(text)

    words = [w.lower() for w in _WORD_RE.findall(sample)]
    if not words:
        return default

    counts: Counter[str] = Counter()
    for word in words:
        for lang, hints in _LANG_HINTS.items():
            if word in hints:
                counts[lang] += 1

    en_hits = counts.get("English", 0)
    es_hits = counts.get("Spanish", 0)

    spanish_marker_hits = len(_SPANISH_MARKERS.findall(sample))

    # No stop-word signal at all — diacritic count is the only hint.
    # Pure-noun Spanish text (place names, lists) lands here.
    if max(en_hits, es_hits) == 0:
        if spanish_marker_hits >= 3:
            return "Spanish"
        return default

    # Below the noise floor — sample too small to trust either way.
    if max(en_hits, es_hits) < 3:
        return default

    # Require Spanish to outweigh English by ≥ 1.5× before flipping
    # away from English. Small sample noise + a few Spanish loanwords
    # shouldn't push an English-dominant document into Spanish output.
    if es_hits >= en_hits * 1.5:
        return "Spanish"
    if en_hits >= es_hits * 1.5:
        return "English"

    # Within 1.5× of each other — diacritics break the tie, but only
    # when they're substantial (>= 8 in a 2000-char sample).
    if spanish_marker_hits >= 8:
        return "Spanish"

    # Default to English for ambiguous mixed-language text — fichero
    # archive sources are predominantly English with embedded Spanish
    # loanwords, not the other way around.
    return "English"


def resolve_output_language(
    requested: str | None,
    text: str,
    default: str = "English",
    primary_language: str | None = None,
) -> str:
    """Resolve a tool's `output_language` config value into a concrete
    language name. Treats "" / None / "auto" as "detect from text";
    everything else passes through unchanged so users can still pin a
    specific language in the workflow editor. When a primary-language
    override is configured, it wins over auto-detect but not over an
    explicit per-workflow language.
    """
    if requested and requested.lower() not in {"", "auto"}:
        return requested
    if primary_language and primary_language.strip():
        return primary_language.strip()
    return detect_language(text, default=default)


def configured_primary_language() -> str | None:
    """The library's master output language, or None when unset (#4172).

    Every tool that resolves an output language must consult this, or the same
    library produces different languages depending on which extraction path
    ran — which is what made SVO statements drift with no LLM misbehaviour
    involved. Two of the three call sites were skipping it.

    Imported lazily: `fichero_server.db.app` pulls in the app database, and
    `lang_detect` is imported from tool modules that must stay cheap.
    """
    from fichero_server.db.app import get_app_db

    return get_app_db().get_setting("default_primary_language")
