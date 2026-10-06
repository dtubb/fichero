"""A model's read of a page or line is checked before it lands (#5522).

Measured 2026-10-06 (Qwen2.5-VL-3B via MLX, 16 GB M4): on a notarial page the model fell into a
loop -- 'Vtho Vntoré Vtho Vntoré ...', CER 1.10 against the ground truth, more text than the page
holds -- and the step ended 'completed' and overwrote the page's text. On a Fraktur page it stopped
at 70% of the text, also 'completed'. A read that came back is not a read that is good.

ONE checker, used by every path a model's page or line reading takes (`process_vision`'s page
paths, the line reader). It answers one question -- is there a measurable sign this read went
wrong? -- and names the sign in words. It never edits the text. A flagged read still lands (the
person can look at it and choose it), but marked, never as the working reading, and never over the
page's text or a better reading.

The signs, and why each threshold is where it is:

* ``repetition`` -- a model looping. Two measures, either trips it:

  - word loop: walking the text's word 4-grams in order, a stretch of at least
    ``LOOP_MIN_WORDS`` (16) consecutive positions whose 4-gram has ALREADY appeared, with the
    most frequent 4-gram appearing at least ``LOOP_MIN_REPEATS`` (4) times. A loop of period p
    words repeated r times makes a stretch of about (r-1)*p; a formula a notary repeats ("en la
    dicha ciudad") recurs as a few 4-grams, broken by new text each time, so its stretch is short.
    16 words is a full sentence said again and again; 4 occurrences rules out a clause quoted
    twice.
  - character loop: a unit of 2-30 characters containing a letter, repeated 8 or more times back
    to back (``CHAR_LOOP_MIN_REPEATS``). Catches loops with no spaces to count words by. A unit
    must hold a letter so dotted leaders, rules and underscores ("........", "____") never trip it.

* ``too-long`` -- more text than the page's lines can hold. Only when the line count is known (a
  pass with lines, or Kraken's own lines): more than ``MAX_CHARS_PER_LINE`` (160) characters per
  line plus ``LENGTH_SLACK_CHARS`` (200). A dense printed line runs ~100 characters and a
  handwritten one 40-90, so 160 is "far beyond", not "a long line"; the slack covers a page whose
  segmenter missed a few lines.

* ``truncated`` -- the model's own signal that it stopped because it ran out of room
  (``finish_reason``/``stop_reason`` of ``length``/``max_tokens``, or an output that used exactly
  its token ceiling). The read is incomplete by the model's own account.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

#: Word n-gram size for the loop measure.
LOOP_NGRAM = 4
#: Consecutive word positions repeating an earlier 4-gram that make a loop.
LOOP_MIN_WORDS = 16
#: The most frequent 4-gram must occur at least this often.
LOOP_MIN_REPEATS = 4
#: Back-to-back repeats of a 2-30 character unit that make a character loop.
CHAR_LOOP_MIN_REPEATS = 8
#: Characters one line can hold, "far beyond" a dense printed line.
MAX_CHARS_PER_LINE = 160
#: Slack over the line capacity, for a segmenter that missed a few lines.
LENGTH_SLACK_CHARS = 200

REPETITION = "repetition"
TOO_LONG = "too-long"
TRUNCATED = "truncated"

#: The key a flag rides under on an artifact's ``data`` and a box's ``metadata``.
READ_FLAG_KEY = "read_flag"

_CHAR_LOOP = re.compile(r"(.{2,30}?)\1{%d,}" % (CHAR_LOOP_MIN_REPEATS - 1), re.S)


@dataclass(frozen=True)
class ReadFlag:
    """Why a read is not trusted, in a word (``kind``) and a sentence (``reason``)."""

    kind: str
    reason: str
    measure: dict[str, Any]

    def as_data(self) -> dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason, "measure": dict(self.measure)}


class ModelText(str):
    """A model's answer, carrying the model's own ``finish_reason``.

    A ``str`` so every caller that treats the answer as text is unchanged; the reason rides along
    until the caller reads it with :func:`finish_reason_of`. Any string operation returns a plain
    ``str`` (the reason is about THIS answer, not a text derived from it).
    """

    finish_reason: str | None

    def __new__(cls, value: str, finish_reason: str | None = None) -> "ModelText":
        made = super().__new__(cls, value)
        made.finish_reason = finish_reason
        return made


def finish_reason_of(text: Any) -> str | None:
    """The model's finish reason, when ``text`` came straight from a model call; None otherwise."""
    return getattr(text, "finish_reason", None)


