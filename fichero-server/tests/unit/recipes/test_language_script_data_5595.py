"""Language and script data that setup searches and stores (#5595), from the esoteric-language run of 2026-10-07.

Through the routes setup calls: `GET /api/recipes/languages`, `POST /api/recipes/assemble`, `PUT /api/recipes/project`
and the Start plan (`source.onboard.widget-and-search`, `source.onboard.language-stored-as-tag`,
`source.onboard.direction-chosen`, `source.onboard.says-no-model`).
"""
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401  (fixtures)


def _codes(client, q):
    r = client.get("/api/recipes/languages", params={"q": q})
    assert r.status_code == 200, r.text
    return [row["code"] for row in r.json()["items"]]


def _assemble(client, **answers):
    return client.post("/api/recipes/assemble", json={"mac_memory_gb": 16, "purposes": ["transcribe"], **answers})


def test_names_scholars_use_find_the_language(client):
    """"Old Church Slavonic", "Slavonic", "Ge'ez" and "Ethiopic" find their language, not nothing."""
    assert "cu" in _codes(client, "Old Church Slavonic") and "cu" in _codes(client, "Slavonic")
    assert "gez" in _codes(client, "Ge'ez") and "gez" in _codes(client, "Ethiopic")
    r = _assemble(client, languages=["Old Church Slavonic"], scripts=["Glag"])
    assert r.status_code == 200, r.text
    assert r.json()["suits"]["languages"] == ["cu"]


def test_a_name_without_its_dates_resolves_and_a_miss_says_what_is_near(client):
    """"Old Irish" is ISO's "Old Irish (to 900)": it resolves to sga (the dialect row sharing the code does not make it
    ambiguous). A name Fichero lacks is refused with the nearest languages; a script's name says it is a script."""
    r = _assemble(client, languages=["Old Irish"], scripts=["Latn"])
    assert r.status_code == 200, r.text
    assert r.json()["suits"]["languages"] == ["sga"]
    miss = _assemble(client, languages=["Old Irishh"], scripts=["Latn"])
    assert miss.status_code == 422 and "doesn't know the language" in miss.json()["detail"]
    script = _assemble(client, languages=["Ethiopic"], scripts=["Ethi"])
    assert script.status_code == 422 and "is a script (Ethi)" in script.json()["detail"], script.text


def test_a_syriac_reader_covers_classical_syriac(client):
    """Classical Syriac is stored as syc; a card listing Syriac (syr) covers it, so no rule refuses it for the
    language alone: the same readers and language-checked steps as for Syriac."""
    from fichero_server.recipes.assemble import Answers, Card, assemble

    syc = _assemble(client, languages=["Classical Syriac"], scripts=["Syrc"]).json()
    assert syc["suits"]["languages"] == ["syc"]
    # No shipped card lists Syriac (the repository's do, online), so the rule is pinned on a card of that shape:
    # a corrector, the job that refuses any card not listing the project's language.
    card = Card(id="t:syriac@1", pin={"hf": "x/syriac-corrector", "revision": "abc"}, jobs=frozenset({"correct"}),
                scripts=frozenset({"Syrc"}), languages=frozenset({"syr"}), material=frozenset())
    step = next(s for s in assemble(Answers(purposes=("transcribe",), languages=frozenset({"syc"}),
                                            scripts=frozenset({"Syrc"})), [card])["steps"] if s["job"] == "correct")
    assert step.get("model") == card.pin, step


def test_vertical_scripts_default_to_their_columns(client):
    """Mongolian defaults to top to bottom with columns left to right, Han and Japanese to columns right to left
    (ruled 2026-09-28); Latin stays left to right; a chosen direction is kept."""
    r = _assemble(client, languages=["mn", "ja", "lzh", "en"], scripts=["Mong", "Jpan", "Hant", "Latn"])
    assert r.status_code == 200, r.text
    r = client.put("/api/recipes/project",
                   json={"answers": {"purposes": ["transcribe"], "languages": ["mn", "ja", "lzh", "en"],
                                     "scripts": ["Mong", "Jpan", "Hant", "Latn"], "directions": {"Jpan": "ltr"}}})
    assert r.status_code == 200, r.text
    directions = client.get("/api/recipes/project").json()["answers"]["directions"]
    assert directions == {"Mong": "ttb-lr", "Jpan": "ltr", "Hant": "ttb", "Latn": "ltr"}


def test_a_step_with_no_model_is_refused_in_words(client, pages):
    """A Coptic recipe has no reader: the Start plan says so in the person's words, never "the model None"."""
    recipe = _assemble(client, languages=["cop"], scripts=["Copt"]).json()
    assert any(s.get("gap") for s in recipe["steps"])
    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["transcribe"], "languages": ["cop"],
                                                             "scripts": ["Copt"]}, "recipe": recipe})
    assert r.status_code == 200, r.text
    refusals = client.get("/api/recipes/project/start").json()["refusals"]
    assert refusals and not [x for x in refusals if "None" in x or "pinned in a known form" in x], refusals
    assert any("Coptic" in x for x in refusals), refusals
