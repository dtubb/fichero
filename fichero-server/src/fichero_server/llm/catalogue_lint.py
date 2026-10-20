"""Checker for model-written catalogue entries (`catalogue.model-entry-is-concise`, #5968).

Pure: text in, findings out. An ERROR fails the entry (over 200 words, a banned analysis phrase, padding by repeated
sentence); a WARNING does not (a long file or folder under 150 words).
"""
from __future__ import annotations

import re

MAX_WORDS = 200
AIM_MIN_WORDS = 150
BANNED = (
    "suggests", "suggesting", "likely", "appears to", "reveals", "highlights", "sheds light",
    "provides insight", "important", "notably",
)


def check(text: str, *, long_item: bool = True) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). `long_item` is False for a short formulaic record, which may be shorter."""
    errors: list[str] = []
    warnings: list[str] = []
    words = len(text.split())
    if words > MAX_WORDS:
        errors.append(f"{words} words: over the {MAX_WORDS}-word cap")
    elif long_item and words < AIM_MIN_WORDS:
        warnings.append(f"{words} words: under the {AIM_MIN_WORDS}-word aim for a long file or folder")
    lowered = text.lower()
    for phrase in BANNED:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            errors.append(f"banned analysis word: {phrase!r}")
    sentences = [re.sub(r"\s+", " ", s).strip().lower() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    for sentence in {s for s in sentences if sentences.count(s) > 1}:
        errors.append(f"padding: sentence repeated: {sentence[:40]!r}")  # ponytail: exact repeats only
    return errors, warnings