def is_truncation(finish_reason: str | None) -> bool:
    """True for the providers' "ran out of room" reasons (``length``, ``max_tokens``). Matched by
    substring: some providers double the value ('lengthlength')."""
    reason = (finish_reason or "").lower()
    return "length" in reason or "max_tokens" in reason


def _word_loop(text: str) -> dict[str, Any] | None:
    words = text.lower().split()
    if len(words) < LOOP_NGRAM + LOOP_MIN_WORDS:
        return None
    grams = [tuple(words[i:i + LOOP_NGRAM]) for i in range(len(words) - LOOP_NGRAM + 1)]
    seen: set[tuple[str, ...]] = set()
    run = longest = 0
    for gram in grams:
        if gram in seen:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
            seen.add(gram)
    top_gram, top_count = Counter(grams).most_common(1)[0]
    if longest >= LOOP_MIN_WORDS and top_count >= LOOP_MIN_REPEATS:
        return {"repeated_words": longest, "phrase": " ".join(top_gram), "times": top_count}
    return None


def _char_loop(text: str) -> dict[str, Any] | None:
    for match in _CHAR_LOOP.finditer(text):
        unit = match.group(1)
        if any(ch.isalpha() for ch in unit):
            return {"phrase": unit, "times": len(match.group(0)) // len(unit)}
    return None


def check_read(
    text: str,
    *,
    finish_reason: str | None = None,
    line_count: int | None = None,
    model: str | None = None,
) -> ReadFlag | None:
    """The first sign this read went wrong, or None for a clean read (see the module docstring for
    each sign and its threshold). ``line_count`` is the page's known number of lines, when known;
    ``model`` names the reader in the reason."""
    who = model or "the model"
    if is_truncation(finish_reason):
        return ReadFlag(TRUNCATED, f"{who} stopped before the end (it ran out of room)",
                        {"finish_reason": finish_reason})
    body = text or ""
    loop = _word_loop(body) or _char_loop(body)
    if loop is not None:
        return ReadFlag(REPETITION, f"{who} repeated itself ('{loop['phrase'].strip()}' {loop['times']} times)",
                        loop)
    if line_count and line_count > 0:
        limit = line_count * MAX_CHARS_PER_LINE + LENGTH_SLACK_CHARS
        if len(body) > limit:
            return ReadFlag(TOO_LONG, f"{who} wrote {len(body)} characters, more than the page's "
                            f"{line_count} lines can hold", {"chars": len(body), "lines": line_count,
                                                              "limit": limit})
    return None


def read_flag_of(holder: Any) -> dict[str, Any] | None:
    """The flag an artifact (its ``data``) or a box (its ``metadata``) carries, or None."""
    for attr in ("data", "metadata"):
        bag = getattr(holder, attr, None)
        if isinstance(bag, dict) and isinstance(bag.get(READ_FLAG_KEY), dict):
            return bag[READ_FLAG_KEY]
    if isinstance(holder, dict) and isinstance(holder.get(READ_FLAG_KEY), dict):
        return holder[READ_FLAG_KEY]
    return None


def page_line_count(db: Any, document_id: str | None) -> int | None:
    """How many lines the page's working pass has, when it is a real pass with lines; None when
    that is not known (no pass, an unconverted result, a pass without lines)."""
    if not document_id:
        return None
    from fichero_server.api.routes.document.segment_readings import is_unconverted_pass, working_pass
    from fichero_server.models import Segment

    answer = working_pass(db, document_id)
    if answer.pass_id is None or is_unconverted_pass(answer.pass_id):
        return None
    count = db.count(Segment, pass_id=answer.pass_id, kind="line", deleted_at=None)
    return count or None


__all__ = [
    "CHAR_LOOP_MIN_REPEATS",
    "LENGTH_SLACK_CHARS",
    "LOOP_MIN_REPEATS",
    "LOOP_MIN_WORDS",
    "LOOP_NGRAM",
    "MAX_CHARS_PER_LINE",
    "ModelText",
    "READ_FLAG_KEY",
    "REPETITION",
    "ReadFlag",
    "TOO_LONG",
    "TRUNCATED",
    "check_read",
    "finish_reason_of",
    "is_truncation",
    "page_line_count",
    "read_flag_of",
]
