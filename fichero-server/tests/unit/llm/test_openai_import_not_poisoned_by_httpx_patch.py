"""Importing the openai SDK while `httpx.AsyncClient` is monkeypatched must
not poison the rest of the process.

Root cause of the original gate failure ("Invalid `http_client` argument;
Expected an instance of `httpx.AsyncClient` but got
langchain_openai.chat_models._client_utils._AsyncHttpxClientWrapper"):

`openai._base_client` defines `DefaultAsyncHttpxClient(httpx.AsyncClient)` at
IMPORT time. If openai's first import happens while a test has
`httpx.AsyncClient` patched, the FAKE class gets baked into openai's
base-class hierarchy and every later default-client ChatOpenAI fails
`isinstance` for the rest of the session.

PREMISE CHANGE (2026-09-04, de2fe6c07): the original fix made
`fichero_server.llm` import openai eagerly at module import. That put httpx
back on the ENGINE BOOT PATH, which import profiling had just paid to clear —
so the eager import moved to tests/conftest.py, where it runs before any test
can patch. The protected party was always the pytest session (production
never monkeypatches httpx); the boot path stays lean and the suite stays
unpoisoned. This file now pins BOTH halves of that contract:

1. the poisoning sequence is survivable when openai is imported first, as
   conftest guarantees for the suite (subprocess, pristine interpreter);
2. `fichero_server.llm` does NOT drag openai/httpx in at module import — the
   boot-path guarantee that caused the premise change;
3. tests/conftest.py actually carries the eager import, so half 1's
   precondition is the suite's reality rather than this file's fiction.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = """
import asyncio
from unittest.mock import patch

import openai  # what tests/conftest.py does for the suite: bind real bases first

import fichero_server.llm as llm


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
    # The poisoning gesture: langchain_openai's first use happens while
    # httpx.AsyncClient is patched (exactly what test_llm_http_client_cache does).
    with patch("httpx.AsyncClient", _FakeAsyncClient):
        llm.get_langchain_model(cfg)

    # Patch reverted. A default-client openai-provider model must construct.
    cfg2 = llm.LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")
    llm.get_langchain_model(cfg2)
    print("CONSTRUCTED_OK")


asyncio.run(main())
"""

_BOOT_SCRIPT = """
import sys

import fichero_server.llm  # noqa: F401

leaked = sorted(m for m in ("openai", "langchain_openai") if m in sys.modules)
print("LEAKED:" + ",".join(leaked))
"""


def test_default_client_survives_httpx_patch_after_conftest_style_import():
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


def test_llm_module_import_keeps_openai_off_the_boot_path():
    # The premise the 2026-09-04 change bought: importing fichero_server.llm
    # must not pull openai/langchain_openai (and with them httpx) into the
    # process. If this fails, engine boot just got slower AND the conftest
    # eager-import stopped being the thing that binds openai's bases first.
    src_dir = str(Path(__file__).resolve().parents[3] / "src")
    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PYTHONPATH": src_dir, "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "LEAKED:\n" in proc.stdout or proc.stdout.strip() == "LEAKED:", proc.stdout


def test_conftest_carries_the_eager_openai_import():
    # Half 1's precondition must be the suite's reality: conftest imports
    # openai before any test runs. Scan code, not comments.
    conftest = (Path(__file__).resolve().parents[2] / "conftest.py").read_text()
    code_lines = [
        ln
        for ln in conftest.splitlines()
        if not ln.strip().startswith("#") and "import openai" in ln
    ]
    assert code_lines, (
        "tests/conftest.py no longer imports openai eagerly — the httpx "
        "poisoning protection (de2fe6c07 premise) has lost its anchor"
    )
