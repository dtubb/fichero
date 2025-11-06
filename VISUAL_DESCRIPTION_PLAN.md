# Visual Description Tool - Implementation Plan

## Overview
Add a workflow step that generates detailed visual descriptions of images using vision AI models. This provides rich descriptive metadata that complements text transcription.

## Goals
1. **AI-Powered**: Use vision models to analyze image content
2. **Detailed**: Generate comprehensive visual descriptions including layout, colors, condition
3. **Workflow Integration**: Seamlessly integrates into existing pipelines
4. **Flexible**: Works with any image type (documents, photographs, artifacts)
5. **Reusable**: Any workflow can use visual description

---

## Component 1: Visual Description Tool

### File: `src/fichero/tools/describe_images.py`

**Purpose**: Analyze images with vision AI and generate detailed visual descriptions

**Function Signature**:
```python
def describe_images_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    description_prompt: Optional[str] = None,
    model: str = "qwen-vl-max",
    skip_processing: bool = False,
    **kwargs
) -> Dict[str, int]:
```

**Process**:
1. Read source manifest (e.g., `enhanced/enhance_manifest.jsonl`)
2. For each image in manifest:
   - Load image file
   - Encode image for vision API
   - Send to vision model with description prompt
   - Parse and structure response
3. Create output manifest with visual descriptions
4. Return statistics

**Input Manifest** (`assets/enhanced/enhance_manifest.jsonl`):
```json
{"source": "documents/file1.jpg", "output": "enhanced/file1.jpg"}
{"source": "documents/file2.jpg", "output": "enhanced/file2.jpg"}
```

**Output Manifest** (`assets/visual_descriptions/descriptions_manifest.jsonl`):
```json
{
  "source": "documents/file1.jpg",
  "visual_description": {
    "layout": "Single page document with handwritten text in portrait orientation",
    "content_type": "Handwritten correspondence on aged paper",
    "text_regions": [
      {
        "location": "top-center",
        "description": "Letterhead or address block",
        "characteristics": "Formal script writing"
      },
      {
        "location": "main-body",
        "description": "Body text in cursive handwriting",
        "characteristics": "Dense paragraphs, consistent hand"
      },
      {
        "location": "bottom-right",
        "description": "Signature block",
        "characteristics": "Flourished signature"
      }
    ],
    "visual_elements": {
      "colors": ["sepia", "cream", "dark brown ink"],
      "paper_condition": "yellowed with age, some edge wear",
      "writing_medium": "dark ink, possibly fountain pen",
      "distinctive_features": ["watermark visible", "fold marks horizontal center"]
    },
    "image_quality": {
      "resolution": "high",
      "clarity": "good, some blur in margins",
      "lighting": "even, minimal shadows",
      "completeness": "full document visible, slight crop on left edge"
    },
    "estimated_era": "late 19th/early 20th century based on paper and writing style",
    "preservation_notes": "foxing spots in upper right corner, minor tears along top edge",
    "raw_description": "A sepia-toned historical document showing handwritten text..."
  }
}
```

**Vision API Integration**:
```python
def analyze_image_visual(image_path: Path, prompt: str, model: str, api_key: str) -> Dict:
    """Use vision model to analyze image and generate description"""

    # Load and encode image
    image = Image.open(image_path).convert("RGB")
    base64_image = encode_image(image, max_size=2048)

    # Configure client based on model
    if model.startswith("qwen"):
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        model_name = "qwen-vl-max"
    elif model.startswith("gpt-4"):
        client = OpenAI(api_key=api_key)
        model_name = "gpt-4-vision-preview"

    # Call vision API
    completion = client.chat.completions.create(
        model=model_name,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        temperature=0.3,
        response_format={"type": "json_object"}
    )

    # Parse JSON response
    description = json.loads(completion.choices[0].message.content)
    return description
```

