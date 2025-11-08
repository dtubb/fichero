# Phase 5 Multi-Pane System - Progress Report

## Completed Items ✅

### 1. Inspector Persistence (output_view.py:704-723)
**Problem:** Inspector panel was disappearing when switching between layouts
**Solution:** Modified `set_layout()` to remember inspector visibility state and restore it after layout changes

```python
async def set_layout(self, layout_type: LayoutType):
    # Remember if inspector was visible
    was_inspector_visible = self.inspector_visible

    # Hide inspector temporarily
    if was_inspector_visible:
        self._hide_inspector()

    # Change the layout
    self.layout_manager.set_layout(layout_type)

    # Re-show inspector if it was visible
    if was_inspector_visible:
        self._show_inspector()
```

### 2. Visual Focus Indicators (output_pane.py:607-623)
**Problem:** Users couldn't see which preview pane was selected/focused
**Solution:** Added `set_focused()` method to OutputPane that displays a blue border (VSCode-style)

```python
def set_focused(self, is_focused: bool):
    if is_focused:
        # Add blue border to indicate focus (like VSCode)
        self._container.style.background_color = '#007ACC'
        self._container.style.margin = 2  # 2px for border
    else:
        # Remove border
        self._container.style.background_color = None
        self._container.style.margin = 0
```

### 3. Focus State Management (layout_manager.py:443-468)
**Problem:** No tracking of which pane has focus
**Solution:**
- Updated `set_focused_pane()` to call `pane.set_focused()` on all panes
- Automatically set focus to pane 0 when creating layouts
- Emit `PANE_FOCUS_CHANGED` event for inspector integration

```python
def set_focused_pane(self, pane_index: int):
    if 0 <= pane_index < len(self.panes):
        # Update all panes to show/hide focus indicator
        for i, pane in enumerate(self.panes):
            pane.set_focused(i == pane_index)

        self.focused_pane_index = pane_index
        # Emit event for inspector to follow
        emit_navigation_event("PANE_FOCUS_CHANGED", {...})
```

## Current State

The system now supports:
- ✅ 9 different layout types (SINGLE, DUAL, DUAL_COMPARE, TRIPLE, QUAD, QUAD_SPLIT_H, QUAD_SPLIT_V, TRIPLE_SPLIT_H, TRIPLE_SPLIT_V)
- ✅ Visual focus indicators (blue border on focused pane)
- ✅ Inspector panel persistence across layout changes
- ✅ Focus tracking with event emission
- ✅ Menu commands to switch layouts (View menu)

## Outstanding Issues & Next Steps

### Dynamic Pane Splitting (User's Priority)

**User Feedback:**
> "maybe its simplest to let us vertical split once, or once on an individual pane, and, horizontal split. that way we could have 1 pane tall, another pane tall, then two panes vertical"

**What this means:**
- Instead of fixed layouts (1/2/3/4 panes), user wants VSCode-style dynamic splitting
- Start with 1 pane
- Split focused pane horizontally OR vertically
- Build custom layouts organically

**Current Architecture Limitation:**
The current `LayoutManager` uses **preset layouts** defined in `set_layout()`. Each layout type creates a fixed arrangement of panes:
- `_create_single_layout()` → 1 pane
- `_create_dual_compare_layout()` → 2 panes side-by-side
- `_create_quad_split_h_layout()` → 2x2 grid
- etc.

**What needs to change:**
1. **Replace fixed layouts with dynamic splitting**
   - Remove preset layout methods
   - Implement `split_pane_horizontal(pane_index)` and `split_pane_vertical(pane_index)`
   - Split the focused pane's container, creating a new pane alongside it

2. **New container structure**
   - Current: Single `_container` Box with direction set at creation
   - Needed: Nested Box hierarchy that can grow dynamically
   - Each split creates a new Box parent containing [old_pane, new_pane]

3. **Pane tracking changes**
   - Current: Flat `self.panes` list
   - Needed: Either keep flat list OR track pane hierarchy for proper splitting/closing

4. **Menu command changes**
   - Remove: "Single Pane", "Dual Compare", etc. (fixed layouts)
   - Add: "Split Vertical", "Split Horizontal", "Close Pane"
   - Commands operate on currently focused pane

### Collection View Integration (Deferred)

**User Feedback:**
> "I can't change it via the collection view"

**Current Behavior:**
- Clicking an item in CollectionView always loads it in OutputView
- OutputView always uses primary pane (pane 0)

**Desired Behavior:**
- Clicking an item should load it in the **focused** pane
- Allows side-by-side comparison by clicking different items

**Blockers:**
- CollectionView doesn't have reference to LayoutManager
- Would need to pass focused pane info through navigation events
- Makes more sense to implement AFTER dynamic splitting is working

### Testing Checklist

Once dynamic splitting is implemented:
- [ ] Test split horizontal creates 2 panes side-by-side
- [ ] Test split vertical creates 2 panes top/bottom
- [ ] Test focus indicator moves correctly between panes
- [ ] Test inspector stays visible when splitting
- [ ] Test can build complex layouts (e.g., 1 tall left, 2 vertical right)
- [ ] Test close pane removes correct pane and adjusts layout
- [ ] Test keyboard shortcuts for split/close
- [ ] Test with collection view item loading
- [ ] Test on mobile (should disable/hide split controls)

## Files Modified

1. `src/fichero/windows/main/views/output/output_view.py`
   - Added inspector preservation in `set_layout()` (lines 704-723)

2. `src/fichero/windows/main/views/output/output_pane.py`
   - Added `set_focused()` method for visual focus indicator (lines 607-623)

3. `src/fichero/windows/main/views/output/layout_manager.py`
   - Updated `set_focused_pane()` to update all panes' focus state (lines 443-468)
   - Added initial focus setting in `set_layout()` (lines 137-139)

## Architecture Considerations for Dynamic Splitting

### Approach 1: Nested Box Hierarchy (Recommended)
```
Root Container (ROW)
├── Pane 1
└── Split Container (COLUMN)
    ├── Pane 2
    └── Pane 3
```

**Pros:**
- Natural nesting matches visual layout
- Easy to find parent container when splitting
- Mirrors VSCode/Emacs split architecture

**Cons:**
- More complex to track pane positions
- Closing panes requires container cleanup

### Approach 2: Flat Pane List with Metadata (Simpler)
```
panes = [
    (pane1, parent_container, index),
    (pane2, parent_container, index),
    (pane3, parent_container, index)
]
```

**Pros:**
- Simpler pane tracking
- Focus index still works with flat list
- Easier to iterate all panes

**Cons:**
- Need to track parent containers separately
- More bookkeeping when splitting/closing

### Recommended Implementation Plan

1. **Start simple:** Implement split_pane_horizontal/vertical that rebuilds entire layout
   - Similar to current `set_layout()` approach
   - Clear all panes, rebuild with new structure
   - Preserve content by storing (item_id, step_index) before rebuild

2. **Add incremental improvements:**
   - Track parent containers to avoid full rebuild
   - Implement proper nested Box hierarchy
   - Add pane closing with container cleanup

3. **Polish:**
   - Add keyboard shortcuts (Cmd+\\ for split, Cmd+W for close)
   - Add split buttons to pane toolbars
   - Add animations/transitions

## Next Session TODO

1. Decide on architecture approach (nested vs flat)
2. Implement `split_pane_horizontal()` and `split_pane_vertical()`
3. Update View menu commands to use split instead of fixed layouts
4. Test with existing content loading
5. Commit and test with user

---

*Generated during Phase 5 implementation - 2025-01-08*
