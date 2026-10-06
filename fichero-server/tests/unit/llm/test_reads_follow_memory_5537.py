"""How many reads one local model server is asked at once follows the model's need and the Mac's
memory, and a server that dies mid-read says so (#5537).

WHY: on the 8 GB Air (2026-10-06) a 3B vision model loaded fine, then four pages were read at once
by the one local MLX server (a line reader asks four line batches at once per page, too), with
Kraken finding lines beside it; the server died mid-read and every page failed 'An error occurred
during streaming' with no cause, and the server's stderr was kept nowhere. Spec:
compute/jobs-and-fine-tuning.md, 'Models in memory'.

Nothing reads this Mac's memory: physical memory is injected. The dying server is a real process.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as routes
from fichero_server.llm import LLMConfig, kraken_runtime, local_inference
from fichero_server.llm.local_inference import (
    LocalModelServerStoppedError,
    ManagedLocalInferenceProcess,
    LocalProviderProfile,
    local_reads_at_once,
)
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
from fichero_server.workflows import page_retry

GB = 1024**3
THREE_B = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]
EIGHT_B = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]


def _mac(gb: int):
    return lambda: gb * GB


# --- the rule ----------------------------------------------------------------------------------------


def test_a_3b_on_an_8_gb_mac_reads_one_page_at_a_time():
    assert local_reads_at_once(THREE_B, physical_bytes=_mac(8)) == 1


def test_a_16_gb_mac_reads_more_up_to_the_ceiling():
    assert local_reads_at_once(THREE_B, physical_bytes=_mac(16)) == local_inference.LOCAL_READS_CEILING == 4
    assert local_reads_at_once(EIGHT_B, physical_bytes=_mac(16)) == 2
    assert local_reads_at_once(THREE_B, physical_bytes=_mac(64)) == 4


def test_an_unknown_mac_reads_one_at_a_time():
    assert local_reads_at_once(THREE_B, physical_bytes=lambda: None) == 1


# --- through the real call path ---------------------------------------------------------------------


class _CountingModel:
    """A model server stand-in that counts how many requests it is asked at once."""

    def __init__(self):
        self.now = 0
        self.peak = 0
        self.calls = 0

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage

        self.now += 1
        self.calls += 1
        self.peak = max(self.peak, self.now)
        try:
            await asyncio.sleep(0.02)
        finally:
            self.now -= 1
        images = sum(1 for part in messages[0].content if part.get("type") == "image_url")
        return AIMessage(content=json.dumps([f"line {i}" for i in range(images)]))


@pytest.fixture
def served(monkeypatch):
    model = _CountingModel()

    async def ready(config, capability="text"):
        return None

    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    monkeypatch.setattr(llm, "get_langchain_model", lambda config, **_: model)
    with llm._LLM_RESULT_CACHE_LOCK:
        llm._LLM_RESULT_CACHE.clear()
    return model


async def _eight_pages(provider: str, model: str):
    await asyncio.gather(*(
        llm.vision(images=[f"data:image/png;base64,page{i}"], prompt="read", config=LLMConfig(provider=provider, model=model))
        for i in range(8)
    ))


@pytest.mark.asyncio
async def test_on_an_8_gb_mac_a_3b_is_asked_one_page_at_a_time(served, monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    await _eight_pages("omlx", "Qwen2.5-VL-3B")
    assert served.calls == 8 and served.peak == 1


@pytest.mark.asyncio
async def test_on_a_16_gb_mac_the_3b_reads_four_at_once(served, monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(16))
    await _eight_pages("omlx", "Qwen2.5-VL-3B")
    assert served.peak == 4


@pytest.mark.asyncio
async def test_a_cloud_model_keeps_its_parallelism(served, monkeypatch):
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    await _eight_pages("openai", "gpt-4o")
    assert served.peak == 8


@pytest.mark.asyncio
async def test_the_line_reader_asks_one_batch_at_a_time_on_an_8_gb_mac(served, monkeypatch, tmp_path):
    """A line reader asks four batches of a page at once, and four pages run at once: on the Air
    that was up to sixteen requests to one 3B server. Bounded at the call, whoever asks."""
    from PIL import Image

    from fichero_server.llm import line_reader
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    page = tmp_path / "page.png"
    Image.effect_noise((64, 32 * 8), 64).convert("RGB").save(page)
    n = 32
    boxes = [OCRGeometryBox(text="", bbox=[0, i / n, 1, 1 / n], level=OCRGeometryLevel.LINE,
                            provider="kraken", model="blla", source="kraken-blla",
                            metadata={"polygon_px": [[0, i * 8], [64, i * 8], [64, i * 8 + 8], [0, i * 8 + 8]]})
             for i in range(n)]
    lines = OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes, source="kraken-blla")
    config = LLMConfig(provider="omlx", model="Qwen2.5-VL-3B")

    results = await asyncio.gather(*(line_reader.read_lines(str(page), lines, config) for _ in range(4)))

    assert served.calls >= 4 * (n // line_reader.LINES_PER_CALL)
    assert served.peak == 1
    assert all(r.text for r in results)


# --- a server that dies mid-read -------------------------------------------------------------------

_DYING_SERVER = r'''
import http.server, os, sys
port = int(sys.argv[sys.argv.index("--port") + 1])
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "4096")
        self.end_headers()
        self.wfile.write(b'{"id": "chatcmpl-1", "choices": [')
        self.wfile.flush()
        print("[METAL] Command buffer execution failed: Insufficient Memory "
              "(00000008:kIOGPUCommandBufferCallbackErrorOutOfMemory)", file=sys.stderr, flush=True)
        os._exit(134)
    def log_message(self, *args):
        pass
print("server ready", file=sys.stderr, flush=True)
http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
'''


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_a_server_that_dies_mid_read_names_it_logs_its_output_and_the_page_is_read_again(
    tmp_path, monkeypatch, caplog
):
    script = tmp_path / "dying_server.py"
    script.write_text(_DYING_SERVER)
    port = _free_port()
    profile = LocalProviderProfile(
        id="local-omlx", name="Local oMLX", provider_type="omlx", model_id="Qwen2.5-VL-3B",
        base_url=f"http://127.0.0.1:{port}/v1", local_only=True, allows_paid_fallbacks=False,
        managed_by_app=True, healthcheck_path="/health", python_executable=sys.executable,
        command=[str(script)],
    )
    monkeypatch.setenv("FICHERO_SKIP_MLX_MEMORY_GUARD", "1")
    process = ManagedLocalInferenceProcess(profile)
    monkeypatch.setitem(routes._MANAGERS, "dying", SimpleNamespace(profile=profile, process=process))

    async def ready(config, capability="text"):
        return None

    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    # The client retries a refused connection ten times with backoff (~50 s); not what is tested.
    import openai._base_client as openai_client

    monkeypatch.setattr(openai_client, "INITIAL_RETRY_DELAY", 0.01)
    monkeypatch.setattr(openai_client, "MAX_RETRY_DELAY", 0.02)
    await process.start()
    try:
        deadline = time.monotonic() + 10
        while "server ready" not in (process.output_tail() or ""):
            assert time.monotonic() < deadline, "the fake server did not start"
            await asyncio.sleep(0.05)
        caplog.set_level(logging.ERROR, logger="fichero_server.llm.local_inference")
        config = LLMConfig(provider="omlx", model="Qwen2.5-VL-3B", api_base=f"http://127.0.0.1:{port}/v1")
        with pytest.raises(LocalModelServerStoppedError) as raised:
            await llm.vision(images=["data:image/png;base64,AAAA"], prompt="read", config=config)
    finally:
        await process.stop()

    cause = str(raised.value)
    assert cause.startswith("The local model server stopped while reading: ")
    assert "Insufficient Memory" in cause
    assert "error occurred during streaming" not in cause.lower()
    assert page_retry.is_passing_cause(cause)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "exited" in logged and "Insufficient Memory" in logged


@pytest.mark.asyncio
async def test_a_failed_request_whose_server_is_still_up_keeps_its_own_error(served, monkeypatch):
    import httpx
    import openai

    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    monkeypatch.setattr(llm, "_SERVER_EXIT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(routes, "engine_started_servers", lambda: [])
    error = openai.APIError("An error occurred during streaming", httpx.Request("POST", "http://127.0.0.1/"), body=None)

    async def fails(messages):
        raise error

    monkeypatch.setattr(served, "ainvoke", fails)
    with pytest.raises(openai.APIError):
        await llm.vision(images=["data:image/png;base64,x"], prompt="read",
                         config=LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))


def test_a_server_gone_while_its_handle_never_heard_is_not_running(caplog):
    """The run whose event loop started the server has ended: nothing sets its return code. The
    pid says it is gone, and its last output goes to the log."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()

    class StaleHandle:
        returncode = None
        pid = child.pid

    process = ManagedLocalInferenceProcess(LocalProviderProfile(
        id="local-omlx", name="Local oMLX", provider_type="omlx", model_id="Qwen2.5-VL-3B",
        base_url="http://127.0.0.1:8766/v1", local_only=True, allows_paid_fallbacks=False,
        managed_by_app=True, healthcheck_path="/health"))
    process._process = StaleHandle()
    process._recent_stderr.append("[METAL] Insufficient Memory")
    caplog.set_level(logging.ERROR, logger="fichero_server.llm.local_inference")

    assert not process.is_running()
    assert process.last_error.startswith("local inference process exited")
    assert "Insufficient Memory" in process.last_error
    assert not process.is_running()  # logged once, not on every look
    assert sum("Insufficient Memory" in r.getMessage() for r in caplog.records) == 1


