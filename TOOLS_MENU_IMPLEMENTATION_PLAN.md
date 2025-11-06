# Tools Menu Implementation Plan

## Overview

Create a comprehensive Tools menu that provides access to all tool operations, navigation, and adjustments.

## Menu Structure

```
Tools
├── Adjust ▸
│   ├── Adjust Crop...
│   ├── Adjust Rotate...
│   ├── Adjust Enhance...
│   ├── Adjust Background Removal...
│   ├── Adjust Image Preparation...
│   ├── Adjust Split...
│   ├── Adjust Segmentation...
│   └── Adjust Recombination...
│
├── Go To ▸
│   ├── Original Image
│   ├── ──────────────
│   ├── Crop Output
│   ├── Rotate Output
│   ├── Enhance Output
│   ├── Background Removal Output
│   ├── Prepare Output
│   ├── Split Output
│   ├── Segment Output
│   ├── Recombine Output
│   ├── ──────────────
│   ├── Transcription Output
│   ├── Description Output
│   ├── LLM Processing Output
│   ├── ──────────────
│   ├── Word Document
│   ├── SVG Output
│   └── Excel Output
│
└── Process ▸
    ├── Crop Image...
    ├── Rotate Image...
    ├── Enhance Image...
    ├── Remove Background...
    ├── Prepare Images...
    ├── ──────────────
    ├── Split Pages...
    ├── Segment Regions...
    ├── Recombine Segments...
    ├── ──────────────
    ├── Transcribe (Qwen Max)...
    ├── Transcribe (LM Studio)...
    ├── Describe Image...
    ├── LLM Process...
    ├── ──────────────
    ├── Convert to Word...
    ├── Convert to SVG...
    ├── JSON to Word...
    └── JSON to Excel...
```

## Implementation Architecture

### 1. Menu Registration System

**File**: `src/fichero/windows/main/views/output/tools_menu_manager.py`

```python
class ToolsMenuManager:
    """Manages the Tools menu for OutputView"""

    def __init__(self, output_view, renderer_registry):
        self.output_view = output_view
        self.renderer_registry = renderer_registry
        self.tools_menu = None

    def build_menu(self) -> toga.Menu:
        """Build the complete Tools menu"""
        return toga.Menu(
            'Tools',
            toga.MenuItem('Adjust', submenu=self._build_adjust_menu()),
            toga.MenuItem('Go To', submenu=self._build_goto_menu()),
            toga.MenuItem('Process', submenu=self._build_process_menu()),
        )

    def _build_adjust_menu(self):
        """Build Adjust submenu"""
        # Dynamically build from registered renderers
        items = []
        for tool_name in self.renderer_registry.list_registered_tools():
            renderer = self.renderer_registry.get_renderer(tool_name)
            if renderer and hasattr(renderer, 'get_editable_json'):
                items.append(toga.MenuItem(
                    f'Adjust {self._format_tool_name(tool_name)}...',
                    action=lambda widget, tool=tool_name: self._on_adjust(tool)
                ))
        return items

    def _build_goto_menu(self):
        """Build Go To submenu"""
        # Build from current item's processing steps
        items = [toga.MenuItem('Original Image', action=self._goto_original)]

        if self.output_view.step_manager.steps:
            items.append(toga.MenuItem.separator())
            for step in self.output_view.step_manager.steps:
                items.append(toga.MenuItem(
                    f'{step.step_name} Output',
                    action=lambda w, s=step: self._goto_step(s)
                ))

        return items

    def _build_process_menu(self):
        """Build Process submenu"""
        # All available tools organized by category
        return [
            # Image processing
            toga.MenuItem('Crop Image...', action=self._process_crop),
            toga.MenuItem('Rotate Image...', action=self._process_rotate),
            toga.MenuItem('Enhance Image...', action=self._process_enhance),
            # ... more items
        ]
```

### 2. Adjust Menu - Opens Inspector with JSON Editor

**Behavior**:
- Menu: `Tools > Adjust > Adjust Crop...`
- Action: Opens inspector panel with crop parameters
- Same as clicking "Adjust" button in toolbar

**Implementation**:

```python
def _on_adjust(self, tool_name: str):
    """
    Open inspector panel for adjusting tool parameters.

    Args:
        tool_name: Name of tool to adjust (e.g., 'crop', 'rotate')
    """
    # Get current step
    state = self.output_view.step_manager.get_state()

    # Find step with matching tool
    for step in self.output_view.step_manager.steps:
        if step.tool_name == tool_name:
            # Navigate to this step
            self.output_view.step_manager.set_current_step(step.step_index)

            # Show inspector with parameters
            self.output_view._show_inspector()
            break
    else:
        # Tool not found in current workflow
        self.output_view.app.main_window.info_dialog(
            'Tool Not Found',
            f'The current item does not have a {tool_name} step.'
        )
```

### 3. Go To Menu - Navigation to Outputs

