"""A date written as a feast: "dia de San Juan de 1791", "Easter 1700", "Michaelmas 1650" (`source.date.feast-days`, #5542).

A fixed feast is its day of the year; a movable one is a number of days after Easter, which the library's computus
gives (`convertdate.holidays`: Gregorian for the western church, the Julian Easter for a source that kept the Julian
calendar). The table is a data file (`recipes/seed/feast-days.yaml`): a name in any language is one more row, and no
language is named here. The answer keeps its reasoning, and a name that can mean two feasts names the other as an
alternative with a lower confidence. A name the table does not hold gives no date, never a guess.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED = Path(__file__).parent / "recipes" / "seed" / "feast-days.yaml"
_YEAR = re.compile(r"^(?P<phrase>.+?)\s+(?P<year>\d{3,4})$")


@dataclass(frozen=True)
class FeastDate:
    jdn: int
    calendar: str
    feast: str
    reasoning: str
    alternatives: tuple[str, ...]
    confidence: float


def fold(text: str) -> str:
    """Lower case, no accents, no full stops or apostrophes, single spaces: how names are written in the table."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[.'’`]", "", plain.lower()).replace("-", " ").split())


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    """The feasts by name: {folded name: feast id}, with the rows, introducers and joiners. A name two feasts
    both claim raises: a table that cannot say which feast a word is would answer by file order."""
    import yaml

    data = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    by_name: dict[str, str] = {}
    for feast, row in data["feasts"].items():
        if ("easter" in row) == ("date" in row):
            raise ValueError(f"{SEED.name}: feast {feast!r} needs exactly one of easter (days after Easter) or date (MM-DD)")
        for name in row["names"]:
            key = fold(name)
            if by_name.setdefault(key, feast) != feast:
                raise ValueError(f"{SEED.name}: {key!r} names both {by_name[key]!r} and {feast!r}")
    for feast, row in data["feasts"].items():
        for other in row.get("also", ()):
            if other not in data["feasts"]:
                raise ValueError(f"{SEED.name}: feast {feast!r} lists {other!r} as also, which is not a feast")
    return {
        "feasts": data["feasts"], "by_name": by_name,
        "introducers": sorted((fold(i) for i in data["introducers"]), key=len, reverse=True),
        "joiners": {fold(j) for j in data["joiners"]},
    }


def _feast_named(phrase: str, t: dict[str, Any]) -> str | None:
    if phrase in t["by_name"]:
        return t["by_name"][phrase]
    for lead in t["introducers"]:
        if phrase.startswith(lead + " ") and phrase[len(lead) + 1:] in t["by_name"]:
            return t["by_name"][phrase[len(lead) + 1:]]
    return None


def easter_jdn(year: int, *, julian_calendar: bool) -> int:
    from convertdate import holidays

    from fichero_server.histdate import gregorian_to_jdn

    return gregorian_to_jdn(*holidays.easter(year, "orthodox" if julian_calendar else "western"))


def parse_feast_date(text: str, *, julian_calendar: bool = False) -> FeastDate | None:
    """The day a feast and a year name, or None when the text is not a feast of the table in a year."""
    from fichero_server.histdate import gregorian_to_jdn, julian_to_jdn

    t = table()
    found = _YEAR.match(fold(text))
    if not found:
        return None
    year = int(found["year"])
    words = found["phrase"].split()
    for n in (2, 1):
        if len(words) > n and " ".join(words[-n:]) in t["joiners"]:
            words = words[:-n]
            break
    feast = _feast_named(" ".join(words), t)
    if feast is None:
        return None
    row = t["feasts"][feast]
    calendar = "julian" if julian_calendar else "gregorian"
    if "easter" in row:
        easter = easter_jdn(year, julian_calendar=julian_calendar)
        jdn = easter + row["easter"]
        reasoning = (f"{feast} is Easter {row['easter']:+d} days; Easter {year} falls on JDN {easter} ({calendar} "
                     f"computus), so {feast} falls on JDN {jdn}")
    else:
        month, day = (int(n) for n in row["date"].split("-"))
        jdn = (julian_to_jdn if julian_calendar else gregorian_to_jdn)(year, month, day)
        reasoning = f"{feast} is a fixed feast on {row['date']} ({calendar} calendar), in {year}"
    alternatives = tuple(row.get("also", ()))
    if alternatives:
        reasoning += f"; the same words can name {', '.join(alternatives)}, the commoner reading taken"
    return FeastDate(jdn, calendar, feast, reasoning, alternatives, 0.55 if alternatives else 0.8)
