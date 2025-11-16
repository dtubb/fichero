# Tool Reference Documentation

**Phase 1 Tool Inventory - Complete Parameter Documentation**

This document provides comprehensive parameter documentation for all 20 tools in `src/fichero/tools/`.

**Date:** 2025-11-15
**Status:** Phase 1 Complete
**Total Tools Documented:** 20

---

## Table of Contents

1. [Image Processing Tools](#image-processing-tools)
2. [AI Processing Tools](#ai-processing-tools)
3. [Document Generation Tools](#document-generation-tools)
4. [Metadata & Analysis Tools](#metadata--analysis-tools)
5. [Parameter Quick Reference](#parameter-quick-reference)

---

## Image Processing Tools

### 1. crop.py

**Purpose:** Automatic intelligent cropping of document images using edge detection

**Batch Function:** `crop_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images to crop
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for cropped images
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Cropped images in same format as input
- Manifest: `crop_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.jpg"],
  "success": true,
  "details": {
    "original_size": [width, height],
    "cropped_size": [width, height],
    "crop_box": [x1, y1, x2, y2]
  }
}
```

---

### 2. rotate.py

**Purpose:** Automatic rotation correction for document images

**Batch Function:** `rotate_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for rotated images
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Rotated images in same format as input
- Manifest: `rotate_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.jpg"],
  "success": true,
  "details": {
    "rotation_angle": 90,
    "method": "exif" or "auto"
  }
}
```

---

### 3. enhance.py

**Purpose:** Image enhancement (contrast, brightness, sharpness)

**Batch Function:** `enhance_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for enhanced images
- `contrast` (float, optional, default=1.5): Contrast enhancement factor (1.0 = no change)
- `brightness` (float, optional, default=1.0): Brightness enhancement factor
- `sharpness` (float, optional, default=1.2): Sharpness enhancement factor
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Enhanced images in same format as input
- Manifest: `enhance_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.jpg"],
  "success": true,
  "details": {
    "contrast": 1.5,
    "brightness": 1.0,
    "sharpness": 1.2
  }
}
```

---

### 4. split.py

**Purpose:** Split multi-page TIFF files into individual images

**Batch Function:** `split_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing TIFF files
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for split images
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.tif`, `.tiff` (multi-page TIFF files)

**Output Format:**
- Individual TIFF files (one per page)
- Naming: `original_name_page_001.tif`, `original_name_page_002.tif`, etc.
- Manifest: `split_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.tif",
  "outputs": [
    "relative/path/to/output_page_001.tif",
    "relative/path/to/output_page_002.tif"
  ],
  "success": true,
  "details": {
    "page_count": 2,
    "pages_extracted": 2
  }
}
```

---

### 5. segment.py

**Purpose:** Segment images into smaller sections for processing

**Batch Function:** `segment_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for segmented images
- `max_pixels` (int, optional, default=16777216): Maximum pixels per segment (default: 16MP)
- `overlap` (int, optional, default=50): Overlap between segments in pixels
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Segmented images with suffix `_seg_001.jpg`, `_seg_002.jpg`, etc.
- Manifest: `segment_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": [
    "relative/path/to/output_seg_001.jpg",
    "relative/path/to/output_seg_002.jpg"
  ],
  "success": true,
  "details": {
    "original_size": [width, height],
    "segment_count": 2,
    "max_pixels": 16777216,
    "overlap": 50
  }
}
```

---

### 6. remove_background.py

**Purpose:** Remove background from document images using Rembg

**Batch Function:** `remove_background_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for background-removed images
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- PNG images with transparent background
- Manifest: `remove_background_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.png"],
  "success": true,
  "details": {
    "model": "u2net",
    "alpha_matting": false
  }
}
```

---

### 7. prepare_images.py

**Purpose:** Prepare images for processing (format conversion, resize, etc.)

**Batch Function:** `prepare_images_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for prepared images
- `max_size` (int, optional): Maximum dimension (width or height) in pixels
- `format` (str, optional): Output format ('jpg', 'png', 'jxl', etc.)
- `quality` (int, optional, default=95): JPEG quality (1-100)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Converted/resized images
- Manifest: `prepare_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.heic",
  "outputs": ["relative/path/to/output.jpg"],
  "success": true,
  "details": {
    "original_format": "heic",
    "output_format": "jpg",
    "original_size": [width, height],
    "output_size": [width, height]
  }
}
```

---

### 8. recombine_segments.py

**Purpose:** Recombine transcriptions from segmented images back into complete documents

**Batch Function:** `recombine_segments_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing segment transcriptions
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for recombined transcriptions
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.txt` files (transcription text files from segmented images)

**Output Format:**
- Recombined text files (one per original document)
- Manifest: `recombine_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/original.jpg",
  "outputs": ["relative/path/to/output.txt"],
  "success": true,
  "details": {
    "segment_count": 3,
    "total_length": 1234,
    "segments_found": 3
  },
  "bg_removed": "relative/path/to/bg_removed.png"
}
```

**Special Notes:**
- Automatically detects and groups segments by parent document
- Preserves `bg_removed` field from segment manifest for downstream tools

---

### 9. convert_to_svg.py

**Purpose:** Convert images to SVG format using Potrace

**Batch Function:** `convert_to_svg_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for SVG files
- `threshold` (int, optional, default=128): Threshold for black/white conversion (0-255)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- SVG vector files
- Manifest: `svg_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.svg"],
  "success": true,
  "details": {
    "threshold": 128,
    "conversion_method": "potrace"
  }
}
```

---

## AI Processing Tools

### 10. transcribe_qwen_max.py

**Purpose:** Transcribe document images using Alibaba Qwen VL Max API

**Batch Function:** `transcribe_qwen_batch(source_folder, source_manifest, output_folder, api_key_cli=None, prompt_file=None, skip_processing=False, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for transcriptions
- `api_key_cli` (str, optional): Qwen API key (if not in environment)
- `prompt_file` (Path, optional): Custom prompt file (YAML format)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Environment Variables:**
- `DASHSCOPE_API_KEY`: Qwen API key

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Text files (`.txt`)
- Manifest: `transcription_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.txt"],
  "success": true,
  "transcription": {
    "text": "Transcribed text content...",
    "model": "qwen-vl-max",
    "prompt": "Transcription prompt used",
    "tokens_used": 1234
  }
}
```

**Prompt File Format (YAML):**
```yaml
system_message: "You are a document transcription expert."
user_prompt: "Transcribe this document exactly as written."
```

---

### 11. transcribe_lmstudio.py

**Purpose:** Transcribe document images using local LM Studio API

**Batch Function:** `transcribe_lmstudio_batch(source_folder, source_manifest, output_folder, api_url=None, model_name=None, prompt_file=None, skip_processing=False, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for transcriptions
- `api_url` (str, optional, default="http://localhost:1234/v1"): LM Studio API URL
- `model_name` (str, optional): Model name to use
- `prompt_file` (Path, optional): Custom prompt file (YAML format)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- Text files (`.txt`)
- Manifest: `transcription_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.txt"],
  "success": true,
  "transcription": {
    "text": "Transcribed text content...",
    "model": "model-name",
    "api_url": "http://localhost:1234/v1",
    "prompt": "Transcription prompt used"
  }
}
```

---

### 12. describe_images.py

**Purpose:** Generate detailed descriptions of images using Qwen VL Max

**Batch Function:** `describe_images_batch(source_folder, source_manifest, output_folder, api_key_cli=None, prompt_file=None, skip_processing=False, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing images
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for descriptions
- `api_key_cli` (str, optional): Qwen API key (if not in environment)
- `prompt_file` (Path, optional): Custom prompt file (YAML format)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Environment Variables:**
- `DASHSCOPE_API_KEY`: Qwen API key

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- JSON files with image descriptions
- Manifest: `description_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["relative/path/to/output.json"],
  "success": true,
  "description": {
    "text": "Detailed image description...",
    "model": "qwen-vl-max",
    "prompt": "Description prompt used",
    "tokens_used": 1234
  }
}
```

---

### 13. llm_process.py

**Purpose:** Process text files with LLM for structured data extraction

**Batch Function:** `llm_process_batch(source_folder, source_manifest, output_folder, api_key_cli=None, prompt_file=None, skip_processing=False, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Input folder containing text files
- `source_manifest` (Path, required): Input manifest file (JSONL format)
- `output_folder` (Path, required): Output folder for LLM-processed JSON
- `api_key_cli` (str, optional): Qwen API key (if not in environment)
- `prompt_file` (Path, required): Prompt file with processing instructions (YAML format)
- `skip_processing` (bool, optional): Skip actual processing, create empty outputs for testing

**Environment Variables:**
- `DASHSCOPE_API_KEY`: Qwen API key

**Input Formats:**
- `.txt` (text files with transcriptions)

**Output Format:**
- JSON files with structured extracted data
- Manifest: `llm_process_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.txt",
  "outputs": ["relative/path/to/output.json"],
  "success": true,
  "llm_processing": {
    "model": "qwen-max",
    "prompt_file": "path/to/prompt.yaml",
    "tokens_used": 5678
  }
}
```

**Prompt File Format (YAML):**
```yaml
system_message: "You are a historical document analyzer."
user_prompt: |
  Extract the following information from this document:
  - Date
  - Sender
  - Recipient
  - Subject
  Return as JSON.
