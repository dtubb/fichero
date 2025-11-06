# OUTPUT VIEW SYSTEM - COMPREHENSIVE IMPLEMENTATION PLAN

## Executive Summary

This plan refactors Fichero's output view system into a flexible, tool-specific inspection platform with visual navigation, multi-document viewing, and interactive editing capabilities. The plan builds on existing infrastructure while addressing critical gaps identified in the codebase exploration.

---

## Current State Analysis

### What Exists
- ✅ **OutputView** (`src/fichero/windows/main/views/output/output_view.py`) - 2000+ lines, handles display
- ✅ **ProcessingResult** tracking in SQLite with comprehensive metadata
- ✅ **OutputsManager** for manifest-based output discovery
- ✅ **EditorRegistry** system for tool-to-editor mapping
- ✅ **InspectorWindow** with 5-tab interface (General, Storage, Details, IIIF, Workflows)
- ✅ **WebView-based image viewer** with zoom/rotate
- ✅ **Split view** capability (dual-pane comparison)

### Critical Gaps
- ❌ `_load_from_library()` method **MISSING** from OutputView (asyncio calls reference non-existent method)
- ❌ No unified StepManager (logic scattered across ProcessingNavigator, OutputsManager, DirectorIntegrationService)
- ❌ No visual workflow graph or step status display
- ❌ No tool-specific output views (one-size-fits-all WebView)
- ❌ No JSON editing + reprocessing workflow
- ❌ No export/share functionality for finished outputs
- ❌ New tools (describe_images, extract_library_metadata, analyze_document_groups, convert_to_svg) not registered in EditorRegistry

---

## Architecture Overview

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         Main Window                              │
│  ┌───────────┬─────────────────────────────────────────────────┐│
│  │           │              Output View Area                    ││
│  │ Library   │  ┌────────────┬────────────┬────────────┐       ││
│  │ Tree      │  │  Output    │  Output    │  Output    │       ││
│  │           │  │  View 1    │  View 2    │  View 3    │       ││
│  │           │  │            │            │            │       ││
│  │           │  │ ┌────────┐ │ ┌────────┐ │ ┌────────┐ │       ││
│  │           │  │ │Rendered│ │ │Rendered│ │ │Rendered│ │       ││
│  │           │  │ │Output  │ │ │Output  │ │ │Output  │ │       ││
│  │           │  │ │(WebView│ │ │(WebView│ │ │(WebView│ │       ││
│  │           │  │ │ or Tool│ │ │ or Tool│ │ │ or Tool│ │       ││
│  │           │  │ │Specific│ │ │Specific│ │ │Specific│ │       ││
│  │           │  │ │)       │ │ │)       │ │ │)       │ │       ││
│  │           │  │ └────────┘ │ └────────┘ │ └────────┘ │       ││
│  │           │  │ ┌────────┐ │ ┌────────┐ │ ┌────────┐ │       ││
│  │           │  │ │JSON    │ │ │JSON    │ │ │JSON    │ │       ││
│  │           │  │ │Inspector│ │ │Inspector│ │ │Inspector│ │       ││
│  │           │  │ │(Editable│ │ │(Editable│ │ │(Editable│ │       ││
│  │           │  │ │)       │ │ │)       │ │ │)       │ │       ││
│  │           │  │ └────────┘ │ └────────┘ │ └────────┘ │       ││
│  │           │  └────────────┴────────────┴────────────┘       ││
│  │           │  ┌───────────────────────────────────────┐      ││
│  │           │  │ Step Navigator (Workflow Graph View)  │      ││
│  │           │  │ [Step 1]→[Step 2]→[Step 3]→[Step 4]   │      ││
│  │           │  └───────────────────────────────────────┘      ││
│  └───────────┴─────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Unified Toolbar (context-aware based on focused output)    ││
│  │  [<][>][Zoom][Rotate][Edit][Export][Share][Steps][Compare]  ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

## PHASE 1: Foundation - Fix Critical Gaps (Week 1-2)

### 1.1 Implement Missing `_load_from_library()` Method
**File**: `src/fichero/windows/main/views/output/output_view.py`

**Current Problem**:
```python
# Line 423 in output_view.py
asyncio.create_task(self._load_from_library(item_id=item_id))
# ❌ Method doesn't exist!
```

**Implementation**:
```python
async def _load_from_library(self, item_id: str):
    """Load outputs from library database for a given item"""
    try:
        # Query ProcessingResult records
        processing_results = await asyncio.to_thread(
            self.app.library_manager.get_processing_results,
            item_id
        )

        if not processing_results:
            self.tool_logger.info(f"No processing results found for item {item_id}")
            return

        # Get most recent result
        latest_result = processing_results[0]  # Sorted by created_at DESC

        # Parse metadata to build ToolOutput list
        tool_outputs = []
        for step_info in latest_result.metadata.get('steps', []):
            manifest_path = step_info.get('manifest_path')
            if manifest_path:
                tool_output = await asyncio.to_thread(
                    self._parse_tool_output_from_manifest,
                    Path(manifest_path),
                    step_info
                )
                tool_outputs.append(tool_output)

        # Load into output view
        await self._display_tool_outputs(tool_outputs, item_id)

    except Exception as e:
        self.tool_logger.error(f"Failed to load from library: {e}")
        self._show_error(f"Could not load outputs: {e}")

def _parse_tool_output_from_manifest(self, manifest_path: Path, step_info: dict) -> ToolOutput:
    """Parse a manifest file to create ToolOutput object"""
    entries = list(srsly.read_jsonl(manifest_path))

    return ToolOutput(
        tool_name=step_info['step_name'],
        output_folder=manifest_path.parent,
        manifest_path=manifest_path,
        files=[entry.get('output') or entry.get('source') for entry in entries],
        parameters=step_info.get('parameters', {}),
        status=step_info.get('status', 'completed')
    )
```

**Testing**:
- Unit test for `_load_from_library()` with mock library_manager
- Integration test loading real ProcessingResult from database
- End-to-end test: process item → load outputs in OutputView

