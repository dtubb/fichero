"""Dedicated MLX runtime provisioning outside the shipped engine env."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Callable
import uuid
import venv

from fichero_server.db.paths import model_store_root

MLX_LM_VERSION = "0.31.3"
#: mlx-lm's OpenAI server CANNOT accept images (#4560). Its
#: ``process_message_content`` rejects every non-text content part with
#: "Only 'text' content type is supported.", so a vision request to the
#: managed sidecar came back 404 no matter which VLM was loaded -- verified
#: live against Qwen3-VL-8B-4bit, which answered text prompts happily and
#: refused the very image the model exists to read. Every model in
#: MANAGED_MLX_MODELS is a vision/OCR VLM, so the whole managed-MLX OCR
#: story was unreachable. mlx-vlm ships the OpenAI-compatible server that
#: does decode ``image_url`` parts, so the runtime provisions BOTH: mlx-lm
#: for text models, mlx-vlm for vision ones.
MLX_VLM_VERSION = "0.6.17"
#: Audio is the third capability the catalog advertises, and it was the one
#: nothing could serve: the Whisper rows called ``import whisper`` inside the
#: shipped engine env, where openai-whisper is undeclared and torch is
#: deliberately absent. mlx-whisper is the MLX-native transcriber, and its
#: INFERENCE path is torch-free -- ``torch`` appears only in
#: ``mlx_whisper/torch_whisper.py``, the original-checkpoint conversion module
#: that ``transcribe`` never imports (verified by reading the 0.4.3 wheel).
#: The package still DECLARES torch, so it is installed with ``--no-deps``
#: alongside the deps the transcribe path actually uses; that keeps ~1.5 GB of
#: unused CUDA-era wheels out of the runtime venv.
MLX_WHISPER_VERSION = "0.4.3"
MLX_WHISPER_DEPENDENCIES = (
    "numba",
    "scipy",
    "tiktoken",
    "more-itertools",
    "tqdm",
)
_RUNTIME_DIRNAME = "mlx-runtime"

def bundled_versions() -> dict[str, str] | None:
    """The MLX packages bundled inside the app's engine (#4973), or None when they are not.

    In the app MLX ships with the engine and there is nothing to provision: the runtime reports
    itself ready with these versions, and models run in the engine (`llm/mlx_in_process.py`).
    """
    from importlib import metadata

    from fichero_server.llm.mlx_in_process import runs_in_process

    if not runs_in_process():
        return None
    found = {}
    for key, dist in (("mlx_lm_version", "mlx-lm"), ("mlx_vlm_version", "mlx-vlm"), ("mlx_whisper_version", "mlx-whisper")):
        try:
            found[key] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            pass
    return found

_METADATA_FILENAME = "runtime.json"

logger = logging.getLogger(__name__)

#: What a person reads when the runtime is missing or could not be set up: in words, no route, no path (#5664).
NOT_SET_UP = ("This Mac's local models are not set up yet. Start sets them up when a step needs them, or install "
              "Local Models in Settings › AI.")
COULD_NOT_SET_UP = ("This Mac's local models could not be set up; the engine's log says why. Try again, or install "
                    "Local Models in Settings › AI.")


class MLXRuntimeInTheAppError(RuntimeError):
    """Something in the app tried to use a separate MLX Python, which the sandbox can't have (#4973)."""


def _refuse_in_the_app() -> None:
    """In the app MLX is bundled and runs in the engine; nothing may build, start or download through a
    separate Python (the sandbox refuses it: "Operation not permitted"). A path that reaches here in the
    app is a bug, said loudly, never a provisioning prompt (2026-10-09)."""
    if bundled_versions() is not None:
        raise MLXRuntimeInTheAppError(
            "MLX ships inside the app and runs in the engine; this step tried to use a separate MLX Python, "
            "which a sandboxed app cannot have. This is a bug in Fichero, not something to install.")


