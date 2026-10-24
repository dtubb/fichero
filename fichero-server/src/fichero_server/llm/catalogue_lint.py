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
#: A folder's archival description (`catalogue.folder-description-fields`, #6087; owner 2026-10-24, replacing the 150-200 figure for it):
#: as long as its fields need, up to about this many words, scope and content getting the most room; never padded. ONE setting.
FOLDER_DESCRIPTION_MAX_WORDS = 500
BANNED = (
    "suggests", "suggesting", "likely", "appears to", "reveals", "highlights", "sheds light",
    "provides insight", "important", "notably",
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


_QUOTE = re.compile(r'"([^"]*)"|\u201c([^\u201d]*)\u201d|\u00ab([^\u00bb]*)\u00bb')


def _outside_the_records_words(text: str, source: str | None) -> str:
    """The text with the quotations that are the record's own taken out. With `source`, a quotation counts as the record's
    only if it is verbatim in it; the model's own framing in quote marks stays in and is checked. Without `source` every
    quotation is taken as the record's (nothing to compare with)."""
    haystack = _squash(source) if source is not None else None

    def keep(match: re.Match) -> str:
        quoted = next(g for g in match.groups() if g is not None)
        return " " if haystack is None or _squash(quoted) in haystack else match.group(0)

    return _QUOTE.sub(keep, text)


def check(text: str, *, long_item: bool = True, source: str | None = None, max_words: int = MAX_WORDS,
          aim_min: int = AIM_MIN_WORDS) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). `long_item` is False for a short formulaic record, which may be shorter."""
    errors: list[str] = []
    warnings: list[str] = []
    words = len(text.split())
    if words > max_words:
        errors.append(f"{words} words: over the {max_words}-word cap")
    elif long_item and words < aim_min:
        warnings.append(f"{words} words: under the {aim_min}-word aim for a long file or folder")
    # A banned word inside a quotation is the record's own (`catalogue.model-entry-is-concise`): not the model's analysis.
    lowered = _outside_the_records_words(text, source).lower()
    for phrase in BANNED:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            errors.append(f"banned analysis word: {phrase!r}")
    sentences = [re.sub(r"\s+", " ", s).strip().lower() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    for sentence in {s for s in sentences if sentences.count(s) > 1}:
        errors.append(f"padding: sentence repeated: {sentence[:40]!r}")  # ponytail: exact repeats only
    return errors, warnings


logger = logging.getLogger(__name__)


def cut_to_cap(text: str, max_words: int = MAX_WORDS) -> str:
    """The text cut at the last sentence that ends within the cap (the first sentences if none ends within it)."""
    if len(text.split()) <= max_words:
        return text
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if len(" ".join([*kept, sentence]).split()) > max_words:
            break
        kept.append(sentence)
    return " ".join(kept) if kept else " ".join(text.split()[:max_words])


async def enforce(text: str, ask: Callable[[str], Awaitable[str]], *, long_item: bool = True, source: str | None = None,
                  max_words: int = MAX_WORDS, aim_min: int = AIM_MIN_WORDS) -> tuple[str, list[str]]:
    """The entry to store, and the flags it carries. Enforced at write time (#5968), in this order: a finding is sent
    back to the model once (`ask(note)` returns the new answer); an entry still over the cap is cut at a sentence end;
    a banned word that remains is FLAGGED (returned, and logged), never dropped silently. Under 150 only warns."""
    errors, _ = check(text, long_item=long_item, source=source, max_words=max_words, aim_min=aim_min)
    if errors:
        try:
            text = await ask("Your last answer broke the rules: " + "; ".join(errors) + ". Write it again within them.")
        except Exception as exc:  # the first answer stands; the cut and the flag below still apply
            logger.warning("catalogue entry retry failed (%s)", exc)
    text = cut_to_cap(text, max_words)
    flags = check(text, long_item=long_item, source=source, max_words=max_words, aim_min=aim_min)[0]
    if flags:
        logger.warning("catalogue entry stored FLAGGED: %s", "; ".join(flags))
    return text, flags
