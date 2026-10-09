"""
Unified Local Model Management

Manages locally-downloaded AI models for Whisper, FastEmbed, and spaCy.
Models are stored in ~/Library/Application Support/Fichero/models/
to avoid macOS auto-cleanup of ~/.cache/ directories.

Storage layout:
    models/
    ├── whisper/        # OpenAI Whisper model weights (.pt files)
    ├── embeddings/     # FastEmbed ONNX models (subdirectories)
    └── spacy/          # Future spaCy models

Models are app-wide (shared across all .fichero libraries).
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from fichero_server.db.embeddings import (
    BGE_M3_MODEL,
    DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL,
    SUPPORTED_EMBEDDING_SPACES,
)
from fichero_server.db.paths import model_store_root
from fichero_server.llm.whisper_runtime import (
    WHISPER_MLX_MODELS,
    audio_runtime_status,
    delete_whisper_model as _delete_whisper_snapshot,
    download_state,
    download_whisper_model as _download_whisper_snapshot,
    installed_bytes as _whisper_installed_bytes,
    snapshot_path as _whisper_snapshot_path,
    total_disk_usage_bytes as _whisper_total_bytes,
)

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    WHISPER = "whisper"
    EMBEDDINGS = "embeddings"
    SPACY = "spacy"


# Stable storage location (not ~/.cache which gets auto-cleaned by macOS)
MODELS_BASE = model_store_root() / "models"


# =============================================================================
# Model Catalogs
# =============================================================================

#: Derived from the ONE Whisper catalog (``whisper_runtime``), which owns the
#: repos, revisions, measured sizes and the one-line "why" for each model. This
#: mapping stays only because callers and tests read it by name; it is no
#: longer a second, drifting source of truth.
WHISPER_MODELS: dict[str, dict] = {
    model_id: {
        "params": model_spec.params,
        "disk_mb": round(model_spec.download_size_bytes / 1_000_000),
        "speed": model_spec.speed,
        "repo_id": model_spec.repo_id,
        "note": model_spec.note,
        "runtime": "mlx-whisper",
    }
    for model_id, model_spec in WHISPER_MLX_MODELS.items()
}


# =============================================================================
# spaCy models (#4671)
# =============================================================================
#
# The SVO grammar gate reads a page's part-of-speech and morphology to convict
# rows the model got wrong — a "verb" that is a proper noun, a first-person
# verb stamped with a bystander's name. Measured on a real Caciques page it
# refused 16 of 17 bad rows, and Apple's on-device NLTagger cannot replace it
# (no morphology for Spanish at all).
#
# `ModelType.SPACY` and a reserved directory have been here since this module
# was written, marked "future". This is that future: the models are real rows
# now, with honest installed-state, so Settings can show what is present and
# what a page's language would need.
#
# UNLIKE Whisper and FastEmbed, spaCy models are pip PACKAGES, not files we
# place in `MODELS_BASE`. So installed-state is asked of the runtime rather
# than measured off disk, and there is no directory of ours to delete.

# The catalog the "Add Models" picker reads. Each row is a real spaCy pipeline
# package the grammar gate can load once installed, with its measured wheel
# size and the one-line "why". The two SMALL models ship in the bundle (see
# pyproject `es_core_news_sm`/`en_core_web_sm`), so they report installed on
# first launch; everything else is an addable download. `sm`/`md`/`lg` are the
# same pipeline at three sizes: `md`/`lg` add word vectors the SVO gate itself
# does not read, so they are offered for the user to TEST, not asserted better.
SPACY_MODELS: dict[str, dict] = {
    "es_core_news_sm": {
        "language": "es",
        "disk_mb": 16,
        "note": "Spanish — the SVO grammar gate. Small is enough: the gate "
                "reads part-of-speech and person, not word vectors. Ships in "
                "the app.",
    },
    "es_core_news_md": {
        "language": "es",
        "disk_mb": 45,
        "note": "Spanish, medium. Same tagger as small plus word vectors; when "
                "installed the gate prefers it over small. Whether it reads your "
                "material better than small is UNMEASURED — add it to test.",
    },
    "es_core_news_lg": {
        "language": "es",
        "disk_mb": 568,
        "note": "Spanish, large. Carries word vectors this gate does not use, "
                "and whether they help on your material is UNMEASURED — "
                "install it to test that, not on the assumption it is better.",
    },
    "en_core_web_sm": {
        "language": "en",
        "disk_mb": 15,
        "note": "English — the same gate, for English-language material. Ships "
                "in the app.",
    },
    "en_core_web_md": {
        "language": "en",
        "disk_mb": 44,
        "note": "English, medium. Same tagger as small plus word vectors; when "
                "installed the gate prefers it over small.",
    },
    "en_core_web_lg": {
        "language": "en",
        "disk_mb": 400,
        "note": "English, large. Word vectors the gate does not read — add it "
                "only to measure whether they help your material.",
    },
    "fr_core_news_sm": {
        "language": "fr",
        "disk_mb": 16,
        "note": "French — part-of-speech and named entities for "
                "French-language material.",
    },
    "de_core_news_sm": {
        "language": "de",
        "disk_mb": 15,
        "note": "German — part-of-speech and named entities for "
                "German-language material.",
    },
    "pt_core_news_sm": {
        "language": "pt",
        "disk_mb": 16,
        "note": "Portuguese — part-of-speech and named entities for "
                "Portuguese-language material.",
    },
}


#: The version of every pipeline Fichero downloads: the one built for the spaCy this engine bundles (3.8).
SPACY_PIPELINE_VERSION = "3.8.0"


def SPACY_RELEASE_URL(name: str, version: str) -> str:  # noqa: N802 -- a constant in spirit; a test points it at a file
    """Where a spaCy pipeline's release archive lives (spaCy's own model releases)."""
    return (f"https://github.com/explosion/spacy-models/releases/download/{name}-{version}/"
            f"{name}-{version}-py3-none-any.whl")


#: What never belongs in a pipeline's data folder (`runtime.spacy.pipelines-download-as-data`).
_CODE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll", ".pth", ".sh", ".exe")


def spacy_pipeline_path(name: str) -> Path | None:
    """The pipeline's data folder in the model store, when it has been downloaded."""
    folder = MODELS_BASE / "spacy" / f"{name}-{SPACY_PIPELINE_VERSION}"
    return folder if (folder / "config.cfg").is_file() else None


