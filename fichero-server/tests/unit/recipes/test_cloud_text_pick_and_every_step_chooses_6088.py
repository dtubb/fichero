"""The rules pick the cheapest adequate cloud text model for Translate, Catalogue and Correct, and every step that needs a model
can choose one (`source.recipe.cloud-text-pick`, `source.find.every-step-lists-models`; owner ruling 2026-10-24, brief
cloud-autopick-2026-10-24, #6088). Fake keys and fake cards only: no real call, no real key."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.recipes.assemble import Answers, Card, assemble
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

TEXT = frozenset({"find-statements", "split-into-entries", "find-names-tag-words", "describe-for-the-catalogue",
                  "translate-transliterate-normalise", "correct"})
STEPS = ("translate-transliterate-normalise", "describe-for-the-catalogue", "correct")


def _cloud(provider: str, model: str, price: float) -> Card:
    return Card(id=f"{provider}:{model}@row", pin={"cloud": provider, "model": model}, jobs=TEXT, scripts=None, languages=None,
                material=frozenset(), runs_on=f"cloud:{provider}", cost_per_page=price, offered_only=True, source="installed",
                note=f"{model} ({provider})", open_licence=True)


def _local() -> Card:
    return Card(id="mlx:text/x/Qwen3-4B@1", pin={"hf": "x/Qwen3-4B"}, jobs=TEXT, scripts=None, languages=None,
                material=frozenset(), runs_on="this-mac", installed=True, runs_here=True, source="installed", note="Qwen3 4B",
                open_licence=True, memory_gb=4, multilingual=True)


CHEAP, DEAR = _cloud("google", "fake-flash", 0.001), _cloud("anthropic", "fake-opus", 0.05)
A = dict(purposes=("catalogue",), jobs=("translate-transliterate-normalise", "correct"), materials=("handwriting",),
         languages=frozenset({"es"}), scripts=frozenset({"Latn"}), pages=20, mac_memory_gb=32)


def _steps(**kw):
    recipe = assemble(Answers(**{**A, **kw["answers"]}), kw.get("cards", []), cloud_text=kw.get("cloud_text", ()))
    return {s["job"]: s for s in recipe["steps"]}


@pytest.mark.parametrize("job", STEPS)
def test_with_the_cloud_allowed_and_a_key_the_cheapest_cloud_text_model_is_picked(job):
    steps = _steps(answers={"cloud_allowed": True, "cloud_keys": ("google", "anthropic")}, cloud_text=[DEAR, CHEAP])
    step = steps[job]
    assert step["model"] == {"cloud": "google", "model": "fake-flash"} and step["runs_on"] == "cloud:google"
    assert step["uses_cloud"] is True and "cheapest cloud text model" in " ".join(step["reasons"])


def test_a_provider_without_a_key_is_never_picked():
    steps = _steps(answers={"cloud_allowed": True, "cloud_keys": ("anthropic",)}, cloud_text=[DEAR, CHEAP])
    assert steps["describe-for-the-catalogue"]["model"] == {"cloud": "anthropic", "model": "fake-opus"}


@pytest.mark.parametrize("answers", [{"cloud_allowed": False, "cloud_keys": ("google",)}, {"cloud_allowed": True, "cloud_keys": ()}])
def test_without_the_cloud_allowed_or_a_key_nothing_is_picked(answers):
    steps = _steps(answers=answers, cloud_text=[CHEAP])
    for job in STEPS:
        assert "model" not in steps[job] and steps[job].get("gap"), job


@pytest.mark.parametrize("job", STEPS)
def test_a_good_enough_local_model_wins_over_the_cheapest_cloud_one(job):
    steps = _steps(answers={"cloud_allowed": True, "cloud_keys": ("google",)}, cards=[_local()], cloud_text=[CHEAP])
    assert steps[job]["runs_on"] == "this-mac" and steps[job]["model"] == {"hf": "x/Qwen3-4B"}


def test_an_unpriced_cloud_model_is_not_picked():
    unpriced = _cloud("google", "no-price", 0.0)
    steps = _steps(answers={"cloud_allowed": True, "cloud_keys": ("google",)}, cloud_text=[unpriced])
    assert steps["describe-for-the-catalogue"].get("gap")  # a cap cannot be held to a model with no listed price


@pytest.fixture
def plan_project(client, with_material, mac, app_db, monkeypatch):  # noqa: F811
    from fichero_server.recipes import discovery

    monkeypatch.setattr(discovery, "_cloud_text_cards", lambda: [CHEAP, DEAR])
    monkeypatch.setattr("fichero_server.recipes.derived._providers_with_keys", lambda: ["google", "anthropic"])
    answers = {"purposes": ["transcribe", "catalogue"], "jobs": ["translate-transliterate-normalise", "correct"], "languages": ["es"],
               "scripts": ["Latn"], "materials": ["handwriting"], "mac_memory_gb": 32, "cloud_allowed": True}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    return recipe


def test_the_plan_carries_the_picked_model_and_its_price_before_start(plan_project, client):
    plan = client.get("/api/recipes/project/start").json()
    runs = {s: r for r in plan["runs"] for s in r["steps"]}
    for job in ("translate-transliterate-normalise", "describe-for-the-catalogue"):
        assert job in runs, (job, [r["steps"] for r in plan["runs"]], [s["step"] for s in plan["skipped"]])
    priced = [row for row in plan["estimate"]["runs"] if row["where"].startswith("cloud")]
    assert any("describe-for-the-catalogue" in row["steps"] for row in priced), plan["estimate"]["runs"]


def test_a_persons_own_pick_is_kept(plan_project, client):
    step = next(c for c in client.get("/api/recipes/project/start").json()["step_choices"] if c["job"] == "describe-for-the-catalogue")
    other = next(c["card"] for c in step["candidates"] if c["card"] == DEAR.id)
    taken = client.post("/api/recipes/project/steps/use-candidate", json={"step": step["step"], "card": other})
    assert taken.status_code == 200, taken.text
    again = next(c for c in client.get("/api/recipes/project/start").json()["step_choices"] if c["job"] == "describe-for-the-catalogue")
    assert again["picked"] == DEAR.id and again["chosen_by"] != "setup"


def test_the_project_cap_still_refuses_a_call_over_it(monkeypatch):
    from fichero_server.llm import LLMConfig, spend

    monkeypatch.setattr(spend, "cap_usd", lambda library: 0.0001)
    monkeypatch.setattr(spend, "has_listed_price", lambda provider, model: True)
    monkeypatch.setattr(spend, "worst_case_usd", lambda config, tokens=None: 1.0)
    monkeypatch.setattr(spend, "booked_usd", lambda library: 0.0)

    async def call():
        async with spend.holding(LLMConfig(provider="google", model="fake-flash"), "/lib"):
            pass

    with pytest.raises(spend.CloudSpendRefusedError):
        asyncio.run(call())


def test_every_step_that_needs_a_model_lists_a_choice(client, with_material, mac, monkeypatch):  # noqa: F811
    """The audit (owner 2026-10-24: every step must be able to choose models): GET /api/recipes/candidates for each job that needs
    a model lists at least one, with a local text model present. A step that cannot choose is named in the failure."""
    from fichero_server.recipes import discovery
    from fichero_server.recipes.jobs import all_jobs

    monkeypatch.setattr(discovery, "local_text_cards", lambda seed=(): [_local()])
    empty = []
    for job in all_jobs():
        if not job.needs_a_model:
            continue
        r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es", "job": job.id, "mac_memory_gb": 32})
        assert r.status_code == 200, (job.id, r.text[:200])
        body = r.json()
        items = body.get("items", body.get("candidates", []))
        if not items:
            empty.append(job.id)
    # Named, as the owner asked: vision or audio steps with no model card of any kind yet (no text model can do them). Each is a
    # [GAP] in docs/contributor_manual/specs/source/models-chains-and-projects.md (`source.find.every-step-lists-models`).
    cannot = {"find-the-script", "refine-shapes", "find-signs", "find-a-tables-cells", "trace-a-drawing", "identify-signs",
              "transcribe-speech"}
    assert set(empty) == cannot, f"steps that cannot choose a model: {sorted(empty)} (expected {sorted(cannot)})"
