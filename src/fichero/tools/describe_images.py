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

    # Normal processing path
    tool_logger.info(f"[green]Describing images in {source_folder}")
    tool_logger.info(f"[cyan]Using model qwen-vl-max")

    load_dotenv()

    # Get API key
    api_key = get_qwen_key(api_key_cli)
    if not api_key:
        raise ValueError("Qwen API key required")

    # Create batch processor
    class VisualDescriptionProcessor(BatchProcessor):
        def __init__(self, *args, api_key=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.api_key = api_key

        def process_batch_parallel(self, batch: list):
            """Process a batch of files using parallel processing"""
            tool_logger.info(f"⚡ Starting parallel processing for {len(batch)} files")

            # Prepare file tasks
            file_tasks = []
            for doc in batch:
                path = Path(doc["path"])

                # Use base folder directly
                if self.base_folder:
                    base_str = str(self.base_folder)
                    if "_staging" in base_str and "documents" not in base_str.lower():
                        full_path = self.base_folder / "documents" / path
                    else:
                        full_path = self.base_folder / path
                else:
                    full_path = path

                # Create output path
                parts = path.parts
                if 'documents' in parts:
                    rel_path = Path(*parts[parts.index('documents') + 1:])
                else:
                    rel_path = path
                out_path = self.output_folder / "documents" / rel_path

                file_tasks.append((full_path, out_path, self.api_key))

            if not file_tasks:
                tool_logger.warning("⚠️ No tasks created for batch")
                return []

            # Process using ThreadPoolExecutor
            max_workers = min(5, len(file_tasks))
            tool_logger.info(f"🧵 Using ThreadPoolExecutor with {max_workers} workers")

            results = []
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_path = {
                        executor.submit(process_image_sync, full_path, out_path, api_key): full_path
                        for full_path, out_path, api_key in file_tasks
                    }

                    for future in concurrent.futures.as_completed(future_to_path):
                        file_path = future_to_path[future]
                        try:
                            result = future.result()
                            results.append(result)
                            tool_logger.info(f"✅ Completed processing: {file_path.name}")
                        except Exception as e:
                            tool_logger.error(f"❌ Failed processing {file_path.name}: {e}")
                            results.append({
                                "error": str(e),
                                "outputs": [],
                                "source": str(file_path)
                            })
            except RuntimeError as e:
                if "cannot schedule new futures after interpreter shutdown" in str(e):
                    tool_logger.warning(f"⚠️ ThreadPoolExecutor unavailable, falling back to sequential processing")
                    for full_path, out_path, api_key in file_tasks:
                        try:
                            result = process_image_sync(full_path, out_path, api_key)
                            results.append(result)
                            tool_logger.info(f"✅ Completed processing: {full_path.name}")
                        except Exception as file_error:
                            tool_logger.error(f"❌ Failed processing {full_path.name}: {file_error}")
                            results.append({
                                "error": str(file_error),
                                "outputs": [],
                                "source": str(full_path)
                            })
                    return results
                else:
                    raise

            tool_logger.info(f"✅ Parallel processing complete, got {len(results)} results")
            return results

        def _process_batch(self, batch: list, stats: dict):
            """Override to use parallel processing"""
            batch_start = time.time()

            tool_logger.info("🚀 Using unified parallel processing")
            results = self.process_batch_parallel(batch)

            batch_time = time.time() - batch_start
            tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")

            # Process results
            for result in results:
                if isinstance(result, dict):
                    self.output_proc.save_entry(result)
                    if result.get("error"):
                        stats["failed"] += 1
                    elif result.get("skipped"):
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1

    # Use the batch processor
    process_name = output_folder.name if output_folder.name else "visual_description"

    processor = VisualDescriptionProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name=process_name,
        processor_fn=None,
        base_folder=source_folder,
        batch_size=5,
        api_key=api_key
    )

    return processor.process()


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
