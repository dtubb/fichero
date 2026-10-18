"""`source.onboard.pages-may-leave` (#5768): a cloud candidate shows greyed, "needs permission", until the person
has said pages may leave this Mac; a local one never does."""
from __future__ import annotations

from dataclasses import replace

from fichero_server.recipes.assemble import Answers, needs_permission
from fichero_server.recipes.cards import all_seed_cards
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

CLOUD = replace(next(iter(all_seed_cards())), runs_on="cloud:anthropic")


def test_a_cloud_candidate_needs_permission_until_pages_may_leave():
    assert needs_permission(CLOUD, Answers(cloud_allowed=False)) is True
    assert needs_permission(CLOUD, Answers(cloud_allowed=True)) is False


def test_a_local_candidate_never_needs_permission():
    local = next(c for c in all_seed_cards() if c.local and c.runs_on == "this-mac")
    assert needs_permission(local, Answers()) is False


def test_the_candidates_route_carries_the_flag(client, mac):
    r = client.get("/api/recipes/candidates", params={"job": "read-a-line", "scripts": "Latn", "languages": "en"})
    assert r.status_code == 200 and r.json()["items"]
    assert all(i["needs_permission"] is False for i in r.json()["items"] if i["installed"])