---

### 1.2 Create Unified StepManager
**New File**: `src/fichero/library/step_manager.py`

**Purpose**: Consolidate step tracking logic from ProcessingNavigator, OutputsManager, and DirectorIntegrationService

**Interface**:
```python
class StepManager:
    """Unified manager for processing step discovery and tracking"""

    def __init__(self, library_manager):
        self.library_manager = library_manager

    # Step Discovery
    def get_available_steps(self, item_id: str) -> List[ProcessingStep]:
        """Get all available steps for an item"""

    def get_step_info(self, item_id: str, step_name: str) -> ProcessingStepInfo:
        """Get detailed info about a specific step"""

    def get_workflow_graph(self, item_id: str) -> WorkflowGraph:
        """Build workflow DAG showing step dependencies"""

    # Step Status
    def get_step_status(self, item_id: str, step_name: str) -> StepStatus:
        """Get status (pending/running/success/failed/partial)"""

    def get_step_outputs(self, item_id: str, step_name: str) -> List[Path]:
        """List output files from a step"""

    def get_step_manifest(self, item_id: str, step_name: str) -> Path:
        """Get path to step's manifest file"""

    # Tool Management
    def list_registered_tools(self) -> List[ToolInfo]:
        """List all tools known to the system"""

    def get_tool_info(self, tool_name: str) -> ToolInfo:
        """Get metadata about a specific tool"""

    def is_tool_registered(self, tool_name: str) -> bool:
        """Check if tool has an output view handler"""

@dataclass
class ProcessingStepInfo:
    """Complete information about a processing step"""
    step_name: str
    tool_name: str
    status: StepStatus  # pending/running/success/failed/partial
    manifest_path: Optional[Path]
    output_folder: Optional[Path]
    parameters: dict
    files_processed: int
    files_succeeded: int
    files_failed: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    log_path: Optional[Path]
    error_message: Optional[str]

@dataclass
class WorkflowGraph:
    """DAG representation of workflow execution"""
    steps: List[ProcessingStepInfo]
    edges: List[Tuple[str, str]]  # (from_step, to_step)
    execution_order: List[str]  # Topologically sorted step names
```

**Implementation Steps**:
1. Create `step_manager.py` with interface above
2. Migrate logic from ProcessingNavigator (filesystem scanning)
3. Migrate logic from OutputsManager (manifest parsing)
4. Migrate logic from DirectorIntegrationService (metadata extraction)
5. Add to LibraryManager: `self.step_manager = StepManager(self)`
6. Update OutputView to use `app.library_manager.step_manager`

---

### 1.3 Register New Tools in EditorRegistry
**File**: `src/fichero/library/outputs/editor_registry.py`

**Current State**: Only 7 tools registered (transcribe_qwen_max, transcribe_lmstudio, catalogue_folder, prepare_images, crop, rotate, enhance)

**Add 4 New Tools**:
```python
def _register_defaults(self):
    """Register default editors for known tools"""
    json_editor = JSONEditor()
    image_editor = ImageEditor()

    # Existing registrations...

    # NEW: Image description tool
    self._tool_map['describe_images'] = json_editor

    # NEW: Metadata extraction tool
    self._tool_map['extract_library_metadata'] = json_editor

    # NEW: Document grouping tool
    self._tool_map['analyze_document_groups'] = json_editor

    # NEW: SVG conversion tool (needs specialized editor)
    svg_editor = SVGEditor()  # Create this
    self._tool_map['convert_to_svg'] = svg_editor
```

---

## PHASE 2: Tool-Specific Output Views (Week 3-4)

### 2.1 Create Base Tool View Component
**New File**: `src/fichero/windows/main/views/output/tool_views/base_tool_view.py`

**Abstract Base Class**:
```python
class BaseToolView(toga.Box):
    """Base class for tool-specific output renderers"""

    def __init__(self, tool_name: str, output_data: dict, **kwargs):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.tool_name = tool_name
        self.output_data = output_data
        self.inspector = None  # JSON inspector component

    @abstractmethod
    def render_output(self) -> toga.Widget:
        """Render the tool's output (left column)"""
        pass

    @abstractmethod
    def create_inspector(self) -> toga.Widget:
        """Create JSON inspector (right column)"""
        pass

    def on_parameter_changed(self, param_name: str, new_value: Any):
        """Called when user edits a parameter in inspector"""
        self.output_data[param_name] = new_value
        self.mark_stale()
        self.trigger_reprocess()

    def mark_stale(self):
        """Mark output as stale (needs reprocessing)"""
        self.add_class('stale-output')

    def trigger_reprocess(self):
        """Request reprocessing with updated parameters"""
        # Emit event to OutputView to rerun step
        pass
```

---

### 2.2 Implement Tool-Specific Views

#### Image Tool View
**File**: `src/fichero/windows/main/views/output/tool_views/image_tool_view.py`

```python
class ImageToolView(BaseToolView):
    """View for image processing tools (crop, rotate, enhance, etc.)"""

    def render_output(self) -> toga.Widget:
        # Use existing WebView with image
        self.webview = toga.WebView(
            style=Pack(flex=1),
            on_webview_load=self.on_webview_load
        )
        self.webview.url = self._get_image_url()
        return self.webview

    def create_inspector(self) -> toga.Widget:
        inspector = toga.Box(style=Pack(direction=COLUMN, padding=10))

        # Editable fields
        inspector.add(self._create_param_editor('brightness', float))
        inspector.add(self._create_param_editor('contrast', float))
        inspector.add(self._create_param_editor('rotation', int))

        # Re-edit button (launches HTML crop UI)
        inspector.add(toga.Button(
            'Re-Crop Image',
            on_press=self.launch_crop_editor,
            style=Pack(padding_top=10)
        ))

        return inspector

    def launch_crop_editor(self, widget):
        """Launch HTML canvas-based crop editor"""
        html = self._generate_crop_editor_html()
        self.webview.set_content(html, 'text/html')
```

#### Transcription Tool View
**File**: `src/fichero/windows/main/views/output/tool_views/transcription_tool_view.py`