**Behavior**:
- Menu: `Tools > Go To > Crop Output`
- Action: Navigates to that step in OutputView
- Updates StepBrowser selection

**Implementation**:

```python
def _goto_step(self, step):
    """
    Navigate to a specific processing step.

    Args:
        step: Step object to navigate to
    """
    # Set current step
    self.output_view.step_manager.set_current_step(step.step_index)

    # Update step browser selection
    self.output_view.step_browser.select_step(step.step_index)

    # Scroll to step in browser
    self.output_view.step_browser.scroll_to_step(step.step_index)

def _goto_original(self, widget):
    """Navigate to original image (step 0)"""
    self.output_view.step_manager.set_current_step(0)
    self.output_view.step_browser.select_step(0)
```

### 4. Process Menu - Run Tool on Current Item

**Behavior**:
- Menu: `Tools > Process > Rotate Image...`
- Action: Opens dialog to configure and run tool
- Processes current item with selected tool

**Implementation**:

```python
def _process_rotate(self, widget):
    """
    Open dialog to process current item with rotate tool.
    """
    # Get current item
    state = self.output_view.step_manager.get_state()
    if not state.item_id:
        self.output_view.app.main_window.info_dialog(
            'No Item Selected',
            'Please select an item to process.'
        )
        return

    # Show process dialog
    dialog = RotateProcessDialog(
        current_item=state.item_id,
        on_complete=self._on_process_complete
    )
    dialog.show()

def _on_process_complete(self, result):
    """
    Handle completion of processing.

    Args:
        result: Processing result with new step information
    """
    # Refresh output view to show new step
    self.output_view.refresh()

    # Navigate to new step
    if result.step_index is not None:
        self.output_view.step_manager.set_current_step(result.step_index)
```

## Menu Item States (Enable/Disable)

### Adjust Menu Items
- **Enabled**: When viewing a step that uses this tool
- **Disabled**: When current step doesn't match tool

```python
def update_adjust_menu_states(self):
    """Update enabled/disabled state of Adjust menu items"""
    current_step = self.output_view.step_manager.get_current_step()

    for menu_item in self.adjust_menu_items:
        tool_name = menu_item.tool_name
        # Enable if current step uses this tool
        menu_item.enabled = (current_step and
                            current_step.tool_name == tool_name)
```

### Go To Menu Items
- **Enabled**: Always (if steps exist)
- **Checkmark**: On currently selected step

```python
def update_goto_menu_states(self):
    """Update checkmarks on Go To menu items"""
    current_index = self.output_view.step_manager.get_state().step_index

    for i, menu_item in enumerate(self.goto_menu_items):
        # Add checkmark to current step
        menu_item.checked = (i == current_index)
```

### Process Menu Items
- **Enabled**: When an item is selected
- **Disabled**: When no item selected

```python
def update_process_menu_states(self):
    """Update enabled/disabled state of Process menu items"""
    has_item = bool(self.output_view.step_manager.get_state().item_id)

    for menu_item in self.process_menu_items:
        menu_item.enabled = has_item
```

## Renderer Integration

Each renderer can define custom menu items:

```python
class CropRenderer(ImageRenderer):
    def get_menu_items(self, context: RenderContext) -> List[MenuItem]:
        """Get custom menu items for crop tool"""
        return [
            MenuItem(
                id='adjust_crop',
                label='Adjust Crop...',
                section='adjust',
                shortcut='Cmd+Shift+C',
                action=self._adjust_crop
            ),
            MenuItem(
                id='recrop',
                label='Re-crop with New Settings',
                section='process',
                action=self._recrop
            ),
            MenuItem(
                id='reset_crop',
                label='Reset to Original',
                section='adjust',
                action=self._reset_crop
            ),
        ]
```

## Keyboard Shortcuts

```python
TOOL_SHORTCUTS = {
    # Adjust shortcuts (Cmd+Shift+Letter)
    'crop': 'Cmd+Shift+C',
    'rotate': 'Cmd+Shift+R',
    'enhance': 'Cmd+Shift+E',
    'remove_background': 'Cmd+Shift+B',

    # Navigation shortcuts (Cmd+Number)
    'goto_original': 'Cmd+0',
    'goto_step_1': 'Cmd+1',
    'goto_step_2': 'Cmd+2',
    'goto_step_3': 'Cmd+3',
    # ... up to Cmd+9

    # Process shortcuts (Cmd+Option+Letter)
    'process_crop': 'Cmd+Option+C',
    'process_rotate': 'Cmd+Option+R',
    'process_enhance': 'Cmd+Option+E',
}
```

## Implementation Steps

### Phase 1: Menu Structure (1-2 hours)
1. ✅ Create `ToolsMenuManager` class
2. ✅ Implement `build_menu()` with three submenus
3. ✅ Register menu in OutputView
4. ✅ Test menu appears in app

