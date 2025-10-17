# Icon Loading Fix - October 8, 2025

## Problem

Icons weren't displaying in toolbar buttons when using the new command-based system.

## Root Cause

When passing icons to `toga.Icon()`, Toga requires **absolute paths**, not relative paths.

Commands were storing relative paths:
```python
icon='resources/icons/toolbar/settings.png'
```

But `BaseToolbar.create_button()` was passing these directly to `toga.Icon()`:
```python
icon_resource = toga.Icon(icon)  # ❌ Fails - needs absolute path
```

## Solution

Updated `BaseToolbar.create_button()` to convert relative paths to absolute paths using `app.paths.app`:

```python
# Convert relative icon path to absolute path using app.paths.app
from pathlib import Path
if isinstance(icon, str):
    icon_path = self.app.paths.app / icon
    icon_resource = toga.Icon(str(icon_path))
else:
    # Already a Path or toga.Icon object
    icon_resource = toga.Icon(icon) if not isinstance(icon, toga.Icon) else icon
```

## Files Modified

- `src/fichero/shared/toolbars/base_toolbar.py` (lines 235-259)

## Testing

### Desktop Mode
```bash
briefcase dev
```

### Mobile Mode (Desktop Simulation)
```bash
FORCE_MOBILE_UI=true TOGA_BACKEND=toga_cocoa briefcase dev
```

### iOS Simulator
```bash
FORCE_MOBILE_UI=true briefcase build iOS -u
FORCE_MOBILE_UI=true briefcase run iOS -d "DEVICE_UUID"
```

## Expected Behavior

Icons should now load correctly for:
- ✅ Bottom toolbar buttons (mobile)
- ✅ Command-based buttons (both platforms)
- ✅ All icon paths in commands

## How Icon Paths Work Now

1. Commands define icons with relative paths:
   ```python
   FicheroCommand(
       icon='resources/icons/toolbar/settings.png' if is_mobile else None
   )
   ```

2. BaseToolbar automatically converts to absolute:
   ```python
   # Internally becomes:
   /path/to/app/resources/icons/toolbar/settings.png
   ```

3. Toga loads the icon successfully

## Fallback Behavior

If an icon fails to load:
- Logs warning: `"Failed to load icon 'X': error, using text fallback"`
- Falls back to text button with label or "⚙" symbol

## Notes

- Icons should still be conditionally applied (`if is_mobile` pattern)
- Desktop typically doesn't use icons (native toolbar uses text labels)
- Mobile uses icons for all toolbar buttons