```python
class TranscriptionToolView(BaseToolView):
    """View for transcription tools (transcribe_qwen_max, transcribe_lmstudio)"""

    def render_output(self) -> toga.Widget:
        # Split view: image on left, text on right
        split = toga.SplitContainer(style=Pack(flex=1))

        # Original image
        image_view = toga.WebView()
        image_view.url = self._get_source_image_url()

        # Transcribed text (editable!)
        text_view = toga.MultilineTextInput(
            value=self.output_data.get('transcription', {}).get('text', ''),
            style=Pack(flex=1, font_family='monospace', font_size=11)
        )
        text_view.on_change = self.on_text_changed

        split.content = [image_view, text_view]
        return split

    def on_text_changed(self, widget):
        """User edited transcription - mark for save"""
        self.output_data['transcription']['text'] = widget.value
        self.mark_modified()
```

#### Document Groups Tool View
**File**: `src/fichero/windows/main/views/output/tool_views/document_groups_tool_view.py`

```python
class DocumentGroupsToolView(BaseToolView):
    """View for analyze_document_groups tool"""

    def render_output(self) -> toga.Widget:
        # Generate HTML visualization of groups
        html = self._generate_groups_visualization()

        webview = toga.WebView(style=Pack(flex=1))
        webview.set_content(html, 'text/html')

        return webview

    def _generate_groups_visualization(self) -> str:
        """Generate HTML showing thumbnail gallery grouped by document"""
        groups = self.output_data.get('analysis', {}).get('groups', [])

        html_parts = ['<html><body style="font-family: sans-serif;">']

        for group in groups:
            html_parts.append(f'<h2>Group {group["group_id"]}: {group["visual_type"]}</h2>')
            html_parts.append(f'<p>{group["visual_characteristics"]}</p>')
            html_parts.append(f'<div style="display: flex; flex-wrap: wrap;">')

            for filename in group['files']:
                thumb_path = self._get_thumbnail_path(filename)
                html_parts.append(f'''
                    <div style="margin: 10px; text-align: center;">
                        <img src="{thumb_path}" style="max-width: 150px; border: 1px solid #ccc;">
                        <p style="font-size: 10px;">{filename}</p>
                    </div>
                ''')

            html_parts.append('</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)
```

#### SVG Tool View
**File**: `src/fichero/windows/main/views/output/tool_views/svg_tool_view.py`

```python
class SVGToolView(BaseToolView):
    """View for convert_to_svg tool"""

    def render_output(self) -> toga.Widget:
        # Display SVG in WebView
        svg_path = self.output_data.get('svg_path')

        webview = toga.WebView(style=Pack(flex=1))
        webview.url = f"file://{svg_path}"

        return webview

    def create_inspector(self) -> toga.Widget:
        inspector = toga.Box(style=Pack(direction=COLUMN, padding=10))

        # SVG generation parameters
        inspector.add(self._create_param_editor('trace_accuracy', int))
        inspector.add(self._create_param_editor('color_precision', int))
        inspector.add(self._create_param_editor('filter_size', int))

        # Re-generate button
        inspector.add(toga.Button(
            'Regenerate SVG',
            on_press=self.trigger_reprocess,
            style=Pack(padding_top=10)
        ))

        return inspector
```

#### Catalogue Tool View
**File**: `src/fichero/windows/main/views/output/tool_views/catalogue_tool_view.py`

```python
class CatalogueToolView(BaseToolView):
    """View for catalogue_folder and llm_process tools"""

    def render_output(self) -> toga.Widget:
        # Show Word document + extracted metadata
        split = toga.SplitContainer(style=Pack(flex=1))

        # Word doc preview (WebView showing HTML conversion or PDF)
        doc_view = toga.WebView()
        doc_view.url = self._get_word_doc_preview_url()

        # Metadata table
        metadata_view = self._create_metadata_table()

        split.content = [doc_view, metadata_view]
        return split

    def _create_metadata_table(self) -> toga.Widget:
        """Create table showing extracted metadata fields"""
        table = toga.Table(
            headings=['Field', 'Value'],
            data=self._get_metadata_rows(),
            style=Pack(flex=1)
        )
        return table

    def _get_metadata_rows(self) -> List[Tuple[str, str]]:
        """Extract metadata for table display"""
        catalogue = self.output_data.get('catalogue', {})
        return [
            ('Title', catalogue.get('title', '')),
            ('Date', catalogue.get('date', '')),
            ('Location', catalogue.get('location', '')),
            ('People', ', '.join(catalogue.get('people', []))),
            ('Organizations', ', '.join(catalogue.get('organizations', []))),
            ('Keywords', ', '.join(catalogue.get('keywords', []))),
        ]
```

---

### 2.3 Tool View Registry
**New File**: `src/fichero/windows/main/views/output/tool_views/registry.py`

```python
class ToolViewRegistry:
    """Maps tool names to their specialized view classes"""

    def __init__(self):
        self._view_map = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in tool views"""
        # Image tools
        self._view_map['crop'] = ImageToolView
        self._view_map['rotate'] = ImageToolView
        self._view_map['enhance'] = ImageToolView
        self._view_map['prepare_images'] = ImageToolView

        # Transcription tools
        self._view_map['transcribe_qwen_max'] = TranscriptionToolView
        self._view_map['transcribe_lmstudio'] = TranscriptionToolView

        # Catalogue tools
        self._view_map['catalogue_folder'] = CatalogueToolView
        self._view_map['llm_process'] = CatalogueToolView

        # New tools
        self._view_map['describe_images'] = JSONToolView
        self._view_map['extract_library_metadata'] = JSONToolView
        self._view_map['analyze_document_groups'] = DocumentGroupsToolView
        self._view_map['convert_to_svg'] = SVGToolView

    def get_view_class(self, tool_name: str) -> Type[BaseToolView]:
        """Get view class for a tool (default to GenericToolView)"""
        return self._view_map.get(tool_name, GenericToolView)

    def register_view(self, tool_name: str, view_class: Type[BaseToolView]):
        """Register a custom view for a tool"""
        self._view_map[tool_name] = view_class

# Global registry
tool_view_registry = ToolViewRegistry()
```

