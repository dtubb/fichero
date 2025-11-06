# SVG Conversion Tool - Implementation Plan

## Overview
Add a workflow step that converts images + transcriptions + metadata into semantic SVG files. This creates searchable, structured vector documents that preserve both visual and textual information with rich metadata.

## Goals
1. **Semantic**: SVG contains structured metadata and text layers
2. **Searchable**: Text is embedded and searchable within SVG
3. **Visual Fidelity**: Preserves image while adding text overlay
4. **Rich Metadata**: Incorporates library metadata and visual descriptions
5. **AI-Enhanced**: Uses LLM to structure and optimize SVG layout
6. **Standards-Based**: Creates valid SVG 1.1/2.0 documents

---

## Component 1: SVG Conversion Tool

### File: `src/fichero/tools/convert_to_svg.py`

**Purpose**: Convert document images + transcriptions into semantic SVG files with embedded metadata

**Function Signature**:
```python
def convert_to_svg_batch(
    source_folder: Path,
    source_manifest: Path,
    transcription_folder: Path,
    transcription_manifest: Path,
    output_folder: Path,
    metadata_manifest: Optional[Path] = None,
    visual_descriptions_manifest: Optional[Path] = None,
    model: str = "gpt-4o",
    layout_mode: str = "overlay",  # "overlay" or "sidebyside"
    skip_processing: bool = False,
    **kwargs
) -> Dict[str, int]:
```

**Process**:
1. Read source manifest for images
2. Read transcription manifest for text
3. Load metadata manifest (optional)
4. Load visual descriptions manifest (optional)
5. For each document:
   - Load image
   - Load transcription text
   - Gather metadata and visual description
   - Send to LLM to generate SVG structure
   - Create SVG file with embedded image and text
6. Create output manifest
7. Return statistics

**Input Manifests**:
- Images: `assets/enhanced/enhance_manifest.jsonl`
- Transcriptions: `assets/cleaned/cleaned_manifest.jsonl`
- Metadata: `assets/library_metadata/metadata_manifest.jsonl` (optional)
- Visual Descriptions: `assets/visual_descriptions/descriptions_manifest.jsonl` (optional)

**Output Manifest** (`assets/svg/svg_manifest.jsonl`):
```json
{
  "source": "documents/file1.jpg",
  "svg_file": "svg/file1.svg",
  "metadata": {
    "has_text_layer": true,
    "has_metadata": true,
    "has_visual_description": true,
    "svg_size": "2000x3000",
    "text_regions": 5,
    "embedded_fonts": ["serif"],
    "created_at": "2025-01-15T10:30:00"
  }
}
```

