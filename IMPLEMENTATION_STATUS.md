# Implementation Status - 4 New Tools

## Status: READY TO IMPLEMENT

All planning documentation is complete. Ready to implement each tool.

## Completed Planning ✅

1. **METADATA_EXTRACTION_PLAN.md** - Complete specification for library metadata extraction
2. **VISUAL_DESCRIPTION_PLAN.md** - Complete specification for visual description tool
3. **SVG_CONVERSION_PLAN.md** - Complete specification for SVG generation (3-step process)
4. **COMPREHENSIVE_IMPLEMENTATION_PLAN.md** - Master plan for all 4 tools

## Implementation Approach

### Tool 1: describe_images.py (500+ lines)
**Model**: transcribe_qwen_max.py
**Key Components**:
- encode_image() - Reuse from transcribe_qwen_max.py
- process_image_sync() - Modified for visual description
- ParallelBatchProcessor - Reuse pattern
- Visual description prompt (detailed JSON output)
- Skip processing mode
- Full manifest with JSON

**Prompt**:
```
Analyze this document image and provide detailed visual description as JSON.

Include:
- layout: Overall structure
- content_type: Document type
- text_regions: Array of text areas
- visual_elements: Colors, condition, features
- image_quality: Resolution, clarity
- estimated_era: Time period
- preservation_notes: Damage, wear

Return ONLY valid JSON.
```

### Tool 2: extract_library_metadata.py (200+ lines)
**Model**: build_documents_manifest.py
**Key Components**:
- Load source manifest
- Query library database (LibraryStorage)
- Match items by source_path
- Create metadata manifest
- Handle missing items gracefully
- Skip processing mode

### Tool 3: convert_to_svg.py (800+ lines)
**Model**: transcribe_qwen_max.py + custom SVG builder
**Key Components**:
- 3-step process:
  1. generate_svg_draft() - First attempt
  2. critique_svg() - Ask model to critique
  3. generate_svg_final() - Improved version
- SVG cleanup - Fix XML issues
- Load transcriptions, metadata, visual descriptions
- Parallel processing
- Skip processing mode

**Prompts**:
1. **Generate**: "Create SVG from image + transcription + metadata"
2. **Critique**: "Review this SVG and suggest improvements"
3. **Regenerate**: "Create improved SVG based on critique"

### Tool 4: analyze_document_groups.py (600+ lines)
**Model**: transcribe_qwen_max.py + ffmpeg integration
**Key Components**:
- create_thumbnails() - Resize images
- create_video_from_images() - ffmpeg command
- analyze_video() - Send to Qwen VL Max
- parse_frame_changes() - Extract timestamps
- group_documents() - Group by visual similarity
- Skip processing mode

**Video Analysis Prompt**:
```
You are watching a video made from document images.
Each frame shows a different document.

Identify the frames (timestamps) where the DOCUMENT TYPE changes.
For example:
- Frame 0-10: Handwritten letters
- Frame 11-25: Typed legal documents (CHANGE)
- Frame 26-30: Photographs (CHANGE)

Return JSON with change points and document type for each group.
```

## File Structure

```
src/fichero/tools/
├── describe_images.py           # ~500 lines
├── extract_library_metadata.py  # ~200 lines
├── convert_to_svg.py            # ~800 lines
├── analyze_document_groups.py   # ~600 lines
└── utils/
    └── svg_builder.py           # ~300 lines (helper for SVG tool)

tests/
├── test_describe_images.py
├── test_extract_library_metadata.py
├── test_convert_to_svg.py
└── test_analyze_document_groups.py
```

## Dependencies

- ✅ **Qwen VL Max API**: Already have (DASHSCOPE_API_KEY)
- ⚠️ **FFmpeg**: Need to install (`brew install ffmpeg`)
- ✅ **PIL/Pillow**: Already have
- ✅ **OpenAI client**: Already have

## Next Steps

1. Implement describe_images.py (copy structure from transcribe_qwen_max.py)
2. Test describe_images.py with sample images
3. Implement extract_library_metadata.py
4. Test extract_library_metadata.py
5. Install ffmpeg: `brew install ffmpeg`
6. Implement convert_to_svg.py (3-step process)
7. Test convert_to_svg.py
8. Implement analyze_document_groups.py (video processing)
9. Test analyze_document_groups.py
10. Update Generic_Catalogue.yml workflow
11. Update llm_process.py to accept metadata + visual descriptions
12. Update Generic_Catalogue.jsonl prompts
13. End-to-end test

## Testing Commands

```bash
# Test describe_images
PYTHONPATH=src python -m fichero.tools.describe_images \
  assets/enhanced assets/enhanced/enhance_manifest.jsonl \
  assets/visual_descriptions --skip-processing

# Test extract_library_metadata
PYTHONPATH=src python -m fichero.tools.extract_library_metadata \
  assets/cleaned assets/cleaned/cleaned_manifest.jsonl \
  assets/library_metadata --skip-processing

# Test convert_to_svg
PYTHONPATH=src python -m fichero.tools.convert_to_svg \
  assets/enhanced assets/enhanced/enhance_manifest.jsonl \
  assets/svg --skip-processing

# Test analyze_document_groups
PYTHONPATH=src python -m fichero.tools.analyze_document_groups \
  assets/enhanced assets/enhanced/enhance_manifest.jsonl \
  assets/document_groups --skip-processing

# Test full workflow
briefcase dev -- library process <collection_id> --items <item_id> \
  --plan "Generic_Catalogue" --workflow "Default"
```

## Estimated Implementation Time

- describe_images.py: 2 hours
- extract_library_metadata.py: 1 hour
- convert_to_svg.py: 3 hours (3-step process + SVG building)
- analyze_document_groups.py: 3 hours (video processing + ffmpeg)
- Testing + Integration: 2 hours
- **Total**: ~11 hours

## Implementation Notes

### Common Patterns (from existing tools)

1. **Batch Processing**:
   ```python
   class CustomBatchProcessor(BatchProcessor):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)

       def _process_file(self, file_path, output_path):
           # Process single file
           pass
   ```

2. **Skip Processing**:
   ```python
   if skip_processing:
       # Create empty/stub output
       output_path.write_text("{}")
       return {"source": str(rel_path), "skipped": True}
   ```

3. **Manifest Saving**:
   ```python
   result = {
       "source": str(rel_path),
       "outputs": [str(output_rel_path)],
       "details": {
           "full": "json data here"
       },
       "processed_at": datetime.now().isoformat()
   }
   ```

4. **API Key Handling**:
   ```python
   from fichero.tools.utils.api_keys import get_qwen_key
   api_key = get_qwen_key(api_key_cli)
   if not api_key:
       raise ValueError("API key required")
   ```

5. **Parallel Processing**:
   ```python
   with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
       futures = {executor.submit(process_fn, item): item for item in items}
       for future in concurrent.futures.as_completed(futures):
           result = future.result()
   ```

## Ready to Code

All architectural decisions made. All patterns identified. All prompts defined.

**Status**: Implementation can begin immediately.

Each tool follows the established patterns from existing tools, ensuring consistency and reliability.
