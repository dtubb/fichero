"""Out of credit, or a credit limit, pauses the run and asks; a rate limit still resumes by itself (#6675).

Spec: docs/contributor_manual/specs/source/recipes-run.md `recipes-run.credit.out-of-credit-pauses-and-asks`. A fake provider
answers 402; no network, no key.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.execution.cancellation import WorkflowPaused, clear_pause, pause_requested
from fichero_server.llm import LLMConfig, retry
from fichero_server.llm.failure import credit_pause_failure
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.node_context import set_current_node
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision
from tests.unit.workflows.test_in_flight_budget_6671 import _InFlight

RUN = "run-6675"


class _NoCredit(Exception):
    status_code = 402

    def __init__(self, words="402: Insufficient credits. Add more using https://openrouter.ai/credits"):
        super().__init__(words)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(cb, "_PROVIDER_SLOTS", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_RATE_LIMIT", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_CREDIT", {})
    monkeypatch.setattr(retry, "_DEAD", {})
    yield
    clear_pause(RUN)


def _call(exc_factory, sends=None):
    async def one():
        if sends is not None:
            sends.append(1)
        raise exc_factory()

    async def go():
        set_current_node("read", run_id=RUN)
        return await cb.call_with_breaker(one, provider="openrouter", breaker=cb.ProviderCircuitBreaker(), max_retries=1,
                                          base_delay=0.001, max_delay=0.002)

    return asyncio.run(go())


def test_a_402_credit_answer_pauses_the_run_and_raises_the_one_prompt():
    with pytest.raises(cb.ProviderCreditStopError):
        _call(_NoCredit)
    assert pause_requested(RUN)
    paused = retry.paused_for_credit([RUN])
    assert paused["provider"] == "openrouter" and paused["cause"] == "out-of-credit"
    assert "Insufficient credits" in paused["detail"]
    with pytest.raises(cb.ProviderCreditStopError):  # a second page: the same one prompt, not another
        _call(_NoCredit)
    assert len(retry._PAUSED_FOR_CREDIT[RUN]) == 1


def test_a_credit_limit_answer_is_named_as_a_limit():
    with pytest.raises(cb.ProviderCreditStopError):
        _call(lambda: _NoCredit("402: Key limit exceeded (monthly limit)."))
    assert retry.paused_for_credit([RUN])["cause"] == "credit-limit"


@pytest.mark.asyncio
async def test_the_next_page_makes_no_call_to_the_provider_and_continue_resumes_it():
    config = LLMConfig(provider="openrouter", model="m", api_key="k")
    sends: list[int] = []

    async def broke():
        sends.append(1)
        raise _NoCredit()

    set_current_node("read", run_id=RUN)
    with pytest.raises(cb.ProviderCreditStopError):
        await retry.resilient(broke, config)
    with pytest.raises(cb.ProviderCreditStopError):
        await retry.resilient(broke, config)
    assert len(sends) == 1, "no further call to a provider that has no credit"

    clear_pause(RUN)
    retry.forget_credit_pause(RUN)  # Continue
    assert retry.paused_for_credit([RUN]) is None

    async def answers():
        sends.append(1)
        return "ok"

    assert await retry.resilient(answers, config) == "ok", "after Continue the provider is asked again"
    assert len(sends) == 2


def test_a_rate_limit_still_pauses_by_itself_and_raises_no_credit_prompt():
    with pytest.raises(cb.ProviderInFlightBudgetError):
        _call(_InFlight)
    assert retry.paused_for_rate_limit([RUN])["provider"] == "openrouter"
    assert retry.paused_for_credit([RUN]) is None


def test_the_paused_failure_names_provider_cause_and_offers_continue():
    failure = credit_pause_failure({"provider": "openrouter", "cause": "credit-limit", "detail": "Credit limit exceeded"},
                                   step="Read the page")
    assert failure.kind == "no-credit" and failure.provider == "OpenRouter" and failure.step == "Read the page"
    assert "credit limit" in failure.words and "paused" in failure.words
    assert failure.detail == "Credit limit exceeded"
    assert [a.kind for a in failure.actions][:2] == ["resume", "open-settings"]


@pytest.mark.asyncio
async def test_a_page_cut_by_no_credit_pauses_the_run_and_has_no_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cb, "compute_backoff_delay", lambda *a, **k: 0.0)
    set_current_node("read", run_id=RUN)
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG stub")
    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
        patch("fichero_server.workflows.tools.vision_base.file_to_data_uri", return_value="data:image/png;base64,AAAA"),
        patch("fichero_server.llm.vision", new=AsyncMock(side_effect=_NoCredit())),
        pytest.raises(WorkflowPaused),
    ):
        await process_vision(
            files=[str(image)], documents=[], prompt="Describe.",
            llm_config=LLMConfig(provider="openrouter", model="m", api_key="k"), library_path="", task_id=None,
            tool_config=VisionToolConfig(artifact_type="transcription", update_page_content=False,
                                         trigger_embedding=False, supports_apple_vision=True),
            vision_mode="llm")
    assert pause_requested(RUN)
