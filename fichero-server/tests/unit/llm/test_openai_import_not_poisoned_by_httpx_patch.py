"""Importing the openai SDK while `httpx.AsyncClient` is monkeypatched must
not poison the rest of the process.

Root cause of last night's gate failure ("Stage 1 chunk N failed: Invalid
`http_client` argument; Expected an instance of `httpx.AsyncClient` but got
langchain_openai.chat_models._client_utils._AsyncHttpxClientWrapper"):

`openai._base_client` defines `DefaultAsyncHttpxClient(httpx.AsyncClient)` at
IMPORT time. `fichero_server.llm._build_langchain_model` imported
langchain_openai (and, transitively, openai) lazily — so the first test to
build a LangChain model while patching `httpx.AsyncClient` (e.g.
test_llm_http_client_cache) permanently baked the FAKE class into openai's
base-class hierarchy. Every later ChatOpenAI that used the default async
client then failed `isinstance(wrapper, httpx.AsyncClient)` for the rest of
the pytest session — the wrapper's MRO pointed at the fake, and the
extract_all Stage 1 chunks in test_catalogue_full_pipeline died on it.

Fix: `fichero_server.llm` imports openai EAGERLY at module import, before any
caller can patch. This test proves it in a pristine interpreter, replaying
the exact gate sequence: patch → build openrouter model → unpatch → build a
default-client openai model. Without the eager import, step 4 raises the
TypeError above (reproduced 2026-09-03).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = """
import asyncio
from unittest.mock import patch

import fichero_server.llm as llm  # must eagerly bind openai's real httpx bases


class _FakeAsyncClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


async def main():
    cfg = llm.LLMConfig(
        provider="openrouter",
        model="gpt-4o-mini",
        api_key="key-1",
        api_base="https://openrouter.ai/api/v1",
    )
    # The poisoning gesture: first langchain_openai/openai usage happens while
    # httpx.AsyncClient is patched (exactly what test_llm_http_client_cache does).
    with patch("httpx.AsyncClient", _FakeAsyncClient):
        llm.get_langchain_model(cfg)

    # Patch reverted. A default-client openai-provider model must construct.
    cfg2 = llm.LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")
    llm.get_langchain_model(cfg2)
    print("CONSTRUCTED_OK")


asyncio.run(main())
"""


def test_default_client_survives_httpx_patch_during_first_langchain_import():
    src_dir = str(Path(__file__).resolve().parents[3] / "src")
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PYTHONPATH": src_dir, "PATH": "/usr/bin:/bin"},
    )
    assert "Invalid `http_client` argument" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr
    assert "CONSTRUCTED_OK" in proc.stdout