def _dir_bytes(folder: Path) -> int:
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())  # one model folder


def download_spacy_pipeline(name: str) -> Path:
    """Fetch the pipeline's release archive and write ONLY its data folder (config, meta, weights) into the store.
    Never installs the package or runs any of its code. Refuses, writing nothing, an archive whose data folder
    holds code or a link, or a member that would land outside it."""
    import shutil
    import stat
    import tempfile
    import urllib.request
    import zipfile

    from fichero_server.core.tls import https_context

    if name not in SPACY_MODELS:
        raise ValueError(f"Unknown spaCy model: {name}")
    version = SPACY_PIPELINE_VERSION
    target = MODELS_BASE / "spacy" / f"{name}-{version}"
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{name}/{name}-{version}/"
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        archive = Path(tmp) / "release.whl"
        with urllib.request.urlopen(SPACY_RELEASE_URL(name, version), timeout=60, context=https_context()) as response, \
                open(archive, "wb") as out:
            shutil.copyfileobj(response, out)
        with zipfile.ZipFile(archive) as z:
            members = [m for m in z.infolist() if m.filename.startswith(prefix) and m.filename != prefix]
            if not members:
                raise RuntimeError(f"refused: the archive for {name} has no data folder {prefix!r}")
            staged = Path(tmp) / "data"
            for m in members:
                rel = m.filename[len(prefix):]
                parts = Path(rel).parts
                if rel.startswith("/") or ".." in parts:
                    raise RuntimeError(f"refused: {m.filename!r} would land outside the data folder")
                if stat.S_ISLNK(m.external_attr >> 16) or rel.lower().endswith(_CODE_SUFFIXES):
                    raise RuntimeError(f"refused: the data folder holds code or a link ({m.filename!r})")
            for m in members:
                if not m.is_dir():
                    dest = staged / m.filename[len(prefix):]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(m))
        meta = json.loads((staged / "meta.json").read_text()) if (staged / "meta.json").is_file() else {}
        if not (staged / "config.cfg").is_file() or f"{meta.get('lang')}_{meta.get('name')}" != name:
            raise RuntimeError(f"refused: the data folder is not the pipeline {name} (no config, or meta names "
                               f"{meta.get('lang')}_{meta.get('name')})")
        if target.exists():
            shutil.rmtree(target)
        staged.rename(target)
    return target