**Default Description Prompt**:
```
Analyze this historical document image in detail. Provide a comprehensive visual description as JSON.

Include:
1. LAYOUT: Overall page structure, orientation, number of text regions
2. CONTENT_TYPE: Type of document (letter, legal, photograph, etc.)
3. TEXT_REGIONS: Array of distinct text areas with:
   - location (top/center/bottom, left/center/right)
   - description (what this region contains)
   - characteristics (handwriting style, font type, formatting)

4. VISUAL_ELEMENTS:
   - colors: Array of prominent colors (paper, ink, highlights)
   - paper_condition: Physical state of the paper/material
   - writing_medium: Type of writing tool used (ink, pencil, typewriter, etc.)
   - distinctive_features: Array of notable visual features (stamps, seals, watermarks, decorations, etc.)

5. IMAGE_QUALITY:
   - resolution: high/medium/low
   - clarity: description of focus and readability
   - lighting: description of lighting conditions
   - completeness: is full document visible or cropped

6. ESTIMATED_ERA: Time period estimate based on visual characteristics
7. PRESERVATION_NOTES: Any damage, wear, stains, repairs visible
8. RAW_DESCRIPTION: A flowing 2-3 sentence description of what you see

Return ONLY valid JSON matching this structure. Be specific and detailed.
```

**Batch Processing**:
```python
class VisualDescriptionProcessor(BatchProcessor):
    """Batch processor for visual descriptions"""

    def __init__(self, *args, api_key=None, model="qwen-vl-max", prompt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = api_key
        self.model = model
        self.prompt = prompt or self._get_default_prompt()

    def _process_file(self, file_path: Path, output_path: Path) -> Dict:
        """Process a single image file"""

        # Skip if already processed
        if output_path.exists():
            return {"source": str(file_path), "skipped": True}

        try:
            # Analyze image with vision model
            description = analyze_image_visual(
                file_path,
                self.prompt,
                self.model,
                self.api_key
            )

            # Save description as JSON
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(description, f, indent=2, ensure_ascii=False)

            # Create manifest entry
            rel_path = SegmentHandler.get_relative_path(file_path)
            return {
                "source": str(rel_path),
                "outputs": [str(rel_path.with_suffix('.json'))],
                "visual_description": description,
                "processed_at": datetime.now().isoformat(),
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Failed to describe {file_path}: {e}")
            return {
                "source": str(file_path),
                "error": str(e)
            }
```

**Error Handling**:
- API key validation before processing
- Retry logic for transient API errors
- Graceful degradation for vision model failures
- Save partial results if batch interrupted

**Skip Processing Mode**:
- Create empty JSON files with stub data
- Fast testing without API calls

---

## Component 2: Workflow Integration

### Update: `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml`

**Add new step** (after enhance, before or after segment):

```yaml
  - name: describe_images
    worker_type: "io"
    help: "Generate detailed visual descriptions of images using AI"
    function: "fichero.tools.describe_images.describe_images_batch"
    args:
      source_folder: "assets/enhanced"
      source_manifest: "assets/enhanced/enhance_manifest.jsonl"
      output_folder: "assets/visual_descriptions"
      model: "qwen-vl-max"
    outputs:
      - "assets/visual_descriptions"
      - "assets/visual_descriptions/descriptions_manifest.jsonl"
```

**Updated workflow order** (two options):

**Option A: Before segmentation** (describe full images):
```yaml
workflows:
  Default:
    - build_documents_manifest
    - enhance
    - describe_images              # NEW - analyze full enhanced images
    - segment
    - transcribe_qwen_max_segmented
    - recombine_segments
    - fuzzy_clean
    - extract_library_metadata
    - catalogue_folder
    - convert_to_word_segmented
    - catalogue_to_word
```

**Option B: After recombine** (describe along with transcription):
```yaml
workflows:
  Default:
    - build_documents_manifest
    - enhance
    - segment
    - transcribe_qwen_max_segmented
    - recombine_segments
    - fuzzy_clean
    - describe_images              # NEW - analyze with transcription available
    - extract_library_metadata
    - catalogue_folder
    - convert_to_word_segmented
    - catalogue_to_word
```

---

## Component 3: Integration with Cataloguing

### Update: `src/fichero/tools/llm_process.py`

**Add visual description manifest support**:

