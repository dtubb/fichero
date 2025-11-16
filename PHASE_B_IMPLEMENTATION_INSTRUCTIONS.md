# PHASE B: PARAMETER UI IMPLEMENTATION INSTRUCTIONS

**Objective:** Create ToolRegistry schemas for 5 priority tools to enable GUI parameter configuration

**Current Status:** 5/20 tools have parameter schemas (25%)
**Target Status:** 10/20 tools have parameter schemas (50%)

---

## TOOLS TO ADD SCHEMAS FOR

### Priority Tools (5)

1. **transcribe_lmstudio** - Local AI transcription
   - Model selection dropdown
   - API URL text input
   - Prompt selection dropdown

2. **llm_process** - Structured data extraction
   - Prompt config selection
   - Hierarchical mode checkbox
   - LLM backend dropdown

3. **prepare_images** - Image preparation
   - Quality slider (0-100)
   - Format dropdown (jpg/png/webp)
   - Max size input

4. **remove_background** - Background removal
   - Method dropdown (rembg/opencv)

5. **segment** - Image segmentation
   - Max pixels input
   - Overlap percentage slider

---

## FILE TO MODIFY

**File:** `src/fichero/windows/main/views/shared/tool_registry.py`

**Current Structure:**
```python
class ToolRegistry:
    def __init__(self):
        self.tools = {
            'crop': self._create_crop_schema(),
            'rotate': self._create_rotate_schema(),
            'enhance': self._create_enhance_schema(),
            'split': self._create_split_schema(),
            'transcribe_qwen_max': self._create_transcribe_schema(),
            # ADD 5 NEW TOOLS HERE
        }
```

---

## SCHEMA STRUCTURE

Each schema method returns a dictionary with parameter definitions:

```python
def _create_{tool}_schema(self):
    """Create parameter schema for {tool} tool"""
    return {
        'parameter_name': {
            'type': 'enum' | 'integer' | 'float' | 'string' | 'boolean',
            'values': ['option1', 'option2'],  # For enum only
            'min': 0,                          # For integer/float only
            'max': 100,                        # For integer/float only
            'default': default_value,
            'label': 'Display Label',
            'description': 'Help text for user',
            'required': True | False,
        },
        # ... more parameters
    }
```

---

## IMPLEMENTATION DETAILS

### 1. transcribe_lmstudio Schema

**Reference:** `TOOL_REFERENCE.md` - transcribe_lmstudio parameters

```python
def _create_transcribe_lmstudio_schema(self):
    """Create parameter schema for LM Studio transcription"""
    return {
        'lmstudio_url': {
            'type': 'string',
            'default': 'http://localhost:1234',
            'label': 'LM Studio URL',
            'description': 'URL of running LM Studio server',
            'required': True,
        },
        'model_name': {
            'type': 'enum',
            'values': [
                'llava-1.5-7b-hf',
                'llava-1.6-mistral-7b',
                'llava-phi-3-mini',
                'cogvlm-grounding-generalist',
            ],
            'default': 'llava-1.5-7b-hf',
            'label': 'Model',
            'description': 'Vision-language model to use',
            'required': True,
        },
        'prompt': {
            'type': 'enum',
            'values': [
                'default_transcription',
                'handwriting_recognition',
                'printed_text',
                'mixed_content',
            ],
            'default': 'default_transcription',
            'label': 'Prompt Template',
            'description': 'Type of transcription to perform',
            'required': False,
        },
        'max_size': {
            'type': 'integer',
            'min': 512,
            'max': 2048,
            'default': 1024,
            'label': 'Max Image Size (px)',
            'description': 'Maximum image dimension',
            'required': False,
        },
    }
```

---

### 2. llm_process Schema

**Reference:** `TOOL_REFERENCE.md` - llm_process parameters

```python
def _create_llm_process_schema(self):
    """Create parameter schema for LLM processing"""
    return {
        'prompt_config': {
            'type': 'enum',
            'values': [
                'catalogue_generic',
                'catalogue_archival',
                'extract_quotations',
                'extract_dates',
                'extract_names',
                'custom',
            ],
            'default': 'catalogue_generic',
            'label': 'Prompt Configuration',
            'description': 'Type of structured extraction',
            'required': True,
        },
        'llm': {
            'type': 'enum',
            'values': [
                'qwen-max',
                'qwen-plus',
                'gpt-4o',
                'gpt-4o-mini',
            ],
            'default': 'qwen-max',
            'label': 'LLM Backend',
            'description': 'Language model to use',
            'required': True,
        },
        'hierarchical': {
            'type': 'boolean',
            'default': False,
            'label': 'Hierarchical Processing',
            'description': 'Process documents in folder hierarchy',
            'required': False,
        },
        'folder_mode': {
            'type': 'boolean',
            'default': False,
            'label': 'Folder Mode',
            'description': 'Process entire folders as single units',
            'required': False,
        },
    }
```

