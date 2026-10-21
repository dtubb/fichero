"""The Start plan lists each step's candidates and the menu is an override of Set Up's pick (`source.onboard.step-candidates-on-the-plan`,
`source.onboard.step-choice-overrides-the-pick`; #4951, #5922).

The cloud candidate here is the Claude card a project with no Anthropic row still lists (it says to add the key first), so no provider
is needed in the app database."""
from __future__ import annotations

import pytest

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

CLAUDE = "anthropic:claude@settings"


@pytest.fixture
def project(client, with_material, mac):  # noqa: F811
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32, "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    return recipe


def _plan(client):
    r = client.get("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()


def _read_choice(plan):
    return next(c for c in plan["step_choices"] if c["job"] == "read-a-line")


def test_the_plan_lists_the_candidates_of_a_step_and_marks_exactly_one(client, project):
    choice = _read_choice(_plan(client))
    assert choice["chosen_by"] == "setup" and choice["picked"]
    assert [c["card"] for c in choice["candidates"] if c["picked"]] == [choice["picked"]]
    assert sum(c["recommended"] for c in choice["candidates"]) == 1
    claude = next(c for c in choice["candidates"] if c["card"] == CLAUDE)
    assert claude["how"] == "cloud-reads-kraken-lines" and not claude["local"] and not claude["available"]
    assert {n["kind"] for n in claude["needs"]} == {"permission", "key"}  # listed greyed, with what it needs, never hidden


def test_a_choice_is_kept_as_the_persons_and_taking_it_back_restores_set_ups_pick(client, project):
    before = _read_choice(_plan(client))
    step = before["step"]
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": CLAUDE})
    assert used.status_code == 200, used.text
    after = _read_choice(_plan(client))
    assert after["chosen_by"] == "person" and after["picked"] == CLAUDE
    assert next(c for c in after["candidates"] if c["card"] == CLAUDE)["picked"]
    # a saved cloud choice with no key / no permission stays the choice (the step does not swap itself); it says what it needs
    assert not next(c for c in after["candidates"] if c["card"] == CLAUDE)["available"]

    back = client.post("/api/recipes/project/steps/use-setup-pick", json={"step": step})
    assert back.status_code == 200, back.text
    restored = _read_choice(_plan(client))
    assert restored["chosen_by"] == "setup" and restored["picked"] == before["picked"]
    assert not back.json()["recipe"].get("overrides")


def test_taking_back_a_step_already_on_set_ups_pick_is_refused_in_words(client, project):
    step = _read_choice(_plan(client))["step"]
    r = client.post("/api/recipes/project/steps/use-setup-pick", json={"step": step})
    assert r.status_code == 422 and "already in use" in r.json()["detail"]
    assert client.post("/api/recipes/project/steps/use-setup-pick", json={"step": "nope"}).status_code == 422
