"""`source.job.find-statements.candidates` (#5637): Apple Intelligence and a cloud text model are candidates for Find
statements beside the parser and an installed text model; a cloud one needs permission until pages may leave."""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)


def test_apple_and_a_cloud_text_model_are_statements_candidates(client, mac):  # noqa: F811
    r = client.get("/api/recipes/candidates", params={"job": "find-statements", "scripts": "Latn", "languages": "es"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ids = {i["id"] for i in items}
    assert "apple:intelligence/foundation-models@os" in ids, ids
    cloud = [i for i in items if "cloud" in i["pin"] and not i["id"].startswith("apple:")]
    assert cloud and all(i["needs_permission"] is True for i in cloud), [(i["id"], i["needs_permission"]) for i in cloud]
    assert any(i["id"].startswith("spacy:svo/") for i in items), "the free parser stays a candidate"