**SVG Output Structure**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="2000" height="3000"
     viewBox="0 0 2000 3000">

  <!-- Metadata Section -->
  <metadata>
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
             xmlns:dc="http://purl.org/dc/elements/1.1/">
      <rdf:Description>
        <dc:title>Historical Correspondence - Smith to Jones</dc:title>
        <dc:description>Letter discussing land transaction</dc:description>
        <dc:date>1892-03-15</dc:date>
        <dc:creator>John Smith</dc:creator>
        <dc:subject>Legal, Land, Correspondence</dc:subject>
        <dc:type>Handwritten Letter</dc:type>
        <dc:format>image/svg+xml</dc:format>

        <!-- Custom metadata from library -->
        <custom:archiveReference xmlns:custom="http://fichero.app/ns">BOX-12-FOLDER-3</custom:archiveReference>
        <custom:collectionName xmlns:custom="http://fichero.app/ns">Smith Family Papers</custom:collectionName>
        <custom:paperCondition xmlns:custom="http://fichero.app/ns">Good, minor foxing</custom:paperCondition>
      </rdf:Description>
    </rdf:RDF>
  </metadata>

  <!-- Definitions -->
  <defs>
    <style type="text/css">
      .document-text {
        font-family: serif;
        font-size: 16px;
        fill: #333;
        opacity: 0.9;
      }
      .heading-text {
        font-family: serif;
        font-size: 20px;
        font-weight: bold;
        fill: #000;
      }
      .region-background {
        fill: white;
        opacity: 0.7;
      }
    </style>
  </defs>

  <!-- Background Image Layer -->
  <g id="image-layer">
    <image x="0" y="0" width="2000" height="3000"
           xlink:href="data:image/jpeg;base64,/9j/4AAQSkZJRg..."
           preserveAspectRatio="xMidYMid meet"/>
  </g>

  <!-- Text Overlay Layer -->
  <g id="text-layer">

    <!-- Letterhead Region -->
    <g id="region-letterhead" class="text-region">
      <rect x="200" y="100" width="1600" height="200" class="region-background"/>
      <text x="1000" y="180" text-anchor="middle" class="heading-text">
        John Smith, Esq.
      </text>
      <text x="1000" y="220" text-anchor="middle" class="document-text">
        123 Main Street, Boston, Massachusetts
      </text>
    </g>

    <!-- Date Region -->
    <g id="region-date" class="text-region">
      <rect x="200" y="350" width="1600" height="60" class="region-background"/>
      <text x="1000" y="390" text-anchor="middle" class="document-text">
        March 15, 1892
      </text>
    </g>

    <!-- Body Text Region -->
    <g id="region-body" class="text-region">
      <rect x="200" y="450" width="1600" height="1800" class="region-background"/>

      <!-- Paragraph 1 -->
      <text x="220" y="500" class="document-text">
        <tspan x="220" dy="0">Dear Mr. Jones,</tspan>
        <tspan x="220" dy="30"></tspan>
        <tspan x="220" dy="30">I write to confirm our discussion regarding the</tspan>
        <tspan x="220" dy="30">parcel of land located at the corner of Oak and</tspan>
        <tspan x="220" dy="30">Elm Streets. As agreed, the purchase price shall</tspan>
        <tspan x="220" dy="30">be $500, payable in gold coin...</tspan>
      </text>

      <!-- Additional paragraphs... -->
    </g>

    <!-- Signature Region -->
    <g id="region-signature" class="text-region">
      <rect x="200" y="2400" width="1600" height="200" class="region-background"/>
      <text x="1400" y="2500" class="document-text">
        Yours faithfully,
      </text>
      <text x="1400" y="2600" class="heading-text" style="font-style: italic;">
        John Smith
      </text>
    </g>

  </g>

  <!-- Interactive Elements (optional) -->
  <g id="interactive-layer">
    <!-- Clickable regions for navigation -->
    <rect x="200" y="100" width="1600" height="200" fill="transparent"
          class="clickable" data-region="letterhead"/>
  </g>

</svg>
```

**LLM Integration for SVG Generation**:

```python
def generate_svg_layout(
    image: Image.Image,
    transcription: str,
    metadata: Dict,
    visual_description: Dict,
    model: str = "gpt-4o"
) -> Dict:
    """Use LLM to analyze content and generate optimal SVG structure"""

    # Encode image for vision model
    base64_image = encode_image(image, max_size=2048)

    # Build context prompt
    prompt = build_svg_generation_prompt(
        transcription=transcription,
        metadata=metadata,
        visual_description=visual_description
    )

    # Call vision + text model
    client = OpenAI(api_key=get_openai_key())

    completion = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        temperature=0.1,
        response_format={"type": "json_object"}
    )

    # Parse layout structure
    layout = json.loads(completion.choices[0].message.content)
    return layout
```

**SVG Generation Prompt**:
```
You are analyzing a historical document to create a semantic SVG structure.

INPUTS:
1. DOCUMENT IMAGE: You can see the visual layout
2. TRANSCRIPTION: The extracted text content (provided below)
3. VISUAL DESCRIPTION: Physical characteristics (provided below)
4. METADATA: Archive metadata (provided below)

TASK:
Analyze the document and provide a JSON structure for creating a semantic SVG with text overlay.

Identify distinct text regions in the document (e.g., letterhead, date, body, signature, margin notes, etc.).
For each region, provide:
- region_id: unique identifier
- region_type: (letterhead/date/salutation/body/closing/signature/notes/other)
- bounds: {x, y, width, height} in relative coordinates (0-1 range)
- text_content: the text that belongs in this region
- text_alignment: (left/center/right/justify)
- font_style: (heading/body/emphasis/signature)
- line_spacing: suggested spacing between lines in pixels

