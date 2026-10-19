"""The grey lines under Languages and Writing system (#5834) say ISO 639-3 + Glottolog (historical languages,
dialects) with names from CLDR, and ISO 15924: the search routes really draw on those."""
from __future__ import annotations

from fichero_server.recipes import names


def test_languages_come_from_iso_639_3_and_glottolog():
    assert any(r["code"] == "es" for r in names.search_languages("Spanish"))  # ISO 639-3
    assert names.GLOTTOLOG_FILE.exists() and names.AUTONYMS_FILE.exists()  # Glottolog and CLDR autonyms are shipped


def test_scripts_are_iso_15924():
    assert [r["code"] for r in names.search_scripts("Latn")][:1] == ["Latn"]
    assert names.SCRIPTS_FILE.name == "iso15924.txt"
