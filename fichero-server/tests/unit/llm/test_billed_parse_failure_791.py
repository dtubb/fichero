"""## 791 LOW 1 (#5987): a reply the provider billed but that would not parse is spend the held cost is booked at."""
from __future__ import annotations

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig

CLOUD = LLMConfig(provider="openai", model="gpt-x")


def test_a_reply_that_would_not_parse_is_still_billed_and_so_counted(monkeypatch):
    """## 791 LOW 1: the provider answered and bills it; the structured path used to raise before it recorded the usage."""
    import asyncio

    from langchain_core.messages import AIMessage
    from pydantic import BaseModel

    class Schema(BaseModel):
        x: int = 0

    class Model:
        profile = None

        def with_structured_output(self, schema, **kwargs):
            return self

        async def ainvoke(self, messages):
            raw = AIMessage(content="not json", usage_metadata={"input_tokens": 100, "output_tokens": 7, "total_tokens": 107})
            return {"raw": raw, "parsed": None, "parsing_error": ValueError("bad")}

    async def ready(config):
        return None

    monkeypatch.setattr(llm, "get_langchain_model", lambda config: Model())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    with llm.collect_usage() as bucket:
        with pytest.raises(RuntimeError, match="parse failed"):
            asyncio.run(llm.chat_structured("hi", Schema, CLOUD))
    assert bucket and bucket[0]["input_tokens"] == 100 and bucket[0]["output_tokens"] == 7

