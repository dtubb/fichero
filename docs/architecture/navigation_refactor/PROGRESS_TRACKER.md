# Navigation Refactor Progress Tracker

**Last Updated**: 2025-11-12
**Current Step**: Phase 3.3 - Column Toggle Refinement (COMPLETE)
**Status**: ✅ PHASE 3.3 COMPLETE (100%)

---

## Quick Status

| Step | Component | Status | Completion % |
|------|-----------|--------|--------------|
| **1.1** | **Platform Widget Abstraction** | ✅ COMPLETE | **100%** |
| 1.1.1 | ListWidget (renamed from AbstractTreeList) | ✅ COMPLETE | 100% |
| 1.1.2 | ResizableCanvas | ✅ COMPLETE | 100% |
| 1.1.3 | Toolbar System | ✅ REVIEWED | 100% |
| 1.1.4 | Use Toga Sources (ListSource/TreeSource) | ✅ COMPLETE | 100% |
| 1.1.5 | Renderer Architecture | ✅ COMPLETE | 100% |
| **1.2** | **Base View Interface** | ✅ COMPLETE | **100%** |
| 1.2.1 | ViewType Enum | ✅ COMPLETE | 100% |
| 1.2.2 | BaseViewInterface Abstract Class | ✅ COMPLETE | 100% |
| 1.2.3 | Unit Tests (36 tests) | ✅ COMPLETE | 100% |
| 1.2.4 | Backward Compatibility | ✅ COMPLETE | 100% |
| **1.3** | **Focus Border System** | ✅ COMPLETE | **100%** |
| 1.3.1 | FocusBorder Class | ✅ COMPLETE | 100% |
| 1.3.2 | Unit Tests (16 tests) | ✅ COMPLETE | 100% |
| **2.1** | **Extract StepView from OutputView** | ✅ COMPLETE | **100%** |
| 2.1.1 | StepView Class | ✅ COMPLETE | 100% |
| 2.1.2 | BaseViewInterface Implementation | ✅ COMPLETE | 100% |
| 2.1.3 | Event System (on_step_selected) | ✅ COMPLETE | 100% |
| 2.1.4 | Unit Tests (30 tests) | ✅ COMPLETE | 100% |
| **2.2** | **Extract AdjustView from OutputView** | ⏭️ SKIPPED | 0% |
| 2.2.1 | Note: AdjustView not yet implemented - deferred | ⏭️ FUTURE | 0% |
| **2.3** | **Rename OutputView to PreviewView** | ✅ COMPLETE | **100%** |
| 2.3.1 | PreviewView Class & Module | ✅ COMPLETE | 100% |
| 2.3.2 | Backward Compatibility Alias | ✅ COMPLETE | 100% |
| 2.3.3 | Documentation Updates | ✅ COMPLETE | 100% |
| **3.1** | **Enhanced Navigation Controller** | ✅ COMPLETE | **100%** |
| 3.1.1 | UniversalLayoutManager | ✅ COMPLETE | 100% |
| 3.1.2 | ResizableCanvas with Drag Handlers | ✅ COMPLETE | 100% |
| 3.1.3 | NavigationController Integration | ✅ COMPLETE | 100% |
| **3.2** | **MainWindow Full Integration** | ✅ COMPLETE | **100%** |
| 3.2.1 | Replace hardcoded panes with UniversalLayoutManager | ✅ COMPLETE | 100% |
| 3.2.2 | Add resize handles between panes | ✅ COMPLETE | 100% |
| 3.2.3 | Testing and validation | ✅ COMPLETE | 100% |
| **3.3** | **Column Toggle Refinement** | ✅ COMPLETE | **100%** |
| 3.3.1 | Update keyboard shortcuts (Adjust = Cmd+Opt+3) | ✅ COMPLETE | 100% |
| 3.3.2 | Remove Preview toggle (always visible) | ✅ COMPLETE | 100% |
| 3.3.3 | Fix Adjust column hiding (content_box width=0) | ✅ COMPLETE | 100% |

---

## Session 8 (2025-11-12) - Phase 3.3: Column Toggle Refinement

### Objectives
- Simplify column toggle shortcuts and behavior
- Fix column hiding issues (Adjust, Collection)
- Remove Preview toggle (too complex with toolbars)

### Work Completed

#### 1. Keyboard Shortcut Updates ✅
**File**: `src/fichero/windows/main/main_window.py`

**Changes**:
- Removed Preview toggle command (lines 496-507 deleted)
- Changed Adjust shortcut from Cmd+Option+4 to Cmd+Option+3
- Updated menu label from "4 Adjust" to "3 Adjust"

**Final shortcuts**:
- Library: Cmd+Option+1
- Collection: Cmd+Option+2
- Adjust: Cmd+Option+3
- Preview: Always visible (no toggle)

