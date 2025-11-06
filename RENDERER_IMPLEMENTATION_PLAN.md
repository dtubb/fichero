# Renderer Implementation Plan

## Overview

Systematic implementation of renderers for all Fichero processing tools, with individual test plans and custom UI affordances per tool.

## Phase 1: Core Image Processing Tools (Priority 1)

These are the most commonly used tools in typical workflows.

### 1. CropRenderer ✅ DONE
- **File**: `tool_renderers/crop_renderer.py`
- **Status**: Implemented
- **Editable Parameters**: crop_box (x, y, width, height), padding, method, template
- **Toolbar Actions**: Edit Parameters, Re-crop, Reset
- **Test Plan**: See `test_renderer.py`

### 2. RotateRenderer ✅ DONE
- **File**: `tool_renderers/rotate_renderer.py`
- **Status**: Implemented
- **Editable Parameters**: rotation_angle, direction
- **Toolbar Actions**: Edit Parameters, Rotate Left, Rotate Right, Reset
- **Test Plan**: See `test_renderer.py`

### 3. EnhanceRenderer ✅ DONE
- **File**: `tool_renderers/enhance_renderer.py`
- **Status**: Implemented
- **Editable Parameters**: contrast, brightness, sharpness, method
- **Toolbar Actions**: Edit Parameters, Re-enhance, Compare Before/After, Reset
- **Test Plan**: TODO

### 4. RemoveBackgroundRenderer
- **File**: `tool_renderers/remove_background_renderer.py`
- **Status**: TODO
- **Editable Parameters**: method, threshold, edge_smoothing
- **Toolbar Actions**: Edit Parameters, Re-process, Toggle Background Preview, Reset
- **Test Plan**: TODO

### 5. PrepareImagesRenderer
- **File**: `tool_renderers/prepare_images_renderer.py`
- **Status**: TODO
- **Editable Parameters**: resize_mode, target_size, quality, format
- **Toolbar Actions**: Edit Parameters, Re-prepare, Batch Settings, Reset
- **Test Plan**: TODO

## Phase 2: Advanced Image Processing (Priority 2)

### 6. SplitRenderer
- **File**: `tool_renderers/split_renderer.py`
- **Status**: TODO
- **Output Type**: Folder with multiple images
- **Editable Parameters**: split_method, split_points, overlap
- **Toolbar Actions**: Edit Split Points, Re-split, Preview All, Merge Back
- **Test Plan**: TODO

### 7. SegmentRenderer
- **File**: `tool_renderers/segment_renderer.py`
- **Status**: TODO
- **Output Type**: Folder with segments
- **Editable Parameters**: segment_method, min_area, padding
- **Toolbar Actions**: Edit Parameters, Re-segment, Preview All, Export Segments
- **Test Plan**: TODO

### 8. RecombineRenderer
- **File**: `tool_renderers/recombine_renderer.py`
- **Status**: TODO
- **Output Type**: Single recombined image
- **Editable Parameters**: layout, spacing, background_color
- **Toolbar Actions**: Edit Layout, Re-combine, Preview, Reset
- **Test Plan**: TODO

## Phase 3: AI/Text Processing Tools (Priority 3)

### 9. TranscribeRenderer (Qwen Max & LM Studio)
- **File**: `tool_renderers/transcribe_renderer.py`
- **Status**: TODO
- **Output Type**: Text/JSON
- **Editable Parameters**: model, prompt_template, max_tokens, temperature
- **Toolbar Actions**: Edit Prompt, Re-transcribe, Copy Text, Export JSON
- **Display**: Side-by-side image and transcription
- **Test Plan**: TODO

### 10. DescribeRenderer
- **File**: `tool_renderers/describe_renderer.py`
- **Status**: TODO
- **Output Type**: Text/JSON description
- **Editable Parameters**: model, description_type, detail_level
- **Toolbar Actions**: Edit Parameters, Re-describe, Copy Description, Export
- **Display**: Image with description overlay
- **Test Plan**: TODO

### 11. LLMProcessRenderer
- **File**: `tool_renderers/llm_process_renderer.py`
- **Status**: TODO
- **Output Type**: Text/JSON
- **Editable Parameters**: model, prompt, system_message, temperature
- **Toolbar Actions**: Edit Prompt, Re-process, Copy Output, View Raw
- **Test Plan**: TODO

## Phase 4: Document Generation Tools (Priority 4)

### 12. ConvertToWordRenderer
- **File**: `tool_renderers/convert_to_word_renderer.py`
- **Status**: TODO
- **Output Type**: .docx file
- **Editable Parameters**: template, layout, include_images, font_settings
- **Toolbar Actions**: Edit Template, Re-generate, Preview, Open Document
- **Display**: Document preview or download link
- **Test Plan**: TODO

### 13. ConvertToSVGRenderer
- **File**: `tool_renderers/convert_to_svg_renderer.py`
- **Status**: TODO
- **Output Type**: .svg file
- **Editable Parameters**: conversion_method, vector_quality, colors
- **Toolbar Actions**: Edit Parameters, Re-convert, Preview SVG, Download
- **Display**: SVG preview with zoom
- **Test Plan**: TODO

