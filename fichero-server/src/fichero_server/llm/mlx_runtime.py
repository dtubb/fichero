"""Dedicated MLX runtime provisioning outside the shipped engine env."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable
import uuid
import venv

from fichero_server.db.paths import server_state_dir

MLX_LM_VERSION = "0.31.3"
_RUNTIME_DIRNAME = "mlx-runtime"
_METADATA_FILENAME = "runtime.json"


@dataclass
class RuntimeProvisionJob:
    job_id: str
    state: str
    current: int
    total: int
    message: str
    error: str | None = None

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.current / self.total) * 100

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["percent"] = self.percent
        return data


class MLXRuntime:
    """Manage the dedicated mlx-lm runtime venv."""

    def __init__(
        self,
        runtime_dir: Path | None = None,
        *,
        create_venv: Callable[[Path], None] | None = None,
        run_command: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.runtime_dir = runtime_dir or mlx_runtime_dir()
        self._create_venv = create_venv or self._default_create_venv
        self._run_command = run_command or self._default_run_command
        self._job_lock = asyncio.Lock()
        self._provision_task: asyncio.Task[None] | None = None
        self._job: RuntimeProvisionJob | None = None

    def status(self) -> dict[str, object]:
        python_path = self.python_path()
        return {
            "provisioned": python_path.exists(),
            "mlx_lm_version": self._metadata().get("mlx_lm_version"),
            "disk_usage_bytes": self._disk_usage_bytes(),
            "python_path": str(python_path) if python_path.exists() else None,
            "runtime_dir": str(self.runtime_dir),
            "job": self._job.to_dict() if self._job is not None else None,
        }

    async def start_provision(self) -> dict[str, object]:
        async with self._job_lock:
            if self._provision_task is not None and not self._provision_task.done():
                return self.status()
            job = RuntimeProvisionJob(
                job_id=str(uuid.uuid4()),
                state="running",
                current=0,
                total=3,
                message="Creating MLX runtime",
            )
            self._job = job
            self._provision_task = asyncio.create_task(self._provision(job))
            return self.status()

    async def wait_for_current_job(self) -> None:
        task = self._provision_task
        if task is not None:
            await task

    def remove(self) -> dict[str, object]:
        if self._provision_task is not None and not self._provision_task.done():
            raise RuntimeError("MLX runtime provisioning is still running")
        target = self.runtime_dir.resolve()
        if target.name != _RUNTIME_DIRNAME:
            raise RuntimeError(f"Refusing to remove unexpected runtime dir: {target}")
        if target.exists():
            shutil.rmtree(target)
        self._job = None
        return self.status()

    def require_python_path(self) -> Path:
        python_path = self.python_path()
        if python_path.exists():
            return python_path
        raise RuntimeError(
            "MLX runtime is not provisioned. Call POST /api/local-inference/runtime/provision "
            "or enable Local Models in Settings before starting oMLX."
        )

    def python_path(self) -> Path:
        return self.runtime_dir / "bin" / "python"

    async def _provision(self, job: RuntimeProvisionJob) -> None:
        try:
            await asyncio.to_thread(self._ensure_parent_dir)
            job.current = 1
            job.message = "Creating runtime virtual environment"
            await asyncio.to_thread(self._create_venv, self.runtime_dir)
            job.current = 2
            job.message = f"Installing mlx-lm=={MLX_LM_VERSION}"
            await asyncio.to_thread(
                self._run_command,
                [str(self.python_path()), "-m", "pip", "install", f"mlx-lm=={MLX_LM_VERSION}"],
            )
            job.current = 3
            job.message = "Writing runtime metadata"
            await asyncio.to_thread(self._write_metadata)
            job.state = "completed"
            job.message = "MLX runtime ready"
        except Exception as exc:
            job.state = "failed"
            job.error = str(exc)
            job.message = "MLX runtime provisioning failed"

    def _ensure_parent_dir(self) -> None:
        self.runtime_dir.parent.mkdir(parents=True, exist_ok=True)

    def _metadata(self) -> dict[str, object]:
        path = self.runtime_dir / _METADATA_FILENAME
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_metadata(self) -> None:
        (self.runtime_dir / _METADATA_FILENAME).write_text(
            json.dumps({"mlx_lm_version": MLX_LM_VERSION}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _disk_usage_bytes(self) -> int:
        if not self.runtime_dir.exists():
            return 0
        total = 0
        for path in self.runtime_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    @staticmethod
    def _default_create_venv(target: Path) -> None:
        builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade=False)
        builder.create(target)

    @staticmethod
    def _default_run_command(argv: list[str]) -> None:
        subprocess.run(argv, check=True, capture_output=True, text=True)


_RUNTIME_MANAGER: MLXRuntime | None = None


def mlx_runtime_dir(home: Path | None = None) -> Path:
    override = os.environ.get("FICHERO_MLX_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()
    return server_state_dir(home) / _RUNTIME_DIRNAME


def get_mlx_runtime() -> MLXRuntime:
    global _RUNTIME_MANAGER
    runtime_dir = mlx_runtime_dir()
    if _RUNTIME_MANAGER is None or _RUNTIME_MANAGER.runtime_dir != runtime_dir:
        _RUNTIME_MANAGER = MLXRuntime(runtime_dir)
    return _RUNTIME_MANAGER


__all__ = [
    "MLXRuntime",
    "MLX_LM_VERSION",
    "RuntimeProvisionJob",
    "get_mlx_runtime",
    "mlx_runtime_dir",
]