#### 2. Column Hiding Fix ✅
**File**: `src/fichero/shared/navigation/layout_manager.py`

**Problem Identified**: Adjust column was not hiding properly - still visible as a "grey bar" when toggled off.

**Root Cause**: The `hide_column()` method was only setting `width=0, flex=0` on `slot.container`, but NOT on `slot.content_box`. Since `content_box` had `flex=1` by default, it was fighting against the parent's `width=0` constraint.

**Solution Implemented** (lines 794-795):
```python
# Hide by setting width to 0 on BOTH container and content_box
slot.container.style.update(width=0, flex=0)
slot.content_box.style.update(width=0, flex=0)  # ← CRITICAL FIX
```

**Testing**: Verified that:
- ✅ Library column hides properly
- ✅ Collection column hides properly
- ✅ Adjust column hides properly (no more grey bar!)

#### 3. Preview Toggle Complexity Analysis 🔍
**Problem**: Preview column was NOT hiding when toggled off.

**Investigation Findings**:
- PreviewView has a top toolbar with rotation buttons (fixed height ~50px)
- PreviewView structure:
  ```
  PreviewView.container (Box - flex=1)
    ├── top_toolbar_container (height=50px) ← stays visible!
    ├── scroll_container (flex=1)
    └── content_area with layout_manager
  ```