---

## PHASE 3: Web-Based Folder View (Week 5)

### 3.1 Folder Gallery Component
**New File**: `src/fichero/windows/main/views/output/folder_view/folder_gallery.py`

**Purpose**: Display folder contents as thumbnail gallery with metadata

```python
class FolderGalleryView(toga.Box):
    """WebView-based gallery for folder contents"""

    def __init__(self, folder_path: Path, **kwargs):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.folder_path = folder_path
        self.webview = None
        self.items = []

        self._build_ui()
        self._load_folder()

    def _build_ui(self):
        """Create WebView and controls"""
        # Gallery WebView
        self.webview = toga.WebView(
            style=Pack(flex=1),
            on_webview_load=self.on_gallery_load
        )
        self.add(self.webview)

        # Controls
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(toga.Button('Select All', on_press=self.select_all))
        controls.add(toga.Button('Deselect All', on_press=self.deselect_all))
        controls.add(toga.Button('View Selected', on_press=self.view_selected))
        self.add(controls)

    def _load_folder(self):
        """Scan folder and generate gallery HTML"""
        # Discover all images
        self.items = []
        for img_path in self.folder_path.glob('**/*.{jpg,jpeg,png,tiff}'):
            self.items.append(FolderItem(
                path=img_path,
                metadata=self._extract_metadata(img_path),
                selected=False
            ))

        # Generate HTML gallery
        html = self._generate_gallery_html()
        self.webview.set_content(html, 'text/html')

    def _generate_gallery_html(self) -> str:
        """Generate responsive thumbnail gallery"""
        html = '''
        <html>
        <head>
            <style>
                body { font-family: sans-serif; padding: 20px; }
                .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }
                .item { border: 2px solid #ccc; padding: 10px; cursor: pointer; transition: all 0.2s; }
                .item:hover { border-color: #007AFF; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
                .item.selected { border-color: #007AFF; background-color: #E5F2FF; }
                .thumbnail { width: 100%; height: 150px; object-fit: cover; }
                .caption { font-size: 11px; margin-top: 5px; }
                .metadata { font-size: 9px; color: #666; margin-top: 3px; }
            </style>
            <script>
                function toggleSelection(index) {
                    var item = document.getElementById('item-' + index);
                    item.classList.toggle('selected');

                    // Send message to Python
                    window.webkit.messageHandlers.toggleSelection.postMessage({index: index});
                }
            </script>
        </head>
        <body>
            <h2>Folder: ''' + self.folder_path.name + '''</h2>
            <div class="gallery">
        '''

        for i, item in enumerate(self.items):
            html += f'''
                <div class="item" id="item-{i}" onclick="toggleSelection({i})">
                    <img class="thumbnail" src="file://{item.path}" alt="{item.path.name}">
                    <div class="caption">{item.path.name}</div>
                    <div class="metadata">
                        Size: {item.metadata.get('size', 'Unknown')}<br>
                        Modified: {item.metadata.get('modified', 'Unknown')}
                    </div>
                </div>
            '''

        html += '''
            </div>
        </body>
        </html>
        '''

        return html

    def _extract_metadata(self, img_path: Path) -> dict:
        """Extract metadata from image file"""
        stat = img_path.stat()
        return {
            'size': f"{stat.st_size / 1024:.1f} KB",
            'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            'path': str(img_path)
        }
```

**Integration**: This becomes an option when right-clicking folders in library tree:
- Right-click folder → "View as Gallery" → Opens FolderGalleryView in output pane

---

## PHASE 4: Multi-View Split System (Week 6)

### 4.1 Refactor OutputView for Multiple Panes
**File**: `src/fichero/windows/main/views/output/output_view.py`

**Current Architecture**: Single WebView or dual split

**New Architecture**: Dynamic multi-pane system

```python
class OutputView(BaseView):
    """Enhanced output view supporting multiple simultaneous panes"""

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.panes = []  # List of OutputPane instances
        self.focused_pane = None
        self.split_container = None

    def add_pane(self, tool_output: ToolOutput, position='right'):
        """Add a new output pane"""
        pane = OutputPane(
            tool_output=tool_output,
            on_focus=self._on_pane_focused,
            on_close=self._on_pane_closed
        )
        self.panes.append(pane)
        self._rebuild_layout()

    def _rebuild_layout(self):
        """Rebuild split container based on panes"""
        if len(self.panes) == 1:
            self.content = self.panes[0]
        elif len(self.panes) == 2:
            self.split_container = toga.SplitContainer(
                content=[self.panes[0], self.panes[1]],
                style=Pack(flex=1)
            )
            self.content = self.split_container
        else:
            # 3+ panes: nested splits
            self.content = self._create_nested_splits()

    def _create_nested_splits(self) -> toga.SplitContainer:
        """Create nested split containers for 3+ panes"""
        # Horizontal split for pairs, then vertical split
        # TODO: More sophisticated layout algorithm
        pass

class OutputPane(toga.Box):
    """Single output pane within multi-view system"""

    def __init__(self, tool_output: ToolOutput, on_focus, on_close, **kwargs):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.tool_output = tool_output
        self.on_focus = on_focus
        self.on_close = on_close
        self.focused = False

        self._build_ui()

    def _build_ui(self):
        # Pane header with title and close button
        header = toga.Box(style=Pack(direction=ROW, padding=5, background_color='#f0f0f0'))
        header.add(toga.Label(
            self.tool_output.tool_name,
            style=Pack(flex=1, padding_left=5)
        ))
        header.add(toga.Button('×', on_press=self._on_close_clicked))
        self.add(header)

        # Tool-specific view
        view_class = tool_view_registry.get_view_class(self.tool_output.tool_name)
        self.tool_view = view_class(
            tool_name=self.tool_output.tool_name,
            output_data=self.tool_output.get_data()
        )
        self.add(self.tool_view)

    def focus(self):
        """Bring pane into focus"""
        self.focused = True
        self.style.update(border='2px solid #007AFF')
        self.on_focus(self)

    def blur(self):
        """Remove focus from pane"""
        self.focused = False
        self.style.update(border='1px solid #ccc')
```