class BundledModel(RuntimeError):
    """A model that ships inside the app: there is nothing a delete could remove."""


def spacy_pipeline_available(name: str) -> bool:
    """In the model store, or bundled with the app."""
    return spacy_pipeline_path(name) is not None or name in _spacy_installed_models()


def _spacy_installed_models() -> set[str]:
    """Which spaCy models this interpreter can actually load."""
    try:
        import spacy.util

        return set(spacy.util.get_installed_models())
    except Exception:  # noqa: BLE001 — spaCy is an optional extra
        return set()


def _spacy_runtime_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("spacy") is not None


def _embedding_metadata(
    *,
    dimensions: int,
    disk_mb: int,
    ram_mb: int,
    languages: str,
    description: str,
    quality: str,
    speed: str,
    activation_note: str,
) -> dict:
    """Build catalog metadata without implying every model is a search space."""
    return {
        "dimensions": dimensions,
        "disk_mb": disk_mb,
        "ram_mb": ram_mb,
        "languages": languages,
        "description": description,
        "quality": quality,
        "speed": speed,
        "is_current_default": False,
        "is_supported_embedding_space": False,
        "requires_explicit_migration": True,
        "activation_note": activation_note,
        "embedding_space_status": "download_only",
    }


EMBEDDINGS_MODELS: dict[str, dict] = {
    BGE_M3_MODEL: _embedding_metadata(
        dimensions=1024,
        disk_mb=2300,
        ram_mb=2300,
        languages="100+ languages",
        description="Large multilingual retrieval model",
        quality="High multilingual retrieval quality; comparable footprint to the current default.",
        speed="Slower startup and inference than small English models.",
        activation_note="Supported only as an explicit embedding-space opt-in; existing vectors must be deliberately re-embedded before mixed-space search is allowed.",
    ),
    DEFAULT_EMBEDDING_MODEL: _embedding_metadata(
        dimensions=1024,
        disk_mb=2200,
        ram_mb=2200,
        languages="100+ languages",
        description="Current pinned multilingual E5 retrieval model",
        quality="Highest-quality current Fichero default for multilingual corpora.",
        speed="Highest RAM use and slowest startup among listed embedding choices.",
        activation_note="Active default embedding space. Keeping this preserves compatibility with existing indexed vectors.",
    ),
    "intfloat/multilingual-e5-base": {
        "dimensions": 768,
        "disk_mb": 1100,
        "ram_mb": 1100,
        "languages": "100+ languages",
        "description": "Mid-size multilingual E5 retrieval model",
        "quality": "Good multilingual quality with lower memory use than e5-large.",
        "speed": "Faster than e5-large; still heavier than English-only small models.",
        "is_current_default": False,
        "is_supported_embedding_space": False,
        "requires_explicit_migration": True,
        "activation_note": "Downloadable local model choice only; not currently wired as an active Fichero search embedding space.",
        "embedding_space_status": "download_only",
    },
    "intfloat/multilingual-e5-small": _embedding_metadata(
        dimensions=384,
        disk_mb=470,
        ram_mb=470,
        languages="100+ languages",
        description="Small multilingual E5 retrieval model",
        quality="Lower multilingual quality than e5-large, but much lighter for memory-constrained use.",
        speed="Fast startup and inference compared with e5-large.",
        activation_note="Downloadable local model choice only; not currently wired as an active Fichero search embedding space.",
    ),
    "BAAI/bge-small-en-v1.5": _embedding_metadata(
        dimensions=384,
        disk_mb=130,
        ram_mb=130,
        languages="English",
        description="Small English retrieval model",
        quality="Strong English retrieval for the footprint; not suitable for multilingual collections.",
        speed="Very fast startup and inference; good low-RAM option for English-primary corpora.",
        activation_note="Downloadable local model choice only; not currently wired as an active Fichero search embedding space.",
    ),
    "all-MiniLM-L6-v2": _embedding_metadata(
        dimensions=384,
        disk_mb=90,
        ram_mb=90,
        languages="English",
        description="Tiny English sentence-transformer model",
        quality="Lowest quality listed; useful only when minimizing disk and RAM matters more than recall.",
        speed="Fastest and smallest listed embedding model.",
        activation_note="Downloadable local model choice only; not currently wired as an active Fichero search embedding space.",
    ),
}

