"""`GET /api/source-settings/resolve` reads the segment's text when nothing is stated (#5176).

WHY: on a real imported Syriac line the resolver answered language "English" as a fallback ("no
text to detect from" -- the line has Syriac text), script not determined, direction ltr. The
Inspector shows that answer, and export and layout would use it. The page text's derivation
already read direction from the letters; the resolver did not, so the two surfaces disagreed
about the same line. Now one set of rungs: the letters give the script (detected, and said
so), the script's letters the direction, and a language is never guessed from a script -- it is
"not determined", naming the script. If this regresses, a Syriac line is English and ltr again.

The file is the real Vienna Syriac folio; that it states no language, script or direction, and
what its lines' letters are, is read with lxml.
"""

from __future__ import annotations

import unicodedata

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import SYRIAC, _import
from tests.unit.api.test_reader_line_map import _view


def _resolve(client, segment_id: str) -> dict[str, dict]:
    response = client.get("/api/source-settings/resolve", params={"segment_id": segment_id})
    assert response.status_code == 200, response.text
    return {s["key"]: s for s in response.json()["settings"]}


def _line(client, doc_id: str, text: str) -> str:
    page = _view(client, doc_id)[0]["pages"][0]
    return next(l["segment_id"] for l in page["lines"] if page["content"][l["char_start"]:l["char_end"]].strip() == text)


def test_the_file_states_nothing_and_its_lines_are_syriac():
    root = etree.parse(str(SYRIAC)).getroot()
    stated = {a for el in root.iter() if isinstance(el.tag, str)
              for a in ("primaryLanguage", "primaryScript", "readingDirection") if el.get(a)}
    assert stated == set()
    first = "".join(next(root.iter("{*}TextLine")).find("{*}TextEquiv/{*}Unicode").itertext())
    assert all(unicodedata.name(ch).startswith("SYRIAC") for ch in first if ch.isalpha())


def test_a_syriac_line_resolves_syrc_rtl_and_no_guessed_language(db, client):
    doc_id = _import(db, SYRIAC)
    root = etree.parse(str(SYRIAC)).getroot()
    first = "".join(next(root.iter("{*}TextLine")).find("{*}TextEquiv/{*}Unicode").itertext()).strip()
    got = _resolve(client, _line(client, doc_id, first))

    assert (got["script"]["value"], got["script"]["source"]) == ("Syrc", "detected")
    assert "letters of its text" in got["script"]["basis"]
    assert got["direction"]["value"] == "rtl" and "letters of its text (Syrc)" in got["direction"]["basis"]
    assert got["language"]["value"] is None and got["language"]["status"] == "unknown"
    assert "Syrc" in got["language"]["basis"] and "English" not in str(got["language"])


def test_the_latin_folio_number_resolves_latn_ltr(db, client):
    doc_id = _import(db, SYRIAC)
    got = _resolve(client, _line(client, doc_id, "1v"))
    assert (got["script"]["value"], got["direction"]["value"]) == ("Latn", "ltr")


def test_a_stated_script_still_wins_over_the_letters(db, client):
    doc_id = _import(db, SYRIAC)
    registry.invoke(db, "source_setting.set",
                    {"level": "node", "key": "script", "value": "Syre", "target_id": doc_id}, BOOT)
    line = _view(client, doc_id)[0]["pages"][0]["lines"][1]["segment_id"]
    got = _resolve(client, line)
    assert got["script"]["value"] == "Syre" and got["script"]["source"] != "detected"


def test_a_line_with_no_text_and_nothing_stated_is_not_determined_never_english():
    """#5231: a hand-drawn line with no reading showed "Language: English · a fallback". What the
    Inspector shows never guesses English; the legacy fallback stays only for tools that must run."""
    from fichero_server.llm.language_policy import resolve_language

    shown = resolve_language(detect=False, guess_english=False)
    assert shown.language is None and shown.status == "unknown", shown
    assert "English" not in str(shown), shown
    assert resolve_language(detect=False).language == "English"  # the tools' legacy default, unchanged
