"""#5264: a hosted model's pages share a wider pool than local work.

Measured 2026-09-30 (M1, a 2 s stub model through the real runner, Transcribe preset): 48 pages took 28.2 s at
the one shared cap of 4 (and a remote in-flight cap of 6), and 11.8 s with a hosted pool of 12.
The runner's own work per page was ~70 ms; the caps were the time. Local inference is
serialized anyway (MLX job lock, Kraken inference lock), so local work keeps the cap of 4 that
bounds rendered pages in memory.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows import builder


@pytest.mark.parametrize(
    ("provider", "remote"),
    [("google", True), ("openai", True), ("anthropic", True), ("ollama", False), ("apple", False), ("mock", False)],
)
def test_hosted_providers_use_the_remote_pool(provider, remote):
    assert builder._is_remote_model(LLMConfig(provider=provider, model="m")) is remote


def test_no_model_is_local_work():
    assert builder._is_remote_model(None) is False


def test_the_hosted_pool_is_wider_than_the_local_one():
    assert builder.REMOTE_VISION_FAN_OUT_CONCURRENCY > builder.VISION_FAN_OUT_CONCURRENCY


def test_the_two_pools_are_separate(monkeypatch):
    """Filling the local pool must not stop a hosted page, and the reverse."""
    monkeypatch.setattr(builder, "VISION_FAN_OUT_CONCURRENCY", 1)
    monkeypatch.setattr(builder, "REMOTE_VISION_FAN_OUT_CONCURRENCY", 1)
    monkeypatch.setattr(builder, "_vision_fan_out_sem", None)
    monkeypatch.setattr(builder, "_remote_vision_sem", None)

    async def scenario():
        entered = []
        release = asyncio.Event()

        async def hold(remote: bool, name: str):
            async with builder.vision_slot(remote=remote):
                entered.append(name)
                await release.wait()

        local = asyncio.create_task(hold(False, "local"))
        hosted = asyncio.create_task(hold(True, "hosted"))
        await asyncio.sleep(0.05)
        both_in = sorted(entered)
        release.set()
        await asyncio.gather(local, hosted)
        return both_in

    assert asyncio.run(scenario()) == ["hosted", "local"]


def test_the_remote_cap_env_override(monkeypatch):
    monkeypatch.setenv("FICHERO_REMOTE_VISION_FAN_OUT_CONCURRENCY", "20")
    assert builder._vision_fan_out_concurrency(
        "FICHERO_REMOTE_VISION_FAN_OUT_CONCURRENCY", 12
    ) == 20
    monkeypatch.setenv("FICHERO_REMOTE_VISION_FAN_OUT_CONCURRENCY", "0")
    assert builder._vision_fan_out_concurrency(
        "FICHERO_REMOTE_VISION_FAN_OUT_CONCURRENCY", 12
    ) == 12
