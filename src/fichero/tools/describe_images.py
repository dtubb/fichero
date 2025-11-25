"""
Visual Description Tool

Generates detailed visual descriptions of document images using Qwen VL Max vision model.
Based on transcribe_qwen_max.py pattern.
"""

import typer
import json
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from io import BytesIO
import base64
from openai import OpenAI
import concurrent.futures
from datetime import datetime
import time

# Import utilities
try:
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger

# Configure logger
tool_logger = get_tool_logger('describe_images')

# Visual description prompt
VISUAL_DESCRIPTION_PROMPT = """Analyze this document image in detail and provide a comprehensive visual description as JSON.

Include:
1. LAYOUT: Overall page structure, orientation, number of distinct regions
2. CONTENT_TYPE: Type of document (handwritten letter, typed document, photograph, legal document, etc.)
3. TEXT_REGIONS: Array of distinct text areas with:
   - location (top/center/bottom, left/center/right)
   - description (what this region contains)
   - characteristics (handwriting style, font type, formatting)

4. VISUAL_ELEMENTS:
   - colors: Array of prominent colors (paper color, ink color, highlights)
   - paper_condition: Physical state of the paper/material
   - writing_medium: Type of writing tool used (ink, pencil, typewriter, printed, etc.)
   - distinctive_features: Array of notable visual features (stamps, seals, watermarks, decorations, marginalia, etc.)

5. IMAGE_QUALITY:
   - resolution: high/medium/low
   - clarity: description of focus and readability
   - lighting: description of lighting conditions
   - completeness: is full document visible or cropped

6. ESTIMATED_ERA: Time period estimate based on visual characteristics (e.g., "late 19th century", "1920s-1930s", "modern")
7. PRESERVATION_NOTES: Any damage, wear, stains, repairs, foxing, tears visible
8. RAW_DESCRIPTION: A flowing 2-3 sentence description of what you see

Return ONLY valid JSON matching this structure:

{
  "layout": "description of overall structure",
  "content_type": "type of document",
  "text_regions": [
    {
      "location": "top-center",
      "description": "what this region contains",
      "characteristics": "style characteristics"
    }
  ],
  "visual_elements": {
    "colors": ["color1", "color2"],
    "paper_condition": "condition description",
    "writing_medium": "medium type",
    "distinctive_features": ["feature1", "feature2"]
  },
  "image_quality": {
    "resolution": "high/medium/low",
    "clarity": "clarity description",
    "lighting": "lighting description",
    "completeness": "completeness description"
  },
  "estimated_era": "time period estimate",
  "preservation_notes": "damage and condition notes",
  "raw_description": "2-3 sentence flowing description"
}

Return ONLY valid JSON. Say nothing else."""


def encode_image(image: Image.Image, max_size: int = 2048) -> str:
    """Encode image to base64 for API with configurable max size"""
    width, height = image.size
    aspect_ratio = max(width, height) / float(min(width, height))

    # Skip extremely wide/tall images
    if aspect_ratio > 200:
        tool_logger.warning(f"Skipping image with extreme aspect ratio: {aspect_ratio:.1f}")
        return ""

    # Resize image if needed
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        image = image.resize((new_width, new_height), Image.LANCZOS)
        tool_logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

    # Encode resized image with compression
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=80)
    encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
    size_kb = len(encoded) / 1024
    tool_logger.info(f"Encoded image size: {size_kb:.1f} KB")
    return encoded


