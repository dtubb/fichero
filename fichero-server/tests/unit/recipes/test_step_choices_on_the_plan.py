"""The Start plan lists each step's candidates and the menu is an override of Set Up's pick (`source.onboard.step-candidates-on-the-plan`,
`source.onboard.step-choice-overrides-the-pick`; #4951, #5922).

The cloud candidate here is the Claude card a project with no Anthropic row still lists (it says to add the key first), so no provider
is needed in the app database."""
from __future__ import annotations

import pytest

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

CLAUDE = "anthropic:claude@settings"


@pytest.fixture
def claude_row(app_db):
    from fichero_server.models import Model, Provider, ProviderType

    row = app_db.save_provider(Provider(name="Anthropic", provider_type=ProviderType("anthropic")))
    app_db.save_model(Model(provider_id=row.id, name="Claude Sonnet", model_id="claude-sonnet-4-5"))
    return row


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


def test_every_candidate_the_plan_lists_can_be_chosen_cloud_readers_included(client, project, claude_row):
    """The menu and `use-candidate` take cards from one list (`_offered_cards`): a listed candidate is never refused as 'not found'."""
    choices = _plan(client)["step_choices"]
    assert any(c["runs_on"].startswith("cloud:") for ch in choices for c in ch["candidates"]), "no cloud reader listed"
    for choice in choices:
        for candidate in choice["candidates"]:
            r = client.post("/api/recipes/project/steps/use-candidate", json={"step": choice["step"], "card": candidate["card"]})
            assert r.status_code == 200, (choice["step"], candidate["card"], r.text)


def test_recommended_is_set_ups_pick_and_is_not_guessed_under_a_persons_choice(client, project):
    choice = _read_choice(_plan(client))
    assert [c["card"] for c in choice["candidates"] if c["recommended"]] == [choice["picked"]]
    client.post("/api/recipes/project/steps/use-candidate", json={"step": choice["step"], "card": CLAUDE})
    under = _read_choice(_plan(client))
    assert under["chosen_by"] == "person" and not any(c["recommended"] for c in under["candidates"])


def test_each_candidate_carries_its_cost_for_the_set_before_start(client, project, claude_row):
    """`cost_usd` is the TryCost shape: free on this Mac, the price list times the pages for a priced cloud model, unknown without a price."""
    plan = _plan(client)
    pages = plan["estimate"]["pages"]
    candidates = _read_choice(plan)["candidates"]
    local = [c for c in candidates if c["local"]]
    assert local and all(c["cost_usd"] == {"value": 0.0, "basis": "estimate", "measured": False, "why": None,
                                           "from": "free on this Mac"} for c in local)
    cloud = [c for c in candidates if not c["local"]]
    assert cloud and all(c["cost_usd"] is None or c["cost_usd"]["basis"] in ("estimate", "unknown") for c in cloud)
    priced = [c for c in cloud if c["cost_usd"] and c["cost_usd"]["basis"] == "estimate"]
    assert not pages or all(c["cost_usd"]["value"] > 0 for c in priced)


def test_a_cloud_choice_the_project_cannot_use_is_not_run_in_place_and_nothing_stands_in_for_it(client, project):
    """`source.onboard.step-choice-overrides-the-pick`: the choice stays the step's, the plan skips the step with the sentence on that
    step (here: the project keeps its pages on this Mac), and no other model is swapped in."""
    step = _read_choice(_plan(client))["step"]
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": CLAUDE}).status_code == 200
    plan = _plan(client)
    skipped = next((s for s in plan["skipped"] if s["step"] == step), None)
    assert skipped is not None and "keeps its pages here" in skipped["why"], plan["skipped"]
    assert _read_choice(plan)["picked"] == CLAUDE and not any(f["step"] == step and f.get("used") for f in plan["fallbacks"])
