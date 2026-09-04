"""Managed MLX model store for local inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Any

from fichero_server.llm.mlx_runtime import get_mlx_runtime
from fichero_server.db.paths import server_state_dir
from fichero_server.llm.providers import ProviderType


@dataclass(frozen=True)
class ManagedModelSpec:
    model_id: str
    repo_id: str
    revision: str
    display_name: str
    download_size_bytes: int
    min_memory_bytes: int
    memory_class: str
    capabilities: tuple[str, ...]
    #: One line saying what this model is FOR, and what is known about it on
    #: this hardware. Shown under the row -- an unlabelled catalog forces the
    #: user to guess which of five OCR models to spend 6 GB on.
    note: str
    #: "verified" when someone has run this model in Fichero and seen output;
    #: "untested" when it is here on its reputation only. Never inferred.
    tested_status: str = "untested"


@dataclass
class ManagedModelDownloadJob:
    job_id: str
    model_id: str
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "model_id": self.model_id,
            "state": self.state,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
            "error": self.error,
        }


#: A CURATED list, deliberately short (#4560 follow-up). Every entry carries a
#: measured download size (summed HF blob sizes for that exact revision), a
#: memory floor, its capabilities, one line on what it is for, and whether
#: anyone has actually RUN it here. Reputation is not evidence: an entry says
#: "untested" until someone watches it produce output in Fichero.
MANAGED_MLX_MODELS: dict[str, ManagedModelSpec] = {
    # --- Vision / OCR -------------------------------------------------------
    "Qwen2.5-VL-3B": ManagedModelSpec(
        model_id="Qwen2.5-VL-3B",
        repo_id="mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
        revision="46d4cf06a06ffc1a766c214174f9cbed2f45bcab",
        display_name="Qwen2.5-VL 3B (OCR)",
        download_size_bytes=3_090_000_000,
        min_memory_bytes=8 * 1024**3,
        memory_class="needs 8 GB unified memory",
        capabilities=("text", "vision"),
        note="Start here for on-device OCR. The small end of the catalog, and the entry that makes vision reachable on a 16 GB Mac.",
        tested_status="verified",
    ),
    "mlx-community/Qwen3-VL-8B": ManagedModelSpec(
        model_id="mlx-community/Qwen3-VL-8B",
        repo_id="mlx-community/Qwen3-VL-8B-Instruct-4bit",
        revision="defcdea7cc7a4b0858fea563cbbce171d328e457",
        display_name="Qwen3-VL 8B (OCR)",
        download_size_bytes=5_777_000_000,
        # NOTE (#4560): 16 GB is the floor for LOADING this model, not for
        # using it as a VLM. Measured on a 16 GB M1: text prompts answered in
        # ~56s, but a single-page vision prefill drove swap to 24 GB of 25 GB
        # and had not produced a token after ten minutes. Raising the floor to
        # 24 GB would be the honest gate, and would also drop the flagship
        # model off every 16 GB Mac -- a product call for Daniel, not a
        # silent change here. Left at 16 GB pending that ruling; the note
        # below tells the user what the floor cannot.
        min_memory_bytes=16 * 1024**3,
        memory_class="needs 16 GB unified memory",
        capabilities=("text", "vision"),
        note="Strongest OCR here, but its VISION path needs 24 GB+ in practice: on a 16 GB Mac a single page drove swap to 24 GB and produced no text in ten minutes. Text prompts work at 16 GB.",
        tested_status="verified",
    ),
    "Chandra-OCR": ManagedModelSpec(
        model_id="Chandra-OCR",
        # mlx-community's own 4-bit conversion, not a one-off personal 8-bit
        # repo (#4560): same model, 5.8 GB instead of 8.2 GB, and it comes from
        # the org whose conversions the rest of this catalog already trusts.
        repo_id="mlx-community/chandra-4bit",
        revision="64c678e4b2c4083a2c738292e6a10107cb7f6b04",
        display_name="Chandra OCR",
        download_size_bytes=5_777_000_000,
        min_memory_bytes=16 * 1024**3,
        memory_class="needs 16 GB unified memory",
        capabilities=("text", "vision"),
        note="Purpose-built document OCR (layout, tables, handwriting) rather than a general VLM. Not yet run inside Fichero -- untested here.",
    ),
    "Nanonets-OCR": ManagedModelSpec(
        model_id="Nanonets-OCR",
        repo_id="mlx-community/Nanonets-OCR-s-4bit",
        revision="b02d1c6c18c7c31ad0ea0bf139f80b9bcf756218",
        display_name="Nanonets OCR-s",
        # Measured, not the model's nominal size: this repo ships a sharded
        # weight set (5.6 GB) AND a second single-file copy (3.1 GB), and a
        # snapshot download fetches both. The number here is what the disk
        # actually loses; the note says why it is larger than the model.
        download_size_bytes=8_727_000_000,
        min_memory_bytes=8 * 1024**3,
        memory_class="needs 8 GB unified memory",
        capabilities=("text", "vision"),
        note="Purpose-built OCR that emits structured markdown (tables, checkboxes, LaTeX). Untested here, and the upstream repo carries two overlapping weight sets, so the download is ~8.7 GB for a ~5.6 GB model.",
    ),
    # --- Text ---------------------------------------------------------------
    "Qwen3-4B-Instruct": ManagedModelSpec(
        model_id="Qwen3-4B-Instruct",
        repo_id="mlx-community/Qwen3-4B-Instruct-2507-4bit",
        revision="50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b",
        display_name="Qwen3 4B Instruct",
        download_size_bytes=2_279_000_000,
        min_memory_bytes=8 * 1024**3,
        memory_class="needs 8 GB unified memory",
        capabilities=("text",),
        note="General text work on-device -- summarise, extract, rewrite -- without sending a document anywhere. Untested here.",
    ),
    "Llama-3.2-3B-Instruct": ManagedModelSpec(
        model_id="Llama-3.2-3B-Instruct",
        repo_id="mlx-community/Llama-3.2-3B-Instruct-4bit",
        revision="7f0dc925e0d0afb0322d96f9255cfddf2ba5636e",
        display_name="Llama 3.2 3B Instruct",
        download_size_bytes=1_825_000_000,
        min_memory_bytes=8 * 1024**3,
        memory_class="needs 8 GB unified memory",
        capabilities=("text",),
        note="The smallest useful text model here at 1.8 GB. Good for short summaries and metadata on machines with no room to spare. Untested here.",
    ),
}

_DEFAULT_PYTHON_DOWNLOAD = """
from huggingface_hub import snapshot_download
import os, sys
repo_id, revision, models_path = sys.argv[1], sys.argv[2], sys.argv[3]
snapshot_download(repo_id=repo_id, revision=revision, cache_dir=models_path)
"""


class MLXModelStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or mlx_model_store_dir()
        self.cache_dir = self.root / "hub"
        self._jobs: dict[str, ManagedModelDownloadJob] = {}
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._job_processes: dict[str, asyncio.subprocess.Process] = {}
        self._model_jobs: dict[str, str] = {}

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HF_HOME"] = str(self.root)
        env["HUGGINGFACE_HUB_CACHE"] = str(self.cache_dir)
        return env

    def list_catalog_entries(self) -> list[Any]:
        from fichero_server.llm.local_inference import (
            LocalModelCatalogEntry,
            LocalModelSource,
            check_local_model_hardware,
        )

        entries: list[LocalModelCatalogEntry] = []
        seen_repo_ids: set[str] = set()
        for spec in MANAGED_MLX_MODELS.values():
            snapshot = self.snapshot_path(spec)
            installed = snapshot.exists()
            supported, unsupported_reason = check_local_model_hardware(
                display_name=spec.display_name,
                min_memory_bytes=spec.min_memory_bytes,
            )
            entries.append(
                LocalModelCatalogEntry(
                    provider_type=ProviderType.omlx,
                    model_id=spec.model_id,
                    display_name=spec.display_name,
                    capabilities=list(spec.capabilities),
                    installed=installed,
                    download_size_bytes=spec.download_size_bytes,
                    disk_usage_bytes=self._disk_usage_bytes(snapshot),
                    min_memory_bytes=spec.min_memory_bytes,
                    memory_class=spec.memory_class,
                    supported=supported,
                    unsupported_reason=unsupported_reason,
                    note=spec.note,
                    tested_status=spec.tested_status,
                    license_label="user-managed",
                    source=LocalModelSource.app_cache if installed else LocalModelSource.remote_catalog,
                )
            )
            seen_repo_ids.add(spec.repo_id)
        for repo_id in self._scan_cached_repo_ids():
            if repo_id in seen_repo_ids:
                continue
            snapshot = self._latest_snapshot_for_repo(repo_id)
            if snapshot is None:
                continue
            supported, unsupported_reason = check_local_model_hardware(
                display_name=repo_id.split("/")[-1],
                min_memory_bytes=None,
            )
            entries.append(
                LocalModelCatalogEntry(
                    provider_type=ProviderType.omlx,
                    model_id=repo_id,
                    display_name=repo_id.split("/")[-1],
                    capabilities=["text", "vision"],
                    installed=True,
                    download_size_bytes=None,
                    disk_usage_bytes=self._disk_usage_bytes(snapshot),
                    min_memory_bytes=None,
                    memory_class=None,
                    supported=supported,
                    unsupported_reason=unsupported_reason,
                    note="Found in your model store, not from the Fichero catalog: capabilities and memory needs are unknown.",
                    tested_status="untested",
                    license_label="user-configured",
                    source=LocalModelSource.user_configured,
                )
            )
        return entries

    async def start_download(self, model_id: str) -> ManagedModelDownloadJob:
        spec = self.spec(model_id)
        self.require_supported(spec)
        existing_id = self._model_jobs.get(model_id)
        if existing_id is not None:
            existing = self._jobs[existing_id]
            if existing.state in {"queued", "running"}:
                return existing
        if self.snapshot_path(spec).exists():
            job = ManagedModelDownloadJob(
                job_id=f"mlx-{len(self._jobs) + 1}",
                model_id=model_id,
                state="completed",
                current=3,
                total=3,
                message="Model already installed",
            )
            self._jobs[job.job_id] = job
            return job
        job = ManagedModelDownloadJob(
            job_id=f"mlx-{len(self._jobs) + 1}",
            model_id=model_id,
            state="queued",
            current=0,
            total=3,
            message="Queued download",
        )
        self._jobs[job.job_id] = job
        self._model_jobs[model_id] = job.job_id
        self._job_tasks[job.job_id] = asyncio.create_task(self._run_download(job, spec))
        return job

    def job(self, job_id: str) -> ManagedModelDownloadJob | None:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> ManagedModelDownloadJob:
        job = self._jobs[job_id]
        process = self._job_processes.get(job_id)
        if process is not None and process.returncode is None:
            process.terminate()
        task = self._job_tasks.get(job_id)
        if task is not None:
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        job.state = "cancelled"
        job.message = "Download cancelled"
        return job

    def delete(self, model_id: str) -> int:
        spec = self.spec(model_id)
        snapshot = self.snapshot_path(spec).resolve()
        if snapshot.name != spec.revision:
            raise ValueError(f"Refusing to delete unexpected path: {snapshot}")
        if not snapshot.exists():
            return 0
        if self.cache_dir.resolve() not in snapshot.parents:
            raise ValueError(f"Refusing to delete outside model store: {snapshot}")
        freed = self._disk_usage_bytes(snapshot)
        shutil.rmtree(snapshot)
        return freed

    def resolve_model_path(self, model_id: str) -> str:
        spec = self.spec(model_id)
        snapshot = self.snapshot_path(spec)
        if snapshot.exists():
            return str(snapshot)
        raise FileNotFoundError(
            f"Local model {model_id} is not installed. Download it from /api/local-inference/models/{model_id}/download before starting oMLX."
        )

    def spec(self, model_id: str) -> ManagedModelSpec:
        if model_id not in MANAGED_MLX_MODELS:
            raise KeyError(f"Unknown managed MLX model: {model_id}")
        return MANAGED_MLX_MODELS[model_id]

    def require_supported(self, spec: ManagedModelSpec) -> None:
        from fichero_server.llm.local_inference import LocalModelHardwareError, check_local_model_hardware

        supported, unsupported_reason = check_local_model_hardware(
            display_name=spec.display_name,
            min_memory_bytes=spec.min_memory_bytes,
        )
        if not supported:
            raise LocalModelHardwareError(unsupported_reason or f"{spec.display_name} is unsupported on this Mac")

    def snapshot_path(self, spec: ManagedModelSpec) -> Path:
        return self.cache_dir / f"models--{spec.repo_id.replace('/', '--')}" / "snapshots" / spec.revision

    async def _run_download(self, job: ManagedModelDownloadJob, spec: ManagedModelSpec) -> None:
        job.state = "running"
        job.current = 1
        job.message = "Resolving MLX runtime"
        python_path = str(get_mlx_runtime().require_python_path())
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        job.current = 2
        job.message = f"Downloading {spec.display_name}"
        process = await asyncio.create_subprocess_exec(
            python_path,
            "-c",
            _DEFAULT_PYTHON_DOWNLOAD,
            spec.repo_id,
            spec.revision,
            str(self.cache_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env(),
        )
        self._job_processes[job.job_id] = process
        stdout, stderr = await process.communicate()
        self._job_processes.pop(job.job_id, None)
        if process.returncode != 0:
            job.state = "failed"
            excerpt = (stderr or stdout).decode("utf-8", errors="replace").strip()
            job.error = excerpt or f"download exited {process.returncode}"
            job.message = "Download failed"
            return
        job.current = 3
        job.state = "completed"
        job.message = "Download complete"

    def _scan_cached_repo_ids(self) -> list[str]:
        if not self.cache_dir.exists():
            return []
        repo_ids: list[str] = []
        for path in self.cache_dir.glob("models--*"):
            if not path.is_dir():
                continue
            repo_ids.append(path.name.removeprefix("models--").replace("--", "/"))
        return repo_ids

    def _latest_snapshot_for_repo(self, repo_id: str) -> Path | None:
        snapshots = self.cache_dir / f"models--{repo_id.replace('/', '--')}" / "snapshots"
        if not snapshots.exists():
            return None
        dirs = [path for path in snapshots.iterdir() if path.is_dir()]
        if not dirs:
            return None
        return sorted(dirs)[-1]

    @staticmethod
    def _disk_usage_bytes(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


_STORE: MLXModelStore | None = None


def mlx_model_store_dir(home: Path | None = None) -> Path:
    return (server_state_dir(home) / "models" / "mlx").expanduser()


def get_mlx_model_store() -> MLXModelStore:
    global _STORE
    root = mlx_model_store_dir()
    if _STORE is None or _STORE.root != root:
        _STORE = MLXModelStore(root)
    return _STORE


__all__ = [
    "MLXModelStore",
    "MANAGED_MLX_MODELS",
    "ManagedModelDownloadJob",
    "ManagedModelSpec",
    "get_mlx_model_store",
    "mlx_model_store_dir",
]
