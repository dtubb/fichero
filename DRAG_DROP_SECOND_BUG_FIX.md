# Second Drag-and-Drop Bug Fix

**Date:** November 25, 2025
**Issue:** TypeError when accessing NSArray.count
**Status:** FIXED ✅

---

## Problem

After fixing the first bug (property vs method for `draggingPasteboard`), a second error appeared:

```
TypeError: 'method' object cannot be interpreted as an integer
```

**Error Location:**
- File: `macos_sidebar.py`
- Line: `for i in range(types.count):`

---

## Root Cause

**The confusion:** `count` is a METHOD in NSArray, not a property!

### Incorrect:
```python
for i in range(types.count):  # ❌ Error!
```

### Correct:
```python
type_count = types.count()  # ✅ Call the method
for i in range(type_count):
```

---

## Why This is Confusing

In many Python collections, `count` is an attribute or method that can be accessed both ways:
- Python lists: `len(list)` or `list.__len__()`
- Some objects: `.count` as property

But in **Objective-C's NSArray**, `count` is explicitly a method:
```objc
// Objective-C
NSUInteger count = [array count];
```

In Rubicon-ObjC, this translates to:
```python
# Rubicon-ObjC
count = array.count()  # Must call as method
```

---

## The Fix

### Both delegate methods needed the same fix:

1. **outlineView_validateDrop_proposedItem_proposedChildIndex_** (line 389)
2. **outlineView_acceptDrop_item_childIndex_** (line 444)

### Before:
```python
for i in range(types.count):  # ❌ TypeError
    type_str = str(types.objectAtIndex(i))
```

### After:
```python
type_count = types.count()  # ✅ Call method
for i in range(type_count):
    type_str = str(types.objectAtIndex(i))
```

---

## Complete Rubicon-ObjC Pattern Reference

### Properties (No Parentheses)

| Objective-C | Rubicon-ObjC | Error if Called |
|-------------|--------------|-----------------|
| `[info draggingPasteboard]` | `info.draggingPasteboard` | `info.draggingPasteboard()` ❌ |
| `[pasteboard types]` | `pasteboard.types` | `pasteboard.types()` ❌ |
| `[item _python_data]` | `item._python_data` | N/A (Python attr) |

### Methods (With Parentheses)

| Objective-C | Rubicon-ObjC | Error if Not Called |
|-------------|--------------|---------------------|
| `[types count]` | `types.count()` | `types.count` ❌ |
| `[types objectAtIndex:i]` | `types.objectAtIndex(i)` | `types.objectAtIndex` ❌ |
| `[pasteboard stringForType:t]` | `pasteboard.stringForType(t)` | N/A |

---

## Decision Tree for Property vs Method

When using Rubicon-ObjC:

```
Is it mentioned in Apple's documentation?
├─ YES → Check docs for "Property" vs "Instance Method"
│   ├─ "Property" → Use without (): obj.property
│   └─ "Instance Method" → Use with (): obj.method()
└─ NO → Try it and handle the error
    ├─ TypeError: 'ObjCInstance' object is not callable
    │   → It's a property, remove ()
    └─ TypeError: 'method' object cannot be interpreted as...
        → It's a method, add ()
```

---

## Updated Code Sections

### outlineView_validateDrop (Lines 389-396)

```python
# Get types (property, not method)
types = pasteboard.types

# Check if our custom UTI is in types
has_collection_uti = False
has_file_url = False

# count() is a method, not a property
type_count = types.count()  # ✅ Fixed
for i in range(type_count):
    type_str = str(types.objectAtIndex(i))
    if type_str == UTI:
        has_collection_uti = True
    elif type_str == "public.file-url":
        has_file_url = True
```

### outlineView_acceptDrop (Lines 444-451)

```python
# Get types (property, not method)
types = pasteboard.types

# Check types by iterating NSArray
has_collection_uti = False
has_file_url = False

# count() is a method, not a property
type_count = types.count()  # ✅ Fixed
for i in range(type_count):
    type_str = str(types.objectAtIndex(i))
    if type_str == UTI:
        has_collection_uti = True
    elif type_str == "public.file-url":
        has_file_url = True
```

---

## New Unit Tests Added

**File:** `tests/unit/test_rubicon_objc_patterns.py`

This comprehensive test file documents all Rubicon-ObjC patterns to prevent future regressions.

### Test Classes:

