"""Run cost accounting: real tokens in, honest money out (2026-09-03).

The defect these tests exist to keep dead: `estimate_cost` returning None for a
model with no registry price, and every caller writing `or 0.0` — so a run on
an unpriceable model reported as free. Free and unknown must never render the
same.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.usage import (
    ModelCallUsage,
    aggregate_usage,
    price_call,
    provider_is_free,
    usage_from_message,
)


class _Message:
    """Stand-in for a langchain AIMessage."""

    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata


# ---------------------------------------------------------------------------
# usage_from_message — provider-reported tokens, or nothing
# ---------------------------------------------------------------------------


def test_usage_from_message_reads_langchain_standard_shape():
    usage = usage_from_message(
        _Message({"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})
    )
    assert usage == {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
        "cache_read_tokens": 0,
    }


def test_usage_from_message_reads_cache_read_detail():
    usage = usage_from_message(
        _Message(
            {
                "input_tokens": 1000,
                "output_tokens": 10,
                "total_tokens": 1010,
                "input_token_details": {"cache_read": 900, "cache_creation": 0},
            }
        )
    )
    assert usage["cache_read_tokens"] == 900


@pytest.mark.parametrize("payload", [None, {}, "not-a-dict"])
def test_usage_from_message_returns_none_when_provider_reported_nothing(payload):
    # None is the signal the caller must flag whatever it substitutes as an
    # estimate — it is never silently turned into zeros.
    assert usage_from_message(_Message(payload)) is None


def test_usage_from_message_survives_a_message_without_the_attribute():
    assert usage_from_message(object()) is None


# ---------------------------------------------------------------------------
# price_call — priced / free / unpriced
# ---------------------------------------------------------------------------


def test_priced_model_computes_cost_from_the_registry():
    call = price_call(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "kind": "chat",
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "total_tokens": 1_000_000,
        }
    )
    assert call.priced is True
    assert call.free is False
    assert call.cost_usd is not None and call.cost_usd > 0


def test_unknown_model_is_unpriced_not_free():
    call = price_call(
        {
            "provider": "openrouter",
            "model": "some-model-nobody-has-priced-x9",
            "input_tokens": 500,
            "output_tokens": 500,
        }
    )
    assert call.cost_usd is None
    assert call.priced is False
    assert call.unpriced is True
    # The whole point: NOT zero.
    assert call.cost_usd != 0.0


def test_on_device_provider_is_a_defensible_zero():
    call = price_call(
        {
            "provider": "apple",
            "model": "apple-intelligence",
            "input_tokens": 900,
            "output_tokens": 100,
        }
    )
    assert call.free is True
    assert call.priced is True
    assert call.cost_usd == 0.0


def test_mlx_provider_is_free_and_priced():
    # Daniel's check: an MLX/Apple run costs $0 and should SAY $0, not
    # "unpriced". `omlx` is the registry's MLX provider id.
    assert provider_is_free("omlx") is True
    call = price_call({"provider": "omlx", "model": "mlx-community/whatever", "input_tokens": 10})
    assert (call.priced, call.cost_usd) == (True, 0.0)


def test_unknown_provider_is_not_assumed_free():
    assert provider_is_free("some-startup-api") is False
    assert provider_is_free(None) is False
    assert provider_is_free("") is False


def test_cached_input_bills_at_the_cache_rate_not_the_full_rate():
    from fichero_server.llm.model_types import _resolve_entry

    entry = _resolve_entry("gpt-4o") or {}
    if entry.get("cache_read_input_token_cost") is None:
        pytest.skip("registry has no cache-read price for the probe model")

    base = {"provider": "openai", "model": "gpt-4o", "input_tokens": 10_000, "output_tokens": 0}
    full = price_call(base)
    cached = price_call({**base, "cache_read_tokens": 10_000})
    assert cached.cost_usd is not None and full.cost_usd is not None
    assert cached.cost_usd < full.cost_usd


def test_cache_read_larger_than_input_cannot_produce_a_negative_cost():
    call = price_call(
        {
            "provider": "openai",
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 0,
            "cache_read_tokens": 5_000,  # nonsense from a provider
        }
    )
    assert call.cost_usd is not None and call.cost_usd >= 0


def test_price_call_accepts_an_already_typed_call():
    typed = ModelCallUsage(provider="apple", model="apple", input_tokens=5)
    assert price_call(typed).cost_usd == 0.0


# ---------------------------------------------------------------------------
# aggregate_usage — the run total
# ---------------------------------------------------------------------------


def _priced(model="gpt-4o", **kw):
    return {"provider": "openai", "model": model, "input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100, **kw}


def test_aggregate_sums_tokens_and_costs():
    totals = aggregate_usage([_priced(), _priced()])
    assert totals.model_calls == 2
    assert totals.input_tokens == 2000
    assert totals.output_tokens == 200
    assert totals.total_tokens == 2200
    assert totals.priced is True
    assert totals.partially_priced is False
    one = price_call(_priced()).cost_usd
    assert one is not None
    assert totals.cost_usd == pytest.approx(one * 2)


def test_aggregate_of_nothing_is_empty_not_free():
    totals = aggregate_usage([])
    assert totals.model_calls == 0
    assert totals.cost_usd is None
    assert totals.priced is False
    assert totals.to_activity_metadata() == {}


def test_aggregate_with_one_unpriceable_call_is_a_floor():
    totals = aggregate_usage([_priced(), _priced(model="mystery-model-zz")])
    assert totals.partially_priced is True
    assert totals.priced is False
    assert totals.unpriced_models == ["mystery-model-zz"]
    # The total is the priced part — reported as a floor, never as the cost.
    assert totals.cost_usd == pytest.approx(price_call(_priced()).cost_usd)


def test_aggregate_with_nothing_priceable_reports_no_cost_at_all():
    totals = aggregate_usage([_priced(model="mystery-a"), _priced(model="mystery-b")])
    assert totals.cost_usd is None
    assert totals.priced is False
    assert totals.partially_priced is False
    assert set(totals.unpriced_models) == {"mystery-a", "mystery-b"}


def test_aggregate_flags_estimated_tokens():
    totals = aggregate_usage([_priced(), _priced(estimated=True)])
    assert totals.estimated_tokens is True


def test_all_free_run_is_priced_at_zero():
    totals = aggregate_usage(
        [{"provider": "apple", "model": "apple", "input_tokens": 10, "output_tokens": 2}]
    )
    assert totals.priced is True
    assert totals.cost_usd == 0.0
    assert totals.to_activity_metadata()["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# to_activity_metadata — the shape the Activity record carries
# ---------------------------------------------------------------------------


def test_activity_metadata_omits_cost_when_unpriced():
    meta = aggregate_usage([_priced(model="mystery-model-zz")]).to_activity_metadata()
    assert "cost_usd" not in meta  # absent reads as unknown; 0.0 would not
    assert meta["cost_priced"] is False
    assert meta["unpriced_models"] == "mystery-model-zz"


def test_activity_metadata_carries_cost_when_priced():
    meta = aggregate_usage([_priced()]).to_activity_metadata()
    assert meta["cost_usd"] > 0
    assert meta["cost_priced"] is True
    assert meta["model_calls"] == 1
    assert meta["total_tokens"] == 1100


def test_activity_metadata_marks_a_partial_total():
    meta = aggregate_usage([_priced(), _priced(model="mystery-model-zz")]).to_activity_metadata()
    assert meta["cost_partial"] is True


def test_activity_metadata_reports_cache_reads_only_when_there_were_some():
    assert "cache_read_tokens" not in aggregate_usage([_priced()]).to_activity_metadata()
    meta = aggregate_usage([_priced(cache_read_tokens=400)]).to_activity_metadata()
    assert meta["cache_read_tokens"] == 400


def test_activity_metadata_is_all_scalars_for_the_stringifying_client():
    meta = aggregate_usage([_priced(), _priced(model="mystery-model-zz", estimated=True)]).to_activity_metadata()
    assert all(isinstance(v, (int, float, str, bool)) for v in meta.values())


# ---------------------------------------------------------------------------
# The collector — what the workflow runner actually drains
# ---------------------------------------------------------------------------


def test_recorded_call_reaches_the_collector_with_cache_reads():
    from fichero_server.llm import _record_usage, collect_usage

    with collect_usage() as bucket:
        usage = usage_from_message(
            _Message(
                {
                    "input_tokens": 1000,
                    "output_tokens": 50,
                    "total_tokens": 1050,
                    "input_token_details": {"cache_read": 800},
                }
            )
        )
        assert usage is not None
        _record_usage(
            "openai",
            "gpt-4o",
            "chat",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
        )

    assert len(bucket) == 1
    assert bucket[0]["cache_read_tokens"] == 800
    assert bucket[0]["estimated"] is False

    totals = aggregate_usage(bucket)
    assert totals.model_calls == 1
    assert totals.cache_read_tokens == 800
    assert totals.priced is True


def test_estimated_call_is_flagged_all_the_way_through_the_collector():
    from fichero_server.llm import _record_usage, collect_usage

    with collect_usage() as bucket:
        _record_usage(
            "openrouter",
            "gpt-4o",
            "chat",
            input_tokens=100,
            output_tokens=10,
            total_tokens=110,
            estimated=True,
        )
    assert aggregate_usage(bucket).estimated_tokens is True


def test_calls_made_outside_a_collector_do_not_explode():
    from fichero_server.llm import _record_usage

    _record_usage("openai", "gpt-4o", "chat", input_tokens=1, output_tokens=1, total_tokens=2)


def test_explicit_bucket_is_the_one_that_fills():
    # The runner declares its bucket before collection starts so the
    # cancel/pause finishers can read it.
    from fichero_server.llm import _record_usage, begin_usage_collection, end_usage_collection

    mine: list = []
    bucket, token = begin_usage_collection(mine)
    assert bucket is mine
    try:
        _record_usage("openai", "gpt-4o", "chat", input_tokens=5, output_tokens=1, total_tokens=6)
    finally:
        end_usage_collection(token)
    assert len(mine) == 1


# ---------------------------------------------------------------------------
# Registry lookup — the gateway keys its models by the gateway
# ---------------------------------------------------------------------------


def test_gateway_model_prices_through_the_provider_prefix():
    # The registry row is "openrouter/qwen/qwen3.6-plus"; the engine records
    # the model as "qwen/qwen3.6-plus" with provider "openrouter". Replayed
    # against the real engine log, missing this priced 417 of 659 calls at
    # nothing (2026-09-03).
    call = price_call(
        {
            "provider": "openrouter",
            "model": "qwen/qwen3.6-plus",
            "input_tokens": 1000,
            "output_tokens": 100,
        }
    )
    assert call.priced is True
    assert call.cost_usd is not None and call.cost_usd > 0


def test_provider_prefix_is_not_doubled_when_the_model_already_carries_it():
    with_prefix = price_call(
        {"provider": "openrouter", "model": "openrouter/qwen/qwen3.6-plus", "input_tokens": 1000}
    )
    without = price_call(
        {"provider": "openrouter", "model": "qwen/qwen3.6-plus", "input_tokens": 1000}
    )
    assert with_prefix.cost_usd == without.cost_usd


def test_provider_prefix_does_not_invent_a_price_for_an_unknown_model():
    call = price_call(
        {"provider": "openrouter", "model": "nobody/prices-this-x9", "input_tokens": 10}
    )
    assert call.cost_usd is None
