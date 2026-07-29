"""
Audio Tools Base Module

Extends llm_base.py with audio-specific functionality.
All audio tools inherit from here.

Provides:
- AUDIO_INPUT_PORTS (inherits BASE + adds files)
- AUDIO_CONFIG_SCHEMA (inherits BASE + adds audio_mode, language, whisper_model_size)
- Local Whisper transcription (openai-whisper)
- Apple Speech Recognition (macOS SFSpeechRecognizer)
- Remote transcription (via LiteLLM/provider APIs)
- process_audio() - shared processing for all audio tools

Inheritance: llm_base.py → audio_base.py → specific audio tools
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig, audio_transcription
from fichero_server.db.paths import server_state_dir

from fichero_server.workflows.types import PortDef, DataType

# Import from llm_base - the parent layer
from fichero_server.workflows.tools._doc_lookup import register_path_mapping
from fichero_server.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    parse_output,
    save_file_artifact as save_artifact,
    save_to_file as llm_save_to_file,
)

logger = logging.getLogger(__name__)


# Stable storage for local models (not ~/.cache which gets auto-cleaned).
# The ONE shared models folder shared with embeddings/spaCy/etc. (#2269) — never
# a per-library, scattered, or stale-bundle-id path. Canonical: local_models.py.
MODELS_BASE = server_state_dir() / "models"

# Process-global Whisper cache, keyed by the model identity and runtime target.
#
# Whisper models are large and expensive to load. The audio tools create a new
# transcription task per file, so constructing the model inside the sync helper
# reloaded it on every call. Cache the loaded object here so all callers in the
# process share one copy per (model_size, download_root, device).
_WHISPER_MODEL_CACHE: dict[tuple[str, str, str | None], Any] = {}
_WHISPER_MODEL_CACHE_LOCK = threading.Lock()


# =============================================================================
# Audio-Specific Port and Config Schemas
# =============================================================================

# Audio input ports: files first, then all base ports
AUDIO_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="files",
            name="Audio Files",
            port_type="input",
            data_type=DataType.FILES,
            required=True,
            description="Audio files to process",
        ),
    ],
    BASE_INPUT_PORTS,
)

# Audio config: base config + audio-specific options
AUDIO_CONFIG_SCHEMA = merge_config_schema(
    BASE_CONFIG_SCHEMA,
    {
        "audio_mode": {
            "type": "string",
            "enum": ["local_whisper", "apple_speech", "llm"],
            "default": "local_whisper",
            "description": "Audio processing engine",
            "x-group": "primary",
        },
        "language": {
            "type": "string",
            "default": "en",
            "description": "Language code for transcription",
            "x-group": "primary",
        },
        "whisper_model_size": {
            "type": "string",
            "enum": ["tiny", "base", "small", "medium", "large", "large-v3", "turbo"],
            "default": "base",
            "description": "Whisper model size (local only)",
            "x-group": "advanced",
        },
    },
)


# =============================================================================
# Audio Tool Configuration (extends LLMToolConfig)
# =============================================================================


@dataclass
class AudioToolConfig(LLMToolConfig):
    """Configuration for an audio tool.

    Extends LLMToolConfig with audio-specific options.
    """

    supports_apple_speech: bool = True
    supports_local_whisper: bool = True


# =============================================================================
# Local Whisper Transcription
# =============================================================================


def transcribe_with_whisper_sync(
    file_path: str,
    model_size: str = "base",
    language: str = "en",
) -> str:
    """Transcribe audio using local Whisper model.

    Models are stored in the shared models folder (server_state_dir()/models/whisper/,
    i.e. ~/Library/Application Support/Fichero/models/whisper/) to avoid macOS
    auto-cleanup of ~/.cache/ and to share one folder with embeddings/spaCy (#2269).

    Args:
        file_path: Path to audio file
        model_size: Whisper model size (tiny, base, small, medium, large, large-v3, turbo)
        language: Language code for transcription

    Returns:
        Transcribed text
    """
    download_root = str(MODELS_BASE / "whisper")
    Path(download_root).mkdir(parents=True, exist_ok=True)

    model = _get_shared_whisper_model(model_size, download_root, device=None)

    logger.info(f"Transcribing: {Path(file_path).name}")
    result = model.transcribe(
        str(file_path),
        language=language if language != "auto" else None,
    )

    return result["text"].strip()


def _get_shared_whisper_model(
    model_size: str,
    download_root: str,
    device: str | None,
) -> Any:
    """Return the process-global Whisper model for one identity, loading once."""
    cache_key = (model_size, download_root, device)
    model = _WHISPER_MODEL_CACHE.get(cache_key)
    if model is not None:
        return model

    with _WHISPER_MODEL_CACHE_LOCK:
        model = _WHISPER_MODEL_CACHE.get(cache_key)
        if model is None:
            try:
                import whisper
            except ImportError as exc:
                raise ImportError(
                    "openai-whisper is not installed. Install with: pip install openai-whisper"
                ) from exc

            if device is None:
                model = whisper.load_model(
                    model_size,
                    download_root=download_root,
                )
            else:
                model = whisper.load_model(
                    model_size,
                    download_root=download_root,
                    device=device,
                )
            _WHISPER_MODEL_CACHE[cache_key] = model
            logger.info(
                "Loaded Whisper model (process-global): %s @ %s device=%s",
                model_size,
                download_root,
                device,
            )
        return model


async def transcribe_with_whisper(
    file_path: str,
    model_size: str = "base",
    language: str = "en",
) -> str:
    """Async wrapper for local Whisper transcription."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        transcribe_with_whisper_sync,
        file_path,
        model_size,
        language,
    )


