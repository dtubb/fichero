"""Natural (numeric-aware) sort key for user-visible names.

Lexicographic sorting puts ``page10`` before ``page2`` — wrong for every
scanned-archive naming scheme this app exists for (Daniel's live bug list,
2026-08-25). ``natural_key`` splits digit runs and compares them as numbers:
``page2 < page10``, ``NCM_Diary_1913… < NCM_Diary_1925…`` stays stable.

Case-insensitive, like the sorts it replaces. Digit runs are capped at 30
characters so a pathological all-digit name cannot make int() quadratic.
"""

from __future__ import annotations

import re

_DIGIT_RUN = re.compile(r"(\d{1,30})")


def natural_key(name: str | None) -> tuple:
    """A sort key ordering embedded numbers numerically.

    Numeric chunks sort before alphabetic ones at the same position
    (``page2`` < ``pagea``), matching Finder's behaviour closely enough.
    """
    parts = _DIGIT_RUN.split((name or "").lower())
    # Alternating [text, digits, text, ...]; tag each chunk so int/str never
    # compare directly (Python 3 would raise).
    return tuple(
        (0, int(part)) if index % 2 else (1, part)
        for index, part in enumerate(parts)
    )
