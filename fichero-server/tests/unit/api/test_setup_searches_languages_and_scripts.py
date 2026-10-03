"""Setup searches every language and script, not only the ones an OS is localised for.

WHY: setup's language and script fields used Apple's locale list, so a historian could not pick Old
Spanish, Syriac, Cherokee's syllabary or a script nobody localises an OS for. The engine now searches
ISO 639-3 (about 8,000 languages, historic ones included) and ISO 15924 (every script code).
"""
from __future__ import annotations


def _codes(client, kind, q):
    r = client.get(f"/api/recipes/{kind}", params={"q": q})
    assert r.status_code == 200, r.text
    return [item["code"] for item in r.json()["items"]]


def test_languages_by_name_and_code_with_the_short_code_preferred(client):
    assert _codes(client, "languages", "spanish")[0] == "es"
    assert "osp" in _codes(client, "languages", "old spanish")
    assert _codes(client, "languages", "syc")[0] == "syc"   # Classical Syriac, no two-letter code


def test_scripts_by_name_and_code(client):
    assert _codes(client, "scripts", "Cher")[0] == "Cher"
    assert "Syrc" in _codes(client, "scripts", "syriac")
    assert _codes(client, "scripts", "") == []


# Glottolog 5.3 (CC BY 4.0) joins ISO 639-3. WHY: ISO has no code for many dialects and under-resourced
# languages, and the spec keeps the BCP 47 tag and the glottocode as two facts (`source.lang.registries`).
# The expected codes below are Glottolog's own (glottolog.org), not made up.

def _items(client, q):
    r = client.get("/api/recipes/languages", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_an_iso_language_carries_its_glottocode(client):
    syriac = _items(client, "syc")[0]
    assert (syriac["code"], syriac["glottocode"], syriac["level"]) == ("syc", "clas1252", "language")
    assert _items(client, "spanish")[0]["glottocode"] == "stan1288"


def test_a_dialect_has_its_glottocode_its_language_and_its_language_tag(client):
    andean = next(i for i in _items(client, "andean spanish") if i["glottocode"] == "ande1249")
    assert (andean["level"], andean["code"], andean["language"]) == ("dialect", "es", "Spanish")


def test_a_glottocode_finds_the_dialect_but_a_tag_does_not_return_every_dialect(client):
    assert _items(client, "east2681")[0]["name"] == "Eastern Syriac"
    by_tag = _items(client, "es")
    assert (by_tag[0]["name"], by_tag[0]["level"]) == ("Spanish", "language")
    assert "ande1249" not in [i["glottocode"] for i in by_tag]  # its dialects share the tag but are not exact hits


def test_a_glottolog_family_is_not_offered(client):
    assert all(i["glottocode"] != "alba1267" for i in _items(client, "albanian"))  # the family, not `sqi`