# =============================================================================
# Apple Speech Recognition (macOS)
# =============================================================================


def apple_speech_recognize_sync(file_path: str, language: str = "en") -> str:
    """Transcribe audio using macOS SFSpeechRecognizer.

    Uses on-device speech recognition available on macOS 10.15+.

    Args:
        file_path: Path to audio file
        language: Language code (e.g., "en", "en-US", "fr")

    Returns:
        Recognized text
    """
    try:
        import Speech
        from Foundation import NSURL, NSLocale  # pylint: disable=no-name-in-module
    except ImportError:
        raise ValueError(
            "Apple Speech framework not available. "
            "Requires macOS with PyObjC and Speech framework access."
        )


    if not os.path.exists(file_path):
        raise ValueError(f"Audio file not found: {file_path}")

    # Map short language codes to locale identifiers
    lang_map = {
        "en": "en-US",
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "pt": "pt-BR",
        "ja": "ja-JP",
        "zh": "zh-CN",
        "ko": "ko-KR",
    }
    locale_id = lang_map.get(language, language)

    # Create recognizer
    locale = NSLocale.alloc().initWithLocaleIdentifier_(locale_id)
    recognizer = Speech.SFSpeechRecognizer.alloc().initWithLocale_(locale)

    if not recognizer or not recognizer.isAvailable():
        raise ValueError(f"Speech recognizer not available for locale: {locale_id}")

    # Create recognition request
    url = NSURL.fileURLWithPath_(file_path)
    request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(url)
    request.setShouldReportPartialResults_(False)

    # Perform recognition synchronously using a semaphore

    result_text = ""
    error_msg = None
    done_event = threading.Event()

    def handler(result, error):
        nonlocal result_text, error_msg
        if error:
            error_msg = str(error)
        elif result and result.isFinal():
            result_text = result.bestTranscription().formattedString()
        done_event.set()

    recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
    done_event.wait(timeout=300)  # 5 minute timeout

    if error_msg:
        raise ValueError(f"Speech recognition failed: {error_msg}")

    return result_text