```python
def process_documents_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    prompt_config: str,
    folder_mode: bool = False,
    metadata_manifest: Optional[Path] = None,
    visual_descriptions_manifest: Optional[Path] = None,  # NEW
    ...
):
    """
    Process documents with LLM prompts

    New parameter:
        visual_descriptions_manifest: Optional JSONL file with visual descriptions per file
    """

    # Load visual descriptions if provided
    visual_desc_map = {}
    if visual_descriptions_manifest and visual_descriptions_manifest.exists():
        visual_desc_map = load_visual_descriptions_manifest(visual_descriptions_manifest)

    # When processing each document:
    for entry in manifest_entries:
        source_file = entry['source']

        # Get visual description for this file
        visual_desc = visual_desc_map.get(source_file, {})

        # Add to prompt context
        context = build_prompt_context(
            text=transcription,
            metadata=file_metadata,
            visual_description=visual_desc,
            page_numbers=page_numbers
        )
```

**Helper function**:
```python
def load_visual_descriptions_manifest(manifest_path: Path) -> Dict[str, Dict]:
    """Load visual descriptions manifest into lookup dict"""
    visual_map = {}
    with open(manifest_path, 'r') as f:
        for line in f:
            entry = json.loads(line)
            source = entry.get('source')
            description = entry.get('visual_description', {})
            visual_map[source] = description
    return visual_map
```

**Updated prompt context builder**:
```python
def build_prompt_context(
    text: str,
    metadata: Dict = None,
    visual_description: Dict = None,
    page_numbers: bool = True
) -> str:
    """Build context string with optional metadata and visual description"""

    context_parts = []

    # Add visual description section if present
    if visual_description:
        context_parts.append("=== VISUAL DESCRIPTION ===")

        if 'layout' in visual_description:
            context_parts.append(f"Layout: {visual_description['layout']}")

        if 'content_type' in visual_description:
            context_parts.append(f"Content Type: {visual_description['content_type']}")

        if 'visual_elements' in visual_description:
            elements = visual_description['visual_elements']
            if 'colors' in elements:
                context_parts.append(f"Colors: {', '.join(elements['colors'])}")
            if 'paper_condition' in elements:
                context_parts.append(f"Paper Condition: {elements['paper_condition']}")
            if 'distinctive_features' in elements:
                context_parts.append(f"Distinctive Features: {', '.join(elements['distinctive_features'])}")

        if 'estimated_era' in visual_description:
            context_parts.append(f"Estimated Era: {visual_description['estimated_era']}")

        if 'raw_description' in visual_description:
            context_parts.append(f"\nVisual Summary: {visual_description['raw_description']}")

        context_parts.append("")

    # Add metadata section if present
    if metadata:
        context_parts.append("=== SOURCE FILE METADATA ===")
        # ... existing metadata code ...
        context_parts.append("")

    context_parts.append("=== DOCUMENT TRANSCRIPTION ===")
    context_parts.append(text)

    return "\n".join(context_parts)
```

---

## Component 4: Catalogue Prompt Updates

### Update: `src/fichero/resources/config_defaults/prompts/Generic_Catalogue.jsonl`

**Modify library_catalogue_entry prompt to use visual descriptions**:

