import typer
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from io import BytesIO
import base64
from openai import OpenAI
import concurrent.futures
from datetime import datetime
import time
import json
import srsly
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Any

# Import utilities
try:
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.files import ensure_dirs
except ImportError:
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.files import ensure_dirs

# Configure tool_logger
tool_logger = get_tool_logger('convert_to_svg')

# SVG Generation Prompts
SVG_DRAFT_PROMPT = """You are an expert at creating semantic SVG documents. Given a document image, its transcription, and metadata, create a complete SVG file.

The SVG should:
1. Embed the image as a base64 data URI in the background layer
2. Create text overlay layers positioned to match the original document text regions
3. Include RDF metadata with all available document information
4. Use proper SVG structure with layers for image, text, and metadata
5. Make text searchable and selectable
6. Use appropriate fonts and styling

CONTEXT:
- Image dimensions: {width}x{height}
- Transcription: {transcription}
- Visual description: {visual_description}
- Library metadata: {library_metadata}

Return ONLY the complete SVG XML, starting with <?xml version="1.0"?> and nothing else."""

SVG_CRITIQUE_PROMPT = """Review this SVG document for quality and correctness. Identify any issues with:
1. XML syntax errors
2. Text positioning and readability
3. Metadata completeness
4. SVG structure and organization
5. Missing or incorrect elements
6. Text layer accuracy compared to transcription

Current SVG:
{svg_content}

Original transcription:
{transcription}

Provide specific, actionable feedback in JSON format:
{{
  "syntax_issues": ["list of XML syntax problems"],
  "positioning_issues": ["text positioning problems"],
  "metadata_issues": ["missing or incorrect metadata"],
  "structure_issues": ["SVG structure problems"],
  "text_accuracy_issues": ["text content mismatches"],
  "recommendations": ["specific improvements to make"]
}}

Return ONLY valid JSON."""

SVG_FINAL_PROMPT = """Based on this critique, create an improved SVG document:

CRITIQUE:
{critique}

ORIGINAL SVG:
{original_svg}

REQUIREMENTS:
- Fix all identified issues
- Ensure valid XML syntax
- Improve text positioning and readability
- Complete all metadata fields
- Verify text accuracy against transcription: {transcription}

Return ONLY the complete improved SVG XML, starting with <?xml version="1.0"?> and nothing else."""


def encode_image(image: Image.Image, max_size: int = 1024) -> str:
    """Encode image to base64 for API"""
    width, height = image.size
    aspect_ratio = max(width, height) / float(min(width, height))

    if aspect_ratio > 200:
        tool_logger.warning(f"Skipping image with extreme aspect ratio: {aspect_ratio:.1f}")
        return ""

    # Resize if needed
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        image = image.resize((new_width, new_height), Image.LANCZOS)

    # Encode
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=80)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def clean_svg_xml(svg_content: str) -> str:
    """Clean up SVG XML to fix common issues"""
    try:
        # Remove markdown code blocks if present
        svg_content = re.sub(r'^```xml\s*', '', svg_content, flags=re.MULTILINE)
        svg_content = re.sub(r'^```\s*$', '', svg_content, flags=re.MULTILINE)
        svg_content = svg_content.strip()

        # Ensure it starts with XML declaration
        if not svg_content.startswith('<?xml'):
            svg_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg_content

        # Fix common XML issues
        svg_content = svg_content.replace('&', '&amp;')
        svg_content = svg_content.replace('&amp;amp;', '&amp;')  # Don't double-escape

        # Try to parse and re-serialize for validation
        try:
            root = ET.fromstring(svg_content.encode('utf-8'))
            # Successfully parsed - return cleaned version
            return svg_content
        except ET.ParseError as e:
            tool_logger.warning(f"SVG XML parse error: {e}, returning as-is")
            return svg_content

    except Exception as e:
        tool_logger.warning(f"Error cleaning SVG XML: {e}")
        return svg_content


def call_qwen_text(client: OpenAI, prompt: str, model: str = "qwen-max") -> str:
    """Call Qwen for text-only generation"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [{"type": "text", "text": prompt}]
            }],
            timeout=180
        )
        return response.choices[0].message.content
    except Exception as e:
        tool_logger.error(f"Qwen text call failed: {e}")
        raise


def call_qwen_vision(client: OpenAI, prompt: str, image_base64: str, model: str = "qwen-vl-max") -> str:
    """Call Qwen VL Max for vision + text generation"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            timeout=180
        )
        return response.choices[0].message.content
    except Exception as e:
        tool_logger.error(f"Qwen vision call failed: {e}")
        raise


