"""Tie text to lines runs a Kraken reader, so setup offers a picker for it (#6256).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md, `source.job.tie-text-to-lines`. WHY: with
`needs_a_model=False` the step row had no model finder though Start runs it with the step's Kraken reader.
"""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


def test_tie_text_to_lines_needs_a_model_and_the_finder_lists_the_kraken_readers(client, mac):  # noqa: F811
    jobs = {j["id"]: j["needs_a_model"] for j in client.get("/api/recipes/jobs").json()["items"]}
    assert jobs["tie-text-to-lines"] is True

    r = client.get("/api/recipes/candidates", params={"job": "tie-text-to-lines", "scripts": "Latn", "languages": "en"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and all("kraken" in str(i["pin"]) or "zenodo" in str(i["pin"]) for i in items), items