### 14. JsonToWordRenderer
- **File**: `tool_renderers/json_to_word_renderer.py`
- **Status**: TODO
- **Output Type**: .docx file
- **Editable Parameters**: template, data_mapping, formatting
- **Toolbar Actions**: Edit Template, Edit Mapping, Re-generate, Open Document
- **Test Plan**: TODO

### 15. JsonToExcelRenderer
- **File**: `tool_renderers/json_to_excel_renderer.py`
- **Status**: TODO
- **Output Type**: .xlsx file
- **Editable Parameters**: sheet_name, column_mapping, formatting
- **Toolbar Actions**: Edit Mapping, Re-generate, Open Spreadsheet
- **Test Plan**: TODO

## Phase 5: Metadata/Analysis Tools (Priority 5)

### 16. AnalyzeGroupsRenderer
- **File**: `tool_renderers/analyze_groups_renderer.py`
- **Status**: TODO
- **Output Type**: JSON analysis
- **Editable Parameters**: grouping_criteria, analysis_depth
- **Toolbar Actions**: Edit Criteria, Re-analyze, Export Results, Visualize
- **Display**: Analysis summary with statistics
- **Test Plan**: TODO

### 17. ExtractMetadataRenderer
- **File**: `tool_renderers/extract_metadata_renderer.py`
- **Status**: TODO
- **Output Type**: JSON metadata
- **Editable Parameters**: metadata_fields, extraction_method
- **Toolbar Actions**: Edit Fields, Re-extract, Export JSON, Copy
- **Display**: Metadata table view
- **Test Plan**: TODO

### 18. BuildManifestRenderer
- **File**: `tool_renderers/build_manifest_renderer.py`
- **Status**: TODO
- **Output Type**: JSONL manifest
- **Editable Parameters**: manifest_format, include_fields
- **Toolbar Actions**: Edit Format, Rebuild, Export, Validate
- **Display**: Manifest viewer with search
- **Test Plan**: TODO

### 19. FuzzyCleanRenderer
- **File**: `tool_renderers/fuzzy_clean_renderer.py`
- **Status**: TODO
- **Output Type**: Cleaned text/JSON
- **Editable Parameters**: fuzzy_threshold, clean_rules
- **Toolbar Actions**: Edit Rules, Re-clean, Preview Changes, Export
- **Display**: Before/after comparison
- **Test Plan**: TODO

## Renderer Architecture Enhancements

### Context-Aware Toolbar System

Each renderer can define its own toolbar buttons/actions:

```python
class BaseRenderer:
    def get_toolbar_actions(self, context: RenderContext) -> List[ToolbarAction]:
        """
        Get toolbar actions for this renderer.

        Returns:
            List of ToolbarAction objects
        """
        return [
            ToolbarAction(
                id='edit_params',
                label='Edit Parameters',
                icon='edit',
                handler='_on_edit_params',
                enabled=True
            ),
            # ... more actions
        ]
```

### Menu Item System

Each renderer can also define custom menu items:

```python
class BaseRenderer:
    def get_menu_items(self, context: RenderContext) -> List[MenuItem]:
        """
        Get menu items for this renderer.

        Returns:
            List of MenuItem objects
        """
        return [
            MenuItem(
                id='export',
                label='Export...',
                submenu=[
                    MenuItem(id='export_json', label='Export as JSON'),
                    MenuItem(id='export_csv', label='Export as CSV'),
                ]
            ),
            # ... more items
        ]
```

## Test Plan Structure

For each renderer, create:

1. **CLI Test**: Test `render_cli()` output
2. **HTML Test**: Test `render_html()` output
3. **JSON Edit Test**: Test `get_editable_json()`, `validate_json()`, `apply_json_edits()`
4. **Toolbar Test**: Test custom toolbar actions
5. **Integration Test**: Test in full OutputView context

## Implementation Order

1. ✅ CropRenderer (DONE)
2. ✅ RotateRenderer (DONE)
3. ✅ EnhanceRenderer (DONE)
4. RemoveBackgroundRenderer
5. PrepareImagesRenderer
6. SplitRenderer
7. SegmentRenderer
8. TranscribeRenderer
9. DescribeRenderer
10. ConvertToWordRenderer
... (continue in priority order)

## Next Steps

1. Create test plans for existing renderers (crop, rotate, enhance)
2. Implement RemoveBackgroundRenderer
3. Implement PrepareImagesRenderer
4. Add toolbar action system to BaseRenderer
5. Wire up renderer-specific toolbars in OutputView
6. Test complete flow for each renderer

## Notes

- Each renderer extends appropriate base (ImageRenderer, TextRenderer, etc.)
- All renderers must implement: `render_html()`, `render_cli()`, `get_editable_json()`, `validate_json()`, `apply_json_edits()`
- Renderers can optionally implement: `get_toolbar_actions()`, `get_menu_items()`
- Test plans should cover both CLI and GUI rendering
- Focus on extensibility - new tools should be easy to add
