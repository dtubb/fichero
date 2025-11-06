import typer
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from io import BytesIO
import base64
from openai import OpenAI
from datetime import datetime
import time
import json
import srsly
import subprocess
import tempfile
import os
from typing import Optional, Dict, List, Any

# Import utilities
try:
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.files import ensure_dirs
except ImportError:
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.files import ensure_dirs

# Configure tool_logger
tool_logger = get_tool_logger('analyze_document_groups')

# Video Analysis Prompt
VIDEO_ANALYSIS_PROMPT = """Analyze this video sequence of document thumbnails AND their transcribed text to identify when documents change.

You have TWO sources of information:
1. VIDEO: Visual appearance of each page
2. TEXT: Transcribed text content for each page

Use BOTH to identify when one document ends and another begins.

Look for these indicators of document boundaries:
- Visual changes: Handwritten vs typed, layout changes, different formatting
- Content changes: New subject/topic, different sender/recipient, date changes
- Contextual changes: End of one letter and start of another, end of telegram and start of report

Identify FRAME TIMESTAMPS where documents change.

Return your answer as JSON in this format:
{{
  "change_points": [
    {{
      "frame_number": 5,
      "timestamp_seconds": 1.5,
      "change_description": "End of handwritten letter about permits, start of typed telegram about shipment",
      "before_visual": "Handwritten cursive",
      "after_visual": "Typed text with telegram format",
      "before_content": "Letter discussing permit application",
      "after_content": "Telegram about cargo shipment"
    }},
    ...
  ],
  "total_frames": 30,
  "groups": [
    {{
      "start_frame": 0,
      "end_frame": 4,
      "visual_type": "Handwritten letter",
      "visual_characteristics": "Cursive handwriting, letter format, pages appear to be continuation of same document",
      "content_summary": "Letter from Antonio Asprilla regarding permit enforcement"
    }},
    ...
  ]
}}

IMPORTANT:
- Use both visual AND text information to identify document boundaries
- Group together pages that belong to the same document (same letter, same report, etc.)
- Only identify SIGNIFICANT changes where one document ends and another begins
- Describe what you observe in both visual appearance and content subject/context

Return ONLY valid JSON."""


def encode_video_base64(video_path: Path) -> str:
    """Encode video file to base64"""
    try:
        with open(video_path, 'rb') as f:
            video_data = f.read()
        encoded = base64.b64encode(video_data).decode('utf-8')
        size_mb = len(encoded) / (1024 * 1024)
        tool_logger.info(f"Encoded video size: {size_mb:.2f} MB")
        return encoded
    except Exception as e:
        tool_logger.error(f"Failed to encode video: {e}")
        raise