---

### 4.2 Focus Management
**Implementation**: Track which pane has focus and update toolbar accordingly

```python
class OutputView(BaseView):
    def _on_pane_focused(self, pane: OutputPane):
        """Called when user clicks in a pane"""
        # Blur all panes
        for p in self.panes:
            p.blur()

        # Focus target pane
        pane.focus()
        self.focused_pane = pane

        # Update toolbar for this tool
        self._update_toolbar_for_tool(pane.tool_output.tool_name)

    def _update_toolbar_for_tool(self, tool_name: str):
        """Show/hide toolbar buttons based on active tool"""
        toolbar = self.window.toolbar

        # Common buttons always visible
        toolbar.show('nav_prev_step', 'nav_next_step', 'zoom_in', 'zoom_out')

        # Tool-specific buttons
        if tool_name in ['crop', 'rotate', 'enhance']:
            toolbar.show('edit_mode', 'save_image')
        elif tool_name in ['transcribe_qwen_max', 'transcribe_lmstudio']:
            toolbar.show('edit_text', 'save_transcription')
        elif tool_name in ['catalogue_folder', 'llm_process']:
            toolbar.show('export_word', 'share_catalogue')
        else:
            toolbar.hide('edit_mode', 'edit_text', 'export_word', 'share_catalogue')
```

---

## PHASE 5: Interactive Editing & Reprocessing (Week 7-8)

### 5.1 JSON Parameter Editor
**File**: `src/fichero/windows/main/views/output/inspector/json_parameter_editor.py`

```python
class JSONParameterEditor(toga.Box):
    """Editable JSON inspector for tool parameters"""

    def __init__(self, data: dict, on_change_callback, **kwargs):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.data = data
        self.on_change = on_change_callback
        self.fields = {}

        self._build_ui()

    def _build_ui(self):
        """Create form fields for each parameter"""
        scroll = toga.ScrollContainer(style=Pack(flex=1))
        form = toga.Box(style=Pack(direction=COLUMN, padding=10))

        for key, value in self.data.items():
            field_box = toga.Box(style=Pack(direction=ROW, padding=5))
            field_box.add(toga.Label(key, style=Pack(width=150)))

            # Create appropriate input widget based on type
            if isinstance(value, bool):
                widget = toga.Switch(value=value, on_change=lambda w, k=key: self._on_field_changed(k, w.value))
            elif isinstance(value, int):
                widget = toga.NumberInput(value=value, step=1, on_change=lambda w, k=key: self._on_field_changed(k, w.value))
            elif isinstance(value, float):
                widget = toga.NumberInput(value=value, step=0.1, on_change=lambda w, k=key: self._on_field_changed(k, w.value))
            elif isinstance(value, str):
                widget = toga.TextInput(value=value, on_change=lambda w, k=key: self._on_field_changed(k, w.value))
            else:
                widget = toga.TextInput(value=str(value), on_change=lambda w, k=key: self._on_field_changed(k, w.value))

            field_box.add(widget)
            form.add(field_box)
            self.fields[key] = widget

        scroll.content = form
        self.add(scroll)

    def _on_field_changed(self, key: str, new_value: Any):
        """User edited a field"""
        self.data[key] = new_value
        self.on_change(key, new_value)
```

---

### 5.2 Reprocessing Workflow
**Implementation**: When user edits parameters, trigger reprocessing

```python
class OutputView(BaseView):
    def _on_parameter_changed(self, pane: OutputPane, param_name: str, new_value: Any):
        """User edited a parameter - offer to reprocess"""
        # Show reprocess prompt
        response = await self.app.main_window.confirm_dialog(
            'Reprocess Step',
            f'Parameter "{param_name}" changed to {new_value}. Reprocess this step and all downstream steps?'
        )

        if response:
            await self._reprocess_from_step(
                pane.tool_output,
                updated_params={param_name: new_value}
            )

    async def _reprocess_from_step(self, tool_output: ToolOutput, updated_params: dict):
        """Rerun a step with new parameters"""
        # Update manifest with new parameters
        self._update_manifest_params(tool_output.manifest_path, updated_params)

        # Determine which steps depend on this one
        dependent_steps = self.app.library_manager.step_manager.get_dependent_steps(
            tool_output.item_id,
            tool_output.tool_name
        )

        # Submit reprocessing task
        await self.app.director_integration.reprocess_step(
            item_id=tool_output.item_id,
            step_name=tool_output.tool_name,
            parameters=updated_params,
            reprocess_downstream=len(dependent_steps) > 0
        )

        # Show progress
        self._show_reprocessing_progress(tool_output.tool_name, dependent_steps)
```

---

### 5.3 Visual Re-Editing Tools
**File**: `src/fichero/windows/main/views/output/editors/crop_editor.py`

