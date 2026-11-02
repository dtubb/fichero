"""`designer.how.where`, `how.model-kind`, `how.what-matters`, `how.access-derived-and-confirmed`, `how.answers-pick-the-card` (#6052)."""
from __future__ import annotations

import pytest

from fichero_server.recipes import how
from fichero_server.recipes.answers import normalise

pytestmark = pytest.mark.recipe_designer


def test_a_place_the_app_does_not_allow_is_listed_greyed_with_its_reason_not_dropped():
    rows = {r["id"]: r for r in how.offered_places(["this-mac"])}
    assert list(rows) == ["this-mac", "another-mac", "cluster", "cloud"]
    assert rows["this-mac"]["allowed"] and rows["cloud"]["allowed"] is False and "cloud" in rows["cloud"]["reason"].lower()
    assert how.offered_places(["this-mac", "huggingface"])[2]["allowed"]  # a cluster tick opens with either of its places


def test_the_three_model_kinds_default_to_compare_and_large_is_greyed_only_with_no_cloud_and_a_small_mac():
    kinds = {k["id"]: k for k in how.model_kind_options(cloud_allowed=False, memory_gb=16)}
    assert list(kinds) == ["small", "large", "compare"] and how.DEFAULT_MODEL_KIND == "compare"
    assert kinds["large"]["allowed"] is False and kinds["large"]["reason"]
    assert how.model_kind_options(cloud_allowed=True, memory_gb=16)[1]["allowed"]
    assert how.model_kind_options(cloud_allowed=False, memory_gb=64)[1]["allowed"]


def test_privacy_is_prefilled_when_only_this_mac_is_ticked_and_never_writes_cloud_allowed():
    assert how.default_matters(["this-mac"]) == "privacy" and how.default_matters(["this-mac", "cloud"]) is None
    kept = normalise({"how": {"places": ["this-mac"], "matters": "privacy"}}, strict=True)
    assert "cloud_allowed" not in kept


def test_answers_are_kept_in_order_and_an_unknown_value_is_refused_in_words():
    assert normalise({"how": {"places": ["cloud", "this-mac"]}}, strict=True)["how"]["places"] == ["this-mac", "cloud"]
    with pytest.raises(ValueError, match="Matters is speed, cost, quality, privacy; not 'fun'"):
        normalise({"how": {"matters": "fun"}}, strict=True)
    with pytest.raises(ValueError, match="Work runs on"):
        normalise({"how": {"places": ["mars"]}}, strict=True)
