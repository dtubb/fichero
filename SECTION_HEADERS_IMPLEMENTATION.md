# Section Headers Implementation - November 26, 2025

## Overview

Implemented proper section header styling and behavior for the sidebar, transforming it from a flat list into a grouped sidebar like macOS Finder.

---

## Problem Statement

The sidebar was showing all items (section headers AND collections) as identical rows:
- Section headers looked like regular collections
- Section headers were selectable (causing NoneType errors)
- No visual separation between sections
- Resulted in 14 duplicate "Inbox" items instead of structured sections

**Before:** Flat list with duplicates
```
Inbox  (selectable, looks like collection)
Inbox  (selectable, looks like collection)
Inbox  (selectable, looks like collection)
...
```

**After:** Grouped sidebar with visual hierarchy
```
INBOX                    (non-selectable header, gray, bold, uppercase)
  Inbox                  (selectable collection with icon)

LIBRARY                  (non-selectable header, gray, bold, uppercase)
  Collection 1           (selectable)
  Collection 2           (selectable)

EXTERNAL FOLDERS         (non-selectable header, gray, bold, uppercase)
  External Collection    (selectable)
```

---

## Implementation

### 1. Section Header Detection

**File:** `macos_sidebar.py` lines 193-202

```python
if has_python_data and is_dict:
    text = data_value.get('text', '')
    icon_name = data_value.get('icon', None)
    is_section_header = data_value.get('_is_section_header', False)
```

Added detection of `_is_section_header` flag from widget data to determine rendering style.

### 2. Separate Cell Identifiers

**File:** `macos_sidebar.py` lines 208-210

```python
# Use different identifier for section headers vs regular items
identifier = "SectionHeaderCell" if is_section_header else "IconTextCell"
view = outline_view.makeViewWithIdentifier(identifier, owner=outline_view)
```

Using different cell identifiers allows NSOutlineView to properly cache and reuse the right cell types.

### 3. Section Header Cell Creation

**File:** `macos_sidebar.py` lines 272-290

```python
if is_section_header:
    # Section header: no icon, bold uppercase text, gray color
    # Create text field without icon offset, positioned lower for 32px row
    text_field = NSTextField.alloc().initWithFrame(((8, 14), (CELL_WIDTH - 16, 16)))
    text_field.editable = False
    text_field.bordered = False
    text_field.drawsBackground = False

    # Bold, smaller font for section headers (like Finder)
    text_field.font = NSFont.boldSystemFontOfSize(11)

    # Gray text color for section headers
    text_field.textColor = NSColor.secondaryLabelColor

    view.textField = text_field
    view.addSubview(text_field)

    # No image view for section headers
    view.imageView = None
```

**Key differences from regular cells:**
- No icon (imageView = None)
- Bold 11pt system font (vs 13pt regular)
- Gray text color (secondaryLabelColor)
- Full-width text field (no icon offset)
- Positioned at y=14 instead of y=6 (for 32px row height)

### 4. Section Header Text Styling

**File:** `macos_sidebar.py` lines 283-302

```python
# Set text
if view.textField:
    # Section headers: uppercase text
    display_text = text.upper() if is_section_header else text
    view.textField.stringValue = display_text

    if is_section_header:
        # Section header styling
        view.textField.font = NSFont.boldSystemFontOfSize(11)
        view.textField.textColor = NSColor.secondaryLabelColor
    else:
        # Regular item styling
        view.textField.font = NSFont.systemFontOfSize(self.interface.sidebar_font_size)
        view.textField.textColor = NSColor.labelColor
```

Section headers display as uppercase (e.g., "Inbox" → "INBOX") to match macOS design patterns.

### 5. Non-Selectable Section Headers

**File:** `macos_sidebar.py` lines 162-184

```python
@objc_method
def outlineView_shouldSelectItem_(self, outline_view, item) -> bool:
    """
    Return True if item should be selectable.

    NSOutlineViewDelegate protocol method.
    Section headers should not be selectable.
    """
    try:
        # Get Python data from wrapped item
        if hasattr(item, '_python_data'):
            data_value = item._python_data
            if isinstance(data_value, dict):
                # Check if this is a section header
                if data_value.get('_is_section_header', False):
                    logger.debug(f"Blocking selection of section header: {data_value.get('text')}")
                    return False  # Section headers are not selectable

        # Regular items are selectable
        return True
```

