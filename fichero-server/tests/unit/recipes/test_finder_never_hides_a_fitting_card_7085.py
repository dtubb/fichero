"""#7085: the model finder never hides a card whose script, language, material and period all fit the project behind the
per-tier cap, and Show All lists every candidate that does the job, searchable by name."""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401  (fixtures)

MCCATMUS = "kraken:zenodo/10.5281/zenodo.13788177@unpinned"
# The Spanish handwriting project of the bug: Latn, es, handwriting, a 19th-century date range.
ASK = {"job": "read-a-line", "scripts": "Latn", "languages": "es", "material": "handwriting", "period": "1800-1899"}


def _ids(client, **extra):
    r = client.get("/api/recipes/candidates", params={**ASK, **extra})
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]


def test_mccatmus_is_in_the_first_list_for_a_nineteenth_century_spanish_handwriting_project(client, mac):
    assert MCCATMUS in _ids(client, worth_only=True)


def test_a_fitting_card_is_never_cut_by_the_cap(client, mac):
    from fichero_server.api.routes.system.recipes import ModelCandidate, worth_listing

    items = client.get("/api/recipes/candidates", params={**ASK, "worth_only": False}).json()["items"]
    kept = worth_listing([ModelCandidate(**i) for i in items], per_tier=0, languages=frozenset({"es"}))
    assert MCCATMUS in [i.id for i in kept]


def test_show_all_lists_every_candidate_and_search_narrows_it(client, mac):
    capped = _ids(client, worth_only=True)
    everything = _ids(client, worth_only=False)
    assert set(capped) <= set(everything)
    found = _ids(client, worth_only=False, q="mccatmus")
    assert MCCATMUS in found and len(found) < len(everything)