def create_thumbnail(image_path: Path, output_path: Path, size: tuple = (512, 512)):
    """Create a thumbnail from an image"""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize maintaining aspect ratio
            img.thumbnail(size, Image.LANCZOS)

            # Create a new image with white background
            background = Image.new('RGB', size, (255, 255, 255))

            # Paste the thumbnail centered
            offset = ((size[0] - img.size[0]) // 2, (size[1] - img.size[1]) // 2)
            background.paste(img, offset)

            # Save thumbnail
            background.save(output_path, 'JPEG', quality=85)

            tool_logger.debug(f"Created thumbnail: {output_path.name}")
            return True

    except Exception as e:
        tool_logger.error(f"Failed to create thumbnail for {image_path}: {e}")
        return False


def create_video_from_thumbnails(thumbnail_paths: List[Path], output_video: Path, fps: int = 2) -> bool:
    """Create video from thumbnail images using ffmpeg"""
    try:
        tool_logger.info(f"Creating video from {len(thumbnail_paths)} thumbnails")

        # Create a temporary directory for numbered thumbnails
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Copy thumbnails with sequential numbering (required by ffmpeg)
            for i, thumb_path in enumerate(thumbnail_paths):
                numbered_path = temp_path / f"frame_{i:05d}.jpg"
                numbered_path.write_bytes(thumb_path.read_bytes())

            # Use ffmpeg to create video
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-framerate', str(fps),
                '-i', str(temp_path / 'frame_%05d.jpg'),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '23',
                str(output_video)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                tool_logger.error(f"ffmpeg failed: {result.stderr}")
                return False

            tool_logger.success(f"Created video: {output_video} ({output_video.stat().st_size / 1024:.1f} KB)")
            return True

    except subprocess.TimeoutExpired:
        tool_logger.error("ffmpeg timed out after 5 minutes")
        return False
    except FileNotFoundError:
        tool_logger.error("ffmpeg not found - please install with: brew install ffmpeg")
        return False
    except Exception as e:
        tool_logger.error(f"Failed to create video: {e}")
        return False


def load_transcription_text(file_list: List[str], transcription_manifest: Optional[Path]) -> str:
    """Load transcription text for each file and format as a single string"""
    if not transcription_manifest or not transcription_manifest.exists():
        return ""

    try:
        # Read transcription manifest
        transcriptions = {}
        for entry in srsly.read_jsonl(transcription_manifest):
            source = entry.get('source', '')
            text = entry.get('transcription', {}).get('text', '')
            if source and text:
                transcriptions[source] = text

        # Build text string with page numbers and content
        text_parts = []
        for i, filename in enumerate(file_list):
            page_num = i + 1
            text = transcriptions.get(filename, '[No transcription available]')
            text_parts.append(f"=== PAGE {page_num}: {filename} ===\n{text}\n")

        combined_text = "\n".join(text_parts)
        tool_logger.info(f"Loaded transcriptions for {len(transcriptions)}/{len(file_list)} files")
        return combined_text

    except Exception as e:
        tool_logger.error(f"Failed to load transcription text: {e}")
        return ""


def analyze_video_with_qwen(video_path: Path, api_key: str, transcription_text: str = "") -> Dict:
    """Send video and transcription text to Qwen VL Max for analysis"""
    try:
        tool_logger.info("Analyzing video with Qwen VL Max")

        # Encode video
        video_base64 = encode_video_base64(video_path)

        # Create OpenAI client
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=180.0
        )

        # Build message content
        content_parts = [
            {
                "type": "video",
                "video": f"data:video/mp4;base64,{video_base64}"
            }
        ]

        # Add transcription text if available
        if transcription_text:
            content_parts.append({
                "type": "text",
                "text": f"TRANSCRIBED TEXT FOR EACH PAGE:\n\n{transcription_text}\n\n---\n\n"
            })
            tool_logger.info(f"Including {len(transcription_text)} chars of transcription text")

        # Add analysis prompt
        content_parts.append({
            "type": "text",
            "text": VIDEO_ANALYSIS_PROMPT
        })

        # Call Qwen VL Max with video and text
        response = client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{
                "role": "user",
                "content": content_parts
            }],
            timeout=180
        )

        # Parse response
        content = response.choices[0].message.content

        try:
            analysis = json.loads(content)
            tool_logger.success(f"Video analysis complete: {len(analysis.get('change_points', []))} change points found")
            return analysis
        except json.JSONDecodeError:
            tool_logger.warning("Response not valid JSON, wrapping in structure")
            return {
                "change_points": [],
                "total_frames": 0,
                "groups": [],
                "raw_response": content
            }

    except Exception as e:
        tool_logger.error(f"Video analysis failed: {e}")
        return {
            "error": str(e),
            "change_points": [],
            "total_frames": 0,
            "groups": []
        }


def map_groups_to_files(
    analysis: Dict,
    file_list: List[str],
    fps: int = 2
) -> List[Dict]:
    """Map video analysis groups back to source files"""

    groups = analysis.get('groups', [])
    if not groups:
        # If no groups identified, treat all files as one group
        groups = [{
            "start_frame": 0,
            "end_frame": len(file_list) - 1,
            "visual_type": "Unknown",
            "visual_characteristics": "No grouping analysis available"
        }]

    file_groups = []

    for i, group in enumerate(groups):
        start_frame = group.get('start_frame', 0)
        end_frame = group.get('end_frame', len(file_list) - 1)

        # Ensure indices are valid
        start_frame = max(0, min(start_frame, len(file_list) - 1))
        end_frame = max(start_frame, min(end_frame, len(file_list) - 1))

        files_in_group = file_list[start_frame:end_frame + 1]

        file_groups.append({
            "group_id": i + 1,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "visual_type": group.get('visual_type', 'Unknown'),
            "visual_characteristics": group.get('visual_characteristics', ''),
            "file_count": len(files_in_group),
            "files": files_in_group
        })

    return file_groups