output_schema:
  type: object
  properties:
    date: {type: string}
    sender: {type: string}
    recipient: {type: string}
    subject: {type: string}
```

---

## Document Generation Tools

### 14. convert_to_word.py

**Purpose:** Convert images and transcriptions to Word documents with side-by-side layout

**Batch Function:** `convert_to_word_batch(images_folder, transcription_manifest, output_folder, transcription_folder=None, skip_processing=False, **kwargs)`

**Parameters:**
- `images_folder` (Path, required): Input folder containing background-removed images
- `transcription_manifest` (Path, required): Input transcription manifest file
- `output_folder` (Path, required): Output folder for Word documents
- `transcription_folder` (Path, optional): Folder containing transcription text files (defaults to manifest's parent)
- `skip_processing` (bool, optional): Skip actual processing, create empty Word files for testing

**Input Formats:**
- Images: `.png`, `.jpg`, `.jpeg`, `.jxl`, `.tif`, `.tiff`
- Transcriptions: `.txt` files

**Output Format:**
- Word documents (`.docx`) - one per parent folder
- Side-by-side layout: image on left page, text on right page
- Manifest: `convert_to_word_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.jpg",
  "outputs": ["documents/parent_folder/parent_folder.docx"],
  "success": true,
  "details": {
    "text_length": 1234,
    "spread_count": 5
  }
}
```

**Special Features:**
- Automatically groups images by parent folder
- Creates one Word document per folder
- Cover page with folder name
- Supports JPEG XL format (requires `djxl` command-line tool)

---

### 15. json_to_word.py

**Purpose:** Convert JSON catalogue data to formatted Word documents

**Batch Function:** `json_to_word_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Source folder containing JSON files
- `source_manifest` (Path, required): Manifest file from LLM processing
- `output_folder` (Path, required): Output folder for Word documents

