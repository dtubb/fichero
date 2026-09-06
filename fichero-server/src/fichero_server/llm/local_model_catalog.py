"""Fold spaCy / Kraken / Whisper into the local-inference model catalog.

MLX already speaks ``LocalModelCatalogEntry`` and installs through the
``/api/local-inference/models/{id}/download`` job flow. These three runtimes
did not — each had its own status/install surface — so the UI would need a
bespoke sheet per provider. This builds the SAME entry shape for each and
dispatches installs/deletes to each runtime's own mechanism, so Settings
renders and drives all four local runtimes through one catalog and one
download/progress/delete path (Shape A, agreed with lane-local-ui).

The install mechanisms genuinely differ — a pip model package (spaCy), a whole
venv (Kraken), a snapshot into the MLX runtime (Whisper) — so the dispatcher
translates each into the one ``ManagedModelDownloadJob`` shape the UI already
polls, rather than pretending they are the same underneath.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fichero_server.llm.mlx_model_store import ManagedModelDownloadJob
from fichero_server.llm.providers import ProviderType

#: Kraken is one runtime with one segmentation model (blla), so it is a single
#: catalog entry whose "installed" is whether the venv is provisioned.
KRAKEN_MODEL_ID = "kraken-blla"
#: Smallest working set measured at install time (kraken_runtime docstring).
KRAKEN_DOWNLOAD_SIZE_BYTES = 996_000_000


def _make_entry(**kwargs: Any):
    """Build a LocalModelCatalogEntry (imported lazily to dodge a cycle)."""
    from fichero_server.llm.local_inference import LocalModelCatalogEntry

    return LocalModelCatalogEntry(**kwargs)


def _source(installed: bool):
    from fichero_server.llm.local_inference import LocalModelSource

    return LocalModelSource.app_cache if installed else LocalModelSource.remote_catalog


# =============================================================================
# Catalog entries
# =============================================================================


def spacy_catalog_entries() -> list[Any]:
    from fichero_server.llm.local_models import LocalModelManager

    entries = []
    for row in LocalModelManager().list_spacy_models():
        # The two bundled small models are the only ones actually run here;
        # everything else is on its reputation until someone installs it.
        tested = "verified" if row.model_id in ("es_core_news_sm", "en_core_web_sm") else "untested"
        entries.append(
            _make_entry(
                provider_type=ProviderType.spacy,
                model_id=row.model_id,
                display_name=row.display_name,
                capabilities=["nlp"],
                installed=row.is_downloaded,
                download_size_bytes=row.expected_size_mb * 1_000_000,
                # A pip package, not a folder in our store — disk use is not
                # ours to measure, so it stays 0 rather than a guess.
                disk_usage_bytes=0,
                min_memory_bytes=None,
                memory_class=None,
                supported=row.available,
                unsupported_reason=row.unavailable_reason,
                note=row.note,
                tested_status=tested,
                license_label="user-managed",
                source=_source(row.is_downloaded),
            )
        )
    return entries


def kraken_catalog_entries() -> list[Any]:
    from fichero_server.llm.kraken_runtime import get_kraken_runtime

    status = get_kraken_runtime().status()
    installed = bool(status.get("installed"))
    return [
        _make_entry(
            provider_type=ProviderType.kraken,
            model_id=KRAKEN_MODEL_ID,
            display_name="Kraken line segmenter (blla)",
            capabilities=["segmentation"],
            installed=installed,
            download_size_bytes=KRAKEN_DOWNLOAD_SIZE_BYTES,
            disk_usage_bytes=int(status.get("disk_usage_bytes", 0)),
            min_memory_bytes=None,
            memory_class=None,
            # Kraken runs in its own subprocess venv; there is no host gate the
            # way audio/MLX has one, so it is always installable.
            supported=True,
            unsupported_reason=None,
            note=(
                "Finds line polygons and baselines on historical hands where "
                "Apple Vision localises badly. ~1 GB, never installed "
                "automatically. Verified on 17th-century secretary hand."
            ),
            tested_status="verified",
            license_label="user-managed",
            source=_source(installed),
        )
    ]


def whisper_catalog_entries() -> list[Any]:
    from fichero_server.llm.local_models import LocalModelManager

    entries = []
    for row in LocalModelManager().list_whisper_models():
        entries.append(
            _make_entry(
                provider_type=ProviderType.whisper,
                model_id=row.model_id,
                display_name=row.display_name,
                capabilities=["audio"],
                installed=row.is_downloaded,
                download_size_bytes=row.expected_size_mb * 1_000_000,
                disk_usage_bytes=row.size_bytes,
                min_memory_bytes=None,
                memory_class=None,
                # A downloaded model stays actionable (deletable) even when the
                # transcriber runtime is missing — mirrors list_whisper_models.
                supported=row.available,
                unsupported_reason=row.unavailable_reason,
                note=row.note,
                tested_status="untested",
                license_label="user-managed",
                source=_source(row.is_downloaded),
            )
        )
    return entries


def catalog_entries() -> list[Any]:
    """Every non-MLX local model as a LocalModelCatalogEntry."""
    return spacy_catalog_entries() + kraken_catalog_entries() + whisper_catalog_entries()


def owns(model_id: str) -> bool:
    """Whether this coordinator (not the MLX store) installs ``model_id``."""
    from fichero_server.llm.local_models import SPACY_MODELS
    from fichero_server.llm.whisper_runtime import WHISPER_MLX_MODELS

    return (
        model_id in SPACY_MODELS
        or model_id == KRAKEN_MODEL_ID
        or model_id in WHISPER_MLX_MODELS
    )


# =============================================================================
# Install / delete dispatch — one ManagedModelDownloadJob shape for all three
# =============================================================================


class LocalModelInstallCoordinator:
    """Owns spaCy/Whisper install jobs; delegates Kraken to its own manager."""

    def __init__(self) -> None:
        self._jobs: dict[str, ManagedModelDownloadJob] = {}
        self._model_jobs: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def wait_for_job(self, job_id: str) -> None:
        """Await a spaCy/Whisper install task (Kraken is awaited on its own)."""
        task = self._tasks.get(job_id)
        if task is not None:
            await task

    async def start_install(self, model_id: str) -> ManagedModelDownloadJob:
        from fichero_server.llm.local_models import SPACY_MODELS
        from fichero_server.llm.whisper_runtime import WHISPER_MLX_MODELS

        if model_id == KRAKEN_MODEL_ID:
            return await self._start_kraken()
        if model_id in SPACY_MODELS:
            return await self._start_thread_install(
                model_id, "spacy", self._install_spacy
            )
        if model_id in WHISPER_MLX_MODELS:
            # Refuse up front (like the MLX hardware gate) rather than queue a
            # snapshot the runtime cannot load — the endpoint turns this into a
            # 409, not a job that fails where no one looks.
            from fichero_server.llm.whisper_runtime import audio_runtime_status

            runtime = audio_runtime_status()
            if not runtime["ready"]:
                raise RuntimeError(str(runtime["reason"]))
            return await self._start_thread_install(
                model_id, "whisper", self._install_whisper
            )
        raise KeyError(f"No local runtime installs model: {model_id}")

    async def _start_kraken(self) -> ManagedModelDownloadJob:
        from fichero_server.llm.kraken_runtime import get_kraken_runtime

        await get_kraken_runtime().start_install()
        return self._kraken_job()

    def _kraken_job(self) -> ManagedModelDownloadJob:
        from fichero_server.llm.kraken_runtime import get_kraken_runtime

        raw = get_kraken_runtime().status().get("job")
        if raw is None:
            # Already installed, or never started — report a terminal job so the
            # UI's poll resolves instead of hanging on a missing job.
            from fichero_server.llm.kraken_runtime import is_installed

            done = is_installed()
            return ManagedModelDownloadJob(
                job_id=f"kraken:{KRAKEN_MODEL_ID}",
                model_id=KRAKEN_MODEL_ID,
                state="completed" if done else "idle",
                current=1 if done else 0,
                total=1,
                message="Kraken already installed" if done else "Not started",
            )
        return ManagedModelDownloadJob(
            job_id=f"kraken:{raw['job_id']}",
            model_id=KRAKEN_MODEL_ID,
            state=raw["state"],
            current=int(raw["current"]),
            total=int(raw["total"]),
            message=raw["message"],
            error=raw.get("error"),
        )

    async def _start_thread_install(self, model_id, prefix, worker) -> ManagedModelDownloadJob:
        async with self._lock:
            existing_id = self._model_jobs.get(model_id)
            if existing_id is not None:
                existing = self._jobs[existing_id]
                if existing.state in {"queued", "running"}:
                    return existing
            job = ManagedModelDownloadJob(
                job_id=f"{prefix}:{model_id}:{len(self._jobs) + 1}",
                model_id=model_id,
                state="running",
                current=1,
                total=2,
                message=f"Installing {model_id}",
            )
            self._jobs[job.job_id] = job
            self._model_jobs[model_id] = job.job_id
        self._tasks[job.job_id] = asyncio.create_task(self._run(job, worker))
        return job

    async def _run(self, job: ManagedModelDownloadJob, worker) -> None:
        try:
            await asyncio.to_thread(worker, job.model_id)
            job.current = 2
            job.state = "completed"
            job.message = "Install complete"
        except Exception as exc:  # noqa: BLE001 — surfaced on the job
            job.state = "failed"
            job.error = str(exc)
            job.message = "Install failed"

    @staticmethod
    def _install_spacy(model_id: str) -> None:
        from fichero_server.llm.local_models import LocalModelManager

        LocalModelManager().download_spacy_model(model_id)

    @staticmethod
    def _install_whisper(model_id: str) -> None:
        # Refuse rather than queue work that cannot run: without a transcriber
        # the snapshot lands but nothing can load it.
        from fichero_server.llm.local_models import LocalModelManager
        from fichero_server.llm.whisper_runtime import audio_runtime_status

        runtime = audio_runtime_status()
        if not runtime["ready"]:
            raise RuntimeError(str(runtime["reason"]))
        LocalModelManager().download_whisper_model(model_id)

    def job(self, job_id: str) -> ManagedModelDownloadJob | None:
        if job_id.startswith("kraken:"):
            return self._kraken_job()
        return self._jobs.get(job_id)

    def delete(self, model_id: str) -> int:
        from fichero_server.llm.local_models import LocalModelManager
        from fichero_server.llm.whisper_runtime import WHISPER_MLX_MODELS

        if model_id == KRAKEN_MODEL_ID:
            from fichero_server.llm.kraken_runtime import get_kraken_runtime

            get_kraken_runtime().remove()
            return 0
        if model_id in WHISPER_MLX_MODELS:
            return LocalModelManager().delete_whisper_model(model_id)
        # spaCy models are pip packages — delete raises, honestly.
        return LocalModelManager().delete_spacy_model(model_id)


_COORDINATOR: LocalModelInstallCoordinator | None = None


def get_local_model_coordinator() -> LocalModelInstallCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = LocalModelInstallCoordinator()
    return _COORDINATOR


__all__ = [
    "KRAKEN_MODEL_ID",
    "KRAKEN_DOWNLOAD_SIZE_BYTES",
    "LocalModelInstallCoordinator",
    "catalog_entries",
    "get_local_model_coordinator",
    "kraken_catalog_entries",
    "owns",
    "spacy_catalog_entries",
    "whisper_catalog_entries",
]