1. **TestRubiconObjCPatterns**
   - Documents property vs method access patterns
   - Serves as reference for future development

2. **TestNSArrayIterationPattern**
   - Tests correct NSArray iteration
   - Tests that wrong patterns fail as expected
   - `test_nsarray_wrong_pattern_fails` - Verifies TypeError occurs with wrong pattern

3. **TestDragTypeCheckingPattern**
   - Tests checking for UTI types in pasteboard
   - Tests checking multiple types in one pass
   - Mirrors actual drag-and-drop validation logic

4. **TestCommonRubiconMistakes**
   - `test_mistake_calling_property_as_method` - First bug
   - `test_mistake_not_calling_method` - Second bug
   - Documents errors to avoid

5. **TestRubiconReferenceGuide**
   - Reference tables for quick lookup
   - Decision tree for property vs method
   - Comprehensive documentation

**Total:** 15+ test methods serving as documentation and regression prevention

---

## Lessons Learned

### 1. Always Check Apple Documentation

For any Objective-C class:
1. Go to https://developer.apple.com/documentation/
2. Search for the class (e.g., "NSArray")
3. Look for the specific member:
   - **Property** section → Use without ()
   - **Instance Methods** section → Use with ()

### 2. Common Gotchas in NSArray

```python
# ❌ Wrong assumptions from other languages
array.length  # Doesn't exist in NSArray
array.size  # Doesn't exist
len(array)  # Doesn't work (it's not a Python list)

# ✅ Correct NSArray patterns
count = array.count()  # Get length
item = array.objectAtIndex(i)  # Get item at index
```

### 3. Testing Strategy

When working with Rubicon-ObjC:
1. Write unit tests with mocks to document patterns
2. Test with real Objective-C objects to verify
3. Add comprehensive error messages for debugging
4. Keep reference documentation updated

---

## Testing Verification

### Manual Testing

After this fix, drag-and-drop should work:

```bash
# Run the app
briefcase dev

# Test scenarios:
1. Drag a file from Finder → Should show copy cursor
2. Drag a folder from Finder → Should show copy cursor
3. Drop the file/folder → Should import successfully
4. Drag a collection to reorder → Should show move cursor
5. Drop to reorder → Should update position
```

### Automated Testing

```bash
# Run the new Rubicon patterns tests
PYTHONPATH=src python3 -m pytest tests/unit/test_rubicon_objc_patterns.py -v

# Run all drag-and-drop tests
PYTHONPATH=src python3 -m pytest tests/unit/test_drag_and_drop.py -v
```

---

## Summary of All Fixes

### First Bug (Initial Fix)
- **Issue:** Calling properties as methods
- **Error:** `TypeError: 'ObjCInstance' object is not callable`
- **Fix:** Remove `()` from property access
- **Examples:** `draggingPasteboard()` → `draggingPasteboard`

### Second Bug (This Fix)
- **Issue:** Not calling methods
- **Error:** `TypeError: 'method' object cannot be interpreted as an integer`
- **Fix:** Add `()` to method calls
- **Examples:** `types.count` → `types.count()`

### Pattern Summary

| Member | Type | Access Pattern | Example |
|--------|------|----------------|---------|
| `draggingPasteboard` | Property | No `()` | `drag_info.draggingPasteboard` |
| `types` | Property | No `()` | `pasteboard.types` |
| `count` | Method | With `()` | `types.count()` |
| `objectAtIndex` | Method | With `(param)` | `types.objectAtIndex(i)` |
| `stringForType` | Method | With `(param)` | `pasteboard.stringForType(uti)` |

---

## Files Modified

1. **src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py**
   - Line 390: `type_count = types.count()` (was `types.count`)
   - Line 445: `type_count = types.count()` (was `types.count`)

2. **tests/unit/test_rubicon_objc_patterns.py**
   - NEW FILE: Comprehensive Rubicon-ObjC pattern documentation
   - 15+ test methods documenting correct patterns
   - Serves as reference and regression prevention

3. **DRAG_DROP_BUG_FIX.md**
   - Updated to reflect correct `count()` usage
   - Added clarification about method vs property
   - Updated code examples

---

## Ready for Testing ✅

Both bugs are now fixed! The drag-and-drop functionality should work correctly.

**Test it with:**
- Files (should create local collection)
- Folders (should create external collection)
- Multiple items (should import all)
- Collection reordering (should update positions)

All patterns are now documented in tests and reference guides to prevent future regressions!
