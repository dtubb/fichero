# Drag & Drop Final Fixes - AttributeError and Section Headers

**Date**: November 30, 2025
**Status**: ✅ FIXED - Ready for Testing

## Issues Fixed

### **Issue 1: AttributeError - Method Access from ObjC Context** ✅

**Error**:
```
AttributeError: rubicon.objc.api.ObjCInstance TogaSidebar has no attribute _find_item_by_id
```

**Root Cause**:
- `_find_item_by_id()` and `_is_descendant_of()` are methods on `NSOutlineViewSidebar` class
- Called from within `@objc_method` on `TogaSidebar` class (inner class)
- In Rubicon-ObjC, `self` inside `@objc_method` refers to the `TogaSidebar` instance, NOT the outer class
- Methods exist on `NSOutlineViewSidebar`, accessible via `self.interface`

**Fix**:
Changed method calls from `self.method()` to `self.interface.method()`

**File**: `macos_sidebar.py`, lines 1096, 1099

**Before**:
```python
dragged_item_data = self._find_item_by_id(self.interface._data, dragged_id)
if self._is_descendant_of(parent_data, dragged_id):
```

**After**:
```python
dragged_item_data = self.interface._find_item_by_id(self.interface._data, dragged_id)
if self.interface._is_descendant_of(parent_data, dragged_id):
```

---

### **Issue 2: Section Headers Rejecting All Drops** ✅

**Problem**:
```
DEBUG: Drop validation - parent: Library, index: 4
DEBUG: ❌ Target 'Library' does not accept drops (_can_accept_drops=False)
```

**User Requirement**:
- Section headers (Favorites, Library) should accept drops **INTO** them (as children, between items)
- But should NOT accept drops **ONTO** the header row itself
- Inbox should reject ALL drops (both onto and into)

**Root Cause**:
- Library section had `_can_accept_drops=False`
- Code rejected ALL drops if `_can_accept_drops=False`, regardless of whether dropping ONTO header or INTO section

**Fix**:
Added special handling for section headers:
1. If `_can_accept_drops=False` AND item is section header → Skip rejection (allow INTO section)
2. If `_can_accept_drops=False` AND item is NOT section header → Reject (Inbox)
3. Existing check already rejects dropping ONTO section header (when `index == -1`)

**File**: `macos_sidebar.py`, lines 1081-1090

**Code**:
```python
# Check _can_accept_drops flag - False means reject ALL drops (Inbox only)
# NOTE: Section headers checked separately (allow INTO section, not ONTO header)
if '_can_accept_drops' in parent_data and not parent_data['_can_accept_drops']:
    # Only reject if this is NOT a section header
    # Section headers can accept drops INTO them (index >= 0), just not ONTO them (index == -1)
    if not parent_data.get('_is_section_header'):
        target_name = parent_data.get('text', 'unknown')
        logger.debug(f"❌ Target '{target_name}' does not accept drops (_can_accept_drops=False)")
        return 0  # Reject
```

**Demo Data Update**:
Changed section headers to `_can_accept_drops': True` for clarity (they DO accept drops into them)

**File**: `widget_list_demo.py`, lines 290, 308

**Before**:
```python
{'_node_type': 'section', '_is_section_header': True,
 'text': 'Library', 'icon': 'folder',
 '_draggable': False, '_can_accept_drops': False, '_drop_types': [],
```

**After**:
```python
{'_node_type': 'section', '_is_section_header': True,
 'text': 'Library', 'icon': 'folder',
 '_draggable': False, '_can_accept_drops': True, '_drop_types': ['collection', 'folder', 'file'],
```

---

## Complete Validation Rules

After these fixes, the validation logic is:

### **1. Section Headers**
- **Dropping ONTO header** (`index == -1`): ❌ REJECTED (lines 1037-1044)
- **Dropping INTO section** (`index >= 0`): ✅ ALLOWED (shows line indicator)
- **Example**: Drag "Photos" between "Documents" and "Videos" under Library → Line indicator appears

### **2. Inbox Collection**
- **All drops**: ❌ REJECTED (`_can_accept_drops=False`, line 1088)
- **Example**: Drag anything onto Inbox → Rejected, no indicator

### **3. Circular References**
- **Dragging parent onto child**: ❌ REJECTED (lines 1092-1102)
- **Example**: Drag "2024" onto "Week 1" (its grandchild) → Rejected

### **4. Everything Else**
- **All other drops**: ✅ ALLOWED (shows blue highlight or line indicator)
- **Examples**:
  - Drag folder onto folder → Blue highlight
  - Drag collection onto collection → Blue highlight
  - Drag between siblings → Line indicator

---

## Expected Behavior After Fix

### ✅ **Test 1: Drag into Library section**
- Drag "Photos" collection under Library section (between items)
- **Expected**: Line indicator appears between items
- **Log**: `✅ Drop BETWEEN items - LINE at index X`

### ✅ **Test 2: Drag onto Library section header**
- Drag "Photos" directly onto "Library" header row
- **Expected**: Rejected, no indicator
- **Log**: `❌ Cannot drop directly onto section header 'Library'`

### ✅ **Test 3: Drag folder onto folder**
- Drag "2024" folder onto "January" folder
- **Expected**: Blue highlight appears on "January"
- **Log**: `✅ Drop INTO 'January' - BLUE on row X`

### ✅ **Test 4: Drag onto Inbox**
- Drag anything onto "Inbox" collection
- **Expected**: Rejected, no indicator
- **Log**: `❌ Target 'Inbox' does not accept drops`

### ✅ **Test 5: Circular reference**
- Drag "2024" onto "Week 1" (its grandchild)
- **Expected**: Rejected, no indicator
- **Log**: `❌ Cannot drag parent onto its own child (circular reference)`

---

## Files Modified

1. **macos_sidebar.py**:
   - Lines 1096, 1099: Fixed method access (`self.interface.method()`)
   - Lines 1081-1090: Added section header special handling

2. **widget_list_demo.py**:
   - Lines 290, 308: Updated section headers to `_can_accept_drops': True`

---

## Summary

**Issue 1**: AttributeError calling `_find_item_by_id()`
**Fix**: Access via `self.interface._find_item_by_id()`
**Result**: ✅ Circular reference check now works

**Issue 2**: Library section rejecting all drops
**Fix**: Skip rejection for section headers (allow INTO section)
**Result**: ✅ Can drop between items under Library section

**Testing**: All drag & drop scenarios should now work correctly!
