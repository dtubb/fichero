"""Model comparison stops reporting unpriced models as free (2026-09-03).

`estimate_cost(...) or 0.0` at four call sites turned "the registry has no
price for this model" into "$0.0000" — and then RANKED on it, so the model
nobody has a price for won "cheapest".
"""

from __future__ import annotations

from fichero_server.workflows.model_comparison import (
    ComparisonResult,
    ModelResult,
    _cheapest_model_label,
    _total_cost,
    estimate_cost,
)


def _result(model: str, cost: float | None, *, error: str | None = None) -> ModelResult:
    return ModelResult(
        provider="openai",
        model=model,
        response="hi",
        latency_ms=100.0,
        cost_usd=cost,
        cost_priced=cost is not None,
        error=error,
    )


def test_estimate_cost_returns_none_for_an_unknown_model():
    assert estimate_cost("nobody-prices-this-x9", 100, 100) is None


def test_estimate_cost_is_zero_for_on_device_models():
    assert estimate_cost("apple", 100, 100) == 0.0


def test_model_result_defaults_to_unpriced_not_free():
    fresh = ModelResult(provider="p", model="m", response="", latency_ms=1.0)
    assert fresh.cost_usd is None
    assert fresh.cost_priced is False


def test_cheapest_ranks_only_priced_results():
    results = [_result("cheap", 0.001), _result("mystery", None)]
    assert _cheapest_model_label(results) == "openai/cheap"


def test_cheapest_is_none_when_nothing_priced():
    assert _cheapest_model_label([_result("mystery", None)]) is None
    assert _cheapest_model_label([]) is None


def test_total_cost_flags_a_partial_total():
    total, priced, unpriced = _total_cost([_result("a", 0.01), _result("mystery", None)])
    assert total == 0.01
    assert priced is False
    assert unpriced == ["mystery"]


def test_total_cost_is_none_when_nothing_priced():
    total, priced, unpriced = _total_cost([_result("mystery", None)])
    assert total is None
    assert priced is False


def test_errored_results_are_not_counted_as_unpriced():
    # A call that never happened has no missing price — it has no call.
    total, priced, unpriced = _total_cost(
        [_result("a", 0.02), _result("boom", None, error="timeout")]
    )
    assert (total, priced, unpriced) == (0.02, True, [])


def test_to_dict_publishes_the_priced_flags():
    result = _result("a", 0.02)
    assert result.to_dict()["cost_priced"] is True
    comparison = ComparisonResult(
        prompt="p",
        models_compared=["openai/a"],
        results=[result],
        total_cost_usd=None,
        total_cost_priced=False,
        unpriced_models=["mystery"],
    )
    payload = comparison.to_dict()
    assert payload["total_cost_usd"] is None
    assert payload["total_cost_priced"] is False
    assert payload["unpriced_models"] == ["mystery"]
