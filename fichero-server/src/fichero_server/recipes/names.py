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


#: Names scholars use that neither ISO nor Glottolog lists, by ISO 639-3 code (#5595): a search or a typed name
#: finds the language by them too.
ALSO_CALLED: dict[str, tuple[str, ...]] = {
    "chu": ("Old Church Slavonic", "Church Slavonic", "Old Slavonic", "Old Bulgarian"),
    "gez": ("Ge'ez", "Ge’ez", "Classical Ethiopic"),
    "lzh": ("Classical Chinese",),
    "ota": ("Ottoman",),
}
#: Languages a model card that lists the first also covers, because they are written as it (#5595): a Syriac
#: reader reads Classical Syriac, which setup stores as `syc` while the cards list `syr`.
ALSO_COVERS: dict[str, tuple[str, ...]] = {"syr": ("syc",)}


def languages_covered(tags) -> frozenset[str]:
    """A card's languages with those written as them (`ALSO_COVERS`)."""
    tags = frozenset(tags)
    return tags | {kin for t in tags for kin in ALSO_COVERS.get(t, ())}


def _plain(name: str) -> str:
    """A name without its parenthesised dates or note: "Old Irish (to 900)" -> "Old Irish"."""
    return name.split(" (")[0].strip()


@lru_cache(maxsize=1)
def _languages() -> tuple[tuple[dict, str], ...]:
    """Each row with the text it is searched by: its name, the name without its dates ("Old Irish" for "Old Irish
    (to 900)"), Glottolog's name where that differs, and any name scholars also use (`ALSO_CALLED`)."""
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
        names = [lang.name, _plain(lang.name), glotto[gc][2] if gc else "", *ALSO_CALLED.get(lang.pt3, ())]
        rows.append(({"code": tag_of[lang.pt3], "name": lang.name, "glottocode": gc, "level": "language"},
                     "\n".join(dict.fromkeys(n for n in names if n)).lower()))
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


# --- Resolving a typed word to its tag (`source.onboard.language-stored-as-tag`, #5479) -------------

#: A Glottolog-only language's private-use tag, as setup stores it (`RecipeSetupStore`).
PRIVATE_USE_PREFIX = "und-x-"


@lru_cache(maxsize=1)
def _language_tags() -> dict[str, str]:
    """Every ISO 639 code (1, 2B, 2T, 3), lower case -> the BCP 47 tag setup stores for it."""
    from iso639 import iter_langs

    tags: dict[str, str] = {}
    for lang in iter_langs():
        if lang.pt3:
            tag = lang.pt1 or lang.pt3
            for code in (lang.pt1, lang.pt2b, lang.pt2t, lang.pt3):
                if code:
                    tags.setdefault(code.lower(), tag)
    return tags


def _as_tag(value: str) -> str | None:
    """The tag a value already is (a known primary subtag, its subtags kept), or None."""
    v = value.strip()
    if v.lower().startswith(PRIVATE_USE_PREFIX):
        return PRIVATE_USE_PREFIX + v[len(PRIVATE_USE_PREFIX):].lower() \
            if v[len(PRIVATE_USE_PREFIX):].lower() in _glottolog() else None
    primary, _, rest = v.partition("-")
    tag = _language_tags().get(primary.lower())
    return None if tag is None else (f"{tag}-{rest}" if rest else tag)


def resolve_language(value: str) -> str:
    """A language's tag for what setup was given: a tag stays a tag (an ISO 639-2/3 code becomes the
    BCP 47 tag, `spa` -> `es`); a name resolves when exactly one language has it ("spanish" -> `es`).
    Otherwise ValueError, in words: the word is never passed to the rules as if it were a tag."""
    tag = _as_tag(value)
    if tag:
        return tag
    word = value.strip().lower()
    found: dict[str, str] = {}
    for row, text in _languages():
        if row.get("level") == "language" and word in text.split("\n"):
            code = row["code"] or f"{PRIVATE_USE_PREFIX}{row['glottocode']}"
            found.setdefault(code, row["name"])
    if len(found) == 1:
        return next(iter(found))
    if found:
        named = ", ".join(f"{name} ({code})" for code, name in sorted(found.items()))
        raise ValueError(f"'{value}' names more than one language ({named}). Choose it from the list.")
    script = next((row for row, text in _scripts() if word in (row["code"].lower(), text, _plain(text))), None)
    if script:
        raise ValueError(f"'{value}' is a script ({script['code']}), not a language: choose the language written "
                         "in it from the list.")
    near = [row for row in search_languages(value, 10) if row.get("level") == "language" and row.get("code")][:3]
    hint = (" Did you mean " + " or ".join(f"{row['name']} ({row['code']})" for row in near) + "?") if near else ""
    raise ValueError(f"Fichero doesn't know the language '{value}'.{hint} Choose it from the list.")


def resolve_script(value: str) -> str:
    """A script's ISO 15924 code for what setup was given: a code (any case) or the script's English
    name ("latin" -> `Latn`). Otherwise ValueError, in words."""
    word = value.strip().lower()
    for row, text in _scripts():
        if word == row["code"].lower() or word == text:
            return row["code"]
    raise ValueError(f"Fichero doesn't know the script '{value}'. Choose it from the list.")


def language_name(tag: str) -> str:
    """A tag's language name for a sentence ("es" -> "Spanish"); the tag itself when unknown."""
    primary = tag.split("-")[0].lower()
    if tag.lower().startswith(PRIVATE_USE_PREFIX):
        row = _glottolog().get(tag[len(PRIVATE_USE_PREFIX):].lower())
        return row[2] if row else tag
    for row, _text in _languages():
        if row.get("level") == "language" and (row["code"] or "").lower() == primary:
            return row["name"]
    return tag


def script_name(code: str) -> str:
    """A script code's English name for a sentence ("Latn" -> "Latin"); the code itself when unknown."""
    return next((row["name"] for row, _text in _scripts() if row["code"] == code), code)
