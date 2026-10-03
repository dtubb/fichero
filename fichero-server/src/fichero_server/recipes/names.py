"""Search the world's languages and scripts for setup (`source.onboard.widget-and-search`).

Languages: ISO 639-3 (about 8,000, historic and constructed included), from the declared
`iso639-lang` package, joined with Glottolog 5.3 (`seed/glottolog.txt.gz`, CC BY 4.0), which adds
about 600 languages ISO has no code for and about 13,000 dialects. Each answer keeps the two
systems apart (`source.lang.registries`): `code` is the BCP 47 tag (the two-letter code where
there is one, else ISO 639-3; a dialect carries its language's tag, since BCP 47 registers no
dialect subtags for these), `glottocode` is Glottolog's, and either may be absent. A language
Glottolog knows and ISO does not has no tag. Glottolog families are left out: a family is not
something a page is written in. Scripts: ISO 15924 (`seed/iso15924.txt`, the Unicode
Consortium's published table, shipped with the engine).
"""
from __future__ import annotations

import gzip
from functools import lru_cache
from pathlib import Path

SEED = Path(__file__).parent / "seed"
SCRIPTS_FILE = SEED / "iso15924.txt"
GLOTTOLOG_FILE = SEED / "glottolog.txt.gz"


@lru_cache(maxsize=1)
def _glottolog() -> dict[str, tuple[str, str, str, str]]:
    """glottocode -> (ISO 639-3 or "", "language" | "dialect", name, a dialect's language glottocode)."""
    rows = {}
    with gzip.open(GLOTTOLOG_FILE, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                glottocode, iso, level, name, language = line.rstrip("\n").split("\t")
                rows[glottocode] = (iso, "dialect" if level == "d" else "language", name, language)
    return rows


@lru_cache(maxsize=1)
def _languages() -> tuple[tuple[dict, str], ...]:
    """Each row with the text it is searched by (its name, and Glottolog's name where that differs)."""
    from iso639 import iter_langs

    glotto = _glottolog()
    glottocode_of = {iso: gc for gc, (iso, _level, _name, _lang) in glotto.items() if iso}
    tag_of: dict[str, str] = {}
    rows = []
    for lang in iter_langs():
        if not lang.pt3:
            continue
        tag_of[lang.pt3] = lang.pt1 or lang.pt3
        gc = glottocode_of.get(lang.pt3)
        also = glotto[gc][2] if gc else ""
        rows.append(({"code": tag_of[lang.pt3], "name": lang.name, "glottocode": gc, "level": "language"},
                     f"{lang.name}\n{also}".lower()))
    for gc, (iso, level, name, language) in glotto.items():
        if iso in tag_of:
            continue  # listed above under its ISO name
        row = {"code": None, "name": name, "glottocode": gc, "level": level}
        if level == "dialect":
            row["code"] = tag_of.get(glotto[language][0])
            row["language"] = glotto[language][2]
        rows.append((row, name.lower()))
    return tuple(rows)


@lru_cache(maxsize=1)
def _scripts() -> tuple[tuple[dict, str], ...]:
    rows = []
    for line in SCRIPTS_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            code, _number, english, *_rest = line.split(";")
            rows.append(({"code": code, "name": english}, english.lower()))
    return tuple(rows)


def _search(rows: tuple[tuple[dict, str], ...], query: str, limit: int) -> list[dict]:
    """Exact code (or glottocode) first, then names starting with the query, then names containing it."""
    q = query.strip().lower()
    if not q:
        return []
    exact, starts, contains = [], [], []
    for row, text in rows:
        own_code = "" if row.get("level") == "dialect" else (row["code"] or "").lower()  # a dialect borrows its tag
        if q in (own_code, row.get("glottocode") or ""):
            exact.append(row)
        elif any(name.startswith(q) for name in text.split("\n")):
            starts.append(row)
        elif q in text:
            contains.append(row)
    return (exact + starts + contains)[:limit]


def search_languages(query: str, limit: int = 20) -> list[dict]:
    return _search(_languages(), query, limit)


def search_scripts(query: str, limit: int = 20) -> list[dict]:
    return _search(_scripts(), query, limit)
