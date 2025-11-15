# Preview Focus System - Comprehensive Plan

## Current Problems Identified

### 1. ✗ Click-to-Focus Doesn't Work
**Issue:** User clicks on a pane, but focus doesn't change
**Root Cause:** Using `on_webview_load` which fires on page load, not on user clicks
**Current Code:** `output_pane.py:117` - `on_webview_load=self._handle_webview_interaction`
**Why It Fails:** WebView load event ≠ user click event

### 2. ✗ Navigation Goes to Wrong Pane
**Issue:** User selects an item, it loads in the wrong pane
**Root Cause:** Unclear - need to trace navigation flow
**Expected:** Should load into blue-bordered (focused) pane
**Actual:** Loads somewhere else

### 3. ✗ No Way to Manually Change Focus
**Issue:** No keyboard shortcut or UI element to change focus
**Current State:** Only programmatic focus changes (on split, on content load)
**Needed:** Cmd+Shift+] or similar to cycle between panes

### 4. ✗ No Central Focus Coordinator
**Issue:** Multiple components think they own focus state
**Current State:**
- MainWindow: Knows about columns (Library, Collection, Preview, Adjust)
- UniversalLayoutManager: Manages column focus (the light blue background)
- LayoutManager (preview): Manages pane focus (the dark blue border)
- PreviewView: Routes commands but doesn't coordinate focus

**Problem:** Who is the source of truth?

### 5. ✗ Commands Don't Route to Focused Pane
**Issue:** Edit/Zoom commands don't know which pane to operate on
**Current:** Commands are at PreviewView level, not pane-specific
**Needed:** Commands should route through focused pane

---

## Architecture Analysis

### Current Component Hierarchy

```
MainWindow
├── UniversalLayoutManager (5-column layout)
│   ├── Column: Library (LibraryView)
│   ├── Column: Collection (CollectionView + StepBrowserView)
│   ├── Column: Preview (PreviewView) ← WE ARE HERE
│   │   ├── Toolbars (shared across all panes)
│   │   ├── content_area
│   │   │   └── LayoutManager.get_container()
│   │   │       └── ColumnContainer[] (columns of panes)
│   │   │           └── OutputPane[] (individual panes)
│   │   │               ├── _outer_box (focus border)
│   │   │               └── _container
│   │   │                   ├── _webview (content)
│   │   │                   └── PathBar (per-pane)
│   │   └── StatusBar
│   └── Column: Adjust (AdjustView)
```

### Who Manages What?

| Component | Manages | Focus Indicator |
|-----------|---------|----------------|
| MainWindow | Window, columns, views | None |
| UniversalLayoutManager | Which column is active | Light blue background on column |
| PreviewView | Toolbars, commands, inspector | None |
| LayoutManager (preview) | Pane layout, split operations | Tracks focused_column/pane_index |
| OutputPane | Individual pane content | Dark blue border when focused |

### Focus State Flow (Current)

```
User Action → ? → LayoutManager._update_all_focus_indicators() → OutputPane.set_focused()
                                                                            ↓
                                                                   Dark blue border
```

**Missing:** The `?` - How does user action trigger focus change?

---

## Proposed Solution

### Option A: Keep LayoutManager as Focus Owner ✅ RECOMMENDED

**Rationale:**
- LayoutManager already tracks `focused_column_index` and `focused_pane_index`
- LayoutManager already has `_update_all_focus_indicators()`
- LayoutManager manages pane creation/destruction
- Minimal changes needed

**Changes Needed:**
1. Fix click detection on OutputPane
2. Add keyboard shortcut to cycle focus
3. Make PreviewView ask LayoutManager for focused pane
4. Route all commands through focused pane

### Option B: Move Focus to PreviewView

**Rationale:**
- PreviewView is higher level
- PreviewView handles commands
- PreviewView coordinates between components

**Changes Needed:**
- Move focus tracking from LayoutManager to PreviewView
- LayoutManager becomes just layout, not focus
- More refactoring

### Option C: Create PreviewPaneManager

