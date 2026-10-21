"""A transcription sent to a provider records its usage like any other call, so the run account lists it
and says its cost is unknown, not nothing (#5591, `ai.where.remote-audio-priced`). Only the provider's
parser is a stub."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fichero_server import llm
from fichero_server.llm import LLMConfig, spend
from fichero_server.llm.usage import price_call
from fichero_server.observability import episodes


class _Parser:
    def __init__(self, **kwargs):
        pass

    def lazy_parse(self, blob):
        yield SimpleNamespace(page_content="  hello  ")


def test_a_remote_transcription_is_recorded_as_a_call_with_an_unknown_cost(monkeypatch, tmp_path):
    import langchain_community.document_loaders.parsers.audio as audio

    monkeypatch.setattr(audio, "OpenAIWhisperParser", _Parser)
    monkeypatch.setattr(llm, "_resolve_api_key", lambda config: "sk-test")
    # The call runs under a project that said yes to cloud models (the egress gate) and accepted this unpriced model
    # (the cap's fail-closed rule): the gates stay, the test meets them.
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n", encoding="utf-8")
    spend.set_accepted(str(tmp_path / "P.fichero"), "openai", "whisper-1", True)
    token = episodes.set_library(str(tmp_path / "P.fichero"))
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"x")

    try:
        with llm.collect_usage() as usage:
            text = asyncio.run(llm.audio_transcription(str(clip), "", LLMConfig(provider="openai", model="whisper-1")))
    finally:
        episodes._episode_library_path.reset(token)

    assert text == "hello"
    assert len(usage) == 1 and usage[0]["kind"] == "audio_transcription" and usage[0]["provider"] == "openai"
    priced = price_call(usage[0])
    assert priced.cost_usd is None and priced.free is False, "recorded, and unpriced: never free"