```json
{
  "name": "library_catalogue_entry",
  "prompt": "Using all the extracted information from previous steps, create a structured library catalogue entry.

If VISUAL DESCRIPTION is provided at the beginning, use it to supplement the catalogue with:
- Document type identification (handwritten, typed, printed, photograph, etc.)
- Physical condition and preservation state
- Visual characteristics (paper color, ink type, writing style)
- Estimated time period from visual cues
- Distinctive visual features (seals, stamps, watermarks, decorations)

If SOURCE FILE METADATA is provided, use it for:
- Archive references and original filenames
- Known dates and provenance
- Existing tags and classifications

Focus on documenting WHAT IS IN THE DOCUMENTS, not analysis or interpretation.

The catalogue entry must include:
- Title (brief descriptive title based on document content)
- Description (use the summary from previous step - what the documents contain)
- Subject Keywords (use the tags from previous step, supplement with visual characteristics)
- People (list of people mentioned in the documents)
- Places (list of locations mentioned in the documents)
- Organizations (list of organizations mentioned in the documents)
- Date Coverage (date range covered by the documents' content, in YYYY-MM-DD format)
- Document Type (e.g., correspondence, legal documents, reports, photographs - use visual description if available)
- Physical Description (from visual analysis if available)
- Condition Notes (preservation state from visual description if available)
- Source Information (archive reference, original filename, etc. from metadata if available)

Return as JSON exactly in this format:

{
  \"catalogue_entry\": {
    \"title\": \"brief descriptive title of document content\",
    \"description\": \"what the documents contain\",
    \"subject_keywords\": \"keyword1; keyword2; keyword3; ...\",
    \"people\": [\"person1\", \"person2\", \"person3\"],
    \"places\": [\"place1\", \"place2\", \"place3\"],
    \"organizations\": [\"org1\", \"org2\", \"org3\"],
    \"date_coverage\": {
      \"start\": \"YYYY-MM-DD or YYYY or null\",
      \"end\": \"YYYY-MM-DD or YYYY or null\"
    },
    \"document_type\": \"type of documents (from visual analysis if available)\",
    \"physical_description\": {
      \"format\": \"from visual description\",
      \"medium\": \"from visual description\",
      \"colors\": \"from visual description\",
      \"distinctive_features\": \"from visual description\"
    },
    \"condition_notes\": \"from visual description if available\",
    \"source_info\": {
      \"archive_reference\": \"from metadata if available\",
      \"original_filename\": \"from metadata if available\",
      \"notes\": \"from metadata if available\"
    }
  }
}

Return ONLY valid JSON. Say nothing else.",
  ...
}
```

---

## Component 5: Alternative Models

### Support Multiple Vision Models:

**Qwen VL Max** (Default):
- Excellent for multilingual documents
- Fast processing
- Cost-effective
- Good at detailed descriptions

**GPT-4 Vision**:
- High quality descriptions
- Better at nuanced visual analysis
- More expensive
- Requires OpenAI API key

**Configuration**:
```yaml
  - name: describe_images
    args:
      model: "qwen-vl-max"    # or "gpt-4-vision"
      description_prompt: "custom_prompt.txt"  # Optional custom prompt
```

---

## Testing Strategy

### Phase 1: Create Visual Description Tool
- Create `describe_images.py`
- Add unit tests
- Test with sample images
- Validate JSON output structure

### Phase 2: Test Vision Models
- Test with Qwen VL Max
- Test with GPT-4 Vision
- Compare output quality
- Optimize prompts

### Phase 3: Integrate with Workflow
- Add step to Generic_Catalogue.yml
- Test full workflow
- Verify descriptions are generated

### Phase 4: Integrate with Cataloguing
- Update llm_process.py
- Add visual description to context
- Test catalogue quality improvement

### Phase 5: End-to-End Testing
- Test full workflow from GUI
- Verify visual descriptions enhance catalogue
- Compare with/without visual descriptions

---

## Benefits

✅ **Rich Metadata**: Captures visual information beyond transcription
✅ **Flexible**: Works with any image type
✅ **AI-Powered**: Uses latest vision models
✅ **Reusable**: Can be used in any workflow
✅ **Backwards Compatible**: Workflows work without it
✅ **Multi-Model**: Supports different vision APIs

---

## Files to Modify

**New Files**:
1. `src/fichero/tools/describe_images.py` - New tool
2. `src/fichero/tools/utils/vision_api.py` - Shared vision API utilities (optional)

**Modified Files**:
1. `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml` - Add step
2. `src/fichero/tools/llm_process.py` - Add visual description support
3. `src/fichero/resources/config_defaults/prompts/Generic_Catalogue.jsonl` - Update prompts

**Test Files**:
1. `tests/test_describe_images.py` - New tests
2. `tests/test_llm_process_with_visuals.py` - Updated tests

---

## API Keys Required

- **Qwen VL Max**: DASHSCOPE_API_KEY (same as transcription)
- **GPT-4 Vision**: OPENAI_API_KEY (if using GPT-4 Vision)

---

## Estimated Costs

**Qwen VL Max**:
- ~$0.002 per image (very cost effective)
- 1000 images = ~$2

**GPT-4 Vision**:
- ~$0.01-0.02 per image (higher quality)
- 1000 images = ~$10-20

---

## Next Steps

1. **Create describe_images.py tool**
2. **Test with sample images**
3. **Add to workflow configuration**
4. **Update cataloguing prompts**
5. **Test end-to-end with real data**
