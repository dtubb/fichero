# PHASE 1: TOOL INVENTORY AUDIT - AGENT INSTRUCTIONS

**Phase:** 1 of 7
**Agent Type:** general-purpose
**Estimated Duration:** 30 minutes
**Prerequisites:** Read `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md`

---

## OBJECTIVE

Create a definitive reference document (`TOOL_REFERENCE.md`) with complete parameter documentation for all 20 Fichero processing tools.

---

## INPUT FILES

**Required Reading:**
1. `TOOL_INTEGRATION_ARCHITECTURE_REPORT.md` - Overview of all 20 tools
2. `src/fichero/tools/*.py` - All 20 tool implementation files

---

## TASK BREAKDOWN

### Task 1: Read All Tool Files

For each of the 20 tools in `src/fichero/tools/`, read the Python file and extract:

1. **Function signature** - Find the `*_batch()` function
   - Example: `crop_batch(source_folder, output_folder, ...)`

2. **All parameters** - Document each parameter:
   - Name
   - Type (str, int, float, bool, Path, etc.)
   - Default value (if any)
   - Description (from docstring or comments)

3. **Input requirements** - What files/data does tool expect?
   - Image formats accepted
   - Manifest file requirements
   - Folder structure expectations

4. **Output format** - What does tool produce?
   - Output files (images, text, documents)
   - JSONL manifest structure
   - Folder organization

### Task 2: Document JSONL Manifest Format

For each tool, extract the JSONL manifest entry structure:

```python
# Example from crop.py
manifest_entry = {
    "file_id": "...",
    "source_file": "...",
    "output_file": "...",
    "parameters": {...},
    "metadata": {...}
}
```

Document the exact fields each tool writes to its manifest.

### Task 3: Verify Function Naming Convention

Check if all tools follow naming convention:
- Expected: `{tool_name}_batch()`
- Document any exceptions (e.g., `llm_process.py` uses `process_documents_batch()`)

### Task 4: Extract Parameter Schemas

For tools that have parameter validation/schemas in code, extract:
- Valid values for enum parameters
- Min/max ranges for numeric parameters
- Required vs optional parameters
- Parameter interdependencies

---

## OUTPUT FORMAT

Create `TOOL_REFERENCE.md` with this structure:

```markdown
# FICHERO TOOL REFERENCE

**Generated:** 2025-11-15
**Purpose:** Definitive parameter documentation for all 20 tools
**Phase:** 1 of 7

---

## TOOL CATEGORIES

### Image Processing Tools (9)

#### 1. crop.py

**Purpose:** Crop document borders using YOLO/contour detection

**Function:** `crop_batch(source_folder, output_folder, source_manifest=None, ...)`

**Parameters:**

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| source_folder | Path/str | - | Yes | Folder containing source images |
| output_folder | Path/str | - | Yes | Folder for cropped outputs |
| source_manifest | Path/str | None | No | JSONL manifest of source files |
| contour_template | str | "auto" | No | Contour detection mode (auto/white_bg/dark_bg) |
| contour_padding | int | 30 | No | Padding pixels around detected border |
| model_path | Path/str | None | No | Path to YOLO model weights |
| output_format | str | "jpg" | No | Output image format (jpg/png) |

**Input Requirements:**
- Images: JPG, PNG, TIFF
- Optional: Source manifest JSONL
- Models: YOLO weights (if using YOLO mode)

**Output Format:**
- Cropped images in `output_folder/`
- Manifest: `output_folder/crop_manifest.jsonl`

**JSONL Manifest Entry:**
```json
{
  "file_id": "document_001",
  "source_file": "input/page001.jpg",
  "output_file": "cropped/page001.jpg",
  "crop_method": "contour",
  "crop_box": [x, y, w, h],
  "original_size": [width, height],
  "cropped_size": [width, height]
}
```

**Notes:**
- Supports both contour detection and YOLO-based cropping
- Auto mode selects best method based on image characteristics
- Padding prevents cutting off document edges

---

(Repeat for all 20 tools)

```

---

## QUALITY CHECKLIST

Before completing, verify:

- [x] All 20 tools documented
- [x] Function signatures accurate
- [x] All parameters documented with types
- [x] Default values specified
- [x] Input/output formats clear
- [x] JSONL manifest structures documented
- [x] Naming convention exceptions noted
- [x] Parameter schemas extracted (where available)

---

## COMPLETION CRITERIA

**Output file created:** `TOOL_REFERENCE.md`

**File contents:**
- Complete parameter documentation for all 20 tools
- JSONL manifest structures
- Input/output format specifications
- Parameter validation rules (where applicable)

**Status update:** Add status section to `TOOL_INTEGRATION_MASTER_PLAN.md`:
```markdown
## PHASE 1 STATUS

- [x] Phase 1: Tool inventory complete
- Output: TOOL_REFERENCE.md (20 tools documented)
- Issues: [List any naming inconsistencies or missing docs]
- Next: Phase 2 (Renderer audit)
```

---

## IMPORTANT NOTES

- **READ-ONLY:** Do not modify tool files, only read and document
- **Accuracy:** Parameter types and defaults must be exact from source code
- **Completeness:** Every parameter must be documented, even internal ones
- **Consistency:** Use same table format for all tools

---

**When complete, report:** "Phase 1 complete. TOOL_REFERENCE.md created with documentation for all 20 tools. Ready for Phase 2."
