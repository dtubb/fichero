# Comprehensive Implementation Plan - 4 New Tools

## Overview
Implementing 4 new tools to enhance the document processing pipeline with visual analysis, metadata extraction, SVG generation, and document grouping.

## Tools to Implement

### 1. **describe_images.py** - Visual Description Tool
- **Based on**: transcribe_qwen_max.py
- **Model**: Qwen VL Max (same API as transcription)
- **Input**: Enhanced images
- **Output**: JSON visual descriptions
- **Flags**: `--skip-processing`, `--testing`
- **Manifest**: Save full visual description JSON

### 2. **extract_library_metadata.py** - Metadata Extraction Tool
- **Based on**: build_documents_manifest.py
- **Model**: N/A (database query)
- **Input**: Source manifest + library database
- **Output**: Metadata manifest with library JSON
- **Flags**: `--skip-processing`
- **Manifest**: Save complete library metadata

### 3. **convert_to_svg.py** - SVG Conversion Tool (3-step)
- **Based on**: transcribe_qwen_max.py
- **Model**: Qwen VL Max
- **Process**:
  1. Generate SVG with Qwen VL Max
  2. Critique SVG with Qwen VL Max
  3. Regenerate improved SVG
  4. Clean up SVG (fix XML issues)
- **Input**: Images + transcriptions + metadata + visual descriptions
- **Output**: Semantic SVG files
- **Flags**: `--skip-processing`, `--testing`, `--skip-critique`
- **Manifest**: Save SVG metadata and critique results

### 4. **analyze_document_groups.py** - Video-based Document Grouping
- **Based on**: transcribe_qwen_max.py + ffmpeg
- **Model**: Qwen VL Max
- **Process**:
  1. Resize images to thumbnails
  2. Create video from images (ffmpeg)
  3. Send video to Qwen VL Max
  4. Ask model to identify frames where document type changes
  5. Group documents by visual similarity
- **Input**: Enhanced images manifest
- **Output**: Document grouping JSON
- **Flags**: `--skip-processing`, `--fps`, `--thumbnail-size`
- **Manifest**: Save grouping results and frame analysis

## Implementation Order

1. ✅ Create plan
2. → Implement describe_images.py
3. → Test describe_images.py
4. → Implement extract_library_metadata.py
5. → Test extract_library_metadata.py
6. → Install ffmpeg
7. → Implement convert_to_svg.py
8. → Test convert_to_svg.py
9. → Implement analyze_document_groups.py
10. → Test analyze_document_groups.py
11. → Update Generic_Catalogue.yml
12. → Update llm_process.py
13. → Update Generic_Catalogue.jsonl
14. → End-to-end testing

## File Structure

```
src/fichero/tools/
├── describe_images.py           # NEW - Visual descriptions
├── extract_library_metadata.py  # NEW - Library metadata
├── convert_to_svg.py            # NEW - SVG generation (3-step)
├── analyze_document_groups.py   # NEW - Video-based grouping
└── utils/
    └── svg_builder.py           # NEW - SVG building utilities

tests/
├── test_describe_images.py
├── test_extract_library_metadata.py
├── test_convert_to_svg.py
└── test_analyze_document_groups.py
```

## Workflow Integration

**Complete Enhanced Workflow**:
```yaml
workflows:
  Default:
    - build_documents_manifest
    - enhance
    - segment
    - transcribe_qwen_max_segmented
    - recombine_segments
    - fuzzy_clean
    - describe_images              # NEW - Step 1
    - extract_library_metadata     # NEW - Step 2
    - convert_to_svg               # NEW - Step 3 (3-step process)
    - analyze_document_groups      # NEW - Step 4
    - catalogue_folder             # Enhanced with metadata + visuals
    - convert_to_word_segmented
    - catalogue_to_word
```

## API Requirements

- **Qwen VL Max API Key**: DASHSCOPE_API_KEY (already have)
- **FFmpeg**: Install via homebrew (`brew install ffmpeg`)

## Testing Strategy

Each tool will have:
1. Unit test with sample data
2. Skip processing mode for fast testing
3. Manifest validation
4. Error handling tests

## Success Criteria

- ✅ All tools run without errors
- ✅ All manifests are valid JSONL
- ✅ All JSON data is preserved in manifests
- ✅ Skip processing works for all tools
- ✅ Unit tests pass
- ✅ Integration with Generic_Catalogue workflow works
- ✅ End-to-end test completes successfully