for _model_id, _metadata in EMBEDDINGS_MODELS.items():
    if _model_id == DEFAULT_EMBEDDING_MODEL:
        _metadata["is_current_default"] = True
        _metadata["embedding_space_status"] = "current_default"
        _metadata["requires_explicit_migration"] = False
    if _model_id.lower() in SUPPORTED_EMBEDDING_SPACES:
        _metadata["is_supported_embedding_space"] = True
        if _model_id != DEFAULT_EMBEDDING_MODEL:
            _metadata["embedding_space_status"] = "supported_opt_in"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class LocalModelInfo:
    """Information about a local model."""

    model_id: str
    model_type: str  # ModelType value
    display_name: str
    size_bytes: int
    is_downloaded: bool
    expected_size_mb: int
    path: str | None
    metadata: dict = field(default_factory=dict)
    #: What this model is FOR, in one line -- shown under the row.
    note: str | None = None
    #: False when the row cannot act: no transcriber runtime, unsupported Mac.
    available: bool = True
    unavailable_reason: str | None = None
    #: idle | downloading | failed | installed. A background download that
    #: failed used to disappear silently; now the row says so.
    download_state: str = "idle"
    download_error: str | None = None

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "display_name": self.display_name,
            "size_bytes": self.size_bytes,
            "is_downloaded": self.is_downloaded,
            "expected_size_mb": self.expected_size_mb,
            "path": self.path,
            "metadata": self.metadata,
            "note": self.note,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "download_state": self.download_state,
            "download_error": self.download_error,
        }


# =============================================================================
# Local Model Manager
# =============================================================================