**Rationale:**
- Separation of concerns
- Clear single responsibility

**Changes Needed:**
- New component
- Most refactoring
- Overkill for current needs

**DECISION: Go with Option A** - Enhance LayoutManager as focus coordinator

---

## Implementation Plan

### Phase 1: Fix Click-to-Focus (HIGH PRIORITY)

**Problem:** `on_webview_load` doesn't detect user clicks

**Solution Options:**

**A. Use WebView JavaScript injection** (Complex)
```python
# Inject JS to detect clicks and call Python
js_code = """
document.addEventListener('click', function(e) {
    window.webkit.messageHandlers.paneClicked.postMessage('click');
});
"""
```
**Pros:** Proper click detection
**Cons:** Complex, may not work reliably in Toga

**B. Add invisible Button overlay** (Hacky)
```python
# Transparent button over WebView
click_button = toga.Button(
    "",
    on_press=self._handle_click,
    style=Pack(flex=1, background_color='transparent')
)
```
**Pros:** Simple
**Cons:** May interfere with WebView interaction

**C. Use Box.on_click if available** (Ideal but may not exist)
```python
self._outer_box.on_click = self._handle_click
```
**Pros:** Clean
**Cons:** Toga Box may not have on_click

**D. Accept that content loading changes focus** (Pragmatic)
- When pane loads content, it gets focus
- Add keyboard shortcut for manual focus change
- This is actually reasonable UX

**RECOMMENDATION: Go with D + keyboard shortcut for now**

### Phase 2: Add Keyboard Shortcut to Cycle Focus (IMMEDIATE)

**Command:** `Cmd+Shift+]` to cycle forward, `Cmd+Shift+[` to cycle backward

**Implementation:**
```python
# In PreviewView.define_commands()
'cycle_focus_next': FicheroCommand(
    id='output.cycle_focus_next',
    label=_("Next Pane"),
    action=self._on_cycle_focus_next,
    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + ']',
    group=toga.Group.VIEW,
    section=30,
    order=20,
    desktop_only=True
),
```

**Handler:**
```python
def _on_cycle_focus_next(self, widget):
    self.layout_manager.cycle_focus(direction='next')
```

**LayoutManager method:**
```python
def cycle_focus(self, direction='next'):
    # Calculate next column/pane indices
    # Update focus
    # Call _update_all_focus_indicators()
```

### Phase 3: Ensure Navigation Routes to Focused Pane (CRITICAL)

**Current Flow:**
```
User clicks item in CollectionView
    ↓
NavigationEventBus: 'show_preview' event
    ↓
PreviewView._on_show_preview_event()
    ↓
PreviewView.load_output(item_id)
    ↓
PreviewView._load_output_async()
    ↓
StepManager.load_item(item_id)
    ↓
PreviewView._on_step_state_changed()
    ↓
layout_manager.get_focused_pane()  ← ALREADY FIXED
    ↓
pane.set_step(item_id, step_index)
```

**This should already work!** We changed line 885 in preview_view.py

**But we need to verify:**
1. Does get_focused_pane() return the correct pane?
2. Is the focused pane actually focused?
3. Are there multiple code paths that bypass this?

### Phase 4: Route All Commands to Focused Pane

**Commands that need routing:**
- Zoom in/out/fit/actual size
- Rotate left/right
- Flip horizontal/vertical
- Crop
- Reset
- Edit

**Current State:**
- Commands defined in PreviewView
- Handlers in PreviewView
- Need to route to focused pane

**Implementation:**
```python
# In PreviewView
def _on_zoom_in(self, widget):
    pane = self.layout_manager.get_focused_pane()
    if pane:
        pane.zoom_in()
    else:
        logger.warning("No focused pane to zoom")
```

### Phase 5: Update Toolbar States Based on Focused Pane

**Problem:** Toolbar buttons (Export, Edit) should enable/disable based on focused pane

**Implementation:**
- When focus changes, emit event
- PreviewView listens for focus change events
- Updates toolbar button states

---

## Quick Win: Keyboard Shortcut Implementation