def generate_svg_3step(
    image: Image.Image,
    transcription: str,
    visual_description: Dict,
    library_metadata: Dict,
    api_key: str
) -> str:
    """Generate SVG using 3-step process: draft -> critique -> final"""

    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        timeout=180.0
    )

    width, height = image.size
    image_base64 = encode_image(image, max_size=1024)

    if not image_base64:
        raise ValueError("Failed to encode image")

    # Step 1: Generate draft SVG
    tool_logger.info("🎨 Step 1: Generating draft SVG with Qwen VL Max")

    visual_desc_str = json.dumps(visual_description, indent=2) if visual_description else "None"
    metadata_str = json.dumps(library_metadata, indent=2) if library_metadata else "None"

    draft_prompt = SVG_DRAFT_PROMPT.format(
        width=width,
        height=height,
        transcription=transcription,
        visual_description=visual_desc_str,
        library_metadata=metadata_str
    )

    draft_svg = call_qwen_vision(client, draft_prompt, image_base64)
    draft_svg = clean_svg_xml(draft_svg)

    tool_logger.info(f"✅ Draft SVG generated ({len(draft_svg)} chars)")

    # Step 2: Critique the SVG
    tool_logger.info("🔍 Step 2: Critiquing SVG with Qwen Max")

    critique_prompt = SVG_CRITIQUE_PROMPT.format(
        svg_content=draft_svg[:10000],  # Limit to first 10k chars for critique
        transcription=transcription
    )

    critique_response = call_qwen_text(client, critique_prompt, model="qwen-max")

    try:
        critique = json.loads(critique_response)
        tool_logger.info(f"✅ Critique received: {len(critique.get('recommendations', []))} recommendations")
    except json.JSONDecodeError:
        tool_logger.warning("Critique response not valid JSON, using as-is")
        critique = {"recommendations": [critique_response]}

    # Step 3: Generate final improved SVG
    tool_logger.info("✨ Step 3: Generating final improved SVG")

    final_prompt = SVG_FINAL_PROMPT.format(
        critique=json.dumps(critique, indent=2),
        original_svg=draft_svg[:10000],  # Limit for context
        transcription=transcription
    )

    final_svg = call_qwen_text(client, final_prompt, model="qwen-max")
    final_svg = clean_svg_xml(final_svg)

    tool_logger.info(f"✅ Final SVG generated ({len(final_svg)} chars)")

    return final_svg


