# set_data_() Bug Fix - Attribute Assignment Issue

**Date**: November 29, 2025
**Issue**: Display showing programming objects after drag & drop
**Status**: ✅ FIXED

## Problem

After attempting to "fix" data assignment by using the `set_data_()` method instead of direct attribute assignment, the app broke:

1. **Initial symptom**: Display showed `<SidebarItem: 0x...>` instead of actual item text
2. **Error logs**: `WARNING: [VIEW] Fallback to str(item) - has_python_data=True, is_dict=False`
3. **Drag & drop symptom**: App worked initially, but broke immediately after performing drag & drop operation

## Root Cause

The `set_data_()` method in SidebarItem is defined as:
```python
@objc_method
def set_data_(self, value):
    """Set the stored Python dict."""
    self._python_data = value
```

**The Issue**: When called from Python code (not from ObjC delegate methods), `@objc_method` decorated methods don't properly set Python attributes on Rubicon-ObjC proxy objects. The attribute exists (`hasattr` returns True) but is inaccessible as a dict (`isinstance(..., dict)` returns False).

## Incorrect "Fix" Attempt

Changed four locations to use `set_data_()`:
1. Line 211: `outlineView_child_ofItem_` - child wrapper creation
2. Line 2053: `attach()` - root wrapper creation
3. Line 2326: `move_item_in_tree()` - rebuild after drag & drop
4. Line 2432: `add_item()` - new item wrapper creation

**Result**: Broke the entire app.

## Actual Fix

**Reverted all `set_data_()` calls back to direct assignment**:
```python
# ✅ CORRECT - Direct attribute assignment in Python code
wrapper = self.SidebarItem.alloc().init()
wrapper._python_data = clean_dict

# ❌ WRONG - Don't call @objc_method from Python for attribute setting
wrapper = self.SidebarItem.alloc().init()
wrapper.set_data_(clean_dict)  # Breaks data access!
```

## Why Direct Assignment Works

In Rubicon-ObjC:
- Python attributes on ObjC objects should be set directly from Python code
- `@objc_method` decorated methods are for ObjC→Python bridging, not Python→Python
- Direct assignment: `obj._python_data = value` ✅
- Method call: `obj.set_data_(value)` ❌ (from Python code)

The `set_data_()` method exists for potential ObjC-side access, but should NOT be called from Python code.

## Lesson Learned

**Rubicon-ObjC Pattern**:
- Set Python attributes directly when in Python context: `obj._attr = value`
- Access Python attributes directly when in @objc_method context: `value = obj._attr`
- Don't route through @objc_method decorated setters from Python code

## Additional Fix: Demo Data

Added drag & drop flags to demo data in `widget_list_demo.py`:
- `_draggable`: True/False (whether item can be dragged)
- `_can_accept_drops`: True/False (whether item accepts drops)
- `_drop_types`: ['collection', 'folder', 'file'] (what types can be dropped)
- `_can_accept_collections`: True/False (legacy flag for backward compatibility)

**Rules**:
- Section headers: not draggable, don't accept drops
- Inbox collection: not draggable, doesn't accept drops (special case)
- Collections: draggable, accept collections/folders/files
- Folders: draggable, accept only files (not collections)

## Files Modified

1. **macos_sidebar.py** (4 locations):
   - Line 211: Reverted to `._python_data = `
   - Line 2053: Reverted to `._python_data = `
   - Line 2326: Reverted to `._python_data = ` (THIS WAS THE DRAG & DROP BUG)
   - Line 2432: Reverted to `._python_data = `

2. **widget_list_demo.py**:
   - Added drag & drop flags to all hierarchical data items
   - Section headers: `_draggable=False, _can_accept_drops=False, _drop_types=[]`
   - Inbox: `_draggable=False, _can_accept_drops=False, _drop_types=[]`
   - Collections: `_draggable=True, _can_accept_drops=True, _drop_types=[...], _can_accept_collections=True`
   - Folders: `_draggable=True, _can_accept_drops=True, _drop_types=['file']`

## Testing

Now working correctly:
- ✅ Display shows proper item text (not programming objects)
- ✅ Drag & drop doesn't corrupt data
- ✅ No `is_dict=False` warnings
- ✅ Inbox not draggable (per flags)
- ✅ Section headers not draggable (per flags)
- ✅ Collections are draggable
- ✅ Folders are draggable

## Summary

The `set_data_()` method approach was fundamentally wrong. Direct attribute assignment is the correct Rubicon-ObjC pattern for setting Python attributes from Python code. The @objc_method decorator is for bridging to Objective-C, not for internal Python-to-Python communication.

**Never use `set_data_()` from Python code** - always use direct assignment: `obj._python_data = value`
