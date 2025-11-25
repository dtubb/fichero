# Transcription Architecture Refactoring

## Overview

The transcription system has been refactored from multiple monolithic tools into a unified plugin-based architecture. This provides a cleaner, more maintainable codebase with pluggable provider backends.

## Architecture

### Before (Monolithic)

```
transcribe_qwen_max.py       (700+ lines, hardcoded batch logic, parallel processing)
transcribe_qwen_ocr.py       (370+ lines, hardcoded sequential processing)
transcribe_openai_ocr.py     (610+ lines, hardcoded parallel processing)
transcribe_lmstudio.py       (470+ lines, hardcoded async processing)
```

**Problems:**
- Duplicated batch processing code across all tools
- Different max_size limits hardcoded (1024, 1500, etc.)
- Mixed concerns: image encoding, API calls, batch handling
- Hard to test individual providers
- Workflow files directly coupled to specific implementations

### After (Plugin-Based)

```
transcribe.py                           # Unified entry point (400 lines)
transcribe_providers/
  ├── __init__.py                       # Provider registry
  ├── base_provider.py                  # Abstract base interface
  ├── dashscope_provider.py             # DashScope SDK (qwen-vl-max, qwen-vl-ocr)
  ├── openai_provider.py                # OpenAI-compatible API
  └── lmstudio_provider.py              # Local LMStudio
```

**Benefits:**
- Clean separation of concerns
- Consistent batch processing logic
- Easy to add new providers
- Testable provider plugins
- Workflow files use unified `transcribe.py` with provider parameter

## Provider Interface

All providers implement `BaseTranscriptionProvider`:

```python
class BaseTranscriptionProvider(ABC):
    @abstractmethod
    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """Process single image, return {text, success, details}"""
        pass

    def validate_config(self) -> bool:
        """Validate provider configuration"""
        pass

    def cleanup(self):
        """Clean up resources"""
        pass

    @property
    def supports_parallel(self) -> bool:
        """Whether provider supports parallel processing"""
        return False
```

## Providers

### 1. DashScope Provider

**File:** `transcribe_providers/dashscope_provider.py`

**Features:**
- Official DashScope SDK with OpenAI-compatible client
- Multiple models: `qwen-vl-max`, `qwen-vl-ocr`, `qwen3-vl-flash`
- Progressive image resizing on timeout (1024→768→512→256)
- Parallel processing support
- Built-in retry with exponential backoff
- API key validation before batch processing

**Configuration:**
```python
DashScopeProvider(
    api_key="your-key",
    model="qwen-vl-max",          # or "qwen-vl-ocr"
    prompt="Custom prompt...",
    max_size=1024,                 # Max image dimension
    timeout=180.0                  # Request timeout
)
```

**Models:**
- `qwen-vl-max` → `qwen3-vl-235b-a22b-instruct` (high quality, flagship)
- `qwen-vl-ocr` → `qwen-vl-ocr` (OCR optimized)
- `qwen3-vl-flash` → `qwen3-vl-flash` (fast, lower quality)

### 2. OpenAI Provider

**File:** `transcribe_providers/openai_provider.py`

**Features:**
- OpenAI-compatible API (works with any compatible endpoint)
- Configurable min_pixels/max_pixels for image scaling
- Streaming support
- Parallel processing support
- Token usage tracking

**Configuration:**
```python
OpenAIProvider(
    api_key="your-key",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model="qwen-vl-ocr",
    stream=False,
    min_pixels=3136,
    max_pixels=6422528
)
```

**Use Cases:**
- Quick migration from existing OpenAI integrations
- Projects already using OpenAI SDK ecosystem

**Limitations:**
- No advanced features (auto-rotation, built-in OCR tasks)
- Must manually craft prompts for complex tasks

### 3. LMStudio Provider

**File:** `transcribe_providers/lmstudio_provider.py`

**Features:**
- Local processing (privacy-focused)
- Connects to local LMStudio instance
- Aggressive image resizing for local performance
- Connection validation

**Configuration:**
```python
LMStudioProvider(
    api_url="http://localhost:1234/v1",
    model_name="qwen2.5-vl-7b-instruct",  # Must match LMStudio model
    max_size=1024,                         # Smaller for local processing
    max_tokens=2048,
    temperature=0.7
)
```

**Use Cases:**
- Privacy-sensitive documents
- Offline processing
- Custom local models