**File:** `preview_view.py`

**Add to define_commands():**
```python
'cycle_focus_next': FicheroCommand(
    id='output.cycle_focus_next',
    label=_("Next Pane"),
    action=self._on_cycle_focus_next,
    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + ']',
    description=_("Focus next preview pane"),
    group=toga.Group.VIEW,
    parent='view.editor_layout',
    section=30,
    order=20,
    show_in_menu=True,
    desktop_only=True,
    context='normal'
),
'cycle_focus_prev': FicheroCommand(
    id='output.cycle_focus_prev',
    label=_("Previous Pane"),
    action=self._on_cycle_focus_prev,
    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '[',
    description=_("Focus previous preview pane"),
    group=toga.Group.VIEW,
    parent='view.editor_layout',
    section=30,
    order=21,
    show_in_menu=True,
    desktop_only=True,
    context='normal'
),
```

**Add handlers:**
```python
def _on_cycle_focus_next(self, widget):
    """Cycle focus to next pane"""
    self.layout_manager.cycle_focus(direction='next')

def _on_cycle_focus_prev(self, widget):
    """Cycle focus to previous pane"""
    self.layout_manager.cycle_focus(direction='prev')
```

**Add to LayoutManager:**
```python
def cycle_focus(self, direction='next'):
    """
    Cycle focus to next/previous pane

    Args:
        direction: 'next' or 'prev'
    """
    total_panes = sum(len(col.panes) for col in self.columns)

    if total_panes <= 1:
        return  # Nothing to cycle

    # Build flat list of (col_idx, pane_idx) tuples
    pane_positions = []
    for col_idx, column in enumerate(self.columns):
        for pane_idx in range(len(column.panes)):
            pane_positions.append((col_idx, pane_idx))

    # Find current position in flat list
    current_pos = pane_positions.index(
        (self.focused_column_index, self.focused_pane_index)
    )

    # Calculate next position
    if direction == 'next':
        next_pos = (current_pos + 1) % len(pane_positions)
    else:  # 'prev'
        next_pos = (current_pos - 1) % len(pane_positions)

    # Update focus
    self.focused_column_index, self.focused_pane_index = pane_positions[next_pos]
    self._update_all_focus_indicators()

    self.logger.info(f"🔄 Cycled focus to Column {self.focused_column_index + 1}, Pane {self.focused_pane_index + 1}")
```

---

## Testing Plan

### Test 1: Keyboard Focus Cycling
1. Split pane (Cmd+\)
2. Press Cmd+Shift+] - focus should move to next pane
3. Verify dark blue border moves
4. Verify status bar updates
5. Press Cmd+Shift+[ - focus should move back

### Test 2: Navigation Routing
1. Focus pane 1 (Cmd+Shift+[ if needed)
2. Click on item A in collection
3. Verify item A loads in pane 1
4. Focus pane 2 (Cmd+Shift+])
5. Click on item B in collection
6. Verify item B loads in pane 2
7. Verify item A still in pane 1

### Test 3: Command Routing
1. Focus pane 1
2. Press Cmd++ (zoom in)
3. Verify pane 1 zooms, pane 2 unchanged
4. Focus pane 2
5. Press Cmd++ (zoom in)
6. Verify pane 2 zooms, pane 1 unchanged

---

## Summary

**Immediate Actions (Today):**
1. ✅ Add keyboard shortcuts (Cmd+Shift+] and Cmd+Shift+[)
2. ✅ Implement cycle_focus() in LayoutManager
3. ✅ Test focus cycling works
4. ✅ Verify navigation routes to focused pane

**Follow-up (Later):**
1. Improve click-to-focus (if keyboard shortcut isn't enough)
2. Route zoom/rotate/edit commands to focused pane
3. Update toolbar states based on focused pane
4. Add visual indicator of which pane is focused (already have border)

**Decision:**
- Keep LayoutManager as focus coordinator
- Add keyboard shortcuts for manual focus change
- Accept that content loading changes focus (reasonable UX)
- Focus on making the system work reliably
