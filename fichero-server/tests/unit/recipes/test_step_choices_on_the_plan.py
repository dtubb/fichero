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
    for choice in (c for c in choices if c["in_plan"]):  # a step not in the plan is turned on in Set Up, not chosen
        for candidate in (c for c in choice["candidates"] if not c["card"].startswith("corrects-unsure:")):  # its own test below
            r = client.post("/api/recipes/project/steps/use-candidate", json={"step": choice["step"], "card": candidate["card"]})
            assert r.status_code == 200, (choice["step"], candidate["card"], r.text)


def test_recommended_is_set_ups_pick_and_is_not_guessed_under_a_persons_choice(client, project):
    choice = _read_choice(_plan(client))
    assert [c["card"] for c in choice["candidates"] if c["recommended"]] == [choice["picked"]]
    client.post("/api/recipes/project/steps/use-candidate", json={"step": choice["step"], "card": CLAUDE})
    under = _read_choice(_plan(client))
    assert under["chosen_by"] == "person" and not any(c["recommended"] for c in under["candidates"])


def test_each_candidate_carries_its_cost_for_the_set_before_start(client, project, claude_row, monkeypatch):
    """`cost_usd` is the TryCost shape: free on this Mac, the price list times the pages for a priced cloud model, unknown without a price."""
    from fichero_server.recipes import routes

    monkeypatch.setattr(routes, "_cloud_cost", lambda model, pages=1: 0.01 * pages)  # the price list knows the cloud models
    plan = _plan(client)
    pages = plan["estimate"]["pages"]
    assert pages > 0, "the test project has no pages to price"
    candidates = _read_choice(plan)["candidates"]
    local = [c for c in candidates if c["runs_on"] == "this-mac"]  # only this Mac is free: a cluster or GPU service is not
    assert local and all(c["cost_usd"] == {"value": 0.0, "basis": "estimate", "measured": False, "why": None,
                                           "from": "free on this Mac"} for c in local)
    priced = [c for c in candidates if c["how"] == "cloud-reads-kraken-lines" and c["cost_usd"] and c["cost_usd"]["value"]]
    assert priced, "no cloud candidate was priced"  # a test that prices nothing must fail, not pass vacuously
    assert all(c["cost_usd"]["value"] == round(0.01 * pages, 2) and c["cost_usd"]["basis"] == "estimate" for c in priced)
    unsure = [c for c in candidates if c["how"] == "kraken-then-cloud-corrects"]
    assert unsure and all(c["cost_usd"]["basis"] == "upper bound" for c in unsure if c["cost_usd"]["value"])


def test_the_cost_of_a_cloud_correction_of_the_unsure_lines_is_an_upper_bound():
    from types import SimpleNamespace

    from fichero_server.recipes.step_choices import _cost

    card = SimpleNamespace(runs_on="cloud:anthropic", pin={"cloud": "anthropic", "model": "m"}, cost_per_page=0.02)
    bound = _cost(card, 10, "kraken-then-cloud-corrects")
    assert bound["basis"] == "upper bound" and bound["value"] == 0.2 and "unsure lines" in bound["from"]
    assert _cost(card, 10, "cloud-reads-kraken-lines")["basis"] == "estimate"


def test_a_cloud_choice_the_project_cannot_use_is_not_run_in_place_and_nothing_stands_in_for_it(client, project):
    """`source.onboard.step-choice-overrides-the-pick`: the choice stays the step's, the plan skips the step with the sentence on that
    step (here: the project keeps its pages on this Mac), and no other model is swapped in."""
    step = _read_choice(_plan(client))["step"]
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": CLAUDE}).status_code == 200
    plan = _plan(client)
    skipped = next((s for s in plan["skipped"] if s["step"] == step), None)
    assert skipped is not None and "keeps its pages here" in skipped["why"], plan["skipped"]
    assert _read_choice(plan)["picked"] == CLAUDE and not any(f["step"] == step and f.get("used") for f in plan["fallbacks"])


def test_beside_a_kraken_reader_the_plan_lists_correct_with_the_unsure_lines_wording_and_how_to_turn_it_on(client, project, claude_row):
    """`source.recipe.kraken-reads-cloud-corrects-unsure`: Correct is not in the plan, but it is found: Kraken reads, a cloud model
    corrects only the lines Kraken is unsure of, listed with the way to turn it on and its cost as an upper bound."""
    plan = _plan(client)
    assert not any(c["job"] == "correct" and c["in_plan"] for c in plan["step_choices"]), "this project has no Correct step"
    entry = next(c for c in plan["step_choices"] if c["job"] == "correct")
    assert entry["in_plan"] is False and entry["wording"] == "Kraken reads; a cloud model corrects only the lines Kraken is unsure of"
    assert entry["turn_on"]["answer"] == "correct_with_a_second_model"
    assert entry["candidates"] and all(c["how"] == "kraken-then-cloud-corrects" and not c["local"] for c in entry["candidates"])
    assert {n["kind"] for c in entry["candidates"] for n in c["needs"]} >= {"permission"}  # listed greyed, never hidden
    assert all(c["cost_usd"] is None or c["cost_usd"]["basis"] in ("upper bound", "unknown") for c in entry["candidates"])


def test_the_certainty_bar_is_set_ups_answer_as_a_number_or_none_for_the_whole_page():
    from fichero_server.recipes.step_choices import _certainty_bar

    assert _certainty_bar({"job_answers": {"review_certainty_bar": "0.7"}}) == 0.7
    assert _certainty_bar({"job_answers": {"review_certainty_bar": "whole-page"}}) is None
    assert _certainty_bar({"job_answers": {"review_certainty_bar": "7"}}) is None and _certainty_bar(None) is None


