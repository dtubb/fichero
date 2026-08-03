"""Bounded-concurrent per-file processing in process_vision (#2539).

The vision/transcribe node used to await each file's vision() call strictly
one-at-a-time on the event loop, so the in-flight LLM concurrency was 1 and the
shared VISION_FAN_OUT_CONCURRENCY semaphore never engaged. #2539 makes the
per-file loop bounded-concurrent (asyncio.gather capped by the semaphore) while
preserving:

- RESULT ORDERING — texts/values/results stay index-aligned to `files` even
  though files complete out of index order.
- ERROR ISOLATION — one file raising records its error and never aborts the
  siblings or the node.
- THE CAP — peak simultaneously in-flight vision calls stays <=
  VISION_FAN_OUT_CONCURRENCY.

These tests patch fichero_server.llm.vision (process_vision re-imports it per call) and
fichero_server.workflows.tools.vision_base.file_to_data_uri (so no real image decode),
and run with library_path="" so the DB save path is skipped — keeping the focus
on the loop's concurrency/ordering/error semantics.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import VISION_FAN_OUT_CONCURRENCY
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision
from unittest.mock import patch


_TOOL_CFG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    skip_if_artifact_exists=False,
)

_LLM_CFG = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


@pytest.fixture(autouse=True)
def _fresh_vision_semaphore():
    """The vision fan-out semaphore is a lazily-created module-global singleton
    bound to the event loop that first created it. In production there is one
    long-lived loop, but pytest-asyncio gives each test a fresh loop, so a cached
    semaphore from a prior test is bound to a dead loop. Reset it so each test
    builds the cap in its own loop. (Resets builder state only; does not modify
    builder.py — that lane is owned elsewhere.)"""
    import fichero_server.workflows.builder as _b

    _b._vision_fan_out_sem = None
    yield
    _b._vision_fan_out_sem = None


def _index_from_images(images) -> int:
    """Our patched file_to_data_uri echoes the file path, so images[0] is the
    file path 'imgN.png' — recover N."""
    name = str(images[0])
    digits = "".join(c for c in name.rsplit("img", 1)[-1] if c.isdigit())
    return int(digits)


async def _run(files, vision_fn):
    with (
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            side_effect=lambda path, max_dimension=2048: path,
        ),
        patch("fichero_server.llm.vision", new=vision_fn),
    ):
        return await process_vision(
            files=files,
            documents=[],
            prompt="Transcribe.",
            llm_config=_LLM_CFG,
            library_path="",  # skip DB save path; exercise loop semantics only
            task_id=None,
            tool_config=_TOOL_CFG,
            vision_mode="llm",
        )


@pytest.mark.asyncio
async def test_files_overlap_and_peak_inflight_capped_by_semaphore(tmp_path):
    """#2539: N>cap files process concurrently, bounded by the semaphore.

    Goes RED on the pre-#2539 one-at-a-time loop: peak in-flight would be 1 and
    elapsed would be ~sum(per-file) instead of ~ceil(N/cap)*per_file.
    """
    n_files = VISION_FAN_OUT_CONCURRENCY * 2  # 8 with cap 4
    per_file = 0.05
    files = [str(tmp_path / f"img{i}.png") for i in range(n_files)]
    for f in files:
        # file_to_data_uri is patched, but make the paths real-ish anyway.
        with open(f, "wb") as fh:
            fh.write(b"PNG")

    inflight = 0
    peak = 0

    async def _vision(images, prompt, config, *, language=None):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        try:
            await asyncio.sleep(per_file)
            return f"text-{_index_from_images(images)}"
        finally:
            inflight -= 1

    start = time.perf_counter()
    result = await _run(files, _vision)
    elapsed = time.perf_counter() - start

    # Cap respected: never more than VISION_FAN_OUT_CONCURRENCY in flight.
    assert peak <= VISION_FAN_OUT_CONCURRENCY, (
        f"peak in-flight {peak} exceeded cap {VISION_FAN_OUT_CONCURRENCY}"
    )
    # Concurrency engaged: at least 2 ran at once (not strictly sequential).
    assert peak >= 2, f"expected overlap, peak in-flight was {peak}"
    # Overlap proven by wall time: ~ceil(8/4)*0.05 = 0.10s, never ~0.40s serial.
    serial = n_files * per_file
    assert elapsed < serial * 0.6, (
        f"elapsed {elapsed:.3f}s looks serial (serial would be ~{serial:.3f}s)"
    )
    # All files produced a result.
    assert len(result["texts"]) == n_files


@pytest.mark.asyncio
async def test_results_ordered_by_input_index_despite_out_of_order_completion(
    tmp_path,
):
    """#2539: completion order is reversed (file 0 slowest), but texts/values/
    results must come back in INPUT order — aggregators depend on this."""
    n_files = 6
    files = [str(tmp_path / f"img{i}.png") for i in range(n_files)]

    async def _vision(images, prompt, config, *, language=None):
        idx = _index_from_images(images)
        # Earlier files sleep longer -> they finish LAST.
        await asyncio.sleep(0.01 * (n_files - idx))
        return f"text-{idx}"

    result = await _run(files, _vision)

    assert result["texts"] == [f"text-{i}" for i in range(n_files)]
    assert result["values"] == [f"text-{i}" for i in range(n_files)]
    assert [r["file"] for r in result["results"]] == files


@pytest.mark.asyncio
async def test_one_file_failing_does_not_kill_the_others(tmp_path):
    """#2539: a single file raising (e.g. provider quota) records its error and
    the sibling files still return their results — node-level error isolation."""
    n_files = 4
    failing = 2
    files = [str(tmp_path / f"img{i}.png") for i in range(n_files)]

    async def _vision(images, prompt, config, *, language=None):
        idx = _index_from_images(images)
        await asyncio.sleep(0.01)
        if idx == failing:
            raise RuntimeError("simulated provider quota error")
        return f"text-{idx}"

    result = await _run(files, _vision)

    # Failed file: empty text, recorded error, still at its index.
    assert result["texts"][failing] == ""
    assert result["results"][failing].get("error")
    assert "simulated provider quota error" in result["results"][failing]["error"]

    # Every other file produced its real result, index-aligned.
    for i in range(n_files):
        if i == failing:
            continue
        assert result["texts"][i] == f"text-{i}"
        assert result["results"][i].get("error") is None

    # Node-level error summary reflects exactly one failure out of four.
    assert result["error"] is not None
    assert "1/4 failed" in result["error"]
