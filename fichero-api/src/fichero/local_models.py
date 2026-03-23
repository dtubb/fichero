"""
Unified Local Model Management

Manages locally-downloaded AI models for Whisper, FastEmbed, and spaCy.
Models are stored in ~/Library/Application Support/com.tubb.fichero/models/
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

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    WHISPER = "whisper"
    EMBEDDINGS = "embeddings"
    SPACY = "spacy"


# Stable storage location (not ~/.cache which gets auto-cleaned by macOS)
MODELS_BASE = Path.home() / "Library" / "Application Support" / "com.tubb.fichero" / "models"


# =============================================================================
# Model Catalogs
# =============================================================================

WHISPER_MODELS: dict[str, dict] = {
    "tiny": {"params": "39M", "disk_mb": 75, "speed": "~10x realtime"},
    "base": {"params": "74M", "disk_mb": 142, "speed": "~7x realtime"},
    "small": {"params": "244M", "disk_mb": 466, "speed": "~4x realtime"},
    "medium": {"params": "769M", "disk_mb": 1500, "speed": "~2x realtime"},
    "large-v3": {"params": "1550M", "disk_mb": 2900, "speed": "1x realtime"},
    "turbo": {"params": "809M", "disk_mb": 1500, "speed": "~8x realtime"},
}

EMBEDDINGS_MODELS: dict[str, dict] = {
    "intfloat/multilingual-e5-large": {
        "dimensions": 1024,
        "disk_mb": 2200,
        "languages": "100+",
        "description": "Best multilingual quality (default)",
    },
    "intfloat/multilingual-e5-base": {
        "dimensions": 768,
        "disk_mb": 1100,
        "languages": "100+",
        "description": "Good multilingual, smaller",
    },
    "BAAI/bge-small-en-v1.5": {
        "dimensions": 384,
        "disk_mb": 130,
        "languages": "English",
        "description": "Fast English-only",
    },
    "all-MiniLM-L6-v2": {
        "dimensions": 384,
        "disk_mb": 90,
        "languages": "English",
        "description": "Tiny English-only",
    },
}


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
        """List all Whisper models (available and downloaded)."""
        results = []
        for name, info in WHISPER_MODELS.items():
            # Whisper stores models as {name}.pt
            model_file = self.whisper_path / f"{name}.pt"
            is_downloaded = model_file.exists()
            size = model_file.stat().st_size if is_downloaded else 0

            results.append(LocalModelInfo(
                model_id=name,
                model_type=ModelType.WHISPER.value,
                display_name=f"Whisper {name} ({info['params']} params)",
                size_bytes=size,
                is_downloaded=is_downloaded,
                expected_size_mb=info["disk_mb"],
                path=str(model_file) if is_downloaded else None,
                metadata=info,
            ))
        return results

    def download_whisper_model(self, model_size: str) -> None:
        """Download a Whisper model to managed storage.

        Args:
            model_size: One of: tiny, base, small, medium, large-v3, turbo
        """
        if model_size not in WHISPER_MODELS:
            raise ValueError(
                f"Unknown Whisper model: {model_size}. "
                f"Available: {', '.join(WHISPER_MODELS.keys())}"
            )

        try:
            import whisper
        except ImportError:
            raise ImportError(
                "openai-whisper is not installed. "
                "Install with: pip install openai-whisper"
            )

        download_root = str(self.whisper_path)
        logger.info(f"Downloading Whisper model '{model_size}' to {download_root}")
        whisper.load_model(model_size, download_root=download_root)
        logger.info(f"Whisper model '{model_size}' downloaded successfully")

    def delete_whisper_model(self, model_size: str) -> int:
        """Delete a downloaded Whisper model.

        Args:
            model_size: Model to delete

        Returns:
            Number of bytes freed
        """
        model_file = self.whisper_path / f"{model_size}.pt"
        if model_file.exists():
            size = model_file.stat().st_size
            model_file.unlink()
            logger.info(f"Deleted Whisper model '{model_size}' ({size} bytes)")
            return size
        return 0

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

            results.append(LocalModelInfo(
                model_id=model_id,
                model_type=ModelType.EMBEDDINGS.value,
                display_name=model_id.split("/")[-1] if "/" in model_id else model_id,
                size_bytes=size,
                is_downloaded=is_downloaded,
                expected_size_mb=info["disk_mb"],
                path=str(model_dir) if is_downloaded else None,
                metadata=info,
            ))
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
                "fastembed is not installed. "
                "Install with: pip install fastembed"
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

    def list_all(self) -> list[LocalModelInfo]:
        """List all models across all types."""
        return self.list_whisper_models() + self.list_embeddings_models()

    def total_disk_usage(self) -> dict[str, int]:
        """Get total disk usage by model type.

        Returns:
            Dict with whisper, embeddings, and total byte counts.
        """
        whisper_bytes = sum(m.size_bytes for m in self.list_whisper_models())
        embeddings_bytes = sum(m.size_bytes for m in self.list_embeddings_models())
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
        else:
            raise ValueError(f"Unknown model type: {model_type}")
