"""`ai.cloud.plan-knows-a-dead-key` (#6097): the Start plan skips a step whose provider is out of credit or has a refused key,
with that cause's words and the fix `choose-model`; a rate limit only ranks down; a call that answers clears the mark."""
from __future__ import annotations

import time

import pytest

from fichero_server.llm import retry
from fichero_server.recipes.start import dead_provider, plan_start
from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe


@pytest.fixture(autouse=True)
def _clean():
    retry._DEAD.clear()
    yield
    retry._DEAD.clear()


def _mark(provider: str, cause: str, *, ago: float = 5.0) -> None:
    retry._DEAD[provider] = (time.monotonic() - ago + retry.DEAD_FOR_SECONDS, cause)


def test_no_credit_skips_the_step_with_the_words_and_choose_model():
    _mark("openai", "quota")
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)
    skipped = {s["step"]: s for s in plan["skipped"]}
    assert "OpenAI" in skipped["correct"]["why"] or "openai" in skipped["correct"]["why"].lower(), skipped
    assert skipped["correct"]["fix"] == "choose-model"
    assert all("correct" not in run["steps"] for run in plan["runs"])


def test_a_refused_key_is_the_same_and_says_the_key():
    _mark("openai", "key")
    why = dead_provider(CLOUD_CORRECT)
    assert why and "key" in why.lower()


def test_a_rate_limit_ranks_down_not_out():
    _mark("openai", "rate-limit")
    assert dead_provider(CLOUD_CORRECT) is None
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)
    assert not [s for s in plan["skipped"] if s["step"] == "correct" and s["fix"] == "choose-model"]


def test_the_mark_outlives_its_thirty_seconds_for_a_plan_and_then_goes():
    _mark("openai", "quota", ago=120.0)  # long past the 30 s a call is failed fast for
    assert dead_provider(CLOUD_CORRECT) is not None
    _mark("openai", "quota", ago=retry.PLAN_MEMORY_SECONDS + 100)
    assert dead_provider(CLOUD_CORRECT) is None


def test_a_local_step_and_an_unmarked_provider_are_untouched():
    _mark("anthropic", "quota")
    assert dead_provider(CLOUD_CORRECT) is None
    assert dead_provider(LINES) is None


def test_a_call_that_answers_clears_the_mark():
    import asyncio

    from fichero_server.llm import LLMConfig

    _mark("openai", "quota")

    async def ok():
        return 1

    async def go():
        retry._DEAD["openai"] = (0.0, "quota")  # expired for the call itself, still remembered for the plan
        return await retry.resilient(ok, LLMConfig(provider="openai", model="m", api_key="k"))

    assert asyncio.run(go()) == 1
    assert "openai" not in retry._DEAD
