"""Claims-only catalogue narrative must never send an empty user prompt.

Found live (Marshall sample, Apple-only chain run, 2026-09-03): the 1–6
Catalogue chain hands '6 · Catalogue' no transcript text — only the KG rows
stages 2–4 wrote. `_generate_resumen("")` then called the model with an EMPTY
user prompt, carrying the entity context only in the system instructions.
Apple's fm-bridge rejects that outright ("Missing or empty 'prompt' field"),
so every Apple-only run of the chain (or the standalone stage 6) completed as
a narrative-less "partial success". The claims context is the source material
on this path and must ride in the user prompt.
"""

from __future__ import annotations

import asyncio


from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import catalogue as catalogue_module


def test_claims_only_resumen_puts_the_claims_in_the_user_prompt(monkeypatch):
    seen: dict[str, str] = {}

    async def fake_chat(prompt, *, config, system, **kwargs):
        seen["prompt"] = prompt
        seen["system"] = system
        return "A grounded narrative."

    monkeypatch.setattr(catalogue_module, "chat_with_fallback", fake_chat)

    paragraph, chunk_summaries = asyncio.run(
        catalogue_module._generate_resumen(
            "",
            "English",
            LLMConfig(provider="apple", model="apple-intelligence"),
            claim_context="People: N.C. Marshall\nDates: 1923",
        )
    )

    assert paragraph == "A grounded narrative."
    assert chunk_summaries == []
    assert seen["prompt"].strip(), "empty user prompt reached the model"
    assert "N.C. Marshall" in seen["prompt"], (
        "claims-only path must carry the claim context as source material "
        "in the user prompt (Apple rejects an empty prompt)"
    )


def test_claims_only_keywords_puts_the_claims_in_the_user_prompt(monkeypatch):
    """Same defect class as the resumen fix, found by the Sonnet run:
    Anthropic returns 400 'at least one message is required' when the
    keywords call sends an empty user prompt."""
    seen: dict[str, str] = {}

    async def fake_chat(prompt, *, config, system, **kwargs):
        seen["prompt"] = prompt
        return "diaries; Panama"

    monkeypatch.setattr(catalogue_module, "chat_with_fallback", fake_chat)

    keywords = asyncio.run(
        catalogue_module._generate_keywords(
            "",
            "English",
            LLMConfig(provider="anthropic", model="claude-sonnet-5"),
            claim_context="People: N.C. Marshall\nDates: 1923",
        )
    )
    assert keywords == "diaries; Panama"
    assert seen["prompt"].strip(), "empty user prompt reached the model"
    assert "N.C. Marshall" in seen["prompt"]


def test_nothing_at_all_still_returns_empty_without_calling_the_model(
    monkeypatch,
):
    async def exploding(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("model called with no material at all")

    monkeypatch.setattr(catalogue_module, "chat_with_fallback", exploding)

    paragraph, chunk_summaries = asyncio.run(
        catalogue_module._generate_resumen(
            "",
            "English",
            LLMConfig(provider="apple", model="apple-intelligence"),
            claim_context="",
        )
    )
    assert paragraph == ""
    assert chunk_summaries == []
