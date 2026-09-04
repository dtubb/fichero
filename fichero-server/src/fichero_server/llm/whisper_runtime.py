"""Whisper transcription served from the managed MLX runtime venv.

Fichero's Whisper surface used to be a shopfront with no shop behind it. The
Downloads tab listed six models; every Download button called
``whisper.load_model`` inside the shipped engine env, where ``openai-whisper``
is undeclared and torch is deliberately absent (it is a ~1.5 GB dependency the
engine does not carry). So every button failed, and so did every
``local_whisper`` workflow run.

The fix mirrors what #4560 did for vision: the capability moves into the
isolated ``mlx-runtime`` venv the app already provisions and owns. mlx-whisper
is the MLX-native transcriber; the weights come from mlx-community's converted
repos through the same HF snapshot store pattern the MLX model store uses; and
a runtime that has no transcriber says so instead of failing at the point of
use with "No module named whisper".

Nothing here imports mlx-whisper into the engine process -- the runtime
interpreter runs it in a subprocess, exactly as ``mlx_vlm.server`` is run.

One cost is stated rather than hidden: each transcription starts its own
interpreter and loads the weights again, so a batch of files pays the load
once per file (seconds for tiny/base, longer for large-v3). The alternative --
a resident sidecar for audio -- is a bigger design than tonight's fix, and a
cache of a model that lives in another process is not a thing this module can
have.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess

from fichero_server.db.paths import server_state_dir
from fichero_server.llm.mlx_runtime import MLXAudioRuntimeMissingError, get_mlx_runtime

logger = logging.getLogger(__name__)


class WhisperModelNotInstalledError(RuntimeError):
    """Raised when the requested Whisper weights are not on disk."""


class UnknownWhisperModelError(ValueError):
    """Raised when a caller names a Whisper model the catalog does not have."""


class WhisperTranscriptionError(RuntimeError):
    """Raised when the runtime transcriber ran and did not produce text."""


@dataclass(frozen=True)
class WhisperModelSpec:
    """One curated Whisper model, with what it costs and what it is for."""

    model_id: str
    repo_id: str
    revision: str
    display_name: str
    params: str
    download_size_bytes: int
    speed: str
    note: str


#: Sizes and revisions read from the Hugging Face API (2026-09-03), not
#: estimated: every number below is the summed blob size of that exact commit.
WHISPER_MLX_MODELS: dict[str, WhisperModelSpec] = {
    "tiny": WhisperModelSpec(
        model_id="tiny",
        repo_id="mlx-community/whisper-tiny-mlx",
        revision="6caf9c55601caafbe6508a8b0d216bdf4783c4e8",
        display_name="Whisper tiny",
        params="39M",
        download_size_bytes=74_000_000,
        speed="~10x realtime",
        note="Fastest and least accurate. Good for checking that audio reaches the transcriber at all.",
    ),
    "base": WhisperModelSpec(
        model_id="base",
        repo_id="mlx-community/whisper-base-mlx",
        revision="1e3e249fb8d01c655324bd6841b1deadffd6d04c",
        display_name="Whisper base",
        params="74M",
        download_size_bytes=144_000_000,
        speed="~7x realtime",
        note="The default. Clear English speech transcribes well; accents and noise do not.",
    ),
    "small": WhisperModelSpec(
        model_id="small",
        repo_id="mlx-community/whisper-small-mlx",
        revision="45f3915923c7a79a5a5b5a7d909d39aeb0e5630e",
        display_name="Whisper small",
        params="244M",
        download_size_bytes=481_000_000,
        speed="~4x realtime",
        note="First size worth trusting on non-English audio. Best size-to-quality trade for interviews.",
    ),
    "medium": WhisperModelSpec(
        model_id="medium",
        repo_id="mlx-community/whisper-medium-mlx",
        revision="7fc08c4eac4c316526498f147dfdee6f6303f975",
        display_name="Whisper medium",
        params="769M",
        download_size_bytes=1_525_000_000,
        speed="~2x realtime",
        note="Noticeably better on accented and noisy recordings; large-v3-turbo is usually the better buy.",
    ),
    "large-v3": WhisperModelSpec(
        model_id="large-v3",
        repo_id="mlx-community/whisper-large-v3-mlx",
        revision="49e6aa286ad60c14352c404340ded53710378a11",
        display_name="Whisper large-v3",
        params="1550M",
        download_size_bytes=3_084_000_000,
        speed="~1x realtime",
        note="Highest accuracy, slowest. Reach for it on archival audio you only transcribe once.",
    ),
    "turbo": WhisperModelSpec(
        model_id="turbo",
        repo_id="mlx-community/whisper-large-v3-turbo",
        revision="a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
        display_name="Whisper large-v3-turbo",
        params="809M",
        download_size_bytes=1_614_000_000,
        speed="~8x realtime",
        note="Near-large-v3 accuracy at a fraction of the time. The recommended model for most transcription.",
    ),
}

#: ``AUDIO_CONFIG_SCHEMA`` has offered "large" as a choice for as long as the
#: audio tools have existed. OpenAI retired the plain "large" checkpoint in
#: favour of large-v3, so honour the old config value rather than failing a
#: saved workflow that still carries it.
WHISPER_MODEL_ALIASES = {"large": "large-v3", "large-v2": "large-v3"}

#: Module-level, because ``LocalModelManager`` is constructed per request and
#: the download runs in a FastAPI BackgroundTask: without somewhere durable to
#: record it, a failed download returned 200 and then vanished. The tab showed
#: a model that was never going to appear and gave no reason.
_DOWNLOAD_STATE: dict[str, tuple[str, str | None]] = {}


def whisper_store_dir(home: Path | None = None) -> Path:
    """The one shared models folder (#2269), not ~/.cache."""
    return server_state_dir(home) / "models" / "whisper"


def whisper_cache_dir(home: Path | None = None) -> Path:
    return whisper_store_dir(home) / "hub"


def resolve_model_id(model_id: str) -> str:
    resolved = WHISPER_MODEL_ALIASES.get(model_id, model_id)
    if resolved not in WHISPER_MLX_MODELS:
        raise UnknownWhisperModelError(
            f"Unknown Whisper model: {model_id}. Available: {', '.join(WHISPER_MLX_MODELS)}"
        )
    return resolved


def spec(model_id: str) -> WhisperModelSpec:
    return WHISPER_MLX_MODELS[resolve_model_id(model_id)]


def snapshot_path(model_spec: WhisperModelSpec, home: Path | None = None) -> Path:
    return (
        whisper_cache_dir(home)
        / f"models--{model_spec.repo_id.replace('/', '--')}"
        / "snapshots"
        / model_spec.revision
    )


def is_installed(model_id: str, home: Path | None = None) -> bool:
    return snapshot_path(spec(model_id), home).exists()


def installed_bytes(model_id: str, home: Path | None = None) -> int:
    return _disk_usage_bytes(snapshot_path(spec(model_id), home))


def total_disk_usage_bytes(home: Path | None = None) -> int:
    return _disk_usage_bytes(whisper_store_dir(home))


def download_state(model_id: str) -> tuple[str, str | None]:
    """(state, error) for one model: idle | downloading | failed | installed."""
    return _DOWNLOAD_STATE.get(resolve_model_id(model_id), ("idle", None))


def audio_runtime_status() -> dict[str, object]:
    """Whether anything can transcribe at all, and why not when it cannot."""
    runtime = get_mlx_runtime()
    ready = runtime.has_audio()
    return {
        "ready": ready,
        "mlx_whisper_version": runtime.status().get("mlx_whisper_version"),
        "reason": None
        if ready
        else (
            "The MLX runtime has no transcriber yet. Provision it in "
            "Settings -> AI -> Local Inference to enable Whisper."
        ),
    }


#: Runs in the MLX runtime interpreter, not this one. The third argument is
#: always ``whisper_cache_dir()`` -- i.e. under ``server_state_dir()/models``,
#: the ONE shared models folder (#2269) -- and is named ``models_path`` so the
#: shared-folder guardrail can see that, exactly as the MLX model store does.
_DOWNLOAD_SCRIPT = """
import sys
from huggingface_hub import snapshot_download
repo_id, revision, models_path = sys.argv[1], sys.argv[2], sys.argv[3]
snapshot_download(repo_id=repo_id, revision=revision, cache_dir=models_path)
"""

_TRANSCRIBE_SCRIPT = """
import json, sys
import mlx_whisper
audio_path, model_path, language = sys.argv[1], sys.argv[2], sys.argv[3]
options = {}
if language and language != "auto":
    options["language"] = language
result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=model_path, **options)
sys.stdout.write(
    "__FICHERO_WHISPER__"
    + json.dumps({"text": result.get("text", ""), "language": result.get("language")})
)
"""


def download_whisper_model(model_id: str, home: Path | None = None) -> Path:
    """Fetch one Whisper model into the shared store. Blocking; raises typed."""
    model_spec = spec(model_id)
    target = snapshot_path(model_spec, home)
    if target.exists():
        _DOWNLOAD_STATE[model_spec.model_id] = ("installed", None)
        return target

    try:
        python_path = get_mlx_runtime().require_audio_python_path()
    except MLXAudioRuntimeMissingError as exc:
        # Recorded, not just raised: the caller is a BackgroundTask whose
        # exception nobody sees, and the row has to be able to say why.
        _DOWNLOAD_STATE[model_spec.model_id] = ("failed", str(exc))
        raise
    cache_dir = whisper_cache_dir(home)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _DOWNLOAD_STATE[model_spec.model_id] = ("downloading", None)
    logger.info("Downloading %s (%s) into %s", model_spec.display_name, model_spec.repo_id, cache_dir)
    try:
        subprocess.run(
            [
                str(python_path),
                "-c",
                _DOWNLOAD_SCRIPT,
                model_spec.repo_id,
                model_spec.revision,
                str(cache_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        excerpt = (exc.stderr or exc.stdout or "").strip().splitlines()
        _DOWNLOAD_STATE[model_spec.model_id] = (
            "failed",
            excerpt[-1] if excerpt else f"download exited {exc.returncode}",
        )
        raise
    _DOWNLOAD_STATE[model_spec.model_id] = ("installed", None)
    return target


def delete_whisper_model(model_id: str, home: Path | None = None) -> int:
    """Remove one model's snapshot; returns bytes freed."""
    model_spec = spec(model_id)
    target = snapshot_path(model_spec, home)
    if not target.exists():
        _DOWNLOAD_STATE.pop(model_spec.model_id, None)
        return 0
    resolved = target.resolve()
    if resolved.name != model_spec.revision:
        raise ValueError(f"Refusing to delete unexpected path: {resolved}")
    if whisper_cache_dir(home).resolve() not in resolved.parents:
        raise ValueError(f"Refusing to delete outside the Whisper store: {resolved}")
    freed = _disk_usage_bytes(resolved)
    shutil.rmtree(resolved)
    _DOWNLOAD_STATE.pop(model_spec.model_id, None)
    logger.info("Deleted %s (%d bytes)", model_spec.display_name, freed)
    return freed


def transcribe_sync(
    file_path: str,
    model_id: str = "base",
    language: str = "en",
    home: Path | None = None,
) -> str:
    """Transcribe one audio file with mlx-whisper in the managed runtime."""
    model_spec = spec(model_id)
    python_path = get_mlx_runtime().require_audio_python_path()
    model_path = snapshot_path(model_spec, home)
    if not model_path.exists():
        raise WhisperModelNotInstalledError(
            f"{model_spec.display_name} is not downloaded. Download it in "
            f"Settings -> AI -> Local Models before transcribing."
        )

    env = {"HF_HUB_OFFLINE": "1", "HF_HOME": str(whisper_store_dir(home))}
    try:
        completed = subprocess.run(
            [str(python_path), "-c", _TRANSCRIBE_SCRIPT, str(file_path), str(model_path), language],
            check=True,
            capture_output=True,
            text=True,
            env={**_base_env(), **env},
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"transcriber exited {exc.returncode}"
        if "ffmpeg" in tail.lower() or "No such file or directory: 'ffmpeg'" in tail:
            raise WhisperTranscriptionError(
                "Whisper needs the ffmpeg CLI to decode audio. Install it with: brew install ffmpeg"
            ) from exc
        raise WhisperTranscriptionError(f"Whisper transcription failed: {tail}") from exc

    marker = "__FICHERO_WHISPER__"
    if marker not in completed.stdout:
        raise WhisperTranscriptionError(
            "The transcriber produced no result payload; "
            f"stderr: {(completed.stderr or '').strip()[-400:]}"
        )
    payload = json.loads(completed.stdout.split(marker, 1)[1])
    return str(payload.get("text", "")).strip()


def _base_env() -> dict[str, str]:
    return os.environ.copy()


def _disk_usage_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


__all__ = [
    "UnknownWhisperModelError",
    "WHISPER_MLX_MODELS",
    "WHISPER_MODEL_ALIASES",
    "WhisperModelNotInstalledError",
    "WhisperModelSpec",
    "WhisperTranscriptionError",
    "audio_runtime_status",
    "delete_whisper_model",
    "download_state",
    "download_whisper_model",
    "installed_bytes",
    "is_installed",
    "resolve_model_id",
    "snapshot_path",
    "spec",
    "total_disk_usage_bytes",
    "transcribe_sync",
    "whisper_cache_dir",
    "whisper_store_dir",
]