class LocalModelManager:
    """Manages locally-downloaded AI models.

    Handles listing, downloading, and deleting models for:
    - Whisper (audio transcription)
    - FastEmbed (text embeddings)
    - spaCy (future NLP models)
    """

    def __init__(self):
        self.base_path = MODELS_BASE
        self.whisper_path = self.base_path / "whisper"
        self.embeddings_path = self.base_path / "embeddings"
        self.spacy_path = self.base_path / "spacy"

        # Ensure directories exist
        self.whisper_path.mkdir(parents=True, exist_ok=True)
        self.embeddings_path.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Whisper Models
    # =========================================================================

    def list_whisper_models(self) -> list[LocalModelInfo]:
        """List all Whisper models, and say honestly which ones can act.

        Every row used to offer a Download button that could not work: the
        download called ``whisper.load_model`` in an env with no
        openai-whisper. The models now come from the MLX runtime, so a runtime
        without a transcriber makes each row say why it is inert instead of
        failing silently in a background task.
        """
        runtime = audio_runtime_status()
        runtime_ready = bool(runtime["ready"])
        runtime_reason = runtime["reason"]
        results = []
        for name, model_spec in WHISPER_MLX_MODELS.items():
            snapshot = _whisper_snapshot_path(model_spec)
            is_downloaded = snapshot.exists()
            state, error = download_state(name)
            results.append(
                LocalModelInfo(
                    model_id=name,
                    model_type=ModelType.WHISPER.value,
                    display_name=f"{model_spec.display_name} ({model_spec.params} params)",
                    size_bytes=_whisper_installed_bytes(name) if is_downloaded else 0,
                    is_downloaded=is_downloaded,
                    expected_size_mb=round(model_spec.download_size_bytes / 1_000_000),
                    path=str(snapshot) if is_downloaded else None,
                    metadata=WHISPER_MODELS[name],
                    note=f"{model_spec.note} ({model_spec.speed})",
                    # A downloaded model stays actionable (it can be deleted)
                    # even when the runtime is missing its transcriber.
                    available=runtime_ready or is_downloaded,
                    unavailable_reason=None if runtime_ready else str(runtime_reason),
                    download_state="installed" if is_downloaded else state,
                    download_error=error,
                )
            )
        return results

    def download_whisper_model(self, model_size: str) -> None:
        """Download a Whisper model into the shared store via the MLX runtime.

        Args:
            model_size: One of: tiny, base, small, medium, large-v3, turbo
        """
        _download_whisper_snapshot(model_size)

    def delete_whisper_model(self, model_size: str) -> int:
        """Delete a downloaded Whisper model.

        Args:
            model_size: Model to delete

        Returns:
            Number of bytes freed
        """
        return _delete_whisper_snapshot(model_size)

    # =========================================================================
    # Embeddings Models (FastEmbed)
    # =========================================================================

    def list_embeddings_models(self) -> list[LocalModelInfo]:
        """List all embeddings models (available and downloaded)."""
        results = []
        for model_id, info in EMBEDDINGS_MODELS.items():
            # FastEmbed stores models in subdirectories
            # The directory name replaces / with -- in the model ID
            model_dir = self._embeddings_model_dir(model_id)
            is_downloaded = model_dir.exists() and any(model_dir.rglob("*"))
            size = (
                sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
                if is_downloaded
                else 0
            )

            results.append(
                LocalModelInfo(
                    model_id=model_id,
                    model_type=ModelType.EMBEDDINGS.value,
                    display_name=model_id.split("/")[-1]
                    if "/" in model_id
                    else model_id,
                    size_bytes=size,
                    is_downloaded=is_downloaded,
                    expected_size_mb=info["disk_mb"],
                    path=str(model_dir) if is_downloaded else None,
                    metadata=info,
                )
            )
        return results

    def download_embeddings_model(self, model_id: str) -> None:
        """Download an embeddings model via FastEmbed.

        Args:
            model_id: HuggingFace model ID (e.g., "intfloat/multilingual-e5-large")
        """
        if model_id not in EMBEDDINGS_MODELS:
            raise ValueError(
                f"Unknown embeddings model: {model_id}. "
                f"Available: {', '.join(EMBEDDINGS_MODELS.keys())}"
            )

        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is not installed. Install with: pip install fastembed"
            )

        cache_dir = str(self.embeddings_path)
        logger.info(f"Downloading embeddings model '{model_id}' to {cache_dir}")
        TextEmbedding(model_name=model_id, cache_dir=cache_dir)
        logger.info(f"Embeddings model '{model_id}' downloaded successfully")

    def delete_embeddings_model(self, model_id: str) -> int:
        """Delete a downloaded embeddings model.

        Args:
            model_id: Model to delete

        Returns:
            Number of bytes freed
        """
        model_dir = self._embeddings_model_dir(model_id)
        if model_dir.exists():
            size = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
            shutil.rmtree(model_dir)
            logger.info(f"Deleted embeddings model '{model_id}' ({size} bytes)")
            return size
        return 0

    def _embeddings_model_dir(self, model_id: str) -> Path:
        """Get the directory path for a FastEmbed model."""
        # FastEmbed uses various naming conventions - check common patterns
        dir_name = model_id.replace("/", "--")
        direct = self.embeddings_path / dir_name
        if direct.exists():
            return direct

        # Also check for models/ subdirectory pattern
        models_sub = self.embeddings_path / "models" / dir_name
        if models_sub.exists():
            return models_sub

        # Check for the model name without org prefix
        short_name = model_id.split("/")[-1] if "/" in model_id else model_id
        short_dir = self.embeddings_path / short_name
        if short_dir.exists():
            return short_dir

        # Default to the direct path
        return direct

    # =========================================================================
    # Unified Operations
    # =========================================================================

    def list_spacy_models(self) -> list[LocalModelInfo]:
        """List the spaCy models the grammar gate can use.

        Installed-state comes from the RUNTIME, not from disk: these are pip
        packages, so a directory under `MODELS_BASE` would be a fiction. When
        spaCy itself is absent — the shipped engine's normal state, since it is
        an optional `[kg]` extra — every row reports why it cannot act rather
        than silently listing models nothing can load.
        """
        runtime = _spacy_runtime_available()
        installed = _spacy_installed_models() if runtime else set()
        results = []
        for model_id, info in SPACY_MODELS.items():
            stored = spacy_pipeline_path(model_id)
            bundled = model_id in installed
            is_downloaded = stored is not None or bundled
            results.append(
                LocalModelInfo(
                    model_id=model_id,
                    model_type=ModelType.SPACY.value,
                    display_name=model_id,
                    # A downloaded pipeline is files in our store and is measured; a bundled one ships in the app,
                    # where the catalog's figure is the honest one.
                    size_bytes=(_dir_bytes(stored) if stored else info["disk_mb"] * 1_000_000 if bundled else 0),
                    is_downloaded=is_downloaded,
                    expected_size_mb=info["disk_mb"],
                    path=str(stored) if stored else None,
                    metadata=info,
                    note=info["note"],
                    available=runtime,
                    unavailable_reason=(
                        None
                        if runtime
                        else "spaCy is not installed in this engine "
                        '(pip install -e ".[kg]")'
                    ),
                    download_state="installed" if is_downloaded else "idle",
                )
            )
        return results

    def download_spacy_model(self, model_id: str) -> None:
        """Download a spaCy pipeline's data folder into the store (`download_spacy_pipeline`); never pip."""
        if not _spacy_runtime_available():
            raise RuntimeError("spaCy is not in this engine, so a pipeline has nothing to run it")
        download_spacy_pipeline(model_id)

    def delete_spacy_model(self, model_id: str) -> int:
        """Delete a downloaded pipeline's folder; a bundled one ships in the app and is not ours to delete."""
        import shutil

        stored = spacy_pipeline_path(model_id)
        if stored is None:
            raise BundledModel(f"{model_id} is bundled with the app (or not downloaded): nothing to delete")
        freed = _dir_bytes(stored)
        shutil.rmtree(stored)
        return freed

    def list_all(self) -> list[LocalModelInfo]:
        """List all models across all types."""
        return (
            self.list_whisper_models()
            + self.list_embeddings_models()
            + self.list_spacy_models()
        )

    def total_disk_usage(self) -> dict[str, int]:
        """Get total disk usage by model type.

        Returns:
            Dict with whisper, embeddings, and total byte counts.
        """
        whisper_bytes = _whisper_total_bytes()
        embeddings_bytes = sum(m.size_bytes for m in self.list_embeddings_models())
        # Downloaded spaCy pipelines are files in our store and count; the bundled ones ship in the app and do not
        # (this number answers "how much disk can this app free").
        spacy_bytes = sum(m.size_bytes for m in self.list_spacy_models() if m.path)
        return {
            "whisper": whisper_bytes,
            "embeddings": embeddings_bytes,
            "spacy": spacy_bytes,
            "total": whisper_bytes + embeddings_bytes + spacy_bytes,
        }

    def download_model(self, model_type: str, model_id: str) -> None:
        """Download a model by type and ID.

        Args:
            model_type: "whisper" or "embeddings"
            model_id: Model identifier
        """
        if model_type == ModelType.WHISPER.value:
            self.download_whisper_model(model_id)
        elif model_type == ModelType.EMBEDDINGS.value:
            self.download_embeddings_model(model_id)
        elif model_type == ModelType.SPACY.value:
            self.download_spacy_model(model_id)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def delete_model(self, model_type: str, model_id: str) -> int:
        """Delete a model by type and ID.

        Args:
            model_type: "whisper" or "embeddings"
            model_id: Model identifier

        Returns:
            Bytes freed
        """
        if model_type == ModelType.WHISPER.value:
            return self.delete_whisper_model(model_id)
        elif model_type == ModelType.EMBEDDINGS.value:
            return self.delete_embeddings_model(model_id)
        elif model_type == ModelType.SPACY.value:
            return self.delete_spacy_model(model_id)
        else:
            raise ValueError(f"Unknown model type: {model_type}")


