"""A transcription sent to a provider records its usage like any other call, so the run account lists it
and says its cost is unknown, not nothing (#5591, `ai.where.remote-audio-priced`). Only the provider's
parser is a stub."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero_server import llm
from fichero_server.llm import LLMConfig
from fichero_server.llm.usage import price_call


class _Parser:
    def __init__(self, **kwargs):
        pass

    def lazy_parse(self, blob):
        yield SimpleNamespace(page_content="  hello  ")


def test_a_remote_transcription_is_recorded_as_a_call_with_an_unknown_cost(monkeypatch, tmp_path):
    import langchain_community.document_loaders.parsers.audio as audio

    monkeypatch.setattr(audio, "OpenAIWhisperParser", _Parser)
    monkeypatch.setattr(llm, "_resolve_api_key", lambda config: "sk-test")
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"x")

    with llm.collect_usage() as usage:
        text = asyncio.run(llm.audio_transcription(str(clip), "", LLMConfig(provider="openai", model="whisper-1")))

    assert text == "hello"
    assert len(usage) == 1 and usage[0]["kind"] == "audio_transcription" and usage[0]["provider"] == "openai"
    priced = price_call(usage[0])
    assert priced.cost_usd is None and priced.free is False, "recorded, and unpriced: never free"