**HTML Canvas-Based Crop Editor**:
```python
class CropEditor:
    """Generates HTML canvas UI for re-cropping images"""

    @staticmethod
    def generate_html(image_path: Path, current_crop: dict) -> str:
        """Generate interactive crop editor HTML"""
        return f'''
        <html>
        <head>
            <style>
                body {{ margin: 0; padding: 20px; font-family: sans-serif; }}
                #canvas {{ border: 2px solid #007AFF; cursor: crosshair; }}
                .controls {{ margin-top: 10px; }}
                button {{ padding: 8px 16px; margin-right: 5px; background: #007AFF; color: white; border: none; border-radius: 4px; cursor: pointer; }}
                button:hover {{ background: #0051D5; }}
            </style>
        </head>
        <body>
            <canvas id="canvas"></canvas>
            <div class="controls">
                <button onclick="applyCrop()">Apply Crop</button>
                <button onclick="resetCrop()">Reset</button>
                <button onclick="cancel()">Cancel</button>
            </div>
            <script>
                const canvas = document.getElementById('canvas');
                const ctx = canvas.getContext('2d');
                const img = new Image();
                img.src = 'file://{image_path}';

                let cropRect = {{
                    x: {current_crop.get('x', 0)},
                    y: {current_crop.get('y', 0)},
                    width: {current_crop.get('width', 100)},
                    height: {current_crop.get('height', 100)}
                }};

                img.onload = function() {{
                    canvas.width = img.width;
                    canvas.height = img.height;
                    draw();
                }};

                function draw() {{
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(img, 0, 0);

                    // Draw crop rectangle
                    ctx.strokeStyle = '#007AFF';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(cropRect.x, cropRect.y, cropRect.width, cropRect.height);

                    // Dim outside crop area
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
                    ctx.fillRect(0, 0, canvas.width, cropRect.y);
                    ctx.fillRect(0, cropRect.y, cropRect.x, cropRect.height);
                    ctx.fillRect(cropRect.x + cropRect.width, cropRect.y, canvas.width, cropRect.height);
                    ctx.fillRect(0, cropRect.y + cropRect.height, canvas.width, canvas.height);
                }}

                // Mouse drag to adjust crop
                let isDragging = false;
                canvas.addEventListener('mousedown', (e) => {{ isDragging = true; }});
                canvas.addEventListener('mouseup', (e) => {{ isDragging = false; }});
                canvas.addEventListener('mousemove', (e) => {{
                    if (!isDragging) return;
                    // Update cropRect based on mouse position
                    // ... implementation
                    draw();
                }});

                function applyCrop() {{
                    window.webkit.messageHandlers.applyCrop.postMessage(cropRect);
                }}

                function resetCrop() {{
                    cropRect = {{x: 0, y: 0, width: img.width, height: img.height}};
                    draw();
                }}

                function cancel() {{
                    window.webkit.messageHandlers.cancel.postMessage({{}});
                }}
            </script>
        </body>
        </html>
        '''
```

---

## PHASE 6: Export & Share Functionality (Week 9)

### 6.1 Export Manager
**New File**: `src/fichero/library/export_manager.py`

```python
class ExportManager:
    """Manages exporting finished outputs for user consumption"""

    def __init__(self, library_manager):
        self.library_manager = library_manager

    def export_output(self, tool_output: ToolOutput, export_format: str, destination: Path):
        """Export a tool's output in specified format"""
        if export_format == 'original':
            # Copy output files as-is
            self._copy_files(tool_output.files, destination)

        elif export_format == 'zip':
            # Create ZIP archive
            self._create_zip_archive(tool_output.files, destination)

        elif export_format == 'share_link':
            # Generate shareable link (if cloud storage configured)
            return self._create_share_link(tool_output)

        else:
            raise ValueError(f"Unknown export format: {export_format}")

    def export_catalogue(self, item_id: str, destination: Path):
        """Export catalogue Word document"""
        # Find catalogue step
        catalogue_output = self.library_manager.step_manager.get_step_outputs(
            item_id,
            'llm_process'  # or 'catalogue_folder'
        )

        # Copy Word doc to destination
        for output_file in catalogue_output:
            if output_file.suffix == '.docx':
                shutil.copy(output_file, destination / output_file.name)
                return destination / output_file.name

        raise FileNotFoundError("No Word document found in catalogue output")
```

---

### 6.2 Export UI
**Integration into OutputView Toolbar**:

```python
class OutputView(BaseView):
    def _setup_toolbar(self):
        """Add export/share buttons to toolbar"""
        self.toolbar.add_command(
            'export_output',
            'Export',
            'Export current output',
            self._on_export_clicked
        )

        self.toolbar.add_command(
            'share_output',
            'Share',
            'Share current output',
            self._on_share_clicked
        )

    async def _on_export_clicked(self, widget):
        """Handle export button click"""
        if not self.focused_pane:
            return

        # Show export dialog
        format_choice = await self.app.main_window.question_dialog(
            'Export Format',
            'Choose export format:',
            ['Original Files', 'ZIP Archive', 'Share Link']
        )

        if format_choice == 'Original Files':
            destination = await self.app.main_window.save_file_dialog(
                'Export to Folder',
                suggested_filename='',
                file_types=[]
            )
            if destination:
                await asyncio.to_thread(
                    self.app.library_manager.export_manager.export_output,
                    self.focused_pane.tool_output,
                    'original',
                    destination
                )
                await self.app.main_window.info_dialog('Export Complete', f'Files exported to {destination}')

        # ... handle other formats

    async def _on_share_clicked(self, widget):
        """Handle share button click"""
        # Generate share link or prepare email attachment
        # Implementation depends on sharing method
        pass
```

---

## PHASE 7: Step Navigator & Workflow Visualization (Week 10)

### 7.1 Workflow Graph Component
**New File**: `src/fichero/windows/main/views/output/workflow_graph.py`

```python
class WorkflowGraphView(toga.Box):
    """Visual representation of workflow execution with step status"""

    def __init__(self, workflow_graph: WorkflowGraph, **kwargs):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.graph = workflow_graph
        self.selected_step = None

        self._build_ui()

    def _build_ui(self):
        """Generate HTML graph visualization"""
        html = self._generate_graph_html()

        self.webview = toga.WebView(style=Pack(flex=1, height=150))
        self.webview.set_content(html, 'text/html')
        self.add(self.webview)

    def _generate_graph_html(self) -> str:
        """Generate D3.js-based workflow graph"""
        # Use D3.js or similar to render DAG
        # Nodes colored by status (green=success, red=failed, yellow=running, gray=pending)
        # Clickable nodes to jump to that step
        return '''
        <html>
        <head>
            <script src="https://d3js.org/d3.v7.min.js"></script>
            <style>
                body { margin: 0; padding: 10px; }
                .node { cursor: pointer; }
                .node.success { fill: #28a745; }
                .node.failed { fill: #dc3545; }
                .node.running { fill: #ffc107; }
                .node.pending { fill: #6c757d; }
                .node:hover { opacity: 0.8; }
            </style>
        </head>
        <body>
            <svg id="graph" width="100%" height="130"></svg>
            <script>
                // D3.js graph rendering
                const data = ''' + json.dumps(self._format_graph_data()) + ''';

                // ... D3 layout and rendering code

                function onNodeClick(stepName) {
                    window.webkit.messageHandlers.stepSelected.postMessage({step: stepName});
                }
            </script>
        </body>
        </html>
        '''
```