### Phase 2: Adjust Menu (2-3 hours)
1. ✅ Implement `_build_adjust_menu()` from registry
2. ✅ Wire up `_on_adjust()` to inspector panel
3. ✅ Add enable/disable logic based on current step
4. ✅ Test with crop and rotate

### Phase 3: Go To Menu (1-2 hours)
1. ✅ Implement `_build_goto_menu()` from steps
2. ✅ Wire up navigation to `_goto_step()`
3. ✅ Add checkmarks for current step
4. ✅ Test step navigation

### Phase 4: Process Menu (3-4 hours)
1. ✅ Implement `_build_process_menu()` with all tools
2. ✅ Create process dialogs for each tool
3. ✅ Wire up tool execution
4. ✅ Test processing workflow

### Phase 5: Keyboard Shortcuts (1-2 hours)
1. ✅ Add shortcut registration
2. ✅ Implement shortcut handlers
3. ✅ Show shortcuts in menu labels
4. ✅ Test all shortcuts work

### Phase 6: Menu State Management (2-3 hours)
1. ✅ Implement menu update on step change
2. ✅ Add enable/disable logic
3. ✅ Add checkmark logic
4. ✅ Test state updates correctly

## File Structure

```
src/fichero/windows/main/views/output/
├── output_view.py                  # Main view, registers menu
├── tools_menu_manager.py           # NEW: Menu management
├── process_dialogs/                # NEW: Process dialogs
│   ├── __init__.py
│   ├── crop_dialog.py
│   ├── rotate_dialog.py
│   ├── enhance_dialog.py
│   └── ... (one per tool)
└── ...
```

## Menu Behavior Details

### Adjust Menu Behavior

**When item clicked:**
1. Check if current item has this tool step
2. If yes: Navigate to that step + open inspector
3. If no: Show dialog "This item was not processed with [tool]"

**Visual feedback:**
- Enabled: When step exists
- Disabled: When step doesn't exist
- Current step's tool is **bolded**

### Go To Menu Behavior

**When item clicked:**
1. Set current step to selected step
2. Update OutputPane to show step output
3. Update StepBrowser selection
4. Scroll StepBrowser to show step

**Visual feedback:**
- Checkmark (✓) on current step
- All items always enabled (if steps exist)

### Process Menu Behavior

**When item clicked:**
1. Show process dialog with tool parameters
2. User configures parameters
3. On OK: Run tool on current item
4. On Complete: Refresh view, show new step

**Visual feedback:**
- Enabled: When item is selected
- Disabled: When no item selected

## Dynamic Menu Building

The Adjust and Go To menus are built dynamically:

```python
def rebuild_menus(self):
    """Rebuild dynamic menus based on current state"""

    # Rebuild Adjust menu from registered renderers
    self._rebuild_adjust_menu()

    # Rebuild Go To menu from current steps
    self._rebuild_goto_menu()

    # Update menu states
    self.update_menu_states()

# Called when:
# - Item changes
# - Step changes
# - Processing completes
# - Renderer registry updates
```

## Testing Plan

### Test 1: Menu Appears
- ✅ Launch app
- ✅ Navigate to OutputView
- ✅ Verify "Tools" menu in menubar
- ✅ Verify submenus: Adjust, Go To, Process

### Test 2: Adjust Menu
- ✅ Load item with crop step
- ✅ Click Tools > Adjust > Adjust Crop...
- ✅ Verify inspector opens with crop JSON
- ✅ Try adjusting parameters
- ✅ Verify changes saved

### Test 3: Go To Menu
- ✅ Load item with multiple steps
- ✅ Click Tools > Go To > [step name]
- ✅ Verify navigation to step
- ✅ Verify checkmark on current step
- ✅ Try all steps

### Test 4: Process Menu
- ✅ Select an item
- ✅ Click Tools > Process > Rotate Image...
- ✅ Verify dialog appears
- ✅ Configure and run
- ✅ Verify new step appears

### Test 5: Menu States
- ✅ Select item without crop
- ✅ Verify Adjust Crop is disabled
- ✅ Select item with crop
- ✅ Verify Adjust Crop is enabled
- ✅ Verify checkmark on current step

### Test 6: Keyboard Shortcuts
- ✅ Press Cmd+Shift+C
- ✅ Verify Adjust Crop activates
- ✅ Press Cmd+1
- ✅ Verify navigation to step 1
- ✅ Test all shortcuts

## Benefits

✅ **Discoverability**: Users can find all tool operations in one menu
✅ **Consistency**: Same pattern for all tools (Adjust/Go To/Process)
✅ **Efficiency**: Keyboard shortcuts for power users
✅ **Context**: Menu items enable/disable based on state
✅ **Extensibility**: New tools automatically appear in menus

## Next Steps

1. Implement ToolsMenuManager
2. Wire up to OutputView
3. Test with existing renderers (crop, rotate)
4. Add process dialogs
5. Add keyboard shortcuts
6. Test thoroughly
7. Roll out to all 20 tools!