**Input Formats:**
- `.json` files (from LLM catalogue processing)

**Output Format:**
- Word documents (`.docx`) with formatted catalogue data
- Manifest: `json_to_word_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.json",
  "outputs": ["relative/path/to/output-catalogue.docx"],
  "success": true,
  "details": {
    "sections_created": 5,
    "output_format": "docx"
  }
}
```

**Special Features:**
- Smart field ordering (summary, tags, key people first)
- Automatic table generation for structured data
- Helvetica font throughout
- Bilingual support (English/Spanish field names)

**Expected JSON Structure:**
```json
{
  "results": {
    "resumen": {
      "resumen": "Summary text..."
    },
    "personas_clave_y_etiquetas": {
      "etiquetas": "tag1; tag2; tag3",
      "personas_clave": [
        {"nombre": "Name", "contexto": "Context"}
      ]
    }
  }
}
```

---

### 16. json_to_excel.py

**Purpose:** Convert multiple JSON files to a single Excel spreadsheet

**Batch Function:** `json_to_excel(source_folder, output_file, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Source folder containing JSON files
- `output_file` (Path, required): Output Excel file path (`.xlsx`)

**Input Formats:**
- `.json` files (any structure)

**Output Format:**
- Excel spreadsheet (`.xlsx`)
- One row per JSON file
- Nested structures flattened into readable strings

**Special Features:**
- Automatic field flattening with dot notation
- List rendering as multi-line strings
- Preferred column ordering (summary, tags, key people first)
- Helvetica font, word wrap, top/left alignment
- `__file__` column shows source JSON path

**Output Structure:**
- Each JSON file becomes one row
- Nested fields: `parent.child.field`
- Lists of dicts rendered as readable multi-line text
- Header row with title-cased column names

---

## Metadata & Analysis Tools

### 17. build_documents_manifest.py

**Purpose:** Generate initial manifest listing all documents in a folder

**Batch Function:** `build_documents_manifest_batch(source_folder, output_manifest, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Directory to scan for files and folders
- `output_manifest` (Path, required): Output file path (`.jsonl`)

**Input Formats:**
- All supported image formats: `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- JSONL manifest with all files and directories
- Manifest: specified by `output_manifest` parameter

**Manifest Structure:**
```json
{
  "path": "relative/path/to/file.jpg",
  "type": "file",
  "mtime": 1234567890.123,
  "size": 1234567,
  "format": "jpg",
  "process_fn": "pillow"
}
```

```json
{
  "path": "relative/path/to/folder",
  "type": "directory"
}
```

**Special Features:**
- Natural alphanumeric sorting (like macOS Finder)
- Format detection with processing function recommendation
- Recursive directory scanning
- Format distribution statistics

---

### 18. analyze_document_groups.py

**Purpose:** Analyze visual similarity to group related documents using AI video analysis

**Batch Function:** `analyze_document_groups_batch(source_folder, source_manifest, output_folder, api_key_cli=None, fps=2, thumbnail_size=512, skip_processing=False, transcription_manifest=None, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Source folder containing images
- `source_manifest` (Path, required): Source manifest file (JSONL)
- `output_folder` (Path, required): Output folder for analysis results
- `api_key_cli` (str, optional): Qwen API key (if not in environment)
- `fps` (int, optional, default=2): Frames per second for video generation
- `thumbnail_size` (int, optional, default=512): Thumbnail size in pixels
- `skip_processing` (bool, optional): Create placeholder grouping without AI analysis
- `transcription_manifest` (Path, optional): Transcription manifest to include text in analysis

**Environment Variables:**
- `DASHSCOPE_API_KEY`: Qwen API key

**Input Formats:**
- `.jpg`, `.jpeg`, `.png`, `.jxl`, `.tif`, `.tiff`, `.heic`, `.heif`

**Output Format:**
- JSON file with document grouping analysis
- Video file (`document_sequence.mp4`)
- Thumbnails folder
- Manifest: `groups_manifest.jsonl`

**Manifest Structure:**
```json
{
  "total_files": 30,
  "groups_found": 3,
  "processed_at": "2025-11-15T10:30:00",
  "video_path": "document_sequence.mp4",
  "fps": 2,
  "thumbnail_size": 512,
  "analysis": {
    "change_points": [
      {
        "frame_number": 5,
        "timestamp_seconds": 2.5,
        "change_description": "End of handwritten letter, start of typed telegram",
        "before_visual": "Handwritten cursive",
        "after_visual": "Typed text with telegram format"
      }
    ],
    "groups": [
      {
        "group_id": 1,
        "start_frame": 0,
        "end_frame": 4,
        "visual_type": "Handwritten letter",
        "file_count": 5,
        "files": ["file1.jpg", "file2.jpg", "..."]
      }
    ]
  }
}
```

**Special Features:**
- Creates video sequence from document thumbnails
- Uses Qwen VL Max for AI-powered visual analysis
- Optionally includes transcription text for context-aware grouping
- Identifies visual and content-based document boundaries
- Requires `ffmpeg` for video creation

---

### 19. extract_library_metadata.py

**Purpose:** Extract library metadata for files to enrich processing context

**Batch Function:** `extract_metadata_batch(source_folder, source_manifest, output_folder, library_db_path=None, collection_id=None, skip_processing=False, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Source folder containing files
- `source_manifest` (Path, required): Input manifest file (JSONL)
- `output_folder` (Path, required): Output folder for metadata manifest
- `library_db_path` (Path, optional): Path to library database file
- `collection_id` (str, optional): Collection ID to query
- `skip_processing` (bool, optional): Skip database queries, create placeholder metadata

**Input Formats:**
- Any file referenced in source manifest

**Output Format:**
- JSONL manifest with library metadata
- Manifest: `metadata_manifest.jsonl`

**Manifest Structure:**
```json
{
  "source": "relative/path/to/file.jpg",
  "processed_at": "2025-11-15T10:30:00",
  "library_metadata": {
    "item_id": "abc123",
    "item_name": "Document Name",
    "collection_id": "col456",
    "collection_name": "Collection Name",
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-15T12:00:00",
    "storage_type": "external",
    "source_path": "/absolute/path/to/source",
    "local_path": "/absolute/path/to/local",
    "status": "active",
    "type": "file",
    "metadata": {
      "custom_field": "value"
    }
  }
}
```

**Special Features:**
- Integrates with Fichero library database
- Multiple path matching strategies (absolute, relative, filename)
- Graceful degradation when database unavailable
- Placeholder mode for workflows without library integration

---

### 20. fuzzy_clean.py

**Purpose:** Clean up transcription text by removing AI artifacts and repetitions

**Batch Function:** `fuzzy_clean_batch(source_folder, source_manifest, output_folder, **kwargs)`

**Parameters:**
- `source_folder` (Path, required): Path to folder containing text files
- `source_manifest` (Path, required): Path to manifest file
- `output_folder` (Path, required): Output folder for cleaned transcriptions

**Input Formats:**
- `.txt` files (transcription text)

**Output Format:**
- Cleaned text files (`.txt`)
- Manifest: named after `output_folder` (e.g., `transcription_manifest.jsonl`)

**Manifest Structure:**
```json
{
  "source": "relative/path/to/input.txt",
  "outputs": ["relative/path/to/output.txt"],
  "success": true,
  "details": {
    "original_length": 5000,
    "cleaned_length": 4200,
    "reduction_percent": 16.0
  },
  "bg_removed": "relative/path/to/bg_removed.png"
}
```

**Cleaning Operations:**
1. **Phrase Removal:** Removes AI-generated meta-commentary
   - "Here is the transcribed text..."
   - "The document appears to be..."
   - "I cannot assist with that..."
   - 200+ patterns removed

2. **Repetition Removal:**
   - Repeated words
   - Repeated phrases
   - Repeated lines between chunks

3. **Formatting:**
   - Combines single-word paragraphs
   - Adjusts line length based on average
   - Cleans excessive whitespace
   - Preserves paragraph breaks

4. **Pathological Pattern Protection:**
   - Detects and removes patterns that cause regex crashes
   - Handles extremely large files (10MB limit)
   - Fallback to minimal cleaning on error

**Special Features:**
- Preserves `bg_removed` field from recombine manifest
- Creates empty output files when input is missing/empty
- Multiple encoding support (UTF-8, Latin-1)
- Automatic recovery from cleaning errors
- Safe handling of malformed input

---

## Parameter Quick Reference

### Common Parameters Across All Tools

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_folder` | Path | Yes | - | Input folder containing files to process |
| `source_manifest` | Path | Yes | - | Input manifest file (JSONL format) |
| `output_folder` | Path | Yes | - | Output folder for processed files |
| `skip_processing` | bool | No | False | Skip actual processing, create stub outputs |

### Tool-Specific Parameters

#### Image Processing

| Tool | Parameter | Type | Default | Description |
|------|-----------|------|---------|-------------|
| enhance | `contrast` | float | 1.5 | Contrast enhancement factor |
| enhance | `brightness` | float | 1.0 | Brightness enhancement factor |
| enhance | `sharpness` | float | 1.2 | Sharpness enhancement factor |
| segment | `max_pixels` | int | 16777216 | Maximum pixels per segment (16MP) |
| segment | `overlap` | int | 50 | Overlap between segments in pixels |
| convert_to_svg | `threshold` | int | 128 | Black/white conversion threshold (0-255) |
| prepare_images | `max_size` | int | None | Maximum dimension in pixels |
| prepare_images | `format` | str | None | Output format ('jpg', 'png', etc.) |
| prepare_images | `quality` | int | 95 | JPEG quality (1-100) |

#### AI Processing

| Tool | Parameter | Type | Default | Description |
|------|-----------|------|---------|-------------|
| transcribe_qwen_max | `api_key_cli` | str | None | Qwen API key (or use env var) |
| transcribe_qwen_max | `prompt_file` | Path | None | Custom prompt file (YAML) |
| transcribe_lmstudio | `api_url` | str | localhost:1234 | LM Studio API URL |
| transcribe_lmstudio | `model_name` | str | None | Model name to use |
| transcribe_lmstudio | `prompt_file` | Path | None | Custom prompt file (YAML) |
| describe_images | `api_key_cli` | str | None | Qwen API key (or use env var) |
| describe_images | `prompt_file` | Path | None | Custom prompt file (YAML) |
| llm_process | `api_key_cli` | str | None | Qwen API key (or use env var) |
| llm_process | `prompt_file` | Path | Required | Prompt file with instructions (YAML) |

#### Document Generation

| Tool | Parameter | Type | Default | Description |
|------|-----------|------|---------|-------------|
| convert_to_word | `transcription_folder` | Path | None | Folder with transcription text files |

#### Metadata & Analysis

| Tool | Parameter | Type | Default | Description |
|------|-----------|------|---------|-------------|
| analyze_document_groups | `api_key_cli` | str | None | Qwen API key (or use env var) |
| analyze_document_groups | `fps` | int | 2 | Frames per second for video |
| analyze_document_groups | `thumbnail_size` | int | 512 | Thumbnail size in pixels |
| analyze_document_groups | `transcription_manifest` | Path | None | Transcription manifest for context |
| extract_library_metadata | `library_db_path` | Path | None | Path to library database |
| extract_library_metadata | `collection_id` | str | None | Collection ID to query |

### Environment Variables

| Variable | Used By | Purpose |
|----------|---------|---------|
| `DASHSCOPE_API_KEY` | transcribe_qwen_max, describe_images, llm_process, analyze_document_groups | Alibaba Qwen API authentication |

### External Dependencies

| Tool | Dependency | Installation | Purpose |
|------|------------|--------------|---------|
| convert_to_word | `djxl` | `brew install libjxl` | JPEG XL format support |
| convert_to_svg | `potrace` | `brew install potrace` | Vector tracing |
| analyze_document_groups | `ffmpeg` | `brew install ffmpeg` | Video creation |
| remove_background | `rembg` | `pip install rembg` | Background removal |

---

## Manifest Chain Flow

**Typical Workflow Manifest Sequence:**

1. `build_documents_manifest.jsonl` - Initial file listing
2. `crop_manifest.jsonl` - Cropped images
3. `rotate_manifest.jsonl` - Rotated images
4. `enhance_manifest.jsonl` - Enhanced images
5. `segment_manifest.jsonl` - Segmented images (if needed)
6. `transcription_manifest.jsonl` - Raw transcriptions
7. `recombine_manifest.jsonl` - Recombined transcriptions (if segmented)
8. `fuzzy_clean_manifest.jsonl` - Cleaned transcriptions
9. `llm_process_manifest.jsonl` - Structured data extraction
10. `json_to_word_manifest.jsonl` - Final Word documents

**Manifest Field Conventions:**

- `source`: Relative path to input file (preserves original extension)
- `outputs`: Array of relative paths to output files
- `success`: Boolean indicating successful processing
- `error`: Error message (if `success` is false)
- `details`: Tool-specific processing metadata
- `processed_at`: ISO 8601 timestamp (when applicable)
- `skipped`: Boolean indicating file was skipped (already exists)

**Special Field Propagation:**

- `bg_removed`: Preserved from segment → recombine → fuzzy_clean chain
- Links background-removed images to final cleaned transcriptions

---

## Notes

### Import Patterns

All tools support both:
1. **Standalone CLI usage:** Can be run directly with `python -m fichero.tools.tool_name`
2. **Workflow executor imports:** Can be imported with `from fichero.tools.tool_name import tool_batch`

### Batch Function Signature

All batch functions follow this pattern:
```python
def tool_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    **kwargs  # Tool-specific parameters
) -> dict:
    """
    Returns:
        Processing statistics dictionary with keys:
        - processed: Number of files processed
        - skipped: Number of files skipped
        - failed: Number of files failed
        - success: Overall success status
    """
```

### CLI Function Signature

All CLI functions use Typer and follow this pattern:
```python
def tool_name(
    source_folder: Path = typer.Argument(..., help="Description"),
    source_manifest: Path = typer.Argument(..., help="Description"),
    output_folder: Path = typer.Argument(..., help="Description"),
    param: Type = typer.Option(default, "--param", help="Description")
):
    """CLI command description"""
    return tool_batch(source_folder, source_manifest, output_folder, param=param)
```

### Skip Processing Mode

All tools support `skip_processing=True` for workflow testing:
- Creates output folders and manifest files
- Creates empty/placeholder output files
- Skips actual processing logic
- Useful for fast workflow validation

---

**End of Tool Reference Documentation**

*Last Updated: 2025-11-15*
*Phase 1 Status: Complete*
*Next Phase: Phase 2 - Unified Parameter System Design*