def analyze_document_groups_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    api_key_cli: str = None,
    fps: int = 2,
    thumbnail_size: int = 512,
    skip_processing: bool = False,
    transcription_manifest: Path = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Analyze document groups using video-based visual similarity

    Args:
        source_folder: Source folder containing images
        source_manifest: Source manifest file
        output_folder: Output folder for analysis results
        api_key_cli: Qwen API key
        fps: Frames per second for video generation
        thumbnail_size: Size of thumbnails in pixels
        skip_processing: Create stub analysis for testing

    Returns:
        Processing statistics dictionary
    """
    # Safely handle paths
    source_folder = Path(os.path.expanduser(str(source_folder))).resolve()
    source_manifest = Path(os.path.expanduser(str(source_manifest))).resolve()
    output_folder = Path(os.path.expanduser(str(output_folder))).resolve()

    tool_logger.progress(f"Analyzing document groups from: {source_manifest}")

    # Output manifest path
    output_manifest = output_folder / "groups_manifest.jsonl"
    ensure_dirs(output_manifest)

    # Statistics
    stats = {
        "total_files": 0,
        "groups_found": 0,
        "video_created": False,
        "success": True
    }

    # Skip processing mode
    if skip_processing:
        tool_logger.info("Skip processing mode - creating placeholder grouping")

        if not source_manifest.exists():
            tool_logger.error(f"Source manifest not found: {source_manifest}")
            stats["success"] = False
            return stats

        try:
            source_entries = list(srsly.read_jsonl(source_manifest))
            stats["total_files"] = len(source_entries)
        except Exception as e:
            tool_logger.error(f"Failed to read source manifest: {e}")
            stats["success"] = False
            return stats

        # Create single placeholder group
        file_list = [entry.get('source', '') for entry in source_entries if entry.get('source')]

        placeholder_result = {
            "total_files": len(file_list),
            "groups_found": 1,
            "processed_at": datetime.now().isoformat(),
            "analysis": {
                "change_points": [],
                "total_frames": len(file_list),
                "groups": [{
                    "group_id": 1,
                    "start_frame": 0,
                    "end_frame": len(file_list) - 1,
                    "visual_type": "Unknown (placeholder)",
                    "visual_characteristics": "Skip processing mode",
                    "file_count": len(file_list),
                    "files": file_list
                }]
            },
            "skip_processing": True
        }

        # Save manifest
        with open(output_manifest, 'w') as f:
            f.write(json.dumps(placeholder_result) + '\n')

        stats["groups_found"] = 1
        tool_logger.success(f"Created placeholder grouping in {output_manifest}")

        return stats

    # Normal processing
    tool_logger.info(f"Analyzing document groups in {source_folder}")

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
        stats["total_files"] = len(source_entries)
    except Exception as e:
        tool_logger.error(f"Failed to read source manifest: {e}")
        stats["success"] = False
        return stats

    # Get file list
    file_list = []
    for entry in source_entries:
        source_file = entry.get('source') or entry.get('outputs', [None])[0]
        if source_file:
            file_list.append(source_file)

    if not file_list:
        tool_logger.error("No files found in manifest")
        stats["success"] = False
        return stats

    tool_logger.info(f"Processing {len(file_list)} files")

    # Create thumbnails
    thumbnail_folder = output_folder / "thumbnails"
    thumbnail_folder.mkdir(parents=True, exist_ok=True)

    thumbnail_paths = []

    for i, source_file in enumerate(file_list):
        source_path = source_folder / source_file

        if not source_path.exists():
            tool_logger.warning(f"Source file not found: {source_path}")
            continue

        # Create thumbnail
        thumb_path = thumbnail_folder / f"thumb_{i:05d}.jpg"
        if create_thumbnail(source_path, thumb_path, size=(thumbnail_size, thumbnail_size)):
            thumbnail_paths.append(thumb_path)

    tool_logger.info(f"Created {len(thumbnail_paths)} thumbnails")

    if not thumbnail_paths:
        tool_logger.error("No thumbnails created")
        stats["success"] = False
        return stats

    # Create video
    video_path = output_folder / "document_sequence.mp4"

    if not create_video_from_thumbnails(thumbnail_paths, video_path, fps=fps):
        tool_logger.error("Failed to create video")
        stats["success"] = False
        return stats

    stats["video_created"] = True

    # Load transcription text if available
    transcription_text = ""
    if transcription_manifest:
        transcription_manifest_path = Path(transcription_manifest)
        tool_logger.info(f"Loading transcriptions from: {transcription_manifest_path}")
        transcription_text = load_transcription_text(file_list, transcription_manifest_path)

    # Analyze video with Qwen VL Max
    analysis = analyze_video_with_qwen(video_path, api_key, transcription_text)

    # Map groups to files
    file_groups = map_groups_to_files(analysis, file_list, fps=fps)

    stats["groups_found"] = len(file_groups)

    # Create result
    result = {
        "total_files": len(file_list),
        "groups_found": len(file_groups),
        "processed_at": datetime.now().isoformat(),
        "video_path": str(video_path.relative_to(output_folder)),
        "fps": fps,
        "thumbnail_size": thumbnail_size,
        "analysis": {
            "change_points": analysis.get('change_points', []),
            "total_frames": len(file_list),
            "groups": file_groups
        }
    }

    # Save manifest
    with open(output_manifest, 'w') as f:
        f.write(json.dumps(result, indent=2) + '\n')

    tool_logger.success(f"Saved grouping analysis to {output_manifest}")

    # Print summary
    tool_logger.info("Summary:")
    tool_logger.info(f"  - Total files: {stats['total_files']}")
    tool_logger.info(f"  - Groups found: {stats['groups_found']}")
    tool_logger.info(f"  - Video created: {stats['video_created']}")

    for group in file_groups:
        tool_logger.info(f"  - Group {group['group_id']}: {group['visual_type']} ({group['file_count']} files)")

    return stats


def analyze_document_groups(
    source_folder: Path = typer.Argument(..., help="Source directory containing images"),
    source_manifest: Path = typer.Argument(..., help="Source manifest file (JSONL)"),
    output_folder: Path = typer.Argument(..., help="Output directory for grouping analysis"),
    api_key: str = typer.Option(None, "--api-key", help="Qwen API key"),
    fps: int = typer.Option(2, help="Frames per second for video"),
    thumbnail_size: int = typer.Option(512, help="Thumbnail size in pixels"),
    skip_processing: bool = typer.Option(False, "--skip-processing", help="Create placeholder grouping"),
    transcription_manifest: Path = typer.Option(None, "--transcription-manifest", help="Transcription manifest file (JSONL)")
):
    """
    Analyze document groups using video-based visual similarity with Qwen VL Max.

    This tool creates thumbnails from document images, compiles them into a video,
    and sends the video to Qwen VL Max to identify when document types change.
    This allows grouping of visually similar documents.

    Example:
        python -m fichero.tools.analyze_document_groups \\
            assets/enhanced \\
            assets/enhanced/enhance_manifest.jsonl \\
            assets/document_groups \\
            --api-key YOUR_KEY \\
            --fps 2 \\
            --thumbnail-size 512
    """
    return analyze_document_groups_batch(
        source_folder,
        source_manifest,
        output_folder,
        api_key_cli=api_key,
        fps=fps,
        thumbnail_size=thumbnail_size,
        skip_processing=skip_processing,
        transcription_manifest=transcription_manifest
    )


if __name__ == "__main__":
    typer.run(analyze_document_groups)
