"""
Transcribe Tool

Extracts text from images using vision LLM or Apple Vision (on-device OCR).
Saves results to Artifact and updates Document.page_content.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Apple Vision OCR (macOS native)
# =============================================================================

def _apple_vision_ocr(image_path: str, language: str = "en") -> str:
    """Extract text from image using macOS Vision framework.

    Uses VNRecognizeTextRequest for on-device OCR.
    """
    try:
        import Vision
        from Quartz import (
            CGImageSourceCreateWithURL,
            CGImageSourceCreateImageAtIndex,
            CGImageSourceCopyPropertiesAtIndex,
        )
        from Foundation import NSURL
        import os

        # Verify file exists and is readable
        if not os.path.exists(image_path):
            raise ValueError(f"File not found: {image_path}")
        if not os.access(image_path, os.R_OK):
            raise ValueError(f"File not readable: {image_path}")

        # Check for iCloud/cloud storage dataless files (SF_DATALESS flag)
        try:
            stat_info = os.stat(image_path)
            # SF_DATALESS = 0x40000000 - file data is not locally present
            if hasattr(stat_info, 'st_flags') and (stat_info.st_flags & 0x40000000):
                raise ValueError(
                    f"File is stored in iCloud/cloud and not downloaded locally. "
                    f"Please download the file first: {image_path}"
                )
            # Also check if blocks is 0 (another indicator of dataless file)
            if stat_info.st_blocks == 0 and stat_info.st_size > 0:
                raise ValueError(
                    f"File appears to be a cloud placeholder (0 blocks, {stat_info.st_size} bytes). "
                    f"Please download the file locally first: {image_path}"
                )
        except OSError:
            pass  # stat failed, continue anyway

        # Load image
        url = NSURL.fileURLWithPath_(image_path)
        image_source = CGImageSourceCreateWithURL(url, None)
        if not image_source:
            # Get file size for diagnostics
            file_size = os.path.getsize(image_path)
            raise ValueError(f"Could not load image source (file size: {file_size} bytes): {image_path}")

        # Get image properties for diagnostics
        props = CGImageSourceCopyPropertiesAtIndex(image_source, 0, None)
        if props:
            width = props.get("PixelWidth", "?")
            height = props.get("PixelHeight", "?")
            color_model = props.get("ColorModel", "?")
            logger.debug(f"Image properties: {width}x{height}, color model: {color_model}")

        cg_image = CGImageSourceCreateImageAtIndex(image_source, 0, None)
        if not cg_image:
            # Provide more diagnostic info
            file_size = os.path.getsize(image_path)
            color_info = f", color model: {props.get('ColorModel', '?')}" if props else ""
            raise ValueError(
                f"CGImage creation failed (file size: {file_size} bytes{color_info}). "
                f"Image may be corrupted, CMYK, or unsupported format: {image_path}"
            )

        # Create text recognition request
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

        # Set language hints
        lang_map = {"en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "pt": "pt-BR"}
        recognition_langs = [lang_map.get(language, language)]
        request.setRecognitionLanguages_(recognition_langs)

        # Create handler and perform request
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success = handler.performRequests_error_([request], None)

        if not success:
            raise ValueError("Vision request failed")

        # Extract results
        results = request.results()
        if not results:
            return ""

        # Combine all recognized text
        lines = []
        for observation in results:
            if hasattr(observation, 'topCandidates_'):
                candidates = observation.topCandidates_(1)
                if candidates:
                    lines.append(candidates[0].string())

        return "\n".join(lines)

    except ImportError as e:
        logger.error(f"Apple Vision framework not available: {e}")
        raise ValueError("Apple Vision OCR requires macOS with Vision framework")
    except Exception as e:
        logger.error(f"Apple Vision OCR failed: {e}")
        raise


async def _apple_vision_ocr_async(image_path: str, language: str = "en") -> str:
    """Async wrapper for Apple Vision OCR."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _apple_vision_ocr, image_path, language)


# =============================================================================
# Prompt Building (defined first so decorator can use it)
# =============================================================================

