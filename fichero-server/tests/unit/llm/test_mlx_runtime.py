from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest

from fichero_server.llm.local_inference import LocalInferenceRuntimeMissingError, ManagedLocalInferenceProcess
from fichero_server.llm.mlx_runtime import (
    MLXAudioRuntimeMissingError,
    MLXRuntime,
    MLX_LM_VERSION,
    MLX_VLM_VERSION,
    MLX_WHISPER_DEPENDENCIES,
    MLX_WHISPER_VERSION,
)


def _touch_python(runtime_dir: Path) -> None:
    python_path = runtime_dir / "bin" / "python"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


def test_runtime_status_reflects_provisioned_and_unprovisioned(tmp_path: Path) -> None:
    runtime = MLXRuntime(tmp_path / "mlx-runtime")

    empty = runtime.status()
    assert empty["provisioned"] is False
    assert empty["python_path"] is None

    _touch_python(runtime.runtime_dir)
    (runtime.runtime_dir / "runtime.json").write_text(
        '{"mlx_lm_version": "0.31.3", "mlx_vlm_version": "0.6.17"}',
        encoding="utf-8",
    )
    ready = runtime.status()

    assert ready["provisioned"] is True
    assert ready["mlx_lm_version"] == "0.31.3"
    assert ready["mlx_vlm_version"] == "0.6.17"
    assert ready["python_path"] == str(runtime.runtime_dir / "bin" / "python")


def test_runtime_with_only_mlx_lm_is_not_provisioned(tmp_path: Path) -> None:
    """A pre-#4560 runtime has mlx-lm and no mlx-vlm, so it cannot read images.

    Every model in the managed catalog is a vision model, and `mlx_lm server`
    refuses image content outright. A runtime in that state reporting itself
    ready is the failure #4504 already fixed once at a different layer: the
    status has to describe what the runtime can actually DO.
    """
    runtime = MLXRuntime(tmp_path / "mlx-runtime")
    _touch_python(runtime.runtime_dir)
    (runtime.runtime_dir / "runtime.json").write_text(
        '{"mlx_lm_version": "0.31.3"}',
        encoding="utf-8",
    )

    status = runtime.status()
    assert status["provisioned"] is False
    assert status["mlx_vlm_version"] is None
    with pytest.raises(RuntimeError, match="mlx-vlm"):
        runtime.require_python_path()


