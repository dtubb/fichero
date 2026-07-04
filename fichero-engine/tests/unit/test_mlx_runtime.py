from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time

import pytest

from fichero.local_inference import LocalInferenceRuntimeMissingError, ManagedLocalInferenceProcess
from fichero.mlx_runtime import MLXRuntime, MLX_LM_VERSION


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
        '{"mlx_lm_version": "0.31.3"}',
        encoding="utf-8",
    )
    ready = runtime.status()

    assert ready["provisioned"] is True
    assert ready["mlx_lm_version"] == "0.31.3"
    assert ready["python_path"] == str(runtime.runtime_dir / "bin" / "python")


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
    assert commands == [[str(runtime.runtime_dir / "bin" / "python"), "-m", "pip", "install", f"mlx-lm=={MLX_LM_VERSION}"]]
    assert runtime.status()["provisioned"] is True


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