**Integration**: Add WorkflowGraphView to top of OutputView

---

## PHASE 8: Platform Detection & Responsive UI (Week 11)

### 8.1 Platform Detection
**File**: `src/fichero/core/platform_detection.py`

```python
import platform
import os

class PlatformInfo:
    """Centralized platform detection and capabilities"""

    def __init__(self):
        self.os_name = platform.system()  # 'Darwin', 'Windows', 'Linux'
        self.is_mobile = self._detect_mobile()
        self.is_desktop = not self.is_mobile
        self.backend = os.environ.get('TOGA_BACKEND', 'unknown')

    def _detect_mobile(self) -> bool:
        """Detect if running on mobile platform"""
        backend = os.environ.get('TOGA_BACKEND', '')
        if 'iOS' in backend or 'Android' in backend:
            return True

        if os.environ.get('FORCE_MOBILE_UI') == 'true':
            return True

        return False

    def supports_webview(self) -> bool:
        """Check if platform supports Toga WebView"""
        # All platforms currently support WebView
        return True

    def supports_multi_window(self) -> bool:
        """Check if platform supports multiple windows"""
        return self.is_desktop

    def supports_split_view(self) -> bool:
        """Check if platform supports split containers"""
        return True  # Toga supports on all platforms

# Global instance
platform_info = PlatformInfo()
```

---

### 8.2 Responsive Layout Adapter
**Pattern**: Use platform_info to adapt layouts

```python
class OutputView(BaseView):
    def _rebuild_layout(self):
        """Build layout appropriate for platform"""
        if platform_info.is_mobile:
            # Mobile: Single pane, swipe between outputs
            self.content = self._create_mobile_layout()
        else:
            # Desktop: Multi-pane splits
            self.content = self._create_desktop_layout()

    def _create_mobile_layout(self) -> toga.Widget:
        """Single-pane layout with swipe navigation"""
        # Use OptionContainer for tabbed views
        tabs = toga.OptionContainer(style=Pack(flex=1))
        for pane in self.panes:
            tabs.add(pane.tool_output.tool_name, pane)
        return tabs

    def _create_desktop_layout(self) -> toga.Widget:
        """Multi-pane split layout"""
        if len(self.panes) == 1:
            return self.panes[0]
        else:
            return self._create_nested_splits()
```

---

## File Structure Summary

```
src/fichero/
├── library/
│   ├── step_manager.py                    # NEW: Unified step tracking
│   ├── export_manager.py                  # NEW: Export/share functionality
│   ├── processing_navigator.py            # REFACTOR: Use StepManager
│   ├── outputs_manager.py                 # REFACTOR: Use StepManager
│   └── outputs/
│       ├── editor_registry.py             # UPDATE: Register new tools
│       ├── base_editor.py                 # (existing)
│       ├── json_editor.py                 # (existing)
│       ├── image_editor.py                # (existing)
│       └── svg_editor.py                  # NEW: SVG tool editor
│
├── windows/
│   ├── main/
│   │   └── views/
│   │       └── output/
│   │           ├── output_view.py         # MAJOR UPDATE: Multi-pane, tool views
│   │           ├── workflow_graph.py      # NEW: Workflow visualization
│   │           ├── tool_views/            # NEW: Tool-specific views
│   │           │   ├── base_tool_view.py
│   │           │   ├── registry.py
│   │           │   ├── image_tool_view.py
│   │           │   ├── transcription_tool_view.py
│   │           │   ├── catalogue_tool_view.py
│   │           │   ├── document_groups_tool_view.py
│   │           │   ├── svg_tool_view.py
│   │           │   └── json_tool_view.py  # Generic fallback
│   │           ├── folder_view/           # NEW: Gallery view
│   │           │   └── folder_gallery.py
│   │           ├── inspector/             # NEW: JSON editor
│   │           │   └── json_parameter_editor.py
│   │           └── editors/               # NEW: Visual editors
│   │               ├── crop_editor.py
│   │               └── rotate_editor.py
│   │
│   └── inspector/
│       └── inspector_window.py            # MINOR UPDATE: Refactor for reuse
│
└── core/
    └── platform_detection.py              # NEW: Platform capabilities

```

---

## Implementation Order

### Critical Path (Weeks 1-4)
1. ✅ Fix `_load_from_library()` - **BLOCKING** all library integration
2. ✅ Create StepManager - Foundation for everything
3. ✅ Register new tools in EditorRegistry
4. ✅ Implement BaseToolView and registry
5. ✅ Implement 3-4 key tool views (Image, Transcription, Catalogue, DocumentGroups)

### High Value (Weeks 5-7)
6. FolderGalleryView for visual folder navigation
7. Multi-pane split system
8. JSONParameterEditor for editing
9. Reprocessing workflow

### Polish (Weeks 8-11)
10. Export/Share Manager
11. WorkflowGraphView
12. Platform detection & responsive UI
13. Visual re-editing tools (crop, rotate)

---

## Key Architectural Decisions

### 1. Where should platform detection logic live?
**Decision**: `src/fichero/core/platform_detection.py` with global `platform_info` instance

**Rationale**:
- Centralized, single source of truth
- Easy to import: `from fichero.core.platform_detection import platform_info`
- Can be mocked for testing different platforms
- Aligns with existing `core/` module for cross-cutting concerns

---

### 2. How should collection views be abstracted?
**Decision**: Adapter pattern via `BaseToolView` + `ToolViewRegistry`

**Rationale**:
- Tool developers implement `BaseToolView` subclass
- Registry maps tool names to view classes
- OutputView is decoupled from specific tools
- Easy to add new tools without modifying OutputView
- Falls back to GenericToolView for unknown tools