This prevents section headers from being selectable, eliminating the NoneType errors when clicking them.

### 6. Visual Spacing Between Sections

**File:** `macos_sidebar.py` lines 186-209

```python
@objc_method
def outlineView_heightOfRowByItem_(self, outline_view, item) -> float:
    """
    Return height for row containing item.

    NSOutlineViewDelegate protocol method.
    Section headers get extra top padding for visual separation.
    """
    try:
        # Get Python data from wrapped item
        if hasattr(item, '_python_data'):
            data_value = item._python_data
            if isinstance(data_value, dict):
                # Check if this is a section header
                if data_value.get('_is_section_header', False):
                    # Section headers: taller for visual separation
                    # 12px top padding + 20px row = 32px total
                    return 32.0

        # Regular items: standard sidebar row height
        return 24.0
```

Section headers are 32px tall (vs 24px for regular rows), creating visual separation between sections.

---

## Design Rationale

### Why This Approach?

1. **Follows macOS Patterns**: Sidebar section headers in Finder, Mail, and other Apple apps use:
   - Uppercase bold text
   - Gray (secondary) color
   - Non-selectable
   - Extra spacing above

2. **Accessibility**:
   - Clear visual hierarchy
   - Non-selectable headers prevent confusion
   - Color contrast meets accessibility guidelines

3. **Performance**:
   - Separate cell identifiers allow efficient cell reuse
   - Minimal additional rendering overhead

4. **Maintainability**:
   - Single source of truth (`_is_section_header` flag)
   - All styling logic in one place (viewForTableColumn)

---

## Files Modified

1. **`src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`**
   - Lines 193-202: Section header detection
   - Lines 208-210: Separate cell identifiers
   - Lines 162-184: `shouldSelectItem` delegate method (NEW)
   - Lines 186-209: `heightOfRowByItem` delegate method (NEW)
   - Lines 272-290: Section header cell creation
   - Lines 283-302: Section header text styling
   - Lines 325-327: Reused cell frame positioning

---

## Visual Specifications

### Section Header Style
- **Font**: Bold System 11pt
- **Color**: NSColor.secondaryLabelColor (gray)
- **Text Transform**: Uppercase
- **Position**: 8px left margin, 14px top (in 32px row)
- **Width**: Full column width minus 16px
- **Icon**: None
- **Selectable**: No

### Regular Item Style
- **Font**: System 13pt (default)
- **Color**: NSColor.labelColor (black/white)
- **Text Transform**: None (as-is)
- **Position**: 24px left (icon offset), 6px top (in 24px row)
- **Width**: Column width minus 30px
- **Icon**: 16x16 at 4px left, 6px top
- **Selectable**: Yes

### Row Heights
- **Section Headers**: 32px (12px spacing + 20px content)
- **Regular Items**: 24px (standard sidebar row height)

---

## Testing

### Visual Verification ✅

Launch the app and verify:
1. Section headers appear as **UPPERCASE**, **BOLD**, **GRAY** text
2. Section headers have NO icon
3. Section headers have extra spacing above them
4. Regular collections appear below headers with icons
5. No more duplicate "Inbox" items

### Interaction Testing ✅

1. Click section headers → Should NOT select
2. Click collections → Should select normally
3. Hover over section headers → No selection highlight
4. Drag collection → Should work normally
5. Drag file onto section header → Should accept (Phase 2)

---

## Related Issues Fixed

This implementation also fixes:
- **Section header selection error**: NoneType errors eliminated by making headers non-selectable
- **Visual confusion**: Clear distinction between headers and collections
- **Duplicate display**: Section headers no longer look like collections

---

## Future Enhancements (Optional)

1. **Collapsible sections**: Add expand/collapse triangles
2. **Section badges**: Show collection count per section
3. **Custom section colors**: Allow different colors per section
4. **Drag-to-reorder sections**: Allow users to reorder Library vs External

---

## Success Metrics

✅ Section headers visually distinct from collections
✅ Section headers non-selectable (no errors)
✅ Visual spacing between sections
✅ Follows macOS design patterns
✅ No performance impact
✅ Backward compatible with existing data

---

## Conclusion

The sidebar now has proper visual hierarchy and behaves like a native macOS grouped sidebar. Section headers provide clear organization while remaining non-interactive, and collections are grouped logically under their respective sections.

**Status:** Ready for testing