# --- before Start ------------------------------------------------------------------------------------


def test_the_start_plan_states_the_need_and_pages_at_once_on_this_mac(monkeypatch):
    from fichero_server.recipes.start import estimate

    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(8))
    local = {"workflow": "read", "steps": ["read"], "runs_on": "this-mac",
             "provider_override": "omlx", "model_override": "Qwen2.5-VL-3B"}
    cloud = {**local, "runs_on": "cloud", "provider_override": "openai", "model_override": "gpt-4o"}

    rows = estimate([local, cloud], 10)["runs"]

    assert rows[0]["memory"] == (
        f"{THREE_B.display_name} needs about 3.9 GB; on this Mac (8.0 GB) it reads one page at a time, "
        "about 3.9 GB at most")
    assert rows[1]["memory"] is None
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", _mac(16))
    assert "reads 4 pages at once, about 6.9 GB at most" in estimate([local], 10)["runs"][0]["memory"]


def test_a_run_torn_down_mid_read_does_not_wedge_the_next_runs_reads():
    """Each workflow run has its own event loop; one closed while a page held the only slot (an 8 GB
    Mac) must not leave every later read waiting forever."""
    from fichero_server.llm.local_inference import local_read_slot

    async def hold_forever(entered: asyncio.Event):
        async with local_read_slot(1):
            entered.set()
            await asyncio.Event().wait()

    old = asyncio.new_event_loop()
    entered = asyncio.Event()
    task = old.create_task(hold_forever(entered))
    old.run_until_complete(entered.wait())
    old.close()  # the run's loop ends with the read still holding its slot

    async def read():
        async with local_read_slot(1):
            return "read"

    assert asyncio.run(asyncio.wait_for(read(), timeout=2)) == "read"
    del task