async def transcribe_with_apple_speech(file_path: str, language: str = "en") -> str:
    """Async wrapper for Apple Speech recognition."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        apple_speech_recognize_sync,
        file_path,
        language,
    )


# =============================================================================
# Remote LLM Transcription
# =============================================================================


async def transcribe_with_llm(
    file_path: str,
    llm_config: LLMConfig,
    prompt: str = "Transcribe this audio accurately.",
    language: str | None = None,
) -> str:
    """Transcribe audio through Fichero's canonical LangChain boundary.

    Args:
        file_path: Path to audio file
        llm_config: LLM configuration with provider and model
        prompt: Optional prompt hint for transcription

    Returns:
        Transcribed text
    """
    logger.info(
        "Remote transcription with %s/%s: %s",
        llm_config.provider,
        llm_config.model,
        Path(file_path).name,
    )
    return (
        await audio_transcription(file_path, prompt, llm_config, language=language)
    ).strip()


# =============================================================================
# Database Operations
# =============================================================================
#
# `save_artifact` here is `llm_base.save_file_artifact` (imported as that name
# above) — the single shared file-oriented wrapper around the canonical
# `llm_base.save_artifact`. Audio no longer re-declares its own wrapper, so the
# per-page document-resolution contract (incl. the `document=` pass-through) is
# enforced in exactly one place and can never drift here.


# =============================================================================
# Main Processing Function
# =============================================================================


async def process_audio(
    files: list[str],
    documents: list[dict],
    prompt: str,
    llm_config: LLMConfig,
    library_path: str,
    task_id: str | None,
    tool_config: AudioToolConfig,
    *,
    # Audio-specific (from AUDIO_CONFIG_SCHEMA)
    audio_mode: str = "local_whisper",
    language: str = "en",
    whisper_model_size: str = "base",
    # LLM parameters (from BASE_CONFIG_SCHEMA)
    temperature: float | None = None,
    max_tokens: int | None = None,
    # Output format (from BASE_CONFIG_SCHEMA)
    output_format: str = "text",
    output_options: dict | None = None,
    # Reference values (from BASE_CONFIG_SCHEMA)
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
    # Context (from BASE_CONFIG_SCHEMA)
    context: str | None = None,
    input_metadata: dict | None = None,
    # Storage (from BASE_CONFIG_SCHEMA)
    save_to_db: bool = True,
    save_to_file_flag: bool = False,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
) -> dict[str, Any]:
    """Process audio files with transcription engines.

    This is the shared core function for all audio tools.
    Dispatches to local Whisper, Apple Speech, or remote LLM based on audio_mode.

    Args:
        files: List of audio file paths
        documents: Document metadata from source tools
        prompt: The prompt (used for LLM mode or post-processing)
        llm_config: LLM configuration
        library_path: Path to library database
        task_id: Workflow task ID
        tool_config: Tool-specific configuration
        audio_mode: "local_whisper", "apple_speech", or "llm"
        language: Language code for transcription
        whisper_model_size: Whisper model size (local mode only)
        temperature: Override LLM temperature
        max_tokens: Override LLM max tokens
        output_format: Expected output format
        output_options: Format-specific options
        reference_values: Known values to match against
        match_mode: How to use reference values
        context: Previous text/transcription
        input_metadata: Existing metadata to include
        save_to_db: Whether to save results
        save_to_file_flag: Whether to export to file
        metadata_field: Override metadata field
        custom_metadata: Additional metadata to save

    Returns:
        Dict with text, value, texts, values, results, artifacts, error
    """
    if isinstance(files, str):
        files = [files]

    if not files:
        logger.warning("process_audio: no input files — all selected IDs may be stale/invalid")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
        }

    # Build path -> document_id mapping
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                register_path_mapping(path_to_doc, doc["path"], doc.get("id"))
    logger.debug(
        f"process_audio: {len(files)} files, mode={audio_mode}, "
        f"model_size={whisper_model_size}, language={language}"
    )

    results = []
    texts = []
    values = []
    artifact_ids = []
    output_files = []

    for file_path in files:
        try:
            # Dispatch to appropriate engine
            if audio_mode == "local_whisper" and tool_config.supports_local_whisper:
                logger.info(
                    f"Local Whisper ({whisper_model_size}): {Path(file_path).name}"
                )
                text = await transcribe_with_whisper(
                    file_path, whisper_model_size, language
                )

            elif audio_mode == "apple_speech" and tool_config.supports_apple_speech:
                logger.info(f"Apple Speech: {Path(file_path).name}")
                text = await transcribe_with_apple_speech(file_path, language)

            else:
                # Remote LLM transcription
                logger.info(f"Remote LLM: {Path(file_path).name}")
                text = await transcribe_with_llm(
                    file_path, llm_config, prompt, language
                )

            # Parse output according to format (usually just text for transcription)
            parsed = parse_output(text, output_format, output_options)

            result = {"file": file_path, "text": text, "value": parsed}

            # Save to database
            if save_to_db and library_path:
                # Set proper provider/model labels for local processing
                save_config = llm_config
                if audio_mode == "local_whisper":
                    save_config = LLMConfig(
                        provider="Local", model=f"Whisper-{whisper_model_size}"
                    )
                elif audio_mode == "apple_speech":
                    save_config = LLMConfig(
                        provider="Apple", model="Speech Recognition"
                    )

                artifact_id = await save_artifact(
                    file_path=file_path,
                    content=text,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=save_config,
                    task_id=task_id,
                    tool_config=tool_config,
                    metadata_field=metadata_field,
                    custom_metadata=custom_metadata,
                )
                if artifact_id:
                    result["artifact_id"] = artifact_id
                    artifact_ids.append(artifact_id)

            # Save to file
            if save_to_file_flag and library_path:
                output_path = await llm_save_to_file(
                    content=text,
                    data=parsed if isinstance(parsed, dict) else None,
                    library_path=library_path,
                    document_id=path_to_doc.get(file_path),
                    file_path=file_path,
                    tool_config=tool_config,
                    output_format=output_format,
                )
                if output_path:
                    output_files.append(output_path)
                    result["output_file"] = output_path

            results.append(result)
            texts.append(text)
            values.append(parsed)

        except Exception as e:
            logger.error(f"Audio processing failed for {file_path}: {e}")
            results.append(
                {"file": file_path, "text": "", "value": None, "error": str(e)}
            )
            texts.append("")
            values.append(None)

    # Check for errors
    errors = [r.get("error") for r in results if r.get("error")]
    error_msg = None
    if errors:
        if len(files) == 1:
            error_msg = errors[0]
        else:
            error_msg = f"{len(errors)}/{len(files)} failed: {errors[0]}"

    # For single file, return the value directly; for multiple, return list
    single_value = values[0] if len(values) == 1 else values

    return {
        "text": "\n\n".join(texts),
        "value": single_value,
        "texts": texts,
        "values": values,
        "results": results,
        "artifacts": artifact_ids,
        "output_files": output_files,
        "error": error_msg,
    }
