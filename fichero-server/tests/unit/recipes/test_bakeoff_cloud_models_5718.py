"""The person's cloud models are compared for reading, whichever provider rows they have (#5718,
`source.try.cloud-models-are-compared-for-reading-and-cleanup`; the clean-up half is waiting on a decision, see the
issue).

WHY: the bake-off took at most two readers of a kind, so with Claude, Gemini, OpenAI and OpenRouter set up two of
them silently never took part, and a person who wanted Gemini beside Claude could not say so. A reader the person
names takes part whatever the cap; every cloud reader shows what it would cost before anything runs; none reads
where the project keeps its pages here; none is the rules' choice.

No network and no key: the provider rows are kept in the test's app database, the price list is the local one.
"""
from __future__ import annotations

import pytest
from fichero_server.recipes import bakeoff
from fichero_server.recipes.assemble import Answers
from fichero_server.recipes.cards import all_seed_cards
from fichero_server.training import evaluation

PROVIDERS = {"anthropic": "claude-sonnet-4-5", "google": "gemini-2.5-pro", "openai": "gpt-4o",
             "openrouter": "qwen/qwen2.5-vl-72b-instruct"}


@pytest.fixture(autouse=True)
def apple_gone(monkeypatch):
    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: False)


@pytest.fixture
def four_clouds(app_db):
    from fichero_server.models import Model, Provider, ProviderType

    for ptype, model in PROVIDERS.items():
        row = app_db.save_provider(Provider(name=ptype.title(), provider_type=ProviderType(ptype)))
        app_db.save_model(Model(provider_id=row.id, name=model, model_id=model, capabilities=["vision"]))


def _answers(cloud_allowed: bool) -> Answers:
    return Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                   materials=("handwriting",), mac_memory_gb=16, cloud_allowed=cloud_allowed)


def _clouds(cloud_allowed: bool, named=None) -> dict:
    chosen = bakeoff.candidates(_answers(cloud_allowed), list(all_seed_cards()), volume=100, sample_pages=4,
                                named=named)
    return {c["card"]: c for c in chosen if not c["local"]}


def test_two_cloud_readers_take_part_unless_the_person_names_more(four_clouds):
    assert len(_clouds(True)) == bakeoff.PER_KIND
    every = _clouds(True)  # the two the cap chose
    offered = {c.id for c in bakeoff.cloud_readers()}  # the saved models and, per key, the frontier ones it serves (#6120)
    left_out = [c for c in offered if c not in every]
    assert len(offered) >= len(PROVIDERS) and len(left_out) == len(offered) - bakeoff.PER_KIND
    named = _clouds(True, named=left_out)
    assert set(left_out) <= set(named) and set(every) <= set(named) and len(named) == len(offered)


def test_every_cloud_reader_is_priced_before_anything_runs_and_scored_only_where_pages_may_leave(four_clouds):
    allowed = _clouds(True, named=[c.id for c in bakeoff.cloud_readers()])
    assert {c["provider"] for c in allowed.values()} == set(PROVIDERS)
    for c in allowed.values():
        assert c["not_scored"] is None
        # The price list's estimate, or "unknown" where it has none (said so, never a made-up price).
        assert c["cost_usd"]["basis"] in ("estimate", "unknown") and c["run_cost_usd"]["basis"] in ("estimate", "unknown")
    kept_here = _clouds(False, named=[c.id for c in bakeoff.cloud_readers()])
    assert {c["not_scored"] for c in kept_here.values()} == {"this project keeps its pages on this Mac: priced, not scored"}
    assert all(c["cost_usd"]["basis"] in ("estimate", "unknown") for c in kept_here.values())


def test_a_cloud_reader_is_offered_never_the_rules_choice(four_clouds):
    assert all(c.offered_only for c in bakeoff.cloud_readers())


def test_the_next_run_names_the_cost_of_the_readers_the_person_named(four_clouds, db, monkeypatch):
    monkeypatch.setattr(bakeoff, "ground_truth", lambda *a, **k: ([{"document_id": "p", "lines": 60}] * 2, []))
    ids = [c.id for c in bakeoff.cloud_readers()]
    one = bakeoff.next_run(db, _answers(True), list(all_seed_cards()), volume=100)
    all_four = bakeoff.next_run(db, _answers(True), list(all_seed_cards()), volume=100, named=ids)
    assert len([c for c in all_four["candidates"] if not c["local"]]) == len(ids)
    assert len([c for c in one["candidates"] if not c["local"]]) == bakeoff.PER_KIND
    assert all_four["run_cost_usd"] >= one["run_cost_usd"]
    assert all_four["sentence"].startswith("The comparison costs") and f"{len(ids)} cloud readers" in all_four["sentence"]