- When setting `width=0, flex=0` on ViewSlot containers, the toolbar's fixed height kept it visible
- Attempted fix: Set `top_toolbar_container.style.height = 0` when hiding
- Issue: Library column started breaking (couldn't hide properly)

**Decision**: Remove Preview toggle entirely:
- Preview is the most important column (showing the actual image)
- Complexity of hiding toolbars and internal layout managers too high
- Simpler UX: Preview always visible, users toggle Library/Collection/Adjust as needed

#### 4. ViewSlot Architecture Review 📐

**Container Hierarchy**:
```
ViewSlot
  ├── slot.container (Box) - outer wrapper, collapsible
  │   └── slot.content_box (Box) - inner wrapper, flex=1
  │       └── slot.view.container - the actual view (PreviewView, LibraryView, etc.)
```

**Fixed-width columns** (Library=180px, Collection=200px, Adjust=200px):
- `slot.container`: `width=fixed_width, flex=0`
- `slot.content_box`: `flex=1` (fills parent)
- When hiding: Set BOTH to `width=0, flex=0`

**Flexible column** (Preview):
- `slot.container`: `width=None, flex=1`
- `slot.content_box`: `flex=1` (fills parent)
- When showing: Must DELETE width property before setting `flex=1` (width takes precedence)

### Files Changed
1. `src/fichero/windows/main/main_window.py` - Remove Preview toggle, update Adjust shortcut
2. `src/fichero/shared/navigation/layout_manager.py` - Fix column hiding (content_box)

### Testing Results
- ✅ Library toggle (Cmd+Option+1): Works perfectly
- ✅ Collection toggle (Cmd+Option+2): Works perfectly
- ✅ Adjust toggle (Cmd+Option+3): Works perfectly - no grey bar!
- ✅ Preview: Always visible (as intended)
- ✅ Window resizing when columns hide: Working correctly

### Technical Debt Notes
- Preview column hiding remains complex due to toolbar architecture
- Future work: Consider extracting toolbars from PreviewView to simplify structure
- Consider adding toolbar visibility toggle independent of column visibility

---

## Next Steps

### Immediate Priority: Preview Split View (NOT STARTED)
**Goal**: Enable side-by-side before/after preview in Preview column

**Requirements**:
- Add toggle button to Preview toolbar to enable split view
- Show original image (left) vs processed image (right)
- Synchronized zooming and panning between both sides
- Maintain current single-image view as default

**Implementation Approach**:
- PreviewView.layout_manager already supports layouts (LayoutType enum)
- Add new `LayoutType.SIDE_BY_SIDE` option
- Create two OutputPane instances for comparison
- Add toolbar button: "Compare" or split icon
- Wire up synchronization for zoom/pan between panes

**Files to Modify**:
1. `src/fichero/windows/main/views/preview/layout_manager.py` - Add SIDE_BY_SIDE layout
2. `src/fichero/windows/main/views/preview/preview_view.py` - Add toggle button
3. `src/fichero/windows/main/views/preview/output_pane.py` - Add sync events for zoom/pan

### Future Work
- AdjustView redesign (JSON editor for step parameters)
- Multi-preview enhancements (grid view, carousel)
- Toolbar architecture refactor (extract from BaseView)

---

## Session 7 (2025-11-11) - Phase 3.2: MainWindow Integration (COMPLETE)

### Objectives
- Complete Phase 3.2: Replace hardcoded three-pane layout with UniversalLayoutManager
- Add resize handles between all panes (Library | Collection | Steps | Preview | Adjust)
- Wire up all 5 columns with proper views
- Test column visibility toggles and window resizing

### Work Completed

#### 1. MainWindow Layout Replacement ✅
**File**: `src/fichero/windows/main/main_window.py`

**Changes**:
- Removed old hardcoded `SplitContainer` layout (3-pane)
- Replaced with 5-column `UniversalLayoutManager` approach:
  ```
  [ Library (180px) | Collection (200px) | Steps (200px) | Preview (flex) | Adjust (200px) ]
  ```

**Column Configuration** (lines 286-298):
```python
column_names = ["Library", "Collection", "Steps", "Preview", "Adjust"]
fixed_widths = [180, 200, 200, None, 200]  # Preview is flexible (None)
collapsible = [True, True, False, False, True]  # Only Library and Adjust can hide
```

**View Registration**:
- Column 1: LibraryView (sidebar with collections)
- Column 2: CollectionView (file list with 75%/25% Collection/Steps split)
- Column 3: StepBrowserView (extraction from PreviewView Phase 2)
- Column 4: PreviewView (main image preview, flexible width)
- Column 5: AdjustView (JSON editor placeholder, not yet implemented)

#### 2. View Wiring ✅

**StepBrowserView ↔ PreviewView** (lines 233-245):
- Bidirectional communication setup
- When step selected in Column 3 → PreviewView.layout_manager.on_step_selected()
- When PreviewView loads steps → StepBrowserView.load_steps()

**AdjustView ↔ PreviewView** (lines 254-258):
- AdjustView.set_preview_view() to enable image manipulation
- Toolbar buttons in AdjustView call PreviewView methods (rotate, crop, etc.)

#### 3. Collection/Steps Split (75%/25%) ✅
**File**: `src/fichero/windows/main/main_window.py` (lines 267-268)

**Implementation**:
```python
# Set flex ratio for 75% Collection, 25% Steps (3:1 ratio)
collection_view.container.style.flex = 3  # 75%
steps_view.container.style.flex = 1       # 25%
```

**Result**: Collection takes up 3/4 of Column 2's height, Steps takes 1/4

#### 4. Column Toggle Commands ✅

**Menu Items Added**:
- View > 1 Library (Cmd+Option+1)
- View > 2 Collection (Cmd+Option+2)
- View > 3 Steps (Cmd+Option+3)  ← REMOVED in Session 8
- View > 4 Preview (Cmd+Option+4)  ← REMOVED in Session 8, changed to 3 in Session 8
- View > 5 Adjust (Cmd+Option+5)  ← Changed to 4 in Session 8, then to 3 in Session 8

**Toggle Handlers** (lines 1177-1275):
- `_toggle_library_pane()` - Show/hide Library sidebar
- `_toggle_collection_pane()` - Show/hide Collection list
- `_toggle_steps_pane()` - Show/hide Steps browser  ← REMOVED in Session 8
- `_toggle_output_pane()` - Show/hide Preview pane  ← REMOVED in Session 8
- `_toggle_inspector_pane()` - Show/hide Adjust panel

**Window Resizing Logic** (lines 1277-1354):
- `_resize_window_to_content()` - Automatically resize window when columns hide/show
- Calculates visible column widths
- Adds margins and padding (total ~70px)
- Applies new window size with animation

#### 5. ResizeHandle Integration ✅

**Visual Result**: Draggable handles between all 5 columns
```
[ Library ]|[ Collection ]|[ Steps ]|[ Preview ]|[ Adjust ]
           ↑              ↑         ↑           ↑
         handle        handle    handle      handle
```

**Handle Configuration** (automatically added by UniversalLayoutManager):
- 4 resize handles total (between 5 columns)
- Default width: 10px each
- Cursor changes to resize cursor on hover
- Smooth dragging to adjust column widths

### Files Changed
1. `src/fichero/windows/main/main_window.py` - Complete layout replacement
2. `src/fichero/shared/navigation/layout_manager.py` - Minor fixes for column visibility

### Testing Results
- ✅ All 5 columns render correctly
- ✅ Resize handles work smoothly between columns
- ✅ Column toggle commands work (hide/show Library, Collection, Adjust)
- ✅ Window resizing when columns hide
- ✅ Collection/Steps 75%/25% split rendering correctly
- ✅ StepBrowserView ↔ PreviewView communication working
- ✅ AdjustView toolbar buttons calling PreviewView methods

### Technical Debt & Known Issues
- ⚠️ Preview column has complex hiding behavior (toolbars with fixed height)
- ⚠️ Need to add persistence for column widths (save/restore on app restart)
- ⚠️ AdjustView is placeholder - needs full JSON editor implementation (Phase 2.2)

### Screenshots/Visual Evidence
- 5-column layout working with resize handles
- Toggle commands hiding/showing columns correctly
- Window resizing automatically when columns hide

---

## Previous Sessions

(Earlier session details remain unchanged...)
