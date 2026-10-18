"""The three ruled money-and-place settings (#5769, ruled 2026-10-17): `source.onboard.spend-cap`,
`source.onboard.cluster-offer`, `source.onboard.copies-may-stay-on-cluster`.

WHY: setup had none of them, so Hugging Face training said it ran by itself with no cap, a person with ACENet access
was never offered it, and nothing said whether working copies may stay on the cluster.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import copies_may_stay, normalise, spend_cap
from fichero_server.recipes.train_offers import TRAIN_HERE_MIN_RAM_GB, train_offers, training_setting

SMALL = TRAIN_HERE_MIN_RAM_GB - 8
RECIPE = {"steps": [{"id": "read", "job": "read-a-line", "settings": {}}]}
COUNTS = {"pages": [], "unmarked": 0, "region_pages": 0, "scope_ids": ["root"], "teacher": "gemini-2.5-pro"}


def test_spend_cap_holds_paid_offers():
    """Default $0: every paid offer stays an offer. Hugging Face never runs by itself under a $0 cap, and its places say
    why they are held; a cap above $0 lets the setting stand."""
    assert spend_cap({}) == 0.0
    held = training_setting("huggingface", mac_memory_gb=SMALL, hf_configured=True, spend_cap=0.0)
    assert held["mode"] == "offered" and "$0" in held["why"]
    assert training_setting(None, mac_memory_gb=SMALL, hf_configured=True, spend_cap=0.0)["mode"] == "offered"
    assert training_setting("huggingface", mac_memory_gb=SMALL, hf_configured=True, spend_cap=20.0)["mode"] == "huggingface"
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=False, setting=held, spend_cap=0.0)
    hf = [t for w in offer["ways"] for t in w["targets"] if t["place"] == "huggingface-jobs"]
    assert hf and all("$0" in t["held"] for t in hf)
    assert all(t.get("held") is None for w in offer["ways"] for t in w["targets"] if t["place"] == "this-mac")
    with pytest.raises(ValueError, match="spend cap"):
        normalise({"purposes": ["transcribe"], "hf_spend_cap_usd": -5}, strict=True)


def test_cluster_offered_beside_hf():
    """Where a cluster is set up, every way offered on Hugging Face also offers the cluster, free, with the attended first
    run's steps named; no cluster set up, none is offered."""
    (offer,) = train_offers(RECIPE, COUNTS, stays_local=False, setting={"mode": "offered", "why": ""},
                            clusters=["ACENET Siku"])
    for way in offer["ways"]:
        if any(t["place"] == "huggingface-jobs" for t in way["targets"]):
            (cluster,) = [t for t in way["targets"] if t["place"] == "cluster"]
            assert cluster["name"] == "ACENET Siku" and cluster["first_run"] and cluster["starts"] is None
    (none,) = train_offers(RECIPE, COUNTS, stays_local=False, setting={"mode": "offered", "why": ""})
    assert not [t for w in none["ways"] for t in w["targets"] if t["place"] == "cluster"]
    (kept,) = train_offers(RECIPE, COUNTS, stays_local=True, setting={"mode": "offered", "why": ""},
                           clusters=["ACENET Siku"])
    assert not [t for w in kept["ways"] for t in w["targets"] if t["place"] == "cluster"]  # pages stay on this Mac


def test_copies_stay_default_follows_pages_may_leave():
    assert copies_may_stay({"cloud_allowed": True}) is True
    assert copies_may_stay({}) is False
    assert copies_may_stay({"cloud_allowed": True, "copies_may_stay_on_cluster": False}) is False
    with pytest.raises(ValueError, match="copies"):
        normalise({"purposes": ["transcribe"], "copies_may_stay_on_cluster": "maybe"}, strict=True)