Also provide:
- document_dimensions: {width, height} in pixels
- suggested_text_size: base font size for body text
- color_scheme: {text_color, background_opacity}

Return JSON in this exact format:

{
  "document_dimensions": {"width": 2000, "height": 3000},
  "suggested_text_size": 16,
  "color_scheme": {
    "text_color": "#333333",
    "background_opacity": 0.7
  },
  "regions": [
    {
      "region_id": "letterhead",
      "region_type": "letterhead",
      "bounds": {"x": 0.1, "y": 0.03, "width": 0.8, "height": 0.067},
      "text_content": "John Smith, Esq.\n123 Main Street, Boston",
      "text_alignment": "center",
      "font_style": "heading",
      "line_spacing": 30
    },
    {
      "region_id": "date",
      "region_type": "date",
      "bounds": {"x": 0.1, "y": 0.117, "width": 0.8, "height": 0.02},
      "text_content": "March 15, 1892",
      "text_alignment": "center",
      "font_style": "body",
      "line_spacing": 20
    },
    {
      "region_id": "body",
      "region_type": "body",
      "bounds": {"x": 0.1, "y": 0.15, "width": 0.8, "height": 0.6},
      "text_content": "[full body text here]",
      "text_alignment": "left",
      "font_style": "body",
      "line_spacing": 25
    }
  ],
  "metadata_for_svg": {
    "title": "extracted from metadata or transcription",
    "date": "from metadata or transcription",
    "creator": "from metadata or transcription",
    "subject": "from metadata",
    "description": "brief description"
  }
}

TRANSCRIPTION:
{transcription}

VISUAL DESCRIPTION:
{visual_description}

METADATA:
{metadata}

Return ONLY valid JSON. Say nothing else.
```

**SVG Builder**:
```python
def build_svg_document(
    image: Image.Image,
    layout: Dict,
    transcription: str,
    metadata: Dict
) -> str:
    """Build complete SVG document from layout structure"""

    width = layout['document_dimensions']['width']
    height = layout['document_dimensions']['height']

    # Encode image as base64 for embedding
    base64_image = encode_image_for_svg(image)

    # Start SVG
    svg_parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" ',
        f'     xmlns:xlink="http://www.w3.org/1999/xlink"',
        f'     width="{width}" height="{height}" ',
        f'     viewBox="0 0 {width} {height}">',
    ]

    # Add metadata section
    svg_parts.append(build_svg_metadata(layout.get('metadata_for_svg', {}), metadata))

    # Add CSS styles
    svg_parts.append(build_svg_styles(layout))

    # Add background image layer
    svg_parts.append(
        f'  <g id="image-layer">',
        f'    <image x="0" y="0" width="{width}" height="{height}" ',
        f'           xlink:href="data:image/jpeg;base64,{base64_image}" ',
        f'           preserveAspectRatio="xMidYMid meet"/>',
        f'  </g>'
    )

    # Add text overlay layer
    svg_parts.append('  <g id="text-layer">')

    for region in layout['regions']:
        svg_parts.append(build_svg_region(region, width, height, layout))

    svg_parts.append('  </g>')

    # Close SVG
    svg_parts.append('</svg>')

    return '\n'.join(svg_parts)