@pytest.mark.asyncio
async def test_provision_coalesces_and_installs_pinned_version(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    create_calls: list[Path] = []

    def create_venv(runtime_dir: Path) -> None:
        create_calls.append(runtime_dir)
        _touch_python(runtime_dir)

    def run_command(argv: list[str]) -> None:
        commands.append(argv)
        time.sleep(0.1)

    runtime = MLXRuntime(tmp_path / "mlx-runtime", create_venv=create_venv, run_command=run_command)

    first = await runtime.start_provision()
    second = await runtime.start_provision()
    assert first["job"]["job_id"] == second["job"]["job_id"]
    assert len(create_calls) <= 1
    await runtime.wait_for_current_job()

    assert create_calls == [runtime.runtime_dir]
    python = str(runtime.runtime_dir / "bin" / "python")
    assert commands == [
        [python, "-m", "pip", "install", f"mlx-lm=={MLX_LM_VERSION}"],
        [python, "-m", "pip", "install", f"mlx-vlm=={MLX_VLM_VERSION}"],
        # --no-deps on purpose: mlx-whisper DECLARES torch, but only its
        # checkpoint-conversion module imports it. Installing the declared
        # dependency set would drag ~1.5 GB of unused wheels into the runtime.
        [python, "-m", "pip", "install", "--no-deps", f"mlx-whisper=={MLX_WHISPER_VERSION}"],
        [python, "-m", "pip", "install", *MLX_WHISPER_DEPENDENCIES],
    ]
    status = runtime.status()
    assert status["provisioned"] is True
    assert status["audio_ready"] is True
    assert status["mlx_whisper_version"] == MLX_WHISPER_VERSION


def test_a_runtime_without_a_transcriber_serves_models_but_refuses_audio(tmp_path: Path) -> None:
    """Audio is its own capability, not a reason to call the runtime broken.

    A runtime holding mlx-lm and mlx-vlm can serve every text and vision model
    in the catalog. Reporting it "not provisioned" because it cannot transcribe
    would push the user to reinstall a runtime that works; reporting audio as
    ready when nothing can transcribe is the lie #4504 removed. So it reports
    provisioned AND audio_ready=False, and the audio path refuses with an
    error that says exactly what to click.
    """
    runtime = MLXRuntime(tmp_path / "mlx-runtime")
    _touch_python(runtime.runtime_dir)
    (runtime.runtime_dir / "runtime.json").write_text(
        '{"mlx_lm_version": "0.31.3", "mlx_vlm_version": "0.6.17"}',
        encoding="utf-8",
    )

    status = runtime.status()
    assert status["provisioned"] is True
    assert status["audio_ready"] is False
    assert status["mlx_whisper_version"] is None
    # The vision/text path is untouched by the missing transcriber.
    assert runtime.require_python_path() == runtime.python_path()
    with pytest.raises(MLXAudioRuntimeMissingError, match="Provision the MLX runtime"):
        runtime.require_audio_python_path()


def test_remove_only_cleans_runtime_prefix(tmp_path: Path) -> None:
    parent = tmp_path / "Fichero"
    runtime_dir = parent / "mlx-runtime"
    sibling = parent / "keep-me"
    _touch_python(runtime_dir)
    sibling.mkdir(parents=True)
    (sibling / "note.txt").write_text("keep", encoding="utf-8")
    runtime = MLXRuntime(runtime_dir)

    runtime.remove()

    assert runtime_dir.exists() is False
    assert sibling.exists() is True


def test_missing_runtime_raises_typed_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_MLX_RUNTIME_DIR", str(tmp_path / "mlx-runtime"))
    process = ManagedLocalInferenceProcess(
        profile=type(
            "Profile",
            (),
            {
                "python_executable": None,
                "command": ["-m", "mlx_lm", "server"],
                "model_id": "mlx-community/Qwen3-VL-8B",
                "base_url": "http://127.0.0.1:8000/v1",
            },
        )()
    )

    with pytest.raises(LocalInferenceRuntimeMissingError):
        process._python_executable()


def test_runtime_prefix_is_separate_from_engine_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "Fichero" / "mlx-runtime"
    monkeypatch.setenv("FICHERO_MLX_RUNTIME_DIR", str(runtime_dir))
    runtime = MLXRuntime(runtime_dir)

    assert runtime.runtime_dir != Path(sys.prefix)
    assert runtime.runtime_dir not in Path(sys.prefix).parents


def test_a_venv_without_mlx_lm_is_not_provisioned(tmp_path):
    """The half-provisioned window is not "ready" (#4504).

    `_provision` creates the venv first and pip-installs mlx-lm second, so
    between those steps the venv python exists while `import mlx_lm` still
    fails. Anything that interrupts that window -- a timeout, a dropped
    network, a quit -- used to leave a runtime reporting itself provisioned and
    then failing at `mlx_lm server` with a bare "No module named mlx_lm".

    Observed for real: a provisioning run killed at ten minutes left exactly
    this state on disk, and `status()` said provisioned.
    """
    runtime = MLXRuntime(tmp_path / "mlx-runtime")
    _touch_python(runtime.runtime_dir)

    assert runtime.python_path().exists()
    assert runtime.status()["provisioned"] is False
    with pytest.raises(RuntimeError, match="not provisioned"):
        runtime.require_python_path()


def test_a_completed_provision_is_provisioned(tmp_path):
    """And the whole thing must still say yes when it really is ready -- the
    other half of the assertion, so the fix cannot be "always return False"."""
    runtime = MLXRuntime(tmp_path / "mlx-runtime")
    _touch_python(runtime.runtime_dir)
    runtime._write_metadata()

    assert runtime.status()["provisioned"] is True
    assert runtime.status()["mlx_lm_version"] == MLX_LM_VERSION
    assert runtime.require_python_path() == runtime.python_path()


def _vision_profile(model_id: str):
    from fichero_server.llm.local_inference import LocalProviderProfile

    return LocalProviderProfile(
        id="app-omlx",
        name="App-managed oMLX",
        provider_type="omlx",
        model_id=model_id,
        base_url="http://127.0.0.1:8000/v1",
    )


def test_vision_models_launch_the_vlm_server_not_mlx_lm() -> None:
    """#4560: `mlx_lm server` cannot read an image, so an OCR model must not get it.

    mlx-lm's `process_message_content` raises "Only 'text' content type is
    supported." for every non-text part, and the server turns that into a 404.
    Verified live: Qwen3-VL-8B-4bit loaded under `mlx_lm server` answered a
    text prompt in 56s and refused an image outright. Since EVERY entry in
    MANAGED_MLX_MODELS is a vision model, sending them to mlx-lm meant the
    managed-MLX OCR path could never work at all.
    """
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    vision_ids = [
        model_id
        for model_id, spec in MANAGED_MLX_MODELS.items()
        if "vision" in spec.capabilities
    ]
    assert vision_ids, "the managed catalog is supposed to hold vision models"

    for model_id in vision_ids:
        process = ManagedLocalInferenceProcess(_vision_profile(model_id))
        assert process._command() == ["-m", "mlx_vlm.server"], model_id


def test_unknown_models_still_get_the_text_server() -> None:
    """A user-configured repo id is not in the catalog and is assumed text-only.

    mlx-lm loads plain text models that mlx-vlm would refuse, so the fallback
    has to stay mlx-lm rather than flipping everything to the VLM server.
    """
    process = ManagedLocalInferenceProcess(_vision_profile("some-user/never-heard-of-it"))
    assert process._command() == ["-m", "mlx_lm", "server"]


def test_an_explicit_command_override_still_wins() -> None:
    """FICHERO_OMLX_COMMAND is the escape hatch; capability routing must not eat it."""
    from fichero_server.llm.local_inference import LocalProviderProfile

    profile = LocalProviderProfile(
        id="app-omlx",
        name="App-managed oMLX",
        provider_type="omlx",
        model_id="Chandra-OCR",
        base_url="http://127.0.0.1:8000/v1",
        command=["-m", "my_own_server"],
    )
    assert ManagedLocalInferenceProcess(profile)._command() == ["-m", "my_own_server"]


def test_a_managed_model_goes_over_the_wire_as_its_local_path(tmp_path, monkeypatch) -> None:
    """The catalog id is OURS; the sidecar only knows paths and Hub repos (#4560).

    "Qwen2.5-VL-3B" names a row in MANAGED_MLX_MODELS. Sent as the OpenAI
    `model` field it made mlx_vlm's server try to FETCH that name from
    Hugging Face, which 401'd "Repository Not Found" -- over a model already
    installed and already loaded in the very process being asked. Measured
    live before the fix; after it the same run transcribed the page.
    """
    import fichero_server.llm as llm
    from fichero_server.llm import LLMConfig, mlx_model_store

    snapshot = tmp_path / "snap"
    snapshot.mkdir()

    class _Store:
        def resolve_model_path(self, model_id: str) -> str:
            if model_id == "Qwen2.5-VL-3B":
                return str(snapshot)
            raise KeyError(model_id)

    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: _Store())

    # ChatOpenAI is imported INSIDE the builder, so patch it at its source.
    import langchain_openai

    captured: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)

    llm._build_langchain_model(LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))
    assert captured.get("model") == str(snapshot), (
        "a managed model must be named by the path the sidecar was launched with"
    )

    captured.clear()
    llm._build_langchain_model(LLMConfig(provider="omlx", model="some-user/byo-repo"))
    assert captured.get("model") == "some-user/byo-repo", (
        "an unmanaged repo id passes through untouched"
    )
