"""Out of provider credit holds the run once, names the provider, links its billing page and offers a local model (#7039).

Spec: docs/contributor_manual/specs/source/recipes-run.md `recipes-run.credit.out-of-credit-pauses-and-asks`. A fake provider
answers each provider's own out-of-credit shape; no network, no key.
"""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution.cancellation import clear_pause, pause_requested
from fichero_server.llm import failure, retry
from fichero_server.llm.failure import BILLING_URLS, credit_pause_failure
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.node_context import set_current_node

RUN = "run-7039"


class _Shape(Exception):
    def __init__(self, status, words):
        super().__init__(words)
        self.status_code = status


#: provider -> the answer a provider with no credit gives (status, words)
SHAPES = {
    "openrouter": (402, "402: Insufficient credits. Add more using https://openrouter.ai/credits"),
    "anthropic": (400, "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing."),
    "openai": (429, "You exceeded your current quota, please check your plan and billing details. insufficient_quota"),
    "google": (429, "RESOURCE_EXHAUSTED: Your prepayment credits are depleted. Please go to AI Studio to manage them."),
    "mistral": (402, "Payment required: insufficient balance on this account."),
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(cb, "_PROVIDER_SLOTS", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_RATE_LIMIT", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_CREDIT", {})
    monkeypatch.setattr(retry, "_LAST_CREDIT", {})
    monkeypatch.setattr(retry, "_DEAD", {})
    yield
    clear_pause(RUN)


def _call(provider, status, words, sends):
    async def one():
        sends.append(1)
        raise _Shape(status, words)

    async def go():
        set_current_node("read", run_id=RUN)
        return await cb.call_with_breaker(one, provider=provider, breaker=cb.ProviderCircuitBreaker(), max_retries=3,
                                          base_delay=0.001, max_delay=0.002)

    return asyncio.run(go())


@pytest.mark.parametrize("provider", sorted(SHAPES))
def test_each_providers_out_of_credit_answer_holds_the_run_once(provider):
    status, words = SHAPES[provider]
    sends: list[int] = []
    with pytest.raises(cb.ProviderCreditStopError):
        _call(provider, status, words, sends)
    assert len(sends) == 1, "no retry of a provider with no credit"
    assert pause_requested(RUN)
    held = retry.paused_for_credit([RUN])
    assert held["provider"] == provider and held["cause"] == "out-of-credit"
    with pytest.raises(cb.ProviderCreditStopError):  # the next page: the same one hold
        _call(provider, status, words, sends)
    assert len(retry._PAUSED_FOR_CREDIT[RUN]) == 1


@pytest.mark.parametrize("provider", sorted(SHAPES))
def test_the_hold_names_the_provider_links_its_billing_page_and_offers_a_local_model(provider):
    status, words = SHAPES[provider]
    with pytest.raises(cb.ProviderCreditStopError):
        _call(provider, status, words, [])
    held = failure.credit_pause_failure(retry.paused_for_credit([RUN]), step="Read")
    assert held.pauses and held.kind == "no-credit"
    assert BILLING_URLS[provider].startswith("https://") and BILLING_URLS[provider] in held.fix
    assert held.provider.lower().replace(" ", "") .startswith(provider[:4])
    kinds = [(a.kind, a.control) for a in held.actions]
    assert kinds[0] == ("resume", None)
    assert ("choose-model", None) in kinds and ("open-settings", failure.LOCAL_MODELS_CONTROL) in kinds


def test_a_provider_with_no_known_billing_page_names_none():
    held = credit_pause_failure({"provider": "somewhere", "cause": "out-of-credit", "detail": ""})
    assert "http" not in held.fix
