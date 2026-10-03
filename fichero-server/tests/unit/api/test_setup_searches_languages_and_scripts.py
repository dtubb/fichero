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
