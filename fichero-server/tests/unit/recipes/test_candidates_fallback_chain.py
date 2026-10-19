"""`source.recipe.candidates-fallback-chain` (#4950, #5582, ruled 2026-10-17): a step's candidates are ranked best
first (accuracy in one-point bands: measured on the person's pages, else published); local and cheaper only break
ties inside the band. The step carries the rest, in order, as its chain; a step whose key is missing runs the next
that can (`source.recipe.alternatives-in-order`)."""
from __future__ import annotations

from dataclasses import replace

from fichero_server.recipes.assemble import Answers, assemble
from tests.unit.recipes.test_assemble_by_rule import CARDS

LATIN = Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), "handwriting", cloud_allowed=True)
LOCAL = next(c for c in CARDS if c.id == "ppocrv6-medium")  # published CER 3.9%, local, free
CLOUD = replace(next(c for c in CARDS if c.id == "gemini-flash"), id="cloud-reader",
                jobs=frozenset({"read-a-line"}), cer_published=0.01)


def _read(cards, answers=LATIN):
    return next(s for s in assemble(answers, cards)["steps"] if s["job"] == "read-a-line")


def test_the_better_cloud_reader_beats_a_cheaper_local_one_outside_the_band():
    assert _read([*CARDS, CLOUD])["card"]["id"] == "cloud-reader"


def test_the_cheaper_local_reader_wins_inside_the_band():
    close = replace(CLOUD, cer_published=0.039)  # same one-point band as the local reader
    assert _read([*CARDS, close])["card"]["id"] == "ppocrv6-medium"


def test_a_cloud_reader_is_never_chosen_while_pages_stay_on_this_mac():
    stays = replace(LATIN, cloud_allowed=False)
    assert _read([*CARDS, CLOUD], stays)["card"]["id"] == "ppocrv6-medium"


def test_the_step_carries_the_rest_of_the_candidates_in_order_as_its_chain():
    step = _read([*CARDS, CLOUD])
    assert [c["id"] for c in step["chain"]] == ["ppocrv6-medium"]
    assert step["chain"][0]["model"] == LOCAL.pin


def test_a_step_whose_key_is_missing_runs_the_next_candidate_and_the_plan_names_it(monkeypatch):
    """Start never substitutes silently: the next candidate in the chain runs, and the plan records which and why."""
    from fichero_server.recipes import start
    from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

    monkeypatch.setattr(start, "provider_without_key", lambda step: "OpenAI" if "cloud" in (step.get("model") or {}) else None)
    local = {"id": "local-correct", "model": {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"},
             "runs_on": "this-mac"}
    plan = start.plan_start(_recipe(LINES, READ, {**CLOUD_CORRECT, "chain": [local]}), stays_local=False)

    assert not [s for s in plan["skipped"] if s["step"] == "correct"], plan["skipped"]
    (said,) = plan["fallbacks"]
    assert said["step"] == "correct" and said["from"] == "OpenAI" and said["to"] == "local-correct"
    assert "Needs a key for OpenAI" in said["why"]
    assert any("correct" in run["steps"] for run in plan["runs"])


def test_a_keyless_step_with_no_candidate_left_is_skipped_as_before(monkeypatch):
    from fichero_server.recipes import start
    from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

    monkeypatch.setattr(start, "provider_without_key", lambda step: "OpenAI" if step.get("id") == "correct" else None)
    plan = start.plan_start(_recipe(LINES, READ, {**CLOUD_CORRECT, "chain": []}), stays_local=False)
    assert plan["fallbacks"] == [] and any(s["step"] == "correct" for s in plan["skipped"])


def test_another_cloud_provider_is_offered_and_never_used_without_the_persons_press(monkeypatch):
    from fichero_server.recipes import start
    from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

    monkeypatch.setattr(start, "provider_without_key",
                        lambda step: "OpenAI" if (step.get("model") or {}).get("cloud") == "openai" else None)
    other = {"id": "gemini", "model": {"cloud": "google", "model": "gemini-2.5-flash"}, "runs_on": "cloud:google"}
    plan = start.plan_start(_recipe(LINES, READ, {**CLOUD_CORRECT, "chain": [other]}), stays_local=False)
    (offered,) = plan["fallbacks"]
    assert offered["used"] is False and offered["to"] == "gemini"
    assert any(s["step"] == "correct" for s in plan["skipped"])
    assert all("correct" not in run["steps"] for run in plan["runs"])


def test_a_project_that_measured_its_noise_band_ties_measured_readers_inside_it():
    """The band is the project's own (`source.train.noise-band-per-project`) once its pages measured one: two readers
    measured 3.1% and 5.0% on the person's pages are two points apart in one-point bands, and the same band in a
    measured band of three points, where the free local reader wins the tie."""
    local = replace(LOCAL, cer_measured_here=0.050)
    cloud = replace(CLOUD, cer_published=LOCAL.cer_published, cer_measured_here=0.031)
    assert _read([*CARDS, local, cloud])["card"]["id"] == "cloud-reader"
    assert _read([*CARDS, local, cloud], replace(LATIN, noise_band=0.03))["card"]["id"] == "ppocrv6-medium"


def test_the_recipe_the_project_assembles_reads_its_measured_band(monkeypatch, tmp_path):
    from fichero_server.api.routes.system import recipes as route
    from fichero_server.recipes.project import write_noise_band

    seen = []
    monkeypatch.setattr(route, "assemble", lambda a, cards, offered: seen.append(a) or {"steps": []})
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "loose_pages": False, "faded_pages": False}
    route._assemble(answers, tmp_path)
    write_noise_band(tmp_path, 0.03, pages=40, model="kraken")
    route._assemble(answers, tmp_path)
    assert [a.noise_band for a in seen] == [0.01, 0.03]  # unmeasured: the one-point band, as before