---

### 3. Should tool-specific output views be separate files?
**Decision**: Yes, separate files in `tool_views/` directory

**Rationale**:
- Better code organization (each tool = one file)
- Easier to maintain and test individually
- Can be developed independently
- Registry pattern loads on-demand
- Future: Could be plugins in separate packages

---

### 4. How should split view system manage multiple outputs?
**Decision**: `OutputPane` class + dynamic split container rebuilding

**Rationale**:
- Each pane is self-contained (easier to add/remove)
- Panes handle their own focus state
- OutputView manages layout (can change algorithm without affecting panes)
- Supports arbitrary number of panes (not just 2)
- Can implement different layouts (grid, tabs) for mobile

---

### 5. Best way to handle reprocessing pipeline?
**Decision**: Event-based with dependency tracking via StepManager

**Workflow**:
```
User edits param → ToolView.on_parameter_changed()
                 ↓
    OutputView._on_parameter_changed() (asks user to confirm)
                 ↓
    StepManager.get_dependent_steps() (find downstream steps)
                 ↓
    DirectorIntegration.reprocess_step() (submit to Director)
                 ↓
    Progress updates via TaskMonitor
                 ↓
    OutputView refreshes when complete
```

**Rationale**:
- StepManager knows workflow graph (can trace dependencies)
- Director handles actual reprocessing (consistent with existing arch)
- User confirmation prevents accidental long-running tasks
- Progress tracking reuses existing TaskMonitor infrastructure

---

### 6. Should web-based folder view be a "tool" or special case?
**Decision**: Special case (not a tool) - triggered by UI action

**Rationale**:
- Folders aren't "outputs" from processing
- Gallery view is a navigation aid, not a processing result
- Triggered by right-click on folder → "View as Gallery"
- Doesn't fit tool paradigm (no input/output/manifest)
- Can coexist with tools in OutputView (separate pane)

---

## Integration with Library Step Manager

### How Step Manager Tracks New Tools

**Current State**: New tools ARE tracked by DirectorIntegrationService
- When workflow runs, DirectorIntegrationService captures ALL steps in `ProcessingResult.metadata['steps']`
- Includes: step_name, manifest_path, status, file counts, etc.
- Works for ANY tool (no hardcoding needed)

**What's Missing**: UI doesn't display new tools properly
- OutputView has `_load_from_library()` missing (can't load from database)
- EditorRegistry doesn't know about new tools (defaults to JSONEditor)
- No tool-specific views for new tools (generic WebView used)

**Solution**: This plan fixes UI layer
1. Implement `_load_from_library()` → Can load from database ✅
2. Register new tools in EditorRegistry → Proper editor assigned ✅
3. Create tool-specific views → Better UX for new tools ✅
4. StepManager provides unified API → Easy to query ✅

---

## Testing Strategy

### Unit Tests
- `test_step_manager.py`: Test step discovery, status tracking, workflow graph
- `test_tool_view_registry.py`: Test tool-to-view mapping
- `test_json_parameter_editor.py`: Test parameter editing
- `test_export_manager.py`: Test export workflows

### Integration Tests
- `test_output_view_library_loading.py`: Test `_load_from_library()` with real database
- `test_multi_pane_system.py`: Test adding/removing panes, focus management
- `test_reprocessing_workflow.py`: Test param edit → reprocess flow

### End-to-End Tests
- Process item → Load in OutputView → Edit param → Reprocess → Export
- Create collection → Process → View multiple outputs side-by-side
- Mobile platform: Test swipe navigation and single-pane layout

---

## Potential Challenges

### Challenge 1: WebView JavaScript ↔ Python Communication
**Problem**: WebView message handlers vary by platform (Toga WebKit vs WebView)

**Mitigation**:
- Abstract message handling in `WebViewMessageBridge` class
- Test on all platforms (macOS, Windows, Linux, iOS, Android)
- Fallback to simpler UI if messaging doesn't work

### Challenge 2: Dynamic Split Container Layout
**Problem**: Toga SplitContainer only supports 2 children; 3+ panes need nesting

**Mitigation**:
- Implement smart layout algorithm (horizontal then vertical)
- Consider OptionContainer (tabs) fallback for mobile
- Limit to 4 panes maximum to avoid complexity

### Challenge 3: Reprocessing Triggers Workflow Queue
**Problem**: Director may be processing other items; reprocessing needs priority

**Mitigation**:
- Add priority queue to Director (if not already present)
- Show queue position in UI
- Allow cancellation of reprocessing task

### Challenge 4: Export Destination (Cloud vs Local)
**Problem**: Users may want cloud storage (Dropbox, Google Drive) not just local export

**Mitigation**:
- Phase 1: Local export only
- Phase 2: Add cloud storage adapters (if requested)
- Use OS share sheet (platform-specific) for mobile

---

## Success Metrics

### Functional
- ✅ All existing tools display correctly in OutputView
- ✅ New 4 tools (describe_images, extract_library_metadata, analyze_document_groups, convert_to_svg) work in OutputView
- ✅ Users can view 2+ outputs side-by-side
- ✅ Users can edit JSON parameters and trigger reprocessing
- ✅ Users can export finished outputs (Word docs, images)
- ✅ Folder gallery view works for browsing images

### Performance
- Load 100-step workflow in <2 seconds
- Switch between panes with <100ms latency
- Reprocessing starts within 1 second of confirmation

### Code Quality
- 80%+ test coverage for new components
- No circular dependencies
- Clean separation: OutputView → ToolViewRegistry → Tool Views
- Documentation for each new class

---

## Next Steps

1. **Review and approve this plan** with stakeholders
2. **Set up project board** with tasks for each phase
3. **Start Phase 1, Task 1.1**: Implement `_load_from_library()` method
4. **Checkpoint after Phase 1**: Review progress, adjust timeline

**Estimated Total**: 11 weeks for full implementation, but phases can be released incrementally after Phase 1 completes.