def build_svg_region(region: Dict, doc_width: int, doc_height: int, layout: Dict) -> str:
    """Build SVG for a single text region"""

    # Convert relative bounds to absolute pixels
    bounds = region['bounds']
    x = int(bounds['x'] * doc_width)
    y = int(bounds['y'] * doc_height)
    w = int(bounds['width'] * doc_width)
    h = int(bounds['height'] * doc_height)

    region_id = region['region_id']
    text_content = region['text_content']
    alignment = region['text_alignment']
    font_style = region['font_style']
    line_spacing = region['line_spacing']

    # Build region group
    svg = [
        f'    <g id="region-{region_id}" class="text-region">',
        f'      <rect x="{x}" y="{y}" width="{w}" height="{h}" class="region-background"/>'
    ]

    # Add text with proper line breaks
    lines = text_content.split('\n')

    text_x = x + 20  # left padding
    if alignment == 'center':
        text_x = x + w // 2
    elif alignment == 'right':
        text_x = x + w - 20

    text_anchor = 'start' if alignment == 'left' else alignment

    # Calculate starting y position
    text_y = y + 40  # top padding

    # Add text element
    svg.append(f'      <text x="{text_x}" y="{text_y}" text-anchor="{text_anchor}" class="{font_style}-text">')

    for i, line in enumerate(lines):
        dy = line_spacing if i > 0 else 0
        svg.append(f'        <tspan x="{text_x}" dy="{dy}">{escape_xml(line)}</tspan>')

    svg.append('      </text>')
    svg.append('    </g>')

    return '\n'.join(svg)


def build_svg_metadata(svg_metadata: Dict, library_metadata: Dict) -> str:
    """Build RDF metadata section"""

    metadata_parts = [
        '  <metadata>',
        '    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
        '             xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '             xmlns:custom="http://fichero.app/ns">',
        '      <rdf:Description>',
    ]

    # Add Dublin Core metadata
    if 'title' in svg_metadata:
        metadata_parts.append(f'        <dc:title>{escape_xml(svg_metadata["title"])}</dc:title>')
    if 'description' in svg_metadata:
        metadata_parts.append(f'        <dc:description>{escape_xml(svg_metadata["description"])}</dc:description>')
    if 'date' in svg_metadata:
        metadata_parts.append(f'        <dc:date>{escape_xml(svg_metadata["date"])}</dc:date>')
    if 'creator' in svg_metadata:
        metadata_parts.append(f'        <dc:creator>{escape_xml(svg_metadata["creator"])}</dc:creator>')
    if 'subject' in svg_metadata:
        metadata_parts.append(f'        <dc:subject>{escape_xml(svg_metadata["subject"])}</dc:subject>')

    # Add custom metadata from library
    if library_metadata:
        if 'metadata' in library_metadata:
            for key, value in library_metadata['metadata'].items():
                safe_key = key.replace('_', '-')
                metadata_parts.append(f'        <custom:{safe_key}>{escape_xml(str(value))}</custom:{safe_key}>')

    metadata_parts.extend([
        '      </rdf:Description>',
        '    </rdf:RDF>',
        '  </metadata>'
    ])

    return '\n'.join(metadata_parts)