def process_image_sync(file_path: Path, out_path: Path, api_key: str) -> dict:
    """Process a single image file synchronously to generate visual description"""
    # Ensure output directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert output path to .json extension
    out_path = out_path.with_suffix('.json')

    # Skip if already exists
    if out_path.exists():
        rel_path = SegmentHandler.get_relative_path(file_path)
        tool_logger.info(f"Skipping existing file: {rel_path}")
        return {
            "outputs": [str(rel_path.with_suffix('.json'))],
            "source": str(rel_path),
            "skipped": True,
            "success": True
        }

    out_path.touch()

    try:
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        tool_logger.info(f"[{timestamp}] Starting to process: {file_path.name}")

        # Load and process image
        try:
            image = Image.open(file_path).convert("RGB")
            orig_width, orig_height = image.size
            tool_logger.info(f"Original image size: {orig_width}x{orig_height}")
        except Exception as e:
            tool_logger.error(f"Failed to open image {file_path}: {e}")
            # Save error to JSON file
            error_data = {"error": f"Failed to open image: {e}"}
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2)
            return {
                "error": f"Failed to open image: {e}",
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

        # Initialize synchronous OpenAI client
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=180.0
        )

        # Encode image
        base64_image = encode_image(image, max_size=2048)
        if not base64_image:
            error_msg = "Failed to encode image"
            tool_logger.error(f"❌ {error_msg}")
            error_data = {"error": error_msg}
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2)
            return {
                "error": error_msg,
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

        # Call vision API
        max_retries = 3
        retry_delay = 1.0
        completion = None

        for attempt in range(max_retries):
            try:
                tool_logger.info(f"🌐 Calling Qwen VL Max (attempt {attempt + 1}/{max_retries}) for: {file_path.name}")

                completion = client.chat.completions.create(
                    model="qwen-vl-max",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                            {"type": "text", "text": VISUAL_DESCRIPTION_PROMPT}
                        ]
                    }],
                    temperature=0.1,  # Low temperature for consistent descriptions
                    timeout=180
                )
                tool_logger.info(f"✅ API call succeeded for: {file_path.name}")
                break

            except Exception as api_error:
                error_str = str(api_error).lower()
                is_auth_error = "401" in error_str or "unauthorized" in error_str

                if is_auth_error:
                    tool_logger.error(f"🔑 FATAL: Invalid API key error: {api_error}")
                    error_data = {"error": f"Invalid API key: {api_error}"}
                    with open(out_path, 'w', encoding='utf-8') as f:
                        json.dump(error_data, f, indent=2)
                    raise ValueError(f"Invalid API key - processing stopped: {api_error}")

                if attempt < max_retries - 1:
                    tool_logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                    tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    tool_logger.error(f"❌ API call failed after {max_retries} attempts: {api_error}")
                    error_data = {"error": f"API call failed: {api_error}"}
                    with open(out_path, 'w', encoding='utf-8') as f:
                        json.dump(error_data, f, indent=2)
                    return {
                        "error": str(api_error),
                        "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                        "source": str(SegmentHandler.get_relative_path(file_path))
                    }

        if not completion:
            error_msg = "Failed to get response from API"
            tool_logger.error(f"❌ {error_msg}")
            error_data = {"error": error_msg}
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2)
            return {
                "error": error_msg,
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        tool_logger.info(f"[{timestamp}] Received response from Qwen VL Max for: {file_path.name}")

        # Extract and parse description
        description_text = completion.choices[0].message.content

        try:
            description_json = json.loads(description_text)
        except json.JSONDecodeError as e:
            tool_logger.warning(f"Failed to parse JSON response, saving as raw text: {e}")
            description_json = {
                "raw_response": description_text,
                "parse_error": str(e)
            }

        # Save description as JSON
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(description_json, f, indent=2, ensure_ascii=False)

        # Create manifest entry
        rel_path = SegmentHandler.get_relative_path(file_path)
        result = {
            "outputs": [str(rel_path.with_suffix('.json'))],
            "source": str(rel_path),
            "visual_description": description_json,  # Full JSON in manifest
            "details": {
                "has_content": bool(description_json),
                "processed_at": datetime.now().isoformat(),
                "model": "qwen-vl-max",
                "original_size": f"{orig_width}x{orig_height}"
            }
        }

        return result

    except Exception as e:
        tool_logger.error(f"Error processing image {file_path}: {str(e)}")
        error_data = {"error": f"Processing error: {e}"}
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2)
        return {
            "error": str(e),
            "outputs": [str(SegmentHandler.get_relative_path(out_path))],
            "source": str(SegmentHandler.get_relative_path(file_path))
        }


