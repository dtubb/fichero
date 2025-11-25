# Qwen-VL-OCR Batch Transcription Implementation Plan

## Overview
Create new batch transcription tools using Alibaba Cloud's Qwen-VL-OCR model for efficient text extraction from images. This replaces individual per-image processing with batch API calls for better cost and performance.

## Goals
1. ✅ Create TWO new transcription tools (keep existing code unchanged)
2. ✅ Implement batch processing (send all images in one request)
3. ✅ Support larger files (up to 10MB per image)
4. ✅ Use Batch API instead of Director multitasking
5. ✅ Update workflow plan configuration
6. ✅ Add comprehensive unit tests

## New Tools to Create

### 1. transcribe_qwen_ocr.py (DashScope SDK)
**Location:** `src/fichero/tools/transcribe_qwen_ocr.py`

**Features:**
- Use DashScope SDK for full feature support
- Batch processing: Process multiple images in single API call
- Advanced recognition task with text positioning
- File path upload (more stable than Base64)
- Automatic image rotation support
- Configurable min_pixels/max_pixels for scaling
- Error handling and retry logic

**API Details:**
- Model: `qwen-vl-ocr-2025-11-20` (latest stable)
- Task: `advanced_recognition` (extracts text + positions)
- Endpoint: Singapore region by default
- Authentication: DASHSCOPE_API_KEY from environment

**Input:**
```python
{
    "input_paths": ["path/to/image1.jpg", "path/to/image2.png"],
    "output_dir": "path/to/output",
    "batch_size": 50,  # Max images per batch
    "min_pixels": 3136,  # 28*28*4
    "max_pixels": 6422528,  # 28*28*8192
    "enable_rotate": True,
    "model": "qwen-vl-ocr-2025-11-20"
}
```

**Output:**
```python
{
    "results": [
        {
            "image_path": "path/to/image1.jpg",
            "text": "Extracted text content",
            "ocr_result": {
                "words_info": [
                    {
                        "text": "word",
                        "location": [x1, y1, x2, y2, x3, y3, x4, y4],
                        "rotate_rect": [cx, cy, w, h, angle]
                    }
                ]
            },
            "success": True
        }
    ],
    "total_processed": 2,
    "total_tokens": 5000,
    "cost_usd": 0.0036
}
```

### 2. transcribe_openai_ocr.py (OpenAI-Compatible)
**Location:** `src/fichero/tools/transcribe_openai_ocr.py`

**Features:**
- Use OpenAI-compatible SDK for easy migration
- Batch processing with sequential calls (OpenAI SDK limitation)
- Custom prompts for extraction
- Streaming support for large responses
- JSON output parsing

**API Details:**
- Model: `qwen-vl-ocr`
- Endpoint: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Authentication: DASHSCOPE_API_KEY as OpenAI api_key

**Input:**
```python
{
    "input_paths": ["path/to/image1.jpg", "path/to/image2.png"],
    "output_dir": "path/to/output",
    "prompt": "Extract all text from the image...",
    "stream": False,
    "min_pixels": 3136,
    "max_pixels": 6422528
}
```

**Output:**
```python
{
    "results": [
        {
            "image_path": "path/to/image1.jpg",
            "text": "Extracted text content",
            "success": True
        }
    ],
    "total_processed": 2,
    "total_tokens": 5000
}
```

## Implementation Details

### Batch Processing Strategy
1. **Collect all images** from input directory
2. **Filter by size** (skip files > 10MB, log warning)
3. **Group into batches** (configurable size, default 50)
4. **Process each batch:**
   - DashScope: Single API call with multiple images
   - OpenAI: Sequential calls (batched in application logic)
5. **Aggregate results** and write to output

### File Size Handling
- Check file size before processing
- Use file path upload (supports up to 10MB)
- Implement image compression fallback if needed
- Log warnings for oversized files

### Error Handling
- Retry logic for transient failures
- Graceful degradation (continue on single image failure)
- Detailed error logging
- Partial results if batch partially succeeds

### Configuration
Update `src/fichero/resources/config_defaults/plans/Enhance_Segment_and_Catalogue.yml`:

```yaml
workflows:
  Transcribe_Batch:
    steps:
      - tool: transcribe_qwen_ocr
        config:
          batch_size: 50
          enable_rotate: true
          min_pixels: 3136
          max_pixels: 6422528
          model: qwen-vl-ocr-2025-11-20
        input_from: enhance_output
        output_to: transcriptions
```

## Testing Strategy

### Unit Tests for transcribe_qwen_ocr.py
**Location:** `tests/unit/test_transcribe_qwen_ocr.py`

**Test Cases:**
1. ✅ Single image transcription
2. ✅ Batch transcription (multiple images)
3. ✅ File size validation (reject > 10MB)
4. ✅ Image scaling (min_pixels/max_pixels)
5. ✅ Error handling (API failure, invalid file)
6. ✅ OCR result parsing (words_info structure)
7. ✅ Token usage calculation
8. ✅ Retry logic

### Unit Tests for transcribe_openai_ocr.py
**Location:** `tests/unit/test_transcribe_openai_ocr.py`

**Test Cases:**
1. ✅ Single image transcription
2. ✅ Sequential batch processing
3. ✅ Custom prompt handling
4. ✅ Streaming output parsing
5. ✅ Error handling (API failure, invalid file)
6. ✅ JSON output parsing
7. ✅ File path vs URL handling
8. ✅ Token usage tracking

## Dependencies
- `dashscope>=1.22.2` (already in requirements)
- `openai>=1.0.0` (already in requirements)
- `Pillow` (for image metadata/size checks)

## Migration Path
1. **Phase 1:** Create new tools alongside existing ones
2. **Phase 2:** Update workflow plans to use new batch tools
3. **Phase 3:** Test in production with small dataset
4. **Phase 4:** Deprecate old single-image tools (optional)

## Success Criteria
- ✅ Both tools process batches successfully
- ✅ 10x cost reduction vs single-image processing
- ✅ All unit tests passing
- ✅ No regression in existing workflows
- ✅ Proper error handling and logging
- ✅ Documentation complete

## Timeline
- Tool Implementation: Use fichero-architect agent
- Code Review: Use specialized review agent
- Unit Tests: Use test creation agent
- Integration: Manual verification