def _build_transcription_prompt(language: str, return_boxes: bool) -> str:
    """Build the transcription prompt."""
    prompt = f"""Extract and transcribe all text from this image.

Language: {language}

Instructions:
- Preserve the original text layout and structure
- Include all visible text, including headers, labels, and annotations
- If text is handwritten, transcribe as accurately as possible
- If text is unclear, indicate with [unclear]
- Maintain paragraph breaks and list formatting
"""

    if return_boxes:
        prompt += """
Additionally, provide bounding box coordinates for each text region in JSON format:
{
    "text": "transcribed text here",
    "boxes": [
        {"text": "...", "x": 0, "y": 0, "width": 100, "height": 20},
        ...
    ]
}
"""
    else:
        prompt += "\nOutput only the transcribed text."

    return prompt


def build_transcribe_prompt(config: dict) -> str:
    """Build the transcription prompt from config.

    This is exposed to the UI so users can see and edit the prompt.
    """
    language = config.get("language", "en")
    return_boxes = config.get("return_boxes", False)
    return _build_transcription_prompt(language, return_boxes)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="transcribe",
    display_name="Transcribe",
    description="Extract text from images using vision LLM. Saves results to database.",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True, description="Image files to transcribe"),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False, description="Document metadata (from source tools) for saving results"),
    ],
    output_ports=[
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT, description="Combined transcribed text"),
        PortDef(id="texts", name="Texts", port_type="output", data_type=DataType.ARRAY, description="Array of individual transcriptions"),
        PortDef(id="structured", name="Structured", port_type="output", data_type=DataType.JSON, description="Full results with file info"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "language": {"type": "string", "default": "en", "description": "Language hint for transcription"},
        "return_boxes": {"type": "boolean", "default": False, "description": "Return bounding boxes for text regions"},
        "prompt": {"type": "string", "description": "Custom prompt (overrides default)"},
        "save_to_db": {"type": "boolean", "default": True, "description": "Save transcription to document in database"},
        "update_page_content": {"type": "boolean", "default": True, "description": "Update Document.page_content for search"},
        "max_image_dimension": {"type": "integer", "default": 2048, "description": "Maximum image dimension (0 = no resize, larger images are downscaled)"},
    },
    default_output_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Combined transcribed text"},
            "texts": {"type": "array", "items": {"type": "string"}, "description": "Individual texts per file"},
        }
    },
    # Default prompt shown in UI (with default config)
    default_prompt=_build_transcription_prompt("en", False),
    # Dynamic prompt builder based on config
    prompt_builder=build_transcribe_prompt,
)
async def transcribe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract text from images using vision LLM.

    Args:
        inputs: Resolved inputs from workflow
            - files: List of image file paths
            - documents: Optional document metadata (from source tools)
            - language: Language hint (default: "en")
            - return_boxes: Whether to return bounding boxes
            - prompt: Custom prompt override
            - save_to_db: Whether to save results to database
            - update_page_content: Whether to update Document.page_content
        state: Current workflow state (for context)
        llm_config: LLM configuration for vision call

    Returns:
        Dict with transcribed text and optional bounding boxes
    """
    logger.info(f">>> TRANSCRIBE FUNCTION CALLED <<<")
    # Get resolved inputs (already resolved by builder from $.paths)
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])  # Document metadata from source tools
    language = inputs.get("language", "en")
    return_boxes = inputs.get("return_boxes", False)
    prompt_override = inputs.get("prompt")
    save_to_db = inputs.get("save_to_db", True)
    update_page_content = inputs.get("update_page_content", True)
    vision_mode = inputs.get("vision_mode", "llm")  # "apple" or "llm"
    max_image_dimension = inputs.get("max_image_dimension", 2048)

    logger.info(f"Transcribe: vision_mode={vision_mode}, language={language}, max_dimension={max_image_dimension}")

    # Get library path for database access
    library_path = state.get("library_path", "")

    # Ensure files is a list
    if isinstance(files, str):
        files = [files]

    if not files:
        return {"text": "", "texts": [], "artifacts": [], "error": "No input files provided"}

    # Build a path -> document_id mapping from documents
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                path_to_doc[doc["path"]] = doc.get("id")

    # Build prompt
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = _build_transcription_prompt(language, return_boxes)

    # Process images
    results = []
    texts = []
    artifact_ids = []

    for file_path in files:
        try:
            # Use Apple Vision or LLM based on vision_mode
            if vision_mode == "apple":
                # On-device OCR using macOS Vision framework
                logger.info(f"Using Apple Vision OCR for: {file_path}")
                text = await _apple_vision_ocr_async(file_path, language)
            else:
                # Convert file to base64 data URI for LLM (with optional resizing)
                image_uri = _file_to_data_uri(file_path, max_dimension=max_image_dimension)

                # Call vision LLM
                text = await vision(
                    images=[image_uri],
                    prompt=prompt,
                    config=llm_config,
                )

            result = {
                "file": file_path,
                "text": text,
            }

            # Save to database if enabled and we have library_path
            if save_to_db and library_path:
                artifact_id = await _save_transcription(
                    file_path=file_path,
                    text=text,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=llm_config,
                    workflow_id=state.get("workflow_id"),
                    task_id=state.get("task_id"),
                    update_page_content=update_page_content,
                )
                if artifact_id:
                    result["artifact_id"] = artifact_id
                    artifact_ids.append(artifact_id)

            results.append(result)
            texts.append(text)

        except Exception as e:
            logger.error(f"Failed to transcribe {file_path}: {e}")
            results.append({
                "file": file_path,
                "text": "",
                "error": str(e),
            })
            texts.append("")

    # Check for errors - propagate to top level for parallel processing detection
    errors = [r.get("error") for r in results if r.get("error")]
    error_msg = None
    if errors:
        # In single-file mode (parallel processing), return error at top level
        if len(files) == 1:
            error_msg = errors[0]
        else:
            # In multi-file mode, summarize errors
            error_msg = f"{len(errors)}/{len(files)} files failed: {errors[0]}"

    # Return structured output
    return {
        "text": "\n\n".join(texts),       # Combined text
        "texts": texts,                     # Individual texts (for [*] access)
        "results": results,                 # Full results with file info
        "artifacts": artifact_ids,          # Created artifact IDs
        "boxes": None,                      # TODO: Parse boxes if return_boxes
        "error": error_msg,                 # Top-level error for parallel detection
    }


async def _save_transcription(
    file_path: str,
    text: str,
    document_id: str | None,
    library_path: str,
    llm_config: LLMConfig,
    workflow_id: str | None,
    task_id: str | None,
    update_page_content: bool = True,
) -> str | None:
    """Save transcription to database.

    Creates an Artifact and optionally updates Document.page_content.

    Returns:
        Artifact ID if saved successfully, None otherwise
    """
    try:
        from fichero.db import db_manager
        from fichero.models import Document, Artifact, Status

        db = db_manager.get_database(library_path)

        # Find document by ID or path
        doc = None
        if document_id:
            doc = db.get(Document, document_id)
        if not doc:
            # Try to find by path
            docs = db.query(Document, path=file_path)
            if docs:
                doc = docs[0]

        if not doc:
            logger.warning(f"Document not found for path: {file_path}")
            return None

        # Create Artifact
        artifact = Artifact(
            document_id=doc.id,
            artifact_type="transcription",
            content=text,
            provider=llm_config.provider,
            model=llm_config.model,
            run_id=task_id,
        )
        db.save(artifact)
        logger.info(f"Created transcription artifact {artifact.id} for document {doc.id}")

        # Update Document.page_content for search indexing
        if update_page_content:
            doc.page_content = text
            doc.status = Status.completed
            doc.updated_at = datetime.now()
            db.save(doc)

            # Trigger re-embedding for search
            db.embed(doc)
            logger.info(f"Updated page_content and embedding for document {doc.id}")

        return artifact.id

    except Exception as e:
        logger.error(f"Failed to save transcription for {file_path}: {e}")
        return None


def _file_to_data_uri(file_path: str, max_dimension: int = 2048) -> str:
    """Convert a file to a base64 data URI with optional resizing.

    Args:
        file_path: Path to image file
        max_dimension: Maximum width/height (default 2048px). Set to 0 to disable resizing.

    Returns:
        Base64 data URI
    """
    from PIL import Image
    import io

    logger.info(f"Converting to data URI: {Path(file_path).name} (max_dimension={max_dimension})")
    path = Path(file_path)

    # Determine MIME type
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    # Resize if needed (reduces API timeout issues with large scans)
    if max_dimension > 0:
        try:
            img = Image.open(path)
            original_size = img.size

            # Only resize if larger than max_dimension
            if img.width > max_dimension or img.height > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                logger.info(f"Resized image {path.name}: {original_size} -> {img.size}")

            # Convert to bytes
            buffer = io.BytesIO()
            img_format = "JPEG" if mime_type == "image/jpeg" else "PNG"
            img.save(buffer, format=img_format, quality=95)
            data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to resize {path.name}, using original: {e}")
            # Fallback to original file
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
    else:
        # No resizing - use original file
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"