```

**Batch Processing**:
```python
class SVGBatchProcessor(BatchProcessor):
    """Batch processor for SVG conversion"""

    def __init__(
        self,
        *args,
        transcription_folder=None,
        transcription_manifest=None,
        metadata_manifest=None,
        visual_descriptions_manifest=None,
        model="gpt-4o",
        layout_mode="overlay",
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.transcription_folder = Path(transcription_folder)
        self.model = model
        self.layout_mode = layout_mode

        # Load manifests
        self.transcription_map = self._load_manifest(transcription_manifest)
        self.metadata_map = self._load_manifest(metadata_manifest) if metadata_manifest else {}
        self.visual_desc_map = self._load_manifest(visual_descriptions_manifest) if visual_descriptions_manifest else {}

    def _process_file(self, file_path: Path, output_path: Path) -> Dict:
        """Process a single image to SVG"""

        # Skip if already processed
        if output_path.exists():
            return {"source": str(file_path), "skipped": True}

        try:
            # Load image
            image = Image.open(file_path).convert("RGB")

            # Get transcription
            rel_path = SegmentHandler.get_relative_path(file_path)
            transcription_entry = self.transcription_map.get(str(rel_path), {})

            # Load transcription file
            transcription_file = self.transcription_folder / transcription_entry.get('outputs', [''])[0]
            if transcription_file.exists():
                transcription = transcription_file.read_text(encoding='utf-8')
            else:
                transcription = ""

            # Get metadata and visual description
            metadata = self.metadata_map.get(str(rel_path), {}).get('library_metadata', {})
            visual_desc = self.visual_desc_map.get(str(rel_path), {}).get('visual_description', {})

            # Generate SVG layout with LLM
            layout = generate_svg_layout(
                image=image,
                transcription=transcription,
                metadata=metadata,
                visual_description=visual_desc,
                model=self.model
            )

            # Build SVG document
            svg_content = build_svg_document(
                image=image,
                layout=layout,
                transcription=transcription,
                metadata=metadata
            )

            # Save SVG file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(svg_content, encoding='utf-8')

            # Create manifest entry
            return {
                "source": str(rel_path),
                "svg_file": str(output_path.relative_to(self.output_folder)),
                "metadata": {
                    "has_text_layer": bool(transcription),
                    "has_metadata": bool(metadata),
                    "has_visual_description": bool(visual_desc),
                    "svg_size": f"{layout['document_dimensions']['width']}x{layout['document_dimensions']['height']}",
                    "text_regions": len(layout['regions']),
                    "created_at": datetime.now().isoformat()
                },
                "processed_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to convert {file_path} to SVG: {e}")
            return {
                "source": str(file_path),
                "error": str(e)
            }
```

---

## Component 2: Workflow Integration

### Update: `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml`

**Add new step** (after visual description or catalogue):

```yaml
  - name: convert_to_svg
    worker_type: "io"
    help: "Convert images + transcriptions to semantic SVG with metadata"
    function: "fichero.tools.convert_to_svg.convert_to_svg_batch"
    args:
      source_folder: "assets/enhanced"
      source_manifest: "assets/enhanced/enhance_manifest.jsonl"
      transcription_folder: "assets/cleaned"
      transcription_manifest: "assets/cleaned/cleaned_manifest.jsonl"
      output_folder: "assets/svg"
      metadata_manifest: "assets/library_metadata/metadata_manifest.jsonl"
      visual_descriptions_manifest: "assets/visual_descriptions/descriptions_manifest.jsonl"
      model: "gpt-4o"
      layout_mode: "overlay"
    outputs:
      - "assets/svg"
      - "assets/svg/svg_manifest.jsonl"
```

**Complete workflow with SVG**:
```yaml
workflows:
  Default:
    - build_documents_manifest
    - enhance
    - segment
    - transcribe_qwen_max_segmented
    - recombine_segments
    - fuzzy_clean
    - describe_images              # Visual description
    - extract_library_metadata     # Library metadata
    - convert_to_svg               # NEW - SVG conversion
    - catalogue_folder
    - convert_to_word_segmented
    - catalogue_to_word
```

---

## Component 3: SVG Viewer Integration (Optional)

### Web-based SVG Viewer:

```python
# src/fichero/tools/view_svg.py

def create_svg_viewer(svg_folder: Path, output_html: Path):
    """Create an HTML viewer for browsing SVG documents"""

    svg_files = list(svg_folder.glob("**/*.svg"))

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>SVG Document Viewer</title>
    <style>
        body {{ margin: 0; font-family: sans-serif; }}
        .container {{ display: flex; height: 100vh; }}
        .sidebar {{ width: 250px; background: #f5f5f5; overflow-y: auto; }}
        .viewer {{ flex: 1; padding: 20px; overflow-y: auto; }}
        .svg-item {{ padding: 10px; cursor: pointer; border-bottom: 1px solid #ddd; }}
        .svg-item:hover {{ background: #e0e0e0; }}
        .svg-item.active {{ background: #007bff; color: white; }}
        #svg-display {{ border: 1px solid #ccc; max-width: 100%; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar" id="sidebar"></div>
        <div class="viewer">
            <div id="metadata"></div>
            <div id="svg-display"></div>
        </div>
    </div>
    <script>
        const svgFiles = {json.dumps([str(f.relative_to(svg_folder)) for f in svg_files])};

        function loadSVG(path) {{
            fetch(path)
                .then(r => r.text())
                .then(svg => {{
                    document.getElementById('svg-display').innerHTML = svg;
                    extractMetadata(svg);
                }});
        }}

        function extractMetadata(svg) {{
            const parser = new DOMParser();
            const doc = parser.parseFromString(svg, 'image/svg+xml');
            const metadata = doc.querySelector('metadata');
            // Display metadata...
        }}

        // Populate sidebar
        svgFiles.forEach(file => {{
            const item = document.createElement('div');
            item.className = 'svg-item';
            item.textContent = file;
            item.onclick = () => loadSVG(file);
            document.getElementById('sidebar').appendChild(item);
        }});
    </script>
</body>
</html>
    """

    output_html.write_text(html)
```

---

## Testing Strategy

### Phase 1: Core SVG Generation
- Create convert_to_svg.py
- Test basic SVG structure
- Validate SVG syntax
- Test with sample images

### Phase 2: LLM Layout Generation
- Test layout analysis with different document types
- Optimize prompts for accuracy
- Test region detection
- Validate text positioning

### Phase 3: Metadata Integration
- Test with library metadata
- Test with visual descriptions
- Validate RDF metadata structure
- Test metadata extraction

### Phase 4: Workflow Integration
- Add to Generic_Catalogue workflow
- Test full pipeline
- Verify SVG output quality
- Compare with original documents

### Phase 5: Viewer and Export
- Create SVG viewer
- Test searchability
- Test SVG rendering in different applications
- Validate accessibility

---

## Benefits

✅ **Searchable**: Text is embedded and searchable
✅ **Semantic**: Structured with rich metadata
✅ **Scalable**: Vector format scales to any size
✅ **Accessible**: Text can be read by screen readers
✅ **Preserves Visual**: Original image embedded
✅ **Standards-Based**: Valid SVG 1.1/2.0
✅ **Web-Compatible**: Works in browsers
✅ **Archive-Ready**: Contains all document information

---

## Files to Create

**New Files**:
1. `src/fichero/tools/convert_to_svg.py` - Main SVG conversion tool
2. `src/fichero/tools/utils/svg_builder.py` - SVG building utilities
3. `src/fichero/tools/view_svg.py` - SVG viewer generator (optional)

**Modified Files**:
1. `src/fichero/resources/config_defaults/plans/Generic_Catalogue.yml` - Add SVG step

**Test Files**:
1. `tests/test_convert_to_svg.py` - SVG conversion tests
2. `tests/test_svg_validation.py` - SVG syntax validation tests

---

## API Requirements

**Required**:
- OpenAI API key (for GPT-4 Vision/GPT-4o)
- OR Qwen API key (for Qwen-VL-Max)

**Models**:
- **GPT-4o** (Recommended): Best quality for layout analysis
- **GPT-4 Vision**: Good quality, slightly older
- **Qwen-VL-Max**: Alternative, may need prompt tuning

---

## Estimated Costs

**GPT-4o**:
- ~$0.01-0.02 per image (vision + layout generation)
- 1000 images = ~$10-20

**GPT-4 Vision**:
- ~$0.02-0.04 per image
- 1000 images = ~$20-40

---

## SVG Applications

**Use Cases**:
1. **Web Publishing**: Display documents in browsers
2. **Digital Archives**: Searchable document collections
3. **Accessibility**: Screen reader compatible
4. **Print**: High-quality vector output
5. **Analysis**: Machine-readable structured documents
6. **Annotation**: Easy to add highlights and notes

---

## Layout Modes

### Overlay Mode (Default):
- Text overlaid on image
- Semi-transparent backgrounds
- Preserves original appearance

### Side-by-Side Mode:
- Image on left, text on right
- Similar to Word output
- Better for readability

### Text-Only Mode:
- Extract text to separate SVG
- No image background
- Smaller file size

---

## Advanced Features (Future)

- **Interactive SVG**: Clickable regions, tooltips
- **Multi-page SVG**: Combine pages into single file
- **SVG Animation**: Highlighting, transitions
- **OCR Correction**: Visual editing of text regions
- **Export Options**: PDF, PNG, HTML from SVG

---

## Next Steps

1. **Create convert_to_svg.py tool**
2. **Test SVG generation with sample documents**
3. **Optimize layout detection prompt**
4. **Add to workflow configuration**
5. **Create SVG viewer**
6. **Test end-to-end pipeline**