def test_only_a_card_that_runs_on_this_mac_is_free_a_cluster_or_gpu_service_is_unknown():
    from types import SimpleNamespace

    from fichero_server.recipes.step_choices import _cost

    here = _cost(SimpleNamespace(runs_on="this-mac"), 10)
    assert here["value"] == 0.0 and "free" in here["from"]
    for where, words in (("cluster", "a cluster"), ("gpu-service", "a GPU service")):
        c = _cost(SimpleNamespace(runs_on=where), 10)
        assert c["value"] is None and c["basis"] == "unknown" and words in c["from"] and "free" not in c["from"]
        assert where not in c["from"], "an internal id is not words"


def _unsure(plan):
    return next(c for c in _read_choice(plan)["candidates"] if c["card"] == "corrects-unsure:" + CLAUDE)


def test_the_read_step_also_lists_kraken_then_a_cloud_correction_and_choosing_it_turns_correct_on(client, project):
    """`source.recipe.kraken-reads-cloud-corrects-unsure`: on the READ step's menu, own card id form; Kraken stays the reader."""
    before = _read_choice(_plan(client))
    step = before["step"]
    option = _unsure(_plan(client))
    assert option["how"] == "kraken-then-cloud-corrects" and not option["picked"] and not option["local"]
    r = client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": option["card"]})
    assert r.status_code == 200, r.text
    plan = _plan(client)
    read = _read_choice(plan)
    assert read["picked"] == option["card"] and read["chosen_by"] == "person"
    assert [c["card"] for c in read["candidates"] if c["picked"]] == [option["card"]]  # exactly one, Kraken's mark moved to it
    recipe = r.json()["recipe"]
    reader = next(s for s in recipe["steps"] if s["id"] == step)
    assert "kraken" in reader["model"] or reader["card"]["id"].startswith("kraken:"), "Kraken stays the reader"
    correct = next(c for c in plan["step_choices"] if c["job"] == "correct")
    assert correct["in_plan"] and correct["picked"] == CLAUDE and correct["wording"].startswith("Kraken reads;")
    assert CLAUDE in [c["card"] for c in correct["candidates"]], "a keyed reader with no listed price stays on Correct's menu"
    assert r.json()["answers"]["job_answers"]["correct_with_a_second_model"] is True


def test_taking_back_kraken_then_a_cloud_correction_turns_correct_off_again(client, project):
    step = _read_choice(_plan(client))["step"]
    client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": "corrects-unsure:" + CLAUDE})
    back = client.post("/api/recipes/project/steps/use-setup-pick", json={"step": step})
    assert back.status_code == 200, back.text
    plan = _plan(client)
    assert _read_choice(plan)["chosen_by"] == "setup" and not any(c["picked"] and c["card"].startswith("corrects-unsure:")
                                                                  for c in _read_choice(plan)["candidates"])
    assert not any(s["job"] == "correct" for s in back.json()["recipe"]["steps"]) and not back.json()["recipe"].get("overrides")


def test_kraken_then_a_cloud_correction_is_refused_in_words_when_kraken_is_not_the_reader(client, project):
    step = _read_choice(_plan(client))["step"]
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": CLAUDE}).status_code == 200
    r = client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": "corrects-unsure:" + CLAUDE})
    assert r.status_code == 422 and "where Kraken reads" in r.json()["detail"]


def test_each_candidate_lists_every_place_it_can_run(client, project, claude_row):
    """`places`: the finder's `PlaceOption`s (`where_it_runs`), a cloud model at its provider, Kraken here and at Hugging Face Jobs."""
    candidates = _read_choice(_plan(client))["candidates"]
    cloud = next(c for c in candidates if c["card"] == CLAUDE)
    assert [p["place"] for p in cloud["places"]] == ["provider"] and cloud["places"][0]["name"] == "anthropic"
    kraken = next(c for c in candidates if c["how"] == "kraken")
    assert [p["place"] for p in kraken["places"]][:2] == ["this-mac", "hf-jobs"] and kraken["places"][0]["can"]
    assert all(c["places"] for c in candidates), "every candidate says where it can run"


def test_taking_back_the_read_step_after_unsure_then_a_cloud_reader_returns_set_ups_reader(client, project):
    """## 914: the read step's own override goes too, and Correct is back as Set Up had it (off)."""
    before = _read_choice(_plan(client))
    step = before["step"]
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": "corrects-unsure:" + CLAUDE}).status_code == 200
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": CLAUDE}).status_code == 200
    back = client.post("/api/recipes/project/steps/use-setup-pick", json={"step": step})
    assert back.status_code == 200, back.text
    after = _read_choice(_plan(client))
    assert after["chosen_by"] == "setup" and after["picked"] == before["picked"], "the cloud reader must not stay"
    assert not back.json()["recipe"].get("overrides") and not any(s["job"] == "correct" for s in back.json()["recipe"]["steps"])


def test_taking_back_the_unsure_choice_leaves_correct_on_when_the_person_had_turned_it_on_themselves(client, project):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32, "cloud_allowed": False, "job_answers": {"correct_with_a_second_model": True}}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    step = _read_choice(_plan(client))["step"]
    assert client.post("/api/recipes/project/steps/use-candidate", json={"step": step, "card": "corrects-unsure:" + CLAUDE}).status_code == 200
    back = client.post("/api/recipes/project/steps/use-setup-pick", json={"step": step})
    assert back.status_code == 200, back.text
    assert back.json()["answers"]["job_answers"]["correct_with_a_second_model"] is True, "the person's own answer stays"
    assert any(s["job"] == "correct" for s in back.json()["recipe"]["steps"]) and not back.json()["recipe"].get("overrides")