---

### 3. prepare_images Schema

**Reference:** `TOOL_REFERENCE.md` - prepare_images parameters

```python
def _create_prepare_images_schema(self):
    """Create parameter schema for image preparation"""
    return {
        'compression_quality': {
            'type': 'integer',
            'min': 1,
            'max': 100,
            'default': 95,
            'label': 'JPEG Quality',
            'description': 'Compression quality (1-100, higher is better)',
            'required': False,
        },
        'output_format': {
            'type': 'enum',
            'values': ['jpg', 'png', 'webp'],
            'default': 'jpg',
            'label': 'Output Format',
            'description': 'Image format for outputs',
            'required': False,
        },
        'max_size': {
            'type': 'integer',
            'min': 512,
            'max': 8192,
            'default': 4096,
            'label': 'Max Dimension (px)',
            'description': 'Maximum width or height',
            'required': False,
        },
    }
```

---

### 4. remove_background Schema

**Reference:** `TOOL_REFERENCE.md` - remove_background parameters

```python
def _create_remove_background_schema(self):
    """Create parameter schema for background removal"""
    return {
        'method': {
            'type': 'enum',
            'values': ['rembg', 'opencv'],
            'default': 'rembg',
            'label': 'Removal Method',
            'description': 'Algorithm to use (rembg is AI-based, opencv is simple)',
            'required': False,
        },
    }
```

---

### 5. segment Schema

**Reference:** `TOOL_REFERENCE.md` - segment parameters

```python
def _create_segment_schema(self):
    """Create parameter schema for image segmentation"""
    return {
        'max_pixels': {
            'type': 'integer',
            'min': 1000000,      # 1 megapixel
            'max': 100000000,    # 100 megapixels
            'default': 25000000, # 25 megapixels (5000x5000)
            'label': 'Max Pixels',
            'description': 'Maximum pixels before segmenting',
            'required': False,
        },
        'overlap': {
            'type': 'integer',
            'min': 0,
            'max': 50,
            'default': 10,
            'label': 'Overlap (%)',
            'description': 'Percentage overlap between segments',
            'required': False,
        },
    }
```

---

## IMPLEMENTATION STEPS

### Step 1: Read Current ToolRegistry
1. Read `tool_registry.py` completely
2. Understand existing schema methods
3. Find where to add new schemas

### Step 2: Add Schema Methods
For each of the 5 tools:
1. Create `_create_{tool}_schema()` method
2. Use exact parameter names from TOOL_REFERENCE.md
3. Follow existing code style
4. Add docstrings

### Step 3: Register Schemas
Update `__init__` method:
```python
self.tools = {
    # ... existing 5 tools ...
    'transcribe_lmstudio': self._create_transcribe_lmstudio_schema(),
    'llm_process': self._create_llm_process_schema(),
    'prepare_images': self._create_prepare_images_schema(),
    'remove_background': self._create_remove_background_schema(),
    'segment': self._create_segment_schema(),
}
```

### Step 4: Verify Implementation
1. Check Python syntax valid
2. Verify all parameter names match tools
3. Ensure types appropriate for UI generation
4. Confirm defaults are reasonable

---

## QUALITY CHECKLIST

- [ ] 5 schema methods created
- [ ] All methods have docstrings
- [ ] Parameter names match TOOL_REFERENCE.md
- [ ] Types appropriate (enum/integer/float/string/boolean)
- [ ] Min/max values reasonable
- [ ] Default values sensible
- [ ] Labels user-friendly
- [ ] Descriptions helpful
- [ ] Required flags correct
- [ ] 5 entries added to self.tools
- [ ] Python syntax valid
- [ ] Code follows existing style

---

## VALIDATION CRITERIA

**Parameter Accuracy:**
- Cross-reference every parameter with TOOL_REFERENCE.md
- Verify parameter names exact match
- Check default values match tool expectations

**UI Usability:**
- Labels clear and concise
- Descriptions helpful for users
- Value ranges make sense
- Defaults are safe choices

**Code Quality:**
- Consistent formatting
- Clear docstrings
- Logical ordering
- No duplicates

---

## OUTPUT DELIVERABLE

Create: `PHASE_B_IMPLEMENTATION_REPORT.md`

Include:
1. **Methods Created:** List of 5 schema methods
2. **Parameters Added:** Count per tool
3. **Verification Results:** All checks passed
4. **Integration Score:** New percentage (should be 50%)
5. **Testing Instructions:** How to test parameter UI

---

## IMPORTANT NOTES

- Use TOOL_REFERENCE.md as authoritative source for parameters
- Match existing schema method patterns exactly
- UI will auto-generate from schemas (dropdowns, sliders, inputs)
- Schemas don't execute tools, just define parameters
- Can be tested without running actual workflows

**When complete, report ready for Phase B Code Review.**
