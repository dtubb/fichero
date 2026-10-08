"""Managed MLX model store for local inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import re
from pathlib import Path
import shutil
from typing import Any

from fichero_server.llm.mlx_runtime import get_mlx_runtime
from fichero_server.db.paths import model_store_root
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
    #: Files to leave on the Hub. A snapshot download takes EVERY file in the
    #: repo, and mlx's loader then globs every ``*.safetensors`` it finds, so a
    #: repo that ships two overlapping weight sets costs double the disk and
    #: hands the loader a mixture. Empty for a clean repo; see Nanonets below
    #: for the one that is not.
    ignore_patterns: tuple[str, ...] = ()
    #: Unified memory this Mac needs for the model to READ A PAGE (its vision path), when that is
    #: more than `min_memory_bytes`, the floor for loading it. None: the load floor is enough, or
    #: nothing more is known. Only a measurement or the model's own note sets it (#5520).
    page_memory_bytes: int | None = None


#: How often a running download's bytes on disk are re-counted for its progress (#5523).
DOWNLOAD_PROGRESS_POLL_SECONDS = 1.0


def _format_bytes(count: int) -> str:
    return f"{count / 1e9:.1f} GB" if count >= 1e8 else f"{count / 1e6:.0f} MB"


@dataclass
class ManagedModelDownloadJob:
    """A model download's progress. ``current`` and ``total`` are BYTES (#5523): they were three
    steps, so a download of any length sat at step 2 of 3 -- 66.7% -- from its first byte to its
    last."""

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
        # The measurement in the note above (#4560), as a fact the defaults and the Start plan read
        # (#5520): never chosen to read pages on a Mac under 24 GB.
        page_memory_bytes=24 * 1024**3,
    ),
    "Qwen2.5-VL-7B": ManagedModelSpec(
        model_id="Qwen2.5-VL-7B",
        # The reader and corrector the recipe rules pin (`recipes/seed/cards.yaml`), so a recipe step
        # naming it can be installed and served here rather than refused as unknown (#5496).
        # Revision and size read from the Hub's API for this exact commit, 2026-10-06.
        repo_id="mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        revision="fdcc572e8b05ba9daeaf71be8c9e4267c826ff9b",
        display_name="Qwen2.5-VL 7B (OCR)",
        download_size_bytes=5_653_000_000,
        min_memory_bytes=16 * 1024**3,
        memory_class="needs 16 GB unified memory",
        capabilities=("text", "vision"),
        note="The recipe rules' default corrector and page reader. Not yet run inside Fichero -- untested here.",
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
        # This repo ships TWO complete weight sets: a sharded pair (5.6 GB,
        # the one `model.safetensors.index.json` points at) and a single
        # `model.safetensors` (3.1 GB). A plain snapshot takes both -- 8.7 GB
        # of disk -- and mlx's loader globs every *.safetensors in the folder,
        # so it would then load a MIXTURE of the two.
        #
        # The single file is the set this repo's own config describes. Read
        # from the Hub without downloading either (safetensors header range
        # requests, 2026-09-03): config.json declares
        # `quantization: {bits: 4, group_size: 64}`; the single file carries
        # 253 `.scales`/`.biases` tensors over U32-packed weights and is
        # 3.07 GB, which is the size of the known-good 4-bit conversion of
        # this same 3B architecture (Qwen2.5-VL-3B-Instruct-4bit is 3.09 GB).
        # The sharded set is quantized too but 5.6 GB -- a coarser precision
        # than the config claims. So the shards and their index stay on the
        # Hub, and the download is 3.1 GB of the weights config.json is
        # actually written for. If it turns out not to load, the fix is to
        # invert this list, not to fetch 8.7 GB.
        ignore_patterns=("model-*-of-*.safetensors", "model.safetensors.index.json"),
        download_size_bytes=3_120_000_000,
        min_memory_bytes=8 * 1024**3,
        memory_class="needs 8 GB unified memory",
        capabilities=("text", "vision"),
        note="Purpose-built OCR that emits structured markdown (tables, checkboxes, LaTeX). Untested here.",
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

#: Argv 4 and beyond are glob patterns to skip -- see ManagedModelSpec.
_DEFAULT_PYTHON_DOWNLOAD = """
from huggingface_hub import snapshot_download
import os, sys
repo_id, revision, models_path = sys.argv[1], sys.argv[2], sys.argv[3]
ignore_patterns = sys.argv[4:] or None
# One line on purpose: the shared-folder guardrail reads per LINE, so a call
# split across lines hides `models_path` from the check that exists to prove
# every download lands under model_store_root()/"models" (#6b).
snapshot_download(repo_id=repo_id, revision=revision, cache_dir=models_path, ignore_patterns=ignore_patterns)
"""


#: Models Fichero trained (#5398): `fichero-trained/<name>`, kept in the store's own Hub-cache layout
#: (revision `trained`) so they resolve and load like any downloaded model, each with its card.
TRAINED_ORG = "fichero-trained"
#: A Hub repository id, `owner/name`: the only names the store looks up as folders of its own.
_REPO_ID = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")
TRAINED_REVISION = "trained"
TRAINED_CARD = "fichero-card.json"


def run_model_choice(provider: str | None, model: str | None) -> tuple[str | None, str | None]:
    """A run's provider/model choice with a trained model's id kept whole (#5567).

    A trained model's id has a slash in it (`fichero-trained/<name>`), so a client that splits
    `--model fichero-trained/<name>` on its first slash sends provider `fichero-trained`, which no
    provider is. The id the app shows is accepted as it is: the provider is the local MLX server
    (`omlx`) and the model the whole id. Any other choice is returned unchanged.
    """
    provider_text = (provider or "").strip()
    model_text = (model or "").strip()
    if provider_text == TRAINED_ORG and model_text:
        return "omlx", f"{TRAINED_ORG}/{model_text}"
    if not provider_text and model_text.startswith(f"{TRAINED_ORG}/"):
        return "omlx", model_text
    return provider, model


def trained_base_spec(card: dict[str, Any]) -> ManagedModelSpec | None:
    """The catalogue model a trained model was trained from, by its card's `base`: the same
    repository, or the catalogue's MLX conversion of it (`Qwen/Qwen2.5-VL-3B-Instruct` is the
    catalogue's `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`). None when the catalogue lacks it."""
    base = str(card.get("base") or "").strip()
    if not base:
        return None
    name = base.rsplit("/", 1)[-1].lower()
    for spec in MANAGED_MLX_MODELS.values():
        repo = spec.repo_id.lower()
        if repo == base.lower() or repo.rsplit("/", 1)[-1] in (name, f"{name}-4bit", f"{name}-8bit", f"{name}-bf16"):
            return spec
    return None


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
            installed = self.is_complete(spec)
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
        # Models Fichero trained: listed with their card, never again as an unknown cached repo.
        for model_id in self.trained_model_ids():
            spec = self.spec(model_id)
            card = self.trained_card(model_id) or {}
            supported, unsupported_reason = check_local_model_hardware(
                display_name=spec.display_name, min_memory_bytes=spec.min_memory_bytes)
            entries.append(
                LocalModelCatalogEntry(
                    provider_type=ProviderType.omlx,
                    model_id=model_id,
                    display_name=spec.display_name,
                    capabilities=list(spec.capabilities),
                    installed=self.is_complete(spec),
                    download_size_bytes=None,
                    disk_usage_bytes=self._disk_usage_bytes(self.trained_dir(model_id)),
                    min_memory_bytes=spec.min_memory_bytes,
                    memory_class=spec.memory_class,
                    supported=supported,
                    unsupported_reason=unsupported_reason,
                    note=spec.note,
                    tested_status="untested",
                    license_label="not for release" if card.get("not_for_release") else "user-managed",
                    source=LocalModelSource.app_cache,
                )
            )
            seen_repo_ids.add(model_id)
        for repo_id in self._scan_cached_repo_ids():
            if repo_id in seen_repo_ids:
                continue
            snapshot = self._latest_snapshot_for_repo(repo_id)
            if snapshot is None:
                continue
            # A model with a readable config says itself whether it reads images (#5519).
            found = self.found_spec(repo_id)
            supported, unsupported_reason = check_local_model_hardware(
                display_name=repo_id.split("/")[-1],
                min_memory_bytes=None,
            )
            entries.append(
                LocalModelCatalogEntry(
                    provider_type=ProviderType.omlx,
                    model_id=repo_id,
                    display_name=repo_id.split("/")[-1],
                    capabilities=list(found.capabilities) if found else ["text", "vision"],
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
        if self.is_complete(spec):
            job = ManagedModelDownloadJob(
                job_id=f"mlx-{len(self._jobs) + 1}",
                model_id=model_id,
                state="completed",
                current=max(spec.download_size_bytes, 1),
                total=max(spec.download_size_bytes, 1),
                message="Model already installed",
            )
            self._jobs[job.job_id] = job
            return job
        job = ManagedModelDownloadJob(
            job_id=f"mlx-{len(self._jobs) + 1}",
            model_id=model_id,
            state="queued",
            current=0,
            total=max(spec.download_size_bytes, 1),
            message="Queued download",
        )
        self._jobs[job.job_id] = job
        self._model_jobs[model_id] = job.job_id
        self._job_tasks[job.job_id] = asyncio.create_task(self._download_then_say(job, spec))
        return job

    async def _download_then_say(self, job: ManagedModelDownloadJob, spec: ManagedModelSpec) -> None:
        """The download, then, once it is complete, the word every window waits for (`model.installed`): a Start
        plan that waited for it reads itself again (`source.onboard.auto.installed-model-first`, #5583)."""
        await self._run_download(job, spec)
        if job.state == "completed":
            from fichero_server.llm.local_models import say_installed

            say_installed("mlx", spec.model_id)

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
        # `is_complete`, not `exists`: handing a partial snapshot to the
        # sidecar produces a loader crash about a missing shard, which reads
        # as a broken model rather than an unfinished download.
        if self.is_complete(spec):
            return str(snapshot)
        raise FileNotFoundError(
            f"Local model {model_id} is not installed. Download it from /api/local-inference/models/{model_id}/download before starting oMLX."
        )

    def canonical_id(self, name: str | None) -> str | None:
        """The store's id for a model a step names by its catalogue id, its Hub repository, or a
        trained model's id; None for any other name (#5520: a recipe pins the repo, the CLI the id).
        A Hub reader the model search found and kept is known too, so it downloads like a catalogue
        model (#5593)."""
        if not name:
            return None
        for model_id, spec in MANAGED_MLX_MODELS.items():
            if name in (model_id, spec.repo_id):
                return model_id
        if self.trained_card(name) is not None or self.found_spec(name) is not None:
            return name
        if self.hub_spec(name) is not None:
            return name
        return None

    @staticmethod
    def hub_spec(repo_id: str) -> ManagedModelSpec | None:
        """A Hub reader the model search found and kept, not yet in this store (`recipes.discovery.hub_spec`)."""
        if not _REPO_ID.match(repo_id or "") or repo_id.startswith(f"{TRAINED_ORG}/"):
            return None
        from fichero_server.recipes.discovery import hub_spec

        return hub_spec(repo_id)

    def spec(self, model_id: str) -> ManagedModelSpec:
        if model_id in MANAGED_MLX_MODELS:
            return MANAGED_MLX_MODELS[model_id]
        card = self.trained_card(model_id)
        if card is None:
            found = self.found_spec(model_id) or self.hub_spec(model_id)
            if found is None:
                raise KeyError(f"Unknown managed MLX model: {model_id}")
            return found
        # A landed model is its base with other weights (#5534): its size is its own weight files,
        # and what it needs to load and read a page is its card's, else its base's. With a size of 0
        # the memory guard thought it needed 1.5 GB, let it start where its 3B base was refused
        # ('needs about 5.0 GB free; this Mac has 4.5 GB'), and it died loading with no reason.
        base = trained_base_spec(card)
        memory = int(card.get("min_memory_bytes") or (base.min_memory_bytes if base else 8 * 1024**3))
        weights = sum(p.stat().st_size for p in self.trained_dir(model_id).glob("*.safetensors"))
        return ManagedModelSpec(
            model_id=model_id, repo_id=model_id, revision=TRAINED_REVISION,
            display_name=str(card.get("display_name") or model_id),
            download_size_bytes=weights or (base.download_size_bytes if base else 0),
            min_memory_bytes=memory, memory_class=f"needs {memory // 1024**3} GB unified memory",
            capabilities=("text", "vision"),
            note=" ".join(filter(None, [str(card.get("summary") or ""),
                                        "Not for release." if card.get("not_for_release") else ""])),
            tested_status="untested",
            page_memory_bytes=card.get("page_memory_bytes") or (base.page_memory_bytes if base else None),
        )

    def found_spec(self, repo_id: str) -> ManagedModelSpec | None:
        """A complete model in this store that the catalogue does not list and Fichero did not train (one
        downloaded by hand or by another tool), as a spec made from its own files (#5519): its config says
        whether it reads images (`vision_config`), its safetensors weights give its size, and the floor to
        load it is that size, nothing more being known until it runs here. None for a name that is not a
        Hub repository in this store, or one with no readable config or no safetensors weights (a GGUF
        repository: this Mac's MLX server cannot load it)."""
        import json

        if (not _REPO_ID.match(repo_id or "") or repo_id.startswith(f"{TRAINED_ORG}/")
                or any(repo_id == spec.repo_id for spec in MANAGED_MLX_MODELS.values())):
            return None
        snapshot = self._latest_snapshot_for_repo(repo_id)
        if snapshot is None:
            return None
        try:
            config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        weights = sum(p.stat().st_size for p in snapshot.glob("*.safetensors"))
        if not isinstance(config, dict) or not weights:
            return None
        return ManagedModelSpec(
            model_id=repo_id, repo_id=repo_id, revision=snapshot.name,
            display_name=repo_id.split("/")[-1], download_size_bytes=weights, min_memory_bytes=weights,
            memory_class=f"needs at least {weights / 1e9:.1f} GB unified memory (its weights)",
            capabilities=("text", "vision") if "vision_config" in config else ("text",),
            note="Found in your model store, not from the Fichero catalogue: its card is made from its own "
                 "config. Not measured here yet.",
        )

    def global_trained_dir(self, model_id: str) -> Path:
        """Where a trained model's MLX weights and card live in this engine's global store."""
        return self.cache_dir / f"models--{model_id.replace('/', '--')}" / "snapshots" / TRAINED_REVISION

    def trained_dir(self, model_id: str) -> Path:
        """Where a trained model's MLX weights and card live: the global store's copy when it has one,
        else its build inside an open project (#5539, `training.project_models`), else the global path."""
        here = self.global_trained_dir(model_id)
        if (here / TRAINED_CARD).is_file() or not model_id.startswith(f"{TRAINED_ORG}/"):
            return here
        from fichero_server.training.project_models import find_mlx_dir

        return find_mlx_dir(model_id) or here

    def trained_card(self, model_id: str) -> dict[str, Any] | None:
        """The card of a model Fichero trained, or None for any other id."""
        if not model_id.startswith(f"{TRAINED_ORG}/"):
            return None
        try:
            import json

            card = json.loads((self.trained_dir(model_id) / TRAINED_CARD).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return card if isinstance(card, dict) else None

    def trained_model_ids(self) -> list[str]:
        from fichero_server.training.project_models import open_project_mlx_ids

        prefix = f"models--{TRAINED_ORG}--"
        found = [f"{TRAINED_ORG}/{p.name[len(prefix):]}" for p in self.cache_dir.glob(f"{prefix}*") if p.is_dir()]
        return sorted(m for m in set(found + open_project_mlx_ids()) if self.trained_card(m) is not None)

    def require_supported(self, spec: ManagedModelSpec) -> None:
        from fichero_server.llm.local_inference import LocalModelHardwareError, check_local_model_hardware

        supported, unsupported_reason = check_local_model_hardware(
            display_name=spec.display_name,
            min_memory_bytes=spec.min_memory_bytes,
        )
        if not supported:
            raise LocalModelHardwareError(unsupported_reason or f"{spec.display_name} is unsupported on this Mac")

    def snapshot_path(self, spec: ManagedModelSpec) -> Path:
        if spec.revision == TRAINED_REVISION and spec.repo_id.startswith(f"{TRAINED_ORG}/"):
            return self.trained_dir(spec.repo_id)  # the global store's copy, or its project's (#5539)
        return self.cache_dir / f"models--{spec.repo_id.replace('/', '--')}" / "snapshots" / spec.revision

    def is_complete(self, spec: ManagedModelSpec) -> bool:
        """Whether this model is DOWNLOADED, not merely started.

        The snapshot directory is created early and fills as blobs land, so
        `snapshot.exists()` is true from the first small file onward. An
        interrupted download therefore looked installed: measured 2026-09-04,
        a Chandra pull killed at 151 MB left a directory of config and
        tokenizer files, and the store answered "Model already installed",
        state=completed, for a model whose 5.6 GB of weights were absent.

        The rule is derived from the FILES PRESENT, deliberately, because two
        other signals look authoritative and are not:

        * ``*.incomplete`` blobs are not evidence of an unfinished model. They
          survive a completed download — the finished Chandra snapshot still
          had two, left by the killed attempt — so testing them called a good
          model broken forever.
        * The repo's own ``model.safetensors.index.json`` is not reliable
          either. mlx-community/Qwen3-VL-8B-Instruct-4bit ships two shards and
          an index naming FOUR, a stale manifest from an earlier layout; mlx
          globs ``*.safetensors`` and never reads it. Trusting it marked a
          working model incomplete.

        What holds: huggingface_hub links a blob into ``snapshots/`` only once
        that blob is whole, so a file's presence there IS the completeness
        signal. A model needs at least one weight file, and a sharded set must
        have every member of its own series — ``model-00001-of-00002`` implies
        ``model-00002-of-00002``, read off the filename rather than a manifest
        that may describe a different release.
        """
        snapshot = self.snapshot_path(spec)
        if not snapshot.exists():
            return False
        weights = [
            path
            for pattern in ("*.safetensors", "*.npz", "*.bin", "*.gguf")
            for path in snapshot.glob(pattern)
        ]
        if not weights:
            return False
        for path in weights:
            match = re.match(r"^(?P<stem>.+)-(?P<index>\d+)-of-(?P<total>\d+)(?P<ext>\..+)$", path.name)
            if not match:
                continue
            total = int(match.group("total"))
            for shard in range(1, total + 1):
                sibling = (
                    f"{match.group('stem')}-{shard:0{len(match.group('index'))}d}"
                    f"-of-{match.group('total')}{match.group('ext')}"
                )
                if not (snapshot / sibling).exists():
                    return False
        return True

    def downloaded_bytes(self, spec: ManagedModelSpec) -> int:
        """Bytes of this model on disk so far: its cache's ``blobs``, finished files and the
        ``.incomplete`` ones being written. Not the snapshot folder -- its files are links to the
        blobs, and counting both would count every byte twice."""
        return self._disk_usage_bytes(self.cache_dir / f"models--{spec.repo_id.replace('/', '--')}" / "blobs")

    def _note_progress(self, job: ManagedModelDownloadJob, spec: ManagedModelSpec) -> None:
        # Capped below the total until the download says it is done: the catalog size is measured,
        # but a byte count that reached it early must not read as finished.
        done = min(self.downloaded_bytes(spec), max(job.total - 1, 0))
        job.current = done
        job.message = (
            f"Downloading {spec.display_name}: {_format_bytes(done)} of {_format_bytes(job.total)}"
        )

    async def _run_download(self, job: ManagedModelDownloadJob, spec: ManagedModelSpec) -> None:
        job.state = "running"
        job.message = "Resolving MLX runtime"
        python_path = str(get_mlx_runtime().require_python_path())
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._note_progress(job, spec)
        process = await asyncio.create_subprocess_exec(
            python_path,
            "-c",
            _DEFAULT_PYTHON_DOWNLOAD,
            spec.repo_id,
            spec.revision,
            str(self.cache_dir),
            *spec.ignore_patterns,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env(),
        )
        self._job_processes[job.job_id] = process
        communicating = asyncio.ensure_future(process.communicate())
        while not communicating.done():
            await asyncio.wait({communicating}, timeout=DOWNLOAD_PROGRESS_POLL_SECONDS)
            if not communicating.done():
                self._note_progress(job, spec)
        stdout, stderr = communicating.result()
        self._job_processes.pop(job.job_id, None)
        if process.returncode != 0:
            job.state = "failed"
            excerpt = (stderr or stdout).decode("utf-8", errors="replace").strip()
            job.error = excerpt or f"download exited {process.returncode}"
            job.message = "Download failed"
            return
        job.current = job.total
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
    return (model_store_root(home) / "models" / "mlx").expanduser()


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
