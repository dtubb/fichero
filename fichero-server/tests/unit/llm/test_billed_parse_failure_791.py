"""## 791 LOW 1 (#5987): a reply the provider billed but that would not parse is spend the held cost is booked at."""
from __future__ import annotations

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig

CLOUD = LLMConfig(provider="openai", model="gpt-x")


def test_a_reply_that_would_not_parse_is_still_billed_and_so_counted(monkeypatch, tmp_path):
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

    # The call runs under a project that said yes to cloud models (the egress gate) with a listed price (the cap's fail-closed rule).
    import contextlib

    from fichero_server.observability import episodes
    from fichero_server.llm import usage

    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n", encoding="utf-8")
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})

    @contextlib.asynccontextmanager
    async def lane(config, *, library=None, subject=None):  # the job lane needs a library database
        yield

    monkeypatch.setattr(llm, "_model_call_slot", lane)
    token = episodes.set_library(str(tmp_path / "P.fichero"))
    monkeypatch.setattr(llm, "get_langchain_model", lambda config: Model())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    try:
        with llm.collect_usage() as bucket:
            with pytest.raises(RuntimeError, match="parse failed"):
                asyncio.run(llm.chat_structured("hi", Schema, CLOUD))
    finally:
        episodes._episode_library_path.reset(token)
    assert bucket and bucket[0]["input_tokens"] == 100 and bucket[0]["output_tokens"] == 7

