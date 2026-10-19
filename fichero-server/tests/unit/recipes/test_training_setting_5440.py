"""`source.onboard.auto.train-offer-comes` (#5440, reworded 2026-10-17): training is an onboarding setting.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: nothing watched the corrected-line count and the
app never read `offered`, so the offer never came. It is now a setting the person makes in setup (`answers.training`: here,
huggingface, offered), defaulting by machine, never an alert; the Start plan shows each offer's setting and what it does.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.train_offers import TRAIN_HERE_MIN_RAM_GB, train_offers, training_setting
from tests.unit.recipes.test_bakeoff_readers import _corrected, _set_up, folder  # noqa: F401

BIG, SMALL = TRAIN_HERE_MIN_RAM_GB + 16, TRAIN_HERE_MIN_RAM_GB - 8


def test_the_default_follows_the_machine():
    """source.onboard.auto.train-offer-comes: "a Mac with enough memory ... trains here ... otherwise huggingface when a
    token is set up; else the offer stays on the Start plan"."""
    assert training_setting(None, mac_memory_gb=BIG, hf_configured=False)["mode"] == "here"
    assert training_setting(None, mac_memory_gb=BIG, hf_configured=True)["mode"] == "here"
    assert training_setting(None, mac_memory_gb=SMALL, hf_configured=True)["mode"] == "huggingface"
    assert training_setting(None, mac_memory_gb=SMALL, hf_configured=False)["mode"] == "offered"


def test_a_choice_wins_and_one_that_cannot_be_met_falls_back_saying_why():
    """source.onboard.auto.train-offer-comes: "A choice that cannot be met falls back to `offered` and says why"."""
    assert training_setting("offered", mac_memory_gb=BIG, hf_configured=True)["mode"] == "offered"
    assert training_setting("huggingface", mac_memory_gb=BIG, hf_configured=True)["mode"] == "huggingface"
    kept = training_setting("huggingface", mac_memory_gb=BIG, hf_configured=False)
    assert kept["mode"] == "offered" and "token" in kept["why"], kept
    small_here = training_setting("here", mac_memory_gb=SMALL, hf_configured=False)
    assert small_here["mode"] == "offered" and "memory" in small_here["why"], small_here


def test_every_offer_carries_the_setting_and_what_it_does():
    """source.onboard.auto.train-offer-comes: "each train offer carries its `setting` ... and what the setting does"."""
    recipe = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
    counts = {"pages": [], "unmarked": 0, "region_pages": 0, "scope_ids": [], "teacher": None}
    here = train_offers(recipe, counts, stays_local=True,
                        setting=training_setting(None, mac_memory_gb=BIG, hf_configured=False))[0]
    offered = train_offers(recipe, counts, stays_local=True,
                           setting=training_setting("offered", mac_memory_gb=BIG, hf_configured=False))[0]

    assert here["setting"]["mode"] == "here" and "by itself" in here["does"], here
    assert offered["setting"]["mode"] == "offered" and "offered" in offered["does"], offered


def test_the_start_plan_carries_the_setting_from_the_projects_answers(client, db, tmp_path, folder, monkeypatch, with_material):  # noqa: F811
    """source.onboard.auto.train-offer-comes: through the route, the saved `answers.training` is on the plan's offers."""
    _set_up(client)
    _corrected(db, tmp_path, "SM_NPQ_C01_001", folder)
    saved = client.get("/api/recipes/project").json()
    client.put("/api/recipes/project", json={"answers": {**saved["answers"], "training": "offered"},
                                             "recipe": saved["recipe"]})

    from fichero_server.recipes.train_offers import _offers_now

    # One corrected page is below the threshold: the plan shows no offer yet (#5804); the engine's own list has the setting.
    assert client.get("/api/recipes/project/start").json()["train_offers"] == []
    read = next(o for o in _offers_now(db) if o["job"] == "read-a-line")
    assert read["setting"]["mode"] == "offered", read


def test_a_project_that_keeps_its_pages_here_never_trains_on_huggingface():
    """source.onboard.auto.train-offer-comes: a project that keeps its pages on this Mac is never defaulted to, nor allowed,
    the Hugging Face setting: the ways that leave this Mac are refused (`train_offers._ways`), so the setting must not
    promise one."""
    default = training_setting(None, mac_memory_gb=SMALL, hf_configured=True, stays_local=True)
    assert default["mode"] == "offered" and "pages on this Mac" in default["why"], default
    chosen = training_setting("huggingface", mac_memory_gb=BIG, hf_configured=True, stays_local=True)
    assert chosen["mode"] == "offered" and "pages on this Mac" in chosen["why"], chosen
    assert training_setting("here", mac_memory_gb=BIG, hf_configured=True, stays_local=True)["mode"] == "here"
    assert training_setting(None, mac_memory_gb=SMALL, hf_configured=True, stays_local=False)["mode"] == "huggingface"
