# OutputView Callback Flow Audit

## Callback Architecture

### Core Components
1. **StepManager** - Manages step state and navigation
2. **StepBrowser** - UI component showing list of steps
3. **OutputPane** - Displays step content
4. **OutputView** - Coordinates all components

### Event Flow Design

**Single Source of Truth**: All step changes go through `StepManager.set_current_step()` which emits a state change event.

**Event Propagation**:
```
User Action → set_current_step() → _emit_state_change() → _on_step_state_changed() → Update UI + Load Pane
```

## Callback Chains

### 1. Initial Load (`_load_output_async`)
```
_load_output_async()
  → step_browser.load_steps(steps, current_index)
      → _on_step_selected(current_index)  [triggered by step_browser]
          → _on_step_browser_selected(index)  [output_view callback]
              → step_manager.set_current_step(index)
                  → _emit_state_change()  [with recursion guard]
                      → _on_step_state_changed(state)
                          → _update_ui_from_state()
                          → pane.set_step(...)
```

**FIXED**: Removed duplicate `set_current_step()`, `pane.set_step()`, and `_update_ui_from_state()` calls from `_load_output_async()` since `step_browser.load_steps()` triggers the full chain.

### 2. Step Browser Click
```
User clicks step in browser
  → DetailedList on_select event
      → step_browser._on_step_selected(widget)
          → _on_step_browser_selected(index)  [output_view callback]
              → step_manager.set_current_step(index)
                  → _emit_state_change()
                      → _on_step_state_changed(state)
                          → _update_ui_from_state()
                          → pane.set_step(...)
```

**FIXED**: Removed duplicate `pane.set_step()` and `_update_ui_from_state()` calls from `_on_step_browser_selected()`.

### 3. Step Dropdown Change
```
User selects from dropdown
  → Selection on_change event
      → _on_step_selected(widget)
          → step_manager.set_current_step(index)
              → _emit_state_change()
                  → _on_step_state_changed(state)
                      → _update_ui_from_state()
                      → pane.set_step(...)
```

**CORRECT**: Only calls `set_current_step()`, lets state change handle the rest.

### 4. Prev/Next Step Buttons
```
User clicks prev/next
  → _on_prev_step() or _on_next_step()
      → step_manager.prev_step() or next_step()
          → _emit_state_change()
              → _on_step_state_changed(state)
                  → _update_ui_from_state()
                  → pane.set_step(...)
```

**CORRECT**: Navigation methods in StepManager emit state changes automatically.

### 5. File Navigation
```
User clicks prev/next file
  → _on_prev_file() or _on_next_file()
      → step_manager.prev_file() or next_file()
          → load_item() for new file
          → _emit_state_change()
              → _on_step_state_changed(state)
                  → _update_ui_from_state()
                  → pane.set_step(...)
```

**CORRECT**: File navigation handles loading and emits state changes.

## Protection Mechanisms

### 1. Recursion Guard in StepManager
```python
# step_manager.py:105
self._emitting_state_change: bool = False

# step_manager.py:414-427
def _emit_state_change(self):
    if self._emitting_state_change:
        return  # Prevent recursive calls

    if self.on_state_changed:
        try:
            self._emitting_state_change = True
            state = self.get_state()
            self.on_state_changed(state)
        finally:
            self._emitting_state_change = False
```

**Purpose**: Prevents infinite loops if state change callback triggers another state change.

### 2. Single Callback Registration
```python
# output_view.py:89
self.step_manager.on_state_changed = self._on_step_state_changed
```

**Verification**: Only one callback registered, no duplicate listeners.

## Potential Issues Fixed

### Issue 1: Duplicate Render Calls
**Problem**: `_on_step_browser_selected()` was calling `pane.set_step()` and `_update_ui_from_state()` directly, but state change callback also calls them.

**Fix**: Removed duplicate calls, only call `set_current_step()` to trigger state change.

**Location**: `output_view.py:763-774`

### Issue 2: Initial Load Duplicates
**Problem**: `_load_output_async()` was calling `set_current_step()`, `pane.set_step()`, and `_update_ui_from_state()`, but `step_browser.load_steps()` already triggers the full chain.

**Fix**: Removed all duplicate calls, rely on `step_browser.load_steps()` to trigger the chain.

**Location**: `output_view.py:584-594`

### Issue 3: WebView set_content() Signature
**Problem**: Using named parameters `set_content(root_url=..., content=...)` instead of positional parameters.

**Root Cause**: Old working implementation used `set_content("", html)` with positional args and base64 data URLs.

**Fix Applied**:
1. Original files: Use `set_content("", html_content)` with base64-encoded images (line 132)
2. Processed files: Use `set_content(root_url, html_content)` with file:// URLs (line 170)

**Locations**:
- `output_pane.py:132` - Original file rendering
- `output_pane.py:170` - Processed file rendering

## Testing Checklist

- [x] Recursion guard prevents infinite loops
- [ ] Single render per step selection
- [ ] Original file displays correctly
- [ ] Processed files display correctly
- [ ] Step browser selection works
- [ ] Dropdown selection works
- [ ] Prev/Next step buttons work
- [ ] Prev/Next file buttons work
- [ ] No duplicate WebView updates
- [ ] Performance is acceptable

## Summary

**Key Principle**: All navigation flows through `set_current_step()` → state change event → single update path.

**Benefits**:
- Single responsibility for UI updates
- No duplicate render calls
- Easy to debug (single callback point)
- Recursion protection prevents crashes

**Files Modified**:
1. `step_manager.py` - Added recursion guard
2. `output_pane.py` - Fixed image path to use file:// URL
3. `output_view.py` - Removed duplicate render calls in two places
