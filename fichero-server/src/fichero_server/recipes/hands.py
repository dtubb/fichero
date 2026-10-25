"""When the material was written, and which hand: Your Material's two questions (section 7c, #5668).

`source.onboard.material.when-written`: a century or a range of years ("16th century", "1650–1700"), kept as typed
with the years it means (`period_years`). `source.onboard.material.which-hand`: chosen from a curated list of hands
for the script and the century (`hands_for`), each mapped to the Hugging Face tags readers carry; anything else is
typed and kept as typed, and "Not sure" is an answer. Both feed the search for readers
(`source.onboard.material.feeds-the-reader-search`): a hand's tags join the finder's tag search (`tags_for`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NOT_SURE = "not-sure"


@dataclass(frozen=True)
class Hand:
    id: str
    title: str
    script: str
    #: The centuries it was written in, inclusive (the 15th century is 15).
    from_century: int
    to_century: int
    #: The Hugging Face tags readers made for it carry.
    tags: tuple[str, ...]
    #: A word of what it looks like, until each hand has its picture.
    looks: str
    #: The languages it was written in, where that is particular to it (Kurrent: German); empty for any (#5688).
    languages: tuple[str, ...] = ()


HANDS: tuple[Hand, ...] = (
    Hand("caroline-minuscule", "Caroline minuscule", "Latn", 8, 12, ("caroline", "carolingian"),
         "round, separate letters, few abbreviations"),
    Hand("gothic-textualis", "Gothic textualis", "Latn", 12, 16, ("textualis", "gothic"),
         "tall, angular, broken strokes; the book hand"),
    Hand("gothic-cursiva", "Gothic cursiva", "Latn", 13, 16, ("cursiva", "gothic"),
         "joined, looped ascenders; the documents' hand"),
    Hand("secretary", "Secretary", "Latn", 15, 17, ("secretary-hand", "secretary"),
         "angular, with a reversed e and a looped d", ("en",)),
    Hand("humanistic", "Humanistic", "Latn", 15, 16, ("humanistic",), "rounded, upright, modelled on Caroline"),
    Hand("italic", "Italic", "Latn", 15, 18, ("italic",), "slanted and joined"),
    Hand("procesal", "Procesal", "Latn", 16, 17, ("procesal", "spanish-paleography"),
         "Spanish court hand, letters run into chains", ("es",)),
    Hand("spanish-humanistic-cursive", "Spanish humanistic cursive (bastarda)", "Latn", 16, 18,
         ("bastarda", "humanistic"), "the Spanish colonial archives' everyday hand", ("es",)),
    Hand("kurrent", "Kurrent", "Latn", 16, 20, ("kurrent",), "German cursive, steep and pointed", ("de",)),
    Hand("copperplate", "Copperplate", "Latn", 18, 19, ("copperplate",), "round, slanted, thick and thin strokes"),
    Hand("palmer", "Palmer method", "Latn", 19, 20, ("palmer", "palmer-method"),
         "upright, rounded and joined; the school cursive of the Americas (letra Palmer)"),
    Hand("modern-cursive", "Modern cursive", "Latn", 20, 21, ("modern-cursive", "cursive"),
         "today's joined everyday handwriting"),
    Hand("naskh", "Naskh", "Arab", 10, 20, ("naskh",), "rounded and clear, the book hand"),
    Hand("nastaliq", "Nastaʿlīq", "Arab", 14, 20, ("nastaliq",), "hanging, sloping words"),
    Hand("hebrew-square", "Hebrew square", "Hebr", 1, 20, ("hebrew-square",), "upright, separate letters"),
    Hand("hebrew-cursive", "Hebrew cursive", "Hebr", 10, 20, ("hebrew-cursive",), "joined and rounded"),
)

_CENTURY = re.compile(r"^\s*(\d{1,2})(?:st|nd|rd|th)\s+century\s*$", re.I)
_RANGE = re.compile(r"^\s*(\d{3,4})\s*(?:[-–—]|to)\s*(\d{3,4})\s*$")
_YEAR = re.compile(r"^\s*(\d{3,4})\s*$")


def period_years(period: str | None) -> tuple[int, int] | None:
    """The years a period answer means: "16th century" is 1501–1600, "1650–1700" itself, "1740" that year; None for
    anything else (kept as typed, said as not read)."""
    if not period:
        return None
    if m := _CENTURY.match(period):
        century = int(m.group(1))
        return (century - 1) * 100 + 1, century * 100
    if m := _RANGE.match(period):
        start, end = sorted((int(m.group(1)), int(m.group(2))))
        return start, end
    if m := _YEAR.match(period):
        return int(m.group(1)), int(m.group(1))
    return None


def _century(year: int) -> int:
    return (year - 1) // 100 + 1


def hands_for(script: str, period: str | None = None, languages: list[str] | None = None) -> list[Hand]:
    """The curated hands for a script, those written in the period's centuries when it is read, and in one of the
    project's languages where a hand is particular to some (#5688), in century order."""
    years = period_years(period)
    asked = {lang.split("-")[0] for lang in languages or []}
    out = []
    for hand in HANDS:
        if hand.script != script:
            continue
        if asked and hand.languages and not asked & set(hand.languages):
            continue
        if years and (hand.to_century < _century(years[0]) or hand.from_century > _century(years[1])):
            continue
        out.append(hand)
    return sorted(out, key=lambda h: (h.from_century, h.title))


def tags_for(hands: list[str] | None) -> list[str]:
    """The Hugging Face tags of the hands answered (a curated hand's tags; a typed one as its own tag, lower-cased
    and hyphenated; nothing for "Not sure")."""
    out: list[str] = []
    for answer in hands or []:
        if not answer or answer == NOT_SURE:
            continue
        hand = next((h for h in HANDS if h.id == answer), None)
        tags = hand.tags if hand else (re.sub(r"[^a-z0-9]+", "-", str(answer).lower()).strip("-"),)
        out += [t for t in tags if t and t not in out]
    return out
