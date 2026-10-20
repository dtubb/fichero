"""Checker for model-written catalogue entries (`catalogue.model-entry-is-concise`, #5968).

Pure: text in, findings out. An ERROR fails the entry (over 200 words, a banned analysis phrase, padding by repeated
sentence); a WARNING does not (a long file or folder under 150 words).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

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
    # A banned word inside a quotation is the record's own (`catalogue.model-entry-is-concise`): not the model's analysis.
    lowered = re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d|\u00ab[^\u00bb]*\u00bb', " ", text).lower()
    for phrase in BANNED:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            errors.append(f"banned analysis word: {phrase!r}")
    sentences = [re.sub(r"\s+", " ", s).strip().lower() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    for sentence in {s for s in sentences if sentences.count(s) > 1}:
        errors.append(f"padding: sentence repeated: {sentence[:40]!r}")  # ponytail: exact repeats only
    return errors, warnings


logger = logging.getLogger(__name__)


def cut_to_cap(text: str) -> str:
    """The text cut at the last sentence that ends within the cap (the first sentences if none ends within it)."""
    if len(text.split()) <= MAX_WORDS:
        return text
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if len(" ".join([*kept, sentence]).split()) > MAX_WORDS:
            break
        kept.append(sentence)
    return " ".join(kept) if kept else " ".join(text.split()[:MAX_WORDS])


async def enforce(text: str, ask: Callable[[str], Awaitable[str]], *, long_item: bool = True) -> tuple[str, list[str]]:
    """The entry to store, and the flags it carries. Enforced at write time (#5968), in this order: a finding is sent
    back to the model once (`ask(note)` returns the new answer); an entry still over the cap is cut at a sentence end;
    a banned word that remains is FLAGGED (returned, and logged), never dropped silently. Under 150 only warns."""
    errors, _ = check(text, long_item=long_item)
    if errors:
        try:
            text = await ask("Your last answer broke the rules: " + "; ".join(errors) + ". Write it again within them.")
        except Exception as exc:  # the first answer stands; the cut and the flag below still apply
            logger.warning("catalogue entry retry failed (%s)", exc)
    text = cut_to_cap(text)
    flags = [e for e in check(text, long_item=long_item)[0]]
    if flags:
        logger.warning("catalogue entry stored FLAGGED: %s", "; ".join(flags))
    return text, flags