def process_document_to_svg(
    file_path: Path,
    out_path: Path,
    api_key: str,
    transcription: str,
    visual_description: Dict,
    library_metadata: Dict
) -> dict:
    """Process a single document to SVG"""

    # Ensure output directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert output path to .svg extension
    out_path = out_path.with_suffix('.svg')

    # Skip if already exists
    if out_path.exists():
        rel_path = SegmentHandler.get_relative_path(file_path)
        tool_logger.info(f"Skipping existing file: {rel_path}")
        return {
            "outputs": [str(rel_path.with_suffix('.svg'))],
            "source": str(rel_path),
            "skipped": True,
            "success": True
        }

    try:
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        tool_logger.info(f"[{timestamp}] Processing: {file_path.name}")

        # Load image
        try:
            image = Image.open(file_path).convert("RGB")
            width, height = image.size
            tool_logger.info(f"Image size: {width}x{height}")
        except Exception as e:
            tool_logger.error(f"Failed to open image {file_path}: {e}")
            return {
                "error": f"Failed to open image: {e}",
                "outputs": [],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

        # Generate SVG with 3-step process
        svg_content = generate_svg_3step(
            image,
            transcription,
            visual_description,
            library_metadata,
            api_key
        )

        # Save SVG
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        tool_logger.success(f"✅ Saved SVG: {out_path}")

        # Create manifest entry
        rel_path = SegmentHandler.get_relative_path(file_path)
        result = {
            "source": str(rel_path),
            "outputs": [str(rel_path.with_suffix('.svg'))],
            "svg_file": str(out_path.relative_to(out_path.parent.parent)),
            "processed_at": datetime.now().isoformat(),
            "success": True,
            "details": {
                "svg_size": f"{width}x{height}",
                "svg_length": len(svg_content),
                "has_transcription": bool(transcription.strip()),
                "has_visual_description": bool(visual_description),
                "has_library_metadata": bool(library_metadata),
                "model": "qwen-vl-max + qwen-max (3-step)"
            },
            "svg_content": svg_content  # Save full SVG in manifest
        }

        return result

    except Exception as e:
        tool_logger.error(f"Error processing {file_path}: {e}")
        return {
            "error": str(e),
            "outputs": [],
            "source": str(SegmentHandler.get_relative_path(file_path))
        }


def load_transcription(source_file: str, transcription_manifest: Path, transcription_folder: Path) -> str:
    """Load transcription for a source file"""
    try:
        if not transcription_manifest.exists():
            return ""

        # Read manifest to find transcription file
        with open(transcription_manifest, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get('source') == source_file or entry.get('source') == str(Path(source_file)):
                    # Get transcription file path
                    outputs = entry.get('outputs', [])
                    if outputs:
                        trans_file = transcription_folder / outputs[0]
                        if trans_file.exists():
                            return trans_file.read_text(encoding='utf-8')
        return ""
    except Exception as e:
        tool_logger.warning(f"Failed to load transcription for {source_file}: {e}")
        return ""


def load_visual_description(source_file: str, visual_manifest: Path) -> Dict:
    """Load visual description for a source file"""
    try:
        if not visual_manifest or not visual_manifest.exists():
            return {}

        with open(visual_manifest, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get('source') == source_file:
                    return entry.get('visual_description', {})
        return {}
    except Exception as e:
        tool_logger.warning(f"Failed to load visual description for {source_file}: {e}")
        return {}


def load_library_metadata(source_file: str, metadata_manifest: Path) -> Dict:
    """Load library metadata for a source file"""
    try:
        if not metadata_manifest or not metadata_manifest.exists():
            return {}

        with open(metadata_manifest, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get('source') == source_file:
                    return entry.get('library_metadata', {})
        return {}
    except Exception as e:
        tool_logger.warning(f"Failed to load library metadata for {source_file}: {e}")
        return {}


def convert_to_svg_batch(
    source_folder: Path,
    source_manifest: Path,
    transcription_folder: Path,
    transcription_manifest: Path,
    output_folder: Path,
    metadata_manifest: Optional[Path] = None,
    visual_descriptions_manifest: Optional[Path] = None,
    api_key_cli: str = None,
    skip_processing: bool = False,
    **kwargs
) -> Dict[str, int]:
    """
    Convert documents to semantic SVG using 3-step Qwen process

    Args:
        source_folder: Source folder containing images
        source_manifest: Source manifest file
        transcription_folder: Folder containing transcriptions
        transcription_manifest: Transcription manifest file
        output_folder: Output folder for SVG files
        metadata_manifest: Optional library metadata manifest
        visual_descriptions_manifest: Optional visual descriptions manifest
        api_key_cli: Qwen API key
        skip_processing: Create stub SVG files for testing

    Returns:
        Processing statistics dictionary
    """
    # Safely handle paths
    import os
    source_folder = Path(os.path.expanduser(str(source_folder))).resolve()
    source_manifest = Path(os.path.expanduser(str(source_manifest))).resolve()
    transcription_folder = Path(os.path.expanduser(str(transcription_folder))).resolve()
    transcription_manifest = Path(os.path.expanduser(str(transcription_manifest))).resolve()
    output_folder = Path(os.path.expanduser(str(output_folder))).resolve()

    if metadata_manifest:
        metadata_manifest = Path(os.path.expanduser(str(metadata_manifest))).resolve()
    if visual_descriptions_manifest:
        visual_descriptions_manifest = Path(os.path.expanduser(str(visual_descriptions_manifest))).resolve()

    tool_logger.progress(f"Converting documents to SVG from: {source_manifest}")

    # Output manifest path
    output_manifest = output_folder / "svg_manifest.jsonl"
    ensure_dirs(output_manifest)

    # Statistics
    stats = {
        "processed_files": 0,
        "failed": 0,
        "skipped": 0,
        "success": True
    }

    # Skip processing mode
    if skip_processing:
        tool_logger.info("Skip processing mode - creating placeholder SVG files")

        if not source_manifest.exists():
            tool_logger.error(f"Source manifest not found: {source_manifest}")
            stats["success"] = False
            return stats

        try:
            source_entries = list(srsly.read_jsonl(source_manifest))
        except Exception as e:
            tool_logger.error(f"Failed to read source manifest: {e}")
            stats["success"] = False
            return stats

        output_entries = []

        for entry in source_entries:
            source_file = entry.get('source')
            if not source_file:
                continue

            # Create placeholder SVG
            source_path = Path(source_file)
            output_path = output_folder / "documents" / source_path.with_suffix('.svg')
            output_path.parent.mkdir(parents=True, exist_ok=True)

            placeholder_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <text x="10" y="50">Placeholder SVG for {source_path.name}</text>
</svg>'''

            output_path.write_text(placeholder_svg, encoding='utf-8')

            # Create manifest entry
            manifest_entry = {
                "source": source_file,
                "outputs": [str(output_path.relative_to(output_folder))],
                "svg_file": str(output_path.relative_to(output_folder)),
                "processed_at": datetime.now().isoformat(),
                "success": True,
                "details": {
                    "skip_processing": True,
                    "svg_size": "100x100",
                    "svg_length": len(placeholder_svg)
                },
                "svg_content": placeholder_svg
            }

            output_entries.append(manifest_entry)
            stats["skipped"] += 1

        # Write output manifest
        srsly.write_jsonl(output_manifest, output_entries)
        tool_logger.success(f"Created {len(output_entries)} placeholder SVG files in {output_manifest}")

        return stats

    # Normal processing
    tool_logger.info(f"Converting documents to SVG in {source_folder}")

    load_dotenv()

    # Get API key
    api_key = get_qwen_key(api_key_cli)
    if not api_key:
        raise ValueError("Qwen API key required")

    # Read source manifest
    if not source_manifest.exists():
        tool_logger.error(f"Source manifest not found: {source_manifest}")
        stats["success"] = False
        return stats

    try:
        source_entries = list(srsly.read_jsonl(source_manifest))
        tool_logger.info(f"Loaded {len(source_entries)} entries from source manifest")
    except Exception as e:
        tool_logger.error(f"Failed to read source manifest: {e}")
        stats["success"] = False
        return stats

    # Process each entry
    output_entries = []

    for entry in source_entries:
        source_file = entry.get('source')
        if not source_file:
            tool_logger.warning(f"Entry missing 'source' field: {entry}")
            continue

        # Get source image path
        source_path = source_folder / source_file
        if not source_path.exists():
            tool_logger.warning(f"Source file not found: {source_path}")
            continue

        # Load transcription
        transcription = load_transcription(source_file, transcription_manifest, transcription_folder)

        # Load visual description
        visual_description = load_visual_description(source_file, visual_descriptions_manifest)

        # Load library metadata
        library_metadata = load_library_metadata(source_file, metadata_manifest)

        # Create output path
        output_path = output_folder / "documents" / Path(source_file).with_suffix('.svg')

        # Process to SVG
        result = process_document_to_svg(
            source_path,
            output_path,
            api_key,
            transcription,
            visual_description,
            library_metadata
        )

        output_entries.append(result)

        if result.get("error"):
            stats["failed"] += 1
        elif result.get("skipped"):
            stats["skipped"] += 1
        else:
            stats["processed_files"] += 1

    # Write output manifest
    srsly.write_jsonl(output_manifest, output_entries)
    tool_logger.success(f"Saved {len(output_entries)} SVG entries to {output_manifest}")

    # Print summary
    tool_logger.info("Summary:")
    tool_logger.info(f"  - Total files processed: {stats['processed_files']}")
    tool_logger.info(f"  - Skipped: {stats['skipped']}")
    tool_logger.info(f"  - Failed: {stats['failed']}")

    return stats


def convert_to_svg(
    source_folder: Path = typer.Argument(..., help="Source directory containing images"),
    source_manifest: Path = typer.Argument(..., help="Source manifest file (JSONL)"),
    transcription_folder: Path = typer.Argument(..., help="Folder containing transcriptions"),
    transcription_manifest: Path = typer.Argument(..., help="Transcription manifest file (JSONL)"),
    output_folder: Path = typer.Argument(..., help="Output directory for SVG files"),
    metadata_manifest: Optional[Path] = typer.Option(None, help="Library metadata manifest (JSONL)"),
    visual_descriptions_manifest: Optional[Path] = typer.Option(None, help="Visual descriptions manifest (JSONL)"),
    api_key: str = typer.Option(None, "--api-key", help="Qwen API key"),
    skip_processing: bool = typer.Option(False, "--skip-processing", help="Create placeholder SVG files")
):
    """
    Convert documents to semantic SVG files using Qwen VL Max (3-step process).

    This tool combines images, transcriptions, visual descriptions, and library
    metadata to create rich semantic SVG documents. Uses a 3-step process:
    1. Generate draft SVG with Qwen VL Max
    2. Critique SVG with Qwen Max
    3. Generate final improved SVG with Qwen Max

    Example:
        python -m fichero.tools.convert_to_svg \\
            assets/enhanced \\
            assets/enhanced/enhance_manifest.jsonl \\
            assets/cleaned \\
            assets/cleaned/cleaned_manifest.jsonl \\
            assets/svg \\
            --metadata-manifest assets/library_metadata/metadata_manifest.jsonl \\
            --visual-descriptions-manifest assets/visual_descriptions/descriptions_manifest.jsonl \\
            --api-key YOUR_KEY
    """
    return convert_to_svg_batch(
        source_folder,
        source_manifest,
        transcription_folder,
        transcription_manifest,
        output_folder,
        metadata_manifest=metadata_manifest,
        visual_descriptions_manifest=visual_descriptions_manifest,
        api_key_cli=api_key,
        skip_processing=skip_processing
    )


if __name__ == "__main__":
    typer.run(convert_to_svg)
