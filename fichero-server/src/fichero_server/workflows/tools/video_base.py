"""
Video Tools Base Module

Extends llm_base.py with video-specific functionality.
Composes audio_base for audio track extraction.
All video tools inherit from here.

Provides:
- VIDEO_INPUT_PORTS (inherits BASE + adds files)
- VIDEO_CONFIG_SCHEMA (inherits BASE + adds extract_audio, frame_sample_rate, max_frames)
- Frame extraction from video (via ffmpeg)
- Audio track extraction (via ffmpeg)
- process_video() - shared processing combining frame analysis + audio transcription

Inheritance: llm_base.py → video_base.py → specific video tools
Composition: audio_base.transcribe_with_whisper() for audio track processing
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import shutil
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero_server.llm import LLMConfig

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
    build_context_section,
    build_reference_section,
    save_file_artifact as save_artifact,
    save_to_file as llm_save_to_file,
)

# Import audio transcription for audio track processing
from fichero_server.workflows.tools.audio_base import transcribe_with_whisper

# Import vision utilities for frame analysis
from fichero_server.workflows.tools.vision_base import file_to_data_uri

logger = logging.getLogger(__name__)


# =============================================================================
# Video-Specific Port and Config Schemas
# =============================================================================

# Video input ports: files first, then all base ports
VIDEO_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="files",
            name="Video Files",
            port_type="input",
            data_type=DataType.FILES,
            required=True,
            description="Video files to process",
        ),
    ],
    BASE_INPUT_PORTS,
)

# Video config: base config + video-specific options
VIDEO_CONFIG_SCHEMA = merge_config_schema(
    BASE_CONFIG_SCHEMA,
    {
        "extract_audio": {
            "type": "boolean",
            "default": True,
            "description": "Extract and transcribe audio track",
            "x-group": "primary",
        },
        "frame_sample_rate": {
            "type": "integer",
            "default": 1,
            "description": "Frames to sample per second",
            "x-group": "advanced",
        },
        "max_frames": {
            "type": "integer",
            "default": 10,
            "description": "Maximum frames to analyze",
            "x-group": "advanced",
        },
        "max_image_dimension": {
            "type": "integer",
            "default": 1024,
            "description": "Max frame size for LLM",
            "x-group": "advanced",
        },
        "whisper_model_size": {
            "type": "string",
            "enum": ["tiny", "base", "small", "medium", "large", "large-v3", "turbo"],
            "default": "base",
            "description": "Whisper model for audio track",
            "x-group": "advanced",
        },
    },
)


# =============================================================================
# Video Tool Configuration (extends LLMToolConfig)
# =============================================================================


@dataclass
class VideoToolConfig(LLMToolConfig):
    """Configuration for a video tool.

    Extends LLMToolConfig with video-specific options.
    """

    extract_audio: bool = True


# =============================================================================
# ffmpeg Utilities
# =============================================================================


def _check_ffmpeg() -> None:
    """Check that ffmpeg is available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "ffmpeg is not installed or not in PATH. Install with: brew install ffmpeg"
        )


def extract_audio_track_sync(video_path: str, output_path: str) -> str:
    """Extract audio track from video as WAV.

    Args:
        video_path: Path to video file
        output_path: Path to write extracted audio

    Returns:
        Path to extracted audio file
    """
    _check_ffmpeg()

    logger.info(f"Extracting audio from: {Path(video_path).name}")
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_path,
            "-vn",  # No video
            "-acodec",
            "pcm_s16le",  # PCM format for Whisper
            "-ar",
            "16000",  # 16kHz sample rate
            "-ac",
            "1",  # Mono
            "-y",  # Overwrite
            output_path,
        ],
        check=True,
        capture_output=True,
    )

    return output_path


async def extract_audio_track(video_path: str, output_path: str) -> str:
    """Async wrapper for audio extraction."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        extract_audio_track_sync,
        video_path,
        output_path,
    )


def sample_frames_sync(
    video_path: str,
    rate: int = 1,
    max_frames: int = 10,
) -> list[str]:
    """Extract key frames from video at given rate.

    Args:
        video_path: Path to video file
        rate: Frames per second to sample
        max_frames: Maximum number of frames to extract

    Returns:
        List of paths to extracted frame images
    """
    _check_ffmpeg()

    frame_dir = tempfile.mkdtemp(prefix="fichero_frames_")

    logger.info(
        f"Sampling frames from: {Path(video_path).name} (rate={rate}, max={max_frames})"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"fps={rate}",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "2",  # High quality JPEG
            os.path.join(frame_dir, "frame_%04d.jpg"),
        ],
        check=True,
        capture_output=True,
    )

    frames = sorted(
        [
            os.path.join(frame_dir, f)
            for f in os.listdir(frame_dir)
            if f.startswith("frame_") and f.endswith(".jpg")
        ]
    )

    logger.info(f"Extracted {len(frames)} frames")
    return frames[:max_frames]


async def sample_frames(
    video_path: str,
    rate: int = 1,
    max_frames: int = 10,
) -> list[str]:
    """Async wrapper for frame sampling."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        sample_frames_sync,
        video_path,
        rate,
        max_frames,
    )


# =============================================================================
# Frame Analysis with Vision LLM
# =============================================================================


