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
from fichero_server.db.paths import server_state_dir
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
MODELS_BASE = server_state_dir() / "models"


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

SPACY_MODELS: dict[str, dict] = {
    "es_core_news_sm": {
        "language": "es",
        "disk_mb": 16,
        "note": "Spanish — the SVO grammar gate. Small is enough: the gate "
                "reads part-of-speech and person, not word vectors.",
    },
    "en_core_web_sm": {
        "language": "en",
        "disk_mb": 15,
        "note": "English — the same gate, for English-language material.",
    },
    "es_core_news_lg": {
        "language": "es",
        "disk_mb": 568,
        "note": "Spanish, large. Carries word vectors this gate does not use, "
                "and its benefit for 16th-century orthography is UNMEASURED — "
                "install it to test that, not on the assumption it is better.",
    },
}


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
            is_downloaded = model_id in installed
            results.append(
                LocalModelInfo(
                    model_id=model_id,
                    model_type=ModelType.SPACY.value,
                    display_name=model_id,
                    # Package size is not measurable without walking
                    # site-packages per model; the catalog's figure is the
                    # honest one and it is labelled as expected, not actual.
                    size_bytes=info["disk_mb"] * 1_000_000 if is_downloaded else 0,
                    is_downloaded=is_downloaded,
                    expected_size_mb=info["disk_mb"],
                    path=None,
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
        """Install a spaCy model package.

        Raises rather than half-succeeding: without the runtime there is
        nothing to install INTO, and a download that quietly does nothing is
        the shape a user reads as "it worked".
        """
        if model_id not in SPACY_MODELS:
            raise ValueError(f"Unknown spaCy model: {model_id}")
        if not _spacy_runtime_available():
            raise RuntimeError(
                "spaCy is not installed in this engine, so its models have "
                'nowhere to go. Install the extra first: pip install -e ".[kg]"'
            )
        from spacy.cli import download as spacy_download

        spacy_download(model_id)

    def delete_spacy_model(self, model_id: str) -> int:
        """Not ours to delete — say so instead of pretending."""
        raise RuntimeError(
            f"{model_id} is a pip package, not a file in this app's model "
            f"store. Remove it with: pip uninstall {model_id}"
        )

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
        # spaCy models are pip packages, not files in our store, so they
        # are listed but deliberately NOT counted here: this number answers
        # "how much disk can this app free", and it cannot free those.
        return {
            "whisper": whisper_bytes,
            "embeddings": embeddings_bytes,
            "total": whisper_bytes + embeddings_bytes,
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