class MLXAudioRuntimeMissingError(RuntimeError):
    """Raised when the MLX runtime exists but holds no transcriber."""


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
        # One setting-up at a time, whichever thread or event loop asks (Settings, Start's job, a model download).
        self._provisioning = threading.Lock()

    def is_provisioned(self) -> bool:
        """Whether this runtime can actually run mlx_lm.

        NOT just "the venv exists" (#4504). ``_provision`` creates the venv
        first and pip-installs mlx-lm second, so between those two steps
        ``python_path().exists()`` is already True while ``import mlx_lm``
        still fails. Any interruption in that window -- a timeout, a lost
        network, a quit -- leaves a runtime that reports itself ready and is
        not. Observed directly: a provisioning run killed at the 10-minute mark
        left exactly that state, and ``status()`` said provisioned.

        The metadata file is written as the LAST step of a successful
        provision, so its presence is the honest signal, and it already records
        the version we installed.
        """
        bundled = bundled_versions()
        if bundled is not None:  # the app: MLX ships inside the engine, nothing to provision (#4973)
            return bool(bundled.get("mlx_lm_version")) and bool(bundled.get("mlx_vlm_version"))
        metadata = self._metadata()
        return (
            self.python_path().exists()
            and bool(metadata.get("mlx_lm_version"))
            # A runtime provisioned before #4560 has mlx-lm and no mlx-vlm, and
            # is therefore blind to images. Reporting it "provisioned" is the
            # same lie #4504 fixed one layer up, so it reports unprovisioned
            # and one Provision click installs the missing half.
            and bool(metadata.get("mlx_vlm_version"))
        )

    def has_audio(self) -> bool:
        """Whether this runtime can transcribe audio.

        Deliberately NOT folded into ``is_provisioned()``. A runtime holding
        mlx-lm and mlx-vlm genuinely CAN serve every text and vision model in
        the catalog, so calling it unprovisioned because it lacks a
        transcriber would be the same kind of lie #4504 and #4560 removed,
        pointed the other way. Audio is reported as its own capability, and
        one Provision click installs whatever half is missing because
        ``_provision`` installs all three every time.
        """
        bundled = bundled_versions()
        if bundled is not None:
            return bool(bundled.get("mlx_whisper_version"))
        metadata = self._metadata()
        return self.python_path().exists() and bool(metadata.get("mlx_whisper_version"))

    def versions(self) -> dict[str, object]:
        """The recorded package versions ONLY -- no disk walk (#5228). ``status()`` adds up the
        runtime's disk usage by walking every file (22,869 on the maintainer's Mac, ~1.1 s), and the
        engine's health check -- the app's heartbeat -- asked for it on every poll just to read these."""
        metadata = bundled_versions() or self._metadata()
        return {key: metadata.get(key) for key in ("mlx_lm_version", "mlx_vlm_version", "mlx_whisper_version")}

    def status(self) -> dict[str, object]:
        python_path = self.python_path()
        # In the app MLX is built in: there is no separate Python or runtime folder to report, even when an old
        # provisioned one is still on disk from before (#4973; seen 2026-10-10 in the Dev Embedded app).
        bundled = bundled_versions() is not None
        return {
            "provisioned": self.is_provisioned(),
            "audio_ready": self.has_audio(),
            **self.versions(),
            "disk_usage_bytes": 0 if bundled else self._disk_usage_bytes(),
            "python_path": None if bundled or not python_path.exists() else str(python_path),
            "runtime_dir": str(self.runtime_dir),
            "job": self._job.to_dict() if self._job is not None else None,
        }

    async def start_provision(self) -> dict[str, object]:
        if bundled_versions() is not None:  # the app: MLX is built in, nothing to provision (#4973)
            return self.status()
        async with self._job_lock:
            if self._provision_task is not None and not self._provision_task.done():
                return self.status()
            job = RuntimeProvisionJob(
                job_id=str(uuid.uuid4()),
                state="running",
                current=0,
                total=6,
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
            raise RuntimeError("This Mac's local models are still being set up; remove them once that has finished.")
        target = self.runtime_dir.resolve()
        if target.name != _RUNTIME_DIRNAME:
            logger.error("not removing %s: not the MLX runtime's own folder", target)
            raise RuntimeError("Fichero will not remove that folder: it is not where this Mac's local models live.")
        if target.exists():
            shutil.rmtree(target)
        self._job = None
        return self.status()

    def require_python_path(self) -> Path:
        _refuse_in_the_app()
        # Same question as `status()`, so it must use the same answer (#4504).
        # Checking only for the venv here let a half-provisioned runtime through
        # the gate, and the failure then surfaced from `mlx_lm server` as a bare
        # "No module named mlx_lm" with no hint that provisioning was the cause.
        if self.is_provisioned():
            return self.python_path()
        # Where it looked goes to the log, never into the sentence a person reads (no route, no path).
        logger.warning("MLX runtime not provisioned: %s", self.missing())
        raise RuntimeError(NOT_SET_UP)

    def ensure_provisioned(self, on_message: Callable[[str], None] | None = None) -> Path:
        """The runtime's interpreter, setting the runtime up first when it is not (#5664: Start fetches what its
        steps need, and a model download needs the runtime). Blocks; one setting-up at a time, so a second caller
        waits for the first and then finds it done. Raises, in words, when it cannot be set up."""
        _refuse_in_the_app()
        if not self.is_provisioned():
            self.provision_now(on_message)
        return self.require_python_path()

    def provision_now(self, on_message: Callable[[str], None] | None = None) -> None:
        """Set the runtime up on this thread (a job's), as Settings' Install does; nothing when it already is.
        RuntimeError, in words, when it fails."""
        if bundled_versions() is not None:
            return
        with self._provisioning:
            if self.is_provisioned():
                return
            job = RuntimeProvisionJob(job_id=str(uuid.uuid4()), state="running", current=0, total=6,
                                      message="Creating MLX runtime")
            self._job = job
            asyncio.run(self._provision_steps(job, on_message))
        if job.state != "completed":
            raise RuntimeError(COULD_NOT_SET_UP)

    def missing(self) -> str:
        """What this runtime lacks, and WHERE it looked (#5534): an engine whose status said
        provisioned while its read said not could not be told apart from one looking elsewhere."""
        python, metadata = self.python_path(), self._metadata()
        if not python.exists():
            return f"no interpreter at {python}"
        absent = [key for key in ("mlx_lm_version", "mlx_vlm_version") if not metadata.get(key)]
        where = self.runtime_dir / _METADATA_FILENAME
        return f"{where} does not record {' or '.join(absent)}" if absent else f"looked in {self.runtime_dir}"

    def require_audio_python_path(self) -> Path:
        _refuse_in_the_app()
        """Interpreter that can run mlx-whisper, or a typed refusal saying so."""
        if self.has_audio():
            return self.python_path()
        raise MLXAudioRuntimeMissingError(
            "This Mac's local models cannot transcribe recordings yet: their transcriber is not installed. "
            "Install Local Models in Settings › AI."
        )

    def python_path(self) -> Path:
        return self.runtime_dir / "bin" / "python"

    async def _provision(self, job: RuntimeProvisionJob) -> None:
        # Settings' Install: the same one-at-a-time as `provision_now`, the lock taken off the event loop.
        await asyncio.to_thread(self._provisioning.acquire)
        try:
            if self.is_provisioned():
                job.current, job.state, job.message = job.total, "completed", "MLX runtime ready"
                return
            await self._provision_steps(job)
        finally:
            self._provisioning.release()

    async def _provision_steps(self, job: RuntimeProvisionJob,
                               on_message: Callable[[str], None] | None = None) -> None:
        def say(message: str) -> None:
            job.message = message
            if on_message is not None:
                on_message(message)

        try:
            await asyncio.to_thread(self._ensure_parent_dir)
            job.current = 1
            say("Creating runtime virtual environment")
            await asyncio.to_thread(self._create_venv, self.runtime_dir)
            job.current = 2
            say(f"Installing mlx-lm=={MLX_LM_VERSION}")
            await asyncio.to_thread(
                self._run_command,
                [str(self.python_path()), "-m", "pip", "install", f"mlx-lm=={MLX_LM_VERSION}"],
            )
            job.current = 3
            say(f"Installing mlx-vlm=={MLX_VLM_VERSION}")
            await asyncio.to_thread(
                self._run_command,
                [str(self.python_path()), "-m", "pip", "install", f"mlx-vlm=={MLX_VLM_VERSION}"],
            )
            job.current = 4
            say(f"Installing mlx-whisper=={MLX_WHISPER_VERSION}")
            await asyncio.to_thread(
                self._run_command,
                [
                    str(self.python_path()),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    f"mlx-whisper=={MLX_WHISPER_VERSION}",
                ],
            )
            job.current = 5
            say("Installing transcription dependencies")
            await asyncio.to_thread(
                self._run_command,
                [str(self.python_path()), "-m", "pip", "install", *MLX_WHISPER_DEPENDENCIES],
            )
            job.current = 6
            say("Writing runtime metadata")
            await asyncio.to_thread(self._write_metadata)
            job.state = "completed"
            say("MLX runtime ready")
        except Exception as exc:
            # What failed (a pip command, a path) goes to the log; the job says it in words.
            logger.exception("MLX runtime set-up failed: %s", exc)
            job.state = "failed"
            job.error = COULD_NOT_SET_UP
            say("MLX runtime provisioning failed")

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
            json.dumps(
                {
                    "mlx_lm_version": MLX_LM_VERSION,
                    "mlx_vlm_version": MLX_VLM_VERSION,
                    "mlx_whisper_version": MLX_WHISPER_VERSION,
                },
                indent=2,
                sort_keys=True,
            ),
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


#: Python environments earlier builds made at run time, before MLX and Kraken shipped inside the app (#4973).
_LEGACY_RUNTIME_DIRNAMES = (_RUNTIME_DIRNAME, "kraken-runtime")


def remove_runtimes_the_app_no_longer_uses(home: Path | None = None) -> list[str]:
    """In the app, delete the Python environments earlier builds provisioned at run time (2026-10-10: two
    half-built ones found in the maintainer's container). Only a folder that IS such an environment (it has
    a `pyvenv.cfg`) is removed; nothing happens outside the app. Returns the folders removed."""
    import shutil

    if bundled_versions() is None:
        return []
    removed = []
    for name in _LEGACY_RUNTIME_DIRNAMES:
        folder = model_store_root(home) / name
        if (folder / "pyvenv.cfg").is_file():
            shutil.rmtree(folder, ignore_errors=True)
            removed.append(str(folder))
    return removed


def mlx_runtime_dir(home: Path | None = None) -> Path:
    override = os.environ.get("FICHERO_MLX_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()
    return model_store_root(home) / _RUNTIME_DIRNAME


def get_mlx_runtime() -> MLXRuntime:
    global _RUNTIME_MANAGER
    runtime_dir = mlx_runtime_dir()
    if _RUNTIME_MANAGER is None or _RUNTIME_MANAGER.runtime_dir != runtime_dir:
        _RUNTIME_MANAGER = MLXRuntime(runtime_dir)
    return _RUNTIME_MANAGER


__all__ = [
    "MLXAudioRuntimeMissingError",
    "MLXRuntime",
    "MLX_WHISPER_DEPENDENCIES",
    "MLX_WHISPER_VERSION",
    "MLX_LM_VERSION",
    "MLX_VLM_VERSION",
    "RuntimeProvisionJob",
    "get_mlx_runtime",
    "mlx_runtime_dir",
]
