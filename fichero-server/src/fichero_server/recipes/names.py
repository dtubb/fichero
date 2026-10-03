"""Search the world's languages and scripts for setup (`source.onboard.widget-and-search`).

Languages: ISO 639-3 (about 8,000, historic and constructed included), from the declared
`iso639-lang` package; a language with a two-letter code answers with it (the BCP 47 form), else
its three-letter code. Scripts: ISO 15924 (`seed/iso15924.txt`, the Unicode Consortium's published
table, shipped with the engine). Setup used Apple's locale list, which knows only the languages an
OS is localised for: no Old Spanish, no Syriac dialects, no undeciphered scripts.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

SCRIPTS_FILE = Path(__file__).parent / "seed" / "iso15924.txt"


@lru_cache(maxsize=1)
def _languages() -> tuple[tuple[str, str], ...]:
    from iso639 import iter_langs

    return tuple((lang.pt1 or lang.pt3, lang.name) for lang in iter_langs() if lang.pt3)


@lru_cache(maxsize=1)
def _scripts() -> tuple[tuple[str, str], ...]:
    rows = []
    for line in SCRIPTS_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            code, _number, english, *_rest = line.split(";")
            rows.append((code, english))
    return tuple(rows)


def _search(rows: tuple[tuple[str, str], ...], query: str, limit: int) -> list[dict[str, str]]:
    """Exact code first, then names starting with the query, then names containing it."""
    q = query.strip().lower()
    if not q:
        return []
    exact = [r for r in rows if r[0].lower() == q]
    starts = [r for r in rows if r not in exact and r[1].lower().startswith(q)]
    contains = [r for r in rows if r not in exact and r not in starts and q in r[1].lower()]
    return [{"code": code, "name": name} for code, name in (exact + starts + contains)[:limit]]


def search_languages(query: str, limit: int = 20) -> list[dict[str, str]]:
    return _search(_languages(), query, limit)


def search_scripts(query: str, limit: int = 20) -> list[dict[str, str]]:
    return _search(_scripts(), query, limit)