# --- The download-model job (`runtime.spacy.pipelines-download-as-data`) ------------------------------------------
DOWNLOAD_KIND = "download-model"
#: What a `download-model` job fetches, by runtime: each catalogue (#5359: Whisper and embeddings
#: models too, which used to download where Activity could not see them).
_DOWNLOADABLE = {"spacy": SPACY_MODELS, "whisper": WHISPER_MODELS, "embeddings": EMBEDDINGS_MODELS}


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if DOWNLOAD_KIND not in jobs.KINDS or jobs.KINDS[DOWNLOAD_KIND].run is None:
        jobs.register_kind(DOWNLOAD_KIND, lambda db, subject: _run_download(subject, db), model=None,
                           lane="network", name="Download a model")


#: How often a running download's row is told how far it has got (its reason, which Activity and the row that
#: asked for it show).
PROGRESS_EVERY_SECONDS = 2.0


def _say_progress(db, words: str) -> None:
    """The running job's reason, in words ("Downloading Qwen2.5-VL 7B: 1.2 GB of 5.6 GB"); nothing outside a job."""
    from fichero_server.execution import jobs

    job_id = jobs.current_job_id()
    if db is not None and job_id is not None:
        jobs.save_detail(db, job_id, json.dumps({"progress": words}), reason=words)