**Limitations:**
- Slower than cloud APIs
- Sequential processing recommended (avoid overloading local machine)
- Limited to models available in LMStudio

## Unified Transcribe Tool

**File:** `transcribe.py`

### Command-Line Usage

```bash
# DashScope with Qwen VL Max (default)
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max

# DashScope with Qwen VL OCR
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-ocr

# OpenAI-compatible API
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider openai --model qwen-vl-ocr

# LMStudio (local)
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider lmstudio --model my-model --api-url http://localhost:1234

# With custom prompt
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max \
    --prompt "Extract text preserving layout and structure"

# With parallel workers (for parallel-capable providers)
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max --max-workers 10
```

### Workflow YAML Usage

All workflow files now use the unified tool with provider parameters:

```yaml
- name: transcribe
  worker_type: "io"
  help: "Transcribe images using AI models"
  function: "fichero.tools.transcribe.transcribe_batch"
  args:
    source_folder: "assets/enhanced"
    source_manifest: "assets/enhanced/enhance_manifest.jsonl"
    output_folder: "assets/transcriptions"
    provider: "dashscope"        # Provider selection
    model: "qwen-vl-max"         # Model selection
    prompt: "Custom prompt..."   # Optional custom prompt
  outputs:
    - "assets/transcriptions"
    - "assets/transcriptions/transcriptions_manifest.jsonl"
```

### Programmatic Usage

```python
from pathlib import Path
from fichero.tools.transcribe import transcribe_batch

# DashScope provider
stats = transcribe_batch(
    source_folder=Path("input"),
    source_manifest=Path("input/manifest.jsonl"),
    output_folder=Path("output"),
    provider="dashscope",
    model="qwen-vl-max",
    api_key_cli="your-api-key",
    max_workers=5
)

# LMStudio provider
stats = transcribe_batch(
    source_folder=Path("input"),
    source_manifest=Path("input/manifest.jsonl"),
    output_folder=Path("output"),
    provider="lmstudio",
    model="qwen2.5-vl-7b-instruct",
    api_url="http://localhost:1234"
)
```

## Batch Processing

The unified tool automatically selects the appropriate batch processing strategy based on the provider:

### Parallel Processing (DashScope, OpenAI)

- Uses `ThreadPoolExecutor` with configurable workers
- Default: 5 concurrent workers
- Efficient for cloud APIs with high throughput

### Sequential Processing (LMStudio)

- Processes one image at a time
- Prevents overloading local machine
- Better for local/limited resources

## Migration Guide

### For Workflow Files

**Old:**
```yaml
function: "fichero.tools.transcribe_qwen_max.transcribe_batch"
args:
  source_folder: "documents"
  source_manifest: "manifest.jsonl"
  output_folder: "transcriptions"
```

**New:**
```yaml
function: "fichero.tools.transcribe.transcribe_batch"
args:
  source_folder: "documents"
  source_manifest: "manifest.jsonl"
  output_folder: "transcriptions"
  provider: "dashscope"
  model: "qwen-vl-max"
```

### For Python Code

**Old:**
```python
from fichero.tools.transcribe_qwen_max import transcribe_batch

stats = transcribe_batch(
    source_folder=input_dir,
    source_manifest=manifest,
    output_folder=output_dir
)
```

**New:**
```python
from fichero.tools.transcribe import transcribe_batch

stats = transcribe_batch(
    source_folder=input_dir,
    source_manifest=manifest,
    output_folder=output_dir,
    provider="dashscope",
    model="qwen-vl-max"
)
```

## Adding New Providers

To add a new provider:

1. Create new file in `transcribe_providers/`:

```python
from .base_provider import BaseTranscriptionProvider

class MyProvider(BaseTranscriptionProvider):
    def __init__(self, api_key, **config):
        super().__init__(api_key, **config)
        # Initialize your provider

    @property
    def name(self) -> str:
        return "My Provider"

    @property
    def model(self) -> str:
        return self.model_name

    def process_image(self, image_path: Path) -> Dict[str, Any]:
        # Implement image processing
        return {
            "text": "transcribed text",
            "success": True,
            "details": {...}
        }
```

2. Register in `transcribe.py`:

```python
from transcribe_providers.my_provider import MyProvider

class ProviderFactory:
    PROVIDERS = {
        "dashscope": DashScopeProvider,
        "openai": OpenAIProvider,
        "lmstudio": LMStudioProvider,
        "myprovider": MyProvider  # Add here
    }
```

