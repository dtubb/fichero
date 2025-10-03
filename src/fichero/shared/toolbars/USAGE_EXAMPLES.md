# Toolbar System Usage Examples

## New HIG-Compliant Architecture

The refactored toolbar system provides:
- **ToolbarCoordinator**: Manages edit mode state across top/bottom toolbars
- **BaseToolbar**: HIG-compliant base with iOS/macOS platform detection
- **TopToolbar**: Navigation + edit mode button that controls bottom toolbar
- **BottomToolbar**: Normal/edit mode button variations

## Basic Usage

### 1. Setting up Coordinated Toolbars

```python
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar

# Create coordinator for edit mode management
coordinator = ToolbarCoordinator(app, is_mobile=app.is_mobile)

# Create toolbars with coordinator integration
top_toolbar = TopToolbar(
    app=app,
    title="Collection",
    auto_mobile_nav=True,  # Child view with back button
    coordinator=coordinator
)

bottom_toolbar = BottomToolbar(
    app=app,
    coordinator=coordinator
)

# Toolbars automatically register with coordinator
```

### 2. Edit Mode Integration

When user taps "Edit" in TopToolbar:

```python
# TopToolbar automatically calls:
coordinator.set_edit_mode(EditModeState.EDIT)

# This triggers:
# 1. TopToolbar shows "Done" button, hides "Edit" button
# 2. BottomToolbar shows edit actions (Delete, Select All, Share)
# 3. Both toolbars get the same edit mode state
```

### 3. Adding Custom Buttons

```python
# Add normal mode buttons to bottom toolbar
bottom_toolbar.add_normal_mode_button(
    text="Add Item",
    icon="plus",
    position="center"
)

# Add custom edit mode buttons
bottom_toolbar.add_edit_mode_button(
    text="Move",
    on_press=handle_move,
    style_class="primary"
)

# Add buttons to top toolbar
top_toolbar.add_button_right(
    text="Settings",
    icon="gear",
    on_press=show_settings
)
```

### 4. Handling Edit Mode Changes

```python
def on_edit_mode_change(state: EditModeState, context: dict):
    if state == EditModeState.EDIT:
        # Update view for edit mode
        enable_selection_mode()
    else:
        # Return to normal mode
        disable_selection_mode()

# Register callback
coordinator.on_edit_mode_change = on_edit_mode_change
```

### 5. Platform-Specific Behavior

```python
# Automatic platform detection
if top_toolbar.is_mobile:
    # iOS HIG behavior:
    # - Navigation bar: 44pt height
    # - Back button: "‹ Library"
    # - Tab bar: 49pt height
    pass
else:
    # macOS HIG behavior:
    # - Toolbar: 52pt height
    # - Back button: "‹ Back"
    # - Bottom toolbar: hidden
    pass
```

## Backward Compatibility

The new system maintains backward compatibility:

```python
# Legacy methods still work
top_toolbar.add_centered_title_only("My Title")
top_toolbar.add_button_text_right("Edit", on_press=edit_handler)
top_toolbar.register_edit_callback(edit_handler)

# NavigationController integration is automatic
# No need to manually set up back handlers
```

## Edit Mode Flow

1. **Normal Mode**:
   - TopToolbar: [Back] [Title] [Edit]
   - BottomToolbar: [Custom buttons from view]

2. **User taps Edit**:
   - TopToolbar: [Title] [Done] (back button hidden on mobile)
   - BottomToolbar: [Select All] [Share] [Delete]

3. **User selects items**:
   - Context updates with selected_count
   - BottomToolbar enables/disables buttons based on selection

4. **User taps Done**:
   - Returns to normal mode
   - Restores original button layout

## HIG Compliance Features

### iOS
- Standard navigation bar height (44pt)
- Tab bar height (49pt, 83pt with home indicator)
- Touch targets (44x44pt minimum)
- SF Symbols icon sizes (22pt)
- iOS blue (#007AFF) and red (#FF3B30) colors

### macOS
- Standard toolbar height (52pt)
- Smaller touch targets (32x32pt)
- macOS icon sizes (16pt)
- Bottom toolbar hidden by default
- macOS blue (#0066CC) colors

This architecture provides a clean, maintainable toolbar system that follows platform conventions and provides excellent edit mode functionality.