async def describe_frames(
    frame_paths: list[str],
    prompt: str,
    llm_config: LLMConfig,
    max_image_dimension: int = 1024,
) -> str:
    """Describe video frames using vision LLM.

    Sends all sampled frames to the vision model as a batch for
    coherent description of the video content.

    Args:
        frame_paths: List of paths to frame images
        prompt: Description prompt
        llm_config: LLM configuration (must support vision)
        max_image_dimension: Max dimension for frame images

    Returns:
        Visual description of the video content
    """
    from fichero_server.llm import vision

    if not frame_paths:
        return ""

    # Convert frames to data URIs
    image_uris = [
        file_to_data_uri(fp, max_dimension=max_image_dimension) for fp in frame_paths
    ]

    logger.info(f"Describing {len(image_uris)} frames with vision LLM")

    # Build a prompt that contextualizes the frames as video content
    frame_prompt = f"""These are {len(image_uris)} frames sampled from a video.

{prompt}

Describe the video content based on these frames, noting any progression or changes between frames."""

    text = await vision(
        images=image_uris,
        prompt=frame_prompt,
        config=llm_config,
    )

    return text.strip()


# =============================================================================
# Database Operations
# =============================================================================
#
# `save_artifact` here is `llm_base.save_file_artifact` (imported as that name
# above) — the single shared file-oriented wrapper around the canonical
# `llm_base.save_artifact`. Video no longer re-declares its own wrapper, so the
# per-page document-resolution contract (incl. the `document=` pass-through) is
# enforced in exactly one place and can never drift here.


# =============================================================================
# Cleanup Utilities
# =============================================================================


def _cleanup_temp_files(*paths: str) -> None:
    """Remove temporary files and directories."""

    for path in paths:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError as e:
            logger.warning(f"Failed to cleanup temp file {path}: {e}")


# =============================================================================
# Main Processing Function
# =============================================================================


async def process_video(
    files: list[str],
    documents: list[dict],
    prompt: str,
    llm_config: LLMConfig,
    library_path: str,
    task_id: str | None,
    tool_config: VideoToolConfig,
    *,
    # Video-specific (from VIDEO_CONFIG_SCHEMA)
    extract_audio: bool = True,
    frame_sample_rate: int = 1,
    max_frames: int = 10,
    max_image_dimension: int = 1024,
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
    """Process video files: frame analysis + audio transcription.

    This is the shared core function for all video tools.
    Extracts frames for vision analysis and audio for transcription,
    then combines both into a comprehensive description.

    Args:
        files: List of video file paths
        documents: Document metadata from source tools
        prompt: The prompt for frame description
        llm_config: LLM configuration (must support vision for frame analysis)
        library_path: Path to library database
        task_id: Workflow task ID
        tool_config: Tool-specific configuration
        extract_audio: Whether to extract and transcribe the audio track
        frame_sample_rate: Frames per second to sample
        max_frames: Maximum frames to analyze
        max_image_dimension: Max frame size for LLM
        whisper_model_size: Whisper model for audio transcription
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
        logger.warning("process_video: no input files — all selected IDs may be stale/invalid")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
        }

    # Override LLMConfig with user values if provided
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    # Build path -> document_id mapping
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                register_path_mapping(path_to_doc, doc["path"], doc.get("id"))
    logger.debug(
        f"process_video: {len(files)} files, extract_audio={extract_audio}, "
        f"frame_rate={frame_sample_rate}, max_frames={max_frames}"
    )

    # Build context section
    context_section = build_context_section(context, input_metadata)

    # Build reference section
    ref_section = build_reference_section(reference_values, match_mode)

    results = []
    texts = []
    values = []
    artifact_ids = []
    output_files = []

    for file_path in files:
        temp_files = []
        try:
            # 1. Extract and transcribe audio track
            audio_text = ""
            if extract_audio:
                try:
                    audio_path = file_path + ".audio.wav"
                    temp_files.append(audio_path)
                    await extract_audio_track(file_path, audio_path)
                    audio_text = await transcribe_with_whisper(
                        audio_path, whisper_model_size
                    )
                    logger.info(f"Audio transcription: {len(audio_text)} chars")
                except Exception as e:
                    logger.warning(f"Audio extraction failed for {file_path}: {e}")
                    audio_text = f"[Audio extraction failed: {e}]"

            # 2. Sample and describe frames with vision LLM
            visual_desc = ""
            try:
                frames = await sample_frames(file_path, frame_sample_rate, max_frames)
                if frames:
                    # Track frame directory for cleanup
                    if frames:
                        temp_files.append(os.path.dirname(frames[0]))

                    # Build prompt with context
                    frame_prompt = f"{context_section}{prompt}{ref_section}"
                    visual_desc = await describe_frames(
                        frames, frame_prompt, effective_config, max_image_dimension
                    )
                    logger.info(f"Visual description: {len(visual_desc)} chars")
            except Exception as e:
                logger.warning(f"Frame analysis failed for {file_path}: {e}")
                visual_desc = f"[Frame analysis failed: {e}]"

            # 3. Combine audio transcript + visual description
            sections = []
            if visual_desc and not visual_desc.startswith("["):
                sections.append(f"## Visual Description\n\n{visual_desc}")
            if audio_text and not audio_text.startswith("["):
                sections.append(f"## Audio Transcript\n\n{audio_text}")

            if not sections:
                # Both failed, include error messages
                combined = ""
                if visual_desc.startswith("["):
                    combined += visual_desc + "\n"
                if audio_text.startswith("["):
                    combined += audio_text
                text = combined.strip() or "No content could be extracted from video."
            else:
                text = "\n\n".join(sections)

            # Parse output according to format
            parsed = parse_output(text, output_format, output_options)

            result = {
                "file": file_path,
                "text": text,
                "value": parsed,
                "visual_description": visual_desc,
                "audio_transcript": audio_text,
            }

            # Save to database
            if save_to_db and library_path:
                artifact_id = await save_artifact(
                    file_path=file_path,
                    content=text,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=effective_config,
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
            logger.error(f"Video processing failed for {file_path}: {e}")
            results.append(
                {"file": file_path, "text": "", "value": None, "error": str(e)}
            )
            texts.append("")
            values.append(None)

        finally:
            # Cleanup temporary files
            _cleanup_temp_files(*temp_files)

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
