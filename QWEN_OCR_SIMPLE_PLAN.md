# Qwen-VL-OCR Simple Implementation Plan

## Philosophy: Keep It Simple

Based on Andy's example code, we'll create ONE clean tool that processes images sequentially with streaming support. No complex batching, no LangGraph (Fichero already has Director), just solid maintainable code.

## Single Tool: transcribe_qwen_ocr.py

**Location:** `src/fichero/tools/transcribe_qwen_ocr.py`

### Core Design (Based on Andy's Pattern)

```python
from openai import OpenAI
from pathlib import Path
import base64
import os

def process_images_with_streaming(
    image_paths: list[Path],
    prompt: str,
    output_dir: Path,
    progress_callback=None
) -> list[dict]:
    """Process images sequentially with streaming (like Andy's code)."""

    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    )

    results = []
    for idx, image_path in enumerate(image_paths):
        # Encode image to base64 (Andy's approach)
        image_data = encode_image_to_base64(image_path)

        # Stream the response
        chat_completion = client.chat.completions.create(
            model="qwen-vl-ocr",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data}},
                    {"type": "text", "text": prompt}
                ]
            }],
            stream=True,
            temperature=0
        )

        # Collect streamed response
        response_text = ""
        for chunk in chat_completion:
            token = getattr(chunk.choices[0].delta, "content", None)
            if token:
                response_text += token
                if progress_callback:
                    progress_callback(idx, len(image_paths), token)

        results.append({
            "image_path": str(image_path),
            "text": response_text,
            "success": True
        })

    return results

def encode_image_to_base64(image_path: Path) -> str:
    """Encode image to base64 data URI (Andy's helper)."""
    with open(image_path, 'rb') as img_file:
        encoded = base64.b64encode(img_file.read()).decode('utf-8')
        mime_type = 'image/jpeg' if image_path.suffix.lower() in ['.jpg', '.jpeg'] else 'image/png'
        return f"data:{mime_type};base64,{encoded}"
```

### Integration with Fichero Architecture

```python
class TranscribeQwenOCR:
    """Fichero tool for Qwen-VL-OCR transcription."""

    def __init__(self, config: dict):
        self.config = config
        self.prompt = config.get('prompt', 'Extract all text from this image.')
        self.stream = config.get('stream', True)
        self.max_file_size_mb = config.get('max_file_size_mb', 10)

    def execute(self, input_dir: Path, output_dir: Path) -> dict:
        """Main execution method (Fichero tool interface)."""

        # Collect images
        image_paths = self._collect_images(input_dir)

        # Validate file sizes
        valid_paths = self._validate_file_sizes(image_paths)

        # Process with streaming
        results = process_images_with_streaming(
            image_paths=valid_paths,
            prompt=self.prompt,
            output_dir=output_dir,
            progress_callback=self._on_progress
        )

        # Save results
        self._save_results(results, output_dir)

        return {
            "total_processed": len(results),
            "results": results
        }
```

## Key Features

### 1. Simple Sequential Processing
- Process one image at a time (like Andy's code)
- Use streaming for responsiveness
- No complex batching logic

### 2. File Size Handling
```python
def _validate_file_sizes(self, image_paths: list[Path]) -> list[Path]:
    """Filter images by size (max 10MB for base64)."""
    valid = []
    for path in image_paths:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb <= self.max_file_size_mb:
            valid.append(path)
        else:
            logger.warning(f"Skipping {path.name}: {size_mb:.1f}MB > {self.max_file_size_mb}MB")
    return valid
```

### 3. Progress Reporting
```python
def _on_progress(self, current: int, total: int, token: str):
    """Report progress during streaming."""
    logger.info(f"Processing {current+1}/{total}: {token[:50]}...")
```

### 4. Error Handling
```python
try:
    results = process_images_with_streaming(...)
except Exception as e:
    logger.error(f"Failed to process {image_path}: {e}")
    # Continue with next image
    continue
```

## Configuration (YAML)

```yaml
# src/fichero/resources/config_defaults/plans/Enhance_Segment_and_Catalogue.yml
workflows:
  Transcribe:
    steps:
      - tool: transcribe_qwen_ocr
        config:
          prompt: "Extract all text from this image. Return plain text only."
          stream: true
          max_file_size_mb: 10
          temperature: 0
        input_from: enhance_output
        output_to: transcriptions
```

## Testing Strategy

### Unit Tests: tests/unit/test_transcribe_qwen_ocr.py

```python
def test_single_image_streaming():
    """Test single image with streaming."""
    # Mock OpenAI client
    # Verify streaming response collection
    # Check output format

def test_base64_encoding():
    """Test image encoding."""
    # Verify base64 data URI format
    # Check MIME type detection

def test_file_size_validation():
    """Test file size filtering."""
    # Create 11MB dummy file
    # Verify it's skipped with warning

def test_error_handling():
    """Test API errors don't stop processing."""
    # Mock API failure on image 2
    # Verify images 1 and 3 succeed
```

## Implementation Steps

1. **Create transcribe_qwen_ocr.py** (1 file, ~200 lines)
   - Copy Andy's streaming pattern
   - Add Fichero tool interface
   - Add file validation and error handling

2. **Update workflow config** (1 line change)
   - Point to new tool in YAML

3. **Create unit tests** (1 file, ~150 lines)
   - Test streaming, encoding, validation, errors

4. **Review and fix** (agent-based)
   - Code review agent
   - Fix any issues

## Why This Is Better

✅ **Simple**: ~200 lines vs 500+ with complex batching
✅ **Proven**: Based on Andy's working code
✅ **Maintainable**: Easy to understand and debug
✅ **Responsive**: Streaming gives real-time feedback
✅ **Robust**: Handles errors gracefully
✅ **Compatible**: Fits Fichero's existing architecture

## What We're NOT Doing

❌ Complex batching (unnecessary complexity)
❌ LangGraph integration (Fichero has Director)
❌ Two separate tools (one is enough)
❌ DashScope SDK (OpenAI SDK simpler)
❌ Advanced features we won't use

## Dependencies

Already in requirements:
- `openai>=1.0.0`
- `Pillow` (for image validation)

## Success Criteria

- ✅ Processes images sequentially with streaming
- ✅ Handles files up to 10MB
- ✅ Continues on errors
- ✅ Integrates with existing Fichero workflows
- ✅ All tests passing
- ✅ Clean, maintainable code