3. Use in workflows:

```yaml
provider: "myprovider"
model: "my-model-name"
```

## Testing

### Testing Individual Providers

```python
from pathlib import Path
from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider

# Create provider
provider = DashScopeProvider(
    api_key="test-key",
    model="qwen-vl-max"
)

# Validate config
assert provider.validate_config()

# Test single image
result = provider.process_image(Path("test.jpg"))
assert result["success"]
assert "text" in result

# Cleanup
provider.cleanup()
```

### Testing Batch Processing

```bash
# Test with small subset
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max --testing

# Test different providers
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-ocr
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider openai --model qwen-vl-ocr
briefcase dev -- transcribe INPUT MANIFEST OUTPUT --provider lmstudio --model my-model
```

## Performance Comparison

| Provider | Model | Parallel | Typical Speed | Best For |
|----------|-------|----------|---------------|----------|
| DashScope | qwen-vl-max | Yes (5-10 workers) | ~3-5s/image | High quality transcription |
| DashScope | qwen-vl-ocr | Yes (5-10 workers) | ~2-3s/image | Fast OCR |
| OpenAI | qwen-vl-ocr | Yes (5-10 workers) | ~2-3s/image | OpenAI ecosystem |
| LMStudio | custom | No (sequential) | ~8-15s/image | Privacy, offline |

## Configuration Recommendations

### High Volume Processing (100+ images)
```yaml
provider: "dashscope"
model: "qwen-vl-ocr"
max_workers: 10
```

### High Quality Requirements
```yaml
provider: "dashscope"
model: "qwen-vl-max"
max_workers: 5
```

### Privacy-Sensitive Documents
```yaml
provider: "lmstudio"
model: "qwen2.5-vl-7b-instruct"
api_url: "http://localhost:1234"
```

### Existing OpenAI Integration
```yaml
provider: "openai"
model: "qwen-vl-ocr"
stream: true
```

## Files Changed

### New Files Created
- `src/fichero/tools/transcribe.py` - Unified transcribe tool
- `src/fichero/tools/transcribe_providers/__init__.py`
- `src/fichero/tools/transcribe_providers/base_provider.py`
- `src/fichero/tools/transcribe_providers/dashscope_provider.py`
- `src/fichero/tools/transcribe_providers/openai_provider.py`
- `src/fichero/tools/transcribe_providers/lmstudio_provider.py`

### Workflow Files Updated
- `src/fichero/resources/config_defaults/plans/Transcribe.yml`
- `src/fichero/resources/config_defaults/plans/Enhance_Segment_and_Catalogue.yml`
- `src/fichero/resources/config_defaults/plans/Default.yml`
- `src/fichero/resources/config_defaults/plans/Default_English.yml`
- `src/fichero/resources/config_defaults/plans/Enhance_Images_and_Catalogue.yml`
- `src/fichero/resources/config_defaults/plans/Segment_and_Catalogue.yml`
- `src/fichero/resources/config_defaults/plans/Quotations.yml`
- `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml`

### Legacy Files (Can Be Deprecated)
- `src/fichero/tools/transcribe_qwen_max.py` - Still works, but use `transcribe.py` with `provider=dashscope, model=qwen-vl-max`
- `src/fichero/tools/transcribe_qwen_ocr.py` - Still works, but use `transcribe.py` with `provider=dashscope, model=qwen-vl-ocr`
- `src/fichero/tools/transcribe_openai_ocr.py` - Still works, but use `transcribe.py` with `provider=openai`
- `src/fichero/tools/transcribe_lmstudio.py` - Still works, but use `transcribe.py` with `provider=lmstudio`

**Note:** Legacy files are kept for backward compatibility but are no longer used by workflows.

## Summary

The refactoring achieves:

✅ **Cleaner Architecture** - Providers as plugins, not monoliths
✅ **Better Maintainability** - Shared batch logic, consistent interface
✅ **Easier Testing** - Test providers independently
✅ **Flexible Configuration** - Switch providers without code changes
✅ **Future-Proof** - Easy to add new providers
✅ **Backward Compatible** - Legacy tools still work
✅ **Unified Batch Handling** - Consistent processing logic
✅ **Clear Separation** - Image encoding, API calls, batch processing separated

The new architecture follows Andy's proven LangChain/LangGraph pattern while maintaining the working qwen_max functionality.