def _run_download(subject: str, db=None) -> None:
    """One `download-model` job: the model of its runtime fetched, then `model.installed` said. Its reason says how
    far it has got; a failure raises with why, which the row keeps (`source.find.one-download-path`, #5620)."""
    runtime, _, name = subject.partition(":")
    if runtime == "mlx":
        _run_mlx_download(name, db)
        return
    if runtime == "kraken":
        from fichero_server.llm.kraken_runtime import download_recognition_model

        _say_progress(db, f"Downloading the Kraken reader {name}")
        download_recognition_model(name)
        say_installed(runtime, name)
        return
    if runtime not in _DOWNLOADABLE:
        raise ValueError(f"no download for {subject!r}")
    _say_progress(db, f"Downloading the {runtime} model {name}")
    LocalModelManager().download_model(runtime, name)
    say_installed(runtime, name)


def _run_mlx_download(name: str, db) -> None:
    """An MLX model fetched by this Mac's model store, the job waiting on it and saying its progress."""
    import asyncio
    import time

    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    said = {"at": 0.0, "words": ""}

    def progress(job) -> None:
        now = time.monotonic()
        if job.message and job.message != said["words"] and now - said["at"] >= PROGRESS_EVERY_SECONDS:
            said.update(at=now, words=job.message)
            _say_progress(db, job.message)

    asyncio.run(get_mlx_model_store().download_and_wait(name, progress))


def _check_mlx(name: str) -> str:
    """The store's id for an MLX model (its catalogue id, Hub repository or a trained model's id); refused, in
    words, when the store does not know it or this Mac cannot run it: said, never queued."""
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    store = get_mlx_model_store()
    model_id = store.canonical_id(name)
    if model_id is None:
        raise ValueError(f"no download for mlx:{name}")
    try:
        store.require_supported(store.spec(model_id))
    except RuntimeError as exc:  # LocalModelHardwareError: this Mac cannot run it
        raise ValueError(str(exc)) from exc
    return model_id


def say_installed(runtime: str, model: str) -> None:
    """A model finished downloading: every window hears `model.installed` (with its runtime and model), so a Start
    plan that waited for it reads itself again and drops the download (`source.onboard.auto.installed-model-first`,
    #5583). The plan itself is worked out afresh on each read; this is only the cue. Best-effort: never raises."""
    from fichero_server.api.change_stream import emit_change_all_libraries

    emit_change_all_libraries(type="model.installed", metadata={"runtime": runtime, "model": model})


def enqueue_download(db, runtime: str, name: str, *, started_by: str = "owner") -> str:
    """Queue a `download-model` job on the network lane; one waiting job per model. An MLX model is checked first
    (one the store knows, that this Mac can run), so a refusal is said at once."""
    from fichero_server.execution import jobs

    if runtime == "mlx":
        name = _check_mlx(name)
    elif runtime == "kraken":
        from fichero_server.llm.kraken_runtime import recognition_spec

        if recognition_spec(name) is None:
            raise ValueError(f"no download for kraken:{name}: not a Kraken reader this Mac can fetch")
    elif runtime not in _DOWNLOADABLE or name not in _DOWNLOADABLE[runtime]:
        raise ValueError(f"no download for {runtime}:{name}")
    register_job_kinds()
    return jobs.enqueue(db, DOWNLOAD_KIND, f"{runtime}:{name}", started_by=started_by, watched=True)