def describe_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    testing: bool = False,
    api_key_cli: str = None,
    skip_processing: bool = False,
    **kwargs
) -> dict:
    """Batch visual description using Qwen VL Max model

    Args:
        source_folder: Source folder containing images
        source_manifest: Manifest file
        output_folder: Output folder for descriptions
        testing: Run on small subset of data
        api_key_cli: Qwen API key (falls back to env var)
        skip_processing: If True, create empty JSON files for fast testing

    Returns:
        Processing statistics dictionary
    """
    if skip_processing:
        tool_logger.info("⚡ SKIP MODE: Creating empty JSON files for testing")

        # Read manifest
        manifest_entries = []
        if Path(source_manifest).exists():
            with open(source_manifest, 'r') as f:
                for line in f:
                    if line.strip():
                        manifest_entries.append(json.loads(line))

        # Create output folder
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        # Create output manifest
        output_manifest_path = output_folder / "descriptions_manifest.jsonl"

        stats = {
            'total': len(manifest_entries),
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }

        with open(output_manifest_path, 'w') as manifest_file:
            for entry in manifest_entries:
                try:
                    # Get source path
                    source = entry.get('source') or (entry.get('outputs', [None])[0] if entry.get('outputs') else None)
                    if not source:
                        continue

                    # Create output path preserving structure
                    source_path = Path(source)
                    output_path = output_folder / "documents" / source_path.parent / f"{source_path.stem}.json"
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    # Create empty JSON file
                    stub_data = {"skip_processing": True}
                    output_path.write_text(json.dumps(stub_data, indent=2))

                    # Write manifest entry
                    manifest_entry = {
                        "source": source,
                        "outputs": [str(output_path.relative_to(output_folder))],
                        "visual_description": stub_data,
                        "processed_at": datetime.now().isoformat(),
                        "success": True,
                        "details": {"skip_processing": True}
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    stats['processed'] += 1

                except Exception as e:
                    tool_logger.error(f"Error creating empty JSON for {source}: {str(e)}")
                    manifest_entry = {
                        "source": source,
                        "outputs": [],
                        "processed_at": datetime.now().isoformat(),
                        "success": False,
                        "error": str(e)
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    stats['failed'] += 1

        tool_logger.success(f"⚡ Skip mode complete: {stats['processed']} empty JSON files created")
        return stats

    # Normal processing path - using async DashScopeProvider
    tool_logger.info(f"[green]Describing images in {source_folder}")
    tool_logger.info(f"[cyan]Using model qwen-vl-max with async batch processing")

    load_dotenv()

    # Get API key
    api_key = get_qwen_key(api_key_cli)
    if not api_key:
        raise ValueError("Qwen API key required")

    # Read manifest to get list of images to process
    manifest_entries = []
    if Path(source_manifest).exists():
        with open(source_manifest, 'r') as f:
            for line in f:
                if line.strip():
                    manifest_entries.append(json.loads(line))

    if not manifest_entries:
        tool_logger.warning("No entries found in manifest")
        return {
            'total': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }

    # Build list of image paths to process
    image_paths = []
    for entry in manifest_entries:
        # Get source path from entry
        source = entry.get('source') or (entry.get('outputs', [None])[0] if entry.get('outputs') else None)
        if not source:
            continue

        # Resolve full path
        source_path = Path(source)
        if source_folder:
            base_str = str(source_folder)
            if "_staging" in base_str and "documents" not in base_str.lower():
                full_path = source_folder / "documents" / source_path
            else:
                full_path = source_folder / source_path
        else:
            full_path = source_path

        if full_path.exists():
            image_paths.append(full_path)
        else:
            tool_logger.warning(f"Image not found: {full_path}")

    if not image_paths:
        tool_logger.warning("No valid images found to process")
        return {
            'total': len(manifest_entries),
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }

    tool_logger.info(f"Found {len(image_paths)} images to process")

    # Import async components
    from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
    from fichero.tools.transcribe_providers.async_batch_processor import run_async_batch

    # Create provider with VISUAL_DESCRIPTION_PROMPT instead of OCR prompt
    provider = DashScopeProvider(
        api_key=api_key,
        model="qwen-vl-max",
        prompt=VISUAL_DESCRIPTION_PROMPT,  # Use description prompt
        max_size=2048,
        timeout=180.0
    )

    # Create output folder
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    output_docs_folder = output_folder / "documents"
    output_docs_folder.mkdir(parents=True, exist_ok=True)

    # Process all images using async batch processor
    tool_logger.info(f"🚀 Starting async batch processing with 15 concurrent requests")
    async_results = run_async_batch(
        provider=provider,
        image_paths=image_paths,
        output_folder=output_docs_folder,
        max_concurrent=15,  # Higher than ThreadPoolExecutor's 5 workers
        skip_existing=True,
        cleanup_provider=True
    )

    # Create output manifest
    output_manifest_path = output_folder / "descriptions_manifest.jsonl"

    stats = {
        'total': len(image_paths),
        'processed': 0,
        'failed': 0,
        'skipped': 0
    }

    # Convert async results to describe_images format and write manifest
    with open(output_manifest_path, 'w') as manifest_file:
        for i, async_result in enumerate(async_results):
            image_path = image_paths[i]

            try:
                # Get relative path
                rel_path = SegmentHandler.get_relative_path(image_path)
                json_rel_path = rel_path.with_suffix('.json')

                # Build output path preserving structure
                json_output_path = output_docs_folder / json_rel_path.parent / json_rel_path.name
                json_output_path.parent.mkdir(parents=True, exist_ok=True)

                # Check if skipped (already existed)
                if async_result.get("skipped"):
                    stats['skipped'] += 1
                    manifest_entry = {
                        "source": str(rel_path),
                        "outputs": [str(json_rel_path)],
                        "skipped": True,
                        "success": True
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    continue

                # Check for errors
                if not async_result.get("success") or async_result.get("error"):
                    stats['failed'] += 1
                    error_msg = async_result.get("error", "Unknown error")

                    # Save error to JSON file
                    error_data = {"error": error_msg}
                    with open(json_output_path, 'w', encoding='utf-8') as f:
                        json.dump(error_data, f, indent=2)

                    manifest_entry = {
                        "source": str(rel_path),
                        "outputs": [str(json_rel_path)],
                        "error": error_msg,
                        "success": False,
                        "processed_at": datetime.now().isoformat()
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    continue

                # Success case - parse the description
                description_text = async_result.get("text", "")

                try:
                    description_json = json.loads(description_text)
                except json.JSONDecodeError as e:
                    tool_logger.warning(f"Failed to parse JSON response for {image_path.name}, saving as raw text: {e}")
                    description_json = {
                        "raw_response": description_text,
                        "parse_error": str(e)
                    }

                # Save description as JSON
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(description_json, f, indent=2, ensure_ascii=False)

                # Get original image dimensions
                try:
                    from PIL import Image
                    image = Image.open(image_path)
                    orig_width, orig_height = image.size
                    original_size = f"{orig_width}x{orig_height}"
                except:
                    original_size = "unknown"

                # Create manifest entry
                manifest_entry = {
                    "source": str(rel_path),
                    "outputs": [str(json_rel_path)],
                    "visual_description": description_json,
                    "success": True,
                    "details": {
                        "has_content": bool(description_json),
                        "processed_at": datetime.now().isoformat(),
                        "model": "qwen-vl-max",
                        "original_size": original_size
                    }
                }
                manifest_file.write(json.dumps(manifest_entry) + "\n")
                stats['processed'] += 1

            except Exception as e:
                tool_logger.error(f"Error creating manifest entry for {image_path}: {str(e)}")
                stats['failed'] += 1
                manifest_entry = {
                    "source": str(SegmentHandler.get_relative_path(image_path)),
                    "outputs": [],
                    "error": str(e),
                    "success": False,
                    "processed_at": datetime.now().isoformat()
                }
                manifest_file.write(json.dumps(manifest_entry) + "\n")

    tool_logger.success(
        f"✅ Visual description complete: {stats['processed']} processed, "
        f"{stats['skipped']} skipped, {stats['failed']} failed"
    )

    return stats


def describe(
    source_folder: Path = typer.Argument(..., help="Input source images folder"),
    source_manifest: Path = typer.Argument(..., help="Input source manifest"),
    output_folder: Path = typer.Argument(..., help="Output folder for descriptions"),
    testing: bool = typer.Option(False, help="Run on a small subset of data"),
    api_key: str = typer.Option(None, "--api-key", help="Qwen API key"),
    skip_processing: bool = typer.Option(False, "--skip-processing", help="Skip processing, create stub files"),
):
    """Batch visual description CLI using Qwen VL Max model"""
    describe_batch(
        source_folder,
        source_manifest,
        output_folder,
        testing,
        api_key,
        skip_processing
    )


def main():
    """Main CLI entry point"""
    typer.run(describe)


if __name__ == "__main__":
    main()
