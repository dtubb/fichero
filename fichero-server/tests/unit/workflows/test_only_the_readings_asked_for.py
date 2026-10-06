"""A run makes only the readings it was asked for, and says truthfully what it is (#5523).

Found 2026-10-06 by the M4 operator (Qwen2.5-VL-3B via MLX on a 16 GB M4):

* every Transcribe run -- failed ones too -- ALSO stored an Apple Vision reading of the page that
  nobody chose; on a Spanish manuscript Apple Vision read Cyrillic (CER 0.815). The cause:
  Transcribe's `regions_first` pre-pass (an Apple Vision OCR saved as a `regions` artifact) was ON
  by default;
* the step was labelled 'Transcribe (cloud)' for a local MLX run;
* the MLX runtime row said ready while its Whisper part had not installed;
* a model download's progress sat at 66.7% throughout: progress was three steps, and the whole
  download is step 2 of 3.

WHY: an unasked-for reading is a second voice on the page that a person has to notice and discount
(and a Cyrillic one competes in every comparison); a label that says 'cloud' on a local run tells a
person their pages left the Mac when they did not; a 'ready' that hides a missing part fails later,
where it cannot be explained; a progress bar that never moves reads as a hang.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import detect_regions as detect_regions_module


@pytest.fixture
def calls(monkeypatch):
    """Which of the two passes ran: the Apple Vision regions pre-pass, and the chosen reader."""
    from fichero_server.workflows.tools import transcribe as transcribe_module

    order: list[str] = []

    async def fake_detect(**kwargs):
        order.append("apple-vision-regions")
        return {"results": []}

    async def fake_process_vision(**kwargs):
        order.append("chosen-reader")
        return {"results": [], "notes": []}

    monkeypatch.setattr(detect_regions_module, "detect_regions", fake_detect)
    monkeypatch.setattr(transcribe_module, "process_vision", fake_process_vision)
    return order


async def _transcribe(inputs, config):
    from fichero_server.workflows.tools.transcribe import transcribe

    return await transcribe(inputs={"files": ["/a.jpg"], "documents": [], **inputs},
                            state={"library_path": "/lib", "input_files": []}, llm_config=config)


@pytest.mark.asyncio
async def test_a_transcribe_with_a_chosen_model_makes_no_apple_vision_reading(calls):
    await _transcribe({}, LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))
    assert calls == ["chosen-reader"]


@pytest.mark.asyncio
async def test_the_regions_pre_pass_runs_when_the_step_asks_for_it(calls):
    await _transcribe({"regions_first": True}, LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))
    assert calls == ["apple-vision-regions", "chosen-reader"]


@pytest.mark.asyncio
async def test_no_second_apple_vision_reading_when_apple_vision_is_the_reader(calls):
    await _transcribe({"regions_first": True, "vision_mode": "apple"}, LLMConfig(provider="omlx", model="x"))
    assert calls == ["chosen-reader"]


@pytest.mark.asyncio
async def test_no_second_apple_vision_reading_when_auto_picks_apple_vision(calls):
    await _transcribe({"regions_first": True, "vision_mode": "auto"},
                      LLMConfig(provider="apple", model="apple-vision"))
    assert calls == ["chosen-reader"]


def test_the_step_defaults_say_no_regions_pre_pass():
    from fichero_server.workflows.registry import get_tool_def

    tool = get_tool_def("transcribe")
    assert tool.config_defaults["regions_first"] is False
    assert tool.config_schema["regions_first"]["default"] is False


def test_the_plain_transcribe_preset_does_not_say_cloud():
    """The preset reads with whichever vision model is set -- a local MLX one included -- so its
    step label must not claim the cloud."""
    import fichero_server

    preset = json.loads((Path(fichero_server.__file__).parent / "resources" / "default_workflows"
                         / "transcribe_cloud.json").read_text())
    step = next(n for n in preset["nodes"] if n["tool"] == "transcribe")
    assert "cloud" not in step["label"].lower()
    assert "cloud" not in preset["tags"]
    assert preset["config"]["preset_version"] >= 5, "existing libraries only get the fix with a bump"


class _Runtime:
    def __init__(self, provisioned: bool, audio_ready: bool):
        self._status = {"provisioned": provisioned, "audio_ready": audio_ready}

    def status(self):
        return self._status


@pytest.mark.parametrize("audio_ready,expect_reason", [(False, True), (True, False)])
def test_the_mlx_row_says_which_part_is_missing(monkeypatch, audio_ready, expect_reason):
    from fichero_server.api.routes.ai import provider_models

    monkeypatch.setattr("fichero_server.llm.mlx_runtime.get_mlx_runtime", lambda: _Runtime(True, audio_ready))
    row = provider_models._mlx_runtime_row()
    assert row.installed is True, "vision and text models still run"
    if expect_reason:
        assert "mlx-whisper" in row.reason and "not installed" in row.reason
    else:
        assert row.reason is None


@pytest.mark.asyncio
async def test_a_download_reports_its_bytes_as_they_arrive(tmp_path, monkeypatch):
    from fichero_server.llm import mlx_model_store
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, MLXModelStore

    store = MLXModelStore(tmp_path / "mlx")
    spec = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]
    blobs = store.cache_dir / f"models--{spec.repo_id.replace('/', '--')}" / "blobs"
    finish = asyncio.Event()

    class Process:
        returncode = 0

        async def communicate(self):
            await finish.wait()
            return b"", b""

    async def fake_exec(*argv, **kwargs):
        return Process()

    class Runtime:
        def require_python_path(self):
            return Path("/tmp/mlx-runtime/bin/python")

    monkeypatch.setattr(mlx_model_store, "get_mlx_runtime", lambda: Runtime())
    monkeypatch.setattr(mlx_model_store.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(mlx_model_store, "DOWNLOAD_PROGRESS_POLL_SECONDS", 0.01)

    job = await store.start_download("Qwen2.5-VL-3B")
    assert job.total == spec.download_size_bytes, "progress is out of the model's bytes, not 3 steps"
    blobs.mkdir(parents=True)
    (blobs / "abc.incomplete").write_bytes(b"x" * 1_000_000)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if job.current == 1_000_000:
            break
    assert job.current == 1_000_000
    assert 0 < job.percent < 1
    assert "1 MB of 3.1 GB" in job.message

    finish.set()
    await store._job_tasks[job.job_id]
    assert job.state == "completed" and job.percent == 100.0
